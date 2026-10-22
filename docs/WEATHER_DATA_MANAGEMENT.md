# Weather Data Management

Implemented 20 October 2026. Requirements: `TEAM_TASK_TICKETS.md` AR-01/AR-02 and
ingestion reliability from AR-04, plus the user's scheduled-ingestion requirements.
No separate formal SRS/SAD was located (available PDF/DOCX files are team tickets).
The five-functionality audit retains its historical snapshot at `f60a7d8` with a
verified implementation update. See [V1 prediction workflow](V1_PREDICTION_WORKFLOW.md)
for the new source-specific observation-to-model path.

## Storage and provenance

`weather_observations` holds genuine measurements, with `source_type=manual` or
`provider`. `demo_weather_observations` holds only `source_type=synthetic`, enforced
by database CHECK constraints. Neither table is the existing V1 simulator storage;
no model, alert, frontend or existing research pipeline is changed.

Every observation references an existing registry location. Writes require an active
location and an approved, active MET administrator. All 12 registered locations are
supported. The scheduler is an operator-controlled trusted process, with no public
trigger endpoint. Manual submissions store the administrator ID; scheduled submissions
have null `submitted_by` and a configuration-controlled source identifier.

`source` is a 1–100 character stable station/feed identifier (letters, digits,
underscore, dot, colon, hyphen). It is an attribution supplied by an authorized
operator, not a claim that the system has independently verified Fiji MET provenance.
Use synthetic for all fabricated demo measurements, including hand-entered fixtures.
Synthetic responses include the research-demonstration notice, including empty feeds.

### Units and validation

| Field | Unit / range | Missing policy |
|---|---|---|
| `observed_at` | Offset-aware ISO 8601; normalized to UTC; at most 5 minutes ahead | Required |
| `rainfall_mm` | mm, 0–5000 | Nullable; requires period |
| `rainfall_period_minutes` | preceding accumulation window, 1–10080 minutes | Present iff rainfall is present |
| `temperature_c` | °C, −90–60 | Nullable |
| `humidity_pct` | %, 0–100 | Nullable |
| `pressure_hpa` | hPa, 800–1100 | Nullable |
| `wind_speed_mps` | m/s, 0–150 | Nullable |
| `wind_direction_deg` | degrees clockwise from north, [0,360) | Nullable |
| `river_level_m` | metres relative to source gauge datum, −100–1000 | Nullable; do not compare different gauge datums |
| `river_discharge_m3s` | m³/s, 0–1,000,000 | Nullable |
| `soil_moisture_pct` | %, 0–100 | Nullable |
| `upstream_rainfall_mm` | mm, 0–5000 | Nullable; requires its own accumulation period |
| `upstream_rainfall_period_minutes` | minutes, 1–10080 | Present iff upstream rainfall is present |
| `coastal_tide_m` | metres relative to declared datum, −20–20 | Nullable |
| `gauge_datum` | Reference identifier, 1–100 characters | Nullable for storage; required for V1 compatibility |

These are broad input plausibility limits, not official MET warning thresholds.
At least one measurement is required. NaN/infinity, extra fields and alternate-unit
payloads are rejected. Null is retained; no zero substitution or imputation occurs.
Responses list missing fields and server receipt time separately from observation time.

Identity is `(location_id, source_type, source, observed_at)` within each table.
An exact retry returns the original record (200); changed measurements at that identity
return 409, never silent overwrite. Unique constraints and savepoints protect concurrent
requests. Data corrections need a future explicit revision/audit policy.

## API

| Method / path | Authorization | Behaviour |
|---|---|---|
| `POST /api/admin/weather/observations` | Approved MET admin bearer JWT | 201 created, 200 exact retry, 409 conflicting duplicate/inactive location |
| `GET /api/weather/latest?location_id=1` | Public | Latest by observation time; status `fresh`, `stale`, or `no_data` |
| `GET /api/weather/observations?location_id=1` | Public | Descending history with `observations`, `limit`, `offset`, provenance envelope |

Both reads accept `dataset=genuine` (default) or `dataset=synthetic` and optional
`source` filter. History accepts offset-aware `start`/`end` (inclusive), `limit`
1–1000 (default 100) and nonnegative `offset`. Equal timestamps break ties by ID.
Unknown location: 404. Known location without data: latest returns 200 with null
observation; history returns 200 with an empty list. Inactive locations remain readable
for historical analysis. Invalid fields/time windows: 422. Storage failures: safe 503.

Freshness is measured from `observed_at`, default 180 minutes, configurable via
`WEATHER_FRESHNESS_MINUTES`. Old submissions are allowed for historical imports and
remain stale; a recent receipt does not make old measurements current.

Example authorized demo input (use an existing location ID):

```json
{
  "location_id": 1,
  "observed_at": "2026-10-20T00:00:00Z",
  "source": "lecturer-demo",
  "source_type": "synthetic",
  "rainfall_mm": 12.5,
  "rainfall_period_minutes": 60,
  "temperature_c": 27.2,
  "humidity_pct": 82
}
```

Read with `/api/weather/latest?location_id=1&dataset=synthetic&source=lecturer-demo`.
The default genuine feed cannot return this measurement.

## Setup and scheduled ingestion

From `backend/`, on the existing initialized database:

