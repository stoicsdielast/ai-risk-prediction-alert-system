# FloodWatch Fiji Prototype Presentation Handbook

**Project:** Flood Risk Prediction and Community Alert System – AI Powered for
Fiji MET

**Purpose:** Team preparation, demonstration, technical defence, and lecturer
questions

**Implementation snapshot:** 3 September 2026

This handbook explains the whole current prototype: what problem it addresses,
what is genuinely implemented, how the React frontend communicates with the
FastAPI backend and PostgreSQL, how authentication and authorization work, what
security and privacy controls exist, how to run and demonstrate it, and how it
could be deployed to AWS later.

Every team member should understand the **prototype boundary** below before
presenting anything.

> **The account system is live. The flood-domain system is still a prototype.**
> Registration, login, JWT validation, current-user retrieval, and user-account
> approval/rejection use FastAPI and PostgreSQL. Weather observations, flood-risk
> predictions, dashboard figures, official-warning examples, and flood-alert
> review actions are illustrative frontend data and are not operational Fiji MET
> information.

This is a university prototype intended to demonstrate a system design. It is
not a deployed emergency-warning service and must not be used for safety
decisions.

Because official-looking names, logos, and warning language can imply
endorsement, any public deployment or external presentation should confirm
branding permission and keep the university-prototype disclaimer prominent.

---

## 1. Fast briefing for every team member

### One-sentence description

FloodWatch Fiji is a prototype web platform that brings flood-risk information,
weather context, community alerts, and controlled Fiji MET administration into
one interface, with a working secure account and approval foundation.

### Thirty-second explanation

Fiji communities need clear and timely information when heavy rainfall may
create flood risk. Our prototype shows how community users could view risk
information while approved Fiji MET administrators review accounts and, in a
future operational version, assess AI-supported predictions and alerts. React
provides the interface, FastAPI provides the API and security rules, PostgreSQL
stores users, Argon2 protects passwords, and JWT Bearer tokens authenticate
protected requests. The current flood and weather screens intentionally use
labelled demo data; the live completed milestone is authentication and account
administration.

### The five facts nobody should get wrong

1. **Authentication is real:** users are stored in PostgreSQL and passwords are
   hashed with Argon2.
2. **Approval is real for user accounts:** pending users can be approved or
   rejected by an approved `MET_ADMIN`, and that change persists in PostgreSQL.
3. **Flood-alert approval is not yet real:** alert review on `/admin/alerts`
   changes React memory only and resets after a page reload.
4. **AI and weather are not connected yet:** the displayed locations,
   measurements, risk levels, confidence values, predictions, and warning text
   come from local prototype data.
5. **The backend is the security boundary:** hiding an admin page in React is
   useful for navigation, but real admin API access is decided again by FastAPI
   using the current PostgreSQL user record.

### Short answer when asked, “What have you completed?”

> We have completed a responsive Fiji MET-branded frontend prototype and an
> end-to-end authentication and user-approval vertical slice. The vertical slice
> includes React forms and route guards, FastAPI validation and authorization,
> Argon2 password hashing, JWT access tokens, and PostgreSQL persistence. The
> weather, AI prediction, operational dashboard, and flood-alert screens prove
> the intended user experience but currently use clearly labelled illustrative
> data.

---

## 2. Problem, proposed solution, and users

### Problem being explored

Flood-risk information may come from several sources and can be difficult to
present consistently to both operational staff and communities. A useful system
must separate machine-generated decision support from official warnings, ensure
that administrative actions are restricted to authorized staff, and present
information clearly on desktop and mobile devices.

### Proposed complete-system idea

The intended complete system would:

- ingest trustworthy weather, rainfall, river, and geographic data;
- use a validated model to estimate flood risk for supported locations;
- show risk spatially on a map;
- help qualified MET staff review predictions and proposed alerts;
- publish only reviewed, approved public warnings;
- notify relevant communities through appropriate channels;
- preserve an audit trail of predictions, reviews, approvals, and delivery;
- protect user and operational data throughout the process.

### Current prototype objectives

The current milestone demonstrates that the team can:

- create a usable public landing and weather-map experience;
- register and persist accounts;
- protect credentials correctly;
- enforce an approval lifecycle;
- authenticate approved users using JWTs;
- distinguish community and administrator access;
- let real administrators approve or reject account requests;
- prototype future weather, prediction, map, and alert workflows without
  pretending that their data is operational.

### Intended users

| User | Current prototype capability | Future complete-system capability |
| --- | --- | --- |
| Public visitor | View landing page and public prototype map | View current public risk and official alerts |
| Community user | Register, log in after approval, view account overview and public map | Receive relevant alerts and localized safety information |
| MET administrator | Review real account requests; view demo operational screens | Review data, predictions, alerts, users, and audit history |
| Project/operations team | Run, test, and inspect the prototype | Operate, monitor, support, and improve the service |

### Human-in-the-loop principle

The AI concept is **decision support**, not autonomous authority. A future model
may recommend a risk level or alert, but an appropriate authorized person should
review the evidence before information is represented as an official warning.
The current UI reinforces this by showing AI prediction and official-warning
information separately.

---

## 3. What is live, what is simulated, and what is future work

### Current implementation truth table

| Area | Source | Persists? | Honest status |
| --- | --- | --- | --- |
| Landing and login UI | React | Static UI | Implemented |
| Registration | React → FastAPI → PostgreSQL | Yes | Implemented |
| Password hashing | `pwdlib` recommended Argon2 | Hash persists | Implemented |
| Login and JWT | FastAPI + PyJWT | Token is per browser tab | Implemented |
| `/api/auth/me` | FastAPI + PostgreSQL | Reads current account | Implemented |
| Role/status checks | FastAPI dependencies + PostgreSQL | Yes | Implemented |
| User-account pending list | FastAPI + PostgreSQL | Yes | Implemented |
| User-account approve/reject | FastAPI + PostgreSQL | Yes | Implemented |
| Community overview identity | Live `/me` result | Current session | Implemented |
| Public interactive map mechanics | Leaflet/React Leaflet | UI state only | Implemented UI |
| OpenStreetMap basemap | External public tile service | External | Live tiles, not our data |
| Location/weather records | `frontend/src/data/prototypeData.ts` | No | Illustrative demo data |
| Flood-risk values | `prototypeData.ts` | No | Illustrative demo data |
| AI confidence/predictions | `prototypeData.ts` | No | Illustrative demo data |
| “Official warning” examples | `prototypeData.ts` | No | Illustrative text only |
| Admin operational metrics | Derived in the browser | No | Demo dashboard |
| Flood-alert approve/reject/suppress | React context | Until reload only | Demo workflow |
| `GET /api/risk/{location}` | Fixed FastAPI response | No | Placeholder; not used by frontend |
| PostGIS spatial storage/queries | None | No | Not implemented |
| Weather API ingestion | None | No | Not implemented |
| Trained AI model/inference | None | No | Not implemented |
| Notification delivery | None | No | Not implemented |
| Reporting/audit module | None | No | Not implemented |
| AWS deployment | No infrastructure files | No | Proposed only |

### Exact prototype data currently displayed

The local dataset contains:

- eight locations: Suva, Nadi, Lautoka, Ba, Sigatoka, Nausori, Labasa, and
  Savusavu;
- three divisions: Central, Western, and Northern;
- two `LOW`, two `MODERATE`, three `HIGH`, and one `VERY_HIGH` risk examples;
- five example alerts: one pending, two approved, one suppressed, and one
  rejected;
- eight derived example prediction records;
- four locations with illustrative official-warning text.

These values are deliberately useful for demonstrating search, filtering,
states, and visual hierarchy. They are not current observations.

The demo timestamps are calculated relative to the time the frontend module
loads, so records can look recently updated after every refresh. This improves
the visual demonstration but increases the need for a prominent demo label; it
is not evidence of polling or a live feed.

### The most important comparison in the demo

| Action | Real or demo? | Where it goes |
| --- | --- | --- |
| Approve a **user account** on `/admin/users/pending` | Real | FastAPI and PostgreSQL |
| Approve a **flood alert** on `/admin/alerts` | Demo | React memory only |

Say this distinction out loud during the presentation.

---

## 4. System architecture

