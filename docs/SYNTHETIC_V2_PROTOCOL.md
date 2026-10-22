# Synthetic v2 tuning protocol (pre-registered)

Registered: 2026-10-19, before any v2 hyperparameter search or reserved-evaluation
scoring. Synthetic Data — Research Demonstration; all metrics are simulator-based.

## Frozen benchmark

- Dataset: `ml/data/synthetic_fiji/v1` (SHA256-verified against
  `dataset_metadata.json`; not regenerated, not modified).
- Simulator: `ml/synthetic/generate.py` unchanged.
- v1 run `ml/runs/synthetic-v1` and serving bundle `ml/artifacts/synthetic/v1`
  are preserved untouched.

## Evaluation-role designation

v1 test-period results (2024 H2–2025, locations seen in training) were already
inspected during v1 development; they are designated **diagnostic** for v2 and
cannot select hyperparameters, calibration or thresholds.

| Data | Role |
|---|---|
| Train 2021-01-01→2023-01-01 (−24 h embargues) | model fitting only |
| Calibration 2023 H1 | Optuna objective, early stopping, calibrator fitting |
| Selection 2023 H2 | model/config choice among top candidates; calibration-method choice |
| Threshold 2024 H1 | operating-threshold selection only |
| Test 2024 H2→2025 (seen locations) | **diagnostic** (previously inspected in v1) |
| Held locations 3/10/12 (test window) | diagnostic |
| Reserved-storm test windows | diagnostic |
| Reserved-eval A: seed 4141, default params, 2024-01-01→2025-12-31 | **independent final evaluation — generated before optimization, unopened until freeze** |
| Reserved-eval B: seed 4141, storm_scale 1.15, drainage_scale 0.85, same window | **independent robustness evaluation — same policy** |

## Hyperparameter budget (fixed)

- CatBoost: 40 Optuna TPE trials (sampler seed 314).
- LightGBM: 30 Optuna TPE trials (sampler seed 314).
- Logistic Regression and Random Forest: untuned v1-style baselines.
- Optuna objective (calibration 2023 H1): maximize budget-feasible recall
  (FP/TP ≤ 75/42 = 1.785714), tie-break higher AP, then F2; infeasible trials
  score −1. Early stopping on the calibration block (CatBoost `early_stopping_rounds=200`,
  LightGBM `early_stopping_rounds=100`).
- Top-5 calibration-objective configs per family are re-evaluated on selection
  (fresh budget threshold per config). Winner = max selection recall under
  budget, then AP, F1, Brier (v1 rule).

## Calibration and threshold (validation only)

- Calibrators: none, sigmoid (logistic on logit), isotonic — fit on calibration
  2023 H1 only; method chosen on selection 2023 H2 by lowest ECE(10), tie-break
  Brier.
- Threshold: budget policy on threshold 2024 H1 only.

## Promotion criteria (pre-registered)

The v2 winner replaces the v1 serving candidate only if all hold:

1. Feasible under the 75/42 budget on selection.
2. Selection recall > 0.8824 **and** selection AP ≥ 0.74139 (v1 catboost__none).
3. Diagnostic test PR-AUC ≥ 0.25 and test event recall ≥ 0.80 (guard against
   catastrophic regime overfit).
4. Reserved-eval A reported before promotion is finalised; severe collapse
   (reserved-A PR-AUC < 0.15 or event recall < 0.5) vetoes promotion.

Otherwise v1 stays the deployed candidate; v2 results are recorded only.

## Feature sets

- `extended` (primary): v1 features + strictly causal new features (see
  `ml/synthetic/features_v2.py`); no label, scenario, hidden state or future
  observation may enter.
- `weather_only` (comparison): meteorological channels + geography + time only
  (no river level/discharge/soil channels), same protocol, used for the
  weather-vs-hydrology feature comparison.

## Compute budget

CPU only, ≤4 threads per fit, Optuna trials sequential. No test/reserved data
may be loaded before the freeze step of `ml/synthetic/train_v2.py`.
