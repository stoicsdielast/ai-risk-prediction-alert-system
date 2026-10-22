# Backend Authentication Guide

This guide explains how to install, configure, run, test, and use backend
registration, login, JWT authentication, protected routes, role-based
authorization, and MET admin account review for the Fiji Flood Risk Prediction
and Community Alert System.

A companion React interface consumes these endpoints and includes clearly
labelled local weather/map/alert prototype views. The alert backend now supports
persisted drafts, administrator review, suppression, and public approved alerts;
see the [Alert System guide](../docs/ALERT_SYSTEM.md). Prediction ingestion,
weather/location management, reporting, and frontend alert integration remain pending.
See the [frontend prototype guide](../docs/PROTOTYPE_UI.md) for that boundary.

## What is implemented

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/admin/users/pending`
- `PATCH /api/admin/users/{user_id}/approve`
- `PATCH /api/admin/users/{user_id}/reject`
- `GET /api/locations`, `GET /api/locations/divisions`, `GET /api/locations/{slug}`
- PostgreSQL user storage through SQLAlchemy
- Dependency-injected database sessions
- Email-format validation and lowercase normalization
- Password length validation from 8 to 128 characters
- Argon2 password hashing through `pwdlib`
- Case-insensitive duplicate prevention through email normalization
- HTTP `409 Conflict` for duplicate registration
- Separate role and account-approval status fields
- New-account defaults of `COMMUNITY`, `PENDING`, and active
- Safe response models that never expose passwords or password hashes
- Short-lived HS256 JWT access tokens containing only user ID and expiration
- Database-backed current-user validation on every protected request
- Reusable approved-MET-admin authorization
- Controlled pending-account approval and rejection transitions
- Tests for registration, login, JWT, authorization, and account review
- Persistent alert lifecycle and APIs documented in the [Alert System guide](../docs/ALERT_SYSTEM.md)

## Prerequisites

Install the following before starting:

- Python 3.11 or newer
- PostgreSQL
- A PostgreSQL database and user with permission to create tables and enum
  types in that database

The existing project virtual environment is located at `backend/.venv`. If it
does not exist, create it from the project root:

```bash
python -m venv backend/.venv
```

Activate it on Linux or macOS:

```bash
source backend/.venv/bin/activate
```

Activate it in Windows PowerShell:

```powershell
backend\.venv\Scripts\Activate.ps1
```

## Install dependencies

From the project root:

```bash
cd backend
python -m pip install -r requirements.txt
```

The authentication-specific packages are:

- `SQLAlchemy` for ORM models and database sessions
- `psycopg` with its binary package for PostgreSQL connectivity
- `pwdlib` and `argon2-cffi` for password hashing
- `PyJWT` for JWT encoding, signature validation, and expiration validation
- `email-validator` for Pydantic email validation
- `pytest` for automated tests

## Create the PostgreSQL database

The following is one example. Run `psql` as a PostgreSQL administrator and use
a strong password of your own:

```sql
CREATE USER flood_app WITH PASSWORD 'replace-with-a-strong-password';
CREATE DATABASE fiji_flood_risk OWNER flood_app;
```

If the database already exists but has a different owner, ensure the
application user can use and create objects in its public schema:

```sql
\connect fiji_flood_risk
GRANT USAGE, CREATE ON SCHEMA public TO flood_app;
```

## Configure environment variables

Copy the example file if `backend/.env` does not already exist:

```bash
cd backend
cp .env.example .env
```

Do not overwrite an existing `.env` containing your local configuration.

Set the database and JWT variables in `backend/.env`:

```dotenv
DATABASE_URL=postgresql+psycopg://flood_app:your-password@localhost:5432/fiji_flood_risk
JWT_SECRET_KEY=replace-this-with-a-unique-random-secret-of-at-least-32-characters
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

Connection format:

```text
postgresql+psycopg://USERNAME:PASSWORD@HOST:PORT/DATABASE
```

