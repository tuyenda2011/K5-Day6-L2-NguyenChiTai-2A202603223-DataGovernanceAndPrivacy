"""Budgeted vendor audits: random baseline or risk-stratified finite-population inference.

Selection never sees labels. Only AuditOracle can reveal selected outcomes.
Intervals invert hypergeometric tails; stratified bounds use Bonferroni.
Scheduled sequential looks spend alpha across both looks and strata.
"""
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import hypergeom

from ..common.audit_oracle import AuditOracle
from ..common.contact_sheet import render_contact_sheet
from ..common.decision import Decision, write_decision
from ..common.io import config_hash, load_config, write_json, sha256_file
from ..common.manifest import verify_manifest
from ..common.review import load_review_decisions, make_review_queue, write_review_queue


@lru_cache(maxsize=4096)
def finite_interval(errors, audited, population, alpha=0.05):
    """Exact two-sided confidence set for a fixed population sampled without replacement."""
    if not 0 <= errors <= audited <= population or population < 1 or not 0 < alpha < 1:
        raise ValueError("invalid population, audit count, error count or alpha")
    if audited == 0:
        return 0.0, 1.0
    possible = np.arange(errors, population - audited + errors + 1)
    keep = ((hypergeom.cdf(errors, population, possible, audited) >= alpha / 2) &
            (hypergeom.sf(errors - 1, population, possible, audited) >= alpha / 2))
    accepted = possible[keep]
    return float(accepted[0] / population), float(accepted[-1] / population)


def select_samples(batch, budget, rng, strategy="stratified", allocation="proportional"):
    """Fixed allocation before inspecting labels; SRS without replacement within each stratum."""
    if budget < 1 or strategy not in {"random", "stratified"}:
        raise ValueError("positive audit budget and random/stratified strategy required")
    if allocation not in {"proportional", "balanced"}:
        raise ValueError("allocation must be proportional or balanced")
    batch = batch.sort_values("sample_id").copy()
    batch["stratum"] = batch.risk_tag if strategy == "stratified" else "all"
    groups = list(batch.groupby("stratum", sort=True))
    n = min(budget, len(batch))
    if len(groups) > n:
        raise ValueError("budget cannot cover every risk stratum; predefine fewer strata")
    # Commit to a label-blind schedule. Every prefix after H draws covers all strata.
    permutations = {name: group.iloc[rng.permutation(len(group))] for name, group in groups}
    counts = {name: 0 for name, _ in groups}
    parts = []
    for step in range(n):
        available = [(name, g) for name, g in groups if counts[name] < len(g)]
        unseen = [(name, g) for name, g in available if counts[name] == 0]
        if unseen:
            name, group = unseen[0]
        elif allocation == "balanced":
            name, group = min(available, key=lambda pair: (counts[pair[0]], pair[0]))
        else:
            # Largest deficit from proportional population allocation; small strata still get one.
            name, group = min(available, key=lambda pair: (
                counts[pair[0]] - (step + 1) * len(pair[1]) / len(batch), pair[0]))
        picked = permutations[name].iloc[[counts[name]]].copy()
        picked["audit_order"] = step + 1
        picked["stratum_population"] = len(group)
        counts[name] += 1
        parts.append(picked)
    selected = pd.concat(parts, ignore_index=True)
    selected["stratum_audited"] = selected.stratum.map(counts)
    selected["inclusion_probability"] = selected.stratum_audited / selected.stratum_population
    return selected


def audit_stages(population, budget, configured=None):
    cap = min(population, budget)
    if configured is None:
        return [cap]
    if (not isinstance(configured, list) or not configured or
            any(not isinstance(n, int) or isinstance(n, bool) for n in configured) or
            configured != sorted(set(configured)) or configured[-1] != budget or
            configured[0] < min(15, budget)):
        raise ValueError("audit_stages must be increasing integers, start at >= min(15, cap), and end at budget cap")
    return sorted({min(n, population) for n in configured})


def estimate_batch(sample, population, confidence):
    groups = list(sample.groupby("stratum", sort=True))
    estimate = low = high = 0.0
    evidence = []
    for name, group in groups:
        N = int(group.stratum_population.iloc[0])
        n, k = len(group), int(group.is_error.sum())
        lo, hi = finite_interval(k, n, N, (1 - confidence) / len(groups))
        weight = N / population
        estimate += weight * k / n
        low += weight * lo
        high += weight * hi
        evidence.append(dict(stratum=name, population=N, n_audited=n, errors=k,
                             weight=weight, est_error_rate=k / n, ci_low=lo, ci_high=hi))
    return estimate, low, high, evidence


