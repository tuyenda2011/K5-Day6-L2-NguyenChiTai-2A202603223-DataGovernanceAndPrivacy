"""T12 tests use invented labels; never require instructor data."""
import json

import numpy as np
import pandas as pd
import pytest
from scipy.stats import hypergeom

from src.main import main
from src.tracks.t12 import finite_interval, select_samples, classify, estimate_batch, audit_stages, inspect_batch
from tools.demo_t12 import prepare


def test_exact_interval_has_nominal_coverage():
    # Enumerate every possible true error count and every audit result in a small population.
    N, n = 12, 5
    for K in range(N + 1):
        coverage = 0
        for k in range(n + 1):
            low, high = finite_interval(k, n, N)
            if low - 1e-12 <= K / N <= high + 1e-12:
                coverage += hypergeom.pmf(k, N, K, n)
        assert coverage >= 0.95 - 1e-12


def test_zero_errors_is_not_proof_of_five_percent():
    lo, hi = finite_interval(0, 20, 100)
    assert lo == 0 and hi > 0.05
    assert classify(lo, hi, 0.05)[0] == "HOLD"
    assert finite_interval(0, 100, 100) == (0, 0)
    assert classify(0.1, 0.2, 0.05)[0] == "REWORK"


def test_selection_is_fixed_unique_and_reproducible():
    data = pd.DataFrame(dict(sample_id=[f"s{i}" for i in range(100)],
                             risk_tag=["normal"] * 90 + ["night"] * 10))
    a = select_samples(data, 20, np.random.default_rng(42))
    b = select_samples(data.sample(frac=1, random_state=1), 20, np.random.default_rng(42))
    pd.testing.assert_frame_equal(a, b)
    assert len(a) == a.sample_id.nunique() == 20
    assert set(a.stratum) == {"normal", "night"}
    with pytest.raises(ValueError, match="cover every"):
        select_samples(data, 1, np.random.default_rng(42))


def test_stratified_estimate_uses_population_weights():
    sample = pd.DataFrame(dict(stratum=["normal", "normal", "night", "night"],
                               stratum_population=[90, 90, 10, 10], is_error=[0, 0, 1, 1]))
    estimate, _, _, _ = estimate_batch(sample, 100, 0.95)
    assert estimate == pytest.approx(0.10)  # naive audit mean 0.50 would be biased


def test_proportional_allocation_preserves_large_strata():
    data = pd.DataFrame(dict(sample_id=[f"s{i:03d}" for i in range(100)],
                             risk_tag=["normal"] * 90 + ["night"] * 10))
    plan = select_samples(data, 20, np.random.default_rng(42))
    assert plan.groupby("stratum").size().to_dict() == {"night": 2, "normal": 18}
    assert plan.audit_order.tolist() == list(range(1, 21))
    balanced = select_samples(data, 20, np.random.default_rng(42), allocation="balanced")
    assert balanced.groupby("stratum").size().to_dict() == {"night": 10, "normal": 10}


@pytest.mark.parametrize("stages", [[10, 20], [15, 21], [20, 15], [15, 15, 20], [15.0, 20], []])
def test_invalid_sequential_schedule_is_rejected(stages):
    with pytest.raises(ValueError, match="audit_stages"):
        audit_stages(100, 20, stages)


def test_sequential_schedule_caps_small_batches_at_census():
    assert audit_stages(10, 20, [15, 20]) == [10]
    assert audit_stages(18, 20, [15, 20]) == [15, 18]


def test_stale_review_is_rejected_when_sampling_protocol_changes(tmp_path):
    import yaml
    config, _ = prepare(tmp_path / "demo", 42)
    out = tmp_path / "poc"
    args = ["--config", str(config), "--output", str(out), "--offline"]
    assert main(args) == 0
    queue = pd.read_csv(out / "review_queue.csv", dtype=str).fillna("")
    queue.loc[0, ["reviewer", "reviewer_decision"]] = ["Test reviewer", "approve"]
    queue.to_csv(out / "review_queue_reviewed.csv", index=False)
    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    cfg["params"]["audit_stages"] = [15, 20]
    config.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    assert main(args) == 2
    assert not (out / "batch_decisions.csv").exists()


