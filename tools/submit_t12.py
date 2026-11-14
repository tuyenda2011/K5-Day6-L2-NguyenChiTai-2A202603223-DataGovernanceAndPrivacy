"""One-command T12 reproduction and machine-readable submission checks.

python -m tools.submit_t12 --mode demo
python -m tools.submit_t12 --mode official  # requires instructor overlay
"""
import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import shutil

import numpy as np
import pandas as pd

from src import compare, evaluate
from src.main import main as run_pipeline
from src.common.io import load_config, write_json
from src.common.manifest import verify_manifest
from src.common.review import load_review_decisions
from tools.demo_t12 import main as demo_main


def validate_artifacts(folder, input_dir):
    """Cross-check declared budget against actual inspected IDs, predictions and history."""
    rows = pd.read_csv(input_dir / "batches.csv", dtype=str)
    policy = load_config(input_dir / "acceptance_policy.yaml")
    predictions = pd.read_csv(folder / "batch_decisions.csv", dtype={"batch_id": str})
    raw = pd.read_csv(folder / "batch_decisions_raw.csv", dtype={"batch_id": str})
    audited = pd.read_csv(folder / "audited_samples.csv", dtype={"batch_id": str, "sample_id": str})
    history = pd.read_csv(folder / "audit_history.csv", dtype={"batch_id": str})
    info = json.loads((folder / "run_info.json").read_text(encoding="utf-8"))
    errors = []
    if info["status"] != 0 or not info["offline"]:
        errors.append("run failed or was not offline")
    if predictions.batch_id.duplicated().any() or set(predictions.batch_id) != set(rows.batch_id):
        errors.append("missing or duplicate batch decisions")
    if audited.sample_id.duplicated().any() or not set(audited.sample_id) <= set(rows.sample_id):
        errors.append("duplicate or unknown audited IDs")
    matched = audited.merge(rows[["sample_id", "batch_id"]], on="sample_id", suffixes=("", "_input"))
    if not matched.batch_id.eq(matched.batch_id_input).all():
        errors.append("audited batch ID does not match input")
    counts = audited.groupby("batch_id").size()
    expected = predictions.batch_id.map(counts).fillna(0)
    if not predictions.n_audited.eq(expected).all() or counts.gt(policy["audit_budget_per_batch"]).any():
        errors.append("declared/actual audit budget mismatch")
    stopped = history.groupby("batch_id").tail(1).set_index("batch_id").n_audited
    if not predictions.n_audited.eq(predictions.batch_id.map(stopped)).all():
        errors.append("audit history does not match final counts")
    for frame in [raw, predictions]:
        if (not np.isfinite(frame[["est_error_rate", "ci_low", "ci_high"]].to_numpy()).all() or
                not frame.est_error_rate.between(0, 1).all() or
                not frame.ci_low.between(0, 1).all() or not frame.ci_high.between(0, 1).all() or
                not frame.ci_low.le(frame.ci_high + 1e-12).all()):
            errors.append("invalid estimate or confidence band")
        if not frame.decision.isin(["ACCEPT", "REWORK", "HOLD"]).all():
            errors.append("unknown decision")
        supported = (frame.accept_supported.astype(str).str.lower().eq("true") if "accept_supported" in frame
                     else frame.ci_high.le(policy["max_error_rate"] + 1e-12))
        if (frame.decision.eq("ACCEPT") & ~supported).any():
            errors.append("ACCEPT without audit evidence")
    if not audited.is_error.isin([0, 1]).all():
        errors.append("non-binary inspected labels")
    gate = json.loads((folder / "quality_gate.json").read_text(encoding="utf-8"))
    hold_rate = float(predictions.decision.eq("HOLD").mean())
    if abs(hold_rate - gate["hold_rate"]) > 1e-12:
        errors.append("quality gate does not match predictions")
    # The most recent run, rather than all historical replays, must log exactly its inspected IDs.
    events = [json.loads(line) for line in (folder / "audit_log.jsonl").read_text(encoding="utf-8").splitlines()]
    starts = [i for i, event in enumerate(events) if event["action"] == "audit_run_start"]
    if not starts:
        errors.append("missing run boundary in audit log")
    else:
        inspected = [e["item_id"] for e in events[starts[-1]:] if e["action"] == "audit_inspect"]
        if len(inspected) != len(audited) or set(inspected) != set(audited.sample_id):
            errors.append("audit log does not match inspected samples")
    required_review = set(raw.loc[raw.decision.eq("HOLD"), "batch_id"])
    reviewed_path = folder / "review_queue_reviewed.csv"
    reviewed_ids = set()
    if reviewed_path.exists():
        reviewed = load_review_decisions(reviewed_path)
        reviewed_ids = set(reviewed.loc[reviewed.reviewer_decision.ne("skip"), "item_id"])
    return dict(automated_checks_passed=not errors, errors=errors,
                batches=len(predictions), audited_samples=len(audited),
                hold_guardrail_pass=gate["hold_guardrail_pass"],
                human_review_complete=required_review <= reviewed_ids)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["auto", "demo", "official"], default="auto")
    parser.add_argument("--output", default="out/t12_submission")
    parser.add_argument("--config", default="configs/lab.yaml")
    parser.add_argument("--reports", default="reports", help="official mode: where metrics_*.json and table1 are copied")
    parser.add_argument("--require-ready", action="store_true", help="exit nonzero until official data, review and quality gates pass")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if config.get("track") != "t12":
        print("Select track t12 in the config first.", file=sys.stderr)
        return 2
    input_dir = Path(config["input"])
    hidden = input_dir / "gt/hidden_errors.csv"
    truth = input_dir / "gt/batch_truth.csv"
    mode = ("official" if hidden.exists() and truth.exists() else "demo") if args.mode == "auto" else args.mode
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    if mode == "official" and not (hidden.exists() and truth.exists()):
        print("Missing instructor overlay; official mode never substitutes simulated labels.", file=sys.stderr)
        return 2
    if mode == "official" and (input_dir.parent / "SIMULATED_DATA.json").exists():
        print("This input is marked as simulated; it cannot be evaluated as official data.", file=sys.stderr)
        return 2
    override = (config.get("params") or {}).get("audit_labels")
    if mode == "official" and override and Path(override).resolve() != hidden.resolve():
        print("Official mode requires audit_labels from the instructor overlay.", file=sys.stderr)
        return 2
    if verify_manifest(input_dir / "manifest.csv"):
        print("Input manifest verification failed.", file=sys.stderr)
        return 2
    capture = io.StringIO()
    with redirect_stdout(capture), redirect_stderr(capture):
        if mode == "demo":
            rc = demo_main(["--output", str(root), "--config", args.config,
                            "--seed", str(config.get("seed", 42))])
            checked_input = root / "input"
            variants = ["baseline", "poc", "balanced", "sequential"]
        else:
            rc = 0
            checked_input = input_dir
            variants = ["baseline", "poc"]
            for name, module in [("baseline", "src.examples.t12_baseline"), ("poc", "src.pipeline")]:
                rc = run_pipeline(["--config", args.config, "--output", str(root / name),
                                   "--pipeline", module, "--run-name", name, "--offline", "--seed", "42"])
                if rc:
                    break
                rc = evaluate.main(["--track", "t12", "--config", args.config, "--gt", str(truth),
                                    "--pred", str(root / name / "batch_decisions.csv"), "--run-name", name,
                                    "--out", str(root / f"metrics_{name}.json")])
                if rc:
                    break
            if not rc:
                base = pd.read_csv(root / "baseline/batch_decisions.csv")
                for name, decision in [("all_hold", "HOLD"), ("all_rework", "REWORK")]:
                    (root / name).mkdir(exist_ok=True)
                    base.assign(decision=decision).to_csv(root / name / "batch_decisions.csv", index=False)
                    shutil.copyfile(root / "baseline/run_info.json", root / name / "run_info.json")
                    rc = evaluate.main(["--track", "t12", "--config", args.config, "--gt", str(truth),
                                        "--pred", str(root / name / "batch_decisions.csv"), "--run-name", name,
                                        "--out", str(root / f"metrics_{name}.json")])
                    if rc:
                        break
            if not rc:
                compare.main([str(root / "metrics_baseline.json"), str(root / "metrics_poc.json"),
                              "--out", str(root / "table_baseline_vs_poc.md")])
                # README contract: official numbers live in reports/ under these exact names.
                reports = Path(args.reports)
                reports.mkdir(parents=True, exist_ok=True)
                for name in ["metrics_baseline.json", "metrics_poc.json", "metrics_all_hold.json", "metrics_all_rework.json"]:
                    shutil.copyfile(root / name, reports / name)
                shutil.copyfile(root / "table_baseline_vs_poc.md", reports / "table1_baseline_vs_poc.md")
    (root / "execution.log").write_text(capture.getvalue(), encoding="utf-8")
    if rc:
        print(f"Pipeline failed (exit {rc}); see {root / 'execution.log'}", file=sys.stderr)
        return rc
    checks = {name: validate_artifacts(root / name, checked_input) for name in variants}
    # Run tests in the active Python environment, not another pytest.exe from PATH.
    result = subprocess.run([sys.executable, "-m", "pytest", "-o", "addopts=", "-q"],
                            capture_output=True, text=True, encoding="utf-8", errors="replace")
    (root / "test_results.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
    # Preserve actual Git evidence; do not invent authors, commits or team contributions.
    try:
        git_evidence = subprocess.run(["git", "shortlog", "-sne", "--all"], capture_output=True,
                                      text=True, encoding="utf-8", errors="replace")
        (root / "git_evidence.txt").write_text(git_evidence.stdout + git_evidence.stderr, encoding="utf-8")
    except FileNotFoundError:
        (root / "git_evidence.txt").write_text("Git executable unavailable; collect evidence on the submission machine.\n", encoding="utf-8")
    owner = str(config.get("owner", "")).strip()
    owner_configured = bool(owner) and "TODO" not in owner.upper()
    group_configured = bool(config.get("group_id")) and config["group_id"] != "G00"
    automated_pass = result.returncode == 0 and all(c["automated_checks_passed"] for c in checks.values())
    ready = (automated_pass and mode == "official" and owner_configured and group_configured and
             checks["poc"]["human_review_complete"] and checks["poc"]["hold_guardrail_pass"])
    write_json(root / "submission_checks.json", dict(mode=mode, simulated=mode == "demo",
               automated_checks_passed=automated_pass, tests_exit_code=result.returncode,
               owner_configured=owner_configured, group_configured=group_configured,
               official_results_available=mode == "official", variants=checks,
               technical_submission_ready=ready,
               note="Report, individual Git contributions, slides and final tags are completed by the team."))
    print(f"T12 mode={mode}; automated checks: {'PASS' if automated_pass else 'FAIL'}")
    print(f"PoC HOLD guardrail: {'PASS' if checks['poc']['hold_guardrail_pass'] else 'FAIL'}; "
          f"human review complete: {checks['poc']['human_review_complete']}")
    print(f"Artifacts: {root}; technical submission ready: {ready}")
    print(f"Review: {root / 'poc/contact_sheet.html'}")
    return 0 if automated_pass and (ready or not args.require_ready) else 2


if __name__ == "__main__":
    raise SystemExit(main())