def classify(low, high, threshold):
    if high <= threshold + 1e-12:
        return "ACCEPT", "UPPER_BOUND_WITHIN_LIMIT"
    if low > threshold + 1e-12:
        return "REWORK", "LOWER_BOUND_ABOVE_LIMIT"
    return "HOLD", "INSUFFICIENT_EVIDENCE"


def threshold_test(evidence, population, threshold, max_cells=10_000_000):
    """Exact one-sided p-values of the stratified estimator at the policy limit.

    T = sum_h (N_h/N) X_h/n_h, X_h ~ independent Hypergeom(N_h, K_h, n_h); K0 = floor(limit * N).
      p_rework = sup P(T >= t_obs) over error allocations with sum K_h = K0      (H0: rate <= limit)
      p_accept = sup P(T <= t_obs) over error allocations with sum K_h = K0 + 1  (H0: rate >  limit)
    T is nondecreasing in every X_h and X_h is stochastically increasing in K_h, so the supremum over each
    composite null is attained on its boundary total. Unlike a Bonferroni CI, no alpha is split over strata.
    With one stratum this is exactly the hypergeometric CI rule. Returns None when enumeration is too large.
    """
    Ns = [int(e["population"]) for e in evidence]
    ns = [int(e["n_audited"]) for e in evidence]
    ks = [int(e["errors"]) for e in evidence]
    weights = [N / population for N in Ns]
    k0 = int(np.floor(threshold * population + 1e-9))
    stat = np.zeros([n + 1 for n in ns])
    for h, (n, w) in enumerate(zip(ns, weights)):
        shape = [1] * len(ns)
        shape[h] = n + 1
        stat = stat + (w * np.arange(n + 1) / n).reshape(shape)
    t_obs = sum(w * k / n for w, k, n in zip(weights, ks, ns))

    def sup_probability(mask, total):
        if total > sum(Ns):
            return 0.0  # this null hypothesis cannot hold for the batch
        if np.prod([max(n + 1, min(total, N) + 1) for n, N in zip(ns, Ns)], dtype=float) > max_cells:
            return None
        tensor = mask.astype(float)
        for n, N in zip(ns, Ns):
            K = np.arange(min(total, N) + 1)
            pmf = hypergeom.pmf(np.arange(n + 1)[None, :], N, K[:, None], n)
            tensor = np.tensordot(tensor, pmf, axes=([0], [1]))  # replaces x_h by K_h
        totals = np.zeros(tensor.shape, dtype=int)
        for h, size in enumerate(tensor.shape):
            shape = [1] * tensor.ndim
            shape[h] = size
            totals = totals + np.arange(size).reshape(shape)
        boundary = totals == total
        return float(tensor[boundary].max()) if boundary.any() else 0.0

    p_rework = sup_probability(stat >= t_obs - 1e-12, k0)
    p_accept = sup_probability(stat <= t_obs + 1e-12, k0 + 1)
    if p_rework is None or p_accept is None:
        return None
    return min(p_accept, 1.0), min(p_rework, 1.0)


def decide_by_test(p_accept, p_rework, alpha):
    """Each direction gets alpha/2, the same error budget as the two-sided (1 - alpha) CI rule."""
    accept, rework = p_accept < alpha / 2, p_rework < alpha / 2
    if accept and not rework:
        return "ACCEPT", "EXACT_TEST_WITHIN_LIMIT"
    if rework and not accept:
        return "REWORK", "EXACT_TEST_ABOVE_LIMIT"
    return "HOLD", "INSUFFICIENT_EVIDENCE"