Standard `postgresql://` and `postgres://` URLs are also accepted and are
normalized internally to the psycopg 3 SQLAlchemy driver.

If the username or password contains reserved URL characters such as `@`,
`:`, `/`, `#`, or `%`, URL-encode those characters before placing the value in
`DATABASE_URL`.

Generate a development JWT secret with Python:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copy the printed value into `JWT_SECRET_KEY`. Do not use the example value or
commit the real value. `JWT_ALGORITHM` is restricted to `HS256`, and token
lifetime must be between 1 and 1440 minutes.

The `.env` file is intentionally excluded from Git. `.env.example` contains no
real credentials and can be committed safely.

## Initialize the database schema

Alembic was not configured in the repository, so this milestone includes a
small explicit schema initializer. From `backend` run:

```bash
python -m app.db.init_db
```

This creates the following objects if they do not already exist:

- `users` table
- `user_role` PostgreSQL enum
- `account_status` PostgreSQL enum
- unique index/constraint for `users.email`
- `locations`, `predictions`, and `alerts` tables and alert/risk enums
- `division` PostgreSQL enum and location coordinate range checks

The initializer uses SQLAlchemy `create_all`, which creates missing objects but
does not migrate an existing table when the model changes. Future schema
changes should introduce Alembic migrations before deployment.

## Load the Fiji demo locations

From `backend` run:

```bash
python -m app.db.seed_locations
```

This creates the tables if needed and loads 12 demo locations covering all four
divisions (Central, Western, Northern, Eastern). It is safe to run repeatedly:
locations are matched by slug, so existing demo rows are reset to their demo
coordinates and divisions, missing ones are added, and locations outside the
demo set are left untouched. The list lives in `DEMO_LOCATIONS` in
`app/db/seed_locations.py`.

## Location API

These read-only endpoints are public because the weather map is available
without signing in.

| Endpoint | Description |
| --- | --- |
| `GET /api/locations` | All locations ordered by name. Optional `division` (`CENTRAL`, `WESTERN`, `NORTHERN`, `EASTERN`) and `search` (case-insensitive partial name match, max 100 characters) query parameters |
| `GET /api/locations/divisions` | The four divisions with display labels |
| `GET /api/locations/{slug}` | One location, or `404 Location not found` |

Example location:

```json
{
  "slug": "suva",
  "name": "Suva",
  "division": "CENTRAL",
  "division_label": "Central Division",
  "latitude": -18.1416,
  "longitude": 178.4419
}
```

## Run the backend

From the `backend` directory:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Available development URLs:

- API root: <http://127.0.0.1:8000/>
- Health check: <http://127.0.0.1:8000/api/health>
- Swagger UI: <http://127.0.0.1:8000/docs>
- OpenAPI JSON: <http://127.0.0.1:8000/openapi.json>

The application creates its database engine lazily. Starting FastAPI does not
create tables automatically; run the schema initialization command first.

## Registration API

### Endpoint

```http
POST /api/auth/register
Content-Type: application/json
```

### Request fields

| Field | Type | Required | Rules |
| --- | --- | --- | --- |
| `name` | string | Yes | Trimmed, 1–255 characters, cannot be blank |
| `email` | string | Yes | Must be a valid email; stored in lowercase |
| `password` | string | Yes | 8–128 characters |
| `role` | enum | No | `COMMUNITY` or `MET_ADMIN`; defaults to `COMMUNITY` |

`role` and account approval `status` are separate. Requesting `MET_ADMIN` does
not approve an account. Every newly registered account receives `PENDING`
status.

### Example request

```bash
curl -i -X POST http://127.0.0.1:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Parvish Mohan",
    "email": "parvish@example.com",
    "password": "FloodRisk123!",
    "role": "COMMUNITY"
  }'
```

### Successful response

Status: `201 Created`

