"""Reproducible T12 wiring demo with invented labels, never official ground truth."""
import argparse
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import yaml

from src import compare, evaluate
from src.main import main as run_pipeline
from src.common.io import deep_merge, load_config, read_json, write_json


def prepare(root, seed, config_path="configs/lab.yaml"):
    config = load_config(config_path)
    source = Path(config.get("input", "fixtures/t12_vendor_batches"))
    input_dir = root / "input"
    (input_dir / "gt").mkdir(parents=True, exist_ok=True)
    for name in ["batches.csv", "acceptance_policy.yaml", "manifest.csv"]:
        shutil.copyfile(source / name, input_dir / name)
    data = pd.read_csv(input_dir / "batches.csv")
    # Separate streams: simulated truth must not reuse the pipeline's sampling RNG.
    rng = np.random.default_rng(np.random.SeedSequence([seed, 12001]))
    labels, truth = [], []
    # Illustrative scenarios, deliberately independent of the unavailable instructor labels.
    rates = [0.01, 0.03, 0.08, 0.15, 0.30]
    risk_weights = {"normal": 1.0, "night": 3.0, "small_object": 4.0, "occlusion": 3.0}
    for i, (bid, group) in enumerate(data.groupby("batch_id", sort=True)):
        group = group.copy()
        n_errors = round(len(group) * rates[i % len(rates)])
        weights = group.risk_tag.map(risk_weights).fillna(1).to_numpy(dtype=float)
        errors = set(rng.choice(group.sample_id, n_errors, replace=False, p=weights / weights.sum()))
        group["is_error"] = group.sample_id.isin(errors).astype(int)
        labels.append(group[["sample_id", "batch_id", "is_error"]])
        truth.append(dict(batch_id=bid, true_error_rate=n_errors / len(group),
                          is_bad=int(n_errors / len(group) > 0.05)))
    pd.concat(labels).to_csv(input_dir / "gt/hidden_errors.csv", index=False)
    pd.DataFrame(truth).to_csv(input_dir / "gt/batch_truth.csv", index=False)
    config.pop("track_config", None)
    config.update(track="t12", input=str(input_dir), seed=seed, offline=True)
    # Keep the group's frozen params so the demo runs the configuration that will be submitted,
    # but never let a configured label file replace the simulated labels.
    params = dict(config.get("params") or {})
    params.pop("audit_labels", None)
    params.setdefault("sampling_strategy", "stratified")
    config["params"] = params
    path = root / "demo_config.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    write_json(root / "SIMULATED_DATA.json", dict(simulated=True, seed=seed,
               notice="Invented labels for local testing only; NOT instructor/official results.",
               scenarios=rates, risk_weights=risk_weights, generator_version=2,
               label_rng_domain=12001, sampling_seed=seed))
    return path, input_dir


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="out/t12_demo")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--config", default="configs/lab.yaml")
    parser.add_argument("--reports", help="optional folder for explicitly simulated report artifacts")
    args = parser.parse_args(argv)
    root = Path(args.output)
    config, input_dir = prepare(root, args.seed, args.config)
    print("SIMULATED LABELS ONLY - not official evaluation")
    variants = [("baseline", "src.examples.t12_baseline", {}),
                ("poc", "src.pipeline", {}),
                ("balanced", "src.pipeline", {"allocation": "balanced"}),
                ("sequential", "src.pipeline", {"audit_stages": [15, 20]})]
    for name, module, params in variants:
        variant_config = root / f"config_{name}.yaml"
        variant_config.write_text(yaml.safe_dump(deep_merge(load_config(config), {"params": params}),
                                               allow_unicode=True), encoding="utf-8")
        rc = run_pipeline(["--config", str(variant_config), "--output", str(root / name),
                           "--pipeline", module, "--run-name", "simulated_" + name, "--offline"])
        if rc:
            return rc
    base = pd.read_csv(root / "baseline/batch_decisions.csv")
    for name, decision in [("all_hold", "HOLD"), ("all_rework", "REWORK")]:
        (root / name).mkdir(exist_ok=True)
        base.assign(decision=decision).to_csv(root / name / "batch_decisions.csv", index=False)
        # Decision-only controls share baseline audits, estimates, runtime and budget.
        shutil.copyfile(root / "baseline/run_info.json", root / name / "run_info.json")
    cost_rows = []
    for name in ["baseline", "poc", "balanced", "sequential", "all_hold", "all_rework"]:
        rc = evaluate.main(["--track", "t12", "--config", str(config),
                       "--gt", str(input_dir / "gt/batch_truth.csv"),
                       "--pred", str(root / name / "batch_decisions.csv"),
                       "--run-name", "simulated_" + name, "--out", str(root / f"metrics_{name}.json")])
        if rc:
            return rc
        metrics = {m["name"]: m["value"] for m in read_json(root / f"metrics_{name}.json")["metrics"]}
        decisions = pd.read_csv(root / name / "batch_decisions.csv")
        cost_rows.append(dict(variant=name, simulated=True, seed=args.seed, total_audits=int(decisions.n_audited.sum()),
                              audits_per_decision=float(decisions.n_audited.mean()),
                              early_stopped_batches=int(decisions.n_audited.lt(20).sum()),
                              mae=metrics["MAE error-rate estimate"], bad_batch_miss_rate=1-metrics["Bad-batch Recall"],
                              hold_rate=metrics["HOLD rate"], false_reject_rate=metrics["False reject rate"],
                              ci_coverage=metrics["CI coverage"], budget_violations=metrics["Budget violations"]))
    pd.DataFrame(cost_rows).to_csv(root / "cost_tradeoff.csv", index=False)
    compare.main([str(root / "metrics_baseline.json"), str(root / "metrics_poc.json"),
                  "--out", str(root / "table_baseline_vs_poc.md")])
    compare.main([str(root / "metrics_poc.json"), str(root / "metrics_sequential.json"),
                  "--out", str(root / "table_fixed_vs_sequential.md")])
    if args.reports:
        reports = Path(args.reports)
        reports.mkdir(parents=True, exist_ok=True)
        for name in ["metrics_baseline.json", "metrics_poc.json", "metrics_all_hold.json",
                     "metrics_all_rework.json", "table_baseline_vs_poc.md", "SIMULATED_DATA.json"]:
            shutil.copyfile(root / name, reports / name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
