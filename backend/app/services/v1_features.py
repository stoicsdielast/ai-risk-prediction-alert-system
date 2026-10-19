"""Frozen V1 causal feature contract, parity-tested against ml.synthetic.features.

No truth/labels, replay feature parquet, or future weather are read here.
"""
from datetime import timedelta
import hashlib
import json

import numpy as np
import pandas as pd
from sqlalchemy import select

from app.models.generated_prediction import V1WeatherProfile
from app.models.weather import DemoWeatherObservation
from app.services.weather_service import utc

RAW = ["rainfall_mm", "temperature_c", "humidity_pct", "pressure_hpa", "wind_speed_ms",
       "wind_direction_deg", "soil_moisture_pct", "river_level_m", "river_discharge_m3s",
       "upstream_rainfall_mm", "coastal_tide_m"]
GEO = ["latitude", "longitude", "elevation_m", "catchment_area_km2", "slope_pct",
       "drainage_capacity_mm_h", "river_proximity_km", "coastal_influence"]
DATUM = "synthetic-fiji-v1-simulated-datum"
CONTRACT = "synthetic-fiji-v1-hourly-v1"


class DataUnavailable(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def feature_row(frame, attributes, feature_names):
    """175 contiguous hours include six-hour recovery before the 168h window.

    The stricter service coverage rule avoids dependence on an unknown carry-in value.
    Missing *measurements* within covered hours follow V1's fitted missingness policy.
    """
    if len(frame) != 175 or not frame.timestamp.is_monotonic_increasing or frame.timestamp.duplicated().any():
        raise DataUnavailable("175 contiguous hourly observations are required")
    if not frame.timestamp.diff().iloc[1:].eq(pd.Timedelta(hours=1)).all():
        raise DataUnavailable("Missing hourly history; irregular samples cannot substitute for V1 hourly windows")
    missing = [key for key in GEO if key not in attributes or attributes[key] is None or not np.isfinite(attributes[key])]
    if missing:
        raise DataUnavailable("Missing required static attributes: " + ", ".join(missing))
    frame = frame.copy()
    for name in RAW:
        if name not in frame or frame[name].notna().sum() == 0:
            raise DataUnavailable(f"Required sensor channel unavailable: {name}")
        if np.isinf(frame[name].to_numpy(dtype=float)).any():
            raise DataUnavailable(f"Non-finite sensor input: {name}")
        frame[name + "_missing"] = frame[name].isna().astype("int8")
    frame[RAW] = frame[RAW].ffill(limit=6)
    for name in ("rainfall_mm", "upstream_rainfall_mm"):
        for hours in (3, 6, 24, 72, 168):
            frame[f"{name}_total_{hours}h"] = frame[name].rolling(hours, min_periods=max(1, hours // 2)).sum()
    for name in ("river_level_m", "river_discharge_m3s", "soil_moisture_pct"):
        for hours in (3, 6, 24):
            frame[f"{name}_change_{hours}h"] = frame[name].diff(hours)
        frame[name + "_mean_24h"] = frame[name].rolling(24, min_periods=1).mean()
    for name in GEO:
        frame[name] = attributes[name]
    frame["month_sin"] = np.sin(2 * np.pi * frame.timestamp.dt.month / 12)
    frame["month_cos"] = np.cos(2 * np.pi * frame.timestamp.dt.month / 12)
    frame["hour_sin"] = np.sin(2 * np.pi * frame.timestamp.dt.hour / 24)
    frame["hour_cos"] = np.cos(2 * np.pi * frame.timestamp.dt.hour / 24)
    names = [name for name in frame if name != "timestamp"]
    if names != feature_names:
        raise DataUnavailable("Deployed model feature names/order do not match the frozen V1 contract")
    return frame.iloc[[-1]][feature_names]


def build_from_weather(db, request, location, feature_names):
    profile = db.get(V1WeatherProfile, (request.source, request.location_id))
    if profile is None:
        raise DataUnavailable("Missing source-specific V1 geography/datum profile; registry coordinates alone are insufficient")
    if profile.provenance.get("contract") != CONTRACT or profile.provenance.get("source_type") != "synthetic":
        raise DataUnavailable("Source profile is not the verified V1 synthetic hourly contract")
    if profile.attributes.get("latitude") != location.latitude or profile.attributes.get("longitude") != location.longitude:
        raise DataUnavailable("Source geography does not match the monitored registry")
    start = request.timestamp - timedelta(hours=174)
    query = select(DemoWeatherObservation).where(
        DemoWeatherObservation.location_id == request.location_id,
        DemoWeatherObservation.source == request.source,
        DemoWeatherObservation.observed_at >= start,
        DemoWeatherObservation.observed_at <= request.timestamp,
    )
    if not request.historical_replay:
        query = query.where(DemoWeatherObservation.received_at <= request.timestamp)
    rows = list(db.scalars(query.order_by(DemoWeatherObservation.observed_at)))
    if len(rows) != 175 or utc(rows[-1].observed_at) != request.timestamp:
        raise DataUnavailable("Insufficient history: need 175 contiguous hours ending at the requested timestamp; late arrivals excluded outside explicit replay")
    records = []
    for row in rows:
        if row.gauge_datum != DATUM:
            raise DataUnavailable("Missing or incompatible river/tide datum; V1 expects its declared simulated datum")
        for amount, period in ((row.rainfall_mm, row.rainfall_period_minutes),
                               (row.upstream_rainfall_mm, row.upstream_rainfall_period_minutes)):
            if amount is not None and period != 60:
                raise DataUnavailable("V1 requires rainfall and upstream rainfall in mm per 60-minute interval")
        records.append({"timestamp": utc(row.observed_at), **{
            name: getattr(row, "wind_speed_mps" if name == "wind_speed_ms" else name) for name in RAW}})
    frame = pd.DataFrame(records)
    features = feature_row(frame, profile.attributes, feature_names)
    provenance = {
        "source_type": "synthetic", "research_mode": True, "contract": CONTRACT,
        "history_start": start.isoformat(), "history_end": request.timestamp.isoformat(),
        "observation_ids": [row.id for row in rows], "source": request.source,
        "profile": profile.provenance, "attributes": profile.attributes,
        "historical_replay": request.historical_replay,
        "features": {name: None if pd.isna(value) else float(value) for name, value in features.iloc[0].items()},
        "raw_history_sha256": digest(json.loads(frame.to_json(orient="records", date_format="iso", double_precision=15))),
    }
    return features, provenance, profile.dataset_version
