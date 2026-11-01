# Project setup

[Back to the project overview](../README.md)

## Local development

### Prerequisites

- Python **3.14**; the backend declares `requires-python >=3.14`.
- Node.js **20.19 or newer on the 20.x line, or 22.12+**, with npm.
- PostgreSQL and a database user with permission to create tables and types.
- Internet access for dependencies and OpenStreetMap basemap tiles.

Commands assume a POSIX shell and start from the repository root unless a block
changes directory. PostgreSQL is required for the application; SQLite is used
only by isolated backend tests.

### 1. Install dependencies

```bash
python3.14 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt -r ml/requirements.txt

cd frontend
npm ci
cd ..
```

The ML requirements provide the CatBoost and Parquet dependencies needed for
synthetic workflows. Foundation-model benchmarks use separate environments.

### 2. Configure the environment

Create a PostgreSQL user and empty development database using a PostgreSQL
administrator account, for example:

```sql
CREATE USER flood_app WITH PASSWORD 'choose-a-local-password';
CREATE DATABASE fiji_flood_risk OWNER flood_app;
```

Copy the examples only when local configuration does not already exist:

```bash
test -f backend/.env || cp backend/.env.example backend/.env
test -f frontend/.env || cp frontend/.env.example frontend/.env
```

In `backend/.env`, set `DATABASE_URL` to your PostgreSQL connection and replace
`JWT_SECRET_KEY` with a unique secret. Generate a value with:

```bash
backend/.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(48))"
```

For local development, use `VITE_API_URL=http://127.0.0.1:8000` in `frontend/.env`.
Environment files are ignored by Git. Browser-visible `VITE_` variables must
never contain database credentials or JWT signing secrets.

### 3. Initialize a fresh development database

The Alembic history assumes that core application tables already exist. For an
**empty database only**, create the current schema, record its migration version
and seed the registry:

```bash
cd backend
.venv/bin/python - <<'PY'
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from app import models
from app.db.base import Base
from app.db.session import get_engine, get_session_factory
from app.db.seed_locations import seed_demo_locations

engine = get_engine()
with engine.begin() as connection:
    if inspect(connection).get_table_names():
        raise SystemExit("Database is not empty. Apply migrations instead.")
    Base.metadata.create_all(connection)
command.stamp(Config("alembic.ini"), "head")
with get_session_factory()() as db:
    seed_demo_locations(db)
PY
```

The seed includes labelled sample risks. It does not import weather, train a
model or issue alerts. Re-running it resets seed locations and sample predictions,
so use it deliberately on an existing database.

For an **existing initialized database**, apply migrations from `backend/`:

```bash
.venv/bin/python -m alembic upgrade head
```

Do not stamp an existing database to skip migrations. The legacy `app.db.init_db`
utility uses `create_all`; it cannot replace migrations for an existing schema.
Starting uvicorn does not initialize or migrate tables.

### 4. Start the application

From `backend/`:

```bash
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal, from the repository root:

```bash
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

- Application: <http://127.0.0.1:5173>
- API health: <http://127.0.0.1:8000/api/health>
- Interactive API documentation: <http://127.0.0.1:8000/docs>

The backend permits frontend origins on `localhost:5173` and `127.0.0.1:5173`.
Use the fixed port above to match that CORS configuration.

### 5. Set up the first administrator

Register an account requesting `MET_ADMIN` through `/register`. New accounts
start as `PENDING` and cannot sign in until approved. The first administrator
must be approved through the documented
[database bootstrap procedure](../backend/README.md#bootstrap-the-first-met-admin-for-development);
there is intentionally no public bootstrap API. That administrator can then
review later account requests in the application.

## Historical analysis and synthetic model setup

Authentication, registry views and alert management can run without a synthetic
model bundle. Historical analysis and V1 inference require locally prepared data
and published artifacts.

The approved V1 reproduction sequence runs from the repository root:

```bash
backend/.venv/bin/python -m ml.synthetic.generate --out ml/data/synthetic_fiji/v1 --seed 314
backend/.venv/bin/python -m ml.synthetic.train --dataset ml/data/synthetic_fiji/v1 --out ml/runs/synthetic-v1
backend/.venv/bin/python -m ml.synthetic.report --out ml/runs/synthetic-v1 --publish ml/artifacts/synthetic/v1
```

These outputs refuse overwrite. Run the sequence only when the output paths are
absent; preserve existing published V1 artifacts and use separate directories for
additional research runs. The [methodology guide](SYNTHETIC_METHODOLOGY.md#9-reproduction-commands)
documents evaluation, stress testing and limitations.

Once the dataset and bundle are available, import historical replay records
from `backend/`:

```bash
.venv/bin/python -m alembic upgrade head
.venv/bin/python -m app.db.import_synthetic --dataset ../ml/data/synthetic_fiji/v1
```

The importer checks dataset integrity and registry identity. Historical replay
storage is separate from the weather API's tables; map weather details can remain
empty until observations are ingested. See [weather data management](WEATHER_DATA_MANAGEMENT.md)
and the [stored-weather V1 workflow](V1_PREDICTION_WORKFLOW.md) for ingestion
and bounded weather imports.

### Optional workflows

Configure these in `backend/.env` and restart the relevant process:

| Setting | Default | Purpose |
| --- | --- | --- |
| `SYNTHETIC_DEMO_ENABLED` | `false` | Permit administrator creation/approval of isolated historical-analysis alerts, including explicit low-risk tests. |
| `ALERT_DEMO_ENABLED` | `false` | Permit older, explicitly marked alert-workflow fixtures. These remain identified as simulated records. |
| `BROWSER_DELIVERY_ENABLED` | `false` | Permit browser delivery for subscribed accounts with notification consent. The site must remain open. |
| `WEATHER_INGESTION_ENABLED` | `false` | Enable the separately run ingestion worker after a feed has been configured. |
| `WEATHER_FEED_SYNTHETIC` | `true` | Identify feed records as synthetic; genuine attribution is reserved for actual observations. |
| `ALERT_TTL_HOURS` | `24` | Set the lifetime of newly approved operational alerts. |
| `ALERT_COOLDOWN_HOURS` | `6` | Coalesce repeated automatic recommendations, with the existing severity-escalation exception. |

To test alerts, sign in as an approved MET administrator, open **Historical
analysis**, load an eligible hour and create a simulated or explicitly marked
test alert. Operational alerts are managed under **Manage alerts**; historical
analysis alerts have a separate management area. Both support acknowledgement,
resolution, confirmed cancellation and retained history. See
[Alert management](ALERT_MANAGEMENT.md) for the full lifecycle and API rules.

## Verification

Backend API and service tests use in-memory SQLite overrides. From `backend/`:

```bash
.venv/bin/python -m pytest tests -q
```

To exercise real PostgreSQL migrations, concurrency and persistence:

```bash
WEATHER_POSTGRES_TEST=1 .venv/bin/python -m pytest weather_tests -q
```

These integration tests use disposable schemas in the configured PostgreSQL
database; the database user needs permission to create schemas. Some other tests
require optional artifacts or their documented environment settings.

Frontend checks run from `frontend/`:

```bash
npm run lint
npm run test
npm run build
```

The production build includes TypeScript checks. ML tests run from the repository
root using an environment with `ml/requirements.txt` installed:

```bash
backend/.venv/bin/python -m pytest ml/tests -q
```
