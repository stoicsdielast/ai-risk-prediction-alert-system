# Demo weather model: next-24-hour proof of concept

This is the pipeline for the demo screen's **six numeric inputs**. Training and
prediction work, but the current model produces many false alarms. It is a US
historical proof of concept, not a validated Fiji warning model or a live API.

## Inputs and target

| Demo field | Meaning at prediction issue time |
| --- | --- |
| `latitude` | Location latitude in degrees |
| `longitude` | Location longitude in degrees |
| `rainfall24hMm` | Liquid rain in the preceding 24 hours, mm |
| `temperatureC` | Current air temperature at 2 m, degrees C |
| `humidityPercent` | Current relative humidity at 2 m, percent |
| `windKph` | Current wind speed at 10 m, km/h |

These match `frontend/src/types/prototype.ts`. No river level, soil, season,
area identifier, label, risk level, prediction or warning is a model input.
The predictor accepts the flat `WeatherLocation` shape or `MapLocation` with
weather inside `conditions`. Missing or invalid measurements cause an error.

Each example is one gauge location at 00:00 UTC on date D. Rain is accumulated
over the preceding 24 hours, with instantaneous temperature/humidity/wind at
00:00. The binary target covers D 00:00 through D 23:45 at 15-minute intervals:
did any observed stage reach the official minor-flood threshold? This is a
next-24-hour gauge-stage task, not long-term susceptibility or town-wide flood
inundation. Below-stage labels do not establish that every nearby street was dry.

## Public dataset