def inspect_batch(plan, population, confidence, threshold, stages, oracle):
    """Stop only at planned looks; Bonferroni over looks protects the stopped CI.

    Sampling order/allocation is frozen before any label is revealed. The stopped
    point estimate can be biased, so sequential results are reported separately.
    """
    observed = plan.iloc[:0].copy()
    history = []
    for look, stop in enumerate(stages, start=1):
        fresh = plan.iloc[len(observed):stop].copy()
        fresh["is_error"] = fresh.sample_id.map(oracle.inspect(fresh.sample_id.tolist()))
        if not fresh.is_error.isin([0, 1]).all():
            raise ValueError("oracle labels must be binary")
        observed = pd.concat([observed, fresh], ignore_index=True)
        if set(observed.stratum) != set(plan.stratum):
            raise ValueError("an audit look must cover every stratum")
        look_confidence = 1 - (1 - confidence) / len(stages)
        estimate, low, high, evidence = estimate_batch(observed, population, look_confidence)
        for row in evidence:
            row["confidence_level"] = look_confidence
            row["simultaneous_batch_confidence"] = confidence
        # round away float noise: (1 - 0.95) / 2 would otherwise be 0.025000000000000022
        alpha_look = round((1 - confidence) / len(stages), 12)
        tested = threshold_test(evidence, population, threshold)
        if tested is None:  # enumeration too large: fall back to the (more conservative) CI rule
            decision, code = classify(low, high, threshold)
            p_accept = p_rework = np.nan
            method = "bonferroni_ci"
        else:
            p_accept, p_rework = tested
            decision, code = decide_by_test(p_accept, p_rework, alpha_look)
            method = "exact_threshold_test"
        history.append(dict(look=look, n_audited=len(observed), errors=int(observed.is_error.sum()),
                            est_error_rate=estimate, ci_low=low, ci_high=high, decision=decision,
                            p_accept=p_accept, p_rework=p_rework, decision_method=method,
                            accept_supported=decision == "ACCEPT",
                            alpha_spent=alpha_look,
                            stop_reason="BOUND_CROSSED" if decision != "HOLD" else
                                        ("BUDGET_EXHAUSTED" if stop == stages[-1] else "CONTINUE")))
        if decision != "HOLD":
            break
    if len(stages) > 1:
        observed["planned_inclusion_probability"] = observed.inclusion_probability
        # Realized n_h/N_h at a label-dependent stopping time is not an inclusion probability.
        observed["inclusion_probability"] = np.nan
    sizes = observed.groupby("stratum").size()
    observed["realized_sampling_fraction"] = observed.stratum.map(sizes) / observed.stratum_population
    return observed, estimate, low, high, evidence, decision, code, history


def apply_review(ctx, predictions, threshold=0.05):
    path = ctx.output_dir / "review_queue_reviewed.csv"
    final = predictions.copy()
    if not path.exists():
        return final
    reviewed = load_review_decisions(path)
    if reviewed.item_id.duplicated().any() or not set(reviewed.item_id) <= set(final.batch_id):
        raise ValueError("review contains duplicate or unknown batch IDs")
    for r in reviewed.itertuples(index=False):
        if r.reviewer_decision == "skip":
            continue
        mask = final.batch_id == r.item_id
        if r.reason != final.loc[mask, "reason"].iloc[0]:
            raise ValueError("stale review: regenerate decisions from the current contact sheet")
        before = final.loc[mask, "decision"].iloc[0]
        after = before
        if r.reviewer_decision in {"edit", "reject", "escalate"}:
            after = ("HOLD" if r.reviewer_decision == "escalate" else
                     r.override_value.strip().upper() or ("REWORK" if r.reviewer_decision == "reject" else ""))
            if after not in {"ACCEPT", "REWORK", "HOLD"} or not r.review_note.strip():
                raise ValueError("override requires ACCEPT/REWORK/HOLD and a nonempty review_note")
            supported = (bool(final.loc[mask, "accept_supported"].iloc[0]) if "accept_supported" in final
                         else final.loc[mask, "ci_high"].iloc[0] <= threshold + 1e-12)
            if after == "ACCEPT" and not supported:
                raise ValueError("cannot ACCEPT an uncertain/bad batch without supporting audit evidence")
            final.loc[mask, "reason_code"] = "HUMAN_OVERRIDE"
            final.loc[mask, "reason"] = r.review_note
        final.loc[mask, "decision"] = after
        final.loc[mask, "owner"] = r.reviewer
        ctx.audit.log(actor=r.reviewer, action="batch_review:" + r.reviewer_decision,
                      item_id=r.item_id, before=before, after=after, reason=r.review_note)
    ctx.stats["n_reviewed"] = len(reviewed)
    return final


