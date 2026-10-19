# Five-Functionality Audit — Flood Risk Prediction and Community Alert System (IS314)

## Verified implementation update — 20 October 2026

The original audit below is retained as a **historical baseline at `f60a7d8`**.
Its missing-weather, dummy-endpoint and absent research-handoff findings are superseded
by this update; the remaining genuine-forecast limitations still apply.

| Functionality | Current verified status |
|---|---|
| 1 Dashboard | PARTIAL; frontend data integration still pending |
| 2 Weather management | Backend storage, authorized ingestion, latest/history, source separation and configurable worker implemented; actual PostgreSQL verified; external provider not configured |
| 3 AI prediction | COMPLETE for the bounded V1 research workflow: persisted weather → 56-feature builder → unchanged trained pipeline → persisted synthetic prediction → optional PENDING demo alert. Genuine operational Fiji forecasts remain BLOCKED |
| 4 Flood mapping | PARTIAL; previous integration gaps remain |
| 5 Alerts/testing | Existing operational lifecycle preserved; automatic isolated synthetic handoff now verified; operational model handoff, expiry/cooldown remain pending |

Evidence: `app/services/v1_features.py`, `v1_model.py`, `prediction_generation.py`,
`synthetic_alert_service.py`, `app/api/routes/predictions.py` and
`tests/test_v1_generation.py`, `weather_tests/test_generation_postgres.py` (all under
`backend/`). Real PostgreSQL tests verify all 12 locations, concurrency/idempotency,
durability and prediction/provenance rollback on alert failure. The real configured
database smoke verified PENDING alerts for Nausori/Sigatoka and no operational writes.

`GET /api/risk/{location}` now returns 410; no hardcoded probability remains.
`POST /api/predictions/generate` is MET-admin authenticated, explicitly research-only,
source-aware and returns DATA_UNAVAILABLE for insufficient/incompatible inputs.
No V2/V3 promotion occurred. Full contracts, feature provenance and genuine-forecast
blockers: [V1 prediction workflow](V1_PREDICTION_WORKFLOW.md) and
[Weather Data Management](WEATHER_DATA_MANAGEMENT.md).

## Historical audit follows

**Audited:** 19 October 2026, against commit `f60a7d8` on `parvish-dev`.
**Method:** Source-code and database inspection, live API integration checks via FastAPI
`TestClient` against the running schema, and full test-suite execution. Requirement IDs
come from `docs/TEAM_TASK_TICKETS.md`, used as proxy requirements. A separate formal
SRS/SAD was not located; formal SRS/SAD traceability remains unverified.
**Rule applied:** a feature is not COMPLETE because a mock or isolated unit test passes —
each verdict cites the code path or a live integration check.

---

## 1. Executive summary

The system has a **genuinely solid authentication, alert-lifecycle and research-ML
core**, but the **operational middle of the system does not exist yet**: there is no
weather-observation subsystem, no route that runs a saved model against real inputs and
writes an operational prediction, and therefore no production path from weather →
prediction → alert. The dashboard and map are honest hybrids — the 12-location registry,
risk markers and alert panels are live, while weather values, admin "AI output" cards
and per-location official warnings are still prototype fixtures.

| # | Functionality | Status | One-line reason |
|---|---|---|---|
| 1 | Flood Risk Dashboard | **PARTIAL** | Alerts and auth live; community risk/weather overview missing; admin metrics still prototype (incl. a fabricated "Next 6 hours" horizon) |
| 2 | Weather Data Management | **MISSING** | No weather model, table, route, service, provider adapter or scheduler exists; only the isolated synthetic-research tables |
| 3 | AI Flood Risk Prediction | **PARTIAL** | Research inference is real and well-tested (Bangladesh replay, synthetic V1/V3), but no operational Fiji prediction route; `create_alert_from_prediction` has no production caller; hardcoded `HIGH/0.82` endpoint still ships |
| 4 | Flood Mapping | **PARTIAL** | Map genuinely reads the backend registry (12 locations, coordinates verified) with good UX; weather/warning panels in the detail card are prototype fixtures; no stale/tile-failure states; no admin location CRUD |
| 5 | Alert System and Testing | **PARTIAL** | Lifecycle, permissions, audit fields, idempotency, approval-gated publication and the admin/public UIs are complete and well-tested; expiry/cooldown, prediction→alert auto-handoff, push subscriptions and saved-location subscriptions are absent |

