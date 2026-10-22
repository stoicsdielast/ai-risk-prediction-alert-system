# Synthetic v3 scenario protocol (pre-registered)

Registered: 2026-10-19, **before** any v3 training run, hyperparameter trial or
scenario scoring. Synthetic Data — Research Demonstration; every metric in the
v3 study is simulator-based and is not a Fiji MET observation or a validated
flood forecast.

## What is frozen

- Simulator: `ml/synthetic/generate.py` with a scenario layer. The default
  configuration (`scenario="realistic"` without the layer) reproduces the
  original v1 simulator bit-for-bit (verified by
  `test_v1_default_path_unchanged`).
- v1 dataset `ml/data/synthetic_fiji/v1`, v2 reserved sets, run
  `ml/runs/synthetic-v1`, run `ml/runs/synthetic-v2` and serving bundle
  `ml/artifacts/synthetic/v1` are **not regenerated, not modified, not
  overwritten**. v2 results in `docs/SYNTHETIC_V2_RESULTS.md` are unchanged.
- Deployed model stays the v1 serving candidate. **Nothing in v3 is promoted
  automatically.**

## Datasets (generated once, before tuning)

| Scenario | Path | Seed | Version | SHA256 of `dataset_metadata.json` |
|---|---|---|---|---|
| controlled | `ml/data/synthetic_fiji/v3/controlled` | 5101 | synthetic-fiji-v3-controlled | `79c964510d24a2ad8e7192857c8aef03a36a292bb920207f7461a5bbbc70cbd7` |
| realistic | `ml/data/synthetic_fiji/v3/realistic` | 5102 | synthetic-fiji-v3-realistic | `8b3d5401bf1978ab18be8a156aeb315e18da8f81e310aaeb756c03361423e75d` |
| stress | `ml/data/synthetic_fiji/v3/stress` | 5103 | synthetic-fiji-v3-stress | `26e6937737063d588460b8ae51129022c1a098fb241a6ada7c6e5ee2b0c941f2` |

Scenarios are **separate experiments with separate seeds and separate
simulator settings**; they are never pooled into a single headline score.

| Scenario | Flood events | Positive 24 h labels | Prevalence | Mean missingness | Purpose |
|---|---|---|---|---|---|
| controlled | 353 | 8,472 | 0.0167 | ~0.001 | learnability / pipeline correctness |
| realistic | 254 | 6,096 | 0.0119 | ~0.006 | harder benchmark, v1-style conditions |
| stress | 752 | 18,048 | 0.0381 | ~0.071 | out-of-distribution robustness |

Stress has a different class prior and a different covariate distribution; its
PR-AUC is therefore always reported next to its own prevalence and precision
lift, never compared as if it were the same task.

## Target and horizon (identical in every scenario)

- `flood_within_24h`: strictly new flood onset at `t < onset <= t+24h`, while no
  flood is active at `t`. Active floods are excluded via `forecast_eligible`;
  an incomplete future horizon is nullable.
- `flood_occurred` (current flood status) is stored separately and is never a
  model input.
- Same partitions, same 75/42 false-alert budget, same held-out locations as v1
  and v2, so numbers are comparable across versions.

## Partitioning (unchanged dates, ±24 h embargoes, storm embargo)

| Role | Window | Use |
|---|---|---|
| train | 2021-01-01 → 2023-01-01 | model fitting only |
| calibration | 2023 H1 | early stopping, calibrator fitting |
| selection | 2023 H2 | candidate/config choice, calibration-method choice |
| threshold | 2024 H1 | operating-threshold choice only |
| test | 2024 H2 → 2025 | **diagnostic** |
| held_location | locations 3/10/12, test window | **diagnostic**, never trained on |
| storm_holdout / held_location_storm | reserved storms (`sha256(scenario_id)%5==0`) | **diagnostic** |

A row whose storm span crosses a partition boundary is embargoed. Rows within
24 h of a temporal boundary are embargoed. `forecast_eligible == False` and
`history_ready == False` rows are excluded.

## Tuning budget (fixed before any trial)

- Inner time-safe folds inside `train`: the training window is cut into **4**
  contiguous, chronologically ordered day blocks (K+1 with K = 3 folds). Block 0
  is the fitting prefix; fold `k` trains on all earlier blocks (minus a 24 h
  embargo) and validates on block `k+1`. Any storm whose span started before a
  validation block but reaches into it is removed from that block's validation
  rows (event/scenario grouping, so one flood episode never appears on both
  sides of a split).
- Optuna TPE, sampler seed **314**: CatBoost **24** trials, LightGBM **18**
  trials, sequential, ≤4 threads per fit.
- Objective: mean budget-feasible recall (FP/TP ≤ 75/42 = 1.785714) across the
  three inner folds, tie-break mean AP, then F2; infeasible trials score −1.
- Top-5 configs per family are refit on `train` (early stopping on
  `calibration`) and ranked on `selection` by recall under budget, then AP, F1,
  Brier. Winner per family, then overall winner.
- Logistic Regression and Random Forest: untuned v1-style baselines.
- Weather-only ablation: winner config of each boosting family refit on the
  weather-only feature set, same protocol.
- Calibration: none vs sigmoid vs isotonic, fit on calibration, chosen on
  selection by lowest ECE(10), tie-break Brier.
- Threshold: budget policy on the threshold partition only.
- Baselines: train-prevalence majority, and the v1 hydrological rule
  (`rainfall_mm_total_24h > 80 and soil_moisture_pct > 75`).

## Out-of-distribution evaluation (fixed now)

The **realistic**-scenario winner (features, calibrator and threshold fixed on
realistic validation data only) is applied unchanged to the controlled and
stress datasets. No re-tuning, no re-thresholding, no recalibration on the OOD
data. This is the only cross-scenario transfer reported.

## Metrics (all scenarios, same definitions)

Classification: precision, recall, F1, balanced accuracy, accuracy, PR-AUC
(average precision), ROC-AUC, Brier, ECE(10), confusion matrix, false alerts
per 1000 observations.

Event level: eligible events, events detected, event recall, median warning
lead hours. Alert episodes: hourly positive predictions are merged into an
episode when the gap is ≤ 6 h; an episode is a **true alarm episode** if an
event onset occurs within 24 h after the episode ends, otherwise it is a
**false alarm episode**; after a true alarm a 12 h cooldown suppresses
duplicate alarms for the same onset. Reported: alarm episodes, false alarm
episodes, false alarm episodes per 1000 observations.

Uncertainty: 95% percentile intervals from a block bootstrap over contiguous
24 h days (200 replicates, seed 314) for PR-AUC, recall, precision and F1 on
the test partition.

Reporting: per scenario, per location, held-out locations, unseen storms.
Controlled / realistic / stress results are tabulated separately.

## Explicitly out of scope

- No promotion or deployment decision: results are recorded only, and any
  change to the deployed model requires a separate human decision.
- No iteration against test, held-location or storm-holdout partitions; if a
  diagnostic number has been seen during development it stays diagnostic.
- No pooling of scenarios, no relabelling, no hidden simulator state in
  features.
