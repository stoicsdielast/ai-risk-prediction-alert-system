# AGENTS.md

## Repository layout

Multi-part student project; not a monorepo with shared tooling. Each part has its own dependencies and commands.

- `frontend/` — React + TypeScript + Vite app (Tailwind 4, Leaflet, react-router)
- `backend/` — FastAPI app (`backend/app/`), plus a standalone AI package (`backend/ai/`) that does not import app settings or register routes
- `ml/` — separate Bangladesh historical research benchmark (own pinned deps, own venv expectations), now also home to `ml/synthetic/`, the approved synthetic Fiji simulator/training pipeline (`docs/SYNTHETIC_METHODOLOGY.md`)
- `docs/` — guides; root `README.md` links the important ones
- Root `ai/` and `database/` are empty placeholders; `archive/` holds the Kaggle India CSV used by `backend/ai`

Three AI codebases exist and are not interchangeable: `backend/ai` (India 12-feature pipeline), `ml/` (Bangladesh benchmark), `ml/synthetic` (Fiji simulator). Do not merge their schemas, data, or artifacts.

## Commands (verified)

Backend tests (from `backend/`, uses in-memory SQLite via conftest overrides — no PostgreSQL needed):

```bash
.venv/bin/python -m pytest tests -q                 # app API tests
.venv/bin/python -m pytest tests ai/tests -q        # include backend/ai tests
```

ML tests (from repo root; `backend/.venv` also works — no `ml/.venv` exists by default):

```bash
backend/.venv/bin/python -m pytest ml/tests -q
```

Frontend (from `frontend/`):

```bash
npm run lint        # oxlint
npm run test        # vitest, single run (59 tests)
npm run build       # tsc -b && vite build — run after lint when verifying
```

There is no repo-wide lint/typecheck, no CI workflows, and no pre-commit config.

## Backend runtime gotchas

- Run all backend commands from `backend/` or imports fail (`No module named 'app'`).
- Requires PostgreSQL and `backend/.env` (copy from `.env.example`). App settings reject SQLite URLs; SQLite is only used inside tests.
- Starting uvicorn does NOT create tables. Initialize explicitly:
  `python -m app.db.init_db`, then seed demo data with `python -m app.db.seed_locations`.
- No Alembic yet; `init_db` uses `create_all` and will not alter existing tables. Introduce Alembic before any deployed schema change.
- CORS origins are hardcoded to `http://localhost:5173` and `http://127.0.0.1:5173` in `backend/app/main.py`. The frontend must run there: `npm run dev -- --host 127.0.0.1 --port 5173 --strictPort`.
- `ALERT_DEMO_ENABLED` (default `false`) gates demo fixtures; tests force it off.
- `RESEARCH_MODEL_DIR` optionally points at model artifacts; defaults to `ml/artifacts` relative to backend.
- Bootstrap of the first MET admin is manual SQL (documented in `backend/README.md`); there is intentionally no API for it.
- Python is 3.14 in `backend/.venv`; `pyproject.toml` requires `>=3.14` (the README's "3.11 or newer" is stale).

## ML pipeline quirks

- Run modules from the repo root: `python -m ml.download`, `python -m ml.train`, `python -m ml.report` (with the ml venv or backend venv after installing `ml/requirements.txt`).
- The finalized `ml/runs/` output refuses overwrite; reproduction runs must use `--out ml/runs/reproduction`.
- `ml/.venv/bin/python -m ml.download --offline` revalidates existing downloads without network.
- Results are Bangladesh proxy labels; never present them as validated Fiji forecasts (this constraint appears throughout docs — preserve it).

## Synthetic Fiji pipeline (ml/synthetic)

- Generate/train/report/stress run from the repo root with `backend/.venv`: `python -m ml.synthetic.generate|train|report|stress`. Outputs refuse overwrite; use fresh directories.
- Serving bundle is published to `ml/artifacts/synthetic/v1/` (gitignored) and consumed by `backend/app/services/synthetic_inference.py`; import via `python -m app.db.import_synthetic` after `alembic upgrade head`.
- `SYNTHETIC_DEMO_ENABLED=true` gates the isolated synthetic alert demo; default false. Synthetic tables/feeds are separate from operational predictions/alerts.
- Every synthetic view/response must carry `source_type='synthetic'` and the research-demonstration notice. Never present simulator output as Fiji MET readings or real forecast skill.
- Locations come only from the existing PostgreSQL registry (`ml/synthetic/locations.csv` mirrors it); never invent monitoring locations.
- **V3 scenario study is research-only; nothing is promoted — deployed model stays V1.** Protocol in `docs/SYNTHETIC_V3_PROTOCOL.md`, numbers in `docs/SYNTHETIC_V3_RESULTS.md`. Train/tune per scenario with `python -m ml.synthetic.train_v3`, pre-registered baselines + OOD transfer with `python -m ml.synthetic.transfer_v3` (all `backend/.venv`, repo root, refuse-overwrite). Research bundles published with `python -m ml.synthetic.finalize_v3`; served read-only via `GET /api/synthetic/research/*` (`SYNTHETIC_RESEARCH_DIR`, default `ml/artifacts/synthetic/v3`) and shown at frontend `/research`. Do not touch v1 serving (`ml/artifacts/synthetic/v1`, `backend/app/services/synthetic_inference.py`).
- Bounded foundation-model benchmark (`python -m ml.synthetic.foundation_v3 --model {tabicl,tabfm}`) runs only in its own venvs (`ml/envs/*`), uses a label-blind context budget and never trains on the full partition. Results are a bounded comparison, not full-partition scores; tabpfn needs a licensed checkpoint and is skipped by default. Do not treat foundation rows as promotion candidates.

## Frontend conventions

- Live backend surface is only auth, admin account review, locations, predictions replay, alerts APIs, and the read-only synthetic research endpoints (`/api/synthetic/research/*`, shown at `/research`). Weather observations, dashboard metrics, map risk markers, and alert demo actions are local prototype data from `src/data/prototypeData.ts` and `src/prototype/`. Label screens accordingly when presenting or extending (see `docs/PROTOTYPE_UI.md`).
- JWT stored in `sessionStorage`; role comes from `GET /api/auth/me`, never decoded from the token.
- Tests live next to source (`*.test.ts(x)`), jsdom env, setup in `src/test/setup.ts`.

## Git workflow

- Per-person feature branches (`parvish-dev`, `louvatu`, `aryan`, `atharv`, `rishi`) merged into `main` via PRs.
- Commit style is conventional commits with scopes: `feat(alerts):`, `fix(auth):`, `feat(ai):`.

## Docs worth reading before big changes

- `backend/README.md` — full auth/alert API contract and troubleshooting
- `docs/PROTOTYPE_UI.md` — live-vs-demo boundary for the UI
- `docs/RESEARCH_BANGLADESH.md` — ml pipeline contract and limitations
- `docs/ALERT_SYSTEM.md` — alert lifecycle and endpoints