**Critical chain gap (the single most important finding):** the integrated demo exit
checklist in `docs/TEAM_TASK_TICKETS.md:683-694` requires "real submitted/retrieved
observations → model input → saved-model inference → persisted result → HIGH
recommendation → MET approval → community notification". Today step one (observations)
and step three (operational inference) have no implementation, so the chain cannot be
demonstrated end-to-end except through the explicitly demo-gated fixtures.

---

## 2. Status of the five functionalities

### Functionality 1 — Flood Risk Dashboard: **PARTIAL**

Authentication, session restore and the alert feeds are live and tested. The community
`/dashboard` has **no risk or weather overview at all** (only alerts + account cards),
which fails `AT-01`'s core requirement. The admin `/admin/dashboard` mixes live alert
counts with `PROTOTYPE_LOCATIONS`/`PROTOTYPE_PREDICTIONS` cards, including the
fabricated `horizon: 'Next 6 hours'` and `confidencePercent` values that `AT-01` AC3
explicitly forbids in a live view.

### Functionality 2 — Weather Data Management: **MISSING**

Nothing exists: no `WeatherObservation` model, no `/api/weather/*` routes, no
`weather_service`, no Alembic revision, no provider adapter, no scheduler. Verified
live: `GET /api/weather/latest` and `POST /api/admin/weather/observations` both return
**404**. The only weather-like persistence is `synthetic_observations`, which is
research-only, imported by a manual CLI from simulator parquet, and structurally
excluded from the operational app.

### Functionality 3 — AI Flood Risk Prediction: **PARTIAL**

The AI contract (`AI-01`) is complete and honest: 12 features with units, missing-value
rules, risk bands labelled "not official Fiji MET warning levels", and explicit
near-chance/limitation documentation in `backend/ai/README.md`. Three inference layers
are real, checksum-verified and never retrain on request. But **no route loads the
12-feature model**, no operational `Prediction` row is ever written by inference (only
seeded samples and demo fixtures), and the hardcoded `GET /api/risk/{location}` →
`HIGH / 0.82` placeholder (`backend/app/main.py:56-64`) still ships on the public API.
Model layering is disciplined and verified: V1 deployed, V2 not promoted, V3
research-only, foundation models (TabICL/TabFM run, TabPFN skipped) research-only with
no serving path.

### Functionality 4 — Flood Mapping: **PARTIAL**

The map's markers, risk colours, search/filter and detail cards genuinely read
`GET /api/locations` from the database; all 12 coordinates were verified identical to
the registry (`ml/synthetic/locations.csv`) and to the seeded backend rows. Gaps: the
detail card's weather block and "Official public warning" text are prototype fixtures
(not alert-driven), 4 of the 12 locations (Navua, Rakiraki, Levuka, Vunisea) have no
prototype weather rows at all, there is no stale-data indicator or tile-failure
handling, and the `LO-02` admin create/update location API does not exist.

### Functionality 5 — Alert System and Testing: **PARTIAL**

The strongest area. Status machine (PENDING → APPROVED/REJECTED/SUPPRESSED,
APPROVED → SUPPRESSED), MET-admin-only transitions with row locks, idempotent retry via
`uq_alert_location_prediction`, flush-only transactional helper, audit columns with DB
check constraints, approval-before-notification ordering, public schema leak tests, and
the full admin/public frontend flows are all implemented and covered by ~74 backend and
~42 frontend alert test cases. Missing: expiry and cooldown (documented as P1),
any production caller of the prediction→alert handoff, browser push/service-worker
delivery, and per-user saved-location subscriptions (absent entirely). Browser
Notification API with opt-in permission, dedup and multi-tab locking **is** present and
tested.

---

## 3. Detailed requirements checklist

Status key: **C** = COMPLETE, **P** = PARTIAL, **M** = MISSING, **B** = BLOCKED.