### Current architecture

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Browser                                                             │
│                                                                     │
│ React + TypeScript + Vite                                           │
│ ├── React Router                                                    │
│ ├── AuthProvider: JWT/current user                                  │
│ ├── PrototypeDataProvider: local flood-domain demo state            │
│ ├── Landing, login, registration                                    │
│ ├── Community and MET-admin workspaces                              │
│ └── Leaflet map                                                     │
└───────────────┬─────────────────────────────┬───────────────────────┘
                │ HTTP/JSON                   │ HTTPS tile requests
                │ Bearer JWT                  ▼
                │                       OpenStreetMap tiles
                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ FastAPI                                                             │
│ ├── Pydantic request validation and safe responses                  │
│ ├── API routes                                                      │
│ ├── authentication/admin services                                   │
│ ├── Argon2 password hashing                                         │
│ ├── JWT signing/validation                                          │
│ └── current-user and MET-admin dependencies                         │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ SQLAlchemy / psycopg
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│ PostgreSQL                                                          │
│ └── users table, role/status enums, Argon2 password hashes          │
└─────────────────────────────────────────────────────────────────────┘
```

### Why there are two React providers

`main.tsx` composes the application in this order:

```text
React StrictMode
  └── BrowserRouter
      └── AuthProvider
          └── PrototypeDataProvider
              └── App routes
```

- `AuthProvider` owns real identity state: access token, current user, loading,
  session error, login, logout, and retry.
- `PrototypeDataProvider` owns local demonstration state: locations,
  predictions, alerts, and simulated alert status changes.

Keeping these separate prevents demo flood data from being confused with live
authentication data and makes future API replacement clearer.

### Responsibility by layer

| Layer | Responsibility | Must not be trusted for |
| --- | --- | --- |
| React UI | Forms, feedback, navigation, responsive presentation | Final authorization decisions |
| Frontend API client | Build HTTP requests, attach JWT, normalize safe errors | Validating JWTs or database roles |
| FastAPI routes | HTTP contract and status-code mapping | Direct low-level persistence logic |
| Service layer | Registration, login, and transition business rules | UI presentation |
| Dependencies | Database session injection, current user, admin requirement | Client-provided claims |
| Pydantic schemas | Input validation and output filtering | Database persistence by themselves |
| SQLAlchemy models/session | Database mapping and transactions | Browser state |
| PostgreSQL | Durable user records, uniqueness, enum constraints | Rendering UI |

---

## 5. Why these technologies were selected

| Technology | Role in this project | Reasonable defence in presentation |
| --- | --- | --- |
| React | Component-based browser UI | Reusable pages/components and clear state-driven rendering |
| TypeScript | Static types for frontend data | Catches many mismatched API/data shapes before runtime |
| Vite | Frontend development/build tool | Fast local feedback and a small production build workflow |
| React Router | URL and access-flow routing | Clean public, protected, and admin route composition |
| Leaflet + React Leaflet | Interactive map UI | Established open-source map interaction without a large proprietary SDK |
| FastAPI | Python web API | Type hints, dependency injection, validation, async-ready framework, and generated OpenAPI docs |
| Pydantic | Request/config validation | Rejects invalid data early and defines safe response shapes |
| SQLAlchemy | Database ORM and sessions | Structured, parameterized database access and testable session injection |
| PostgreSQL | Durable relational storage | Strong constraints, transactions, concurrency, and future PostGIS path |
| psycopg 3 | PostgreSQL driver | Connects SQLAlchemy to PostgreSQL |
| `pwdlib` + Argon2 | Password hashing | Modern salted, deliberately expensive, one-way password verification |
| PyJWT | JWT creation and validation | Standard signed access-token implementation with expiration |
| Pytest | Backend automated tests | Fast repeatable evidence for business and security rules |

### PostgreSQL versus PostGIS

PostgreSQL is used now for authentication. PostGIS is a PostgreSQL extension
that adds geographic types, indexes, and spatial functions. The current map
coordinates are local TypeScript data, so there are no PostGIS tables or
queries yet. PostGIS becomes valuable later for catchments, river networks,
location proximity, risk zones, and intersection queries.

---

## 6. Repository guide

```text
fiji-flood-risk-system/
├── README.md
├── docs/
│   ├── AUTHENTICATION_WORKFLOW.md  Detailed auth explanation
│   ├── PROTOTYPE_UI.md             Detailed UI/demo explanation
│   └── PRESENTATION_HANDBOOK.md    This team handbook
├── backend/
│   ├── .env.example               Safe configuration template
│   ├── requirements.txt
│   ├── README.md                   Backend setup/API reference
│   ├── app/
│   │   ├── api/
│   │   │   ├── dependencies.py    Current user and MET-admin checks
│   │   │   └── routes/
│   │   │       ├── auth.py        Register, login, and /me
│   │   │       └── admin.py       Pending, approve, and reject
│   │   ├── core/
│   │   │   ├── config.py          Environment-backed settings
│   │   │   └── security.py        Argon2 and JWT helpers
│   │   ├── db/
│   │   │   ├── base.py            SQLAlchemy declarative base
│   │   │   ├── init_db.py         Initial create_all schema command
│   │   │   └── session.py         Engine/session dependency
│   │   ├── models/user.py         User table and enums
│   │   ├── schemas/               Validated request/response models
│   │   ├── services/              Auth and admin business rules
│   │   └── main.py                FastAPI app, CORS, routers, placeholders
│   └── tests/                      33 backend auth/admin tests
└── frontend/
    ├── .env.example               Public API base URL template
    ├── public/fijimetlogo.svg      Fiji MET logo served directly by Vite
    ├── src/
    │   ├── api/                    Typed fetch wrappers
    │   ├── auth/                   Provider, context, and route guards
    │   ├── components/             Shared UI, layout, map, and pills
    │   ├── data/prototypeData.ts   Illustrative domain records
    │   ├── pages/                  Public/community/admin pages
    │   ├── prototype/              In-memory demo provider
    │   ├── types/                  Auth and prototype TypeScript types
    │   ├── App.tsx                 Route tree
    │   └── main.tsx                React composition entrypoint
    └── package.json
```

The empty older files under `backend/app/auth/` are not the canonical route or
schema implementation. `backend/app/auth/security.py` only re-exports the newer
security helpers for compatibility. The active code is under `app/api`,
`app/schemas`, and `app/core`.

---

## 7. Frontend explained

### Routes, access, and data source

| Frontend route | Who can open it? | Main source |
| --- | --- | --- |
| `/` | Signed-out visitor | Static React landing page |
| `/login` | Signed-out visitor | Live auth API |
| `/register` | Signed-out visitor | Live registration API |
| `/registration-submitted` | Signed-out visitor | Navigation state after registration |
| `/weather-map` | Public | Local demo records + external OSM tiles |
| `/dashboard` | Authenticated user | Live current-user data plus explanatory UI |
| `/admin/dashboard` | `MET_ADMIN` in frontend navigation | Local prototype metrics |
| `/admin/alerts` | `MET_ADMIN` in frontend navigation | Local in-memory alert workflow |
| `/admin/users/pending` | Approved, active `MET_ADMIN` | Live protected API/PostgreSQL |
| `*` | Anyone | Not-found page |

Authenticated users who visit `/`, `/login`, or `/register` are redirected by
role. A MET administrator goes to `/admin/dashboard`; a community user goes to
`/dashboard`.

An unauthenticated user who tries a protected path is sent to `/login` with the
requested path saved. After successful login, the frontend returns to that path.
The role guard still redirects a community user away from an admin path.

### Landing page

The landing page uses the real `/fijimetlogo.svg` asset, Fiji MET navy
`#2d3055`, clear calls to action, a static observation-to-alert workflow, and
feature cards. “Weather Map” opens the public prototype map. “Alerts” in the
landing header scrolls to feature information; it is not a public live-alert
feed.

### Login page

The responsive login page provides:

- visible email/password labels;
- a password show/hide control;
- submit-only spinner and “Signing in…” state;
- generic invalid-credential feedback;
- distinct pending, rejected, and inactive account feedback;
- desktop two-panel branding and a smaller mobile layout.

The complete page is not replaced during an ordinary login. A full branded
loader is shown only while a stored JWT is actually being checked on a guarded
route.

### Registration page

The user enters name, email, password, password confirmation, and a requested
role. The browser checks password confirmation for convenience, but FastAPI is
still responsible for authoritative validation. A successful registration
navigates to the pending-approval explanation page.

The UI permits a `MET_ADMIN` **request**. It does not grant access: the backend
forces every new account to `PENDING`.

### Community overview

`/dashboard` shows live name, email, role, approval state, and protected-session
information returned by `/api/auth/me`. It also links to the public prototype
map and clearly describes which modules are integrated versus simulated.

