# Public river flood-stage proof of concept

This is the **river-input benchmark**, which uses fields outside the demo screen.
For the model restricted to the demo's six weather/location fields, use
[the prototype weather pipeline](../prototype_weather/README.md). Its results
are saved separately and differ from the river-input results below.

This model now runs on **observed public US river data**. It predicts whether a
river gauge reaches its NOAA minor-flood threshold during the next UTC 24 hours.
The four locations are Marengo, Iowa City, Wapello (Iowa River) and Little Falls,
New Jersey (Passaic River). These scores are not Fiji validation results.

From `backend`, with the project's existing `.venv` and requirements installed:

```bash
# Download/cache real 2020–2025 gauge observations and prepare both target classes.
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ai.river.data

# Train and evaluate using separate chronological periods.
PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 .venv/bin/python -m ai.river.train

# Run the saved model on the latest complete historical date in the dataset.
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ai.river.predict

# Or inspect a particular historical day.
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ai.river.predict --date 2025-07-20
```

The prediction command is a **historical demonstration**, not a current warning.
It uses only the feature columns, with observed outcomes returned separately for
comparison. Loading joblib is restricted to trusted locally produced files.
`areas_without_complete_data` identifies locations excluded on the requested
date, so a missing prediction is not mistaken for a below-stage forecast.

## Observations and labels

[USGS Instantaneous Values](https://waterservices.usgs.gov/docs/iv-service/)
provides approved gauge-height observations in feet. `sites.csv` supplies the
matching NOAA station identifiers and documented thresholds:

- [Iowa River flood-stage changes](https://www.weather.gov/dvn/FloodStagesChangedAlongIowaRiver): 15 ft at Marengo, 23.5 ft at Iowa City, 21 ft at Wapello.
- [NOAA historical summary for Little Falls](https://www.weather.gov/media/marfc/FloodClimo/PSC/LittleFallsNJ.pdf): 7 ft.

The downloader also checks gauge identifiers, units and thresholds against
NOAA's current public gauge metadata and stores the response. The historical
sources support the fixed thresholds for this 2020–2025 proof of concept.

For every UTC day, all **96 quarter-hour slots** must have approved,
non-estimated measurements. The maximum of those readings determines the label:
1 at or above minor flood stage; 0 below it throughout the sampled window.
Missing slots, provisional measurements and estimates exclude the day. No
negative label is inferred from missing reports. This is observed river-stage
classification, not confirmation that every street in a town stayed dry;
short peaks between samples can be missed.

Features use stage margins relative to each gauge's threshold, previous changes,
weekly summaries, season and area identity. The latest input is from 23:45 UTC
on D−2, **24 hours 15 minutes before issue**. All rolling calculations use a full
calendar before excluding incomplete rows. No measurement in the forecast window
is a model input. Approved historical data can include later revisions; this
backtest does not reconstruct real-time publication history.

## Evaluation

Training uses 2020–2021, validation 2022–2023, and final testing 2024–2025, with
30-day gaps before validation and test. Related positive days are grouped within
each river system, and episodes crossing boundaries are rejected. The Iowa-only
candidate dataset lacked positives in validation; Little Falls adds documented
validation floods while preserving the chosen final test years.

Logistic regression, random forest and histogram gradient boosting compete on
validation average precision, then ROC-AUC and Brier score. Validation F2 chooses
the threshold. The selected model is not refitted on validation or test rows.
Final metrics are compared with persistence of the last known stage status and
an always-below-stage baseline, and broken down by area. There is also a separate
score for days where the latest input was below stage, distinguishing more
difficult transitions from continuing floods.

The current dataset has **7,187 rows: 100 flood-stage and 7,087 below-stage**.
After temporal gaps, training has 15 flood-stage days from two grouped episodes;
validation has six from two episodes. That is a small event sample, even though
the row count is larger. Test has 69 flood-stage days from six grouped episodes.

The saved random forest detected 63/69 test flood-stage days, missed six, and
flagged 115 below-stage days. Its recall is higher than persistence, while its
precision and F1 are lower. High overall accuracy alone is uninformative because
most days are below flood stage. Probabilities are uncalibrated and the selected
0.05 threshold reflects the recall-oriented validation objective, not an
official warning trigger. These results do not demonstrate transfer to Fiji.

## Output files

- `ai/data/river/dataset.csv`: prepared observations, labels, past-only features.
- `ai/data/river/manifest.json`: coverage, source URLs, hashes and limitations.
- `ai/data/river/raw/`: compressed original USGS responses and NOAA metadata.
- `ai/models/river/river_flood_model.joblib`: selected model plus metadata.
- `ai/models/river/test_predictions.csv`: all final-test predictions and outcomes.
- `ai/artifacts/river/training_report.json`: reviewable evaluation report.
- `ai/artifacts/river/test_comparison.csv`: model and baseline comparisons.

Generated raw data and model binaries are ignored by Git. The existing Fiji
area pipeline still requires verified local outcomes; this POC does not bypass
those checks or publish alerts. Applying it to Fiji would require local river
observations, matching flood thresholds and a separate evaluation.

The USGS legacy service has a planned migration. Its
[official migration guide](https://api.waterdata.usgs.gov/docs/ogcapi/migration/)
describes replacement APIs. Existing cached responses allow this dataset to be
rebuilt offline. New downloads will need an endpoint update when the legacy
service retires.

Tests:

```bash
PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 .venv/bin/python -m pytest \
  ai/tests/test_river_pipeline.py -q -p no:cacheprovider
```

Synthetic test fixtures verify coverage, timing, missing-data handling, label
consistency, split isolation and saved predictions. Only the downloaded USGS
observations produced the performance report described above.
