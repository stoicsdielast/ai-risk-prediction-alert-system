# IS314 five-functionality audit evidence

Audit date: **21 October 2026, Pacific/Fiji**. Source revision: **e809391**.
Deliverable: [eight-page demo guide](IS314_Five_Functionalities_Demo_Guide.pdf).
Editable print source: [HTML](IS314_Five_Functionalities_Demo_Guide.html).

This was an audit/documentation task. No application source changes, real-database
writes, migrations, resets, retraining, alert creation/approval, commits or pushes
were performed. Existing application servers were used for public GET checks.
Database inspection used explicit PostgreSQL READ ONLY transactions, rolled back.
Tests used the repository's isolated fixtures. Frontend build output is generated,
gitignored output. An isolated headless browser profile had no user credentials.

## Implementation and readiness

| Functionality | Actual implementation | Verification | Readiness / gaps |
|---|---|---|---|
| Flood Risk Dashboard | Approved-user overview, MET dashboard, saved locations/history, prediction analytics and saved model-performance views | API/service and frontend tests; read-only analytics service against configured DB/artifacts; guest role redirect in browser | Core implemented; signed-in admin UI not exercised live. Personalized saved-location risk summary remains partial. Weather readings live in map detail/replay |
| Weather Data Management | Authorized ingestion, finite/range/time/period checks, identity-safe insertion, source-separated PostgreSQL storage, latest/history GETs, configurable polling worker | Weather API/feed tests and actual read-only PostgreSQL/API reads | Partial overall: genuine table empty, worker disabled, provider URL unconfigured; no weather-entry or manual-provider-fetch UI |
| AI Flood Risk Prediction | Deployed synthetic V1 CatBoost, historical replay, stored-weather causal feature builder, authenticated generation/persistence/provenance with optional isolated review | Valid serving-model checksum; actual read-only feature building + prediction; artifact-based metrics; generation/parity/rollback tests | Complete synthetic PoC path, partial overall SRS. No validated genuine Fiji model or automatic scheduled genuine prediction. V2/V3/foundation studies are research-only |
| Flood Mapping | API-backed 12-location Leaflet point map, division/search/risk filters, details, stored weather, approved alerts; protected create/update/deactivate location APIs | Live DB identity reads; headless browser 12→1 marker search; location/map/admin API tests | Core map implemented; administration API-only, no dedicated form. No PostGIS geometry, inundation polygons, flood-depth overlay or push-updated map |
| Alert System and Testing | Operational pending/approve/reject/suppress, expiry/cooldown, public approved feed; separate synthetic review; saved-location opt-in, durable outbox and open-tab delivery protocol | Alert/notification API and browser-mock tests; read-only public feeds and aggregate outbox records | Lifecycle implemented; new synthetic alerts blocked by current flag. No audit-time OS popup verification or closed-browser push/SMS/email |

## Requirements reviewed and source-of-truth boundaries

Reviewed `README.md`, `backend/README.md`, `AGENTS.md`, `docs/SRS_Group13.pdf`,
`docs/SAD_Group13-1.pdf`, `docs/FIVE_FUNCTIONALITY_AUDIT.md`,
`docs/WEATHER_DATA_MANAGEMENT.md`, `docs/V1_PREDICTION_WORKFLOW.md`,
`docs/ALERT_SYSTEM.md`, `docs/PROTOTYPE_UI.md`, `docs/SYNTHETIC_METHODOLOGY.md`,
and V2/V3 research protocols/results.

SRS/SAD describe planned external weather acquisition, PostGIS, personalized
risk information and timely notification requirements. They are not evidence
that those features are installed. Some older README/prototype sections and the
"No Alembic yet" AGENTS note lag current source. Alembic files are present;
no migration was executed in this audit. The supplied SRS/SAD are now available,
although older workflow documentation says they were absent at its writing.

The deprecated India experiment and historical Bangladesh benchmark were not
merged with the synthetic model. The user-deleted India CSV was not restored.
`GET /api/risk/suva` returns **410** (retired placeholder).
`/api/predictions/model-info` and `/flood-risk` are the historical Bangladesh
interface, not the deployed V1 model's display/generation contract.

## Frontend → API → service → storage/model → frontend traces

1. **Dashboard:** `/login` → `POST /api/auth/login` → JWT;
   `GET /api/auth/me` → server-verified role → `/dashboard` or
   `/admin/dashboard`. React consumes `/api/locations`, approved/admin alerts,
   and `/api/admin/analytics/predictions/overview|trend` or
   `/api/admin/analytics/models/performance`. Analytics read stored data/artifacts;
   no training or prediction generation occurs on these pages.
2. **Weather:** authorized `POST /api/admin/weather/observations` or configurable
   `app.services.weather_ingestion` → `WeatherCreate` → weather service →
   `weather_observations` or `demo_weather_observations` →
   `GET /api/weather/latest|observations` → `useLocationWeather` → selected map
   detail. Source/location/time identities are checked; missing values are not
   silently replaced with invented weather. Source and rainfall period matter.