def test_sequential_ci_coverage_at_label_dependent_stopping():
    from itertools import product
    from math import comb

    class Labels:
        def __init__(self, values):
            self.values = dict(zip(plan.sample_id, values))

        def inspect(self, ids):
            return {i: self.values[i] for i in ids}

    data = pd.DataFrame(dict(sample_id=[f"s{i}" for i in range(8)], risk_tag="normal"))
    plan = select_samples(data, 8, np.random.default_rng(42), "random")
    coverage = {K: 0.0 for K in range(9)}
    # Each binary ordering with K errors has probability 1 / choose(8, K).
    for values in product([0, 1], repeat=8):
        K = sum(values)
        _, _, low, high, _, _, _, _ = inspect_batch(plan, 8, .95, .25, [4, 8], Labels(values))
        if low - 1e-12 <= K / 8 <= high + 1e-12:
            coverage[K] += 1 / comb(8, K)
    assert min(coverage.values()) >= .95 - 1e-12


def test_sequential_pipeline_stops_early_without_spending_remaining_budget(tmp_path):
    import yaml
    config, input_dir = prepare(tmp_path / "demo", 42)
    labels_path = input_dir / "gt/hidden_errors.csv"
    labels = pd.read_csv(labels_path)
    labels["is_error"] = 1
    labels.to_csv(labels_path, index=False)
    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    cfg["params"]["audit_stages"] = [15, 20]
    config.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    out = tmp_path / "sequential"
    assert main(["--config", str(config), "--output", str(out), "--offline"]) == 0
    pred = pd.read_csv(out / "batch_decisions.csv")
    assert pred.n_audited.eq(15).all()
    assert pred.decision.eq("REWORK").all()
    inspected = pd.read_csv(out / "audited_samples.csv")
    assert len(inspected) == 75
    assert inspected.inclusion_probability.isna().all()
    assert inspected.realized_sampling_fraction.gt(0).all()
    history = pd.read_csv(out / "audit_history.csv")
    assert len(history) == 5
    assert history.alpha_spent.eq(.025).all()


def test_manual_accept_cannot_bypass_uncertainty_and_failed_run_has_no_stale_prediction(tmp_path):
    config, _ = prepare(tmp_path / "demo", 42)
    out = tmp_path / "poc"
    args = ["--config", str(config), "--output", str(out), "--offline"]
    assert main(args) == 0
    queue = pd.read_csv(out / "review_queue.csv", dtype=str).fillna("")
    queue.loc[0, ["reviewer", "reviewer_decision", "override_value", "review_note"]] = [
        "Test reviewer", "edit", "ACCEPT", "Try to bypass uncertainty"]
    queue.to_csv(out / "review_queue_reviewed.csv", index=False)
    assert main(args) == 2
    assert not (out / "batch_decisions.csv").exists()
    assert not (out / "decision.json").exists()


def test_submission_artifact_validator_detects_false_budget_claim(tmp_path):
    from tools.submit_t12 import validate_artifacts
    config, input_dir = prepare(tmp_path / "demo", 42)
    out = tmp_path / "poc"
    assert main(["--config", str(config), "--output", str(out), "--offline"]) == 0
    assert validate_artifacts(out, input_dir)["automated_checks_passed"]
    pred = pd.read_csv(out / "batch_decisions.csv")
    pred.loc[0, "n_audited"] = 1
    pred.to_csv(out / "batch_decisions.csv", index=False)
    result = validate_artifacts(out, input_dir)
    assert not result["automated_checks_passed"]
    assert "declared/actual audit budget mismatch" in result["errors"]


def test_official_submission_refuses_simulated_input(tmp_path):
    from tools.submit_t12 import main as submit_main
    config, _ = prepare(tmp_path / "demo", 42)
    assert submit_main(["--mode", "official", "--config", str(config),
                        "--output", str(tmp_path / "official")]) == 2


def test_oracle_refuses_extra_audits(tmp_path):
    from src.common.audit_oracle import AuditOracle, BudgetExceededError
    labels = tmp_path / "labels.csv"
    labels.write_text("sample_id,batch_id,is_error\ns1,b,0\ns2,b,1\n", encoding="utf-8")
    oracle = AuditOracle(str(labels), "sample_id", "is_error", "batch_id", budget_per_group=1)
    assert oracle.inspect(["s1", "s1"]) == {"s1": 0}
    with pytest.raises(BudgetExceededError):
        oracle.inspect(["s2"])