### Functionality 1 — Dashboard (owner: Louvatu)

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| AT-01 | Community risk/weather overview on `/dashboard` | **M** | `frontend/src/pages/DashboardPage.tsx` renders only alerts (`:38-39`), account cards (`:45-61`) and a prototype-labelled map promo (`:63-101`); no risk/weather panel exists |
| AT-01 | Admin dashboard from backend data | **P** | Alerts live (`AdminDashboardPage.tsx:111-152`); locations/high-risk/divisions/predictions from `usePrototypeData()` (`:75`, `:122-151`, `:196-237`) |
| AT-01 | Remove fabricated horizon/confidence from live views | **M** | `frontend/src/data/prototypeData.ts:227-236` still emits `horizon: 'Next 6 hours'` + `confidencePercent`, rendered as "AI model output" (`AdminDashboardPage.tsx:196-237`) |
| AT-01 | Loading/empty/error/retry states | **P** | Complete for alert feeds (`AlertFeedStatus.tsx:14-41`); prototype panels have no states because they never load |
| AT-01 | Changing stored records changes displayed counts | **P** | True for alerts (live test `AlertsDashboardPage.test.tsx:215-235`); false for locations/risk/predictions |
| AT-02 | Typed shared API clients | **P** | `api/client.ts:59-93` + locations/alerts/predictions/auth clients exist; **no weather or risk-feed client** (endpoints absent) |
| AT-02 | Refresh/abort/stale-response handling | **P** | Alert feeds: 30 s polling, abort, stale-guard (`useAlertFeed.ts:10-49`); map: abort+retry only, no polling, no cross-view refresh bus (`useMapLocations.ts:43-76`) |
| AT-02 | No silent prototype fallback as live data | **P** | Error paths clean (`WeatherMapPage.tsx:171-180`); but prototype weather renders under "Latest observation / Current weather" headings (`LocationDetailCard.tsx:120-139`) |
| AT-05 | Frontend auth regression tests (guards, restored session, expiry, logout) | **P** | Role guard + 401 session-clear covered inside `AlertsDashboardPage.test.tsx:171-213`; **no `src/auth/` test file exists**; no restored-session or logout test |

### Functionality 2 — Weather Data Management (owner: Rishi)

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| AR-01 | Weather observation model + MET-admin write API + validation | **M** | No weather model in `backend/app/models/` (only alert/location/prediction/risk/synthetic/user); no weather route (`main.py:32-39` inventory); no weather schema; only migration is `migrations/versions/20261019_synthetic_demo.py` (synthetic tables). Live: `POST /api/admin/weather/observations` → 404 |
| AR-02 | Latest-weather read by location with freshness/staleness | **M** | No `/api/weather/latest` route (live 404). No `stale/fresh` logic anywhere in `backend/app`. Map weather is `prototypeData.ts:20-23` with fake `minutesAgo()` timestamps (`:6-8`) |
| AR-03 | Feature builder: observations + location → 12 model keys | **M** | No `weather_service.py`/feature service. The 12 keys exist only in `backend/ai/config.py:19-25` (India contract). Bangladesh inference takes features from the request body (`research_inference.py:57-93`); synthetic inference reads a published parquet (`synthetic_inference.py:29`) |
| AR-04 | Ingestion reliability, idempotency, provider adapter | **M** | No provider integration, no scheduler/cron/BackgroundTasks in `backend/app`. Only idempotency is the synthetic import CLI (`import_synthetic.py:24-33`), which refuses non-synthetic sources. `backend/README.md:728-731` lists weather ingestion as intentionally not provided |

*Note:* `backend/alembic/` does not exist; migrations live in `backend/migrations/` with
exactly one revision (synthetic demo tables). Any weather table must be added there.