3. **Stored-weather V1 generation:** approved-admin
   `POST /api/predictions/generate` → source/freshness/research checks →
   `v1_features.build_from_weather` (175 contiguous hourly readings + verified
   profile) → saved imputer/scaler/CatBoost → `synthetic_predictions` and
   `generated_prediction_provenance` → optional PENDING `synthetic_alerts` →
   response. The prediction transaction is tested, not executed by this audit.
   The `/simulation` replay is a separate read path using the full imported replay
   archive and published feature bundle, not the canonical 2,100-row weather snapshot.
4. **Mapping:** `useLocations` / `useMapLocations` → `GET /api/locations` →
   location service + latest `predictions` → React-Leaflet markers. Public alerts
   are fetched separately and matched by numeric location ID. The selected weather
   request also uses that ID. POST/PATCH admin location APIs manage registry rows;
   deactivation preserves referenced history. `/api/me/subscriptions` manages
   per-user saved locations, independently of location administration.
5. **Operational alerts:** saved operational prediction or manual admin draft →
   `alert_service` → `alerts` → approval stamps expiry and enqueues eligible
   `notification_outbox` rows in the transaction → `/api/alerts/active` and
   `/api/me/notifications` → client polling, claim, eligibility check, display and
   receipt → history. Source-specific synthetic review stays in
   `synthetic_alerts` and never enters this outbox.

## Source and test index

| Area | Key source files | Test evidence |
|---|---|---|
| Dashboard/analytics | `frontend/src/pages/{DashboardPage,AdminDashboardPage,AdminAnalyticsPage,AdminModelPerformancePage}.tsx`; `backend/app/services/analytics_service.py`; `api/routes/analytics.py` | `backend/tests/test_analytics.py`; corresponding frontend page tests and analytics calculations/panel tests |
| Weather | `backend/app/api/routes/weather.py`; `schemas/weather.py`; `models/weather.py`; `services/{weather_service,weather_ingestion}.py`; `frontend/src/locations/useLocationWeather.ts` | `backend/tests/{test_weather,test_weather_feed}.py`; `frontend/src/api/weather.test.ts`; map-detail tests |
| AI | `ml/synthetic/{generate,features,train,stress}.py`; `backend/app/services/{v1_features,v1_model,prediction_generation}.py`; `schemas/generated_prediction.py` | `backend/tests/test_v1_generation.py`; `ml/tests/test_synthetic_pipeline.py` and other research tests |
| Locations/map | `backend/app/api/routes/locations.py`; `services/location_service.py`; `models/location.py`; `frontend/src/pages/WeatherMapPage.tsx`; `components/map/{WeatherMap,LocationDetailCard}.tsx` | `backend/tests/{test_locations,test_admin_locations}.py`; frontend map, detail, page and location-hook tests |
| Alerts/notifications | `backend/app/services/{alert_service,synthetic_alert_service,notification_outbox}.py`; `api/routes/{alerts,notifications,synthetic}.py`; `frontend/src/alerts/{useBrowserAlerts,outboxDelivery,browserNotificationService}.ts` | `backend/tests/{test_alerts,test_alert_demo,test_notifications}.py`; frontend outbox/browser/control/saved-location tests |

## Fresh executed checks

| Command / working directory | Result |
|---|---|
| `.venv/bin/python -m pytest tests -q` — `backend/` | **271 passed, 9 skipped**, 43.78 seconds; one Starlette/httpx deprecation warning |
| `MPLCONFIGDIR=/tmp/is314-demo-mpl OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 backend/.venv/bin/python -m pytest ml/tests -q` — root | **46 passed, 1 skipped**, 20.94 seconds |
| `npm run lint` — `frontend/` | Passed, oxlint |
| `npm run test` — `frontend/` | **155 passed**, 22 test files, 7.06 seconds, jsdom |
| `npm run build` — `frontend/` | TypeScript and Vite production build passed |

Six backend skips need an explicit PostgreSQL migration test database; three need
absent Training-02 artifacts. The ML skip needs an absent historical audit output.
`backend/weather_tests` were not run: those opt-in tests create disposable schemas
and exercise migrations/concurrency, outside this no-database-modification audit.
`backend/ai/tests` is a deprecated experiment suite, not evidence for the served V1.
Frontend Notification tests use mocks; they do not establish real OS delivery.

## Actual configured-database snapshot (read-only)

- 12 active locations, matching the existing registry: Suva, Nausori, Navua,
  Nadi, Lautoka, Ba, Sigatoka, Rakiraki, Labasa, Savusavu, Levuka and Vunisea.
