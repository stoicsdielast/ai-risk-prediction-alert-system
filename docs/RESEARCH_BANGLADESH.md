# Bangladesh daily flood research proof of concept

This is historical research for the Fiji MET university project while Fiji data
is pending. It is not validated for Fiji and cannot issue operational public
warnings. Read the [measured technical report](../ml/artifacts/technical_report.md)
and [machine-readable evaluation](../ml/artifacts/evaluation.json) before presenting results.

## What was added

- `ml/config.py`, `download.py`, `data.py`: pinned download, Git blob/SHA256 and
  full Parquet verification, license/provenance report, label screening, audit,
  causal features, sampling, embargo and station holdout.
- `ml/train.py`, `report.py`, `requirements.txt`, `tests/`: four classifier
  comparisons, validation-only selection/thresholds, frozen evaluation,
  train-only KMeans, saved pipelines/metadata, plots, report and invariant tests.
- `backend/app/api/routes/predictions.py`, `schemas/research_prediction.py`,
  `services/research_inference.py`, `models/research_prediction.py`: historical
  API, validation, cached inference and separate SQLAlchemy persistence.
- Existing `main.py`, settings, model registration and `.env.example` register
  this functionality. The other auth/admin/location/alert routes remain available.
- `frontend/src/api/predictions*` and `components/research/`: a labelled, opt-in
  Bangladesh replay panel and its own geographic map in the community dashboard,
  admin dashboard and weather map. Existing Fiji location/weather/alert flows remain.

## Label and licensing limits

The source lacks a repository license. Public accessibility does not establish
reuse or redistribution rights. Dataset and individual source terms, including
GFMS, reanalysis and MERIT Hydro, remain unresolved. Raw records, derived
individual records, replay examples and model binaries stay local and are
ignored by Git. Do not publish them as cleared assets.

The requested **verified non-flood** definition cannot be independently
established from this source. We explicitly model source-qualified proxy labels
instead. `observed` 0 is no detection in a source-covered future day; it is not
physical-gauge proof of no flood. Unknown and positive-only labels are excluded,
never recoded as safe. The technical report states this limitation prominently.

## Reproduce from the repository root

The tested interpreter is Python 3.14.7. The existing backend virtual environment
was used for this run; a separate ML environment is also supported:

```bash
python -m venv ml/.venv
ml/.venv/bin/python -m pip install -r ml/requirements.txt
ml/.venv/bin/python -m ml.download
MPLCONFIGDIR=/tmp/is314-mpl OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
  ml/.venv/bin/python -m ml.train
ml/.venv/bin/python -m ml.report
ml/.venv/bin/python -m pytest ml/tests -q
```

