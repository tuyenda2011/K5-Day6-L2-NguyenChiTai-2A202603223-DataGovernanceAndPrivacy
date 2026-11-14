"""Render T12 report tables from recorded artifacts; never invent evaluation numbers.

python -m tools.build_t12_report_tables
Only reads existing JSON/CSV and updates marked report tables, without rerunning evaluation.
"""
import json
from pathlib import Path
import re

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def read_json(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def main():
    qa = ROOT / "reports/t12_qa"
    baseline = read_json("reports/t12_simulated/metrics_baseline.json")
    poc = read_json("reports/t12_simulated/metrics_poc.json")
    tables = {"baseline": (ROOT / "reports/t12_simulated/table_baseline_vs_poc.md").read_text(
        encoding="utf-8").replace("mean |est - true|", r"mean \|est - true\|").strip()}
    base_slices = {row["slice"]: row for row in baseline["extra"]["slices"]}
    rows = ["| Batch | N input | Tỉ lệ lỗi thật (mô phỏng) | Baseline ước lượng | PoC ước lượng | Baseline / PoC |",
            "|---|---|---|---|---|---|"]
    sizes = pd.read_csv(ROOT / "fixtures/t12_vendor_batches/batches.csv").groupby("batch_id").size()
    for row in poc["extra"]["slices"]:
        b = base_slices[row["slice"]]
        rows.append(f"| {row['slice']} | {sizes[row['slice']]} | {row['true_error_rate']:.6f} | "
                    f"{b['est_error_rate']:.6f} | {row['est_error_rate']:.6f} | {b['dec']} / {row['dec']} |")
    tables["slices"] = "\n".join(rows)
    study = pd.read_csv(ROOT / "reports/t12_simulated/study_summary_seeds1000-1099.csv").set_index(["variant", "metric"])
    rows = ["| Phương án | MAE (fraction), mean ± SE | HOLD rate, mean ± SE | CI coverage, mean ± SE | Audit/batch |",
            "|---|---|---|---|---|"]
    for variant in ["baseline", "poc", "balanced", "sequential", "all_hold", "all_rework"]:
        cells = []
        for metric in ["mae", "hold_rate", "ci_coverage"]:
            r = study.loc[(variant, metric)]
            cells.append(f"{r['mean']:.4f} ± {r['monte_carlo_se']:.4f}")
        audits = study.loc[(variant, "audits_per_decision"), "mean"]
        rows.append(f"| {variant} | " + " | ".join(cells) + f" | {audits:.2f} |")
    tables["study"] = "\n".join(rows)
    original = pd.read_csv(ROOT / "reports/t12_review/batch_decisions_raw.csv").set_index("batch_id")
    final = pd.read_csv(ROOT / "reports/t12_review/batch_decisions.csv").set_index("batch_id")
    reviewed = pd.read_csv(ROOT / "reports/t12_review/review_queue_reviewed.csv").set_index("item_id")
    rows = ["| Batch | Lỗi thấy / đã audit | CI 95% | Review đã xác nhận | Trước → sau |",
            "|---|---|---|---|---|"]
    for bid, row in original.iterrows():
        rows.append(f"| {bid} | {row.n_errors_observed}/{row.n_audited} | [{row.ci_low:.2f}; {row.ci_high:.2f}] | "
                    f"{reviewed.loc[bid, 'reviewer_decision']} | {row.decision} → {final.loc[bid, 'decision']} |")
    tables["review"] = "\n".join(rows)
    summary = read_json("reports/t12_qa/qa_summary.json")
    counts = summary["tests"]
    tables["qa"] = "\n".join([
        "| Kiểm tra | Kết quả thực chạy |", "|---|---|",
        f"| pytest | {counts['passed']} passed, {counts['skipped']} skipped, {counts['failures']} failed, {counts['errors']} errors |",
        f"| Manifest | {summary['manifests_output'].strip().splitlines()[-1]} |",
        f"| Python | {summary['machine']['python']} |",
        f"| OS | {summary['machine']['platform']} |",
        f"| CPU | {summary['machine']['processor']} |",
        f"| Source commit QA | `{summary['source_commit']}` |"])
    report_path = ROOT / "reports/group_report.md"
    report = report_path.read_text(encoding="utf-8")
    for name, content in tables.items():
        (qa / f"table_{name}.md").write_text(content + "\n", encoding="utf-8")
        pattern = rf"(<!-- BEGIN GENERATED {name} -->).*?(<!-- END GENERATED {name} -->)"
        report = re.sub(pattern, lambda m: m[1] + "\n\n" + content + "\n\n" + m[2], report, flags=re.S)
    report_path.write_text(report, encoding="utf-8")
    print("Updated 5 tables from recorded artifacts and reports/group_report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