- Four divisions; extension list contains `plpgsql` only, not PostGIS.
- `weather_observations`: **0** genuine rows.
- `demo_weather_observations`: **2,100** synthetic rows (175 × 12), source
  `synthetic-fiji-v1-weather`; latest **2024-07-10T00:00:00Z**, stale.
- `synthetic_observations`: **525,888** full-replay rows.
- `predictions`: **9**, all explicitly sample records.
- `synthetic_predictions`: **1**; `generated_prediction_provenance`: **0**.
- `alerts`: **2** APPROVED rows; `synthetic_alerts`: **1** APPROVED row.
  Active counts are time-sensitive because operational alerts expire.
- `notification_outbox`: **2** DELIVERED receipts; these report browser display,
  not independent OS-popup observation or human acknowledgement.
- One approved MET-admin account exists; no identity or credentials are recorded here.
- Settings probe: synthetic demo creation **false**, browser delivery operator gate
  **true**, weather ingestion **false**, weather feed URL **not configured**.
  Operator configuration and browser permission are separate requirements.

## Live GET and public-browser evidence

- HTTP 200: `/api/health`, `/api/locations` (12), `/api/locations/divisions` (4),
  `/api/weather/latest?location_id=2&dataset=synthetic` (stale), the same request
  with `dataset=genuine` (`no_data`), `/api/synthetic/info` (ready, alerts disabled),
  `/api/synthetic/frame?timestamp=2024-07-30T01:00:00Z` (12 locations),
  `/api/synthetic/research/info`, `/api/alerts/active` and `/api/synthetic/alerts`.
- HTTP 401: unauthenticated `/api/admin/analytics/models/performance`.
- HTTP 410: `/api/risk/suva`.
- Real headless Chromium: `/weather-map` renders 12 markers; searching Nausori
  gives one location and one marker. `/simulation` displays the requested July 30
  timestamp, notice, 12 locations, Nausori **72.8%**, and disabled creation notice.
  `/alerts` loads; visiting `/admin/model-performance` without login redirects to
  `/login`. No account was logged in, created or modified for this check.
- Direct **read-only** inference from the canonical stored-weather snapshot:
  Nausori, **2024-07-10T00:00:00Z**, 56 features, probability
  **0.0025066690261676293**, provisional LOW. No prediction was persisted.
- Analytics service read the deployed V1 metadata and saved evaluation artifacts
  successfully under a read-only DB transaction. Signed-in admin UI was not exercised.

## AI metrics provenance and interpretation

`ml/artifacts/synthetic/v1/model_metadata.json` selects
`synthetic-fiji-v1-catboost__none`, 56 features, threshold
**0.44468999871002474**. Serving-model SHA256 matches metadata:
`bad1e95d5a09c6982c6872f43aab8cb06ba5ac6499a057e68a465ce79ea084b3`.
Numbers in the PDF come from `ml/runs/synthetic-v1/metrics.csv`, not new training.
Dataset counts come from `ml/data/synthetic_fiji/v1/dataset_metadata.json`.
V1 test has 94,404 records, 1,176 positives; selected CatBoost TP/FP/FN/TN is
348/663/828/92,565. Its raw-model PR-AUC is 0.283944 and Brier 0.011889.

The dataset target is a new simulated onset in the next 24 hours. Existing floods
and incomplete horizons are handled separately in training. Hidden states, event
IDs and future conditions are excluded from inputs. Calibration, selection and
threshold blocks are disjoint; temporal embargoes and location/storm holdouts apply.
V1 raw CatBoost was selected on validation. Sigmoid improves its test Brier but is
not the deployed variant; choosing it now from test results would be inappropriate.
V1 event recall (87.76%, 49 events) is not positive-hour recall (29.59%).
V2/V3 and bounded foundation-model studies are research-only; their scores cannot
be substituted for V1 deployment metrics. Future Fiji MET integration requires
licensed compatible observations, valid geography/datums and event labels,
independent spatial/temporal/prospective validation, calibration and approval.

## Presentation scripts and setup

Five approximately one-minute scripts are included on PDF pages 2–6.
The practical end-to-end checklist and exact startup commands are on page 7.
No migration, import, model training, fixture creation or permission grant is needed
or performed just to read this guide. New alert creation is conditional on a
separately prepared isolated instance; the current gate is off.

```bash
# Terminal 1, from repository root; existing prepared DB/env/artifacts required
cd backend
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2, from repository root
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Use your own approved account. Never copy passwords, JWTs, environment values or
private connection strings into slides or the PDF. Open-browser notifications
need consent, permission, saved locations and server/account gates. No permission
was requested or OS notification emitted during this audit.

## PDF verification

The HTML print source uses eight explicit A4 portrait pages, white backgrounds,
navy headings, an SVG architecture diagram and no screenshots. Each page was
rendered and visually inspected. Layout checks confirm content stays above the
footer with no horizontal overflow. PDF metadata/text checks confirm eight A4
pages, selectable text, no encryption, no PDF JavaScript and non-empty output.
