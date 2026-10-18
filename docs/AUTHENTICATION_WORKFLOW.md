# Authentication System: How It Works

This document explains the complete authentication and account-approval flow
for the Flood Risk Prediction and Community Alert System. It covers how the
React frontend, FastAPI backend, PostgreSQL database, JWT access tokens, and
MET administrator permissions work together.

For installation details, also see:

- [Frontend setup guide](../frontend/README.md)
- [Backend setup guide](../backend/README.md)

## Current scope

The implemented authentication system provides:

- User registration
- Argon2 password hashing
- Account approval statuses
- Login with email and password
- JWT access tokens
- Protected backend and frontend routes
- Current-user retrieval
- Role-based MET administrator authorization
- Pending-user listing
- Account approval and rejection
- Local browser logout

It does not yet provide refresh tokens, password reset, email verification,
OAuth providers, frontend flood functionality, AI prediction, weather, maps,
alerts, or reporting.

## System overview

```text
┌───────────────────────────┐
│ React frontend            │
│ http://localhost:5173     │
│                           │
│ Forms, route guards,      │
│ sessionStorage, admin UI  │
└─────────────┬─────────────┘
              │ HTTP/JSON
              │ Authorization: Bearer <JWT>
              ▼
┌───────────────────────────┐
│ FastAPI backend           │
│ http://127.0.0.1:8000     │
│                           │
│ Validation, password      │
│ checks, JWT validation,   │
│ roles and account rules   │
└─────────────┬─────────────┘
              │ SQLAlchemy
              ▼
┌───────────────────────────┐
│ PostgreSQL                │
│                           │
│ users, roles, statuses,   │
│ Argon2 password hashes    │
└───────────────────────────┘
```

The frontend controls what the user sees, but it is not the security boundary.
FastAPI validates authentication and authorization again for every protected
API request.

## Roles and account statuses

Role and status answer different questions.

| Field | Values | Meaning |
| --- | --- | --- |
| `role` | `COMMUNITY`, `MET_ADMIN` | What the user may do after approval |
| `status` | `PENDING`, `APPROVED`, `REJECTED` | Whether the account may authenticate |
| `is_active` | `true`, `false` | Whether the account is enabled |

Important rules:

- Every new account starts as `PENDING`.
- Omitting a role during registration defaults to `COMMUNITY`.
- Requesting `MET_ADMIN` does not approve the account.
- Only an active, `APPROVED` user can receive and use an access token.
- Only an active, approved `MET_ADMIN` can access account-review APIs.
- A role sent from the browser is never trusted for authorization. The backend
  reads the current role from PostgreSQL.

## User record

The PostgreSQL `users` table contains approximately:

```text
id
name
email
hashed_password
role
status
is_active
```

The API never returns `hashed_password`. The plaintext password is never stored.

## 1. Registration flow

The user opens `/register` and submits name, email, password, confirmation, and
the requested account type.

```text
React registration form
        │
        │ POST /api/auth/register
        ▼
Pydantic validates input
        │
        ├── normalize email to lowercase
        ├── require valid email
        ├── require password length 8–128
        └── validate COMMUNITY or MET_ADMIN
        │
        ▼
Registration service checks duplicate email
        │
        ▼
Password is hashed with Argon2
        │
        ▼
PostgreSQL stores user as PENDING and active
        │
        ▼
Frontend shows pending-approval confirmation
```

Example request:

```json
{
  "name": "Example User",
  "email": "user@example.com",
  "password": "Password123!",
  "role": "COMMUNITY"
}
```

Example response:

```json
{
  "id": 4,
  "name": "Example User",
  "email": "user@example.com",
  "role": "COMMUNITY",
  "status": "PENDING"
}
```

A duplicate email returns HTTP `409` with `Account already exists`. Validation
failures return HTTP `422`.

## 2. Account approval flow

A pending user cannot log in. An approved MET administrator reviews requests at:

```text
/admin/users/pending
```

The page calls:

```http
GET /api/admin/users/pending
Authorization: Bearer <ADMIN_TOKEN>
```