Only the 44 MB classification Parquet and small audit sources are fetched from
commit `4d6ec74e22a63c1e33012d0f8d106e238dda4e1c`. Download fails clearly on
HTTP errors, Git hash mismatch, schema mismatch or unreadable Parquet. The
explicit alternative is the [monthly-resolution n-gauhar dataset](https://github.com/n-gauhar/Flood-prediction).
It needs a different monthly task/schema and cannot substitute for a 24-hour label.

For existing downloaded files, run `python -m ml.download --offline` to recheck
all blob hashes and Parquet decoding. Never manufacture data to bypass failure.

A completed output directory is protected from accidental training overwrite.
For a clean reproduction of the same predeclared experiment:

```bash
MPLCONFIGDIR=/tmp/is314-mpl OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
  ml/.venv/bin/python -m ml.train --out ml/runs/reproduction
ml/.venv/bin/python -m ml.report --out ml/runs/reproduction
```

`--smoke` uses shorter estimators, marks its metadata smoke-only and is rejected
by serving. It must use a separate output directory and must not be cited as
final model performance. Training CLI accepts only 20k–40k sample sizes; the
reported run used the default 30k. Tests use clearly synthetic fixtures solely
for software invariants. Hyperparameter changes require a new study/fresh test
period; reproducing an existing run is not permission to tune against its test.

## Artifacts

`ml/artifacts/` contains `classifier.joblib` (preprocessor and classifier in one
pipeline), `thresholds.json`, `feature_schema.json`, `model_metadata.json`,
`provenance.json`, `evaluation.json`, all per-station metrics, audit CSV/JSON,
`performance.png`, `clustering.joblib`, `clustering.json`, `clustering.png`,
cluster profiles/counts/assignments, the subset/selection manifest and replay
examples. `technical_report.md` is generated from the frozen metrics.

The binary threshold maximizes validation F1. Four presentation boundaries are
independently configurable in `thresholds.json`: LOW below .25, MODERATE from
.25, HIGH from .50, VERY_HIGH from .75. They are illustrative, unvalidated safety
thresholds. The selected weighted model is poorly calibrated, so its score must
not be presented as a calibrated real-world probability or confidence.

Inference caches trusted local artifacts once per process/directory. Restart
the API after changing artifacts or threshold configuration. Never load
uploaded/untrusted pickle/joblib files. The loader checks classifier SHA256,
feature/class compatibility, research status and scikit-learn version. It does
not download data or train during requests. A missing optional ML package
returns controlled model unavailability without disabling existing APIs.

## Run FastAPI with persistence

Use the existing backend environment and PostgreSQL/auth settings documented in
[backend setup](../backend/README.md). Install the same pinned ML dependencies
in that environment, since it loads the pipeline:

```bash
backend/.venv/bin/python -m pip install -r ml/requirements.txt
cd backend
.venv/bin/python -m app.db.init_db
.venv/bin/python -m uvicorn app.main:app --reload
```

`app.db.init_db` adds the `research_predictions` table through the existing
metadata/create-tables path. It references the authenticated user, but no Fiji
location or alert. No existing prediction table columns are migrated. A
database failure rolls back and returns 503; no successful unpersisted result
is reported. This work has not connected to or changed your running PostgreSQL.

Default model path is `<repository>/ml/artifacts` and works when launched from
`backend`. Override with `RESEARCH_MODEL_DIR=/absolute/trusted/artifact/directory`.
The API never writes its artifact directory; successful request records go to
PostgreSQL through the existing session dependency.

## API contract and exact replay command

`GET /api/predictions/model-info` and `GET /api/predictions/replay-examples` are
public read-only endpoints, like the existing map location reads. They return
`data_unavailable` if trained artifacts/examples are missing. `model-info`
exposes the exact feature allowlist, units, horizon and threshold qualification.
Replay-example responses omit ground-truth labels and expected output scores.

`POST /api/predictions/flood-risk` requires an approved authenticated user through
the existing `get_current_user` dependency. Send `mode: historical_replay`,
`country: Bangladesh`, a registered station ID, `feature_date`, timezone-aware
`as_of`, and all 30 numeric features. No unknown fields, labels or regimes are
accepted. Missing/null required measurements produce `data_unavailable` and a
feature list. Invalid types, non-finite values, physical ranges, station/date,
coordinate mismatch or premature timestamps return 422.

`as_of` must follow the feature day's UTC 23:59:59 convention and be less than
24 hours later. It cannot be future-dated. This is a retrospective daily index,
not a verified real-time publication schedule. Rainfall/discharge histories must
already exist; a six-value prototype-weather form cannot supply them.

After login, export your existing token locally, then run from the repository
root; the command prints the actual saved-model response, including persistence ID:

```bash
# Set RESEARCH_TOKEN locally to your approved account's access token.
backend/.venv/bin/python - <<'PY'
import json, os, urllib.request
examples = json.load(open('ml/artifacts/replay_examples.json'))
example = next(item for item in examples if item['id'] == 'normal')
payload = {key: example[key] for key in ('mode', 'country', 'feature_date', 'as_of', 'features')}
payload['station_id'] = example['station']['station_id']
request = urllib.request.Request(
    'http://127.0.0.1:8000/api/predictions/flood-risk',
    data=json.dumps(payload).encode(),
    headers={'Content-Type': 'application/json',
             'Authorization': 'Bearer ' + os.environ['RESEARCH_TOKEN']},
)
with urllib.request.urlopen(request) as response:
    print(json.dumps(json.load(response), indent=2))
PY
```

Choose `high_risk` instead of `normal` for the higher-scoring held-out example.
These internal IDs describe demonstrations, not verified operational risk.
Successful output has `status: ok`, `probability`, `presentation_tier`,
`prediction_horizon_hours: 24`, `model_version`, replay `timestamp`,
`generated_at`, `source`, `research_mode: true`, binary threshold/class,
station/country and an explicit research disclaimer.

Existing routes, including the legacy `/api/risk/{location}` placeholder, remain
available for compatibility. That legacy hardcoded endpoint is not connected to
this research model and must not be used as evidence of model output. It still
requires replacement before any operational deployment.

## Frontend demonstration

```bash
cd frontend
npm install
npm run dev
```

Open the existing dashboard or weather map and select **Open Bangladesh research
replay**. Public visitors can inspect the model/examples; approved users can run
the actual authenticated saved-model API. Select the lower/higher-scoring
historical example. The panel and its dedicated Bangladesh map show country,
station, source, date, model, score and research qualification. No foreign points
are overlaid on Fiji locations and no research score updates Fiji public alerts.

**Show internal demo alert** displays an internal message only after a click.
**Allow browser demo alerts** asks the browser for permission; it sends nothing.
After permission, clicking the internal demo button may additionally show a
notification beginning DEMO ONLY with Bangladesh/date/research context. Permission
denial or unsupported browsers leave the internal demo available. Panel consent
can be disabled. No email, SMS, push campaign or real public warning is sent.

## Tests and optional advanced model

```bash
MPLCONFIGDIR=/tmp/is314-mpl OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
  backend/.venv/bin/python -m pytest ml/tests -q
cd backend
.venv/bin/python -m pytest tests ai/tests -q
cd ../frontend
npm test
npm run build
npm run lint
```

API tests use isolated SQLite and approved-user fixtures; an additional test
checks real saved-artifact replay parity when local artifacts exist. No running
database or public-alert service is contacted. FastAPI TestClient's thread/event
loop startup stalled in this execution sandbox; the same suite runs successfully
outside that restriction. The existing Starlette/httpx deprecation warning is
unrelated to prediction behavior.

TabFM is optional and **not benchmarked**. The [official repository](https://github.com/google-research/tabfm)
documents separate backend requirements, bounded context (default 100 rows),
Apache-2.0 source and separately licensed non-commercial/non-production default
weights. A future benchmark should use its own compatible Python environment,
pin its commit and weight hash, restrict context/preprocessing to training rows,
select settings on validation only, cap CPU/GPU time and memory, and report a
timeout/unavailable result honestly. Do not alter the completed baseline to
depend on TabFM. TimesFM is a possible future discharge forecaster, not this
binary classifier.