```bash
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m app.services.weather_ingestion --once
# For continuous polling, run as a separate supervised service:
.venv/bin/python -m app.services.weather_ingestion
```

The worker exits without network access when `WEATHER_INGESTION_ENABLED=false`
(default). It is intentionally separate from uvicorn workers. Enable it and configure
`WEATHER_FEED_URL`, `WEATHER_FEED_SOURCE`, and optional secret `WEATHER_FEED_TOKEN`.
Use HTTPS for authenticated remote feeds. `WEATHER_FEED_SYNTHETIC=true` is the default;
set false only for a genuine observational feed, never a forecast or simulation.

The feed contract is a JSON array of at most 1000 objects using the POST field names
and units above. Source and source type are overridden by trusted configuration.
Unknown station IDs, invalid records and conflicting duplicates reject the complete
poll transaction. Previously committed data remains intact. Empty responses insert
nothing and freshness checks still run for all active registry locations.

Defaults: 900 seconds between completed polls, 20-second HTTP timeout, three attempts
with exponential backoff capped at 60 seconds. Errors log exception type/attempt, not
credentials or raw payload. Freshness warnings identify missing/stale location IDs for
the configured source. PostgreSQL advisory locking prevents overlapping polling
transactions. Retries are safe after a commit because identities are idempotent.
The worker uses configured database credentials; deploy under the same supervised
service environment as the backend, restart on failure, and monitor its logs.

**Provider status:** no previous provider integration was found. This is a canonical
JSON adapter, exercised against a local HTTP test fixture. No external weather API,
Fiji MET feed, or genuine automatic ingestion has been configured or verified.
A provider-specific mapping requires agreed access, licensing, station coverage,
measurement units and accumulation semantics before enabling it.

## AI consumption contract

Prediction code can call the read-only storage service within its own SQLAlchemy session:

```python
from app.services.weather_service import observations, present

rows = observations(db, location_id, synthetic=False, source="approved-gauge", limit=1)
if not rows:
    raise ValueError("No observation available")
reading = present(rows[0])
if reading.stale:
    raise ValueError("Observation is stale")
# Preserve reading.id, location_id, source, source_type, observed_at,
# rainfall_period_minutes and missing_fields alongside any future inference input.
```

For rolling rain totals use bounded history, matching source and non-overlapping
accumulation intervals; do not sum overlapping totals or treat missing intervals as zero.
Do not silently switch to synthetic when genuine data is missing.

Potential India-contract mapping (not an implemented or validated Fiji model adapter):

| Model key | Stored source |
|---|---|
| Latitude / Longitude | Existing registry coordinates |
| Rainfall (mm) | `rainfall_mm`, only once model-compatible accumulation semantics are agreed |
| Temperature (°C) / Humidity (%) | `temperature_c` / `humidity_pct` |
| River Discharge (m³/s) / Water Level (m) | `river_discharge_m3s` / `river_level_m`, with compatible gauge datum |
| Elevation (m), Population Density, Infrastructure, Land Cover, Soil Type | Not supplied by this weather workflow; approved location metadata still needed |

The mapping above concerns only the older India model. The deployed synthetic V1
instead uses 56 features, including pressure, wind and soil moisture. Its exact builder,
source-specific geography, saved-pipeline inference, persistence and isolated pending
alert workflow are now documented in [V1 prediction workflow](V1_PREDICTION_WORKFLOW.md).
Never include outcome labels or merge the three models' incompatible schemas.

## Verification and remaining work

```bash
# From backend; unit/API and existing regressions
.venv/bin/python -m pytest tests ai/tests -q -rs
# Real PostgreSQL, disposable random schemas on configured DATABASE_URL
WEATHER_POSTGRES_TEST=1 .venv/bin/python -m pytest weather_tests -q
# Configured application's real schema, approved admin, real auth, all 12 locations
.venv/bin/python -m app.db.weather_smoke
```

PostgreSQL tests execute migrations up/down/up, concurrent identical submissions,
source constraints and committed retrieval after disposing connections. The smoke
command inserts only unique-source synthetic readings, checks separate-session
persistence and genuine-feed exclusion, then deletes only its own test readings.

Remaining: formal SRS/SAD review when supplied; real-provider selection/mapping and
successful external ingestion; operational supervision of the worker; approved gauge
datum/static feature metadata and AR-03 feature-building contract. Frontend weather
integration belongs to the separate dashboard/map tasks. This implementation does not
claim automatic official observations or forecast validity.

### Verification results (20 October 2026)

- Backend + India AI: **348 passed, 9 skipped**. Six skips require the older
  `TEST_DATABASE_URL` location-migration suite; three require training-02 artifacts.
- Weather PostgreSQL suite: **2 passed**, no skips, against actual configured
  PostgreSQL in disposable schemas, including migration rollback/re-upgrade.
- Configured development schema migrated to `20261020_weather`; real-auth smoke
  returned POST 201 / GET 200 and separate-session persistence for **all 12 locations**.
  Synthetic smoke measurements were cleaned up after verification.
- ML: **46 passed, 1 skipped** (frozen selection-audit artifact absent).
- Frontend: **62 passed**, lint and production build passed.
- Non-failing warnings: existing Starlette/httpx deprecation and Alembic's missing
  `path_separator` setting. No external-provider ingestion was tested or claimed.
