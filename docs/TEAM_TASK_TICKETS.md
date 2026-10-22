# IS314 Flood Risk System — Team Task Tickets

**Project:** Flood Risk Prediction and Community Alert System — AI Powered for Fiji MET  
**Prepared:** 12 October 2026 (Pacific/Fiji)  
**Basis:** Repository audit completed on 11 October 2026  
**Purpose:** Assign the remaining work, define handoffs, and make completion verifiable.

## 1. Ownership

| Person | Primary responsibility | Assigned tickets |
| --- | --- | --- |
| You — project lead | AI/model work, prediction API, and prediction request interface | AI-01 to AI-03 |
| Aryan | Weather backend, observations, and model feature preparation | AR-01 to AR-04 |
| Louvatu | Database migrations, locations, risk read APIs, and flood map | LO-01 to LO-04 |
| Atharv | Dashboard, shared frontend data, alert interface, and frontend tests | AT-01 to AT-05 |
| Rishi | Integration contracts, backend alert completion, system tests, and release preparation | RI-01 to RI-05 |

This allocation follows technical dependencies rather than assumptions about individual skill levels. Ticket counts do not measure effort: Rishi has more cross-team coordination, while Aryan and Louvatu have substantial backend work. No completion dates are assumed; agree dates after each owner reviews the scope.

AI training, model selection, evaluation, saved-model loading, inference, the prediction endpoint, and its frontend request interface remain yours. Aryan prepares observations/features; he does not train or change the model. Atharv displays your returned results on the dashboard and owns shared frontend refresh handling. Rishi verifies alert integration; you own changes inside the prediction service and route.

## 2. Starting point and working rules

The audit verified 122 passing backend/AI tests, passing frontend lint/type checks/build, a loadable saved Random Forest, and all four PostgreSQL tables. Authentication and account approval are implemented. The database has users but no locations, predictions, or alerts. The dashboard, map, and alert frontend read local prototype data. Weather management and FastAPI inference are missing.

Use these definitions for every ticket:

- **DoR — Definition of Ready:** Information, contracts, dependencies, and access needed before implementation/integration can be completed.
- **DoD — Definition of Done:** Deliverables, review, and verification required to close the ticket.
- **Acceptance criteria:** Observable behaviours that a reviewer can check. All criteria must pass.
- **P0:** Required for the first complete integrated demo.
- **P1:** Required for the final system; do after the first integrated flow works.
- **P2:** Optional extension; do only after required work or confirmed project scope.

Shared DoD applies in addition to each ticket's own DoD:

- [ ] Changes are on a named branch, reviewed, and integrated into the shared repository.
- [ ] Relevant automated checks pass; new behaviour has meaningful tests.
- [ ] API/schema changes are documented and announced to affected owners.
- [ ] Loading, empty, invalid-input, and failure behaviour are handled where applicable.
- [ ] Existing authentication and passing tests remain intact.
- [ ] No secrets are committed. Fixtures and demonstration records are clearly labelled.
- [ ] Owner provides verification commands, results, and a screenshot or API response where useful.

Recommended branch naming: `ticket/AR-01-weather-observations`. Use this progress line in the ticket or team tracker: `Status: Ready / In progress / Blocked / Review / Done | Blocker: ... | Evidence: ...`. A named file or attractive UI is not evidence of a completed backend connection.

## 3. Shared integration contract

The following are **proposed new contracts**, not claims that these endpoints already exist. Rishi coordinates agreement in RI-01; the named implementation owner owns the code. Final path/field changes must be agreed before dependent frontend integration.

| Capability | Proposed contract | Implementation owner | Consumers |
| --- | --- | --- | --- |
| Location list/details | `GET /api/locations`, `GET /api/locations/{id}` | Louvatu | Aryan, Atharv, map |
| Location management | Admin-only create/update location endpoints | Louvatu | MET administration, provisioning |
| Weather input | `POST /api/admin/weather/observations` | Aryan | Approved MET administrator |
| Latest weather | `GET /api/weather/latest?location_id={id}` | Aryan | Dashboard, feature builder, map |
| Model features | Internal `build_prediction_features(...)` function | Aryan | Your prediction service |
| Prediction request | `POST /api/predictions` with agreed location/observation IDs | You | Your prediction interface |
| Latest risk/map feed | `GET /api/locations/risks` | Louvatu | Dashboard, map |
| Prediction history/read | `GET /api/predictions?location_id={id}` | You | Dashboard |
| Admin alerts | Existing `/api/admin/alerts` list/detail/create/edit/review routes | Existing backend; Rishi extends | Atharv |
| Public alerts | Existing `GET /api/alerts/active` | Existing backend; Rishi extends | Atharv, map |

Contract rules:

1. Use integer database IDs consistently. Keep names/display labels separate from IDs.
2. Use ISO 8601 UTC timestamps in APIs; display dates in Pacific/Fiji where appropriate.
3. Risk enum: `LOW`, `MODERATE`, `HIGH`, `VERY_HIGH`. Agree a display label if “Severe” is required; do not invent a different backend enum silently.
4. Return `flood_probability` between 0 and 1 and `model_version`. Label the percentage as flood probability, not confidence in prediction correctness.
5. Agree observation units, rainfall accumulation period, maximum acceptable observation age, error shapes, pagination, access permissions, and null/empty behaviour.
6. A location with no prediction has an explicit no-data state. Do not default it to LOW or invent a probability.
7. High-risk inference creates a PENDING recommendation. Only approved alerts appear publicly; preserve MET review.
8. Preserve the model's exact feature names. Do not fill unavailable inputs with invented measurements or labels. Any missing-value policy must be agreed with you.
9. Do not present the existing hardcoded six-hour horizon as validated. Only show a horizon supported by the agreed model contract.
10. Store the observation/input reference used for a prediction so a result can be traced to its inputs. You and Louvatu agree any Prediction schema extension.

## 4. Aryan — Weather backend

### AR-01 — Store and validate weather observations

**Owner:** Aryan | **Priority:** P0 | **Dependencies:** RI-01; LO-01 migration foundation

**What to do**

- Add a weather observation model and request/response schemas linked to a location. Include measurement time, source, units/accumulation period, and the agreed weather fields.
- Implement approved-MET-admin observation submission. Validate physical ranges, supported units, timestamps, missing fields, and location state.
- Supply a weather migration to Louvatu for ordering/review; do not create a separate migration system.

**DoR**

- Location identifiers, weather fields/units, optional versus required values, and permissions are agreed in RI-01.
- Louvatu has provided the migration base/revision convention. Owners have local backend/database setup.

**DoD**

- Observation table, migration, schemas, and protected write API are integrated and documented.
- Valid submissions persist; invalid requests and authorization failures are covered by tests.

**Acceptance criteria**

1. An approved MET administrator submits valid measurements and receives the stored observation with integer ID, location ID, source, and timestamp.
2. A separate database session/request can retrieve the submitted record; restart does not lose it.
3. Invalid ranges, unsupported units, future timestamps beyond the agreed tolerance, and nonexistent/inactive locations produce controlled errors without inserting a row.
4. Anonymous/community users cannot write observations; malformed bodies receive field-level validation errors.

**Starting files:** `backend/app/models/`, `schemas/`, `api/routes/`, `services/`, `db/session.py`. Coordinate new migrations with Louvatu.

### AR-02 — Expose latest weather from actual stored observations

**Owner:** Aryan | **Priority:** P0 | **Dependencies:** AR-01; RI-01

**What to do**

- Add latest-weather retrieval by location with observation time, source, units, and freshness information.
- Support a small, clearly labelled demo input set through AR-01; keep manually entered observations distinguishable from a live provider.

**DoR**

- AR-01 persists observations. Latest/no-data/stale response contracts are agreed with Louvatu and Atharv.

**DoD**

- Read endpoint returns database-backed observations with documented empty/stale behaviour.
- Tests verify timestamp ordering, location isolation, missing data, and database failure handling.

**Acceptance criteria**

1. With two differently dated observations at one location, the endpoint returns the latest by observation time, not insertion order.
2. Each location receives only its own observations; unknown IDs and locations without observations have distinct documented outcomes.
3. Stale data is explicitly identified using the agreed freshness rule.
4. Database failures produce a safe error, not hardcoded weather or credentials/stack traces.

**Starting files:** New weather routes/service; `backend/app/db/session.py`; coordinate LO-03 consumers.

### AR-03 — Build the model feature input from observations and location data

**Owner:** Aryan | **Priority:** P0 | **Dependencies:** AR-01, LO-02; your AI-01 contract

**What to do**

- Provide a reusable internal feature-building function for your prediction service.
- Map observed weather and stored location attributes to all 12 exact model feature keys. Document the source and unit of each feature.
- Return input provenance and handle missing/stale measurements according to the agreed policy. AI inference stays yours.

**DoR**

- You have confirmed the feature schema and missing-value policy. Louvatu has agreed where static attributes are stored.
- Units and temporal meanings are confirmed; an observation and matching location exist.

**DoD**

- Feature builder and feature-source table are integrated; you can call it without importing frontend prototype data.
- Tests cover key names, transformations, provenance, missing data, stale data, and location mismatch.

**Acceptance criteria**

1. A supplied location/observation produces exactly the model's required numeric and categorical keys.
2. Neither `Flood Occurred` nor `Historical Floods` is included.
3. Every value can be traced to a stored observation or documented location attribute; unavailable data is never silently fabricated.
4. Missing required data or incompatible rainfall units/periods stop prediction with a clear reason; permitted nulls follow your approved policy.
5. An observation from a different location cannot be used for the requested location.

**Starting files:** `backend/ai/config.py` as a read-only contract reference; new `backend/app/services/weather_service.py` or feature service. Do not edit training/inference code.

