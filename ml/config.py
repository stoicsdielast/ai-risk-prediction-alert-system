from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "data/raw"
ARTIFACTS = ROOT / "artifacts"
REPOSITORY = "https://github.com/Srabon-bot/Bangladesh-flood-data-set"
COMMIT = "4d6ec74e22a63c1e33012d0f8d106e238dda4e1c"
DATA_PATH = "data/features/2026-08-07c/all_stations.parquet"
DATA_BLOB = "9fc1842d6767d0e627d81512ce8b75aadd44d81f"
TARGET = "flood_within_24h"
REGIME = TARGET + "_label_regime"
SEED = 314
BASE = ["rainfall_local_mm", "rainfall_upstream_mm", "soil_moisture_local", "river_discharge_m3s"]
# Explicit allowlist. No automatic numeric-column selection.
FEATURES = BASE + [f"{c}_lag{lag}d" for c in BASE for lag in (1, 2, 3, 5)] + [
    f"{c}_sum{days}d" for c in BASE[:2] for days in (7, 14)
] + ["river_discharge_m3s_mean7d", "river_discharge_m3s_mean14d",
     "elevation_m", "hand_m", "latitude", "longitude"]
HOLDOUT_STATIONS = ["SW90", "TE01", "GA01", "SW174", "CH01", "CO01"]
VALIDATION_START = "2022-01-01"
TEST_START = "2024-01-01"
EMBARGO_DAYS = 3  # Conservative maximum of all provided 24/48/72-hour horizons.
TIERS = {"MODERATE": 0.25, "HIGH": 0.5, "VERY_HIGH": 0.75}
DISCLAIMER = (
    "Research Proof of Concept — Bangladesh historical replay. "
    "Not validated for Fiji or operational public warnings. "
    "Labels are source-qualified flood-detection proxies, not independently verified ground truth. "
    "Probability tiers are provisional presentation thresholds."
)
