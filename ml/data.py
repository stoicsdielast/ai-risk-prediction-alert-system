"""Fail-closed label screening and causal feature reconstruction."""
import ast
import hashlib
import json

import numpy as np
import pandas as pd

from ml.config import (ARTIFACTS, BASE, COMMIT, EMBARGO_DAYS, FEATURES, HOLDOUT_STATIONS,
                       RAW, REGIME, TARGET, TEST_START, VALIDATION_START)


def stations():
    # Parse literal station declarations; never execute downloaded source code.
    tree = ast.parse((RAW / "source/stations.py").read_text())
    result = {}
    declaration = next(node.value for node in tree.body if isinstance(node, ast.AnnAssign)
                       and isinstance(node.target, ast.Name) and node.target.id == "STATIONS")
    for node in declaration.elts:
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Station":
            sid, name, river, lat, lon, basin = [ast.literal_eval(a) for a in node.args]
            result[sid] = dict(station_id=sid, name=name, river=river, latitude=lat, longitude=lon, basin=basin)
    if len(result) != 30:
        raise ValueError("Expected 30 source station declarations")
    return result


def validate_raw(frame):
    required = ["date", "station_id", REGIME, TARGET, "elevation_m", "hand_m", *BASE]
    if set(required) - set(frame):
        raise ValueError("Missing dataset schema columns")
    if frame["date"].isna().any() or frame["station_id"].isna().any():
        raise ValueError("Null station/date keys")
    if frame.duplicated(["station_id", "date"]).any():
        raise ValueError("Duplicate station/date keys; resolve rather than silently deduplicate")
    known = frame[TARGET].dropna()
    if not known.isin([0, 1]).all():
        raise ValueError("Non-binary known target")


def accessible(dates):
    return dates.between("2013-01-01", "2016-03-31") | dates.between("2021-01-01", "2026-02-02")


def screen_labels(frame):
    # A 24h negative is acceptable only when the NEXT day has source coverage.
    return frame[REGIME].eq("observed") & frame[TARGET].isin([0, 1]) & accessible(frame.date + pd.Timedelta(days=1))


def build_features(frame, registry):
    validate_raw(frame)
    result = frame.sort_values(["station_id", "date"]).copy()
    if not result.station_id.isin(registry).all():
        raise ValueError("Unknown source station")
    gaps = result.groupby("station_id").date.diff().dropna()
    if not gaps.eq(pd.Timedelta(days=1)).all():
        raise ValueError("Daily series must be complete before constructing lags")
    # Rebuild the allowlisted histories from raw past/current values, not from
    # precomputed source columns whose causality might change in a future version.
    for column in BASE:
        values = pd.to_numeric(result[column], errors="raise")
        result[column] = values.where(np.isfinite(values))
        if (result[column].dropna() < 0).any():
            raise ValueError(f"Negative physical measurement: {column}")
        groups = result.groupby("station_id")[column]
        for lag in (1, 2, 3, 5):
            result[f"{column}_lag{lag}d"] = groups.shift(lag)
        if column in BASE[:2]:
            for days in (7, 14):
                result[f"{column}_sum{days}d"] = groups.transform(lambda s: s.rolling(days, min_periods=days).sum())
        if column == "river_discharge_m3s":
            for days in (7, 14):
                result[f"{column}_mean{days}d"] = groups.transform(lambda s: s.rolling(days, min_periods=days).mean())
    result["latitude"] = result.station_id.map(lambda sid: registry[sid]["latitude"])
    result["longitude"] = result.station_id.map(lambda sid: registry[sid]["longitude"])
    return result


def split_rows(frame):
    validation, test = pd.Timestamp(VALIDATION_START), pd.Timestamp(TEST_START)
    embargo = pd.Timedelta(days=EMBARGO_DAYS)
    holdout = frame.station_id.isin(HOLDOUT_STATIONS)
    part = pd.Series("excluded", index=frame.index)
    part.loc[~holdout & (frame.date < validation - embargo)] = "train"
    part.loc[~holdout & (frame.date >= validation) & (frame.date < test - embargo)] = "validation"
    part.loc[~holdout & (frame.date >= test)] = "test"
    part.loc[holdout & (frame.date >= test)] = "holdout_station"
    return part


