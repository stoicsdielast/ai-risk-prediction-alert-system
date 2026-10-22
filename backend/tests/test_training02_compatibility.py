"""Optional real-artifact compatibility, without changing the active model path."""
import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.security import create_access_token
from app.models.alert import Alert
from app.models.prediction import Prediction
from app.models.research_prediction import ResearchPrediction
from app.services.research_inference import load_model


@pytest.fixture
def training02(monkeypatch):
    directory = Path(__file__).resolve().parents[2] / "ml/runs/training-02"
    if not (directory / "model_metadata.json").exists():
        pytest.skip("Run all training-02 stages for calibrated real-artifact integration")
    monkeypatch.setenv("RESEARCH_MODEL_DIR", str(directory))
    get_settings.cache_clear(); load_model.cache_clear()
    yield directory
    get_settings.cache_clear(); load_model.cache_clear()


@pytest.mark.parametrize("example_id", ["normal", "high_risk"])
def test_new_artifact_uses_existing_authenticated_api(client, db, user_factory, training02, example_id):
    examples = json.loads((training02 / "replay_examples.json").read_text())
    example = next(row for row in examples if row["id"] == example_id)
    payload = {key: example[key] for key in ["mode", "country", "feature_date", "as_of", "features"]}
    payload["station_id"] = example["station"]["station_id"]
    user = user_factory(email="training02@example.com")
    response = client.post("/api/predictions/flood-risk", json=payload,
                           headers={"Authorization": "Bearer " + create_access_token(user.id)})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "ok" and result["research_mode"] is True
    assert result["probability"] == pytest.approx(example["expected_probability"])
    assert result["country"] == "Bangladesh" and result["model_version"].startswith("bd-research-02-")
    assert db.scalar(select(func.count()).select_from(ResearchPrediction)) == 1
    assert db.scalar(select(func.count()).select_from(Prediction)) == 0
    assert db.scalar(select(func.count()).select_from(Alert)) == 0
    info = client.get("/api/predictions/model-info").json()
    assert info["feature_schema"]["features"] == list(payload["features"])


def test_signed_trends_are_accepted_when_in_selected_schema(client, user_factory, training02):
    example = json.loads((training02 / "replay_examples.json").read_text())[0]
    signed = [key for key in example["features"] if key.startswith(("discharge_change", "soil_water_change"))]
    if not signed:
        pytest.skip("Validation selected the original feature set; extended signed features are not served")
    payload = {key: example[key] for key in ["mode", "country", "feature_date", "as_of", "features"]}
    payload["station_id"] = example["station"]["station_id"]
    payload["features"][signed[0]] = -1.
    user = user_factory(email="signed-trend@example.com")
    response = client.post("/api/predictions/flood-risk", json=payload,
                           headers={"Authorization": "Bearer " + create_access_token(user.id)})
    assert response.status_code == 200 and response.json()["status"] == "ok"
