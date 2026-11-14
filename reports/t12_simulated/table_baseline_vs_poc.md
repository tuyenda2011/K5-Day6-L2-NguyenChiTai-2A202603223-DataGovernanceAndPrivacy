Baseline: `simulated_baseline` (git e81b153, seed 42) · PoC: `simulated_poc` (git e81b153, seed 42)

| Metric (unit) | Slice | Baseline | PoC | Δ abs | Δ rel | Better | N |
|---|---|---|---|---|---|---|---|
| **MAE error-rate estimate** (mean |est - true| over batches (fraction)) | all | 0.0600 | 0.0421 | -0.0179 | -29.8% | lower | 5 |
| **Bad-batch Recall** (bad batches not ACCEPTed / bad batches (reported separately from MAE)) | all | 1.0000 | 1.0000 | 0.0000 | +0.0% | higher | None |
| False reject rate (good batches sent to REWORK / good batches) | all | 0.0000 | 0.0000 | 0.0000 | baseline=0 | lower | None |
| HOLD rate (batches on HOLD / batches) | all | 0.8000 | 0.8000 | 0.0000 | +0.0% | lower | None |
| CI coverage (batches whose CI contains true rate / batches (nominal 0.95)) | all | 0.8000 | 1.0000 | 0.2000 | +25.0% | higher | 5 |
| Budget violations (batches audited above budget 20) | all | 0.0000 | 0.0000 | 0.0000 | baseline=0 | lower | 5 |
| Guardrail: HOLD rate <= 0.4 (1 = pass, 0 = fail (constrained primary)) | all | 0.0000 | 0.0000 | 0.0000 | baseline=0 | higher | None |
| Runtime / 100 items (s) | all | 0.0477 | 0.0452 | | | lower | |
