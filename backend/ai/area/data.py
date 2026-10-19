"""Download archived forecasts for Fiji reference points; never invent flood labels.

From backend: python -m ai.area.data --start 2024-01-01 --end 2025-12-31
The prediction window is 00:00–24:00 Pacific/Fiji on forecast_date. The previous_day2
archive is used so even the final hour's forecast reference precedes issue time
by 24 hours, leaving time for the weather model to run and be published. This is
a conservative archive baseline, not a reconstruction of the latest available run.
"""

import argparse
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from ai.inspection import write_json

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT.parent / "data" / "area"
API_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
DOCS_URL = "https://open-meteo.com/en/docs/previous-runs-api"
MODEL = "gfs_seamless"
TIMEZONE = "Pacific/Fiji"
VARIABLES = {
    "precipitation_previous_day2": "mm",
    "temperature_2m_previous_day2": "°C",
    "relative_humidity_2m_previous_day2": "%",
}
FEATURES = [
    "latitude", "longitude", "elevation_m", "forecast_rain_mm_24h",
    "forecast_rain_mm_6h_max", "forecast_rain_mm_1h_max",
    "forecast_temp_c_mean", "forecast_humidity_pct_mean", "season_sin", "season_cos",
]
LABEL_COLUMNS = ["area_id", "forecast_date", "observed_flood", "label_source", "event_id", "coverage_note"]


def read_areas(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"area_id", "name", "latitude", "longitude"}
    if not required <= set(frame) or frame.empty:
        raise ValueError("Areas need area_id, name, latitude and longitude")
    if frame["area_id"].isna().any() or frame["area_id"].duplicated().any():
        raise ValueError("Area identifiers must be present and unique")
    if not frame["area_id"].str.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*").all():
        raise ValueError("Area identifiers must be lowercase URL slugs")
    for name, low, high in (("latitude", -90, 90), ("longitude", -180, 180)):
        frame[name] = pd.to_numeric(frame[name], errors="raise")
        if not frame[name].between(low, high).all():
            raise ValueError(f"Invalid {name}")
    return frame


def build_daily_features(payload: dict, area: dict, start: str, end: str) -> tuple[pd.DataFrame, list[str]]:
    """Reject incomplete hours; a missing forecast is not zero rainfall."""
    if payload.get("timezone") != TIMEZONE:
        raise ValueError("Forecast timezone must be Pacific/Fiji")
    if any(payload.get("hourly_units", {}).get(key) != unit for key, unit in VARIABLES.items()):
        raise ValueError("Unexpected weather variables or units")
    hourly = pd.DataFrame(payload["hourly"])
    hourly["time"] = pd.to_datetime(hourly["time"], errors="raise").dt.tz_localize(TIMEZONE)
    if hourly["time"].duplicated().any() or not hourly["time"].is_monotonic_increasing:
        raise ValueError("Forecast hours must be unique and ordered")
    for key in VARIABLES:
        hourly[key] = pd.to_numeric(hourly[key], errors="raise")
    rows, missing_days = [], []
    for day in pd.date_range(start, end, freq="D", tz=TIMEZONE):
        end_of_day = day + pd.Timedelta(hours=24)
        subset = hourly[(hourly["time"] >= day) & (hourly["time"] < end_of_day)]
        # Precipitation is the PRECEDING hour's sum; include next midnight,
        # rather than the hour ending at this day's midnight.
        rain_hours = hourly[(hourly["time"] > day) & (hourly["time"] <= end_of_day)]
        expected_hours = pd.date_range(day, periods=24, freq="h")
        expected_rain_hours = expected_hours + pd.Timedelta(hours=1)
        if not pd.DatetimeIndex(subset["time"]).equals(expected_hours) or not pd.DatetimeIndex(rain_hours["time"]).equals(expected_rain_hours):
            missing_days.append(day.date().isoformat())
            continue
        values = subset[["temperature_2m_previous_day2", "relative_humidity_2m_previous_day2"]].to_numpy(dtype=float)
        rain = rain_hours["precipitation_previous_day2"]
        if not np.isfinite(values).all() or not np.isfinite(rain.to_numpy(dtype=float)).all():
            missing_days.append(day.date().isoformat())
            continue
        humidity = subset["relative_humidity_2m_previous_day2"]
        if (rain < 0).any() or not humidity.between(0, 100).all():
            raise ValueError("Rainfall or humidity outside valid ranges")
        issue = day.tz_convert("UTC")
        angle = 2 * np.pi * (day.dayofyear - 1) / (366 if day.is_leap_year else 365)
        rows.append({
            "area_id": area["area_id"], "forecast_date": day.date().isoformat(),
            "issued_at": issue.isoformat(), "window_end": (issue + pd.Timedelta(hours=24)).isoformat(),
            "latest_reference_time_bound": (issue - pd.Timedelta(hours=24)).isoformat(),
            "weather_model": MODEL, "forecast_offset_days": 2,
            "latitude": area["latitude"], "longitude": area["longitude"],
            "grid_latitude": payload["latitude"], "grid_longitude": payload["longitude"],
            "elevation_m": payload["elevation"],
            "forecast_rain_mm_24h": float(rain.sum()),
            "forecast_rain_mm_6h_max": float(rain.rolling(6).sum().max()),
            "forecast_rain_mm_1h_max": float(rain.max()),
            "forecast_temp_c_mean": float(subset["temperature_2m_previous_day2"].mean()),
            "forecast_humidity_pct_mean": float(humidity.mean()),
            "season_sin": float(np.sin(angle)), "season_cos": float(np.cos(angle)),
        })
    return pd.DataFrame(rows), missing_days