### AR-04 — Complete weather ingestion reliability and tests

**Owner:** Aryan | **Priority:** P1 | **Dependencies:** AR-01 to AR-03

**What to do**

- Complete weather validation/API coverage and a reproducible input-to-feature walkthrough.
- Document manual observation entry as the initial ingestion source. If the team selects an external provider, add an adapter with timeouts, source mapping, and controlled failure handling.
- Define observation identity so repeated provider/import requests do not silently duplicate the same reading.

**DoR**

- Initial ingestion source is agreed. A provider adapter starts only when access, allowed usage, field coverage, and units are known.
- Observation identity and failure/refresh rules are agreed.

**DoD**

- Weather tests and input runbook are integrated; source limitations are explicit.
- Selected ingestion mode handles repeated inputs and unavailable sources predictably.

**Acceptance criteria**

1. The documented ingestion command/workflow yields data retrievable by AR-02 and usable by AR-03.
2. Repeating the same source observation follows the agreed idempotency/conflict rule.
3. Provider failures, if a provider is integrated, preserve existing data and never replace it with invented current weather.
4. Weather regression tests pass and explain which fields cannot currently be obtained automatically.

**Starting files:** New weather tests/services, `backend/.env.example`, `backend/README.md` weather section. Coordinate final documentation with Rishi.

## 5. Louvatu — Database and flood mapping

### LO-01 — Establish migrations and extend location storage

**Owner:** Louvatu | **Priority:** P0 | **Dependencies:** RI-01 schema agreement

**What to do**

- Configure one Alembic migration workflow for the project and a documented baseline for both new and existing databases.
- Extend Location with validated latitude/longitude and agreed display/static attributes needed by mapping/features.
- Coordinate weather and prediction schema changes supplied by Aryan and you. Preserve existing users and alert references.

**DoR**

- Owners have agreed required location/observation/prediction fields and migration ownership.
- A disposable PostgreSQL database is available; existing-table baseline strategy is reviewed before use on shared data.

**DoD**

- Migration configuration and reviewed revisions are committed with fresh/existing database instructions.
- Schema changes are tested on PostgreSQL without destroying existing users or alert references.

**Acceptance criteria**

1. A new database upgrades to all required tables/constraints through documented migrations.
2. A database representing the current schema upgrades without losing users; its baseline procedure verifies schema compatibility before stamping.
3. Stored coordinates obey valid latitude/longitude ranges.
4. The team uses one ordered migration history; schema changes do not rely solely on `create_all()`.

**Starting files:** `backend/app/models/location.py`, `prediction.py`, `db/init_db.py`, `requirements.txt`; new Alembic configuration/revisions.

### LO-02 — Provide location APIs and repeatable demo provisioning

**Owner:** Louvatu | **Priority:** P0 | **Dependencies:** LO-01; RI-01

**What to do**

- Add location list/detail APIs and protected administrator create/update operations.
- Provide repeatable provisioning of clearly labelled monitored demo locations and required static attributes.
- Define deactivation behaviour without deleting referenced historical predictions/alerts.

**DoR**

- Location fields/IDs/permissions are agreed; migrations are ready for the required columns.

**DoD**

- APIs, provisioning instructions/script, and location tests are integrated.
- Aryan can reference valid database locations; frontend consumers can read coordinates.

**Acceptance criteria**

1. List/detail responses contain integer IDs, names, coordinates, and agreed display fields.
2. Only approved MET administrators can create/update locations; invalid coordinates and blank names are rejected.
3. Repeating demo provisioning does not duplicate locations or erase user records.
4. Deactivation preserves history and prevents new weather/prediction/alert work according to the agreed policy.

**Starting files:** `backend/app/models/location.py`; new location schemas/routes/services/tests.

### LO-03 — Expose the shared location/weather/risk read feed

**Owner:** Louvatu | **Priority:** P0 | **Dependencies:** LO-02, AR-02; your AI-02 persistence contract

**What to do**

- Add a read API joining monitored locations, latest observations, latest predictions, and approved public alerts.
- Provide consistent IDs, risk/probability, observation/prediction timestamps, model version, and no-data states for map/dashboard consumers.
- Keep internal alert review fields out of public responses.

**DoR**

- Aryan and you have supplied persisted weather/prediction response contracts.
- Atharv agrees feed fields; pending versus approved visibility rules are fixed.

**DoD**

- Shared feed is integrated and tested for latest-record selection, no-data handling, and public visibility.
- Atharv and the map can consume the same risk source without duplicating inference.

**Acceptance criteria**

1. A stored prediction appears against the correct location with its actual probability/risk/model version.
2. Missing or stale data is explicitly represented; no prediction is replaced with a default LOW value.
3. Pending, rejected, suppressed, expired, and inactive-location alerts are excluded from public warning output according to implemented lifecycle rules.
4. Feed results update when new observations/predictions or alert approval/suppression are saved.

