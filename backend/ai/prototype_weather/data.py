"""Join the verified US gauge labels to the demo's six weather/location fields.

From backend: python -m ai.prototype_weather.data
ERA5 is retrospective reanalysis, not a weather archive available at issue time.
The result is a feature-compatible research POC, not a validated live forecast.
"""

import argparse
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from ai.inspection import dataset_sha256, write_json
from ai.river.data import DATA_DIR as RIVER_DATA, ROOT as RIVER_ROOT, read_sites
from ai.river.train import validate_dataset as validate_river_dataset
from ai.prototype_weather.schema import INPUT_COLUMNS, validate_inputs

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "prototype_weather"
REPORT_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "prototype_weather"
API_URL = "https://archive-api.open-meteo.com/v1/archive"
UNITS = {"rain": "mm", "temperature_2m": "°C", "relative_humidity_2m": "%", "wind_speed_10m": "km/h"}
LABEL_COLUMNS = [
    "area_id", "river_system", "forecast_date", "issued_at", "window_end",
    "observed_flood_stage", "target_max_stage_ft", "approved_samples",
    "flood_stage_ft", "label_source", "threshold_source",
]


def build_weather_features(payload: dict, latitude: float, longitude: float, days: list[str]) -> tuple[pd.DataFrame, list[str]]:
    if payload.get("utc_offset_seconds") != 0 or payload.get("timezone") not in ("GMT", "UTC"):
        raise ValueError("Historical weather timestamps must be UTC")
    if any(payload.get("hourly_units", {}).get(name) != unit for name, unit in UNITS.items()):
        raise ValueError("Weather units do not match the demo fields")
    hourly = pd.DataFrame(payload["hourly"])
    hourly["time"] = pd.to_datetime(hourly["time"], utc=True, errors="raise")
    if hourly["time"].duplicated().any() or not hourly["time"].is_monotonic_increasing:
        raise ValueError("Weather hours must be unique and ordered")
    hourly = hourly.set_index("time")
    hourly[list(UNITS)] = hourly[list(UNITS)].apply(pd.to_numeric, errors="raise")
    rows, missing = [], []
    for day in days:
        issue = pd.Timestamp(day, tz="UTC")
        # Rain is a preceding-hour total: the 24 endpoints are D-23h ... D.
        rain = hourly.reindex(pd.date_range(issue - pd.Timedelta(hours=23), issue, freq="h"))["rain"]
        current = hourly.reindex([issue])[["temperature_2m", "relative_humidity_2m", "wind_speed_10m"]]
        if not np.isfinite(rain.to_numpy(float)).all() or not np.isfinite(current.to_numpy(float)).all():
            missing.append(day)
            continue
        if (rain < 0).any():
            raise ValueError("Rainfall cannot be negative")
        row = current.iloc[0]
        rows.append({
            "forecast_date": day, "latitude": latitude, "longitude": longitude,
            "rainfall24hMm": float(rain.sum()), "temperatureC": float(row["temperature_2m"]),
            "humidityPercent": float(row["relative_humidity_2m"]), "windKph": float(row["wind_speed_10m"]),
            "weather_reference_at": issue.isoformat(),
            "rain_window_start": (issue - pd.Timedelta(hours=24)).isoformat(),
            "weather_source_kind": "ERA5_REANALYSIS",
        })
    result = pd.DataFrame(rows)
    if not result.empty:
        validate_inputs(result)
    return result, missing