### Functionality 3 — AI Flood Risk Prediction (owner: Parvish)

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| AI-01 | 12-feature contract, units, missing rules, bands, output schema, honest limitations | **C** | `backend/ai/config.py:19-38`; `predict.py:34-45,48-73,95-102`; `backend/ai/README.md:13-16,56-65,85-115,241-255` (near-chance ROC-AUC ≈ 0.502, no horizon defined, Fiji transfer untested) |
| AI-01 | No unsupported 6-hour forecast/confidence claims | **P** | Model code clean (horizons pinned to 24 h: `schemas/research_prediction.py:44`, `synthetic_inference.py:38`); residue: `prototypeData.ts:233` "Next 6 hours" (prototype-labelled, still shipped) |
| AI-02 | Saved-model inference in FastAPI, no retraining | **P** | Real for research models: Bangladesh (`predictions.py:48-84` → `research_inference.py:45-53`), synthetic V1 (`routes/synthetic.py`), V3 research (`routes/synthetic_research.py`). **Missing for the operational 12-feature model** — no route imports `ai.predict` |
| AI-02 | Prediction persistence with provenance | **P** | `ResearchPrediction` stores inputs+result JSON (`models/research_prediction.py:10-19`); the operational `predictions` table is only ever written by `seed_locations.py:150` and `alert_demo_service.py:41` (both `is_sample=True`). Verified live: 8/12 locations carry sample predictions flagged `is_sample` |
| AI-02 | HIGH/VERY_HIGH → PENDING via `create_alert_from_prediction` in same transaction | **P** | Helper correct and complete (`alert_service.py:141-180`, flush-only, savepoint, idempotent; tests `test_alerts.py:105-267`) but **no production inference caller** — only demo fixture (`alert_demo_service.py:47`) and admin retry (`alert_service.py:186`). Bangladesh route explicitly refuses (`predictions.py:71-72`) |
| AI-02 | Model readiness state | **C** | `GET /api/predictions/model-info` returns `data_unavailable` when artifacts missing (`predictions.py:26-33`); `/api/synthetic/info` + `/api/synthetic/research/info` report readiness |
| AI-03 | Inference regression tests, API ≡ direct parity | **P** | Strong for existing layers: pipeline reproduction (`ai/tests/test_pipeline.py:62-74`), API-vs-direct parity (`test_research_predictions.py:127-138`), rollback (`:110-116`). Nothing tests a 12-feature API or the V1 synthetic HTTP routes (former absent, latter untested) |
| — | Hardcoded `HIGH/0.82` placeholder removed | **M** | `backend/app/main.py:56-64` live on public API — confirmed: `GET /api/risk/suva` → `{'risk_level': 'HIGH', 'probability': 0.82}` |

**Model inventory (verified):**

| Model | Trained | Served | Versioned | Status |
|---|---|---|---|---|
| India 12-feature RF | Yes (`backend/ai/models/`) | **No** (CLI only) | Yes | Contract complete, not integrated |
| Bangladesh research | Yes (`ml/artifacts/`) | Yes — `POST /api/predictions/flood-risk` | sha256-verified | Research replay, API-tested; not operational Fiji inference |
| Synthetic V1 | Yes (`ml/artifacts/synthetic/v1/`) | Yes — `/api/synthetic/*` (demo-gated writes) | checksum-verified | **Deployed model — unchanged** |
| Synthetic V2 | Yes (`ml/runs/synthetic-v2/`) | No | run metadata | Not promoted (`SYNTHETIC_V2_RESULTS.md:13-15`) |
| Synthetic V3 | Yes (`ml/runs/synthetic-v3/`) | Read-only `/api/synthetic/research/*` | manifests | Research-only, `research_only: true` in code |
| TabICL / TabFM | Run outputs only | No | run JSONs | Research-only benchmark; TabPFN skipped (no licensed checkpoint) |

### Functionality 4 — Flood Mapping (owner: Atharv)

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| LO-01 | One ordered migration workflow | **P** | `backend/migrations/` with one revision; but `init_db.py:10` still uses `create_all` for operational tables — the ticket's "not solely `create_all`" is only half met |
| LO-02 | Location list/detail APIs | **C** | `GET /api/locations` (division/search filters) + `GET /api/locations/{slug}` + `/divisions` (`routes/locations.py:28-67`); 39 tests in `test_locations.py` |
| LO-02 | Admin create/update + deactivation API | **M** | No POST/PUT/PATCH location route exists anywhere; deactivation only via direct DB/seed |
| LO-02 | Repeatable demo provisioning | **C** | `python -m app.db.seed_locations`, slug-keyed, idempotent (`seed_locations.py:101-159`, tests `:158-179,323,332`) |
| LO-03 | Shared feed: locations + latest prediction, explicit no-data | **C** | `location_service.py` joins latest prediction; `null` prediction, never defaulted to LOW (`schemas/location.py:15-36`); live check: 12 locations, 8 with sample predictions correctly flagged |
| LO-03 | Feed joins observations + approved alerts; stale flag | **M** | No observation model to join; alerts remain a separate endpoint; no staleness field |
| LO-04 | Map reads backend feed for markers/risk/details | **C** | `useMapLocations.ts:47` → `GET /api/locations`; marker positions from DB coords (`WeatherMap.tsx:131-149`); coordinates verified identical to `ml/synthetic/locations.csv` for all 12 |
| LO-04 | Search/filter/selection/no-data UX | **C** | `WeatherMapPage.tsx:11-70,105-188`; "No prediction available" (`LocationDetailCard.tsx:34-44`); 9 page tests |
| LO-04 | Weather + official warning from live sources | **M** | Detail card weather block and warning text come from `prototypeData.ts` fixtures joined by slug (`useMapLocations.ts:66-73`, `LocationDetailCard.tsx:108-162`); 4 of 12 locations have no prototype rows (weather section hidden, warning falls back to demo copy) |
| LO-04 | Stale-data + tile-failure behaviour | **M** | No last-updated indicator; `TileLayer` has no error handling (`WeatherMap.tsx:126-129`) |