**Starting files:** `backend/app/models/location.py`, `prediction.py`, `alert.py`, `services/alert_service.py`; new risk-feed route/schema/service.

### LO-04 — Connect the flood map to actual backend data

**Owner:** Louvatu | **Priority:** P0 | **Dependencies:** LO-03; existing frontend API client

**What to do**

- Replace prototype location/weather/risk/warning records on `/weather-map` with the shared backend feed.
- Preserve marker selection, search, risk filters, tooltips, and location details; adapt string IDs to the agreed integer contract.
- Add loading, retry, empty/no-data, stale-data, and tile-failure behaviour with focused map tests.

**DoR**

- Feed endpoint is available, or its agreed contract permits clearly labelled development stubs. Live acceptance requires the endpoint.
- Coordinate shared frontend types/client changes with Atharv.

**DoD**

- Map reads backend data and approved warnings; prototype mode, if retained, is explicit and separate.
- Tests/manual evidence cover marker updates, filters, no data, API failure, and unavailable basemap tiles.

**Acceptance criteria**

1. Database location coordinates determine marker positions; saving a new prediction changes that location's risk marker after refresh.
2. Search, filtering, and selection still work with API IDs and responses.
3. A location without a prediction displays “No prediction available”; pending recommendations never appear as official warnings.
4. Approving/suppressing an alert changes the warning shown after refresh.
5. API/tile failure produces a visible status and leaves usable location information; it never silently switches to mock weather.

**Starting files:** `frontend/src/pages/WeatherMapPage.tsx`, `components/map/WeatherMap.tsx`, `LocationDetailCard.tsx`, `api/client.ts`, `types/prototype.ts`.

## 6. Atharv — Dashboard and alert frontend

### AT-01 — Replace dashboard prototype metrics with backend results

**Owner:** Atharv | **Priority:** P0 | **Dependencies:** LO-03, AR-02; RI-01

**What to do**

- Connect the MET dashboard to actual monitored locations, weather, predictions, and alerts.
- Add a community risk/weather overview to `/dashboard` while preserving account information and role restrictions.
- Add refresh, loading, empty/no-data, stale-data, and error/retry states.

**DoR**

- Feed contracts and community/admin visibility are agreed. Backend integration starts when the APIs are available.

**DoD**

- Both dashboard roles show API-derived information with focused tests and backend-change demonstration evidence.
- Mock confidence values and unsupported forecast wording are removed from live views.

**Acceptance criteria**

1. Changing stored prediction/alert records changes displayed counts and results after refresh.
2. Community users see their allowed risk/weather information but cannot access admin operations.
3. Probability, model version, and timestamps match backend responses; no fabricated horizon is displayed.
4. Empty/failing APIs produce clear messages and retry controls rather than stale demo cards presented as live.

**Starting files:** `frontend/src/pages/DashboardPage.tsx`, `AdminDashboardPage.tsx`, `api/`, `components/dashboard/`, `PrototypeDataProvider.tsx`.

### AT-02 — Provide shared live frontend data types and refresh handling

**Owner:** Atharv | **Priority:** P0 | **Dependencies:** RI-01; LO-03 and AR-02 for live verification

**What to do**

- Add typed clients/shared response types for location, latest-weather, risk-feed, and alert reads. Coordinate map usage with Louvatu and keep prediction request/inference code with you.
- Provide a shared refresh mechanism for dashboard/map/public alerts after your saved prediction or an alert review action.
- Handle request cancellation, stale responses, API errors, and freshness consistently without presenting prototype fallbacks as live data.

**DoR**

- Read contracts, error shapes, permissions, and refresh ownership are agreed with Louvatu, Aryan, and you. Contract fixtures can support early work; final acceptance uses the backend.

**DoD**

- Shared clients/types and refresh handling are integrated with focused tests and a documented handoff to Louvatu and you.
- Data consumers use the same identifiers and risk/probability meanings.

**Acceptance criteria**

1. Location/weather/risk/alert reads use the agreed endpoints and preserve integer IDs, timestamps, risk enums, and actual probabilities.
2. Triggering refresh after a saved prediction or alert mutation updates affected consumers without a full browser reload.
3. An older request resolving after a newer request cannot overwrite the newer visible data; requests/subscriptions are cleaned up when views unmount.
4. Failed requests surface usable error/retry state and do not silently load `PROTOTYPE_*` records.

**Starting files:** `frontend/src/api/client.ts`, new domain API/type/data-hook files, dashboard/workspace components. Your `api/predictions.ts` and prediction request interface stay yours.

### AT-03 — Connect administrator alert management to existing APIs

**Owner:** Atharv | **Priority:** P0 | **Dependencies:** Existing alert backend; LO-02 for manual drafts; RI-01

**What to do**

- Replace local alert state/actions with authenticated list/detail/create/edit/approve/reject/suppress requests.
- Add suppression-reason input, supported pending edits, manual draft entry, and review/audit details appropriate for administrators.
- Handle status filters, pagination, request failures, stale-state conflicts, and expired sessions.