```json
{
  "id": 1,
  "name": "Parvish Mohan",
  "email": "parvish@example.com",
  "role": "COMMUNITY",
  "status": "PENDING"
}
```

`password`, `hashed_password`, and `is_active` are deliberately omitted from
the public response.

### Register with the default role

The `role` field can be omitted. The account will use `COMMUNITY`:

```bash
curl -X POST http://127.0.0.1:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test User",
    "email": "test.user@example.com",
    "password": "SecurePass123!"
  }'
```

### Duplicate email response

Registering the same email again, including with different capitalization,
returns `409 Conflict`:

```json
{
  "detail": "Account already exists"
}
```

### Validation error response

An invalid email, short password, unsupported role, missing field, or blank
name returns `422 Unprocessable Entity`. FastAPI returns details identifying
the invalid request field. For example, this request is invalid:

```bash
curl -X POST http://127.0.0.1:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test User",
    "email": "not-an-email",
    "password": "short",
    "role": "COMMUNITY"
  }'
```

Unexpected SQLAlchemy database failures return `500 Internal Server Error`
with a generic message:

```json
{
  "detail": "Unable to create account"
}
```

Database exception details and stack traces are not included in the API
response.

## Login API

Only active users whose status is `APPROVED` can log in.

```bash
curl -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "parvish@example.com",
    "password": "FloodRisk123!"
  }'
```

A successful login returns:

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

Send the token in subsequent requests:

```http
Authorization: Bearer eyJ...
```

Login failures are deliberately controlled:

| Condition | Status | Message |
| --- | --- | --- |
| Unknown email or wrong password | `401` | `Invalid credentials` |
| Pending account | `403` | `Account approval pending` |
| Rejected account | `403` | `Account has been rejected` |
| Inactive account | `403` | `Account is inactive` |

Password verification happens before account status is disclosed. The JWT
contains only a string user ID in `sub` and an expiration timestamp in `exp`.

## Current-user API

`GET /api/auth/me` requires a valid Bearer token:

```bash
curl http://127.0.0.1:8000/api/auth/me \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Example response:

```json
{
  "id": 1,
  "name": "Parvish Mohan",
  "email": "parvish@example.com",
  "role": "COMMUNITY",
  "status": "APPROVED"
}
```

Missing, malformed, incorrectly signed, or expired tokens return `401`. The
dependency loads the user from PostgreSQL on every request. Disabling,
rejecting, or returning an account to a non-approved state therefore prevents
continued access even if an older token has not expired.

## MET admin account review APIs

All `/api/admin` routes require a valid token for an active, approved
`MET_ADMIN`. A `COMMUNITY` user receives `403 Insufficient permissions`; roles
sent in client requests or JWT claims are never trusted for authorization.

List pending users:

```bash
curl http://127.0.0.1:8000/api/admin/users/pending \
  -H "Authorization: Bearer ADMIN_ACCESS_TOKEN"
```

Approve a pending user:

```bash
curl -X PATCH http://127.0.0.1:8000/api/admin/users/4/approve \
  -H "Authorization: Bearer ADMIN_ACCESS_TOKEN"
```

Reject a pending user:

```bash
curl -X PATCH http://127.0.0.1:8000/api/admin/users/4/reject \
  -H "Authorization: Bearer ADMIN_ACCESS_TOKEN"
```

Approval and rejection only allow a transition from `PENDING`. A missing user
returns `404`. Attempting to transition an already approved or rejected user
returns `409` with a controlled message. Every response uses `UserResponse`, so
password hashes are never returned.

## MET admin analytics APIs

Read-only analytics for an approved `MET_ADMIN`; no route writes to the
database, generates a prediction, retrains or promotes a model.

```bash
# Summary counts, risk bands and model provenance for the last 30 days (days 1..365)
curl "http://127.0.0.1:8000/api/admin/analytics/predictions/overview?days=30" \
  -H "Authorization: Bearer ADMIN_ACCESS_TOKEN"