def prepare(river_dataset: Path, sites_path: Path, output: Path) -> dict:
    river = validate_river_dataset(pd.read_csv(river_dataset, dtype={"usgs_id": str}))
    sites = read_sites(sites_path)
    if set(river["area_id"]) != set(sites["area_id"]):
        raise ValueError("Weather sites must exactly match the observed-label areas")
    raw = output / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    frames, sources = [], []
    with httpx.Client(timeout=180, follow_redirects=True) as client:
        for site in sites.to_dict(orient="records"):
            labels = river[river["area_id"] == site["area_id"]]
            gauge_path = river_dataset.parent / "raw" / f"noaa-{site['noaa_id'].lower()}.json"
            metadata = json.loads(gauge_path.read_text())["payload"]
            if metadata["usgsId"] != site["usgs_id"]:
                raise ValueError("Gauge coordinates do not match the label source")
            latitude, longitude = metadata["latitude"], metadata["longitude"]
            start = (pd.Timestamp(labels["forecast_date"].min()) - pd.Timedelta(days=1)).date().isoformat()
            end = labels["forecast_date"].max()
            url = str(httpx.URL(API_URL, params={
                "latitude": latitude, "longitude": longitude, "start_date": start, "end_date": end,
                "hourly": ",".join(UNITS), "models": "era5", "timezone": "UTC",
                "temperature_unit": "celsius", "wind_speed_unit": "kmh", "precipitation_unit": "mm",
            }))
            cache = raw / f"{site['area_id']}-{start}-{end}-era5.json.gz"
            if not cache.exists():
                response = client.get(url)
                response.raise_for_status()
                cached = {"url": url, "retrieved_at": datetime.now(timezone.utc).isoformat(), "payload": response.json()}
                temp = cache.with_suffix(".tmp")
                with gzip.open(temp, "wt", encoding="utf-8") as handle:
                    json.dump(cached, handle)
                temp.replace(cache)
            with gzip.open(cache, "rt", encoding="utf-8") as handle:
                cached = json.load(handle)
            if cached["url"] != url:
                raise ValueError("Cached weather request changed; use a new output directory")
            weather, missing = build_weather_features(cached["payload"], latitude, longitude, labels["forecast_date"].tolist())
            if weather.empty:
                raise ValueError(f"No complete weather features for {site['area_id']}")
            selected_labels = labels[LABEL_COLUMNS].copy()
            # An external benchmark only; it is never passed to the model.
            selected_labels["reference_persistence"] = labels["margin_lag2_ft"].ge(0).astype(int)
            merged = selected_labels.merge(weather, on="forecast_date", how="inner", validate="one_to_one")
            frames.append(merged)
            sources.append({
                "area_id": site["area_id"], "url": url, "retrieved_at": cached["retrieved_at"],
                "sha256": dataset_sha256(cache), "coordinate_source_sha256": dataset_sha256(gauge_path),
                "requested_coordinates": [latitude, longitude],
                "weather_grid_coordinates": [cached["payload"]["latitude"], cached["payload"]["longitude"]],
                "rows": len(merged), "missing_weather_dates": missing,
            })
            print(f"{site['area_id']}: {len(merged)} labelled days using the six demo inputs", flush=True)
    dataset = pd.concat(frames).sort_values(["forecast_date", "area_id"])
    dataset.to_csv(output / "dataset.csv", index=False)
    manifest = {
        "feature_contract": "frontend/src/types/prototype.ts WeatherLocation numeric weather/location fields",
        "input_columns": INPUT_COLUMNS,
        "feature_source": "Open-Meteo ERA5 reanalysis; weather data CC BY 4.0",
        "weather_documentation": "https://open-meteo.com/en/docs/historical-weather-api",
        "label_source": "Approved USGS quarter-hour stage observations and documented NOAA minor flood stages",
        "river_dataset_sha256": dataset_sha256(river_dataset),
        "dataset_sha256": dataset_sha256(output / "dataset.csv"),
        "rows": len(dataset), "positive_rows": int(dataset["observed_flood_stage"].sum()),
        "negative_rows": int(dataset["observed_flood_stage"].eq(0).sum()),
        "weather_semantics": "Rain during preceding 24 hours ending at issue; temperature/humidity/wind at issue; location coordinates",
        "evaluation_kind": "RETROSPECTIVE_REANALYSIS_POC", "fiji_validated": False,
        "limitations": [
            "ERA5 is retrospective reanalysis published after valid time, not measurements demonstrably available at forecast issue.",
            "Thus this is a next-day association hindcast, not an operational forecast-skill claim.",
            "The target is US gauge flood-stage exceedance, not observed flood inundation throughout a Fiji area.",
            "The label cohort matches the prior river POC and inherits its strict gauge coverage/history exclusions.",
            "Point weather cannot represent all upstream rainfall, drainage or river storage.",
        ],
        "sources": sources,
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--river-dataset", type=Path, default=RIVER_DATA / "dataset.csv")
    parser.add_argument("--sites", type=Path, default=RIVER_ROOT / "sites.csv")
    parser.add_argument("--output", type=Path, default=DATA_DIR)
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    args = parser.parse_args()
    try:
        manifest = prepare(args.river_dataset, args.sites, args.output)
        write_json(args.report_dir / "data_manifest.json", manifest)
    except (ValueError, OSError, KeyError, httpx.HTTPError) as error:
        parser.exit(1, f"Demo weather preparation failed: {error}\n")
    print(f"Prepared {manifest['rows']} verified-label rows with prototype-compatible inputs.")


if __name__ == "__main__":
    main()