def test_offline_end_to_end_and_human_override(tmp_path):
    config, _ = prepare(tmp_path / "demo", 42)
    out = tmp_path / "poc"
    args = ["--config", str(config), "--output", str(out), "--offline"]
    assert main(args) == 0
    pred = pd.read_csv(out / "batch_decisions.csv")
    audited = pd.read_csv(out / "audited_samples.csv")
    assert len(pred) == 5
    assert pred.n_audited.eq(20).all()
    assert len(audited) == audited.sample_id.nunique() == 100
    assert audited.groupby("batch_id").size().le(20).all()
    assert (pred.ci_low <= pred.est_error_rate).all()
    assert (pred.est_error_rate <= pred.ci_high + 1e-12).all()
    assert (out / "contact_sheet.html").exists()
    assert json.loads((out / "run_info.json").read_text())["stats"]["n_items"] == 500
    before = (out / "batch_decisions_raw.csv").read_bytes()
    queue = pd.read_csv(out / "review_queue.csv", dtype=str).fillna("")
    queue.loc[0, ["reviewer", "reviewer_decision", "override_value", "review_note"]] = [
        "Test reviewer", "edit", "REWORK", "Manual correction requested"]
    queue.to_csv(out / "review_queue_reviewed.csv", index=False)
    assert main(args) == 0
    assert (out / "batch_decisions_raw.csv").read_bytes() == before
    final = pd.read_csv(out / "batch_decisions.csv").set_index("batch_id")
    assert final.loc[queue.item_id.iloc[0], "reason_code"] == "HUMAN_OVERRIDE"
    events = [json.loads(line) for line in (out / "audit_log.jsonl").read_text().splitlines()]
    assert any(e["action"] == "batch_review:edit" and e["actor"] == "Test reviewer" for e in events)


def test_missing_labels_fails_after_writing_selection(tmp_path):
    config, input_dir = prepare(tmp_path / "demo", 42)
    (input_dir / "gt/hidden_errors.csv").unlink()
    out = tmp_path / "poc"
    assert main(["--config", str(config), "--output", str(out), "--offline"]) == 2
    assert (out / "audit_selection.csv").exists()
    assert not (out / "batch_decisions.csv").exists()


def _evidence(Ns, ns, ks):
    return [dict(population=N, n_audited=n, errors=k) for N, n, k in zip(Ns, ns, ks)]


def test_exact_threshold_test_bounds_wrong_decisions_by_enumeration():
    from src.tracks.t12 import threshold_test, decide_by_test
    Ns, ns, limit = (12, 8), (8, 5), .25
    decisions, worst = set(), 0.0
    for K1 in range(Ns[0] + 1):
        for K2 in range(Ns[1] + 1):
            bad, wrong = (K1 + K2) / sum(Ns) > limit, 0.0
            for x1 in range(ns[0] + 1):
                for x2 in range(ns[1] + 1):
                    p = hypergeom.pmf(x1, Ns[0], K1, ns[0]) * hypergeom.pmf(x2, Ns[1], K2, ns[1])
                    if p == 0:
                        continue
                    d = decide_by_test(*threshold_test(_evidence(Ns, ns, (x1, x2)), sum(Ns), limit), .05)[0]
                    decisions.add(d)
                    wrong += p * ((d == "REWORK" and not bad) or (d == "ACCEPT" and bad))
            worst = max(worst, wrong)
    assert decisions == {"ACCEPT", "HOLD", "REWORK"}  # the test is not vacuous
    assert worst <= .025 + 1e-12  # same per-direction error budget as the 95% two-sided CI rule


@pytest.mark.parametrize("N,n,limit", [(100, 20, .05), (50, 15, .1), (1000, 20, .05), (30, 30, .1)])
def test_exact_test_equals_ci_rule_for_one_stratum(N, n, limit):
    from src.tracks.t12 import threshold_test, decide_by_test
    for k in range(n + 1):
        low, high = finite_interval(k, n, N)
        assert decide_by_test(*threshold_test(_evidence([N], [n], [k]), N, limit), .05)[0] == classify(low, high, limit)[0]


