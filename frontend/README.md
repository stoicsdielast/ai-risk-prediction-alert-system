# FloodWatch Fiji Frontend

React and TypeScript frontend for the Flood Risk Prediction and Community
Alert System. The current milestone combines live authentication/account review
with three polished flood-domain prototype views.

## Implemented

- Welcome and access overview
- User registration for `COMMUNITY` and `MET_ADMIN` requests
- Pending-approval confirmation
- Approved-user login
- JWT storage in browser `sessionStorage`
- Session restoration through `GET /api/auth/me`
- Protected account overview
- MET-admin-only pending account review
- Approve and reject actions
- Local logout
- Responsive `#2d3055` sidebar workspace
- Protected MET-admin operational dashboard
- Public Leaflet map with Fiji location and risk markers
- Searchable and filterable location details
- Separate AI-prediction and official-warning presentation
- Protected alert list, filters, review details, and demo actions
- Loading, success, error, and empty states where applicable

Registration, login, current-user checks, and user-account moderation use the
FastAPI/PostgreSQL backend. Weather observations, flood predictions, dashboard
metrics, operational alerts, and alert actions are illustrative local data and
are not persisted. See the
[prototype architecture and demo guide](../docs/PROTOTYPE_UI.md) before presenting
the system.

Real AI inference, weather ingestion, operational alert delivery, reports,
refresh tokens, and password reset are not implemented yet.

## Prerequisites

- Node.js supported by the Vite version in `package.json`
- The FastAPI backend running at `http://127.0.0.1:8000`
- PostgreSQL running for real registration and login requests
- Internet access to display OpenStreetMap background tiles

## Environment configuration

Copy the example if `frontend/.env` does not exist:

```bash
cd frontend
cp .env.example .env
```

The development setting is:

```dotenv
VITE_API_URL=http://127.0.0.1:8000
```

Restart Vite after changing this value. Do not place JWTs, database passwords,
or private server secrets in a `VITE_` variable because Vite exposes those
values to browser code.

The backend currently permits CORS only from the default Vite development
origins on port `5173`. If Vite selects another port, stop the other process and
restart on `5173`, or update the backend CORS configuration deliberately.

## Install and run

From the project root:

```bash
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open <http://127.0.0.1:5173>.

Run the backend in another terminal:

```bash
cd backend
.venv/bin/python -m uvicorn app.main:app --reload
```

## Account workflow

1. Open `/register` and submit a community or MET-admin request.
2. The backend creates the account with `PENDING` status.
3. An approved MET administrator reviews it at `/admin/users/pending`.
4. Once approved, the user signs in at `/login`.
5. The frontend stores the access token in `sessionStorage` for the current tab.
6. Protected routes call `/api/auth/me` and use the database-backed user role.

The frontend route guard improves navigation but is not the security boundary.
The FastAPI backend still validates every JWT and administrator action.

## Routes

| Route | Access | Purpose |
| --- | --- | --- |
| `/` | Public | Welcome and account workflow |
| `/login` | Public | Approved-user login |
| `/register` | Public | New account request |
| `/registration-submitted` | Public | Pending confirmation |
| `/weather-map` | Public | Prototype Fiji weather and flood-risk map |
| `/dashboard` | Authenticated | Account and project overview |
| `/admin/dashboard` | Approved MET admin | Prototype operational summary |
| `/admin/alerts` | Approved MET admin | Prototype alert-review workflow |
| `/admin/users/pending` | Approved MET admin | Account review |

The workspace displays **Demo data** on prototype flood pages and **Live auth
API** on database-backed account pages. Alert approve/reject/suppress actions
change React state only and reset after a full reload. Account approve/reject
actions are real protected backend operations and persist in PostgreSQL.

## Token behavior

- Tokens are never written to URLs or application logs.
- Closing the browser tab removes `sessionStorage` for that tab.
- Logout removes the token locally; there is no backend logout endpoint yet.
- On startup, the frontend validates a stored token through `/api/auth/me`.
- Temporary network/server failures offer a session-check retry instead of
  deleting an otherwise valid token.
- A rejected, pending, inactive, expired, or invalid session cannot enter a
  protected route.
- The frontend does not decode role information from the JWT. It uses the user
  returned by the backend.

Browser storage is JavaScript-readable. A future production deployment should
review Content Security Policy and consider an HttpOnly-cookie authentication
design if the backend contract changes.

## Validation commands

```bash
npm run lint
npm run build
```

The production output is generated in `frontend/dist`.

## Source structure

```text
src/
├── api/
│   ├── admin.ts
│   ├── auth.ts
│   └── client.ts
├── auth/
│   ├── AuthContext.ts
│   ├── AuthProvider.tsx
│   ├── RouteGuards.tsx
│   └── useAuth.ts
├── components/
│   ├── dashboard/                    Summary cards
│   ├── layout/                       Sidebar and workspace shell
│   ├── map/                          Leaflet map and location detail
│   ├── pills/                        Risk/status/source pills
│   └── shared authentication UI
├── data/prototypeData.ts             Illustrative flood-domain records
├── pages/
│   ├── AdminDashboardPage.tsx
│   ├── AlertsDashboardPage.tsx
│   ├── AdminUsersPage.tsx
│   ├── DashboardPage.tsx
│   ├── LoginPage.tsx
│   ├── NotFoundPage.tsx
│   ├── RegisterPage.tsx
│   ├── RegistrationSubmittedPage.tsx
│   ├── WeatherMapPage.tsx
│   └── WelcomePage.tsx
├── prototype/                        Shared in-memory demo state
├── types/                            Auth and prototype domain types
├── App.tsx
├── App.css
├── prototype.css
├── index.css
└── main.tsx
```
