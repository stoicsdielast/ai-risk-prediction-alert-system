# Standalone flood-occurrence AI milestone (DEPRECATED)

> **Deprecated: early India-dataset experiment only.** This milestone was an early
> prototype trained on the Kaggle India CSV and is **not** the deployed model. The
> current model is the **synthetic Fiji CatBoost V1** pipeline under `ml/synthetic`
> (V2/V3 retained for research). The India CSV was used solely in early experiments
> and is intentionally absent from the repository; nothing here should be used for
> new training, promotion or operational decisions.

For the current **six-input demo weather model**, use the
[prototype weather training guide](prototype_weather/README.md). Its dataset,
models and results are in the `prototype_weather` subdirectories. The India
milestone described below uses a different feature schema and remains separate.

This component trains an explainable binary flood-occurrence classifier, saves
its complete preprocessing/model pipeline, and provides standalone probability
and prototype risk-band inference. It does not import backend settings, access
PostgreSQL, or register any FastAPI routes.

**The Kaggle India CSV is development/prototyping data, not official Fiji MET
training data. The model and risk thresholds are not validated for emergency
decisions.** This milestone demonstrates the software pipeline; the measured
results do not establish useful flood prediction capability.

## Dataset and inspection

The original file was `archive/flood_risk_dataset_india.csv`, relative to
the repository root. **The India CSV is no longer part of this project and is
absent from the working tree**; it is documented here only as an early experiment.
Its original Kaggle URL and collection/synthesis methodology were not supplied and
are unverified. The tests no longer read it (`ai/tests/test_pipeline.py` now uses
in-memory fixtures only).

The inspected file contains **10,000 rows and 14 columns**, no missing values,
no duplicate rows, and no repeated rows of the retained feature set.
`Flood Occurred` is the actual target: `0` = non-flood (4,943 records), `1` =
flood (5,057 records). No four-class labels are manufactured.

| Columns | Observed datatype | Role |
| --- | --- | --- |
| `Latitude`, `Longitude` | float64 | Numeric predictors |
| `Rainfall (mm)`, `Temperature (°C)`, `Humidity (%)` | float64 | Numeric predictors |
| `River Discharge (m³/s)`, `Water Level (m)`, `Elevation (m)` | float64 | Numeric predictors |
| `Population Density` | float64 | Numeric predictor; unit unspecified in CSV |
| `Infrastructure` | int64, values 0/1 | Numeric predictor; flag meaning unverified |
| `Land Cover` | string | Categorical predictor |
| `Soil Type` | string | Categorical predictor |
| `Historical Floods` | int64, values 0/1 | Excluded: timing/definition unverified |
| `Flood Occurred` | int64, values 0/1 | Target only; excluded from predictors |

`Land Cover` values: Agricultural, Desert, Forest, Urban, Water Body.
`Soil Type` values: Clay, Loam, Peat, Sandy, Silt. There is no identifier column.
The 12 retained predictors comprise 10 numeric and two categorical columns.
Their exact names, including units and Unicode characters, are the inference
schema. `config.py` records the inspected schema; training rejects changed
columns so that a future dataset requires an explicit feature review.

Each training run prints shape, column datatypes, first five rows, missing
counts, duplicates, categorical unique values, descriptive statistics, target
distribution, numeric target correlations, included/excluded features, and
data concerns before constructing preprocessing. The same inspection is saved
as `artifacts/dataset_summary.json`.

## Preprocessing and split

Each model is a scikit-learn `Pipeline` containing a `ColumnTransformer`:

- Numeric: `SimpleImputer(strategy="median")`, then `StandardScaler`.
- Categorical: `SimpleImputer(strategy="most_frequent")`, then
  `OneHotEncoder(handle_unknown="ignore")`.

Scaling is appropriate for Logistic Regression; the same transforms are used
for Random Forest for a consistent input pipeline. All transforms fit only on
training rows. Unknown category strings are ignored by the encoder at inference.
Missing measurements must use `null` with the feature key still present.

