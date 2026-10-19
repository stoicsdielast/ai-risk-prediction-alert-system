# Frontend Prototype: Architecture, Setup, and Demo Guide

This guide explains how the current FloodWatch Fiji frontend prototype works,
how to run it, and which parts are connected to the FastAPI/PostgreSQL backend.
It is intended for development, demonstrations, and university-project review.

For the detailed authentication design and API behavior, see
[Authentication System: How It Works](./AUTHENTICATION_WORKFLOW.md).

## Prototype boundary

The interface deliberately combines a working account system with illustrative
flood-operation screens. The badges in the workspace help identify the source:

| Area | Current source | Persistent? | Status |
| --- | --- | --- | --- |
| Registration, login, and current user | FastAPI + PostgreSQL | Yes | Live |
| Pending-account list and account approval/rejection | FastAPI + PostgreSQL | Yes | Live |
| Community account overview | Current user returned by FastAPI | Yes | Live auth data |
| Weather observations and monitored locations | `prototypeData.ts` | No | Demo data |
| Flood-risk levels and AI predictions | `prototypeData.ts` | No | Demo data |
| MET operational dashboard metrics | Derived from local prototype data | No | Demo data |
| Flood-alert list and alert actions | React prototype state | No | Demo workflow |
| `/research` synthetic scenario study | Read-only FastAPI + published research bundles | No (bundles on disk) | Research only |
| OpenStreetMap basemap | Public internet tile service | External tiles only | Visual context |

The prototype weather values, risk levels, predictions, alert messages, and
"official warning" examples are not current Fiji MET information. They must not
be used for safety decisions or presented as a functioning warning service.

## Architecture

```text
Browser
├── React Router
│   ├── public authentication pages
│   ├── public weather-map prototype
│   ├── protected community overview
│   └── protected MET-admin workspaces
├── AuthProvider
│   ├── JWT in sessionStorage
│   └── live /api/auth/me user
└── PrototypeDataProvider
    ├── local locations and predictions
    └── in-memory alert state
         │
         ├── live account requests ──────► FastAPI ──────► PostgreSQL
         │                                JWT + SQLAlchemy
         │
         └── basemap tile requests ─────► OpenStreetMap tile server
```

`AuthProvider` and `PrototypeDataProvider` have intentionally different jobs:

- `AuthProvider` calls the backend, restores authenticated sessions, and owns
  the current user and JWT.
- `PrototypeDataProvider` supplies local weather, prediction, and alert records.
  Alert status changes remain in React memory and reset after a full browser
  reload.
- React route guards improve navigation, but FastAPI remains the security
  boundary for every live protected API.

## Frontend routes

| Route | Access | Data source | Purpose |
| --- | --- | --- | --- |
| `/` | Signed-out users | Static UI | Welcome and access choices |
| `/login` | Signed-out users | Live auth API | Login with an approved account |
| `/register` | Signed-out users | Live auth API | Request a community or MET-admin account |
| `/registration-submitted` | Signed-out users | Navigation state | Explain that approval is pending |
| `/weather-map` | Public | Local demo data + map tiles | Explore prototype conditions and flood-risk signals |
| `/dashboard` | Authenticated | Live current-user data | Community/account overview |
| `/admin/dashboard` | Approved `MET_ADMIN` | Local demo data | Operational summary and recent activity |
| `/admin/alerts` | Approved `MET_ADMIN` | Local in-memory data | Demonstrate an alert-review workflow |
| `/admin/users/pending` | Approved `MET_ADMIN` | Live admin API | Approve or reject actual registered accounts |
| `/research` | Authenticated (any role) | Live read-only research API | Synthetic scenario study, research only |

Authenticated users visiting a public authentication page are redirected to
their workspace. A `MET_ADMIN` goes to `/admin/dashboard`; a community user goes
to `/dashboard`. A community user who attempts an admin frontend route is sent
back to `/dashboard`.

The frontend role guard is not sufficient protection for a real admin action.
The existing account-review API also validates the JWT, active/approved state,
and current PostgreSQL role on the backend. Future alert APIs must do the same.

## Live authentication and account integration

The frontend currently calls these implemented APIs:

| Method and endpoint | Used by |
| --- | --- |
| `POST /api/auth/register` | Registration form |
| `POST /api/auth/login` | Login form |
| `GET /api/auth/me` | Login verification and session restoration |
| `GET /api/admin/users/pending` | Live pending-account page |
| `PATCH /api/admin/users/{user_id}/approve` | Live account approval |
| `PATCH /api/admin/users/{user_id}/reject` | Live account rejection |