### Public map

The map supports real user interactions:

- search by location or division;
- filter by risk level;
- choose a marker or location card;
- inspect condition, temperature, rainfall, humidity, and wind examples;
- view AI label, confidence meter, and explanation;
- view official-warning example separately;
- handle empty search/filter results.

The interaction is real; the underlying weather/risk content is local demo
data. The basemap requires internet access to OpenStreetMap tile servers. If
tiles fail, the local list and detail data can still render.

### MET operational dashboard

The admin dashboard derives its initial values from local data:

- 8 monitored locations;
- 3 represented divisions;
- 2 approved/active example alerts;
- 1 pending example alert;
- 4 high or very-high risk locations.

Recent alerts, recent predictions, confidence values, and the quick-action link
are prototype presentation features, not backend results.

### Flood-alert workflow

`/admin/alerts` supports searching, status filtering, selecting an alert, and
confirming approve/reject/suppress actions. It deliberately waits about 450 ms
to simulate an asynchronous action. The change is shared while navigating in
the same SPA session but resets on full reload because no alert API/database
exists.

### Real user-account review

`/admin/users/pending` is different: it fetches PostgreSQL-backed pending users
and sends real protected PATCH requests. Approved/rejected accounts disappear
from the pending list, and the state remains after reload.

### Frontend API connection

The browser reads:

```dotenv
VITE_API_URL=http://127.0.0.1:8000
```

`api/client.ts` combines that base with paths such as `/api/auth/login`, sets
JSON headers, and adds this header when a token is supplied:

```http
Authorization: Bearer <access-token>
```

It safely converts FastAPI string or validation-array errors into frontend
messages. A network failure becomes a controlled “Cannot reach the server”
message.

Never put `DATABASE_URL`, `JWT_SECRET_KEY`, passwords, or other secrets in a
`VITE_` variable. Vite embeds those variables into browser code during build.

---

## 8. Backend explained

### API inventory

| Method | Endpoint | Access | Current behaviour |
| --- | --- | --- | --- |
| `GET` | `/` | Public | API-running message |
| `GET` | `/api/health` | Public | `{"status":"healthy"}` |
| `GET` | `/api/risk/{location}` | Public | Fixed placeholder `HIGH`, `0.82`; not AI |
| `POST` | `/api/auth/register` | Public | Validate, hash, store pending user |
| `POST` | `/api/auth/login` | Public | Verify approved active user, return JWT |
| `GET` | `/api/auth/me` | Bearer JWT | Return current safe user record |
| `GET` | `/api/admin/users/pending` | Approved active `MET_ADMIN` | List pending users |
| `PATCH` | `/api/admin/users/{id}/approve` | Approved active `MET_ADMIN` | `PENDING → APPROVED` |
| `PATCH` | `/api/admin/users/{id}/reject` | Approved active `MET_ADMIN` | `PENDING → REJECTED` |

FastAPI also generates development documentation at `/docs` and an OpenAPI
document at `/openapi.json`.

`/api/health` is currently a basic application liveness response. It does not
query PostgreSQL, so it can return “healthy” while database-dependent auth is
unavailable. Production should separate a cheap liveness check from a
database-backed readiness check.

### Backend request path

```text
HTTP request
  ↓
Pydantic schema validation
  ↓
FastAPI route: request/response contract
  ↓
Service: business rules
  ↓
Injected SQLAlchemy Session
  ↓
PostgreSQL transaction
  ↓
Pydantic safe response model
  ↓
JSON response
```

### Dependency injection

`get_db()` creates a SQLAlchemy session for a request, yields it to the route,
and closes it afterward. Routes declare `db: Session = Depends(get_db)` instead
of constructing global ad-hoc sessions. This makes cleanup reliable and lets
tests substitute an isolated test session.

`get_current_user()` and `require_met_admin()` are also dependencies. This
centralizes protected-request logic instead of repeating it in every route.

### Error handling

Known conditions are translated into controlled HTTP responses. For example:

- duplicate email → `409 Account already exists`;
- invalid body → `422` validation details;
- invalid credentials → `401 Invalid credentials`;
- pending/rejected/inactive account → appropriate `403`;
- missing account → `404 User not found`;
- repeated terminal transition → `409`;
- unexpected database problem → generic `500` message.

The client does not receive raw SQL errors, connection details, stack traces,
password hashes, or server secrets.

### Development CORS

The backend currently permits browser origins:

```text
http://localhost:5173
http://127.0.0.1:5173
```

That is a development allowlist. CORS tells browsers which frontend origins may
call the API; it is **not** authentication or authorization. Production origins
must be configurable and restricted to the deployed HTTPS frontend.

---

## 9. Database design

### Current `users` table

| Column | Type/constraint concept | Purpose |
| --- | --- | --- |
| `id` | Integer primary key | Stable internal user ID |
| `name` | String up to 255, required | Display name |
| `email` | String up to 320, unique/indexed, required | Normalized login identifier |
| `hashed_password` | String up to 255, required | Argon2 verifier, never plaintext |
| `role` | `user_role` enum | `COMMUNITY` or `MET_ADMIN` |
| `status` | `account_status` enum | `PENDING`, `APPROVED`, or `REJECTED` |
| `is_active` | Boolean, defaults true | Independent account enable/disable switch |

Role, status, and activity answer different questions:

```text
role       → What may this approved user do?
status     → Has this account request been approved?
is_active  → Is this account currently enabled?
```

### Defaults

Application and database model defaults are:

```text
role      = COMMUNITY
status    = PENDING
is_active = true
```

Registration explicitly forces `PENDING` and active. Requesting `MET_ADMIN`
does not bypass approval.

### Current schema management limitation

The project runs:

```bash
python -m app.db.init_db
```

This calls SQLAlchemy `Base.metadata.create_all()` and is suitable for creating
the initial development schema. Although `alembic` is present in
`requirements.txt`, there is no `alembic.ini`, migration environment, or
revision directory. Therefore:

- do not claim that migrations are implemented;
- do not run or present `alembic upgrade head`;
- remember that `create_all()` creates missing objects but does not safely
  evolve an existing table when models change;
- introduce configured, reviewed Alembic revisions before deployment.

### Test database

Backend tests override `get_db` and use isolated in-memory SQLite. They do not
write demo users to PostgreSQL and destroy the schema after each fixture. This
makes unit/integration-style API tests quick, but it does not test PostgreSQL
enum behaviour, psycopg diagnostic shapes, or real PostgreSQL row locks.

---

## 10. Authentication from end to end

### 10.1 Registration

```text
User completes React form
  ↓ POST /api/auth/register
Pydantic validates and normalizes
  ├── name trimmed, 1–255, not blank
  ├── valid email, lowercase
  ├── password 8–128 characters
  └── COMMUNITY or MET_ADMIN
  ↓
Service checks normalized email
  ↓
Argon2 creates salted one-way hash
  ↓
SQLAlchemy inserts PENDING, active user
  ↓
PostgreSQL unique constraint protects email race
  ↓
Safe response: id, name, email, role, status
```

Example request:

```json
{
  "name": "Demo Community User",
  "email": "community.demo@example.com",
  "password": "Use-A-Private-Demo-Password!",
  "role": "COMMUNITY"
}
```

Example response:

```json
{
  "id": 2,
  "name": "Demo Community User",
  "email": "community.demo@example.com",
  "role": "COMMUNITY",
  "status": "PENDING"
}
```

Passwords and hashes are not fields in the response model.

### 10.2 Why both a duplicate check and a database unique constraint exist

The first query gives a clear user-friendly conflict in the usual case. It is
not enough by itself because two requests could check simultaneously before
either inserts. The database uniqueness constraint is the authoritative race
protection. A recognized uniqueness error is mapped back to the same safe
`409 Account already exists` response.

### 10.3 Account approval

A new user cannot log in. An already approved MET administrator can list
pending accounts and transition exactly one from `PENDING` to `APPROVED` or
`REJECTED`.

The service uses a row-locking query (`SELECT ... FOR UPDATE`) and rejects
changes to an already terminal account. In PostgreSQL, this helps serialize two
administrators trying to review the same record. One succeeds; a later reviewer
should receive a controlled conflict.

There is currently no reversal, approval reason, reviewer ID, or approval time.
Those should become audit fields later.

### 10.4 Login