### Functionality 5 — Alert System and Testing (owner: Aryan)

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| RI-02 | `create_alert_from_prediction` transactional helper | **C** | `alert_service.py:141-180` — flush-only, savepoint, HIGH/VERY_HIGH only, sample-blocked; rollback tests `test_alerts.py:228-251` |
| RI-02 | Helper called from a production prediction flow | **M** | Callers: demo fixture, admin retry, tests only (see AI-02) |
| RI-02 | Retry idempotency / no revival | **C** | `uq_alert_location_prediction` (`models/alert.py:34`); reuse logic `alert_service.py:154-179`; tests `:204-225,254-267` |
| RI-02 | Approval-only publication, atomic rollback | **C** | Public filter `alert_service.py:308`; hook after commit `:264-269`; tests `:125,279,323-358,550-577` |
| RI-02 | Expiry policy | **M** | No `expires_at` column (`models/alert.py:64-91`); documented as manual suppression (`ALERT_SYSTEM.md:82`); ticket marks it P1 |
| RI-02 | Cooldown / escalation policy | **M** | No cooldown code anywhere in `backend/app` |
| RI-02 | Audit fields | **C** (columns) / **M** (log table) | Full reviewer/timestamp/reason columns with DB check constraints (`models/alert.py:48-60`); no separate audit-history table |
| RI-02 | No notification before approval commit | **C** | Hook ordering test `test_alerts.py:550-568`; separate-session visibility `:323-343` |
| AT-03 | Admin UI on real APIs (list/create/edit/approve/reject/suppress) | **C** | `api/alerts.ts:25-68`, `AlertsDashboardPage.tsx:64-342`; suppression reason required; 409 → refresh; session-expiry logout; 15 test cases |
| AT-04 | Public approved-alert panel + polling + dedup | **C** | `GET /api/alerts/active` (`routes/alerts.py:126-135`); 30 s poll (`useAlertFeed.ts:7,37`); id-dedup (`api/alerts.ts:39`); suppression removal tested (`CommunityAlertsPage.test.tsx:31-51`) |
| AT-04 | Severity by text, accessibility | **C** | `RiskPill` text labels; `aria-live`/`aria-label` (`AlertFeedStatus.tsx:21`, card/banner) |
| — | Browser notifications, opt-in/out | **C** | `browserNotificationService.ts` (click-gated permission `:33-47`, dedup via localStorage+`navigator.locks`, HIGH/VERY_HIGH filter); UI control `BrowserAlertControl.tsx`; 17 frontend test cases |
| — | Push subscriptions / service worker | **M** | No `PushManager`/service worker/web-push code in frontend or backend |
| — | Saved-location subscriptions | **M** | No `saved_location` model/route/subscription concept anywhere |

---

## 4. Outstanding bugs and missing integrations

**Integration gaps (block the integrated demo):**

1. **No weather → feature → prediction → alert chain.** Three separate missing links:
   observation storage (AR-01/02), feature building (AR-03), and an operational
   prediction route that persists a real `Prediction` and calls
   `create_alert_from_prediction` (AI-02). Until all three land, the alert lifecycle can
   only be demonstrated with fixtures or seeded samples.
2. **`GET /api/risk/{location}` dummy endpoint** (`backend/app/main.py:56-64`) returns
   fixed `HIGH/0.82` on the public, unauthenticated API. Confirmed live. Documented as a
   placeholder in five docs but never removed — a reviewer can mistake it for real
   output.
3. **Admin dashboard prototype metrics** including the fabricated "Next 6 hours"
   horizon and confidence values (`prototypeData.ts:227-236` →
   `AdminDashboardPage.tsx:196-237`) violate `AT-01` AC3 while being presented under an
   "AI model output" heading.
4. **Map detail-card weather and official warnings are fixtures** joined by slug
   (`useMapLocations.ts:66-73`); approving/suppressing an alert changes the workspace
   banner but **not** the per-location warning panel (fails `LO-04` AC4 at the
   marker level). 4 of 12 locations have no fixture weather at all.