The administrator confirms either action:

```http
PATCH /api/admin/users/{user_id}/approve
PATCH /api/admin/users/{user_id}/reject
Authorization: Bearer <ADMIN_TOKEN>
```

No request body is required. The backend:

1. Validates the JWT.
2. Loads the administrator from PostgreSQL.
3. Verifies active and `APPROVED` state.
4. Verifies the current database role is `MET_ADMIN`.
5. Locks and loads the target user.
6. Allows a transition only from `PENDING`.
7. Commits `APPROVED` or `REJECTED`.
8. Returns a safe user response without password data.

A community user receives HTTP `403`. A missing user receives `404`. Trying to
change an already approved or rejected account receives `409`.

## 3. First MET administrator bootstrap

There is deliberately no public API that automatically creates an approved
administrator.

For local development:

1. Register the intended first administrator normally with role `MET_ADMIN`.
2. Confirm that the record is `PENDING`.
3. Connect to PostgreSQL using a privileged local account.
4. Approve exactly that account in a transaction.

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

Verify that exactly the intended row is returned, then run:

```sql
COMMIT;
```

If the row is missing or unexpected, run `ROLLBACK;` instead. After this
one-time bootstrap, the approved administrator can manage later requests through
the protected frontend.

## 4. Login flow

The user submits email and password at `/login`.

```text
React login form
        │
        │ POST /api/auth/login
        ▼
Backend finds normalized email
        │
        ▼
Argon2 verifies supplied password
        │
        ▼
Backend checks active and APPROVED state
        │
        ▼
Backend signs short-lived JWT
        │
        ▼
Frontend calls GET /api/auth/me
        │
        ▼
Token is stored in sessionStorage
        │
        ▼
User enters protected frontend route
```

The login request uses JSON, not OAuth form data:

```json
{
  "email": "user@example.com",
  "password": "Password123!"
}
```

Success returns:

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

Login outcomes:

| Condition | HTTP status | Message |
| --- | --- | --- |
| Wrong password or unknown email | `401` | `Invalid credentials` |
| Pending account | `403` | `Account approval pending` |
| Rejected account | `403` | `Account has been rejected` |
| Inactive account | `403` | `Account is inactive` |

The same generic `401` is used for an unknown email and wrong password. A dummy
Argon2 verification also reduces the timing difference between those cases.

## 5. JWT contents and validation

The token contains only a stable user identifier and expiration:

```json
{
  "sub": "4",
  "exp": 1788312345
}
```

It does not contain password data, email, role, account status, JWT secret, or
database credentials.

The browser sends it as:

```http
Authorization: Bearer <JWT>
```

FastAPI validates:

- Bearer authentication format
- JWT signature using `JWT_SECRET_KEY`
- Configured `HS256` algorithm
- Required `sub` and `exp` claims
- Token expiration
- Positive canonical user ID
- User still exists
- User is still active and approved

Invalid or expired tokens return HTTP `401`.

## 6. Current-user dependency

`GET /api/auth/me` is used to establish the current authenticated user:

```text
JWT sub
  ↓
Load user by ID from PostgreSQL
  ↓
Check current is_active and status
  ↓
Return id, name, email, role, status
```

This database lookup happens on protected requests. If an account is disabled,
rejected, deleted, or has its role changed, the change takes effect without
waiting for the JWT to expire.

Example response:

```json
{
  "id": 4,
  "name": "Example User",
  "email": "user@example.com",
  "role": "COMMUNITY",
  "status": "APPROVED"
}
```

## 7. Frontend session handling

The React `AuthProvider` owns the browser authentication state:

```text
token
current user
loading state
temporary session-check error
login()
logout()
retrySession()
```

The JWT is stored under a project-specific key in `sessionStorage`:

- It remains available during reloads in the current tab.
- It is removed by local logout.
- It normally disappears when the tab/session closes.
- It is never placed in a URL or application log.
- There is no backend logout or refresh-token endpoint yet.

When React starts and finds a token, it calls `/api/auth/me`:

- `200`: restore the user.
- `401` or account-state `403`: remove the invalid session.
- Temporary network or server failure: keep the token and show a retry screen.

Because browser storage is JavaScript-readable, future production deployment
should include strong XSS prevention and Content Security Policy. An HttpOnly
cookie design can be considered if the backend contract changes later.

## 8. Frontend route guards

| Frontend route | Access rule |
| --- | --- |
| `/` | Public welcome page |
| `/login` | Public login page |
| `/register` | Public registration page |
| `/registration-submitted` | Public pending confirmation |
| `/dashboard` | Authenticated user |
| `/admin/users/pending` | Authenticated `MET_ADMIN` |

The React guards provide navigation and user experience only. A user cannot gain
real permission by changing frontend state because the backend independently
checks JWT, status, active state, and role.

## 9. Logout

Logout currently happens entirely in React:

```text
User selects Log out
        ↓
Remove JWT from sessionStorage
        ↓
Clear current React user
        ↓
Navigate to /login
```

There is no server-side token revocation list. The old token remains
cryptographically valid until expiration if copied elsewhere, but every request
still checks the current database account state. Refresh tokens and explicit
revocation are outside the current milestone.

## 10. Error handling

The shared API client handles both FastAPI error formats:

```json
{"detail": "Account already exists"}
```

and validation arrays:

```json
{
  "detail": [
    {"loc": ["body", "email"], "msg": "value is not a valid email address"}
  ]
}
```

Network failures display a safe connection message. Database exception details,
stack traces, password hashes, and tokens are not shown to users.

## 11. Source-code map

```text
frontend/src/
├── api/client.ts                 Shared fetch and safe API errors
├── api/auth.ts                   Register, login, current-user calls
├── api/admin.ts                  Pending, approve, reject calls
├── auth/AuthProvider.tsx         Token and current-user state
├── auth/RouteGuards.tsx          Public, protected, admin navigation
├── pages/LoginPage.tsx           Login form
├── pages/RegisterPage.tsx        Registration form
├── pages/DashboardPage.tsx       Protected account overview
└── pages/AdminUsersPage.tsx      MET-admin review interface

backend/app/
├── api/dependencies.py           Current-user and MET-admin dependencies
├── api/routes/auth.py            Register, login, /me endpoints
├── api/routes/admin.py           Pending, approve, reject endpoints
├── core/config.py                Database and JWT environment settings
├── core/security.py              Argon2 and JWT functions
├── models/user.py                User model, roles, statuses
├── schemas/auth.py               Login and token schemas
├── schemas/user.py               Registration and safe user schemas
├── services/auth_service.py      Registration and authentication rules
└── services/admin_service.py     Account-review database operations
```

## 12. Environment configuration

Backend `.env`:

```dotenv
DATABASE_URL=postgresql+psycopg://flood_app:password@localhost:5432/fiji_flood_risk
JWT_SECRET_KEY=a-unique-secret-containing-at-least-32-characters
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

Frontend `.env`:

```dotenv
VITE_API_URL=http://127.0.0.1:8000
```

Never place the database URL or JWT secret in a `VITE_` variable. Vite variables
are embedded into public browser code.

The backend currently permits browser requests from
`http://localhost:5173` and `http://127.0.0.1:5173`. A different Vite port or a
deployed frontend origin must be deliberately added to the backend CORS
configuration. PostgreSQL is required for real authentication; the PostGIS
extension is not needed for this milestone.

## 13. Run the complete authentication system

Terminal 1 — backend:

```bash
cd backend
.venv/bin/python -m uvicorn app.main:app --reload
```

Terminal 2 — frontend:

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

PostgreSQL is required for real registration, login, and account review. The
backend tests use isolated SQLite instead.

## 14. Validation commands

Backend:

```bash
cd backend
.venv/bin/python -m pytest -q
```

Frontend:

```bash
cd frontend
npm run lint
npm run build
```

These checks validate backend behavior, TypeScript compilation, frontend lint,
and the production frontend bundle.