```text
React sends email + password
  ↓ POST /api/auth/login
Backend loads normalized email
  ↓
Argon2 verifies password
  ↓
Check is_active
  ↓
Check status == APPROVED
  ↓
Create expiring signed JWT
  ↓
React immediately calls GET /api/auth/me
  ↓
Only after /me succeeds, store token and user
  ↓
Navigate to requested or role-appropriate dashboard
```

Login outcomes:

| Condition | HTTP | Backend detail | Frontend presentation |
| --- | --- | --- | --- |
| Unknown email | `401` | `Invalid credentials` | Invalid email or password |
| Wrong password | `401` | `Invalid credentials` | Invalid email or password |
| Pending user with correct password | `403` | `Account approval pending` | Pending approval pill |
| Rejected user with correct password | `403` | `Account has been rejected` | Account rejected pill |
| Inactive approved user with correct password | `403` | `Account is inactive` | Account inactive pill |
| Approved active user | `200` | Access token | Continue to protected page |

The same `401` response for unknown email and wrong password avoids directly
confirming whether an email is registered. For an unknown email, the service
still verifies a dummy Argon2 hash to make request timing more similar.

### 10.5 JWT contents

The access token payload contains only:

```json
{
  "sub": "2",
  "exp": 1788312345
}
```

- `sub` is the stable user ID as a string.
- `exp` is the expiration time.
- the current default lifetime is 60 minutes.
- HS256 signs the token using the backend secret.

A JWT is **signed, not encrypted**. Anyone holding a token can decode its JSON
payload, which is why no password, password hash, email, role, account status,
database credential, or secret is placed inside it.

### 10.6 Current-user validation

For every live protected backend request:

```text
Authorization: Bearer <token>
  ↓
Validate Bearer scheme
  ↓
Validate HS256 signature + required sub/exp + expiration
  ↓
Require canonical positive integer user ID
  ↓
Load that user from PostgreSQL
  ↓
Recheck existence, status, and is_active
  ↓
For admin API: recheck role == MET_ADMIN
```

The backend does not rely only on data in the token. Therefore disabling,
rejecting, deleting, or changing the role of a user takes effect on their next
protected API request, even if their token has not expired.

### 10.7 Browser session behaviour

The JWT is stored under this key in `sessionStorage`:

```text
fiji-flood-access-token
```

`sessionStorage` normally survives reloads in the same tab and is cleared with
the tab/session. It is less persistent than `localStorage`, but JavaScript can
still read it, so preventing cross-site scripting remains essential.

On application startup with a stored token:

- `/me` success restores the current user;
- `/me` `401` or account-state `403` clears the invalid session;
- a temporary network/server problem retains the token and offers retry/logout;
- the branded loader lasts only while the actual request is pending.

Logout removes the token and user locally. There is no server revocation list
or refresh token yet. A copied token can remain cryptographically valid until
expiration, although a database account-state change can block it immediately.

### 10.8 Authentication versus authorization

- **Authentication:** “Who are you?” Email/password login and JWT establish a
  user identity.
- **Authorization:** “What are you allowed to do?” Current role, status, and
  activity determine access.

React route guards improve the user experience. FastAPI dependencies enforce
real permissions. Editing React state or sending `"role":"MET_ADMIN"` from a
browser cannot authorize an admin API request.

### 10.9 `401` versus `403`

- `401 Unauthorized` means a valid identity could not be established: missing,
  malformed, expired, incorrectly signed token, or wrong login credentials.
- `403 Forbidden` means the server understands the identity/credential context,
  but account state or permissions prohibit the operation.

---

## 11. First administrator and demo accounts

### Are dummy accounts automatically created?

**No.** There is no runtime seed script, startup hook, default password, dummy
administrator, or public auto-admin endpoint.

`admin@example.com` and other users in tests exist only inside temporary SQLite
fixtures. Documentation emails are examples only. They do not create records in
your PostgreSQL database.

### Safe first-admin development bootstrap

1. Start PostgreSQL, initialize the schema, and start FastAPI.
2. Register the intended admin normally with role `MET_ADMIN`.
3. It is safely created as `PENDING` with an Argon2 password hash.
4. Connect to the same database named in `DATABASE_URL` using an authorized
   local PostgreSQL account.
5. Run this narrow transaction, replacing the email with the exact normalized
   demo-admin email:

```sql
BEGIN;

UPDATE users
SET status = 'APPROVED'::account_status
WHERE email = 'met.admin.demo@example.com'
  AND role = 'MET_ADMIN'::user_role
  AND status = 'PENDING'::account_status
  AND is_active IS TRUE
RETURNING id, name, email, role, status, is_active;
```

Verify that `RETURNING` shows exactly one intended record. Then run:

```sql
COMMIT;
```

If it returns no row or the wrong row, run:

```sql
ROLLBACK;
```

After this one-time bootstrap, use the protected admin UI/API for later account
decisions. Never add an unauthenticated “make me admin” endpoint.

### Recommended presentation accounts

Prepare synthetic local records before the presentation:

| Account | Suggested state | Purpose |
| --- | --- | --- |
| `met.admin.demo@example.com` | `MET_ADMIN`, `APPROVED`, active | Demonstrate admin access |
| `community.pending.demo@example.com` | `COMMUNITY`, `PENDING`, active | Demonstrate denied login and real approval |
| `community.approved.demo@example.com` | `COMMUNITY`, `APPROVED`, active | Demonstrate community access |

Use passwords kept outside Git and presentation slides. Do not use real student,
staff, or community credentials.

---

## 12. Security review

### Controls already implemented

- Argon2 password hashing through `pwdlib.PasswordHash.recommended()`.
- Raw passwords are never stored or returned.
- Registration passwords use Pydantic `SecretStr` and length 8–128.
- Emails are validated, trimmed, and normalized to lowercase.
- Duplicate emails are protected by precheck and database uniqueness.
- Unknown-email and wrong-password login share a generic `401` response.
- Unknown-email verification uses a dummy Argon2 hash to reduce timing signals.
- JWT secret must come from backend configuration and be at least 32 characters.
- JWT algorithm is restricted to `HS256`.
- Tokens require `sub` and `exp`; expired/malformed tokens are rejected.
- JWT contains no role or personal/credential data beyond an internal user ID.
- Protected requests reload the current account from PostgreSQL.
- Admin authorization uses the current database role, not frontend input.
- Pending/rejected/inactive accounts cannot authenticate or continue protected
  API access.
- SQLAlchemy uses parameterized query construction rather than string-building
  SQL with user input.
- Database sessions close after requests; failed transactions roll back.
- Admin status updates request a database row lock and permit only pending
  transitions.
- Response schemas exclude passwords, hashes, and `is_active`.
- Unexpected database errors become generic API responses.
- Real `.env` files are ignored by Git; example files contain placeholders.
- Development CORS is an explicit origin list.
- Automated tests exercise registration, login, tokens, status changes, role
  denial, and account review.

### Threat and control matrix

| Threat | Current response | Remaining work before production |
| --- | --- | --- |
| Stolen database password hashes | Argon2 slows offline guessing | Strong password policy, monitoring, breach procedure |
| Account enumeration | Generic login `401` and dummy hash | Rate limits and monitoring |
| JWT tampering | HS256 signature, fixed algorithm, expiration | Managed secret rotation and key procedures |
| Frontend privilege manipulation | Backend reloads user and role | Apply same dependency to every future admin API |
| Duplicate registration race | Unique email constraint | PostgreSQL integration/concurrency tests |
| Concurrent account review | Row lock and pending-only transition | Audit reviewer/time/reason |
| SQL injection | SQLAlchemy expression queries | Secure review for any future raw SQL |
| Database failure disclosure | Safe generic API errors | Structured redacted logs and alerting |
| Token theft through XSS | React escaping; per-tab storage | CSP, dependency scanning, XSS testing; consider HttpOnly design |
| Cross-site request forgery | Bearer token is manually added, not browser cookie | Reassess and add CSRF protection if switching to cookies |
| Brute-force login | Argon2 cost only | Rate limit, lockout/risk controls, alerting |
| Long-lived copied token | 60-minute expiry and DB state recheck | Refresh/revocation design, token rotation |
| Secret exposure | `.env` ignored and config uses `SecretStr` | AWS Secrets Manager, IAM least privilege, rotation |
| Network interception | Local development only | HTTPS everywhere and TLS database connections |
| Unreviewed schema changes | Initial `create_all` only | Alembic migrations and deployment review |
| Demo risk mistaken for live warning | Demo labels and disclaimer | Strong watermarking, clearly fictional content, prevent public indexing |
| Fixed public `/api/risk` mistaken for AI | Source comment and known scope | Remove it or namespace/label it before public deployment |
| Public admin-role requests abused | Every request remains pending | Invite-only admin onboarding, staff verification, MFA |
| Shallow health check hides DB outage | Auth returns safe failures | Add separate database readiness check and monitoring |
| Branding implies official endorsement | University-prototype footer | Confirm permission and preserve prominent non-operational notice |

