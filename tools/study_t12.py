"""Bounded multi-seed simulation: cost/miss/uncertainty trade-off, not official scores.

Every seed in the declared range is retained; there is no best-seed selection.
"""
import argparse
from contextlib import redirect_stdout
import io
from pathlib import Path

import numpy as np
import pandas as pd

from src.common.io import write_json
from tools.demo_t12 import main as demo_main


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="out/t12_study")
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    if not 2 <= args.repeats <= 100:
        parser.error("--repeats must be between 2 and 100")
    root = Path(args.output)
    root.mkdir(parents=True, exist_ok=True)
    seeds = list(range(args.seed, args.seed + args.repeats))
    write_json(root / "study_protocol.json", dict(simulated=True, seeds=seeds,
               scenarios=[0.01, 0.03, 0.08, 0.15, 0.30], protocol_version=2,
               generator_version=2, label_rng_domain=12001,
               note="All planned seeds are reported. Monte Carlo SE describes this generator only; not official performance."))
    results = []
    for i, seed in enumerate(seeds):
        destination = root / f"seed_{seed}"
        log = io.StringIO()
        with redirect_stdout(log):
            rc = demo_main(["--output", str(destination), "--seed", str(seed)])
        (destination / "execution.log").write_text(log.getvalue(), encoding="utf-8")
        if rc:
            print(f"Study failed at seed {seed}: {destination}")
            return rc
        result = pd.read_csv(destination / "cost_tradeoff.csv")
        result["replicate"] = i
        results.append(result)
        print(f"Simulation {i + 1}/{len(seeds)} complete")
    frame = pd.concat(results, ignore_index=True)
    frame.to_csv(root / "replicate_metrics.csv", index=False)
    metrics = ["audits_per_decision", "mae", "bad_batch_miss_rate", "hold_rate",
               "false_reject_rate", "ci_coverage", "budget_violations"]
    summary = []
    for variant, group in frame.groupby("variant", sort=True):
        for metric in metrics:
            values = group[metric]
            summary.append(dict(variant=variant, metric=metric, repeats=len(group),
                                mean=values.mean(), std=values.std(ddof=1),
                                monte_carlo_se=values.std(ddof=1) / np.sqrt(len(group)),
                                minimum=values.min(), maximum=values.max(), simulated=True))
    pd.DataFrame(summary).to_csv(root / "summary.csv", index=False)
    print(f"Simulation-only study artifacts: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
