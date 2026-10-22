"""Real enum migration, concurrent duplicates and audit preservation in a temporary schema."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from weather_tests.test_postgres import postgres, pytestmark  # noqa: F401
from app.api.routes.synthetic import get_synthetic_model
from app.core.config import get_settings
from app.main import app
from app.models import Alert, Location, User
from app.models.synthetic import SyntheticAlert, SyntheticDataset, SyntheticObservation


def test_additive_migration_preserves_existing_operational_records(postgres):
    engine, factory, headers = postgres
    with TestClient(app) as client:
        with factory() as db:
            location_id = db.scalar(select(Location.id))
            users = db.scalar(select(func.count()).select_from(User))
        draft = client.post('/api/admin/alerts', headers=headers, json={
            'location_id': location_id, 'severity': 'HIGH', 'message': 'Migration fixture only'}).json()
        approved = client.patch(f"/api/admin/alerts/{draft['id']}/approve", headers=headers).json()
        command.downgrade(Config('alembic.ini'), '20261023_notifications')
        # Seed data and an approved alert exist BEFORE the migration being tested.
        with engine.connect() as conn:
            assert conn.scalar(text('SELECT count(*) FROM alerts')) == 1
        command.upgrade(Config('alembic.ini'), 'head')
        preserved = client.get(f"/api/admin/alerts/{draft['id']}", headers=headers).json()
        assert all(preserved[key] == approved[key] for key in ('id', 'message', 'approved_at', 'approved_by_user_id', 'expires_at'))
        assert preserved['closed_at'] is None
        assert client.patch(f"/api/admin/alerts/{draft['id']}/resolve", headers=headers, json={'reason': 'Test complete'}).status_code == 200
        with pytest.raises(RuntimeError, match='audit exists'):
            command.downgrade(Config('alembic.ini'), '20261023_notifications')
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(User)) == users
            assert db.get(Alert, draft['id']).closure_reason == 'Test complete'


def test_concurrent_synthetic_test_creation_reuses_one_persisted_alert(postgres, monkeypatch):
    _, factory, headers = postgres
    monkeypatch.setattr(get_settings(), 'synthetic_demo_enabled', True)
    stamp = datetime(2025, 1, 15, 12, tzinfo=timezone.utc)
    with factory() as db:
        location_id = db.scalar(select(Location.id).where(Location.slug == 'suva'))
        db.add(SyntheticDataset(version='synthetic-fiji-v1', metadata_json={'config': {}}, observation_count=1))
        db.flush()
        db.add(SyntheticObservation(dataset_version='synthetic-fiji-v1', location_id=location_id, observed_at=stamp, values={}))
        db.commit()
    class Model:
        def predict(self, location_id, timestamp):
            return {'status': 'ok', 'probability': .1, 'risk_category': 'LOW', 'model_version': 'pg-test-fixture'}
    app.dependency_overrides[get_synthetic_model] = Model
    with TestClient(app) as client:
        def create(_):
            return client.post('/api/synthetic/admin/alerts', headers=headers, json={
                'location_id': location_id, 'timestamp': stamp.isoformat(), 'test_alert': True})
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create, range(2)))
        assert all(response.status_code == 201 for response in results), [response.text for response in results]
        assert len({response.json()['id'] for response in results}) == 1
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SyntheticAlert)) == 1
        assert db.scalar(select(func.count()).select_from(Alert)) == 0