**DoR**

- Read `docs/ALERT_SYSTEM.md`; endpoint bodies and integer IDs are confirmed.
- Approved admin login and a demo location are available for live review tests.

**DoD**

- Real alert API client and review UI are integrated; mutations persist after reload.
- Tests cover allowed transitions, required reasons, authorization failures, and 409 conflicts.

**Acceptance criteria**

1. List/detail uses `/api/admin/alerts`; ALL filtering deliberately combines supported statuses or uses an agreed backend extension, not an unsupported `status=ALL`.
2. Approving a pending alert saves the reviewer/timestamp and makes it available in the public API.
3. Suppression sends a nonblank reason and removes approved alerts from public display.
4. Reviewed alerts cannot be edited/reapproved; 409 responses trigger refresh and a clear message.
5. Full reload preserves backend status. Anonymous/community users cannot perform review actions.

**Starting files:** `frontend/src/pages/AlertsDashboardPage.tsx`, `prototype/PrototypeDataProvider.tsx`; new `api/alerts.ts`; backend alert schemas as contract reference.

### AT-04 — Display approved alerts and community notifications

**Owner:** Atharv | **Priority:** P0 | **Dependencies:** Existing public alert API; AT-03 for approval walkthrough

**What to do**

- Fetch `/api/alerts/active` and provide a visible community alert panel/banner with message, severity, location, and timestamp.
- Implement a documented refresh/polling interval and client deduplication so the same approved alert is not repeatedly announced.
- Handle suppression/removal, expiry when RI-02 lands, unavailable API, and accessibility.

**DoR**

- Public response schema and polling interval are agreed. A real approved demo alert can be created through AT-03/API.

**DoD**

- Community notification display uses actual approved alerts; polling cleans up on unmount/logout as applicable.
- Tests cover new alerts, repeats, removal, errors, and severity presentation.

**Acceptance criteria**

1. Approving a backend alert causes a visible notification within the configured refresh interval without a full browser reload.
2. Message, risk severity, location, and time match the public response.
3. Pending/rejected/suppressed/expired alerts are not shown as active public warnings.
4. Repeated polling does not create repeated toasts for an unchanged alert; suppression removes it from the active panel.
5. API failure is visible and does not imply that no warnings exist. Severity is conveyed by text as well as colour.

**Starting files:** Dashboard/workspace components, new public alert panel and API client; `components/Alert.tsx` is feedback infrastructure only.

### AT-05 — Add frontend component and authentication regression tests

**Owner:** Atharv | **Priority:** P1 | **Dependencies:** AT-01 to AT-04; coordinate map coverage with Louvatu

**What to do**

- Set up a frontend test runner and test the live dashboard, prediction, alert, and route/session behaviours.
- Improve session-expiry handling so a protected live view does not remain misleadingly signed in; agree the revalidation mechanism with Rishi.
- Keep tests at user-observable boundaries. Any mocked responses must be labelled test fixtures and match the agreed API contracts.

**DoR**

- Test tools/scripts and coverage boundaries are agreed; stable live API contracts exist.

**DoD**

- A documented frontend test command passes alongside lint/type/build checks.
- Tests and any session handling fixes are integrated; Rishi can run them in CI.

**Acceptance criteria**

1. Tests cover role guards, restored sessions, expired/invalid tokens, temporary network failure, and logout.
2. Prediction submission/loading/error/result and alert review/notification paths have meaningful assertions.
3. Unavailable or empty domain APIs are visibly handled; frontend tests do not count a static prototype card as successful integration.
4. Existing backend authorization remains the security boundary; frontend handling does not bypass permission failures.

**Starting files:** `frontend/package.json`, `src/auth/`, `api/`, `pages/`, components; add frontend tests. Coordinate CI with RI-04.

## 7. Rishi — Alerts, QA, and release preparation

### RI-01 — Agree cross-team contracts and establish a reproducible baseline

**Owner:** Rishi | **Priority:** P0 | **Dependencies:** All owners' contract review; no implementation blocker to drafting

**What to do**

- Turn Section 3 into an agreed API/data contract with example requests/responses, permissions, freshness rules, and error conventions.
- Coordinate ownership of shared files/migrations and delivery of the existing untracked AI/alert code, dataset, and model reproduction instructions.
- Record dependencies and handoff status; do not modify model behaviour on your behalf.

**DoR**

- Audit findings and this document are available. Each owner confirms their schema/endpoint requirements.

**DoD**

- Agreed contract/examples and shared setup checklist are in the repository.
- Existing features needed by the team are available from the shared repository or a documented artifact source; no dependency on unexplained local files remains.

**Acceptance criteria**

1. Each owner can identify their inputs, outputs, IDs, timestamps, permissions, and error shapes.
2. A fresh checkout contains required source/test files; dataset and ignored joblib artifacts have explicit acquisition/training instructions.
3. No credentials are committed; nobody is instructed to blindly overwrite the project's existing uncommitted work.
4. Each shared file has an agreed primary editor, and dependent teams acknowledge the first contract version.