### Security limitations to state honestly

The prototype does **not** yet include:

- email verification;
- password reset/change;
- multifactor authentication;
- login rate limiting or account lockout;
- refresh tokens;
- server-side logout/revocation/denylist;
- JWT issuer, audience, issued-at, token ID, and key-rotation metadata;
- breached-password checking or complexity rules beyond length;
- security-event audit records;
- approval reviewer, reason, or timestamp;
- production HTTPS/TLS configuration;
- Content Security Policy;
- automated dependency/security scanning;
- PostgreSQL integration or penetration testing;
- environment-driven production CORS;
- configured database migrations.

These are limitations, not reasons to hide the current achievement. The correct
presentation framing is: “We built a sound authentication foundation for this
milestone and have identified the controls needed for production.”

### Why Argon2 hashes rather than encrypts passwords

The application never needs to recover a password. Encryption is reversible if
someone obtains the key. A password hash is one-way: login hashes/verifies the
candidate against the stored verifier. Argon2 is deliberately resource
intensive and salted, which makes bulk password guessing more expensive.

### Why CORS is not a security boundary

CORS is enforced by browsers. It does not stop a command-line client or another
server from sending requests. JWT validation and server-side authorization are
the controls that protect the API.

---

## 13. Privacy, data governance, and responsible use

### Current personal-data inventory

| Data | Classification | Why it exists | Exposure rule |
| --- | --- | --- | --- |
| Full name | Personal identifier | Account display/review | Current user and authorized account review only |
| Email | Personal identifier/login ID | Login and account contact identity | Never place in JWT; restrict admin listing |
| Password | Highly sensitive secret | Verify identity at registration/login | Process transiently; never store/log |
| Argon2 hash | Sensitive credential verifier | Password verification | Database/backend only; never API response |
| Role/status/activity | Account authorization metadata | Access decisions | Return only what UI needs |
| JWT | Sensitive bearer credential | Authenticate a browser session | Never log, show, or place in URL |
| Demo weather/risk data | Non-personal illustrative data | UI demonstration | Clearly label as non-operational |
| OSM tile request metadata | IP address, referrer, tile coordinates | Fetch external map background | Disclose third party and follow provider policy |
| Future server access logs | IP, route, status, timing may be recorded by hosting | Security and operations | Minimize, redact, restrict, and expire |

Future contact numbers, subscriptions, precise home locations, accessibility
needs, device identifiers, and notification delivery history could be more
sensitive than the current dataset and require a separate privacy design.

No analytics service, advertising tracker, application cookie, phone number,
home address, or browser GPS collection was found in the current code. This is
a description of the code snapshot, not a promise about future hosting logs or
third-party network services.

### Privacy principles the team should propose

1. **Purpose limitation:** collect data only for account access, risk service,
   and explicitly explained notification purposes.
2. **Data minimization:** do not collect date of birth, address, phone, precise
   location, or identity documents unless a justified feature needs them.
3. **Transparency:** publish a plain-language notice describing data, purpose,
   recipients, retention, and contact channel.
4. **Access control:** use least privilege; community users should never see
   pending-user lists or internal operational information.
5. **Accuracy:** let authorized processes correct account/contact information;
   label prediction uncertainty and observation timestamps.
6. **Retention:** define how long pending/rejected accounts, logs, alerts,
   notification records, and backups remain; delete or anonymize when no longer
   needed.
7. **Security:** HTTPS, encryption at rest, managed secrets, backups, monitoring,
   vulnerability management, and incident response.
8. **Accountability:** audit sensitive administrative actions with reviewer,
   time, decision, and reason.
9. **User rights/processes:** define verified ways to request access,
   correction, deletion, or support where applicable.
10. **Legal/organizational review:** before operational use, confirm current Fiji
    legal requirements and Fiji MET/university policies with an authorized
    privacy or legal stakeholder. Do not claim legal compliance based only on
    this prototype.

### Logging rules

Safe production logs may record request ID, route, status, timestamp, duration,
and internal user ID where justified. They should not record:

- raw passwords;
- `Authorization` headers or JWTs;
- password hashes;
- complete database URLs;
- JWT secrets;
- unnecessary request bodies or personal data.

### Safety and AI responsibility

- Never label a prediction as an official warning without an authorized review
  process.
- Display source, age, confidence, and limitations of data.
- Evaluate model performance by region, season, event type, and community—not
  only one overall accuracy number.
- Measure false negatives because missed floods can be dangerous, and false
  positives because repeated false alarms can reduce trust.
- Test data gaps, sensor failure, network loss, and model drift.
- Provide a manual override and documented operational responsibility.
- Design for low bandwidth, mobile screens, accessibility, and clear language.
- Preserve the authoritative Fiji MET/emergency channel when the system is
  unavailable.

---

## 14. Local setup and complete runbook

### Prerequisites

- Python 3.11 or newer;
- Node.js and npm;
- PostgreSQL;
- internet access if OpenStreetMap tiles must display;
- a PostgreSQL role allowed to create the table and enum types.

PostgreSQL is required for end-to-end registration, login, `/me`, and account
review. The landing page and local prototype data can render without it, but
auth requests will fail. PostGIS is not required for the current milestone.

### 14.1 Create a backend virtual environment

From the project root:

```bash
python -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
```

### 14.2 Create PostgreSQL database/user

One development example, run from an authorized PostgreSQL session:

```sql
CREATE USER flood_app WITH PASSWORD 'replace-with-a-strong-local-password';
CREATE DATABASE floodrisk OWNER flood_app;
```

If the database exists with another owner, grant only the permissions the
application needs. The final database name must exactly match `DATABASE_URL`.

### 14.3 Configure backend environment

From `backend`, copy the safe template only if `.env` does not already exist:

```bash
cd backend
test -f .env || cp .env.example .env
```

Set real local values in `backend/.env`:

```dotenv
DATABASE_URL=postgresql+psycopg://flood_app:YOUR_URL_ENCODED_PASSWORD@127.0.0.1:5432/floodrisk
JWT_SECRET_KEY=YOUR_UNIQUE_SECRET_WITH_AT_LEAST_32_CHARACTERS
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

Restrict the local secret file where the operating system supports it:

```bash
chmod 600 .env
```

Generate a development secret without putting it in source code:

```bash
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(48))"
```

If a username/password contains `@`, `:`, `/`, `#`, `%`, or other reserved URL
characters, URL-encode it in `DATABASE_URL`.

### 14.4 Initialize schema

From `backend`:

```bash
.venv/bin/python -m app.db.init_db
```

This step is what creates `users`, `user_role`, and `account_status`. Starting
FastAPI alone does not create them.

### 14.5 Run backend

Terminal 1, from `backend`:

```bash
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Verify:

```bash
curl http://127.0.0.1:8000/api/health
```

Expected:

```json
{"status":"healthy"}
```

Development URLs:

- API: `http://127.0.0.1:8000`
- Swagger: `http://127.0.0.1:8000/docs`
- OpenAPI: `http://127.0.0.1:8000/openapi.json`

### 14.6 Configure and run frontend

`frontend/.env` should contain only the public API URL:

```dotenv
VITE_API_URL=http://127.0.0.1:8000
```

Terminal 2, from `frontend`:

```bash
npm install
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open `http://127.0.0.1:5173`.

Using port 5173 matters because the current backend CORS list permits exactly
the localhost and 127.0.0.1 variants of that port. `--strictPort` prevents Vite
from silently changing to a port that CORS rejects.

### 14.7 Run quality checks

Backend, from `backend`:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider
```

Frontend, from `frontend`:

```bash
npm run lint
npm run build
```

### 14.8 Inspect PostgreSQL safely

Connect to the exact database from `DATABASE_URL`, then run:

```sql
SELECT current_database(), current_schema();

\d users