def test_exact_test_reworks_where_bonferroni_ci_holds():
    from src.tracks.t12 import threshold_test, decide_by_test
    Ns, ns, ks = (53, 20, 18, 9), (10, 4, 4, 2), (2, 1, 1, 0)
    sample = pd.DataFrame(dict(
        stratum=sum([[h] * n for h, n in enumerate(ns)], []),
        stratum_population=sum([[N] * n for N, n in zip(Ns, ns)], []),
        is_error=sum([[1] * k + [0] * (n - k) for k, n in zip(ks, ns)], [])))
    _, low, high, _ = estimate_batch(sample, 100, .95)
    assert classify(low, high, .05)[0] == "HOLD"
    assert decide_by_test(*threshold_test(_evidence(Ns, ns, ks), 100, .05), .05)[0] == "REWORK"


def test_single_audit_cannot_support_a_precise_claim():
    # Failure mode in the handout: claiming a precise rate from 1 sample out of 100.
    for errors in (0, 1):
        low, high = finite_interval(errors, 1, 100)
        assert high - low > .9
        assert classify(low, high, .05)[0] == "HOLD"


def test_frozen_policy_overrides_config_and_tolerates_missing_confidence(tmp_path):
    import yaml
    config, input_dir = prepare(tmp_path / "demo", 42)
    # Hidden policy that differs from configs/tracks/t12.yaml and omits confidence_level.
    from src.common.io import sha256_file
    policy = input_dir / "acceptance_policy.yaml"
    policy.write_text("max_error_rate: 0.05\naudit_budget_per_batch: 15\n", encoding="utf-8")
    manifest = pd.read_csv(input_dir / "manifest.csv")
    manifest.loc[manifest.path == "acceptance_policy.yaml", "sha256"] = sha256_file(policy)
    manifest.to_csv(input_dir / "manifest.csv", index=False)
    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    cfg["params"]["audit_budget_per_batch"] = 20
    config.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    out = tmp_path / "poc"
    assert main(["--config", str(config), "--output", str(out), "--offline"]) == 0
    pred = pd.read_csv(out / "batch_decisions.csv")
    assert pred.n_audited.le(15).all()
    protocol = json.loads((out / "audit_protocol.json").read_text(encoding="utf-8"))
    assert protocol["confidence_level"] == .95
    assert protocol["config_conflicts_ignored"]["audit_budget_per_batch"] == {"config": 20, "policy": 15}
    events = [json.loads(line) for line in (out / "audit_log.jsonl").read_text().splitlines()]
    assert any(e["action"] == "policy_config_conflict" for e in events)


def test_invalid_reviewer_cannot_change_decision(tmp_path):
    config, _ = prepare(tmp_path / "demo", 42)
    out = tmp_path / "poc"
    args = ["--config", str(config), "--output", str(out), "--offline"]
    assert main(args) == 0
    queue = pd.read_csv(out / "review_queue.csv", dtype=str).fillna("")
    queue.loc[0, ["reviewer_decision", "override_value"]] = ["edit", "ACCEPT"]
    queue.to_csv(out / "review_queue_reviewed.csv", index=False)
    assert main(args) == 2


def test_demo_includes_comparison_and_trivial_controls(tmp_path):
    from tools.demo_t12 import main as demo_main
    assert demo_main(["--output", str(tmp_path)]) == 0
    assert "simulated_poc" in (tmp_path / "table_baseline_vs_poc.md").read_text(encoding="utf-8")
    assert (tmp_path / "metrics_all_hold.json").exists()
    assert (tmp_path / "metrics_all_rework.json").exists()