**Starting files:** This document, `backend/ai/README.md`, `docs/ALERT_SYSTEM.md`, `.gitignore`, API/schema files and repository status. Coordinate integration with you.

### RI-02 — Complete backend alert lifecycle and prediction handoff

**Owner:** Rishi | **Priority:** P1 for expiry/cooldown; P0 for existing-helper handoff | **Dependencies:** Your AI-02; LO-02; agreed alert policy

**What to do**

- Verify/document use of `create_alert_from_prediction()` inside your prediction transaction; you implement its call in your service.
- Preserve retry idempotency, approval-only publication, and atomic rollback. Add configurable expiry and a documented repeated-event/cooldown policy for new predictions if required by the final system.
- Keep auditability and escalation behaviour explicit; do not revive reviewed historical alerts automatically.

**DoR**

- You confirm prediction persistence and transaction ownership. Expiry, cooldown, severity escalation, and withdrawal rules are agreed before extending behaviour.

**DoD**

- Handoff works with stored results and its rollback/retry cases are tested.
- Agreed lifecycle extensions, migrations supplied to Louvatu, public visibility, and policy documentation are integrated.

**Acceptance criteria**

1. HIGH/VERY_HIGH saved results create PENDING recommendations; LOW/MODERATE do not. No public alert appears before review.
2. Retrying one prediction creates at most one recommendation and never revives a rejected/suppressed alert.
3. Prediction/alert failure rolls back together when the prediction service uses the documented transaction contract.
4. Expired alerts are excluded publicly. Repeated new predictions and increased severity follow the approved cooldown/escalation policy, with traceable decisions.
5. Approval/suppression audit fields remain valid and no notification hook is called before successful approval commit.

**Starting files:** `backend/app/services/alert_service.py`, `notification_service.py`, `models/alert.py`, `schemas/alert.py`, `tests/test_alerts.py`. Coordinate prediction-route changes with you.

### RI-03 — Add PostgreSQL integration and backend regression coverage

**Owner:** Rishi | **Priority:** P1 | **Dependencies:** LO-01; weather/prediction/alert contracts

**What to do**

- Add a disposable PostgreSQL integration test setup in addition to the existing SQLite tests.
- Verify migrations, enum/foreign-key/check constraints, persistence, rollback, concurrent alert retries/review, and safe database errors.
- Extend important authentication cases such as incorrectly signed tokens and write-permission boundaries without rewriting functioning authentication.

**DoR**

- Disposable database and credentials are available through test configuration; migrations and ownership are established.

**DoD**

- PostgreSQL suite is isolated, repeatable, documented, and runnable by the team/CI.
- Findings are fixed by the responsible owner; existing backend/AI tests still pass.

**Acceptance criteria**

1. Tests never write to the development/demo/production database and clearly identify the selected disposable database.
2. Actual PostgreSQL constraints and transaction behaviour are exercised rather than assumed from SQLite.
3. Concurrent requests for the same prediction cannot create duplicate alerts; conflicting review transitions have one valid outcome.
4. Authentication/authorization/error tests pass without exposing hashes, secrets, or internal database details.

**Starting files:** `backend/tests/conftest.py`, `test_alerts.py`, authentication tests; new PostgreSQL integration fixtures/tests.

### RI-04 — Automate the complete system flow and CI

**Owner:** Rishi | **Priority:** P0 for first integration test; P1 for full CI | **Dependencies:** AR-03, LO-04, AT-01 to AT-04, your AI-02

**What to do**

- Add browser/API integration tests for login, weather input, prediction, dashboard/map changes, MET review, and public notification.
- Configure CI for backend/AI tests, disposable PostgreSQL integration, frontend tests, lint/type/build, and agreed browser checks.
- Use explicit fixtures for repeatable high/low alert branches. Separately verify a real saved-model prediction; do not report fixture results as model accuracy.

**DoR**

- Core APIs/UIs are integrated. Repeatable test accounts/locations/observations and model artifact setup are available.
- Atharv provides the frontend test command and helps identify stable UI selectors.

**DoD**

- End-to-end script and CI configuration are committed with pass/fail evidence and useful diagnostics.
- Full system can be verified from a clean test setup; temporary test resources are cleaned safely.

**Acceptance criteria**

1. An approved user can log in and see a real persisted prediction on dashboard/map after a valid weather submission and inference request.
2. The deterministic HIGH branch creates only a pending recommendation; MET approval then produces a community notification, and suppression removes it.
3. The LOW branch produces no recommendation; expired tokens, unavailable APIs, invalid input, and duplicate retries have expected outcomes.
4. A real saved-model response is checked independently for probability, risk mapping, version, and persistence; controlled fixture branches are clearly distinguished.
5. CI fails when a required test/type/build check fails and reports enough evidence to locate the error.