SELECT id, name, email, role, status, is_active
FROM users
ORDER BY id;
```

To verify hashing without exposing it in slides:

```sql
SELECT id, email, left(hashed_password, 10) AS hash_prefix
FROM users
ORDER BY id;
```

The prefix should look like an Argon2 identifier such as `$argon2...`, never a
plaintext password.

### 14.9 Quick API demonstration commands

Register a synthetic community user:

```bash
curl -i -X POST http://127.0.0.1:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Demo Community User",
    "email": "community.pending.demo@example.com",
    "password": "Use-A-Private-Demo-Password!",
    "role": "COMMUNITY"
  }'
```

The response should be `201 Created` with `PENDING` status and no password
field. Repeating the normalized email should produce `409 Conflict`.

Log in with an already approved account:

```bash
curl -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "met.admin.demo@example.com",
    "password": "YOUR_PRIVATE_ADMIN_PASSWORD"
  }'
```

Copy the returned token into a temporary shell variable. Do not paste a real
token into source code, screenshots, chat, or slides:

```bash
FLOOD_ADMIN_TOKEN='PASTE_TEMPORARY_ACCESS_TOKEN_HERE'
```

Get the current user:

```bash
curl http://127.0.0.1:8000/api/auth/me \
  -H "Authorization: Bearer ${FLOOD_ADMIN_TOKEN}"
```

List pending users:

```bash
curl http://127.0.0.1:8000/api/admin/users/pending \
  -H "Authorization: Bearer ${FLOOD_ADMIN_TOKEN}"
```

Approve user ID 2:

```bash
curl -X PATCH http://127.0.0.1:8000/api/admin/users/2/approve \
  -H "Authorization: Bearer ${FLOOD_ADMIN_TOKEN}"
```

Reject a different pending user, for example ID 3:

```bash
curl -X PATCH http://127.0.0.1:8000/api/admin/users/3/reject \
  -H "Authorization: Bearer ${FLOOD_ADMIN_TOKEN}"
```

Always obtain the actual IDs from the pending-user response. Approval and
rejection require no request body. Clear the temporary variable afterward:

```bash
unset FLOOD_ADMIN_TOKEN
```

---

## 15. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `relation "users" does not exist` | Schema not initialized, or connected to different DB | Confirm database name, then run `python -m app.db.init_db` from `backend` |
| `database ... does not exist` | DB name in URL is wrong/not created | Create it or correct final URL segment |
| `password authentication failed` | PostgreSQL user/password mismatch | Verify credentials and URL-encode reserved characters |
| `permission denied for schema public` | App role cannot create objects | Grant appropriate `USAGE, CREATE` for local development |
| Backend configuration validation fails | Missing/invalid env values | Check all four backend variables and 32+ character JWT secret |
| Browser says server cannot be reached | FastAPI is not running/wrong URL | Check `/api/health` and `VITE_API_URL` |
| Browser reports CORS error | Vite used a different host/port | Run exactly on 5173 or update backend allowlist deliberately |
| Registration returns `409` | Normalized email already exists | Use the existing account or a new synthetic email |
| Login returns `401` | Unknown email or wrong password | Use correct credentials; response deliberately stays generic |
| Login returns pending `403` | Account is not approved | Approve through an existing admin or bootstrap first admin |
| Admin route returns `403` | Current DB role is not `MET_ADMIN` | Check current user record; do not edit frontend role state |
| Map background is blank | OSM tiles unavailable/offline | Check network; local markers/list details are still prototype data |
| Alert action resets | Expected demo behaviour | It is React memory; a future alert API will persist it |
| `ModuleNotFoundError: app` | Backend command run from wrong folder | `cd backend` before running module commands |

If `psql` says `users` does not exist, first check:

```sql
SELECT current_database();
```

The application may have initialized a database named in `DATABASE_URL` while
`psql` is connected to a differently named database.

---

## 16. Test evidence and quality story

### Verified on this implementation snapshot

| Check | Result on 3 September 2026 |
| --- | --- |
| Backend Pytest suite | 33 passed; one upstream Starlette TestClient deprecation warning |
| Frontend Oxlint | Passed |
| TypeScript + Vite production build | Passed |

The warning does not represent a failed project test; it concerns an upstream
TestClient API transition and should still be tracked during dependency updates.

### Backend coverage by behaviour

- successful registration;
- normalized duplicate email conflict;
- invalid email;
- short password;
- plaintext password not stored;
- password/hash omitted from response;
- approved login;
- wrong password and unknown email generic `401`;
- pending, rejected, and inactive login denial;
- JWT contains only `sub` and `exp`;
- valid, missing, malformed, and expired-token behaviour;
- safe `/me` response;
- disabling/status-changing a user invalidates continuing access;
- MET admin versus community authorization;
- pending-user filtering;
- approve/reject persistence;
- missing-user `404`;
- repeated terminal transition conflicts.

### Testing limitations

- no frontend unit, component, or end-to-end automation yet;
- no real PostgreSQL integration suite;
- no browser accessibility automation;
- no load, security, or penetration testing;
- no weather/AI/alert backend tests because those services do not exist;
- no continuous-integration workflow in the repository.

### Strong answer to “How do you know it works?”

> We use layered evidence. Backend API tests verify the authentication and
> authorization rules through FastAPI while substituting an isolated database.
> Frontend lint and TypeScript production build catch code/type problems. We
> manually verify responsive routes and end-to-end PostgreSQL behaviour. We also
> acknowledge that PostgreSQL integration and browser E2E automation are the
> next quality gaps rather than claiming the SQLite suite proves everything.

---

## 17. Presentation and live-demo runbook

### Suggested 10–12 slide structure

1. **Title and team** — project name, Fiji problem context.
2. **Problem and users** — communities, MET staff, clarity/timeliness.
3. **Proposed solution** — monitor, assess, review, inform.
4. **Prototype boundary** — live auth versus demo flood data.
5. **Architecture** — React → FastAPI → PostgreSQL, plus OSM.
6. **Frontend experience** — landing, map, responsive design, roles.
7. **Backend and database** — layered API, user model, transactions.
8. **Authentication flow** — Argon2, approval, JWT, `/me`, RBAC.
9. **Security and privacy** — implemented controls and honest gaps.
10. **Demonstration** — public map, pending user, admin approval, community login.
11. **Testing and evidence** — 33 backend tests, lint/build, known gaps.
12. **Roadmap and deployment** — data/AI/alerts/PostGIS, proposed AWS path.

### Suggested team speaking split

Adapt this if the group size differs:

| Speaker | Owns | Must understand beyond own section |
| --- | --- | --- |
| 1 — Product/context | Problem, users, objectives, prototype boundary | Live versus demo distinction |
| 2 — Frontend | React, routes, map UI, responsive experience | API client and session flow |
| 3 — Backend/database | FastAPI layers, endpoints, SQLAlchemy, PostgreSQL | Safe responses and status codes |
| 4 — Auth/security/privacy | Argon2, JWT, RBAC, threats, data governance | First-admin and production gaps |
| 5 — Demo/testing/deployment | Demo sequence, tests, AWS proposal, roadmap | Whole-system architecture |

Every member should be able to answer the five facts in section 1 and explain
why account approval is real while alert approval is simulated.

### Pre-presentation checklist

- [ ] PostgreSQL is running.
- [ ] `backend/.env` points to the intended local database.
- [ ] `users` table exists.
- [ ] Synthetic approved MET admin can log in.
- [ ] Synthetic pending community user exists, or registration will create it.
- [ ] Backend `/api/health` returns healthy.
- [ ] Frontend is on port 5173.
- [ ] Browser session is cleared or planned tabs are prepared.
- [ ] Internet works if OSM tiles are part of the demo.
- [ ] No `.env`, password, JWT, or authorization header is visible on screen.
- [ ] Team knows what to do if internet/backend fails.
- [ ] Nobody calls demo weather/AI data “live.”

### Recommended 6–8 minute live demonstration

1. **Landing page** — explain purpose, branding, and routes.
2. **Public weather map** — show the “Demo data” badge, search Nadi, filter
   high-risk records, and distinguish the AI estimate from official-warning
   example.
3. **Register a community account** — show that the response/workflow is
   pending and that pending login is denied.
4. **Log in as prepared MET admin** — explain JWT and role redirect; state that
   operational dashboard metrics are illustrative.
5. **Demonstrate alert review** — approve a pending flood alert; point out the
   explicit browser-only notice and reload reset if useful.
6. **Open Users/Admin** — point out “Live auth API,” approve the real pending
   community user, and reload to show PostgreSQL persistence.
7. **Logout and log in as community user** — show live name/role from `/me`.
8. **Attempt an admin path** — show community redirect, then explain that the
   backend independently rejects real admin API calls.

### Narration for the key handover

> The admin dashboard and alert review show our intended operational experience,
> but these records are local demonstration data. Now we move to Users/Admin.
> This page is different: it calls our protected FastAPI API and persists the
> account decision in PostgreSQL. That is our completed end-to-end security
> vertical slice.

### Demo fallback plan

- **If PostgreSQL/backend fails:** present landing/map UI, then use Swagger or
  tests/screenshots to explain the live contract; do not pretend calls worked.
- **If OSM tiles fail:** use location list and detail panel; explain that tiles
  are the only external map request.
- **If a demo account is wrong:** inspect only safe account columns in psql;
  never reveal hashes/passwords on a projector.
- **If time is short:** show public map, pending registration, admin account
  approval, then community login. Those demonstrate the strongest story.

---

## 18. AWS deployment proposal — not currently implemented

There are currently no Dockerfiles, Compose files, CI/CD workflows, Terraform,
CloudFormation, AWS configuration, or deployed migration revisions in the
repository. The following is a **recommended future architecture**, not a claim
about the current system.

### Practical proposed architecture

```text
Users
  │ HTTPS
  ├───────────────────────────────┐
  ▼                               ▼