def download(areas_path: Path, start: str, end: str, output: Path) -> dict:
    start_day, end_day = date.fromisoformat(start), date.fromisoformat(end)
    if start_day < date(2024, 1, 1) or end_day < start_day or end_day >= datetime.now(timezone.utc).date():
        raise ValueError("Use a completed date range starting on or after 2024-01-01")
    areas = read_areas(areas_path)
    output.mkdir(parents=True, exist_ok=True)
    raw = output / "raw"
    raw.mkdir(exist_ok=True)
    frames, sources = [], []
    with httpx.Client(timeout=90, follow_redirects=True) as client:
        for area in areas.to_dict(orient="records"):
            params = {
                "latitude": area["latitude"], "longitude": area["longitude"],
                "start_date": start, "end_date": (end_day + timedelta(days=1)).isoformat(), "hourly": ",".join(VARIABLES),
                "models": MODEL, "timezone": TIMEZONE,
            }
            cache = raw / f"{area['area_id']}-{start}-{end}-{MODEL}-day2-window24h.json"
            url = str(httpx.URL(API_URL, params=params))
            if not cache.exists():
                response = client.get(url)
                response.raise_for_status()
                payload = response.json()
                if payload.get("error"):
                    raise ValueError(payload.get("reason", "Weather API failed"))
                write_json(cache, {"url": url, "retrieved_at": datetime.now(timezone.utc).isoformat(), "payload": payload})
            cached = json.loads(cache.read_text())
            if cached["url"] != url:
                raise ValueError(f"Area coordinates or request changed; remove stale cache {cache}")
            frame, missing_days = build_daily_features(cached["payload"], area, start, end)
            if frame.empty:
                raise ValueError(f"No complete forecast days for {area['area_id']}")
            frames.append(frame)
            sources.append({
                "area_id": area["area_id"], "url": url, "retrieved_at": cached["retrieved_at"],
                "raw_sha256": hashlib.sha256(cache.read_bytes()).hexdigest(),
                "rows": len(frame), "missing_days": missing_days,
                "requested_coordinates": [area["latitude"], area["longitude"]],
                "weather_grid_coordinates": [cached["payload"]["latitude"], cached["payload"]["longitude"]],
            })
            print(f"{area['area_id']}: {len(frame)} complete days, {len(missing_days)} incomplete days", flush=True)
    features = pd.concat(frames, ignore_index=True).sort_values(["forecast_date", "area_id"])
    features.to_csv(output / "features.csv", index=False)
    # A separate template avoids overwriting a researcher's completed label file.
    labels = features[["area_id", "forecast_date"]].copy()
    for column in LABEL_COLUMNS[2:]:
        labels[column] = ""
    labels.to_csv(output / "labels_template.csv", index=False)
    manifest = {
        "source": "Open-Meteo Previous Model Runs API / NOAA GFS", "documentation": DOCS_URL,
        "licence": "Weather data: CC BY 4.0; free API for non-commercial use",
        "model": MODEL, "timezone": TIMEZONE, "forecast_offset_days": 2,
        "window": "00:00 to 24:00 Pacific/Fiji on forecast_date",
        "precipitation_alignment": "Preceding-hour totals at 01:00 through next midnight; instantaneous temperature/humidity at 00:00 through 23:00.",
        "availability_assumption": "Fixed 48-hour offsets: latest hourly forecast reference is 24 hours before issue; publication time is not supplied by the archive.",
        "start": start, "end": end, "areas": len(areas), "feature_rows": len(features),
        "verified_label_rows": 0, "training_ready": False,
        "limitations": [
            "Town reference points, not catchment averages or flood-extent polygons.",
            "Archived weather forecasts are predictors, not observed flood labels.",
            "Blank labels mean unknown, never no-flood. Positive-only event catalogs do not establish monitored negative days.",
            "Different towns may share a weather grid cell. Small-scale drainage and river measurements are not included.",
        ],
        "sources": sources,
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--areas", type=Path, default=ROOT / "areas.csv")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        report = download(args.areas, args.start, args.end, args.output)
    except (ValueError, OSError, KeyError, httpx.HTTPError) as error:
        parser.exit(1, f"Data preparation failed: {error}\n")
    print(f"Prepared {report['feature_rows']} area-days. Verified flood labels are still required for training.")


if __name__ == "__main__":
    main()