**Starting files:** New CI workflow and system/browser tests; existing backend tests; frontend test configuration supplied by Atharv.

### RI-05 — Make setup, readiness, and the lecturer demo reproducible

**Owner:** Rishi | **Priority:** P1 | **Dependencies:** RI-01; core integration; other owners' setup notes

**What to do**

- Update README/setup/presentation docs to match current features, test counts, real-versus-demo boundaries, Python runtime, migrations, and artifact setup.
- Make frontend API URL and backend CORS environment-appropriate; verify one documented run/deployment configuration.
- Add readiness reporting for required database/model availability, using your exposed model-loading status rather than implementing inference.
- Prepare a lecturer demo runbook and data/account provisioning checklist with honest ML metrics and no unsupported horizon claims.

**DoR**

- Team agrees the target environment and required readiness checks. You supply model availability/version status and inference limitations.
- Core ticket verification evidence and migration commands are available.

**DoD**

- Fresh setup and the agreed environment smoke test succeed; configuration examples contain no secrets.
- Docs/runbook match actual behaviour and contain fallback steps for unavailable APIs/map tiles.

**Acceptance criteria**

1. A teammate follows the documented setup from a clean checkout and reaches working auth, weather, prediction, map, and reviewed public alerts.
2. Runtime instructions agree with supported Python and installed dependencies; model acquisition/training is explicit.
3. Frontend requests target the configured backend and pass CORS in the agreed environment, not a visitor's localhost accidentally.
4. Readiness reports missing database/model dependencies; it does not always return healthy when prediction cannot run.
5. Lecturer materials distinguish manual observations, live provider data if any, ML limitations, fixture tests, and notifications actually implemented.

**Starting files:** `README.md`, `backend/README.md`, `frontend/README.md`, `docs/PRESENTATION_HANDBOOK.md`, `PROTOTYPE_UI.md`, `ALERT_SYSTEM.md`, `.env.example` files, `core/config.py`, `main.py`, `api/client.ts`, `vercel.json`.

## 8. Your reserved AI tickets

These tickets belong to you. Other owners provide inputs and tests at their boundaries; they do not take over model development.

### AI-01 — Finalise the AI contract and validate the modelling approach

**Owner:** You | **Priority:** P0 contract; P1 stronger data/evaluation | **Dependencies:** Aryan's feature-source agreement

**What to do:** Confirm the 12 features, units, missing-value rules, risk mapping, output schema, supported input source, and prediction horizon. Investigate near-chance performance, source provenance, independent evaluation, calibration, and Fiji transfer. Preserve reproducible preprocessing/training and saved pipelines.

**DoR:** Current dataset, artifacts, metrics, and feature list are available; observation definitions can be reviewed with Aryan.

**DoD:** Contract and current limitations are documented; any model/data change has reproducible metrics and a versioned saved pipeline. Independent evaluation is separated from model selection before stronger performance claims.

**Acceptance criteria:** Feature and output contracts are usable by Aryan/Atharv; inference matches saved preprocessing; metrics come from actual evaluation; unsupported six-hour forecasts/confidence claims are absent.

**Starting files:** `backend/ai/config.py`, `inspection.py`, `preprocessing.py`, `train.py`, `evaluate.py`, model metadata/artifacts.

### AI-02 — Integrate saved-model inference and prediction persistence into FastAPI

**Owner:** You | **Priority:** P0 | **Dependencies:** AR-03, LO-01/LO-02, RI-01; existing alert helper

**What to do:** Load the saved pipeline once, add validated prediction/read APIs, call Aryan's feature builder, persist results and input provenance, invoke the existing recommendation helper in the same transaction, and replace/remove the fixed HIGH/0.82 placeholder. Build the frontend prediction request/result interface using actual location/observation IDs; use Atharv's shared refresh handoff to update the risk views. Coordinate necessary prediction schema changes with Louvatu.

**DoR:** Valid location/observation data, feature builder contract, model artifact, permissions, and transaction handoff are agreed.

**DoD:** Real API inference, persistence, frontend submission/result display, no-data/error handling, rollback, and model readiness state are integrated and tested; Atharv can display the persisted result through the shared read feed.

**Acceptance criteria:** Actual model outputs are returned/stored with probability/risk/version/time; normal requests never retrain; missing model/invalid or stale inputs return controlled errors; high-risk results produce pending recommendations only; prediction and alert failures cannot leave inconsistent records. The frontend sends actual location/observation IDs, disables duplicate submission while loading, displays the returned result/errors, and triggers shared refresh after success.

**Starting files:** `backend/ai/predict.py`, new prediction routes/schemas/service, `models/prediction.py`, `app/main.py`, new `frontend/src/api/predictions.ts` and prediction request/result components; coordinate `alert_service.py` with Rishi and refresh handling with Atharv.

### AI-03 — Verify inference and deliver the model handoff

**Owner:** You | **Priority:** P0 | **Dependencies:** AI-01/AI-02