**Correctness/quality issues:**

5. `docs/PROTOTYPE_UI.md:20-23,71` is now stale — it claims the map and dashboard
   metrics are entirely local demo data, but the map genuinely reads live
   `/api/locations` + live alerts. The live/demo boundary in the doc no longer matches
   the code.
6. `init_db.py` still uses `create_all` for operational tables alongside the single
   Alembic revision (`LO-01` AC4 half-met).
7. Leaflet `divIcon` interpolates `riskLevel` into an HTML string without escaping
   (`WeatherMap.tsx:41-53`) — enum-constrained today, but an unescaped HTML sink fed by
   API data.
8. No rate limiting on the unauthenticated public alert feed (acknowledged future
   hardening, tickets line 676).
9. `GET /api/health` (`main.py:49-53`) is unconditional and never reports missing
   database/model dependencies (`RI-05` AC4).
10. Frontend has no `src/auth/` tests: no restored-session, logout, or
    invalid-signature-token coverage at the frontend layer (`AT-05` AC1 incomplete).
11. No test exercises the synthetic V1 HTTP routes (`/api/synthetic/info|frame|alerts`)
    — only the V3 research routes are covered.

**Security observations (limited source review, not a security certification):**

- Token handling is sound: JWT in sessionStorage, role from `/api/auth/me`, 401/403 →
  logout; admin actions re-validated server-side per request.
- Public alert schema leak tests assert absence of reviewer IDs and suppression reasons
  (`test_alerts.py:348-535`).
- Workflow-bypass payloads rejected by `extra="forbid"` (`schemas/alert.py:19`).
- Findings include the dummy risk endpoint (item 2) and the unescaped divIcon sink
  (item 7); this is not an exhaustive security assessment.

---

## 5. Prioritized remaining tasks and team ownership

Ownership follows the current assignment: **Parvish** — AI/ML + coordination,
**Rishi** — backend/weather, **Louvatu** — dashboard/frontend, **Atharv** —
database/flood mapping, **Aryan** — alerts/QA. (Ticket-file owners differ in places;
reassignment is assumed deliberate.)

### P0 — required for the first complete integrated demo

| # | Task | Requirement | Owner | Files to change |
|---|---|---|---|---|
| P0-1 | Weather observation table + Alembic revision, MET-admin write API with range/unit/timestamp validation | AR-01 | Rishi | new `backend/app/models/weather.py`, `schemas/weather.py`, `api/routes/weather.py`, `services/weather_service.py`, `migrations/versions/*_weather_observations.py` |
| P0-2 | `GET /api/weather/latest?location_id=` with observation-time ordering and explicit stale/no-data states | AR-02 | Rishi | `api/routes/weather.py`, `services/weather_service.py` |
| P0-3 | Feature builder mapping stored observations + location attributes to the agreed model keys with provenance; missing/stale policy that refuses rather than fabricates | AR-03 | Rishi + Parvish | new `services/feature_service.py`; contract in `backend/ai/config.py` (read-only reference) |
| P0-4 | Operational prediction route: load saved model once, validate inputs, persist `Prediction` with input provenance, call `create_alert_from_prediction` in the same transaction | AI-02 | Parvish | new `services/prediction_service.py`, `api/routes/predictions.py` (new operational endpoint), `models/prediction.py` (provenance columns if needed) |
| P0-5 | Remove or hard-gate the dummy `GET /api/risk/{location}` endpoint | AI-02 | Parvish | `backend/app/main.py:56-64` |
| P0-6 | Admin dashboard: replace `PROTOTYPE_LOCATIONS`/`PROTOTYPE_PREDICTIONS` panels with the live locations/predictions feed; delete the "Next 6 hours" horizon card | AT-01 | Louvatu | `pages/AdminDashboardPage.tsx`, `data/prototypeData.ts:227-236`, new `api/` risk-feed client |
| P0-7 | Community dashboard: add the risk/weather overview panel required by AT-01 (live feed once P0-1/2 land) | AT-01 | Louvatu | `pages/DashboardPage.tsx`, shared data hook |
| P0-8 | Map detail card: drive weather + per-location warning from live sources (observations + approved alerts); until P0-1 lands, keep fixtures but label them inline, not under "Latest observation" | LO-04 | Atharv + Louvatu | `components/map/LocationDetailCard.tsx`, `locations/useMapLocations.ts` |

