# Persisted weather → V1 research prediction → pending demo alert

## Scope and source restrictions

The deployed model remains **`synthetic-fiji-v1-catboost__none`**, horizon **24 hours**.
It predicts simulated new flood onset; its provisional bands are not Fiji MET levels.
V2/V3 are not promoted. No training, calibration, threshold tuning or artifact writes
occur in the new request path. The India 12-feature and Bangladesh interfaces are separate.

This completes the database-backed **research/demo inference workflow**, not validated
genuine Fiji forecasts. `source_type=manual|provider` and `research_mode=false` requests
return `DATA_UNAVAILABLE`: real gauge datums/geography and a validated compatible
operational model are still unavailable. No real observations are copied into synthetic
storage and no assumed geography is attached to genuine measurements.

The original SRS/SAD was not found; requirement traceability uses the available
`TEAM_TASK_TICKETS.md` AR-03 and AI-02/03, plus the explicit user requirements.

## Exact feature compatibility

The selected artifact contains **56 ordered features**. `v1_model.py` verifies model
and feature-schema SHA-256 values, source/version, selected CatBoost variant and absence
of a calibrator. It executes the saved **median SimpleImputer (with fitted missingness
indicators) → StandardScaler → CatBoost** pipeline without fitting anything.
The pipeline and all preprocessing statistics are inside `selected_model.joblib`.

`v1_features.py` implements the original `ml/synthetic/features.py` causal operations.
Tests compare all 56 values and final pipeline probabilities against saved V1 feature
rows for all 12 locations. No saved feature parquet, hidden state, future rain, event ID,
scenario, outcome label or replay probability is used to construct request features.

| Feature group | Origin and exact semantics |
|---|---|
| `rainfall_mm`, `temperature_c`, `humidity_pct`, `pressure_hpa`, `wind_speed_ms`, `wind_direction_deg`, `soil_moisture_pct`, `river_level_m`, `river_discharge_m3s`, `upstream_rainfall_mm`, `coastal_tide_m` | Eleven current sensor channels; weather `wind_speed_mps` maps to training `wind_speed_ms` without numerical conversion |
| Eleven `<channel>_missing` flags | Original null status **before** forward fill |
| Rainfall and upstream totals at 3/6/24/72/168h | Past-and-current rolling sums; minimum periods `max(1, window//2)`; only one-hour accumulation inputs accepted |
| River level/discharge/soil moisture change at 3/6/24h | Current forward-filled value minus value at that exact hourly lag |
| River level/discharge/soil moisture mean at 24h | Past-and-current rolling mean, minimum one non-null value |
| Latitude/longitude | Registry coordinates; source profile must match |
| Elevation, catchment area, slope, drainage capacity, river proximity, coastal influence | Six **declared simulator assumptions**, imported from checksum-verified V1 `locations.csv`; not measured Fiji geography |
| Month/hour sine/cosine | UTC month/hour, exactly the V1 formulas |

Missing sensor values receive at most **six hours of forward-only recovery**. Remaining
NaNs are passed to the saved training-fitted imputer. No backfill, newly fitted imputer
or zero substitution is allowed. An entirely absent sensor channel is rejected.

The service requires **175 contiguous hourly records**, ending exactly at the request
timestamp: a complete 168-hour window plus conservative recovery history. This is
stricter than V1 replay's minimum readiness at index 168 and avoids unknown carry-in
values near the start of a fetched window. Missing rows, missing static inputs, unknown
profiles, incompatible periods or gauge datum yield `DATA_UNAVAILABLE`, with no writes.

Both rainfall channels must be mm per **60-minute** interval; daily totals are not
divided by 24 and overlapping accumulations are not summed. River level and tide must
declare `gauge_datum="synthetic-fiji-v1-simulated-datum"`, meaning V1's simulated river
datum and simulated mean sea level respectively. Real gauge elevations are not equivalent.

## Persistence and provenance

- `demo_weather_observations`: complete raw sensor history, with new nullable upstream
  rain/period, tide and datum fields. The same optional fields are available in genuine
  weather storage, but genuine inference remains blocked.
- `v1_weather_profiles`: source/location-specific static attributes and verified dataset
  provenance. The bounded import command below registers profiles; requests cannot
  supply arbitrary feature vectors or invented geography.
- `synthetic_predictions`: probabilities/categories, keyed by source-specific dataset
  version, location, timestamp and model version. Uses the existing unique constraint.
- `generated_prediction_provenance`: observation IDs/window, ordered feature values,
  raw-history hash, source profile, model hash, replay mode, generation time and actor.
- `synthetic_alerts`: isolated pending-review records; no operational prediction/alert
  row is written and no notification hook is called.

Identical retries reuse predictions and alerts. Different input/model hashes at an
existing identity return **409**. Reviewed alerts are never revived by a retry.
Prediction and provenance insertion use a savepoint, with unique-conflict recovery.
The existing `create_alert_from_prediction` entrypoint dispatches `SyntheticPrediction`
objects to a separate, flush-only synthetic helper. Operational `Prediction` objects
retain their existing behaviour. The caller commits prediction/provenance/alert together.

When `SYNTHETIC_DEMO_ENABLED=true`, HIGH/VERY_HIGH create PENDING demo alerts for an
approved MET administrator; LOW/MODERATE create none. When false, inference still saves
the research prediction but creates no alert. Approval remains an explicit action via
the existing synthetic admin API. Nothing is auto-approved or auto-published.

## API

### `POST /api/predictions/generate`

Requires an approved, active MET-admin JWT, since generation can queue review.