# Stored-probability series per location; source is operational or synthetic
curl "http://127.0.0.1:8000/api/admin/analytics/predictions/trend?days=7&source=operational&location_id=1&location_id=2" \
  -H "Authorization: Bearer ADMIN_ACCESS_TOKEN"

# Parsed saved research artifacts (V1/V2/V3) and the deployed model metadata
curl "http://127.0.0.1:8000/api/admin/analytics/models/performance" \
  -H "Authorization: Bearer ADMIN_ACCESS_TOKEN"
```

Operational `predictions` (genuine and sample) and `synthetic_predictions` are
reported separately and never merged. An unknown `location_id` returns `404`; an
out-of-range `days` returns `422`. `models/performance` reads
`RESEARCH_RUNS_DIR` (default `ml/runs`) and returns `available: false` with a
reason for any run whose artifacts are absent, so the endpoint degrades honestly
rather than inventing numbers. The frontend surfaces these at `/admin/analytics`
and `/admin/model-performance`.

## Bootstrap the first MET admin for development

There is intentionally no public endpoint that creates or automatically
approves an administrator.

First register the intended administrator normally:

```bash
curl -X POST http://127.0.0.1:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Initial MET Admin",
    "email": "admin@example.com",
    "password": "Use-A-Strong-Password!",
    "role": "MET_ADMIN"
  }'
```

It will be stored as `PENDING`. Connect through a privileged local PostgreSQL
session and start a transaction:

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

Carefully verify that `RETURNING` shows exactly the intended single account.
If it does, finish with:

```sql
COMMIT;
```

If no row or an unexpected row is returned, use:

```sql
ROLLBACK;
```

After committing, that administrator can log in and review all later pending
accounts through the protected admin endpoints. This manual step is for local
development bootstrap only.

## User data model

The `users` table contains:

| Column | Purpose |
| --- | --- |
| `id` | Primary-key user identifier |
| `name` | User's display name |
| `email` | Normalized unique email address |
| `hashed_password` | Argon2 password hash; never plaintext |
| `role` | `COMMUNITY` or `MET_ADMIN` |
| `status` | `PENDING`, `APPROVED`, or `REJECTED` |
| `is_active` | Whether the account is active; defaults to `true` |

Database and application defaults are both defined for role, status, and
active state. Registration also assigns these values explicitly.

## Verify registration in PostgreSQL

Connect to the configured database:

```bash
psql -U flood_app -h localhost -d fiji_flood_risk
```

Inspect the schema and enum types:

```sql
\d users
\dT+ user_role
\dT+ account_status
```

Inspect a registered account:

```sql
SELECT
    id,
    name,
    email,
    role,
    status,
    is_active,
    hashed_password
FROM users
WHERE email = 'parvish@example.com';
```

Confirm that:

- The email is lowercase.
- The role is `COMMUNITY` unless `MET_ADMIN` was requested.
- The status is `PENDING`.
- `is_active` is `true`.
- `hashed_password` starts with an Argon2 identifier such as `$argon2`.
- The plaintext password is not present.

## Run automated tests

From `backend`:

```bash
python -m pytest -q
```

The tests use an isolated in-memory SQLite database through FastAPI's database
dependency override. They do not write to the configured PostgreSQL database.

The test suite covers registration, password storage, login outcomes, JWT
creation and validation, missing/malformed/expired tokens, current-user
responses, account disabling, MET admin authorization, pending-user listing,
approval, rejection, missing users, and invalid repeat transitions.

Run one test file with verbose output:

```bash
python -m pytest tests/test_login.py -v
```

## Authentication code structure

```text
backend/
├── .env.example
├── app/
│   ├── api/routes/auth.py       # Registration, login, and current user
│   ├── api/routes/admin.py      # Protected account-review endpoints
│   ├── api/dependencies.py      # Current-user and MET-admin dependencies
│   ├── core/config.py           # Environment-backed configuration
│   ├── core/security.py         # Argon2 and JWT security helpers
│   ├── db/base.py               # SQLAlchemy declarative base
│   ├── db/init_db.py            # Explicit initial schema creation
│   ├── db/session.py            # Engine, session factory, get_db dependency
│   ├── models/user.py           # User model and enums
│   ├── schemas/auth.py          # Login and token schemas
│   ├── schemas/user.py          # Request validation and response filtering
│   ├── services/auth_service.py # Registration/login/access-state logic
│   ├── services/admin_service.py # Pending-list and status-transition logic
│   └── main.py                  # FastAPI application and router registration
└── tests/
    ├── conftest.py              # Isolated test DB and dependency override
    ├── test_registration.py     # Registration tests
    ├── test_login.py            # Login outcome and JWT tests
    ├── test_authentication.py   # Protected current-user tests
    └── test_admin.py            # Role and account-review tests