def representative_subset(frame, rows=30000):
    if not 20000 <= rows <= 40000:
        raise ValueError("Research subset must contain 20,000–40,000 rows")
    screened = frame.loc[screen_labels(frame)].copy()
    # All required histories must really exist. Never invent the weather.
    screened = screened.dropna(subset=FEATURES)
    if len(screened) < rows:
        raise ValueError(f"Only {len(screened)} fully screened rows, need {rows}")
    # Target-independent stable uniform sampling over every eligible station/day.
    keys = screened.station_id + ":" + screened.date.dt.strftime("%Y-%m-%d") + ":314"
    screened["selection_hash"] = keys.map(lambda key: hashlib.sha256(key.encode()).hexdigest())
    subset = screened.sort_values("selection_hash").head(rows)
    subset = subset.sort_values(["date", "station_id"]).copy()
    subset["partition"] = split_rows(subset)
    return subset


def audit(frame, out=ARTIFACTS):
    out.mkdir(parents=True, exist_ok=True)
    labels = []
    for horizon in ("24h", "48h", "72h"):
        target = "flood_within_" + horizon
        counts = frame.groupby([target, target + "_label_regime"], dropna=False).size().reset_index(name="rows")
        counts["horizon"] = horizon
        labels.append(counts.rename(columns={target: "label", target + "_label_regime": "regime"}))
    pd.concat(labels).to_csv(out / "label_regimes.csv", index=False)
    frame.isna().mean().rename("missing_fraction").to_csv(out / "missingness.csv")
    frame.isna().groupby(frame.date.dt.year).mean().to_csv(out / "missingness_by_year.csv")
    frame.groupby([frame.date.dt.year.rename("year"), REGIME], dropna=False)[TARGET].agg(["count", "sum", "mean"]).to_csv(out / "labels_by_year.csv")
    frame.groupby("station_id")[TARGET].agg(["count", "sum", "mean"]).to_csv(out / "labels_by_station.csv")
    violations = frame[REGIME].eq("observed") & ~accessible(frame.date + pd.Timedelta(days=1))
    report = {
        "shape": list(frame.shape), "dtypes": frame.dtypes.astype(str).to_dict(),
        "date_start": str(frame.date.min()), "date_end": str(frame.date.max()),
        "stations": int(frame.station_id.nunique()), "duplicate_rows": int(frame.duplicated().sum()),
        "duplicate_station_dates": int(frame.duplicated(["station_id", "date"]).sum()),
        "unknown_24h": int(frame[TARGET].isna().sum()), "screened_label_rows": int(screen_labels(frame).sum()),
        "invalid_observed_coverage": int(violations.sum()), "source_commit": COMMIT,
        "label_policy": "Keep only observed 0/1 with next-day GFMS coverage; exclude unknown AND positive-only regimes. Source negatives are NOT independently verified non-floods.",
        "prediction_time": "Offline daily replay after the feature day closes; daily reanalysis publication latency and source time zone are unverified. No real-time availability claim.",
        "leakage_excluded": [c for c in frame if c not in FEATURES and c not in ["date", "station_id", "station_name"]],
        "reliability": ["GFMS modelled flood detections and coverage assumptions can miss real floods.",
                        "Positive-only archive matching is not a negative-label source.",
                        "Station coordinates are approximate virtual gauges; nearby stations share model grids.",
                        "README terrain provenance differs from stations.py (MERIT Hydro); precise source script takes precedence, terms unresolved.",
                        "Feature reanalysis latency prevents interpreting offline performance as operational forecasting."],
    }
    (out / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
    validate_raw(frame)
    if violations.any():
        raise ValueError("Observed regime has dates outside source coverage")
    return report