AWS Amplify Hosting              FastAPI on AWS App Runner
React/Vite static build          managed Python/container service
  │                               │
  │ VITE_API_URL at build         │ VPC connector / private network
  │                               ▼
  │                         Amazon RDS for PostgreSQL
  │                         private, encrypted, backed up
  │
  └──── Custom domains / DNS / certificates

FastAPI runtime also uses:
  ├── AWS Secrets Manager for DB/JWT secrets
  ├── IAM role with least privilege
  └── CloudWatch logs, metrics, and alarms
```

Why this is reasonable:

- Amplify Hosting supports React single-page applications and Git-based
  deployment to a CDN.
- App Runner can run a Python web service with less infrastructure management
  than operating a raw virtual machine.
- RDS provides managed PostgreSQL operations; keep it private and use it for
  current auth, with a reviewed PostGIS extension/version later.
- Secrets Manager avoids committing or baking database/JWT secrets into builds.
- CloudWatch provides a place for redacted logs, health metrics, and alarms.

For a larger or more controlled production design, ECS Fargate behind an
Application Load Balancer is an alternative to App Runner. It provides more
explicit container, networking, load-balancing, and scaling control, but adds
more infrastructure and operational work. The team should choose after defining
availability, budget, skills, and traffic—not claim that both are deployed.

Official AWS starting references:

- [AWS Amplify Hosting](https://docs.aws.amazon.com/amplify/latest/userguide/welcome.html)
- [AWS App Runner Python platform](https://docs.aws.amazon.com/apprunner/latest/dg/service-source-code-python.html)
- [Security in Amazon RDS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.html)
- [Encrypting Amazon RDS resources](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Overview.Encryption.html)
- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/)

### Required work before an AWS deployment

1. Add a real Alembic configuration and reviewed initial migration.
2. Make CORS origins environment-configurable.
3. Add a production deployment definition, such as a tested Dockerfile or
   App Runner configuration.
4. Pin/test a supported Python runtime and production server command.
5. Add environment separation for development, staging, and production.
6. Store DB credentials and JWT secret in a managed secret service; rotate test
   credentials that have ever been shared.
7. Keep RDS non-public in private subnets/security groups and allow only the
   backend service to connect.
8. Require TLS from browser to API and TLS from backend to database.
9. Enable RDS encryption at rest, automated backups, retention, restore tests,
   and appropriate deletion protection.
10. Add structured redacted logging, metrics, health checks, and alarms.
11. Configure the SPA fallback so client routes serve `index.html`.
12. Build the frontend with the production HTTPS `VITE_API_URL`.
13. Restrict CORS to the exact deployed frontend domain.
14. Add rate limiting, audit logging, security headers/CSP, and vulnerability
    scanning.
15. Run tests and a PostgreSQL migration in staging before production.
16. Define rollback, incident response, and data recovery procedures.
17. Review OpenStreetMap tile-service usage/privacy requirements or contract a
    production-suitable tile provider.
18. Confirm authorization to use official branding in the deployed context.

### Secrets and environment separation

| Value | Local development | Proposed AWS |
| --- | --- | --- |
| `VITE_API_URL` | Frontend `.env`, public localhost URL | Build-time public HTTPS API URL |
| `DATABASE_URL` | Backend `.env`, ignored by Git | Backend runtime secret/config only |
| `JWT_SECRET_KEY` | Backend `.env`, ignored by Git | Secrets Manager; restricted IAM role |
| JWT algorithm/expiry | Backend `.env` | Non-secret environment configuration |
| CORS origins | Hard-coded localhost today | Environment-specific exact HTTPS origins |

The frontend must never receive the database URL or JWT signing secret.

### Network and database rules

- RDS should not be publicly reachable.
- Security groups should allow database traffic only from the backend service.
- Use a dedicated application database user rather than the RDS master user.
- Encrypt storage/backups and require TLS connections.
- Test restore procedures rather than assuming a backup is usable.
- Apply schema changes as migrations during a controlled release.
- Separate production data from development/demo data.

### Scaling story

The React build is static and can be served through a CDN. FastAPI application
instances can scale horizontally because durable user state is in PostgreSQL,
not server memory. The current JWT is stateless, although protected calls still
query PostgreSQL for current authorization. Before significant scale, measure
database load, add appropriate connection-pool sizing, indexes/caching where
justified, and separate background ingestion/notification jobs from request
handling.

Do not promise cost figures without checking the chosen AWS Region, current
service pricing, traffic, storage, backup, and availability requirements.

---

## 19. Future complete architecture and roadmap

### Intended flood-data pipeline

```text
Trusted weather/river/rainfall/geospatial sources
  ↓
Scheduled ingestion + validation + timestamp/quality checks
  ↓
PostgreSQL/PostGIS observations and geographic features
  ↓
Feature engineering and versioned model inference
  ↓
Persisted prediction with model version, confidence, horizon, and evidence
  ↓
MET-admin review workflow with audit trail
  ↓
Approved official alert
  ↓