def run(ctx):
    # Retain the append-only audit log and user's reviewed CSV, but never leave a stale
    # successful prediction that could accidentally be evaluated after this run fails.
    for filename in ["batch_decisions.csv", "batch_decisions_raw.csv", "decision.json",
                     "quality_gate.json", "review_queue.csv", "contact_sheet.html",
                     "audited_samples.csv", "audit_history.csv", "stratum_estimates.csv"]:
        ctx.out(filename).unlink(missing_ok=True)
    for stale in (ctx.output_dir / "decisions").glob("batch_*.json"):
        stale.unlink()
    # 01 Load vendor batches: provenance (manifest sha256), schema, frozen policy.
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else ["missing manifest"]
    if problems:
        raise ValueError(f"provenance check failed: {problems[:3]}")
    batch = pd.read_csv(ctx.input_dir / "batches.csv", dtype={"sample_id": str, "batch_id": str})
    required = {"sample_id", "batch_id", "vendor", "risk_tag", "annotator_id", "seconds_spent", "n_boxes"}
    if not required <= set(batch) or batch.empty:
        raise ValueError(f"batches.csv must be nonempty and contain {sorted(required)}")
    if batch[list(required)].isna().any().any() or batch.sample_id.duplicated().any():
        raise ValueError("missing metadata or duplicate sample IDs")
    for col in ["sample_id", "batch_id", "risk_tag"]:
        if batch[col].astype(str).str.strip().eq("").any():
            raise ValueError(f"blank {col}")
    policy = load_config(ctx.input_dir / "acceptance_policy.yaml")
    for key in ["audit_budget_per_batch", "max_error_rate"]:
        if key not in policy:
            raise ValueError(f"acceptance_policy.yaml must define {key}")
    budget = policy["audit_budget_per_batch"]
    threshold = float(policy["max_error_rate"])
    # The handout fixes 95%; older/hidden policies may omit the key.
    confidence = float(policy.get("confidence_level", 0.95))
    if not isinstance(budget, int) or isinstance(budget, bool) or budget < 1:
        raise ValueError("policy audit budget must be a positive integer")
    if not 0 <= threshold <= 1 or not 0 < confidence < 1:
        raise ValueError("invalid policy threshold/confidence")
    # The fixture policy is frozen before sampling and is what the evaluator checks budget against.
    # Config values never override it; any disagreement is logged instead of aborting the run.
    config_conflicts = {key: dict(config=ctx.param(key), policy=policy[key])
                        for key in ["audit_budget_per_batch", "max_error_rate"]
                        if ctx.param(key) is not None and ctx.param(key) != policy[key]}
    if config_conflicts:
        ctx.audit.log(actor="pipeline", action="policy_config_conflict", item_id="acceptance_policy.yaml",
                      before=config_conflicts, after="policy values used",
                      reason="frozen fixture policy takes precedence over config params")
    # 02 Select samples under the budget, label-blind, before any label is revealed.
    strategy = ctx.param("sampling_strategy", "stratified")
    allocation = ctx.param("allocation", "proportional")
    plan = pd.concat([select_samples(g, budget, ctx.rng, strategy, allocation)
                      for _, g in batch.groupby("batch_id", sort=True)], ignore_index=True)
    stages_by_batch = {bid: audit_stages(len(group), budget, ctx.param("audit_stages"))
                       for bid, group in batch.groupby("batch_id", sort=True)}
    for bid, scheduled in plan.groupby("batch_id", sort=True):
        if stages_by_batch[bid][0] < scheduled.stratum.nunique():
            raise ValueError("the first audit look must cover all risk strata")
    plan.to_csv(ctx.out("audit_selection.csv"), index=False)
    selection_hash = config_hash(dict(selection=sha256_file(ctx.out("audit_selection.csv")),
                                     stages=stages_by_batch, confidence=confidence, threshold=threshold,
                                     input_hash=sha256_file(ctx.input_dir / "batches.csv")))
    write_json(ctx.out("audit_protocol.json"), dict(policy=policy, strategy=strategy, seed=ctx.seed,
               policy_sha256=sha256_file(ctx.input_dir / "acceptance_policy.yaml"),
               batch_sha256=sha256_file(ctx.input_dir / "batches.csv"),
               pipeline_sha256=sha256_file(Path(__file__)),
               confidence_method="hypergeometric inversion; Bonferroni across strata and scheduled looks within each batch",
               decision_method="exact one-sided test of the stratified estimator at the limit (sup over error "
                               "allocations), alpha/2 per direction per look; Bonferroni CI rule as fallback",
               fixed_sample=all(len(s) == 1 for s in stages_by_batch.values()),
               stages=stages_by_batch, allocation=allocation, protocol_version=3,
               confidence_level=confidence, config_conflicts_ignored=config_conflicts,
               sequential_estimate_caveat="Point estimates at optional stopping may be biased; CI spends alpha across looks.",
               input_items=len(batch)))
    # 03 Estimate error rate + uncertainty; labels come only through the budgeted AuditOracle.
    labels_path = Path(ctx.param("audit_labels", ctx.input_dir / "gt" / "hidden_errors.csv"))
    if not labels_path.exists():
        raise FileNotFoundError(f"Audit labels missing: {labels_path}. Selection written to audit_selection.csv. "
                                "Use instructor overlay, or python -m tools.demo_t12 for SIMULATED labels.")
    oracle = AuditOracle(str(labels_path), "sample_id", "is_error", "batch_id",
                         budget_per_group=budget, total_budget=len(plan), audit=ctx.audit)
    ctx.audit.log(actor="pipeline", action="audit_run_start", item_id=selection_hash,
                  after=dict(seed=ctx.seed, stages=stages_by_batch, budget_per_batch=budget))
    rows, strata, observed_parts, histories = [], [], [], []
    owner = str(ctx.config.get("owner", "TODO: assign batch reviewer"))
    for batch_id, scheduled in plan.groupby("batch_id", sort=True):
        N = int((batch.batch_id == batch_id).sum())
        sample, est, low, high, evidence, decision, code, history = inspect_batch(
            scheduled, N, confidence, threshold, stages_by_batch[batch_id], oracle)
        observed_parts.append(sample)
        histories.extend(dict(batch_id=batch_id, **look) for look in history)
        last = history[-1]
        reason = (f"{len(sample)}/{N} audited; estimate={est:.4f}; {confidence:.0%} CI=[{low:.4f}, {high:.4f}]; "
                  f"limit={threshold:.4f}; p_accept={last['p_accept']:.4f}; p_rework={last['p_rework']:.4f} "
                  f"(reject if < {last['alpha_spent'] / 2:.4f}); selection={selection_hash}")
        rows.append(dict(batch_id=batch_id, est_error_rate=est, decision=decision, n_audited=len(sample),
                         ci_low=low, ci_high=high, reason_code=code, reason=reason, owner=owner,
                         p_accept=last["p_accept"], p_rework=last["p_rework"],
                         decision_method=last["decision_method"], accept_supported=last["accept_supported"],
                         cost_per_item=len(sample) / N, n_errors_observed=int(sample.is_error.sum()),
                         stop_reason=history[-1]["stop_reason"],
                         score=float(decision == "HOLD") + high - low))
        strata.extend(dict(batch_id=batch_id, **e) for e in evidence)
    observed = pd.concat(observed_parts, ignore_index=True)
    observed.to_csv(ctx.out("audited_samples.csv"), index=False)
    pd.DataFrame(histories).to_csv(ctx.out("audit_history.csv"), index=False)
    predictions = pd.DataFrame(rows)
    predictions.to_csv(ctx.out("batch_decisions_raw.csv"), index=False)
    pd.DataFrame(strata).to_csv(ctx.out("stratum_estimates.csv"), index=False)
    # 04 Human inspects hard cases: queue + contact sheet, reviewer overrides, audit log.
    queue = make_review_queue(predictions, "batch_id", "score", len(predictions), "reason", "decision")
    write_review_queue(queue, ctx.out("review_queue.csv"))
    render_contact_sheet(queue, ctx.out("contact_sheet.html"), image_col=None,
                         title="T12 - Batch audit: confidence bands and decisions")
    final = apply_review(ctx, predictions, threshold)
    # 05 ACCEPT / REWORK / HOLD with reason_code + owner; HOLD guardrail reported, never forced.
    final.to_csv(ctx.out("batch_decisions.csv"), index=False)
    hold_rate = float(final.decision.eq("HOLD").mean())
    max_hold = float((ctx.config.get("eval_params") or {}).get("max_hold_rate", 0.4))
    write_json(ctx.out("quality_gate.json"), dict(hold_rate=hold_rate, max_hold_rate=max_hold,
               hold_guardrail_pass=hold_rate <= max_hold, budget_violations=int(final.n_audited.gt(budget).sum()),
               note="Execution success does not imply the quality guardrail passes."))
    ctx.stats.update(n_items=len(batch), n_batches=len(final), n_audited=len(observed),
                     hold_rate=hold_rate, hold_guardrail_pass=hold_rate <= max_hold,
                     sampling_strategy=strategy, allocation=allocation, audit_labels=str(labels_path))
    for index, r in enumerate(final.itertuples(index=False)):
        write_decision(Decision(r.decision, r.reason_code, r.reason, r.owner, r.batch_id,
                                evidence=["audited_samples.csv", "stratum_estimates.csv"]),
                       ctx.out(f"decisions/batch_{index:04d}.json"), ctx.out("decision_log.csv"))
    status = "HOLD" if final.decision.eq("HOLD").any() else ("REWORK" if final.decision.eq("REWORK").any() else "GO")
    write_decision(Decision(status, "BATCH_AUDIT_COMPLETE", f"HOLD rate={hold_rate:.2f}; guardrail <= {max_hold}: {hold_rate <= max_hold}",
                            owner, "t12", ["batch_decisions.csv"], dict(hold_rate=hold_rate)),
                   ctx.out("decision.json"))