```

Request processing follows this path:

```text
POST /api/auth/register
        ↓
Pydantic request validation
        ↓
FastAPI route
        ↓
Registration service
        ↓
Argon2 password hashing + SQLAlchemy session
        ↓
PostgreSQL users table
        ↓
Safe UserResponse serialization
```

Protected request processing follows this path:

```text
Authorization: Bearer <token>
        ↓
Verify signature, algorithm, required sub, and expiration
        ↓
Load user by sub from PostgreSQL
        ↓
Recheck active and APPROVED state
        ↓
For admin routes, verify database role is MET_ADMIN
        ↓
Execute route and return a safe response schema
```

## Security behavior

- The raw password is used only long enough to generate an Argon2 hash.
- Only `hashed_password` is persisted.
- The response schema has no password-related fields.
- Email normalization prevents capitalization-based duplicate registration
  through this API.
- A database uniqueness constraint protects against concurrent duplicate
  inserts.
- Database sessions are closed after each request.
- Failed transactions are rolled back.
- Database error details are replaced with a generic client response.
- `.env` is ignored by Git.
- The JWT secret is required from the environment, stored as a Pydantic
  `SecretStr`, and never hard-coded or returned.
- JWT decoding fixes the allowed algorithm to configured `HS256` and requires
  both `sub` and `exp`.
- JWTs contain no password, hash, role, email, or database information.
- Authorization reloads the account and role from PostgreSQL rather than
  trusting client input or token role claims.
- Expired tokens are rejected, and state changes affect existing tokens on the
  next protected request.

## Troubleshooting

### `ModuleNotFoundError: No module named 'app'`

Run backend commands from the `backend` directory:

```bash
cd backend
python -m uvicorn app.main:app --reload
```

### `DATABASE_URL` validation error

Confirm that `backend/.env` exists and contains a PostgreSQL URL. SQLite URLs
are accepted only by the isolated test fixtures, not by application settings.

### `database ... does not exist`

Create the database first and verify that the final path segment in
`DATABASE_URL` matches its name.

### `password authentication failed`

Verify the PostgreSQL username and password. URL-encode special characters in
the URL password.

### `permission denied for schema public`

Grant schema permissions using an administrative PostgreSQL account:

```sql
GRANT USAGE, CREATE ON SCHEMA public TO flood_app;
```

### `relation "users" does not exist`

Initialize the schema:

```bash
python -m app.db.init_db
```

### Registration returns `409 Conflict`

An account with that normalized email already exists. This is expected
duplicate-prevention behavior.

### Registration returns `500 Internal Server Error`

Check that PostgreSQL is running, `DATABASE_URL` is correct, the database
exists, permissions are sufficient, and the schema initializer completed.
Server-side logs may contain diagnostic details; API responses intentionally do
not expose them.

### JWT configuration validation error

Confirm that all three JWT variables exist in `backend/.env`, that the secret
has at least 32 characters, `JWT_ALGORITHM` is `HS256`, and the expiry is a
positive integer no greater than 1440.

### Protected route returns `401`

Log in again and send the returned token exactly as
`Authorization: Bearer YOUR_ACCESS_TOKEN`. Tokens that are expired, malformed,
signed with a different secret, or missing required claims are rejected.

### Protected route returns `403`

The token may be valid while the database account is pending, rejected,
inactive, or lacks the `MET_ADMIN` role required by an admin route. Check the
current database values; authorization deliberately does not trust the token
for current account state or role.

## Current limitations and next milestone

This milestone intentionally does not provide:

- Refresh tokens or token revocation storage
- Password reset or email verification
- Account approval audit fields such as `approved_by` or `approved_at`
- Operational prediction ingestion or external notification delivery. Weather
  observation storage and APIs are now available; see the weather section below.

The React authentication interface uses this backend as its security boundary.
Use the existing Alembic migration workflow before modifying deployed schemas.

# Bangladesh historical research API

The separate [research runbook](../docs/RESEARCH_BANGLADESH.md) describes the
authenticated `/api/predictions/flood-risk` endpoint, public model-info and replay
reads, model setup and the additional `research_predictions` table. These are
historical Bangladesh proxy-label results, not validated Fiji forecasts. Run
`python -m app.db.init_db` after updating to create the research table.

# Synthetic research demonstration API

The isolated synthetic replay and alert-approval demonstration is documented in
[the synthetic methodology guide](../docs/SYNTHETIC_METHODOLOGY.md). Summary:

- Tables: `synthetic_datasets`, `synthetic_observations`, `synthetic_predictions`,
  `synthetic_alerts` (Alembic revision `20261019_synthetic`); they are never
  mixed with operational predictions or alerts.
- Setup: publish the serving bundle to `ml/artifacts/synthetic/v1/`, run
  `python -m alembic upgrade head`, then
  `python -m app.db.import_synthetic --dataset ../ml/data/synthetic_fiji/v1`
  (checksum- and registry-verified, idempotent).
- Reads: `GET /api/synthetic/info`, `GET /api/synthetic/frame?timestamp=`
  (timezone-aware exact hourly timestamps), `GET /api/synthetic/alerts`.
- Demo writes (require `SYNTHETIC_DEMO_ENABLED=true` and a MET_ADMIN token):
  `POST /api/synthetic/admin/alerts` (HIGH/VERY_HIGH forecasts, or an explicit
  `test_alert=true` for isolated LOW/MODERATE tests) and
  `POST /api/synthetic/admin/alerts/{id}/approve`. Administrator acknowledgement,
  resolution, cancellation and the required additive migration are documented
  in [Alert management](../docs/ALERT_MANAGEMENT.md).
- Every response carries `source_type: "synthetic"` and a research-demonstration
  notice. These are simulator outputs, never official Fiji MET readings or
  emergency warnings.

# Weather observation backend

The weather storage/API and optional standalone ingestion worker are documented in
[`docs/WEATHER_DATA_MANAGEMENT.md`](../docs/WEATHER_DATA_MANAGEMENT.md).
Run `.venv/bin/python -m alembic upgrade head` on an existing initialized database
before using these endpoints. Genuine and synthetic weather are physically separated;
no external weather provider is configured by default.

## V1 observation-driven prediction generation

`POST /api/predictions/generate` now supports authenticated MET-admin research
inference from stored synthetic weather, with exact V1 features, immutable provenance,
and atomic optional PENDING demo-alert creation. The genuine operational path remains
blocked; the selected model and V1/V2/V3 artifacts are unchanged.
`GET /api/risk/{location}` is retired (410 Gone), replacing its hardcoded HIGH/0.82.
See [V1 prediction workflow](../docs/V1_PREDICTION_WORKFLOW.md) for migrations,
bounded weather imports, source restrictions, example requests and real PostgreSQL tests.