Public API/map + notification delivery + delivery status
```

### Recommended milestone order

1. **Harden the foundation:** Alembic, production config, audit columns, rate
   limiting, stronger session/security design, PostgreSQL integration tests.
2. **Persist domain data:** locations, observations, catchments, predictions,
   alerts, review events; introduce PostGIS where spatial queries justify it.
3. **Weather ingestion:** one approved source, validation, timestamps,
   staleness/failure handling, background job.
4. **Baseline risk model:** documented dataset, feature pipeline, validation,
   versioning, reproducible metrics, safe fallback.
5. **Prediction API:** return source, model version, horizon, confidence,
   generated time, and limitations.
6. **Alert backend:** pending/reviewed states, authorized transitions, reviewer,
   reason, timestamps, audit events.
7. **Notification service:** opted-in recipients, channels, retries, delivery
   status, rate controls, templates, emergency fallback.
8. **Operational readiness:** monitoring, backups/restores, incident exercises,
   accessibility/usability testing, privacy/security review.

### Suggested future domain tables

Do not build these until requirements are agreed, but the likely conceptual
model includes:

```text
users
locations
catchments / risk_zones (PostGIS)
weather_observations
model_versions
predictions
alerts
alert_reviews
notification_subscriptions
notification_deliveries
audit_events
```

Prediction and official alert should remain separate records so an AI estimate
cannot accidentally become an official warning merely by changing a UI label.

---

## 20. Likely lecturer questions and strong short answers

### Project and scope

**Is this already a live Fiji MET system?**

No. It is a university prototype for the Fiji MET context. Authentication and
account review are functional; flood/weather/AI/alert data is illustrative.

**Does use of the Fiji MET logo mean the system is officially endorsed?**

The prototype uses the supplied branding for the university project. Official
deployment or external distribution would require confirmed authorization and
an explicit statement of operational ownership.

**What exact problem are you solving?**

We are exploring a single, role-aware interface for understanding flood risk,
reviewing decision-support information, and communicating approved alerts more
clearly.

**What is the main achievement of this milestone?**

A complete auth vertical slice from responsive React UI through FastAPI
business rules to durable PostgreSQL data, plus a realistic domain UI prototype.

**Is the AI real? What algorithm did you use?**

No trained model is connected, so we should not invent an algorithm or accuracy.
The UI defines a future prediction contract; model selection and evaluation are
future milestones.

**Is weather live?**

No. Eight local records demonstrate the UI. Only OpenStreetMap basemap tiles are
requested externally.

**Which approval is real?**

User-account approval is real and PostgreSQL-backed. Flood-alert review is a
browser-only simulation.

### Frontend

**Why React Context instead of Redux?**

There are only two small global domains—authentication and prototype data.
Separate contexts are sufficient and avoid unnecessary dependency/complexity.

**Why TypeScript?**

It documents API/data shapes and catches many invalid property, role, and status
uses at build time.

**Why is the map public?**

The proposed community-facing risk view is public, while internal admin and
account tools are protected. Its current content is clearly marked demo data.

**What happens offline?**

Static/local UI can render, but OSM tiles may be blank. Real auth requires the
backend and database; future live weather would also need network/data sources.

**Can someone bypass a React route guard?**

They can manipulate browser code, which is why a frontend guard is never the
security boundary. FastAPI rechecks every real protected operation.

### Backend and database

**Why FastAPI?**

It fits the Python/AI ecosystem, provides typed validation and dependency
injection, and automatically exposes an OpenAPI contract.

**Why SQLAlchemy?**

It gives structured parameterized queries, models, transactions, and injectable
sessions that can be replaced in tests.

**Why PostgreSQL?**

It provides durable relational constraints and transactions and supports a
future PostGIS spatial path.

**Is PostGIS currently used?**

No. Coordinates are frontend demo data. PostGIS is future work for spatial
storage/indexing and queries.

**Are migrations implemented?**

No. Alembic is installed but not configured. Initial development schema uses
SQLAlchemy `create_all`; proper migrations are required before deployment.

**How do you prevent duplicate emails?**

Email is normalized to lowercase, checked for friendly feedback, and protected
authoritatively by a unique database constraint.

**What if two admins approve the same user?**

The service asks PostgreSQL to lock the row and allows only a `PENDING`
transition. A later conflicting request receives `409`.

### Authentication and security

**Why hash rather than encrypt passwords?**

Passwords never need to be recovered. Argon2 provides salted one-way
verification and deliberately makes guessing expensive.

**What is in the JWT?**

Only the user ID in `sub` and expiry in `exp`.

**Is a JWT encrypted?**

No, it is signed. Its payload is readable, so sensitive data is deliberately
excluded.

**Why query PostgreSQL when JWT is stateless?**

It gives immediate enforcement of account disable, rejection, deletion, or role
changes. Signature/expiry prove token validity; the database proves current
authorization.

**Can a user change the JWT or frontend role to become admin?**

Changing a signed token invalidates its signature, and no role is trusted from
the token/frontend. `require_met_admin` reads the current database role.

**Why can the public form request `MET_ADMIN`?**

It requests a role only. The backend always creates the account as pending, and
an existing approved admin must intentionally review it.

**How is the first administrator created?**

Normal pending registration followed by one narrow privileged local database
transaction. There is deliberately no public approved-admin shortcut.

**Why use a dummy password hash for unknown email?**

It makes unknown-user and wrong-password work more similar and reduces timing
signals that could help email enumeration.

**Why use `sessionStorage`?**

It supports reload within a tab and is less persistent than `localStorage`,
which is appropriate for this prototype. It remains JavaScript-readable, so it
is not a complete XSS defence.

**Does logout revoke the token?**

Not server-side in this milestone. It removes the browser copy. The token
expires, and current database state can block it earlier.

**Why `401` versus `403`?**

`401` means identity/credentials cannot be validated. `403` means the known
account or role is not permitted.

**Does CORS protect the API?**

No. CORS is a browser origin policy. JWT validation and backend authorization
protect the API.

**What would you add before production?**

Rate limiting, stronger session/revocation decisions, migrations, audit logs,
managed secrets, HTTPS/CSP, PostgreSQL integration tests, monitoring, backups,
and privacy/security review.

### Privacy and responsibility

**What personal data do you store?**

Name, email, password hash, role, approval status, and activity state. Raw
passwords are not stored.

**Are you privacy compliant?**

We have minimization and access-control foundations, but we do not claim legal
compliance from a prototype. Operational use requires a current Fiji legal and
organizational privacy review, retention policy, user processes, and controls.

**Could AI issue a dangerous false warning?**

That is why the design separates prediction from official warning and proposes
human review, provenance, confidence, monitoring, and fallback procedures.

**Which model metric matters?**

No model exists yet. Future evaluation must include false negatives, false
positives, calibration, lead time, regional/seasonal performance, robustness,
and operational usefulness—not accuracy alone.

### Deployment and operations

**Is it deployed on AWS now?**

No. AWS is a documented proposal; there are no cloud infrastructure files in
the repository.

**How would you deploy it?**

One practical path is Amplify Hosting for React, App Runner for FastAPI, private
RDS PostgreSQL, Secrets Manager for credentials, and CloudWatch for monitoring,
after adding migrations, production config, TLS, and security controls.

**How would it scale?**

Static frontend assets use a CDN; stateless FastAPI instances can scale
horizontally; PostgreSQL remains durable state. We would size connections,
measure load, and move ingestion/notifications to background workers.

**What if the database is unavailable?**

Live auth/account operations fail safely. Production needs monitoring, retries
where safe, backups, tested recovery, and a service-status/fallback plan.

**How do you protect AWS credentials and secrets?**

Use IAM least privilege and Secrets Manager, never Git or frontend `VITE_`
variables; rotate credentials and restrict RDS network access.

### Testing

**How many tests pass?**

On this documented snapshot, 33 backend tests pass. Frontend lint and production
build also pass.

**Do tests use the real PostgreSQL database?**

No. They use isolated in-memory SQLite through FastAPI dependency override.
That avoids polluting development data but leaves a known PostgreSQL integration
testing gap.

---

## 21. Glossary

| Term | Meaning in this project |
| --- | --- |
| API | HTTP interface connecting React to FastAPI |
| Authentication | Proving which user is making a request |
| Authorization | Deciding what that authenticated user may do |
| Argon2 | One-way password hashing algorithm used through `pwdlib` |
| Bearer token | Credential sent in the `Authorization` header; whoever bears it can use it |
| CORS | Browser rule controlling which origins may call the API |
| Dependency injection | FastAPI supplies reusable DB/auth dependencies to routes |
| JWT | Signed token carrying `sub` and `exp` in this project |
| ORM | SQLAlchemy mapping between Python objects and database rows |
| Pydantic | Validation and serialization layer used by FastAPI/config |
| RBAC | Role-based access control; `COMMUNITY` versus `MET_ADMIN` |
| PostgreSQL | Current durable user database |
| PostGIS | Future PostgreSQL spatial extension; not currently used |
| SPA | Single-page React application whose routes render in the browser |
| Prototype data | Illustrative local records that reset/do not represent live conditions |
| Human in the loop | Authorized review between AI recommendation and official action |

---

## 22. Final team cheat sheet

```text
PROJECT
FloodWatch Fiji: flood-risk and community-alert system prototype for Fiji MET.

LIVE
Registration, Argon2 hashing, PostgreSQL users, login, JWT, /me,
roles/status, and user-account approve/reject.

DEMO ONLY
Weather values, locations, flood risk, AI prediction, official-warning examples,
admin operational metrics, and flood-alert review.

FRONTEND
React + TypeScript + Vite + Router + Context + Leaflet.

BACKEND
FastAPI + Pydantic + SQLAlchemy + psycopg.

DATABASE
PostgreSQL users table. PostGIS not used yet.

AUTH
Only active APPROVED users log in. JWT = sub + exp. Backend reloads user.

ADMIN
Only current approved active MET_ADMIN may call /api/admin routes.

PASSWORDS
Argon2 hashes only; never plaintext and never returned.

DUMMY USERS
None are seeded. Test users are temporary SQLite records only.

DEPLOYMENT
Local only today. AWS architecture is proposed, not implemented.

TESTS
33 backend tests passed; frontend lint/build passed on 3 September 2026.

SAFETY LINE
This is not operational Fiji MET data or an official warning service.
```

### Detailed companion documents

- [Authentication workflow](./AUTHENTICATION_WORKFLOW.md)
- [Frontend prototype architecture and demo guide](./PROTOTYPE_UI.md)
- [Backend setup and API reference](../backend/README.md)
- [Frontend setup and usage](../frontend/README.md)