### P1 — required for the final system

| # | Task | Requirement | Owner | Files |
|---|---|---|---|---|
| P1-1 | Admin location create/update/deactivation API (MET-admin only, validated coordinates) | LO-02 | Atharv | `api/routes/locations.py`, `schemas/location.py`, `services/location_service.py`, tests |
| P1-2 | Full risk feed join: locations + observations + predictions + approved alerts with stale flag | LO-03 | Atharv + Rishi | new `api/routes/risks.py` or extend `locations.py` |
| P1-3 | Alert expiry (`expires_at` + public filter) and repeated-event cooldown policy | RI-02 | Aryan | `models/alert.py`, `migrations/`, `services/alert_service.py:298-311`, tests |
| P1-4 | Weather ingestion runbook + observation identity/idempotency for repeated imports | AR-04 | Rishi | `services/weather_service.py`, `backend/README.md`, `.env.example` |
| P1-5 | Frontend auth regression suite: restored session, logout, invalid token, role guards as dedicated tests | AT-05 | Aryan | new `frontend/src/auth/*.test.ts(x)` |
| P1-6 | PostgreSQL disposable integration suite (migrations, constraints, concurrent alert retry) | RI-03 | Aryan | `backend/tests/conftest.py` + new integration tests |
| P1-7 | Map stale-data indicator + tile-failure handling | LO-04 | Atharv | `WeatherMapPage.tsx`, `WeatherMap.tsx` |
| P1-8 | Fix stale `docs/PROTOTYPE_UI.md` live/demo boundary table | RI-05 | Louvatu | `docs/PROTOTYPE_UI.md:15-28,62-75` |
| P1-9 | HTTP-layer tests for synthetic V1 routes + `/api/health` readiness reporting | AI-03 / RI-05 | Parvish | new `backend/tests/test_synthetic_v1_routes.py`, `main.py:49-53` |
| P1-10 | CI workflow running backend/ML/frontend suites | RI-04 | Aryan | new `.github/workflows/ci.yml` (none exists today) |

### P2 — optional extensions (do not delay the demo)

| # | Task | Owner |
|---|---|---|
| P2-1 | Saved-location subscriptions (model, API, frontend toggle) | Aryan |
| P2-2 | Service worker + Web Push delivery with durable outbox | Aryan |
| P2-3 | Immutable alert audit-history table | Atharv |
| P2-4 | Escape the Leaflet divIcon risk interpolation | Atharv |
| P2-5 | Historical weather/risk charts (needs P0-1/2 persistence) | Louvatu |
| P2-6 | Rate limiting on public feed; CORS via environment config | Aryan |
| P2-7 | PostGIS flood polygons (needs legitimate zone data) | Atharv |

---

## 6. Exact implementation files requiring changes

**Backend (create):** `app/models/weather.py`, `app/schemas/weather.py`,
`app/api/routes/weather.py`, `app/services/weather_service.py`,
`app/services/feature_service.py`, `app/services/prediction_service.py`,
`migrations/versions/<weather_revision>.py`.

**Backend (modify):** `app/main.py` (remove dummy risk endpoint, readiness-aware
health), `app/api/routes/predictions.py` (operational endpoint),
`app/api/routes/locations.py` (admin CRUD), `app/services/alert_service.py`
(expiry/cooldown), `app/models/alert.py` (+`expires_at`), `app/models/prediction.py`
(provenance columns), `db/init_db.py` (stop relying on `create_all`).

**Frontend (modify):** `pages/AdminDashboardPage.tsx` (live feed, remove 6 h horizon
card), `pages/DashboardPage.tsx` (risk/weather overview), `components/map/LocationDetailCard.tsx`
and `locations/useMapLocations.ts` (live weather/warning), `data/prototypeData.ts`
(retire fixture predictions), `api/` (weather + risk-feed clients), new
`src/auth/*.test.ts(x)`.

**Docs (modify):** `docs/PROTOTYPE_UI.md` (live/demo boundary),
`backend/README.md` (weather runbook), `README.md` (current feature set).

---

## 7. Demonstration readiness checklist

**Ready to demo now (with honest labelling):**

- [x] Registration → pending → MET-admin approval → login (live, PostgreSQL)
- [x] Community alerts page: approved alerts from `GET /api/alerts/active`, polling,
      suppression removal (live)