Every registered account starts active with status `PENDING`. Selecting
`MET_ADMIN` requests that role but does not approve it. Only an active account
with status `APPROVED` can log in.

After a successful password check, FastAPI returns an HS256 JWT containing the
user ID in `sub` and an expiration in `exp`. The frontend immediately verifies
the token through `/api/auth/me` and then stores it in `sessionStorage` under:

```text
fiji-flood-access-token
```

On reload, the frontend uses the stored token to call `/api/auth/me` again.
Invalid, expired, rejected, pending, or inactive sessions are removed. A
temporary network failure retains the token and shows a retry screen. Logout is
currently local: it clears the token and user state but does not revoke the JWT
on the backend.

## Prototype flood screens

### Public weather and flood-risk map

`/weather-map` is intentionally public. It contains local records for eight
Fiji locations across the Central, Western, and Northern divisions. A user can:

- Search by location or division.
- Filter locations by low, moderate, high, or very-high risk.
- Select a map marker or a location card.
- Inspect illustrative weather metrics, rainfall, humidity, and wind.
- Compare an AI prediction label/confidence with a separately labelled warning
  example.

The selected detail panel clearly treats AI output as decision support rather
than an official warning. Searching and filtering occur entirely in the
browser; they do not call FastAPI.

### MET operational dashboard

`/admin/dashboard` is visible only after an approved MET-admin session has been
restored. Its content is still prototype data. It derives:

- Number of monitored locations.
- Approved and pending alert counts.
- Number of high/very-high-risk locations.
- Recent alert activity.
- Recent prototype predictions and confidence values.

Because the dashboard and alert screen share `PrototypeDataProvider`, changing
a demo alert can change the derived dashboard counts during the same browser
session. It does not update PostgreSQL.

### MET alert management

`/admin/alerts` demonstrates the intended review experience. An administrator
can search, filter, select a record, and confirm approve, reject, or suppress
actions. The provider waits briefly to simulate an API request, updates React
state, and shows a success message.

These alert actions:

- Do not call FastAPI.
- Do not write to PostgreSQL.
- Do not send a community alert.
- Do not contact Fiji MET or an emergency service.
- Reset when the application is fully reloaded.

This is different from `/admin/users/pending`: account approval and rejection
on that page are real backend operations and persist in PostgreSQL.

### Synthetic research view (research only, nothing promoted)

`/research` is a lecturer-facing, read-only view of the synthetic scenario study
documented in [docs/SYNTHETIC_V3_RESULTS.md](SYNTHETIC_V3_RESULTS.md). It calls
`GET /api/synthetic/research/{info,frame,storms,series}`, which serve published
research bundles from `SYNTHETIC_RESEARCH_DIR` (default
`ml/artifacts/synthetic/v3`) with no database writes and no path into alert
creation.

- Scenario selector lists the controlled, realistic, and stress scenarios;
  unpublished scenarios are disabled.
- The frame table shows all 12 monitored locations for a chosen hour: simulated
  weather, provisional probability and risk band, and (display-only) evaluation
  labels under `Ground truth …` column titles.
- Storm replay lists simulated storms and, per selected location, a timeline of
  alarm episodes against onsets.

Ground truth is served only from a separate `research_truth.parquet` under the
`ground_truth` key with `research_view_only: true`; the scorer never receives
labels. Every response carries `source_type: synthetic` and a
research-demonstration notice. This page is not a Fiji MET forecast, not an
operational dashboard, and shares nothing with the deployed V1 serving path
(`/api/synthetic/*`), the alert demo, or notifications. The badge on the page
reads **Synthetic Data — Research Demonstration**.

## Map tiles and internet access

Leaflet and React Leaflet render the map, while the background tiles come from:

```text
https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png
```

An internet connection and access to the OpenStreetMap tile host are therefore
needed to see the basemap. The prototype location records are local and are not
downloaded from OpenStreetMap. If tile requests are blocked or offline, the
search, location list, risk records, and detail cards can still load, but the
map background may be blank.

For deployment, review the OpenStreetMap tile usage policy and choose a tile
provider appropriate for expected traffic. Do not treat the public development
tile service as an unlimited production map backend.

## Prerequisites

