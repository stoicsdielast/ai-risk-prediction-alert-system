"""Numeric model inputs supplied by the weather-map prototype.

Rainfall is the total for the preceding 24 hours. Temperature, humidity and
wind describe the conditions available at prediction time. Labels, warnings,
river measurements and other display fields are never model inputs here.
"""

import numpy as np
import pandas as pd
from pandas.api.types import is_datetime64_any_dtype, is_timedelta64_dtype


INPUT_COLUMNS = [
    "latitude", "longitude", "rainfall24hMm", "temperatureC",
    "humidityPercent", "windKph",
]


def validate_inputs(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a validated float copy containing exactly the prototype inputs."""
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("Prototype weather inputs must be a pandas DataFrame")
    if frame.columns.duplicated().any():
        raise ValueError("Prototype weather input columns must be unique")
    missing = [column for column in INPUT_COLUMNS if column not in frame]
    if missing:
        raise ValueError("Missing prototype weather inputs: " + ", ".join(missing))

    result = frame[INPUT_COLUMNS].copy()
    for column in INPUT_COLUMNS:
        values = result[column]
        if (values.map(lambda value: isinstance(value, (bool, np.bool_))).any()
                or is_datetime64_any_dtype(values.dtype)
                or is_timedelta64_dtype(values.dtype)):
            raise ValueError(f"{column} must contain numeric measurements, not booleans or dates")
        try:
            numeric = pd.to_numeric(values, errors="raise")
            if np.iscomplexobj(numeric):
                raise ValueError("Complex measurements are not supported")
            result[column] = numeric.astype(float)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError(f"{column} must contain numeric measurements") from error
        if not np.isfinite(result[column].to_numpy()).all():
            raise ValueError(f"{column} must contain finite, non-missing measurements")

    bounds = {
        "latitude": (-90, 90),
        "longitude": (-180, 180),
        "rainfall24hMm": (0, None),
        "temperatureC": (-273.15, None),
        "humidityPercent": (0, 100),
        "windKph": (0, None),
    }
    for column, (lower, upper) in bounds.items():
        if result[column].lt(lower).any() or (upper is not None and result[column].gt(upper).any()):
            limit = f"between {lower} and {upper}" if upper is not None else f"at least {lower}"
            raise ValueError(f"{column} must be {limit}")
    return result


def features_from_location(payload: dict) -> pd.DataFrame:
    """Adapt either WeatherLocation or MapLocation without using display outputs."""
    if not isinstance(payload, dict):
        raise ValueError("A prototype weather location must be an object")
    conditions = payload.get("conditions", payload)
    if not isinstance(conditions, dict):
        raise ValueError("Location conditions must include the prototype weather measurements")
    selected = {column: conditions[column] for column in INPUT_COLUMNS if column in conditions}
    for coordinate in ("latitude", "longitude"):
        if coordinate in payload:
            selected[coordinate] = payload[coordinate]
    return validate_inputs(pd.DataFrame([selected]))