- [x] Admin alert management: list/filter/create/edit/approve/reject/suppress with
      reason, audit fields, conflict handling (live)
- [x] Browser notification opt-in with permission gating and duplicate protection
- [x] Flood map: 12 registry locations, DB-driven coordinates and risk markers,
      search/filter/detail cards, "No prediction available" states (live feed;
      weather/warning panels are fixtures — label them)
- [x] Synthetic research page `/research`: three V3 scenarios, per-location frame,
      storm replay (live read-only research API, clearly badged)
- [x] Bangladesh research replay endpoint (live saved-model inference, research-only)
- [x] Alert demo fixtures (`ALERT_DEMO_ENABLED=true`) for a scripted HIGH→approve→
      notify→suppress walkthrough — **must be announced as fixtures**

**Requires work before demoing as real:**

- [ ] Weather observation submission and latest-weather display (P0-1, P0-2 — nothing exists)
- [ ] End-to-end weather → prediction → HIGH recommendation → approval → community
      notification (P0-1…P0-4 chain)
- [ ] Dashboard risk/weather overview as live data (P0-6, P0-7)
- [ ] Per-location official warnings driven by alert approvals (P0-8)
- [ ] Any claim that the 12-feature India model is "in production" (it is CLI-only)

**Do not demo as real under any circumstances:**

- Synthetic V1/V2/V3 outputs, foundation-model benchmarks (research only; V1 is the
  deployed model but its data are simulator output)
- Bangladesh metrics as Fiji forecast skill
- `GET /api/risk/{location}` (hardcoded dummy — remove before review)

---

## 8. Test results (run at commit `f60a7d8`)

| Suite | Command | Result |
|---|---|---|
| ML (incl. synthetic V3) | `backend/.venv/bin/python -m pytest ml/tests -q` | **46 passed, 1 skipped** |
| Backend + AI | `cd backend && .venv/bin/python -m pytest tests ai/tests -q` | **328 passed, 9 skipped** |
| Frontend | `cd frontend && npm run test` | **62 passed** (10 files) |
| Frontend lint | `npm run lint` | **clean** (oxlint) |
| Frontend build | `npm run build` | **succeeds** (tsc + vite) |
| Live integration (this audit) | FastAPI TestClient | `/api/locations` 200 (12 rows, 8 sample predictions correctly flagged); `/api/alerts/active` 200; `/api/synthetic/research/info` 200 (3 scenarios); `/api/weather/latest` **404**; `/api/risk/suva` 200 hardcoded dummy |

Skip gates in source include `TEST_DATABASE_URL` for PostgreSQL migration tests,
research/training artifacts and selected feature sets. ML gates include frozen
selection-audit and V2/V3 artifacts. The original run did not retain a per-test skip
summary, so attributing all skips to demo flags or V3 publication is unsupported.
No browser end-to-end test was run; lifecycle evidence comes from source and API/UI
tests. The read-only live API checks did not mutate operational alerts.

---

## 9. Recommended completion order

1. **Rishi — P0-1/P0-2 (weather storage + read API).** Everything downstream depends on
   real observations; the schema and validation decisions unblock Parvish's feature
   builder.
2. **Parvish — P0-5 (remove dummy risk endpoint) immediately**, then P0-3/P0-4
   (feature builder + operational prediction route with transactional alert handoff)
   once observations exist. This is the critical path to the integrated demo.
3. **Louvatu — P0-6/P0-7 (dashboard live feed)** can start against the existing
   `/api/locations` predictions feed and finish when the risk feed lands; delete the
   6-hour horizon card first (small, immediately visible honesty fix).
4. **Atharv — P0-8 (map live weather/warning)** and P1-1 (location admin CRUD); P1-2
   (full risk feed) pairs with Rishi's observation API.
5. **Aryan — P1-3 (expiry/cooldown), P1-5 (frontend auth tests), P1-6 (PG integration
   tests), P1-10 (CI)** in parallel; these are quality gates, not demo blockers.
6. Re-run this audit's live integration checklist after P0-4 lands — that is the moment
   the integrated demo exit checklist (`TEAM_TASK_TICKETS.md:683-694`) becomes
   satisfiable end-to-end.

---

*Audit produced by code inspection and live checks; no model-selection rules, scores or
artifacts were modified. V1 remains the deployed model; nothing in V2/V3/foundation
research was promoted.*
