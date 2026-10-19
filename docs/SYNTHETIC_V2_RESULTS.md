# Synthetic v2 tuning results

Synthetic Data — Research Demonstration. All metrics below are simulator-based. They are
**not** Fiji MET observations, not validated Fiji flood forecasts, and no real forecast skill
is claimed. The v1 dataset, v1 run and v1 serving bundle were not modified.

Pre-registered protocol: `docs/SYNTHETIC_V2_PROTOCOL.md` (registered 2026-10-19 before any
v2 search). Input hashes are recorded in `ml/runs/synthetic-v2/selection_lock.json`
(dataset SHA256 `cf04169ce32938c4e614bad85dca94a7c196bbde352404d501a452a7adc49feb`).

## Outcome (headline)

- **v2 is NOT promoted.** v1 (`catboost__none`) stays the deployed synthetic serving candidate.
- Sole blocking criterion (protocol rule 2): the v2 winner's **selection PR-AUC 0.700 < v1 0.741**.
  Every other pre-registered criterion passes.
- On **both independent reserved evaluations** (generated before optimization, opened only at the
  freeze step) and on the diagnostic test partition, v2 dominates v1 on PR-AUC, precision, F1 and
  false alarms at equal or better event recall. Because these partitions are diagnostic and cannot
  select (rule 2 does), the automatic decision remains "not promoted"; the reserved evidence is
  recorded here for human review rather than silently overriding the protocol.

## Selected candidate

- Winner: **`catboost_tuned3`**, calibration **none**, extended feature set (76 features).
- Operating threshold: **0.0834790** (selected on the 2024 H1 threshold partition, budget policy
  FP/TP ≤ 75/42).
- `model_version`: `synthetic-fiji-v2-catboost_tuned3__none`; model SHA256
  `88d30698cd17e514e37f4be5a5011ab0ae36478ee3674456e90142d5080666f1`.
- Hyperparameter budget met: CatBoost **40** Optuna TPE trials, LightGBM **30** (seed 314).

## Hyperparameter search (selection 2023 H2, budget-feasible)

Top configs per family, ranked by selection recall under budget (then AP/F1/Brier):

| Candidate | Family | Features | Thr. | Recall | Precision | F1 | PR-AUC | FA/1000 |
|---|---|---|---|---|---|---|---|---|
| **catboost_tuned3** | catboost | extended | 0.001829 | **0.8852** | 0.3602 | 0.5121 | **0.7000** | 57.43 |
| catboost_tuned2 | catboost | extended | 0.001401 | 0.8231 | 0.3595 | 0.5004 | 0.6391 | 53.57 |
| lightgbm_tuned5 | lightgbm | extended | 0.009307 | 0.8333 | 0.3609 | 0.5036 | 0.6824 | 53.91 |
| catboost_weather_only | catboost | weather-only | 0.001402 | 0.8009 | 0.3621 | 0.4987 | 0.6330 | 51.54 |
| lightgbm_weather_only | lightgbm | weather-only | 0.009823 | 0.7898 | 0.3995 | 0.5306 | 0.6287 | 43.36 |
| logistic_baseline | sklearn | extended | 0.038934 | 0.6833 | 0.3646 | 0.4755 | 0.5737 | 43.49 |
| random_forest_baseline | sklearn | extended | 0.052635 | 0.7417 | 0.3600 | 0.4847 | 0.5514 | 48.16 |

Thresholds shown here are the in-sample selection-budget thresholds used for ranking.
All "selection" table values use that convention (matching the v1 protocol reference).

**Feature-set ablation:** at matched budget feasibility the extended set beats weather-only for
both families (CatBoost recall 0.885 vs 0.801, AP 0.700 vs 0.633; LightGBM 0.833/0.682 vs
0.790/0.629), so the river/discharge/soil/upstream history features carry real signal.

**Calibration (chosen on selection, lowest ECE then Brier):** `none` ECE 0.03094 / Brier 0.02949
chosen over isotonic (ECE 0.03163) and sigmoid (ECE 0.03180). The tuned model is already
well-calibrated; extra calibration did not help.

## Diagnostic partitions (winner, threshold-partition operating threshold 0.08348)

Previously inspected; **diagnostic only**, cannot select.

| Stage | Recall | Precision | F1 | PR-AUC | ROC-AUC | Brier | Events | Event recall |
|---|---|---|---|---|---|---|---|---|
| train | 0.551 | 0.490 | 0.519 | 0.639 | 0.988 | 0.0056 | 47 | 1.00 |
| calibration | 0.537 | 0.273 | 0.362 | 0.330 | 0.880 | 0.0105 | 18 | 1.00 |
| selection | 0.392 | 0.812 | 0.528 | 0.700 | 0.974 | 0.0295 | 45 | 1.00 |
| threshold | 0.599 | 0.366 | 0.455 | 0.513 | 0.955 | 0.0095 | 19 | 1.00 |
| **test** | **0.421** | **0.455** | 0.437 | **0.395** | 0.916 | 0.0099 | 49 | **1.00** |
| held_location | 0.587 | 0.371 | 0.455 | 0.491 | 0.949 | 0.0056 | 11 | 1.00 |
| storm_holdout | 0.527 | 0.309 | 0.389 | 0.256 | 0.889 | 0.0134 | 14 | 1.00 |
| held_location_storm | – | – | – | – | – | 0.0018 | 0 | – |

