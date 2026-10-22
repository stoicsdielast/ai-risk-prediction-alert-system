"""Real configured-database smoke, temporary V1 weather and isolated pending alerts.

SYNTHETIC_DEMO_ENABLED=true python -m app.db.prediction_smoke
"""
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.core.config import get_settings
from app.core.security import create_access_token
from app.db.import_v1_weather import import_window
from app.db.session import get_session_factory
from app.main import app
from app.models import (AccountStatus, Alert, DemoWeatherObservation, GeneratedPredictionProvenance,
                        Prediction, SyntheticAlert, SyntheticDataset, SyntheticPrediction,
                        User, UserRole, V1WeatherProfile)
from app.services.v1_model import file_sha256


def main():
    if not get_settings().synthetic_demo_enabled:
        raise RuntimeError("Enable SYNTHETIC_DEMO_ENABLED for this isolated pending-alert smoke")
    factory = get_session_factory()
    source = "inference-smoke-" + uuid4().hex
    timestamp = "2024-07-30T01:00:00Z"
    directory = get_settings().synthetic_model_dir
    artifact_hashes = {path.name: file_sha256(path) for path in directory.iterdir() if path.is_file()}
    with factory() as db:
        admin = db.scalar(select(User).where(User.role == UserRole.MET_ADMIN, User.status == AccountStatus.APPROVED, User.is_active.is_(True)))
        if admin is None:
            raise RuntimeError("An approved MET administrator is required")
        token = create_access_token(admin.id)
        baseline = [db.scalar(select(func.count()).select_from(model)) for model in (Prediction, Alert)]
        imported = import_window(db, Path(__file__).resolve().parents[3] / "ml/data/synthetic_fiji/v1", timestamp, source)
    dataset = imported["dataset_version"]
    try:
        with TestClient(app) as client:
            for location_id in range(1, 13):
                payload = {"location_id": location_id, "timestamp": timestamp, "source": source,
                           "source_type": "synthetic", "research_mode": True, "historical_replay": True}
                response = client.post("/api/predictions/generate", json=payload, headers={"Authorization": f"Bearer {token}"})
                assert response.status_code == 200, response.text
                result = response.json()
                assert result["status"] == "OK", result
                with factory() as db:
                    saved = db.get(SyntheticPrediction, result["prediction_id"])
                    assert saved.probability == result["probability"]
                    assert db.get(GeneratedPredictionProvenance, saved.id).input_sha256 == result["input_sha256"]
                    if location_id == 2:
                        assert result["alert_status"] == "PENDING"
                print(f"location={location_id} probability={result['probability']:.9f} risk={result['risk_category']} alert={result['alert_status']} persisted=verified synthetic=true")
        with factory() as db:
            assert baseline == [db.scalar(select(func.count()).select_from(model)) for model in (Prediction, Alert)]
    finally:
        with factory() as db:
            ids = select(SyntheticPrediction.id).where(SyntheticPrediction.dataset_version == dataset)
            db.execute(delete(GeneratedPredictionProvenance).where(GeneratedPredictionProvenance.prediction_id.in_(ids)))
            db.execute(delete(SyntheticAlert).where(SyntheticAlert.prediction_id.in_(ids)))
            db.execute(delete(SyntheticPrediction).where(SyntheticPrediction.dataset_version == dataset))
            db.execute(delete(V1WeatherProfile).where(V1WeatherProfile.source == source))
            db.execute(delete(DemoWeatherObservation).where(DemoWeatherObservation.source == source))
            db.execute(delete(SyntheticDataset).where(SyntheticDataset.version == dataset))
            db.commit()
    assert artifact_hashes == {path.name: file_sha256(path) for path in directory.iterdir() if path.is_file()}
    print("Temporary smoke rows removed; operational predictions/alerts and every V1 artifact hash unchanged.")


if __name__ == "__main__":
    main()