```json
{
  "location_id": 2,
  "timestamp": "2024-07-30T01:00:00Z",
  "source": "synthetic-fiji-v1-weather",
  "source_type": "synthetic",
  "research_mode": true,
  "historical_replay": true
}
```

Successful 200 response includes `status="OK"`, `probability`, `risk_category`,
`horizon_hours=24`, location/timestamp, source/type, model version, generation time,
prediction ID, input hash, research notice, optional alert ID/status and replay mode.
Insufficient/incompatible data returns 200 with `status="DATA_UNAVAILABLE"`, a reason,
and null prediction/probability. Validation: 422; missing location: 404; inactive or
conflicting identity: 409; unavailable model or failed database transaction: safe 503.

`timestamp` requires an explicit timezone and exact UTC hour; future timestamps are
rejected. Queries never include observations later than that timestamp. Outside
explicit historical replay, stale timestamps (default >180 minutes) are rejected and
records received after the requested timestamp are excluded. Historical replay allows
later archive ingestion but **does not establish that those records were available to
a real-time forecaster at the historical date**. Source/mode are explicit and persisted.

`current_flood_state_assessed=false`: unlike the old dataset replay route, this weather
path does not consult simulation truth to suppress currently active floods. Scores
retain the trained new-onset interpretation and require independent current-event
assessment; they are not an ongoing-flood detector or validated emergency forecasts.
These predictions must not be used as additional held-out evaluation scores.

### Retired `GET /api/risk/{location}`

Returns **410 Gone**, explaining the replacement APIs. No application code caller was
found; the old hardcoded HIGH/0.82 result is no longer returned. Existing
`/api/locations`, Bangladesh, `/api/synthetic/*` and `/api/synthetic/research/*` remain.

## Setup and reproducible walkthrough

From `backend/`, with existing PostgreSQL and an approved MET administrator:

```bash
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m app.db.import_v1_weather --timestamp 2024-07-30T01:00:00Z
```

The import reads the original V1 dataset, verifies weather/geography checksums and
registry coordinates, and imports 175 hours × 12 locations into the new weather tables.
It does not read label files, alter existing replay data or manufacture new measurements.
Re-running is idempotent; mismatched source profiles/data refuse overwrite. The default
source is `synthetic-fiji-v1-weather`. Its source-specific synthetic dataset namespace
is deliberately different from the original `/api/synthetic` replay namespace.

Use the JSON request above with a real admin token. To enable pending **demo** alerts,
set `SYNTHETIC_DEMO_ENABLED=true` for the backend process; the default remains false.

Reproducible real configured-database smoke:

```bash
SYNTHETIC_DEMO_ENABLED=true .venv/bin/python -m app.db.prediction_smoke
```

This uses a unique temporary source, real auth and separate database sessions. It
cleans up only its own weather/profile/prediction/alert records. It verifies operational
prediction/alert counts and every V1 serving-artifact hash remain unchanged.

Verified example at **2024-07-30 01:00 UTC**:

| Location | Probability | Provisional category | Result |
|---|---:|---|---|
| Nausori (2) | 0.728087104 | VERY_HIGH | Isolated PENDING demo alert |
| Sigatoka (7) | 0.709634310 | VERY_HIGH | Isolated PENDING demo alert |
| Lautoka (5) | 0.285023291 | MODERATE | No alert |
| Suva (1) | 0.001391835 | LOW | No alert |

All 12 locations produced persisted predictions. This timestamp was selected to cover
the HIGH alert branch in testing, not to estimate accuracy or forecast performance.

## Verification and blockers

```bash
.venv/bin/python -m pytest tests ai/tests -q -rs
WEATHER_POSTGRES_TEST=1 .venv/bin/python -m pytest weather_tests -q -s
# From repository root:
backend/.venv/bin/python -m pytest ml/tests -q -rs
# From frontend:
npm run lint
npm run test
npm run build
```

Tests cover all-location feature/pipeline parity, bounded history, missingness recovery,
missing geography, datum/units, future-data exclusion, auth/source/freshness gates,
immutable duplicate identities, corrupted model handling, and atomic rollback.
Real PostgreSQL tests cover concurrent requests sharing a pending alert, separate-session
durability, reviewed-alert idempotency, and an actual database failure during alert insert.

Verified results for this implementation:

- Backend/India AI: **356 passed, 9 skipped** (six older location-migration tests require
  `TEST_DATABASE_URL`; three training-02 compatibility tests require missing artifacts).
- Actual PostgreSQL weather + generation suite: **4 passed**, no skips. Migrations
  upgrade/downgrade/re-upgrade in disposable schemas; the configured application schema
  was also upgraded to `20261021_generation` and exercised by the real-auth smoke.
- ML: **46 passed, 1 skipped** (missing frozen selection-audit artifact).
- Frontend: **62 passed**; lint and production build passed.
- Existing configured-database reads returned 200: V1 info/frame, V3 research info,
  locations, public alerts and Bangladesh model-info. No browser end-to-end test was run.
- Non-failing warnings: existing Starlette/httpx and Alembic `path_separator` deprecations.

Still blocking genuine Fiji forecasts: validated real static geography and gauge/tide
reference data; compatible upstream/weather coverage and accumulation conventions;
verified real-provider ingestion; current-event assessment; and independent Fiji model
validation/approval. V1's assumed geography must never be substituted for those inputs.
Next integration task: Functionality 1 dashboard data integration, with explicit
research/demo labelling; mapping integration can then consume the same typed feeds.
