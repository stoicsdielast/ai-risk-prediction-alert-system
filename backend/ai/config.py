"""Paths and reproducible prototype configuration (no backend settings needed)."""

from pathlib import Path

AI_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = AI_DIR.parent.parent
DEFAULT_DATASET = REPOSITORY_ROOT / "archive" / "flood_risk_dataset_india.csv"
PROCESSED_DIR = AI_DIR / "data" / "processed"
MODELS_DIR = AI_DIR / "models"
ARTIFACTS_DIR = AI_DIR / "artifacts"
MODEL_PATH = MODELS_DIR / "flood_risk_model.joblib"
METADATA_PATH = MODELS_DIR / "model_metadata.json"
TARGET_COLUMN = "Flood Occurred"
RANDOM_STATE = 42
TEST_SIZE = 0.20
PROTOTYPE_VERSION = "flood-occurrence-prototype-v1"

# Observed CSV schema, checked again on every training run.
NUMERIC_FEATURES = (
    "Latitude", "Longitude", "Rainfall (mm)", "Temperature (°C)",
    "Humidity (%)", "River Discharge (m³/s)", "Water Level (m)",
    "Elevation (m)", "Population Density", "Infrastructure",
)
CATEGORICAL_FEATURES = ("Land Cover", "Soil Type")
FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES
EXCLUDED_FEATURES = {
    TARGET_COLUMN: "Outcome label; including it would directly leak the target.",
    "Historical Floods": (
        "CSV has no event dates or provenance proving this flag predates the "
        "target event; conservatively excluded until its definition is verified."
    ),
}

# Development thresholds only; these are not official Fiji MET warning levels.
MODERATE_THRESHOLD = 0.25
HIGH_THRESHOLD = 0.50
VERY_HIGH_THRESHOLD = 0.75
RISK_THRESHOLDS = (MODERATE_THRESHOLD, HIGH_THRESHOLD, VERY_HIGH_THRESHOLD)
