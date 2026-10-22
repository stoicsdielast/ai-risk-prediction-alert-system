# Synthetic Fiji weather and flood simulation — methodology and evaluation

**Synthetic Data — Research Demonstration.** Every observation, flood event and
metric described in this document is produced by a local simulator. None of it
is an official Fiji MET reading, a validated flood forecast, or evidence of
real-world forecasting skill. The dataset exists only so classification
predictions can be compared with known simulation outcomes in an academic proof
of concept.

Related documents:

- `docs/SYNTHETIC_LOCATION_AUDIT.json` — authoritative location audit
- `docs/SYNTHETIC_MIGRATION_BACKUP.md` — pre-migration backup inventory
- `ml/data/synthetic_fiji/v1/dataset_metadata.json` — dataset contract
- `ml/data/synthetic_fiji/v1/data_quality_report.md` — quality checks
- `ml/runs/synthetic-v1/evaluation_report.md` — measured run report
- `ml/runs/synthetic-v1/protocol.json` — split/selection protocol

## 1. Locations (authentic metadata vs simulated characteristics)

The 12 monitored locations are the existing application registry read from the
PostgreSQL `locations` table on 2026-10-19 (`docs/SYNTHETIC_LOCATION_AUDIT.json`).
`location_id`, `slug`, `name`, `division`, `latitude` and `longitude` are
authentic application metadata and are identical in the database seed
(`backend/app/db/seed_locations.py`), the flood map and
`ml/synthetic/locations.csv`. No location was invented.

Hydrological characteristics (`elevation_m`, `catchment_area_km2`, `slope_pct`,
`drainage_capacity_mm_h`, `river_proximity_km`, `coastal_influence`) are fixed
simulated assumptions drawn once from a dedicated RNG seed, independent of the
weather seed and of flood outcomes, so they cannot encode labels.

## 2. Simulator (`ml/synthetic/generate.py`)

- Hourly (`1h`/`2h`/`3h`/`6h` configurable) observations for all 12 locations,
  2021-01-01 through 2025-12-31 by default, seed-configurable, deterministic
  (verified by `test_simulator_reproducible_and_covers_existing_registry`).
- Weather field: an AR(1) spatially correlated cloud process (Cholesky spatial
  covariance from great-circle-like distances) drives thresholded gamma
  rainfall. Discrete storm systems propagate over nearby locations with
  Gaussian footprints, sinusoidal intensity profiles and an extreme
  (cyclone-like) mixture; wet-season (Nov–Apr) frequency and amplitude exceed
  dry season.
- Hydrology: rainfall → soil-moisture bucket → upstream routing delay →
  fast/slow runoff convolution → discharge vs a bankfull capacity reduced by
  simulated blockage and tidal backwater → channel storage vs a hidden flood
  depth capacity. Pluvial excess appears when rainfall intensity exceeds
  drainage capacity, which itself degrades when soil is saturated. Flooding
  starts when storage exceeds capacity and ends when it falls below 45%.
- Observations add realistic sensor noise, multiplicative discharge noise, and
  0.6% independent missing values per channel. Units are documented in
  `dataset_metadata.json`.
- Hidden states (storage, capacity, blockage, vulnerability) drive event
  generation and are never exported as features.

## 3. Ground-truth generation (`label_events`)

- `flood_events.csv`: one record per simulated inundation episode
  (`event_id`, `location_id`, `event_start`, `event_end`, `severity`,
  duration, peak hydrological conditions, originating `scenario_id`).
- `flood_occurred` = 1 while an episode is active at the observation timestamp.
- `flood_within_24h` = 1 iff a **new** episode starts strictly after time t and
  within t+24h at a location that is not currently flooded. Observations during
  an active flood are marked `forecast_eligible = False` so the prediction
  target is unambiguous. The last 24 h of the series are null (unknown future).
  Optional 48 h and 72 h horizons are also produced.
- Labels come from the hidden hydrological simulation; no individual positive
  label is assigned or forced. Distribution is tuned only through
  simulator-level parameters (storm scale, drainage scale).

v1 distribution (seed 314): 525,888 observations, 278 flood events,
13,905 currently-flooded observations, 511,696 eligible rows with 6,672
positives (1.304% prevalence). Events occur at every location (12–41 per
location) and in both seasons, with wet-season totals 2–10× dry season.

## 4. Features (`ml/synthetic/features.py`)

Leakage-safe, causal features only: per-channel missing indicators; a
forward-only 6 h sensor recovery (never back-filled); rainfall and upstream
rainfall rolling totals over 3/6/24/72/168 h; river level, discharge and soil
moisture 3/6/24 h differences and 24 h means; declared geography; month/hour
cyclic encodings. Rows lack 168 h of history until `history_ready`. Asserted
exclusions: no label, event, scenario, hidden-state, future or target columns.
`test_features_do_not_change_when_only_future_weather_changes` proves features
at time t are invariant to any observation after t.

## 5. Protocol (`ml/synthetic/train.py`)

- Chronological partitions with 24 h embargoes on both sides of every boundary:
  train 2021–2022, calibration 2023 H1, selection 2023 H2, threshold 2024 H1,
  test 2024 H2–2025.
- Spatial holdout: locations 3 (Navua), 10 (Savusavu), 12 (Vunisea) are never
  seen in training (their pre-test history is excluded too).