**What to do:** Add prediction API/model regression tests, verify artifact/version reproducibility, and provide a real observation-to-output example plus startup/artifact instructions for Rishi and Atharv.

**DoR:** Prediction API and saved-model version are available; expected outputs/errors and input provenance are defined.

**DoD:** Model/API tests pass without retraining during requests; handoff includes example requests/responses, exact commands, metrics, and limitations.

**Acceptance criteria:** Reloaded pipeline reproduces probabilities; risk boundaries and malformed/missing/stale inputs are tested; API output matches direct inference on the same features; a clean setup can obtain the artifact; fixture high-risk outputs are never presented as real model performance.

**Starting files:** `backend/ai/tests/test_pipeline.py`, new prediction API tests, `backend/ai/README.md`.

## 9. Execution order and handoffs

| Stage | Aryan | Louvatu | Atharv | Rishi | You |
| --- | --- | --- | --- | --- | --- |
| 1. Agree inputs and setup | Weather field/unit definitions | Migration/location plan | Review response/UI requirements | RI-01 contract and repository baseline | AI-01 feature/output contract |
| 2. Build independent foundations | AR-01 storage/input, AR-02 reads | LO-01 migrations, LO-02 location APIs | AT-03 existing alert API integration; draft other UI against labelled contract fixtures | Existing alert handoff/tests; plan RI-03/04 | Saved-model startup and prediction API structure |
| 3. Connect prediction data | AR-03 feature builder | LO-03 live read feed | AT-02 shared live data/refresh, AT-01 dashboards | Verify transaction/idempotency handoff | AI-02 inference/persistence/request interface, AI-03 tests |
| 4. Complete public flow | Weather failure verification | LO-04 live map | AT-04 approved notifications | RI-04 first full flow test | Confirm real API/model equivalence |
| 5. Final-system quality | AR-04 ingestion reliability | Migration/map regressions | AT-05 frontend/auth tests | RI-02 lifecycle extensions, RI-03 PostgreSQL tests, CI and RI-05 release | Independent evaluation/data improvements |

First actions for each owner:

- **Aryan:** Review the model features with you and draft AR-01 field/unit rules.
- **Louvatu:** Agree the migration baseline and Location extension; start LO-01.
- **Atharv:** Read the already implemented alert API and start AT-03, which does not depend on finished AI integration.
- **Rishi:** Finalise RI-01 with the team and confirm everyone can access the current source/artifacts.
- **You:** Confirm AI-01 request/output/feature contracts so other owners can progress.

Handoff rule: provide endpoint/function signature, example valid/invalid payloads, verification command, branch/commit reference, known limitations, and acknowledgement from the receiving owner. Mark dependent implementation blocked only for the missing handoff; continue independent ticket work.

## 10. Optional extensions — do not delay the integrated demo

| Extension | Owner | Readiness / acceptance boundary |
| --- | --- | --- |
| External SMS/email/push delivery, subscriptions, retries/outbox | Rishi | Starts only when required channel/provider/scope is agreed; approval queues a durable delivery, retries avoid duplicate sends, and failures are traceable |
| Backend authentication hardening: rate limiting, recovery, refresh/revocation policy | Rishi, with Atharv for UI | Agree the mechanism first; retain role/approval checks and test expired/revoked tokens and recovery without information leakage |
| Flood polygons, overlays, or PostGIS | Louvatu | Requires legitimate zone data and an actual requirement; zones match locations and risk source rather than decorative shapes |
| Historical weather/risk charts | Atharv, using Aryan/your history APIs | Requires persisted history; displayed points/times match actual records |
| Full immutable alert edit-history log | Rishi | Requires retention/history policy and Louvatu's migration review; every change is attributable without rewriting past events |

Convert an extension into a full ticket with its own DoR/DoD/acceptance criteria before scheduling it. In-app approved-alert display is P0; external delivery is a separate scope decision.

## 11. Integrated demo exit checklist

- [ ] Approved user login succeeds; community/admin access boundaries remain enforced.
- [ ] Real submitted/retrieved observations are stored against database locations.
- [ ] Those observations and agreed static attributes produce the model input without invented values.
- [ ] Saved-model inference returns a persisted result through FastAPI without retraining.
- [ ] Dashboard and map display that result and its data timestamps.
- [ ] HIGH/VERY_HIGH recommendation handling is verified; recommendations remain private until review.
- [ ] MET approval makes an alert visible through the public API and community notification panel.
- [ ] Refresh preserves records; suppression removes the public warning.
- [ ] Invalid input, missing/stale data, expired tokens, and unavailable services are demonstrated/tested.
- [ ] Clean setup, test commands, artifacts, real-versus-fixture boundaries, and honest ML metrics are documented.

**Completion evidence:** Owners attach results to their tickets. Rishi verifies the complete flow; you review the AI boundary and overall integration. A ticket closes only when its own criteria and the shared DoD are satisfied.
