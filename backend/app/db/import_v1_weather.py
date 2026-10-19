"""Import a bounded, verified V1 weather window into the new weather workflow.

No generated labels/features are imported. Geography remains explicitly assumed.
Run from backend: python -m app.db.import_v1_weather --timestamp 2024-07-10T00:00:00Z
"""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
from sqlalchemy import func, select

from app.db.session import get_session_factory
from app.models.generated_prediction import V1WeatherProfile
from app.models.location import Location
from app.models.synthetic import SyntheticDataset
from app.models.weather import DemoWeatherObservation
from app.schemas.weather import WeatherCreate
from app.services.v1_features import CONTRACT, DATUM, GEO, RAW
from app.services.v1_model import file_sha256
from app.services.weather_service import insert_observation


def import_window(db, directory, timestamp, source="synthetic-fiji-v1-weather"):
    directory = Path(directory)
    metadata = json.loads((directory / "dataset_metadata.json").read_text())
    if (metadata.get("dataset_version") != "synthetic-fiji-v1" or metadata.get("source_type") != "synthetic"
            or metadata.get("config", {}).get("frequency") != "1h" or metadata.get("timezone") != "UTC"):
        raise ValueError("Only the original hourly UTC V1 synthetic dataset is supported")
    for name in ("locations.csv", "weather_observations.parquet"):
        if file_sha256(directory / name) != metadata["file_sha256"][name]:
            raise ValueError(f"Dataset checksum mismatch: {name}")
    timestamp = pd.Timestamp(timestamp)
    if timestamp.tzinfo is None or timestamp != timestamp.floor("h"):
        raise ValueError("Choose an exact offset-aware hour")
    timestamp = timestamp.tz_convert("UTC")
    registry = pd.read_csv(directory / "locations.csv")
    actual = {row.id: row for row in db.scalars(select(Location).where(Location.is_active.is_(True)))}
    if set(actual) != set(registry.location_id):
        raise ValueError("Dataset must match all 12 active registry locations")
    for row in registry.itertuples():
        loc = actual[row.location_id]
        if (loc.slug != row.slug or loc.latitude != row.latitude or loc.longitude != row.longitude):
            raise ValueError("Dataset identity/geography does not match registry")
    weather = pd.read_parquet(directory / "weather_observations.parquet", filters=[
        ("timestamp", ">=", timestamp - pd.Timedelta(hours=174)), ("timestamp", "<=", timestamp)])
    if len(weather) != len(actual) * 175 or weather.groupby("location_id").size().ne(175).any():
        raise ValueError("Requested window does not have 175 hours for every location")
    dataset_version = "weather-v1-" + hashlib.sha256(source.encode()).hexdigest()[:32]
    provenance = {"source_type": "synthetic", "contract": CONTRACT,
                  "dataset_metadata_sha256": file_sha256(directory / "dataset_metadata.json"),
                  "locations_sha256": metadata["file_sha256"]["locations.csv"],
                  "observations_sha256": metadata["file_sha256"]["weather_observations.parquet"],
                  "gauge_datum": DATUM, "geography_type": "declared_simulator_assumptions"}
    dataset = db.get(SyntheticDataset, dataset_version)
    if dataset is None:
        dataset = SyntheticDataset(version=dataset_version, metadata_json={**provenance, "config": metadata["config"]}, observation_count=0)
        db.add(dataset)
        db.flush()
    elif dataset.metadata_json.get("dataset_metadata_sha256") != provenance["dataset_metadata_sha256"]:
        raise ValueError("Source already belongs to a different dataset")
    for row in registry.to_dict(orient="records"):
        profile = db.get(V1WeatherProfile, (source, int(row["location_id"])))
        attributes = {key: float(row[key]) for key in GEO}
        if profile is None:
            db.add(V1WeatherProfile(source=source, location_id=int(row["location_id"]),
                                   dataset_version=dataset_version, attributes=attributes, provenance=provenance))
        elif profile.attributes != attributes or profile.provenance != provenance:
            raise ValueError("Existing source profile differs; refusing overwrite")
    db.flush()
    created = 0
    for row in weather.to_dict(orient="records"):
        values = {("wind_speed_mps" if key == "wind_speed_ms" else key):
                  None if pd.isna(row[key]) else float(row[key]) for key in RAW}
        values.update(location_id=int(row["location_id"]), observed_at=row["timestamp"].to_pydatetime(),
                      source=source, source_type="synthetic", gauge_datum=DATUM,
                      rainfall_period_minutes=60 if values["rainfall_mm"] is not None else None,
                      upstream_rainfall_period_minutes=60 if values["upstream_rainfall_mm"] is not None else None)
        _, inserted = insert_observation(db, WeatherCreate(**values))
        created += inserted
    dataset.observation_count = db.scalar(select(func.count()).select_from(DemoWeatherObservation).where(DemoWeatherObservation.source == source))
    db.commit()
    return {"created": created, "source": source, "timestamp": timestamp.isoformat(),
            "dataset_version": dataset_version, "source_type": "synthetic"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("../ml/data/synthetic_fiji/v1"))
    parser.add_argument("--timestamp", required=True)
    parser.add_argument("--source", default="synthetic-fiji-v1-weather")
    args = parser.parse_args()
    with get_session_factory()() as db:
        print(json.dumps(import_window(db, args.dataset, args.timestamp, args.source)))


if __name__ == "__main__":
    main()