- Python 3.11 or newer
- PostgreSQL
- Node.js `^20.19.0` or `>=22.12.0`, as required by the installed Vite version
- Internet access for dependency installation and OpenStreetMap tiles

PostgreSQL is required for real registration, login, session restoration, and
account review. PostGIS is not required by the current authentication or
prototype UI. The public weather map can display its local records without a
backend, although its basemap still needs internet access.

## Backend setup

From the project root, create and activate a virtual environment if one does
not already exist:

```bash
python -m venv backend/.venv
source backend/.venv/bin/activate
```

Install the backend dependencies:

```bash
cd backend
python -m pip install -r requirements.txt
```

Create a local PostgreSQL user and database using a PostgreSQL administrator.
For example:

```sql
CREATE USER flood_app WITH PASSWORD 'replace-with-a-strong-password';
CREATE DATABASE fiji_flood_risk OWNER flood_app;
```

Copy the environment example only if `.env` does not already exist:

```bash
cp .env.example .env
```

Configure `backend/.env`:

```dotenv
DATABASE_URL=postgresql+psycopg://flood_app:your-password@localhost:5432/fiji_flood_risk
JWT_SECRET_KEY=replace-with-a-unique-random-secret-at-least-32-characters-long
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

Generate a development JWT secret with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Never commit `backend/.env`, and never expose the database URL or JWT secret to
the React application.

Initialize a new database schema:

```bash
python -m app.db.init_db
```

This uses SQLAlchemy `create_all`. It creates missing initial objects but is not
a migration system. Alembic should be added before future deployed schema
changes.

Start FastAPI from `backend`:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Useful URLs:

- Health check: <http://127.0.0.1:8000/api/health>
- Swagger UI: <http://127.0.0.1:8000/docs>

## Frontend setup

In a second terminal, from the project root:

```bash
cd frontend
npm install
```

The mapping feature added these packages to `frontend/package.json`:

```text
leaflet ^1.9.4
react-leaflet ^5.0.0
@types/leaflet ^1.9.22 (development dependency)
```

On a fresh clone, the single `npm install` command above installs their locked
versions. To add them manually to another checkout, use:

```bash
npm install leaflet@^1.9.4 react-leaflet@^5.0.0
npm install --save-dev @types/leaflet@^1.9.22
```

If `frontend/.env` does not exist, copy the example:

```bash
cp .env.example .env
```

Do not overwrite an existing `frontend/.env`. Its development setting is:

```dotenv
VITE_API_URL=http://127.0.0.1:8000
```

`VITE_` values are included in public browser code. Never put a JWT secret,
database password, or other server secret in a `VITE_` variable.

Start Vite on a backend-approved CORS origin:

```bash
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open <http://127.0.0.1:5173>. The backend currently permits browser requests
only from `http://localhost:5173` and `http://127.0.0.1:5173`. If the port or
host changes, update CORS deliberately rather than disabling it broadly.

## Bootstrap the first approved MET administrator

There is intentionally no public endpoint that creates an approved admin.

1. Open `/register` and request a `MET_ADMIN` account, or register through the
   API.
2. Confirm that the new record is `PENDING`.
3. Connect to the local database using a privileged PostgreSQL account.
4. Approve only the intended account in a transaction:

```sql
BEGIN;

UPDATE users
SET status = 'APPROVED'::account_status
WHERE email = 'admin@example.com'
  AND role = 'MET_ADMIN'::user_role
  AND status = 'PENDING'::account_status
  AND is_active IS TRUE
RETURNING id, name, email, role, status, is_active;
```

Verify that exactly one intended account is returned, then run `COMMIT;`. If
the result is empty or unexpected, run `ROLLBACK;`. The approved administrator
can then log in and manage later account requests through the live account page.

## Suggested demonstration walkthrough

1. Start PostgreSQL, FastAPI, and Vite.
2. Open `/weather-map` while signed out. Point out the **Demo data** badge,
   search for `Nadi`, select a risk filter, and inspect its detail panel.
3. Register a community account. Show that the response leads to the pending
   approval screen and that the account cannot log in yet.
4. Bootstrap the first MET administrator if the development database does not
   already contain one, then sign in as that administrator.
5. Show `/admin/dashboard`. Explain that its operational metrics, alerts, and
   predictions are derived from local prototype data.
6. Open `/admin/alerts`, filter to pending alerts, select one, and approve or
   reject it. Explain that this action is browser-only and resets on reload.
