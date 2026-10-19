# Fiji area forecasts: next 24 hours

This development pipeline prepares weather predictors for the application's 12
Fiji locations and trains a classifier when sourced daily flood outcomes are
available. It does not replace the existing model or publish alerts.

The target is whether flooding occurs anywhere in the named town area during
00:00–24:00 Pacific/Fiji on `forecast_date`, with a prediction issued at the start
of that window. Locations in `areas.csv` match the application's seed locations.
They are town reference points, not surveyed catchment boundaries. A positive
observation does not mean the entire town or the reference coordinate flooded.
Define consistent area boundaries and observation coverage before evaluating a
model for operational use.

## Prepare public weather data

From `backend`, using the existing virtual environment and requirements:

```bash
.venv/bin/python -m ai.area.data --start 2024-01-01 --end 2025-12-31
```

Outputs under the ignored `ai/data/area/` directory:

- `features.csv`: one complete forecast record per area/day.
- `raw/`: cached API responses with request URLs and retrieval timestamps.
- `manifest.json`: provenance, raw-file hashes, grid coordinates and missing days.
- `labels_template.csv`: blank outcomes, ready to copy to `verified_labels.csv`.

Reruns reuse cached responses. Do not fill in `labels_template.csv` directly:
the downloader regenerates that template. A separate completed label file is
left untouched. Dates with missing hours or values are excluded, never filled
with zero rainfall. Downloads need internet access; training and tests run locally.

[Open-Meteo Previous Runs](https://open-meteo.com/en/docs/previous-runs-api)
provides archived NOAA GFS forecasts. We explicitly select `gfs_seamless` and
48-hour offsets (`previous_day2`). Even the last input hour's forecast reference
is at least 24 hours before issue time. This allows a conservative availability
margin; the API does not supply publication timestamps. These are older,
fixed-offset forecasts, not one reconstructed latest-available run. Single-run
archives would support a closer simulation of a live forecast later.

Rainfall uses the preceding-hour totals at 01:00 through the following midnight.
Temperature and humidity use instantaneous values at 00:00 through 23:00, per
the [weather variable definitions](https://open-meteo.com/en/docs).
Predictors include rainfall totals and peaks, temperature, humidity, elevation,
coordinates, season and area identity. Weather data attribution: Open-Meteo and
NOAA GFS, CC BY 4.0; the free API is for non-commercial use.

## Observed flood outcomes

`public_positive_labels.csv` contains seven manually extracted area/day
observations from Fiji MET's December 2024 and November 2025 climate summaries.
Each row identifies the source page, figure and locality. This is an incomplete
positive-only seed catalog, **not a training-ready dataset**. Event IDs are local
grouping identifiers, not official MET IDs. The November entries are grouped
conservatively to avoid splitting related weather episodes across evaluation sets.

Required label columns:

| Column | Meaning |
| --- | --- |
| `area_id` | Slug matching the forecast row |
| `forecast_date` | Local Fiji date in YYYY-MM-DD format |
| `observed_flood` | 1 observed flood; 0 documented non-flood; blank unknown |
| `label_source` | Traceable observation source, preferably URL and page |
| `event_id` | Same event identifier across affected places/days; required for 1 |
| `coverage_note` | Locality and observation coverage supporting the outcome |

A negative needs evidence that the defined area and day were monitored without
flooding. No news report, low rainfall, a cancelled warning, an unobserved satellite
pixel, or an app sample prediction does not establish a negative. A point gauge
below threshold alone does not exclude surface flooding elsewhere in a town.
The validator requires provenance fields but cannot verify the truth of a source;
researchers must review those records.

Public satellite event products may provide additional evidence, but the
[Global Flood Database](https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1)
covers selected events in 2000–2018, outside this forecast archive's chosen window.
Its event extents are not a complete daily flood/non-flood record. Fiji coverage
has not been established here. The seven MET observations also do not establish
coverage for unreported days. More independent events and documented negative
coverage are needed before a meaningful Fiji classifier can be trained.

## Train and evaluate when labels are ready

Choose boundaries before inspecting final-test performance, ensuring both classes
and enough independent events occur in each period. Example boundaries:

```bash
OMP_NUM_THREADS=1 .venv/bin/python -m ai.area.train \
  --features ai/data/area/features.csv \
  --labels ai/data/area/verified_labels.csv \
  --validation-start 2025-01-01 --test-start 2025-07-01 \
  --gap-days 7 --output ai/models/area
```

Passing the blank template or the supplied positive-only catalog intentionally
stops training. Unknown outcomes are excluded. Whole dates stay together, with
seven-day gaps by default; events crossing development/test boundaries are
rejected. Preprocessing fits on training rows only. Logistic regression, random
forest and histogram gradient boosting compete on validation average precision;
validation F2 selects a recall-oriented decision threshold. The selected model
is evaluated once on untouched later dates against a constant training-prevalence
baseline, with additional per-area scores. `--holdout-area nadi` reserves that
area entirely from training/selection and evaluates its future dates separately.

Outputs: `area_flood_model.joblib` (pipeline plus metadata),
`training_report.json` (hashes, versions, split support and metrics), and
`test_predictions.csv`. Probabilities are uncalibrated and artifacts remain
development-only. Loading joblib is for trusted local artifacts. The bundle has
its own schema and is not accepted by the legacy app predictor automatically.

The older India CSV model had ROC-AUC about 0.502. This is a different geography,
target and evaluation protocol: its scores cannot serve as a like-for-like
performance comparison. No improved Fiji performance is established yet.

## Verify the implementation

```bash
PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 .venv/bin/python -m pytest \
  ai/tests/test_area_pipeline.py -q -p no:cacheprovider
```

Synthetic unit fixtures exercise window alignment, incomplete data, provenance,
unknown labels, chronological/event/area separation, saved probabilities, and
invariance of model selection when only final-test labels change. Their scores
are software-test results, not evidence of real flood-prediction performance.
