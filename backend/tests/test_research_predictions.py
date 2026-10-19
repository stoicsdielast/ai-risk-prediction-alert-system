import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token
from app.models.alert import Alert
from app.models.prediction import Prediction
from app.models.research_prediction import ResearchPrediction
from app.services.research_inference import ModelUnavailable, ResearchModel, load_model, presentation_tier


@pytest.fixture
def research_artifacts(tmp_path, monkeypatch):
    # Tiny synthetic software-test model. Never used as research evidence.
    features = ["rainfall_local_mm", "latitude", "longitude"]
    data = pd.DataFrame({features[0]: np.arange(20), "latitude": 23., "longitude": 90.})
    pipeline = Pipeline([("scale", StandardScaler()), ("classifier", LogisticRegression())]).fit(data, np.arange(20) > 10)
    joblib.dump(pipeline, tmp_path / "classifier.joblib")
    contents = {
        "model_metadata.json": {"research_mode": True, "smoke_only": False, "model_version": "synthetic-test-only", "disclaimer": "Research only",
             "classifier_sha256": hashlib.sha256((tmp_path / "classifier.joblib").read_bytes()).hexdigest(), "versions": {"scikit-learn": sklearn.__version__}},
        "feature_schema.json": {"features": features},
        "thresholds.json": {"binary_threshold": .6, "presentation_tiers": {"MODERATE": .25, "HIGH": .5, "VERY_HIGH": .75}},
        "stations.json": {"A": {"latitude": 23, "longitude": 90}},
        "provenance.json": {"license_status": "Unresolved"},
        "replay_examples.json": [],
    }
    for name, content in contents.items(): (tmp_path / name).write_text(json.dumps(content))
    monkeypatch.setenv("RESEARCH_MODEL_DIR", str(tmp_path))
    get_settings.cache_clear(); load_model.cache_clear()
    yield tmp_path
    load_model.cache_clear()


@pytest.fixture
def payload():
    return {"mode": "historical_replay", "country": "Bangladesh", "station_id": "A",
            "feature_date": "2024-05-01", "as_of": "2024-05-01T23:59:59Z",
            "features": {"rainfall_local_mm": 18., "latitude": 23., "longitude": 90.}}


@pytest.fixture
def authorization(user_factory):
    user = user_factory(email="research@example.com")
    return {"Authorization": "Bearer " + create_access_token(user.id)}


def test_research_info_and_authenticated_persisted_inference(client, db, research_artifacts, payload, authorization):
    info = client.get("/api/predictions/model-info")
    assert info.status_code == 200 and info.json()["research_mode"] is True
    response = client.post("/api/predictions/flood-risk", json=payload, headers=authorization)
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "ok" and result["country"] == "Bangladesh" and result["research_mode"]
    assert 0 <= result["probability"] <= 1 and result["prediction_id"] > 0
    assert result["prediction_horizon_hours"] == 24
    assert db.scalar(select(func.count()).select_from(ResearchPrediction)) == 1
    assert db.scalar(select(func.count()).select_from(Prediction)) == 0
    assert db.scalar(select(func.count()).select_from(Alert)) == 0


def test_requires_approved_authentication(client, research_artifacts, payload):
    assert client.post("/api/predictions/flood-risk", json=payload).status_code == 401


def test_missing_history_is_data_unavailable_without_persistence(client, db, research_artifacts, payload, authorization):
    del payload["features"]["rainfall_local_mm"]
    response = client.post("/api/predictions/flood-risk", json=payload, headers=authorization)
    assert response.json()["status"] == "data_unavailable"
    assert response.json()["missing_features"] == ["rainfall_local_mm"]
    assert response.json()["probability"] is None
    assert db.scalar(select(func.count()).select_from(ResearchPrediction)) == 0


@pytest.mark.parametrize("change", ["target", "coordinates", "negative", "overflow", "bool", "string", "timestamp", "naive_time", "country", "station"])
def test_rejects_leaking_or_invalid_inputs(client, research_artifacts, payload, authorization, change):
    if change == "target": payload["features"]["flood_byStor"] = 1
    elif change == "coordinates": payload["features"]["latitude"] = -18
    elif change == "negative": payload["features"]["rainfall_local_mm"] = -1
    elif change == "overflow": payload["features"]["rainfall_local_mm"] = 10 ** 400
    elif change == "bool": payload["features"]["rainfall_local_mm"] = True
    elif change == "string": payload["features"]["rainfall_local_mm"] = "18"
    elif change == "timestamp": payload["as_of"] = "2024-05-01T12:00:00Z"
    elif change == "naive_time": payload["as_of"] = "2024-05-01T23:59:59"
    elif change == "country": payload["country"] = "Fiji"
    elif change == "station": payload["station_id"] = "UNKNOWN"
    assert client.post("/api/predictions/flood-risk", json=payload, headers=authorization).status_code == 422


def test_corrupt_artifact_returns_controlled_unavailable(client, research_artifacts, payload, authorization):
    (research_artifacts / "classifier.joblib").write_bytes(b"corrupt")
    response = client.post("/api/predictions/flood-risk", json=payload, headers=authorization)
    assert response.status_code == 200 and response.json()["status"] == "data_unavailable"
    assert response.json()["probability"] is None


def test_persistence_failure_rolls_back_without_success(client, db, research_artifacts, payload, authorization, monkeypatch):
    def fail_flush(*args, **kwargs):
        raise SQLAlchemyError("synthetic persistence failure")
    monkeypatch.setattr(Session, "flush", fail_flush)
    response = client.post("/api/predictions/flood-risk", json=payload, headers=authorization)
    assert response.status_code == 503
    assert db.scalar(select(func.count()).select_from(ResearchPrediction)) == 0


def test_threshold_boundaries_and_invalid_config(research_artifacts):
    levels = {"MODERATE": .25, "HIGH": .5, "VERY_HIGH": .75}
    assert [presentation_tier(p, levels) for p in [0, .249, .25, .5, .75, 1]] == ["LOW", "LOW", "MODERATE", "HIGH", "VERY_HIGH", "VERY_HIGH"]
    path = research_artifacts / "thresholds.json"
    content = json.loads(path.read_text()); content["presentation_tiers"]["HIGH"] = .1; path.write_text(json.dumps(content))
    with pytest.raises(ModelUnavailable): load_model(str(research_artifacts))


def test_real_saved_model_replay_parity_when_available(client, monkeypatch, payload, authorization):
    directory = Path(__file__).resolve().parents[2] / "ml/artifacts"
    if not (directory / "classifier.joblib").exists(): pytest.skip("Run python -m ml.train for real-artifact integration")
    monkeypatch.setenv("RESEARCH_MODEL_DIR", str(directory)); get_settings.cache_clear(); load_model.cache_clear()
    for example in json.loads((directory / "replay_examples.json").read_text()):
        request = {key: example[key] for key in ("mode", "country", "feature_date", "as_of", "features")}
        request["station_id"] = example["station"]["station_id"]
        response = client.post("/api/predictions/flood-risk", json=request, headers=authorization)
        assert response.status_code == 200 and response.json()["status"] == "ok"
        assert response.json()["probability"] == pytest.approx(example["expected_probability"])
    public = client.get("/api/predictions/replay-examples").json()
    assert all("observed_proxy_label" not in e and "expected_probability" not in e for e in public["examples"])