The stratified split uses `test_size=0.20` and `random_state=42`: 8,000 training
records (3,954 non-flood / 4,046 flood) and 2,000 test records (989 non-flood /
1,011 flood). No full-dataset imputation, scaling, encoding, or resampling occurs
before the split. Duplicate feature rows are rejected to prevent them crossing
the split. The dataset SHA-256 and test-row indices are recorded for replay.

## Models, evaluation, and measured results

The baseline is Logistic Regression (`max_iter=1000`). Random Forest uses 200
trees, `min_samples_leaf=2`, `max_features="sqrt"`, and `n_jobs=1` for reproducible
probability accumulation. Both use balanced class
weights and seed 42. There is no expensive parameter search or neural network.

For each model, training calculates accuracy, flood-class precision, recall,
F1, ROC-AUC, a two-class classification report, and a confusion matrix.
Classifier decisions use their default binary decision rule; the risk-band
thresholds do not change training labels or reported classifier metrics.

The completed run on this CSV produced:

| Model | Accuracy | Flood precision | Flood recall | Flood F1 | ROC-AUC |
| --- | ---: | ---: | ---: | ---: | ---: |
| Logistic Regression | 0.502500 | 0.507874 | 0.510386 | 0.509127 | 0.502198 |
| Random Forest | 0.509000 | 0.514428 | 0.511375 | 0.512897 | 0.502166 |

**Random Forest was selected** by lexicographic priority: flood recall, then
F1, ROC-AUC, and accuracy. A tie proceeds to the next metric; an- exact tie keeps
training order. Random Forest detected 517 of 1,011 floods, while Logistic
Regression detected 516. This one-record difference is not evidence of a
meaningful scientific advantage. The selected model still missed 494 floods.

Its confusion matrix has actual classes on rows and predicted classes on
columns, both ordered non-flood, flood:

```text
[[501, 488],
 [494, 517]]
```

An always-flood majority-class reference has accuracy 0.505500 on this split.
Both models' ROC-AUC values are approximately 0.502, close to chance. Numeric
feature/target linear correlations all have absolute magnitude below 0.03.
These observations suggest weak measured signal; they do not prove how the
source dataset was generated.

The same test split is used to compare/select models, as required for this
milestone. These metrics are development comparisons, not an independent final
assessment. An untouched validation dataset or nested/cross-validation selection
procedure is needed before making stronger performance claims.

Random Forest feature importance uses the fitted transformer's
`get_feature_names_out()`. The top ten are river discharge, humidity, water
level, temperature, elevation, rainfall, latitude, population density, longitude,
and infrastructure. Ranked values and the plot are generated from the fitted
forest even if another model wins. Impurity importance tends to favour
continuous/high-cardinality features; these rankings are not causal findings,
particularly with ROC-AUC near chance.

## Prototype risk mapping

| Flood probability | Risk level |
| --- | --- |
| `0 <= p < 0.25` | `LOW` |
| `0.25 <= p < 0.50` | `MODERATE` |
| `0.50 <= p < 0.75` | `HIGH` |
| `0.75 <= p <= 1` | `VERY_HIGH` |

Named thresholds live in `config.py`. The mapping function also accepts an
explicit tuple of three increasing thresholds. These are unvalidated development
thresholds, not official Fiji MET warnings. Probabilities have not been
calibrated. The compatibility field `confidence_percent` means only
`flood_probability * 100`, not confidence that the prediction is correct.

## Exact commands

Run these commands from the repository root. The existing environment uses
Python 3.14; `backend/pyproject.toml` declares Python >=3.14. If the environment
does not exist, first run `python3.14 -m venv backend/.venv`.

```bash
source backend/.venv/bin/activate
python -m pip install -r backend/requirements.txt
cd backend
python -m ai.train
python -m ai.evaluate
python -m ai.predict
```

The default source is resolved relative to the module, independent of the
shell's current directory. A compatible CSV can be explicitly supplied from
the `backend` directory:

