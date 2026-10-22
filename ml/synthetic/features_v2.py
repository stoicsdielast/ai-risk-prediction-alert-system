"""v2 causal feature sets: extended hydrological and weather-only, no future information.

Extends ml/synthetic/features.py without modifying it. Every new feature at
time t uses only observations at t or earlier within the same location, so a
FastAPI inference service can recompute them from raw observation history.
"""
import numpy as np
import pandas as pd
from ml.synthetic.generate import RAW_COLUMNS, GEO_COLUMNS

WEATHER_CHANNELS = ["rainfall_mm", "temperature_c", "humidity_pct", "pressure_hpa",
                    "wind_speed_ms", "wind_direction_deg", "upstream_rainfall_mm", "coastal_tide_m"]
HYDRO_CHANNELS = ["soil_moisture_pct", "river_level_m", "river_discharge_m3s"]


def build_features_v2(observations, locations, frequency="1h"):
    """Return (frame, extended_names, weather_only_names).

    Frame columns are computed forward-only; missing values are recovered with a
    6 h forward fill (never back-filled) after missing indicators are recorded.
    """
    dt = pd.Timedelta(frequency).total_seconds() / 3600
    frame = observations.sort_values(["location_id", "timestamp"])[["location_id", "timestamp"] + RAW_COLUMNS].copy()
    frame = frame.reset_index(drop=True)
    for c in RAW_COLUMNS:
        frame[c + "_missing"] = frame[c].isna().astype("int8")
    frame[RAW_COLUMNS] = frame.groupby("location_id", sort=False)[RAW_COLUMNS].ffill(limit=max(1, int(6 / dt)))

    groups = frame.groupby("location_id", sort=False)
    for c in ["rainfall_mm", "upstream_rainfall_mm"]:
        for hours in [3, 6, 24, 72, 168, 336]:
            window = max(1, int(hours / dt))
            frame[f"{c}_total_{hours}h"] = groups[c].transform(
                lambda s: s.rolling(window, min_periods=max(1, window // 2)).sum())
        for hours in [24, 72]:
            window = max(1, int(hours / dt))
            frame[f"{c}_max_{hours}h"] = groups[c].transform(
                lambda s: s.rolling(window, min_periods=1).max())
        steps = max(1, int(24 / dt))
        frame[f"{c}_lag_{24}h"] = groups[c].shift(steps)

    frame["rain_intensity_3h_mm_h"] = frame["rainfall_mm_total_3h"] / 3.0
    frame["upstream_excess_24h"] = frame["upstream_rainfall_mm_total_24h"] - frame["rainfall_mm_total_24h"]

    for c in ["river_level_m", "river_discharge_m3s", "soil_moisture_pct"]:
        for hours in [3, 6, 24, 48]:
            steps = max(1, int(hours / dt))
            frame[f"{c}_change_{hours}h"] = groups[c].diff(steps)
        frame[c + "_mean_24h"] = groups[c].transform(lambda s: s.rolling(max(1, int(24 / dt)), min_periods=1).mean())

    frame["river_level_anomaly_24h"] = frame["river_level_m"] - frame["river_level_m_mean_24h"]
    frame["river_discharge_anomaly_24h"] = frame["river_discharge_m3s"] - frame["river_discharge_m3s_mean_24h"]
    frame["level_discharge_ratio"] = frame["river_level_m"] / (frame["river_discharge_m3s"] + 1.0)
    frame["soil_moisture_change_72h"] = groups["soil_moisture_pct"].diff(max(1, int(72 / dt)))
    frame["coastal_tide_max_6h"] = groups["coastal_tide_m"].transform(
        lambda s: s.rolling(max(1, int(6 / dt)), min_periods=1).max())

    # Dry-spell length in hours since the last meaningful rain, per location.
    dry = np.empty(len(frame), dtype="float64")
    for _, idx in frame.groupby("location_id", sort=False).groups.items():
        values = frame.loc[idx, "rainfall_mm"].to_numpy()
        times = frame.loc[idx, "timestamp"].astype("int64").to_numpy()
        last = -1
        out = np.empty(len(values), dtype="float64")
        threshold = 1.0
        for i, v in enumerate(values):
            if v > threshold:
                last = i
            out[i] = np.nan if last < 0 else (times[i] - times[last]) / (3600 * 10**9)
        dry[idx] = out
    frame["dry_spell_hours"] = dry

    frame = frame.merge(locations[["location_id", "latitude", "longitude"] + GEO_COLUMNS],
                        on="location_id", validate="many_to_one", sort=False)
    frame["tide_stress_6h"] = frame["coastal_tide_max_6h"] * frame["coastal_influence"]

    frame["month_sin"] = np.sin(2 * np.pi * frame.timestamp.dt.month / 12)
    frame["month_cos"] = np.cos(2 * np.pi * frame.timestamp.dt.month / 12)
    frame["hour_sin"] = np.sin(2 * np.pi * frame.timestamp.dt.hour / 24)
    frame["hour_cos"] = np.cos(2 * np.pi * frame.timestamp.dt.hour / 24)
    frame["history_ready"] = frame.groupby("location_id", sort=False).cumcount() >= int(168 / dt)

    hydro_suffixes = ("soil_moisture", "river_level", "river_discharge", "level_discharge_ratio")
    extended, weather_only = [], []
    for c in frame.columns:
        if c in ("location_id", "timestamp", "history_ready"):
            continue
        forbidden = any(x in c for x in ["flood", "event", "scenario", "hidden", "future", "target"])
        assert not forbidden, f"leaky feature name: {c}"
        extended.append(c)
        if not any(s in c for s in hydro_suffixes):
            weather_only.append(c)
    return frame, extended, weather_only