- Storm holdout: storms deterministically reserved by `sha256(scenario_id)%5`
  (plus 24 h pre/168 h post windows) are excluded from training; their test
  windows form `storm_holdout` and `held_location_storm` evaluations.
- Model choice: highest selection-period recall under the predeclared
  false-alert budget (75 FP per 42 TP), then AP, F1, Brier — locked in
  `selection_lock.json` **before** any threshold or test scoring. Thresholds
  come from the 2024 H1 partition only. Sigmoid calibrators fit on 2023 H1
  only.
- Baselines: majority-class prevalence and a fixed rainfall>80 mm/24 h &
  soil>75% rule.

## 6. Measured results (all simulator-based)

Selected model: **CatBoost (raw)**, threshold 0.4447, version
`synthetic-fiji-v1-catboost__none`.

Chronological test (94,404 rows, 1,176 positives): accuracy 0.984,
balanced accuracy 0.644, precision 0.344, recall 0.296, F1 0.318,
PR-AUC 0.284, ROC-AUC 0.946, Brier 0.0119, TN/FP/FN/TP = 92,565/663/828/348.
Event-level recall 0.878 across 49 eligible events, median lead 9 h,
7.0 false alerts per 1,000 observations. Full comparison of all eight
candidates plus baselines: `ml/runs/synthetic-v1/evaluation_report.md`.

Transfer: held-location recall 0.379 (11 events, all detected); storm-holdout
recall 0.387 (14 events, 0.929 event recall). The joint unseen-location ×
unseen-storm subset contains zero flood events — no detection claim is made
there. Stress tests on independent seeds/settings show degraded but non-zero
skill (e.g. independent seed 8314: PR-AUC 0.220, event recall 0.868), which is
reported as evidence of regime sensitivity, not robustness.

Clustering (MiniBatchKMeans, k=5, on weather/hydrology variables) is
interpreted descriptively only; cluster flood incidence is never treated as a
validated risk category.

## 7. Serving integration (isolated demo only)

- Alembic migration `20261019_synthetic` creates `synthetic_datasets`,
  `synthetic_observations`, `synthetic_predictions`, `synthetic_alerts` —
  separate from operational prediction/alert tables.
- `python -m app.db.import_synthetic` verifies checksums and location identity
  before importing (idempotent, refuses mismatched registries).
- `GET /api/synthetic/info|frame`, `GET /api/synthetic/alerts`, and
  MET-admin-only `POST /api/synthetic/admin/alerts` +
  `/approve` implement replay and the pending→approved demonstration. Risk
  categories LOW/MODERATE/HIGH/VERY_HIGH are provisional bands relative to the
  validation threshold. Every response carries
  `source_type="synthetic"` and the research-demonstration notice.
- The React `/simulation` page shows the notice on every view and drives
  optional browser notifications only for locally approved synthetic alerts.
  `SYNTHETIC_DEMO_ENABLED` (default false) gates alert creation; live alert
  workflows and feeds are untouched.

## 8. Limitations

- Simulator physics is simplified; parameters are assumed, not calibrated to
  any gauge, catchment or historical Fiji event.
- Skill metrics measure learning of simulator rules only. Independent-seed
  stress tests degrade, confirming regime sensitivity.
- Held-location and storm subsets are small (11–49 events); confidence in
  transfer estimates is low, and correlated hours within storms inflate
  effective sample size.
- Static geography and vulnerability do not evolve; no infrastructure failure,
  landslide or dam-break modes are modeled.
- No cost-sensitive alert policy, societal impact or Fiji MET endorsement is
  implied.

## 9. Reproduction commands

Run from the repository root (uses `backend/.venv`):

```bash
# 1. Generate dataset (deterministic; refuses to overwrite)
backend/.venv/bin/python -m ml.synthetic.generate --out ml/data/synthetic_fiji/v1 --seed 314

# 2. Train, select and evaluate (writes ml/runs/synthetic-v1)
backend/.venv/bin/python -m ml.synthetic.train --dataset ml/data/synthetic_fiji/v1 --out ml/runs/synthetic-v1

# 3. Write measured evaluation report and publish serving bundle
backend/.venv/bin/python -m ml.synthetic.report --out ml/runs/synthetic-v1 --publish ml/artifacts/synthetic/v1

# 4. Stress-test on independent simulator seeds/settings
backend/.venv/bin/python -m ml.synthetic.stress --out ml/runs/synthetic-v1

# 5. Backend: migrate and import (from backend/, PostgreSQL required)
python -m alembic upgrade head
python -m app.db.import_synthetic --dataset ../ml/data/synthetic_fiji/v1

# 6. Run the demo backend with synthetic alerts enabled
SYNTHETIC_DEMO_ENABLED=true uvicorn app.main:app --reload

# 7. Frontend (must run on 127.0.0.1:5173 for CORS)
cd frontend && npm run dev -- --host 127.0.0.1 --port 5173 --strictPort

# 8. Tests
backend/.venv/bin/python -m pytest tests ai/tests -q   # from backend/
backend/.venv/bin/python -m pytest ml/tests -q         # from repo root
cd frontend && npm run lint && npm run test && npm run build
```

Generated data (`ml/data/`), run outputs (`ml/runs/`) and published model
bundles (`ml/artifacts/synthetic/`) are gitignored; regenerate them locally
with the commands above.