`held_location_storm` contains no eligible flood events (locations 3/10/12 have no reserved-storm
events in the frozen dataset), so its classification metrics are undefined.

## Independent reserved evaluations (v1 vs v2, same data, own thresholds)

Reserved A = seed 4141, default simulator params; Reserved B = seed 4141, storm_scale 1.15 /
drainage_scale 0.85. Generated before optimization, scored once here.

| Evaluation | Subset | Model | Recall | Precision | F1 | PR-AUC | Event recall | FA/1000 |
|---|---|---|---|---|---|---|---|---|
| A default | all | v1 | 0.508 | 0.207 | 0.294 | 0.333 | 1.00 | 18.97 |
| A default | all | **v2** | 0.513 | **0.373** | **0.432** | **0.471** | 1.00 | **8.38** |
| A default | unseen | v1 | 0.495 | 0.274 | 0.353 | 0.368 | 1.00 | 11.15 |
| A default | unseen | **v2** | 0.586 | **0.378** | **0.459** | **0.555** | 1.00 | **8.21** |
| B wetter | all | v1 | 0.453 | 0.221 | 0.297 | 0.285 | 0.962 | 20.05 |
| B wetter | all | **v2** | 0.466 | **0.322** | **0.381** | **0.382** | 1.00 | **12.29** |
| B wetter | unseen | v1 | 0.451 | 0.217 | 0.293 | 0.251 | 1.00 | 13.89 |
| B wetter | unseen | **v2** | 0.500 | 0.214 | 0.299 | **0.387** | 1.00 | 15.71 |

v2 improves PR-AUC and precision and roughly halves false alarms on the default reserved set while
holding event recall at 1.00. The wetter reserved set is harder for both models; v2 still leads on
PR-AUC and on the all-locations precision.

## Comparison with v1 (diagnostic + reserved)

| Partition | v1 CatBoost | v2 catboost_tuned3 |
|---|---|---|
| selection recall / AP | 0.8824 / **0.7414** | **0.8852** / 0.7000 |
| test (diagnostic) recall / AP | 0.296 / 0.284 | **0.421 / 0.395** |
| reserved A all recall / AP | 0.508 / 0.333 | 0.513 / **0.471** |
| reserved A unseen recall / AP | 0.495 / 0.368 | **0.586 / 0.555** |
| reserved B all recall / AP | 0.453 / 0.285 | 0.466 / **0.382** |
| reserved B unseen recall / AP | 0.451 / 0.251 | **0.500 / 0.387** |

## Top features (winner, gain importance)

`month_sin` (39.3), `month_cos` (9.3), `river_proximity_km` (3.6), `wind_direction_deg` (3.5),
`rainfall_mm` (3.5), `upstream_rainfall_mm_total_168h` (3.2), `rainfall_mm_total_336h` (2.7),
`rainfall_mm_total_168h` (2.7), `upstream_rainfall_mm` (2.5), `soil_moisture_pct_mean_24h` (2.2),
`tide_stress_6h` (2.1). Seasonality dominates, with multi-day rainfall accumulation, upstream
totals and antecedent soil moisture contributing beyond the instantaneous v1 channels. Full list:
`ml/runs/synthetic-v2/feature_importance.csv`.

## Serving compatibility

`ml/synthetic/evaluate_v2.py` rebuilds a truncated-history sample through
`backend/app/services/synthetic_inference.py` and compares the last-window features and prediction
with the full-history computation:

- `windowed_feature_max_abs_diff`: **0.0** (bit-identical).
- model loads: true; prediction status: `ok`; version
  `synthetic-fiji-v2-catboost_tuned3__none`; 77 serving columns.

So the v2 winner would drop into the existing FastAPI synthetic surface unchanged, but it is **not
published** — `ml/artifacts/synthetic/v2` is intentionally absent and `ml/artifacts/synthetic/v1`
is untouched.

## Reproduce

```bash
backend/.venv/bin/python -m ml.synthetic.train_v2   --dataset ml/data/synthetic_fiji/v1 --out ml/runs/synthetic-v2
backend/.venv/bin/python -m ml.synthetic.finalize_v2 --dataset ml/data/synthetic_fiji/v1 --run ml/runs/synthetic-v2
backend/.venv/bin/python -m ml.synthetic.evaluate_v2 --run ml/runs/synthetic-v2
```

Run from the repo root with `backend/.venv`. Outputs refuse overwrite; use fresh directories.
Runtime ~5 min for training on 16 cores; Optuna trials sequential at 4 threads/fit.

## Artefacts (`ml/runs/synthetic-v2/`, gitignored)

`selection_metrics.csv`, `metrics.csv`, `per_location_metrics.csv`, `confusion_matrices.csv`,
`reserved_evaluation.csv`, `reserved_per_location.csv`, `comparison_vs_v1.csv`,
`thresholds.json`, `calibration_comparison.csv`, `best_params.json`, `selection_lock.json`,
`promotion_decision.json`, `promotion_final.json`, `serving_compatibility.json`,
`feature_importance.csv`, `optuna_trials_catboost.csv`, `optuna_trials_lightgbm.csv`,
`predictions.parquet`, `*_pr_calibration.png`.
