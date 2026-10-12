"""Inspect the source CSV without fitting or transforming any features."""

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import (
    CATEGORICAL_FEATURES, EXCLUDED_FEATURES, FEATURE_COLUMNS,
    NUMERIC_FEATURES, TARGET_COLUMN,
)


def dataset_sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def read_dataset(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise ValueError(f"Dataset not found: {path}. Supply --dataset path/to/file.csv.")
    try:
        frame = pd.read_csv(path)
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeError) as error:
        raise ValueError(f"Unable to read CSV {path.name}: {error}") from error
    if frame.empty:
        raise ValueError("Dataset contains no records.")
    if TARGET_COLUMN not in frame:
        raise ValueError(f"Expected observed target column {TARGET_COLUMN!r} is missing.")
    return frame


def inspect_dataset(frame: pd.DataFrame, path: Path) -> dict[str, Any]:
    """Produce a serializable report of actual values and data quality concerns."""
    categorical = frame.select_dtypes(include=["object", "string", "category"]).columns
    numeric = frame.select_dtypes(include="number").columns
    report = {
        "dataset_filename": path.name,
        "dataset_sha256": dataset_sha256(path),
        "shape": {"rows": len(frame), "columns": len(frame.columns)},
        "columns": frame.columns.tolist(),
        "dtypes": {name: str(dtype) for name, dtype in frame.dtypes.items()},
        "first_rows": json.loads(frame.head().to_json(orient="records")),
        "missing_values": {name: int(count) for name, count in frame.isna().sum().items()},
        "duplicate_rows": int(frame.duplicated().sum()),
        "categorical_unique_values": {
            name: sorted(str(value) for value in frame[name].dropna().unique())
            for name in categorical
        },
        "descriptive_statistics": json.loads(frame.describe(include="all").to_json()),
        "target_column": TARGET_COLUMN,
        "target_distribution": {
            str(label): int(count)
            for label, count in frame[TARGET_COLUMN].value_counts(dropna=False).items()
        },
        "numeric_target_correlations": {
            name: float(value) if pd.notna(value) else None
            for name, value in frame[numeric].corr()[TARGET_COLUMN].items()
            if name != TARGET_COLUMN
        } if TARGET_COLUMN in numeric else {},
        "numeric_features": list(NUMERIC_FEATURES),
        "categorical_features": list(CATEGORICAL_FEATURES),
        "excluded_features": EXCLUDED_FEATURES,
        "identifier_columns": [],
        "concerns": [
            "Kaggle India development data; not official Fiji MET operational data.",
            "Original dataset URL, collection method, units for binary flags and "
            "population density, and synthetic/observational provenance are unverified.",
            "No timestamps: water level/discharge and other measurements cannot be "
            "verified as available before the outcome. No forecast lead time is established.",
            "Historical Floods is excluded because its timing and meaning are unverified.",
            "Random row splitting does not establish transfer to Fiji or performance "
            "on future events or unseen locations.",
        ],
    }
    print("\nDATASET INSPECTION")
    print(f"Dataset: {path.name}; shape: {frame.shape}")
    print("\nDatatypes:\n", frame.dtypes.to_string())
    print("\nFirst five rows:\n", frame.head().to_string(index=False))
    print("\nMissing values:\n", frame.isna().sum().to_string())
    print("Duplicate rows:", report["duplicate_rows"])
    print("Categorical unique values:", report["categorical_unique_values"])
    print("\nDescriptive statistics:\n", frame.describe(include="all").to_string())
    print("\nTarget distribution:", report["target_distribution"])
    print("Numeric target correlations:", report["numeric_target_correlations"])
    print("Numerical features:", list(NUMERIC_FEATURES))
    print("Categorical features:", list(CATEGORICAL_FEATURES))
    print("Excluded columns:", EXCLUDED_FEATURES)
    print("Identifier columns: none in the observed schema")
    for concern in report["concerns"]:
        print("Dataset concern:", concern)
    return report


def validate_dataset(frame: pd.DataFrame) -> None:
    expected = set(FEATURE_COLUMNS) | set(EXCLUDED_FEATURES)
    if set(frame.columns) != expected:
        raise ValueError(
            f"CSV schema changed. Missing: {sorted(expected - set(frame.columns))}; "
            f"unexpected: {sorted(set(frame.columns) - expected)}. Review features first."
        )
    target = frame[TARGET_COLUMN]
    if target.isna().any() or set(target.unique()) != {0, 1}:
        raise ValueError("Flood Occurred must contain both binary classes 0 and 1, with no missing labels.")
    if target.value_counts().min() < 2:
        raise ValueError("Need at least two records of each class for a stratified split.")
    if frame.duplicated().any() or frame[list(FEATURE_COLUMNS)].duplicated().any():
        raise ValueError("Repeated feature rows found; review/group duplicates before splitting to avoid leakage.")
    for name in NUMERIC_FEATURES:
        if not pd.api.types.is_numeric_dtype(frame[name]):
            raise ValueError(f"Expected numeric column {name!r}; inspect its values.")
        if np.isinf(frame[name].dropna().to_numpy(dtype=float)).any():
            raise ValueError(f"Column {name!r} contains infinite values.")
        if frame[name].isna().all():
            raise ValueError(f"Column {name!r} has no observed values.")
    for name in CATEGORICAL_FEATURES:
        if frame[name].isna().all():
            raise ValueError(f"Column {name!r} has no observed values.")