# QA additions for Nguyen Chi Tai: exercise the review CSV through the real runner.
def test_review_escalation_holds_rework_batch_and_preserves_audit_evidence(tmp_path):
    config, _ = prepare(tmp_path / "demo", 42)
    out = tmp_path / "poc"
    args = ["--config", str(config), "--output", str(out), "--offline"]
    assert main(args) == 0
    raw_before = (out / "batch_decisions_raw.csv").read_bytes()
    original = pd.read_csv(out / "batch_decisions.csv").set_index("batch_id")
    queue = pd.read_csv(out / "review_queue.csv", dtype=str).fillna("")
    target = queue.index[queue.suggested_action.eq("REWORK")][0]
    batch_id = queue.loc[target, "item_id"]
    note = "Escalate simulated vendor evidence for a second independent review."
    queue.loc[target, ["reviewer", "reviewer_decision", "review_note"]] = [
        "QA test reviewer", "escalate", note]
    queue.to_csv(out / "review_queue_reviewed.csv", index=False)
    events_before = (out / "audit_log.jsonl").read_bytes()

    assert main(args) == 0

    final = pd.read_csv(out / "batch_decisions.csv").set_index("batch_id")
    assert final.loc[batch_id, "decision"] == "HOLD"
    assert final.loc[batch_id, "reason_code"] == "HUMAN_OVERRIDE"
    assert final.loc[batch_id, "owner"] == "QA test reviewer"
    assert final.loc[batch_id, "reason"] == note
    pd.testing.assert_frame_equal(final.drop(index=batch_id), original.drop(index=batch_id))
    assert (out / "batch_decisions_raw.csv").read_bytes() == raw_before
    audit_bytes = (out / "audit_log.jsonl").read_bytes()
    assert audit_bytes.startswith(events_before)  # replay must append, never erase history
    events = [json.loads(line) for line in audit_bytes[len(events_before):].splitlines()]
    reviews = [event for event in events if event["action"] == "batch_review:escalate"]
    assert len(reviews) == 1
    assert reviews[0]["item_id"] == batch_id
    assert reviews[0]["actor"] == "QA test reviewer"
    assert (reviews[0]["before"], reviews[0]["after"], reviews[0]["reason"]) == (
        "REWORK", "HOLD", note)
    gate = json.loads((out / "quality_gate.json").read_text(encoding="utf-8"))
    assert gate["hold_rate"] == pytest.approx(final.decision.eq("HOLD").mean())
    assert gate["hold_guardrail_pass"] is False


@pytest.mark.parametrize("note", ["", "   "], ids=["empty", "whitespace"])
def test_review_override_requires_explanation_and_removes_stale_outputs(tmp_path, capsys, note):
    config, _ = prepare(tmp_path / "demo", 42)
    out = tmp_path / "poc"
    args = ["--config", str(config), "--output", str(out), "--offline"]
    assert main(args) == 0
    queue = pd.read_csv(out / "review_queue.csv", dtype=str).fillna("")
    queue.loc[0, ["reviewer", "reviewer_decision", "override_value", "review_note"]] = [
        "QA test reviewer", "edit", "REWORK", note]
    queue.to_csv(out / "review_queue_reviewed.csv", index=False)

    assert main(args) == 2

    assert "nonempty review_note" in capsys.readouterr().err
    for filename in ["batch_decisions.csv", "decision.json", "quality_gate.json"]:
        assert not (out / filename).exists()
    info = json.loads((out / "run_info.json").read_text(encoding="utf-8"))
    assert info["status"] == 2
    events = [json.loads(line) for line in (out / "audit_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert not any(event["action"].startswith("batch_review:") for event in events)


@pytest.mark.parametrize("invalid_id", ["duplicate", "unknown"])
def test_review_rejects_duplicate_or_unknown_batch_ids(tmp_path, capsys, invalid_id):
    config, _ = prepare(tmp_path / "demo", 42)
    out = tmp_path / "poc"
    args = ["--config", str(config), "--output", str(out), "--offline"]
    assert main(args) == 0
    reviewed = pd.read_csv(out / "review_queue.csv", dtype=str).fillna("").iloc[[0]].copy()
    reviewed.loc[:, "reviewer"] = "QA test reviewer"
    reviewed.loc[:, "reviewer_decision"] = "approve"
    if invalid_id == "duplicate":
        reviewed = pd.concat([reviewed, reviewed], ignore_index=True)
    else:
        reviewed.loc[:, "item_id"] = "UNKNOWN_BATCH_NOT_IN_INPUT"
    reviewed.to_csv(out / "review_queue_reviewed.csv", index=False)

    assert main(args) == 2

    assert "duplicate or unknown batch IDs" in capsys.readouterr().err
    assert not (out / "batch_decisions.csv").exists()
    assert not (out / "decision.json").exists()
    info = json.loads((out / "run_info.json").read_text(encoding="utf-8"))
    assert info["status"] == 2
    events = [json.loads(line) for line in (out / "audit_log.jsonl").read_text(encoding="utf-8").splitlines()]
    assert not any(event["action"].startswith("batch_review:") for event in events)
