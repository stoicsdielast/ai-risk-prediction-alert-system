"""Research replay endpoints; all existing Fiji routes retain their contracts."""
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.research_prediction import ResearchPrediction
from app.models.user import User
from app.schemas.research_prediction import ResearchPredictionRequest, ResearchPredictionResponse
from app.services.research_inference import InvalidResearchInput, ModelUnavailable, load_model, presentation_tier

router = APIRouter(prefix="/api/predictions", tags=["research predictions"])
SOURCE = "https://github.com/Srabon-bot/Bangladesh-flood-data-set"
DISCLAIMER = "Research Proof of Concept — Bangladesh historical replay. Not validated for Fiji or operational public warnings."


def get_research_model():
    return load_model(str(get_settings().research_model_dir.resolve()))


@router.get("/model-info")
def model_info():
    try:
        model = get_research_model()
    except ModelUnavailable as error:
        return {"status": "data_unavailable", "research_mode": True, "reason": str(error), "source": SOURCE, "disclaimer": DISCLAIMER}
    return {"status": "ok", **model.metadata, "feature_schema": model.schema,
            "thresholds": model.thresholds, "license_status": model.provenance["license_status"]}


@router.get("/replay-examples")
def replay_examples():
    try:
        model = get_research_model()
        examples = json.loads((model.directory / "replay_examples.json").read_text())
    except (ModelUnavailable, OSError, ValueError):
        return {"status": "data_unavailable", "research_mode": True, "examples": [], "disclaimer": DISCLAIMER}
    # Labels/expected outputs are evaluation artifacts, never request features.
    return {"status": "ok", "research_mode": True, "disclaimer": model.metadata["disclaimer"],
            "examples": [{k: v for k, v in item.items() if k not in ("observed_proxy_label", "expected_probability")} for item in examples]}


@router.post("/flood-risk", response_model=ResearchPredictionResponse)
def flood_risk(data: ResearchPredictionRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    result = ResearchPredictionResponse(status="data_unavailable", timestamp=data.as_of,
        generated_at=datetime.now(timezone.utc), station_id=data.station_id, source=SOURCE, disclaimer=DISCLAIMER)
    try:
        model = get_research_model()
        result.model_version = model.metadata["model_version"]
        result.disclaimer = model.metadata["disclaimer"]
        probability, missing = model.predict(data)
    except InvalidResearchInput as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ModelUnavailable as error:
        result.reason = str(error)
        return result
    if missing:
        result.missing_features = missing
        result.reason = "Required measurements or historical features are unavailable"
        return result
    result.status = "ok"
    result.probability = probability
    result.presentation_tier = presentation_tier(probability, model.thresholds["presentation_tiers"])
    result.binary_threshold = model.thresholds["binary_threshold"]
    result.binary_prediction = int(probability >= result.binary_threshold)
    # Research runs cannot enter create_alert_from_prediction: separate table,
    # separate geography, no Fiji location_id or alert relationship.
    record = ResearchPrediction(user_id=user.id, station_id=data.station_id,
        model_version=result.model_version, inputs=data.model_dump(mode="json"), result=result.model_dump(mode="json"))
    try:
        db.add(record)
        db.flush()
        result.prediction_id = record.id
        record.result = result.model_dump(mode="json")
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(status_code=503, detail="Unable to persist research prediction; initialize research_predictions table") from error
    return result