7. Open `/admin/users/pending`. Point out the **Live auth API** badge and approve
   the community account. This action is persisted in PostgreSQL.
8. Log out, log in as the newly approved community user, and show the protected
   `/dashboard` identity data returned by `/api/auth/me`.
9. Return to `/weather-map` and reiterate that it is a public prototype view,
   not live weather or warning information.

The most important demonstration distinction is:

```text
Account approve/reject = live backend + PostgreSQL
Alert approve/reject/suppress = local UI simulation only
```

## Validation and build commands

Run backend tests from `backend` with the virtual environment active:

```bash
python -m pytest -q
```

The backend tests use an isolated in-memory SQLite database, so PostgreSQL is
not required for that test command. PostgreSQL is still required for manual
end-to-end authentication testing.

Run frontend static validation and a production build from `frontend`:

```bash
npm run lint
npm run build
```

Optionally inspect the production build locally:

```bash
npm run preview
```

There is no automated frontend component or end-to-end test suite yet. The
current frontend gates are TypeScript/build validation, linting, and manual
browser testing.

## Future backend API gaps

The prototype UI should not be considered complete until real, authorized APIs
and persistence replace the local data provider. Future work includes:

The [Alert System backend](ALERT_SYSTEM.md) now implements persisted drafts,
administrator review, suppression, and public approved alerts. The frontend
continues to use its local demo provider; connecting that page remains pending.

| Capability | Current prototype | Future backend need |
| --- | --- | --- |
| Weather observations | Hard-coded local records | Ingestion and read API with source/update metadata |
| Monitored locations | Hard-coded coordinates | PostgreSQL/PostGIS location model and query API |
| Flood predictions | Illustrative labels/confidence | Model pipeline, persisted runs, horizons, and read API |
| Official warnings | Illustrative strings | Authoritative warning source and clearly separated API |
| Dashboard metrics | Calculated in the browser | Authorized aggregate/summary endpoint |
| Alert listing | Local array | Backend list/detail endpoints implemented; frontend connection pending |
| Alert review actions | In-memory state change | Backend transitions, `MET_ADMIN` authorization, and validation implemented; frontend connection pending |
| Alert delivery | Not implemented | Audience/channel delivery, retries, and delivery status |
| Operational audit | Not shown in frontend | Backend actor/time/reason fields implemented; complete immutable history remains pending |

The existing `GET /api/risk/{location}` route in `backend/app/main.py` returns a
fixed placeholder response. The frontend prototype does not call it, and it is
not a substitute for the future prediction APIs.

The implemented alert routes and proposed remaining frontend contracts include:

```text
GET   /api/locations
GET   /api/locations/{location_id}/conditions
GET   /api/predictions/recent
GET   /api/alerts/active

GET   /api/admin/dashboard/summary
GET   /api/admin/alerts
GET   /api/admin/alerts/{alert_id}
PATCH /api/admin/alerts/{alert_id}/approve
PATCH /api/admin/alerts/{alert_id}/reject
PATCH /api/admin/alerts/{alert_id}/suppress
```

The alert routes in this list are implemented; the other domain routes remain
proposals. Alert administrator endpoints reuse the backend's approved-and-active
`MET_ADMIN` dependency and use a separate alert status enum from account approval.

When the real APIs are added:

- Keep AI recommendations separate from authoritative official warnings.
- Enforce all MET-admin permissions in FastAPI, not only React.
- Record who approved, rejected, suppressed, or published an alert.
- Add Alembic before evolving deployed database tables.
- Add frontend unit/integration tests and browser-level end-to-end tests.
- Define offline, stale-data, loading, and partial-failure behavior.

## Source map

```text
frontend/src/
├── App.tsx                            Route composition
├── api/                               Live FastAPI client calls
├── auth/                              JWT/user state and route guards
├── components/layout/                 Workspace shell, sidebar, badges
├── components/map/                    Leaflet map and location details
├── data/prototypeData.ts              Illustrative local records
├── prototype/PrototypeDataProvider.tsx Shared in-memory demo state
├── pages/AdminDashboardPage.tsx       Demo operational summary
├── pages/AlertsDashboardPage.tsx      Demo alert workflow
├── pages/WeatherMapPage.tsx           Public demo map
├── pages/AdminUsersPage.tsx            Live account review
└── pages/DashboardPage.tsx             Live current-user overview
```