```bash
python -m ai.train --dataset ../archive/flood_risk_dataset_india.csv
python -m ai.evaluate --dataset ../archive/flood_risk_dataset_india.csv
```

Evaluation reloads the selected saved model and recreates the original test
split, verifying the CSV hash and row indices. It writes
`artifacts/selected_model_evaluation.json` and the selected-model confusion
matrix without refitting. Both models' training evaluations remain in
`model_results.json` and `model_comparison.csv`. To replay the baseline:

```bash
python -m ai.evaluate --model ai/models/logistic_regression.joblib
```

`python -m ai.predict` uses the first real held-out row saved during training.
In the measured run, zero-based CSV row index 2448 produced probability
0.426643 and `MODERATE`; its actual label was **1 (flood)**. This is a missed
flood under the classifier's binary decision rule, and is intentionally shown
without choosing a more flattering sample. Its real input is available in
`data/processed/test_sample.json`.

To predict another observation, create a JSON object with all 12 exact feature
keys and run from `backend`:

```bash
python -m ai.predict --input path/to/observation.json
```

Missing keys, unknown keys (including target/history), nonnumeric measurements,
infinite values, malformed JSON, and missing model files receive clear errors.

Run standalone AI checks and existing backend regression tests from `backend`:

```bash
python -m pytest ai/tests tests -q
```

## Saved files and layout

```text
backend/ai/
  config.py                  # Paths, inspected schema, prototype thresholds
  inspection.py              # Inspection, validation, fingerprint, JSON output
  preprocessing.py           # Reusable sklearn transformations/pipeline
  train.py                   # Training, comparison, selection, persistence
  evaluate.py                # Shared evaluation, plots, replay command
  predict.py                 # Saved-model inference and sample command
  data/raw/                  # Reserved; original CSV remains in archive/
  data/processed/
    test_split.csv           # Raw held-out feature values and actual target
    test_sample.json         # One real test observation and its actual label
  models/
    flood_risk_model.joblib   # Selected COMPLETE preprocessing/model pipeline
    logistic_regression.joblib
    random_forest.joblib
    model_metadata.json
  artifacts/
    dataset_summary.json
    model_results.json
    model_comparison.csv
    feature_importance.csv
    feature_importance.png
    confusion_matrix.png
    selected_model_evaluation.json
  notebooks/                 # Reserved; notebooks are not required to reproduce
  tests/test_pipeline.py
```

The selected model is stored at **`backend/ai/models/flood_risk_model.joblib`**.
Joblib files and the large test CSV are excluded from Git and regenerated by
training. Reports, plots, metadata, and the small sample remain reviewable.
Only load joblib files created by a trusted training process.

Metadata records model type, UTC training time, dataset filename/hash/shape,
feature schema and exclusions, target, split sizes/distributions/indices,
metrics, version identifier, prototype thresholds, and package/Python versions.
The same metadata is embedded in the pipeline so inference needs only the
joblib file. Training regenerates outputs; metrics are calculated every time,
never taken from this README. Seeds and dependency pins reproduce the measured
results; run identifiers/timestamps intentionally change on each training run.

## Later FastAPI integration and remaining data work

In a later milestone, FastAPI can load `ai.predict.load_model()` once at startup
and call `predict_flood_risk(observation, model=loaded_model)` behind a validated
request schema. It returns flood probability, probability percentage, prototype
risk level, model version, and a UTC prediction timestamp. This milestone makes
no FastAPI, authentication, frontend, or PostgreSQL changes.

Before operational modelling, obtain documented Fiji observations, define the
prediction time/horizon, verify feature availability before the outcome, confirm
units and flag definitions, review the excluded history flag, evaluate temporal
and geographic generalization, assess probability calibration, and agree on
validated warning thresholds. With no timestamps or measurement definitions in
this CSV, concurrent water level/discharge could still be unavailable at a
future prediction time. Geographic transfer from India to Fiji is untested.