Weather comes from [Open-Meteo's ERA5 historical weather API](https://open-meteo.com/en/docs/historical-weather-api).
Coordinates and thresholds come from NOAA gauges. Labels use
[USGS approved gauge-height observations](https://waterservices.usgs.gov/docs/iv-service/)
and documented minor-flood stages: the
[Iowa River thresholds](https://www.weather.gov/dvn/FloodStagesChangedAlongIowaRiver)
and [Little Falls historical summary](https://www.weather.gov/media/marfc/FloodClimo/PSC/LittleFallsNJ.pdf).
This joins real public records; no synthetic examples enter the measured results.

Every target day must have all 96 approved, non-estimated quarter-hour readings.
Missing observations are excluded, never labelled as non-flood. The cohort is
the same as the earlier river benchmark, including its stricter history-based
exclusions, so it does not use every complete target day in the raw archives.

| Location | River | Usable days | Flood-stage days |
| --- | --- | ---: | ---: |
| Marengo, Iowa | Iowa River | 1,237 | 45 |
| Iowa City, Iowa | Iowa River | 1,957 | 0 |
| Wapello, Iowa | Iowa River | 1,873 | 25 |
| Little Falls, New Jersey | Passaic River | 2,120 | 30 |
| Total | Two river systems | 7,187 | 100 |

Records cover 2020–2025; 7,087 examples are below stage. All retained labels
have complete matching weather. Source URLs, download timestamps, hashes,
requested coordinates and weather grid coordinates are in
`ai/artifacts/prototype_weather/data_manifest.json` and the river manifest.

ERA5 is reconstructed historical weather released after its valid time. These
results are therefore a **retrospective evaluation**, not evidence that a live
forecast could have achieved the same scores. Archived gauge data can also be
revised. Fiji has not been evaluated, nor has an unseen river system.

## Training and results

Dates are split chronologically with 30-day gaps; flood episodes cannot cross
partitions. The 227 gap rows are excluded from fitting and scoring.

| Partition | Period | Rows | Flood-stage days | Grouped flood episodes |
| --- | --- | ---: | ---: | ---: |
| Train | 2020–2021 | 2,138 | 15 | 2 |
| Validation | 2022–2023 | 2,396 | 6 | 2 |
| Test | 2024–2025 | 2,426 | 69 | 6 |

Three scikit-learn models are compared using validation average precision
(AP), then ROC-AUC, then lower Brier score:

| Model | Setup | Validation AP | Validation ROC-AUC |
| --- | --- | ---: | ---: |
| Logistic regression | Balanced class weights, C=1, max 2,000 iterations | 0.00269 | 0.479 |
| Random forest | 300 trees, depth 10, minimum leaf 5, balanced subsamples | 0.00244 | 0.440 |
| Histogram gradient boosting | 200 iterations, 15 leaves, learning rate 0.05, L2=1 | 0.00313 | 0.556 |

Each pipeline scales only the six numeric features, fitting preprocessing only
on training rows. No oversampling or artificial flood labels are used. Seed 42
and one computation thread make repeated runs deterministic in this environment.

Gradient boosting wins validation AP, although validation AP is weak (baseline
prevalence is 0.00250). Its decision threshold is chosen by validation F2, which
emphasizes recall. All observed validation score cutoffs are searched, with ties
resolved toward the higher threshold. The fitted model is not refitted on
validation or test data. Its present threshold is approximately 0.000267; scores
are uncalibrated and should not be presented as validated flood probabilities.

| Selected-model test measure | Result |
| --- | ---: |
| Accuracy | 59.52% |
| Flood-stage recall | 85.51% (59 of 69 detected) |
| Flood-stage precision | 5.72% (59 of 1,031 positive predictions) |
| F1 | 0.1073 |
| ROC-AUC | 0.7664 |
| Average precision | 0.0986 |
| False positives / false negatives | 972 / 10 |
| True negatives / true positives | 1,385 / 59 |

Always predicting below stage obtains 97.16% accuracy but detects zero flood
days. Thus accuracy alone is misleading. AP improves over test prevalence
(0.0284), but false alarms remain excessive. A separate gauge-persistence
reference performs better; it uses river measurements absent from the demo and
is never fed into this model.

Only two independent flood episodes appear in each of training and validation.
That makes selection and threshold estimation unstable. Local weather also
omits upstream rain and river storage. More verified events and a fresh future
evaluation are needed before making stronger performance claims. Test years
were previously inspected for the river benchmark; the initial weather run also
exposed a coarse-threshold bug corrected using validation scores. This is
development evidence, not a fresh independent final study.

## Run it

From the repository root, enter `backend`. The existing virtual environment
already contains the required packages:

```bash
cd backend

# Retrain from the dataset already downloaded on this machine.
PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 .venv/bin/python -m ai.prototype_weather.train

# Run on the latest complete historical date (missing areas are listed).
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ai.prototype_weather.predict

# Or use a JSON object with the demo's six fields.
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ai.prototype_weather.predict \
  --input ai/artifacts/prototype_weather/example_location.json
```

For a new checkout, install `backend/requirements.txt` into a Python environment,
then download/prepare the data before training:

```bash
# From backend, after creating/installing the project's .venv:
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ai.river.data
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ai.prototype_weather.data
PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 .venv/bin/python -m ai.prototype_weather.train
```

The first two commands download public data when the request-specific caches
are absent, and reuse existing caches otherwise. River preparation supplies
verified labels; the river model itself does not need training. Downloading
years of 15-minute readings is the slowest step. Local raw data and model
binaries are ignored by Git.

Optional arguments: training accepts `--dataset`, `--output`, `--report-dir`,
`--validation-start`, `--test-start` and `--gap-days`. Prediction accepts `--model`
and either `--input` or a historical `--date YYYY-MM-DD`. Changed splits must
retain both observed classes in every partition and separate flood episodes.

Generated files:

- `ai/data/prototype_weather/dataset.csv`: six features, labels and audit metadata.
- `ai/models/prototype_weather/prototype_weather_model.joblib`: pipeline and metadata.
- `ai/models/prototype_weather/test_predictions.csv`: each test prediction and outcome.
- `ai/artifacts/prototype_weather/training_report.json`: full results and limitations.
- `ai/artifacts/prototype_weather/test_comparison.csv`: selected model and references.
- `ai/artifacts/prototype_weather/historical_example.json`: saved inference example.

Load only locally trained, trusted joblib files. The model has no backend route
and does not publish alerts. The UI still uses prototype weather fixtures; a
live feed and separate local validation remain future integration work.

Tests:

```bash
PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 .venv/bin/python -m pytest \
  ai/tests/test_prototype_weather_*.py -q -p no:cacheprovider
```

Tests cover the frontend field contract, valid units and ranges, past-only
rainfall windows, observation quality, chronological separation, threshold
selection, saved inference, and exclusion of labels from model inputs. Test
fixtures are synthetic and are not used for the reported performance.
