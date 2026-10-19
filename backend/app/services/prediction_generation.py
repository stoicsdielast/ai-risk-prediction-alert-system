from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.models.generated_prediction import GeneratedPredictionProvenance
from app.models.synthetic import SyntheticPrediction
from app.schemas.generated_prediction import GeneratedPredictionResponse
from app.services.alert_service import create_alert_from_prediction
from app.services.v1_features import DataUnavailable, build_from_weather, digest
from app.services.weather_service import require_location, utc


def generate(db, request, actor, model):
    location = require_location(db, request.location_id, writing=True)
    if not request.research_mode:
        raise DataUnavailable("V1 is research-only; genuine operational Fiji forecasts are not supported")
    if request.source_type != "synthetic":
        raise DataUnavailable("Genuine measurements cannot use simulator geography/datum assumptions; validated Fiji geography and a compatible model are unavailable")
    if not request.historical_replay and (datetime.now(timezone.utc) - request.timestamp).total_seconds() > get_settings().weather_freshness_minutes * 60:
        raise DataUnavailable("Observation timestamp is stale; use explicit historical_replay only for research")
    features, provenance, dataset_version = build_from_weather(db, request, location, model.features)
    input_hash = digest(provenance)
    identity = (SyntheticPrediction.dataset_version == dataset_version,
                SyntheticPrediction.location_id == request.location_id,
                SyntheticPrediction.observed_at == request.timestamp,
                SyntheticPrediction.model_version == model.metadata["model_version"])

    def existing():
        prediction = db.scalar(select(SyntheticPrediction).where(*identity).with_for_update())
        if prediction:
            saved = db.get(GeneratedPredictionProvenance, prediction.id)
            if saved is None or saved.input_sha256 != input_hash or saved.model_sha256 != model.sha256:
                raise HTTPException(409, "Prediction identity already exists with different input/model provenance")
            return prediction, saved
        return None

    result = existing()
    if result is None:
        probability, category = model.predict(features)
        try:
            with db.begin_nested():
                prediction = SyntheticPrediction(dataset_version=dataset_version, location_id=location.id,
                    observed_at=request.timestamp, model_version=model.metadata["model_version"],
                    probability=probability, risk_category=category)
                db.add(prediction)
                db.flush()
                saved = GeneratedPredictionProvenance(prediction_id=prediction.id, source=request.source,
                    inputs=provenance, input_sha256=input_hash, model_sha256=model.sha256, created_by=actor.id)
                db.add(saved)
                db.flush()
                result = prediction, saved
        except IntegrityError:
            result = existing()
            if result is None:
                raise
    prediction, saved = result
    alert = create_alert_from_prediction(db, prediction, research_actor_id=actor.id)
    # Only this caller commits. Any inference/persistence/alert failure rolls everything back.
    db.commit()
    return GeneratedPredictionResponse(status="OK", location_id=location.id, timestamp=request.timestamp,
        source=request.source, source_type="synthetic", historical_replay=request.historical_replay,
        prediction_id=prediction.id, probability=prediction.probability, risk_category=prediction.risk_category,
        model_version=prediction.model_version, generated_at=utc(saved.generated_at), input_sha256=saved.input_sha256,
        alert_id=alert.id if alert else None, alert_status=alert.status if alert else None)
