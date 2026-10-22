# Training-02: controlled calibration and recall experiment

This extends the existing research pipeline. It reads `ml/runs/training-01`,
verifies its contents and never modifies it. The active FastAPI model directory
and all five existing project modules remain unchanged. No emergency
notifications are enabled.

Results are local under `ml/runs/training-02/`. Read its generated
`technical_report.md`, `evaluation_table.csv` and `per_station_metrics.csv` for
actual outcomes. The run directory is ignored by Git, like other local ML runs.

## Run the stages

From the repository root, using the already installed backend environment:

```bash
cd /home/mohanx13/UNI/cs314/fiji-flood-risk-system
```

1. Audit the pinned data, original classifier, splits, station holdout, labels,
   feature reconstruction and new feature availability:

```bash
MPLCONFIGDIR=/tmp/is314-mpl OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
  backend/.venv/bin/python -m ml.training02 audit
```

2. Run the predeclared logistic, CatBoost and LightGBM search. Fit preprocessing
   and classifiers on original training rows, select hyperparameters on tuning
   rows, and fit sigmoid/isotonic on separate calibration rows. This stage also
   produces validation PR/calibration plots and training-only KMeans:

```bash
MPLCONFIGDIR=/tmp/is314-mpl OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
  backend/.venv/bin/python -m ml.training02 fit
```

3. Select the model/calibration on the model-selection block, then select a
   recall-oriented threshold on the separate threshold block using the
   user-approved baseline false-alerts-per-detection budget. Save feature
   importance and lock the model, threshold, code and holdout hashes:

```bash
MPLCONFIGDIR=/tmp/is314-mpl OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
  backend/.venv/bin/python -m ml.training02 select
```

4. Score the locked original/selected policies on the exact original temporal
   and entirely unseen-station records. No fitting or selection occurs here:

```bash
MPLCONFIGDIR=/tmp/is314-mpl OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
  backend/.venv/bin/python -m ml.training02 evaluate
```

5. Render the readable report from saved measurements, without retraining:

```bash
MPLCONFIGDIR=/tmp/is314-mpl backend/.venv/bin/python -m ml.training02 report
```

For a fresh complete run, use one command and a **new empty directory**:

```bash
MPLCONFIGDIR=/tmp/is314-mpl OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
  backend/.venv/bin/python -m ml.training02 all --out ml/runs/training-02-reproduction
```

All stages accept `--out` and `--baseline`; use the same values at every stage.
The audit refuses an existing output directory or any path overlapping the
baseline. Completed fit, selection and evaluation stages refuse overwrite.
Changes after selection invalidate the lock. A new run does not authorize
retuning against the existing known test results.

## Study design and interpretation

- Original cohort, sampling keys, training rows, temporal test and six entire
  held-out stations remain fixed. Raw unknown/positive-only labels remain
  excluded. Required histories must exist; no new cohort is chosen to improve
  scores.
- Original validation is split into tuning (2022 H1), calibration (2022 H2),
  model selection (2023 H1) and threshold selection (2023 H2). Every boundary
  has a three-day embargo. All calibration uses `FrozenEstimator` so the base
  classifier/preprocessing cannot refit on calibration records.
- Twenty-eight search configurations compare original and extended features,
  weighted/unweighted logistic regression, regularized LightGBM and CatBoost.
  Hyperparameters use tuning AP. The model/calibration criterion is selection
  Brier, retaining at least 95% of baseline AP on the same validation block.
- Additional histories are trailing 72h rainfall totals, 3-day discharge mean,
  signed discharge changes over 1/3/7 days, relative 3-day discharge change and
  7-day soil-water change. Existing daily rain supplies the 24h total, and
  existing trailing sums supply the 7-day total. No future field or flood flag
  is an input. Inference still requires the closed historical feature day;
  real-time reanalysis availability cannot be established from these files.
- The selected threshold maximizes validation recall while keeping FP/TP no
  worse than the original model's original threshold on the same validation
  block. Absolute FP counts and rates are also shown. F1/default-.5 and
  original-model threshold-only comparisons separate ranking/calibration gains
  from operating-point changes. Cost-ratio sensitivity includes the no-alert
  option and does not drive model selection.
- The original test's results were already seen. This is a **retrospective
  frozen comparison**, not a fresh blind test. No final-test fitting occurs,
  but new independent prospective data are needed for confirmation.
- Seasonal half-year prevalence differs substantially, and selection has only
  31 positive labels. Isotonic calibration and AP may be unstable. Do not
  describe a small numerical improvement as established generalization.
- KMeans uses training-only log1p/standardization and silhouette selection.
  Flood incidence is a post-hoc source-label association, never a validated
  risk class. Optional HDBSCAN is not used in this controlled experiment.

## Saved outputs

- `plan.json`, `split_audit.json`, `audit/`, `feature_audit.csv`,
  `partition_summary.csv`, `row_manifest.csv`: provenance and screening.
- `development.parquet`, `evaluation_holdout.parquet`: physically separate
  development/final data; fitting functions read development only.
- `hyperparameter_search.*`, `candidate_models.json`, `candidates/`,
  `development_metrics.csv`, `selection_metrics.csv`: fitted alternatives and
  measured train/validation comparisons, including weighted/unweighted C=1 LR.
- `feature_set_comparison.csv`: descriptive validation comparisons of original
  and hydrological feature sets within each family/weight group.
- `validation_pr_calibration.png`, `validation_reliability_bins.csv`,
  `validation_threshold_tradeoffs.png`, `threshold_tradeoffs.csv`,
  `cost_sensitivity.json`, `thresholds.json`: probability/decision tradeoffs.
- `selection_lock.json`, `classifier.joblib`, `feature_schema.json`,
  `model_metadata.json`, `provenance.json`, `stations.json`: compatible selected
  inference bundle. The original binary/thresholds are separately copied.
- `evaluation_table.csv`, `evaluation.json`, `per_station_metrics.csv`,
  `per_station_differences.csv`, `all_predictions.parquet`,
  `final_comparison.png`: final comparisons and confusion matrices.
- `validation_permutation_importance.csv`, `native_feature_importance.csv`,
  `feature_importance.png`: validation permutation and supported native
  importance; correlated features limit interpretation.
- `clustering.joblib`, `clustering.json`, `cluster_weather_profiles.csv`,
  `cluster_incidence.csv`, `cluster_assignments.csv`, and cluster plots:
  weather-pattern exploration, without target-based clustering.
- `reproducibility.json`, `technical_report.md`, `verification.json`: run
  identity, limitations and executed verification.

## Test compatibility without deploying

```bash
MPLCONFIGDIR=/tmp/is314-mpl OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
  backend/.venv/bin/python -m pytest ml/tests -q
cd backend
.venv/bin/python -m pytest tests/test_research_predictions.py tests/test_training02_compatibility.py -q
```

Real-artifact API tests override `RESEARCH_MODEL_DIR` only inside isolated tests.
They check existing endpoint schemas, approved-user authentication, persisted
replay parity and separation from Fiji predictions/public alerts. The current
server continues to use its existing setting. No frontend rebuild or API route
change is needed to make a standard scikit-learn calibrated artifact compatible.

Do not automatically deploy this study's winner. The source has no established
redistribution license, negative labels are not independently verified, and no
result validates Fiji or public emergency warnings.
