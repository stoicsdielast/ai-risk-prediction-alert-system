"""Read-only analytics over stored predictions and saved research artifacts.

Nothing here writes to the database, generates predictions, retrains or promotes a
model. Operational ``predictions`` (genuine / sample) and ``synthetic_predictions``
are always reported separately and never merged into one series or total.
"""
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Location
from app.models.prediction import ALERT_DEMO_MODEL_PREFIX, Prediction
from app.models.synthetic import SyntheticDataset, SyntheticPrediction

RISK_ORDER = ("LOW", "MODERATE", "HIGH", "VERY_HIGH")
HIGH_RISK = ("HIGH", "VERY_HIGH")
STALE_AFTER_HOURS = 24
HORIZON_HOURS = 24  # V1 target: flood onset within the next 24 hours
MAX_TREND_POINTS = 5000
NOTICE = "Synthetic Data — Research Demonstration. Not official Fiji MET readings or validated flood forecasts."


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def iso(value: datetime | None) -> str | None:
    value = as_utc(value)
    return value.isoformat() if value else None


def operational_kind(is_sample: bool) -> str:
    return "sample" if is_sample else "genuine"


def empty_risk_counts() -> dict[str, int]:
    return {level: 0 for level in RISK_ORDER}


def freshness(latest: datetime | None, now: datetime) -> dict:
    latest = as_utc(latest)
    if latest is None:
        return {"latest_at": None, "age_hours": None, "stale": None, "stale_after_hours": STALE_AFTER_HOURS}
    age = max((now - latest).total_seconds() / 3600, 0.0)
    return {"latest_at": iso(latest), "age_hours": round(age, 2), "stale": age > STALE_AFTER_HOURS,
            "stale_after_hours": STALE_AFTER_HOURS}


def validate_locations(db: Session, location_ids: list[int]) -> list[int]:
    ids = sorted(set(location_ids))
    if not ids:
        return []
    known = set(db.scalars(select(Location.id).where(Location.id.in_(ids))))
    missing = [i for i in ids if i not in known]
    if missing:
        raise LookupError(f"Unknown location id(s): {missing}")
    return ids


# --------------------------------------------------------------------------- overview

def _operational_summary(db: Session, window_start: datetime, now: datetime) -> dict:
    by_kind: dict[str, dict] = {}
    for kind_sample in (False, True):
        kind = operational_kind(kind_sample)
        base = Prediction.is_sample.is_(kind_sample)
        total, latest = db.execute(select(func.count(Prediction.id), func.max(Prediction.predicted_at)).where(base)).one()
        risk_all = empty_risk_counts()
        for level, count in db.execute(select(Prediction.risk_level, func.count()).where(base).group_by(Prediction.risk_level)):
            risk_all[level.value] = count
        window = base & (Prediction.predicted_at >= window_start)
        risk_window = empty_risk_counts()
        for level, count in db.execute(select(Prediction.risk_level, func.count()).where(window).group_by(Prediction.risk_level)):
            risk_window[level.value] = count
        locations = db.scalars(select(Prediction.location_id).where(window).distinct()).all()
        by_kind[kind] = {
            "total": total, "by_risk": risk_all,
            "window": {"predictions": sum(risk_window.values()), "by_risk": risk_window,
                       "high_risk": sum(risk_window[level] for level in HIGH_RISK),
                       "locations_with_predictions": len(locations), "location_ids": sorted(locations)},
            "freshness": freshness(latest, now),
        }
    versions = []
    for version, is_sample, count, first, last in db.execute(
        select(Prediction.model_version, Prediction.is_sample, func.count(), func.min(Prediction.predicted_at),
               func.max(Prediction.predicted_at)).group_by(Prediction.model_version, Prediction.is_sample)
        .order_by(func.max(Prediction.predicted_at).desc())
    ):
        versions.append({"model_version": version, "kind": operational_kind(is_sample), "predictions": count,
                         "first_at": iso(first), "last_at": iso(last),
                         "alert_workflow_demo": version.startswith(ALERT_DEMO_MODEL_PREFIX)})
    return {"kinds": by_kind, "model_versions": versions}


def _synthetic_summary(db: Session, days: int) -> dict:
    total, latest, earliest = db.execute(select(func.count(SyntheticPrediction.id),
        func.max(SyntheticPrediction.observed_at), func.min(SyntheticPrediction.observed_at))).one()
    # Synthetic timestamps are simulated time, so the window is anchored to the latest synthetic
    # record rather than the wall clock; the anchor is reported so it is never mistaken for "now".
    anchor = as_utc(latest)
    risk_all = empty_risk_counts()
    for category, count in db.execute(select(SyntheticPrediction.risk_category, func.count()).group_by(SyntheticPrediction.risk_category)):
        if category in risk_all:
            risk_all[category] = count
    risk_window, locations = empty_risk_counts(), []
    if anchor is not None:
        start = anchor - timedelta(days=days)
        window = (SyntheticPrediction.observed_at >= start) & (SyntheticPrediction.observed_at <= anchor)
        for category, count in db.execute(select(SyntheticPrediction.risk_category, func.count()).where(window).group_by(SyntheticPrediction.risk_category)):
            if category in risk_window:
                risk_window[category] = count
        locations = db.scalars(select(SyntheticPrediction.location_id).where(window).distinct()).all()
    versions = [{"model_version": v, "dataset_version": d, "predictions": c}
                for v, d, c in db.execute(select(SyntheticPrediction.model_version, SyntheticPrediction.dataset_version,
                                                 func.count()).group_by(SyntheticPrediction.model_version, SyntheticPrediction.dataset_version))]
    return {"total": total, "by_risk": risk_all, "earliest_observed_at": iso(earliest), "latest_observed_at": iso(latest),
            "window_anchor": iso(anchor), "window_anchor_kind": "latest synthetic record (simulated time, not wall clock)",
            "window": {"predictions": sum(risk_window.values()), "by_risk": risk_window,
                       "high_risk": sum(risk_window[level] for level in HIGH_RISK),
                       "locations_with_predictions": len(locations), "location_ids": sorted(locations)},
            "model_versions": versions, "notice": NOTICE}


def prediction_overview(db: Session, days: int, now: datetime | None = None) -> dict:
    now = now or utcnow()
    window_start = now - timedelta(days=days)
    return {"generated_at": iso(now), "window_days": days, "window_start": iso(window_start),
            "operational": _operational_summary(db, window_start, now),
            "synthetic": {"source_type": "synthetic", **_synthetic_summary(db, days)},
            "monitored_locations": db.scalar(select(func.count(Location.id)).where(Location.is_active.is_(True))) or 0}


# ----------------------------------------------------------------------------- trend

def _risk_bands() -> dict | None:
    """V1 research tiers derive from the deployed threshold t (see synthetic_inference.risk_category)."""
    deployed = _deployed(Path(get_settings().synthetic_model_dir))
    threshold = deployed.get("threshold") if deployed else None
    if not isinstance(threshold, (int, float)) or not 0 < threshold < 1:
        return None
    return {"moderate_from": threshold * 0.5, "high_from": threshold, "very_high_from": min(1.0, threshold * 1.5),
            "model_version": deployed.get("model_version")}


def prediction_trend(db: Session, location_ids: list[int], days: int, source: str, now: datetime | None = None) -> dict:
    now = now or utcnow()
    locations = {row.id: row for row in db.scalars(select(Location).where(Location.id.in_(location_ids)) if location_ids else select(Location))}
    ids = sorted(locations)
    names = {i: locations[i].name for i in ids}
    if source == "synthetic":
        model = SyntheticPrediction
        time_col = model.observed_at
        span = db.execute(select(func.min(time_col), func.max(time_col), func.count()).where(model.location_id.in_(ids))).one()
        anchor = as_utc(span[1])
        start = anchor - timedelta(days=days) if anchor else None
        query = select(model).where(model.location_id.in_(ids), time_col >= start, time_col <= anchor) if anchor else None
    else:
        model = Prediction
        time_col = model.predicted_at
        span = db.execute(select(func.min(time_col), func.max(time_col), func.count()).where(model.location_id.in_(ids))).one()
        anchor = now
        start = now - timedelta(days=days)
        query = select(model).where(model.location_id.in_(ids), time_col >= start)
    points, truncated = [], False
    if query is not None:
        rows = db.scalars(query.order_by(time_col.asc(), model.id.asc()).limit(MAX_TREND_POINTS + 1)).all()
        truncated = len(rows) > MAX_TREND_POINTS
        for row in rows[:MAX_TREND_POINTS]:
            if source == "synthetic":
                points.append({"id": row.id, "location_id": row.location_id, "location": names[row.location_id],
                               "timestamp": iso(row.observed_at), "probability": row.probability, "risk_level": row.risk_category,
                               "model_version": row.model_version, "kind": "synthetic", "horizon_hours": HORIZON_HOURS,
                               "dataset_version": row.dataset_version})
            else:
                points.append({"id": row.id, "location_id": row.location_id, "location": names[row.location_id],
                               "timestamp": iso(row.predicted_at), "probability": row.flood_probability,
                               "risk_level": row.risk_level.value, "model_version": row.model_version,
                               "kind": operational_kind(row.is_sample),
                               # Sample rows are workflow fixtures, not model output, so no horizon is claimed.
                               "horizon_hours": None if row.is_sample else HORIZON_HOURS})
    earliest, latest, total = as_utc(span[0]), as_utc(span[1]), span[2]
    available_days = None
    if earliest is not None and latest is not None:
        available_days = max(math.ceil(((anchor if source == "operational" else latest) - earliest).total_seconds() / 86400), 1)
    return {"source": source, "source_type": "synthetic" if source == "synthetic" else "operational",
            "window_days": days, "window_start": iso(start), "window_end": iso(anchor), "horizon_hours": HORIZON_HOURS,
            "anchor_kind": "latest synthetic record (simulated time)" if source == "synthetic" else "current time",
            "locations": [{"id": i, "name": names[i]} for i in ids],
            "points": points, "truncated": truncated, "max_points": MAX_TREND_POINTS,
            "data_span": {"earliest": iso(earliest), "latest": iso(latest), "stored_predictions": total, "available_days": available_days},
            "freshness": freshness(latest, now) if source == "operational" else None,
            "risk_band_thresholds": _risk_bands() if source == "synthetic" else None,
            "notice": NOTICE if source == "synthetic" else None}


# ------------------------------------------------------------------- model performance

STAGE_DESCRIPTIONS = {
    "train": "Fitting partition (in-sample; optimistic)",
    "calibration": "Probability calibration partition",
    "selection": "Model-selection partition",
    "threshold": "Alert-threshold setting partition",
    "test": "Chronological hold-out test (diagnostic)",
    "held_location": "Unseen monitoring locations",
    "storm_holdout": "Reserved storm events",
    "held_location_storm": "Unseen locations and reserved storms",
}
STAGE_ORDER = list(STAGE_DESCRIPTIONS)
METRIC_FIELDS = {"precision": "precision", "recall": "recall", "f1": "f1", "pr_auc": "pr_auc_average_precision",
                 "roc_auc": "roc_auc", "brier": "brier", "prevalence": "prevalence", "event_recall": "event_recall",
                 "median_warning_lead_hours": "median_warning_lead_hours", "threshold": "threshold"}


def _number(value):
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except (OSError, ValueError):
        return None


def _confusion(raw: str | None) -> dict | None:
    try:
        tn, fp, fn, tp = json.loads(raw or "")
        return {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)}
    except (ValueError, TypeError):
        return None


def _stage_sort(row: dict):
    return STAGE_ORDER.index(row["stage"]) if row["stage"] in STAGE_ORDER else len(STAGE_ORDER)


def _run_summary(run: Path, key: str, label: str, role: str) -> dict:
    lock = _read_json(run / "selection_lock.json")
    selected = lock.get("selected") if lock else None
    metrics_rows = _read_csv(run / "metrics.csv")
    if not lock or not selected or not metrics_rows:
        return {"key": key, "label": label, "role": role, "available": False,
                "reason": "Saved evaluation artifacts were not found for this run."}
    partitions = [{"stage": r["stage"], "rows": int(float(r["rows"])), "positives": int(float(r["positives"]))}
                  for r in _read_csv(run / "partition_summary.csv") if r.get("rows") not in (None, "")]
    for row in partitions:
        row["prevalence"] = row["positives"] / row["rows"] if row["rows"] else None
    metrics = []
    for row in metrics_rows:
        if row.get("candidate") != selected:
            continue
        entry = {"stage": row["stage"], "description": STAGE_DESCRIPTIONS.get(row["stage"], row["stage"]),
                 "rows": int(float(row["rows"])), "positives": int(float(row["positives"])),
                 "confusion": _confusion(row.get("confusion_matrix_tn_fp_fn_tp"))}
        entry.update({name: _number(row.get(column)) for name, column in METRIC_FIELDS.items()})
        metrics.append(entry)
    metrics.sort(key=_stage_sort)
    importance = []
    raw = [(r["feature"], _number(r["importance"])) for r in _read_csv(run / "feature_importance.csv")]
    total = sum(v for _, v in raw if v is not None and v > 0)
    if total > 0:
        importance = [{"feature": f, "share_percent": round(100 * v / total, 3)}
                      for f, v in sorted(((f, v) for f, v in raw if v is not None), key=lambda x: -x[1])[:15]]
    protocol = _read_json(run / "protocol.json") or {}
    summary = _read_json(run / "run_summary.json") or {}
    thresholds = summary.get("threshold")
    return {"key": key, "label": label, "role": role, "available": True, "selected_candidate": selected,
            "threshold": thresholds, "partitions": sorted(partitions, key=_stage_sort), "metrics": metrics,
            "feature_importance": importance,
            "feature_importance_method": "Share of the selected model's own importance values; scale differs between model families.",
            "dataset_version": protocol.get("dataset_version"),
            "dataset_sha256": lock.get("dataset_sha256"), "selected_before_threshold_scoring": lock.get("selected_before_threshold_scoring")}


def _deployed(model_dir: Path) -> dict | None:
    meta = _read_json(model_dir / "model_metadata.json")
    if not meta:
        return None
    return {"model_version": meta.get("model_version"), "selected_candidate": meta.get("selected_candidate"),
            "threshold": meta.get("threshold"), "threshold_feasible": meta.get("threshold_feasible"),
            "n_features": len(meta.get("features") or []), "risk_tiers": meta.get("risk_tiers"),
            "selected_at": meta.get("selected_at"), "source_type": meta.get("source_type"),
            "model_sha256": meta.get("model_sha256")}


def _dataset_overview(db: Session, version: str) -> dict | None:
    row = db.get(SyntheticDataset, version)
    if row is None:
        return None
    meta = row.metadata_json or {}
    return {"version": row.version, "observation_count": row.observation_count, "imported_at": iso(row.imported_at),
            "config": meta.get("config"), "timezone": meta.get("timezone"), "notice": meta.get("notice"),
            "source_type": meta.get("source_type", "synthetic")}


def model_performance(db: Session) -> dict:
    settings = get_settings()
    runs = Path(settings.research_runs_dir)
    v1 = _run_summary(runs / "synthetic-v1", "v1", "Synthetic Fiji V1 (CatBoost)", "deployed")
    v2 = _run_summary(runs / "synthetic-v2", "v2", "Synthetic Fiji V2 (tuned CatBoost)", "research candidate, not promoted")
    promotion = _read_json(runs / "synthetic-v2" / "promotion_final.json")
    if v2["available"]:
        v2["promotion"] = ({"promoted": promotion.get("promoted"), "criteria": promotion.get("criteria")}
                           if promotion else None)
        v2["comparison_vs_v1"] = [
            {"model": r["model"], "partition": r["partition"], "recall": _number(r["recall"]), "ap": _number(r["ap"])}
            for r in _read_csv(runs / "synthetic-v2" / "comparison_vs_v1.csv")]
    scenarios = []
    for name in ("controlled", "realistic", "stress"):
        entry = _run_summary(runs / "synthetic-v3" / name, f"v3-{name}", f"Synthetic V3 · {name} scenario", "research only")
        entry["scenario"] = name
        scenarios.append(entry)
    deployed = _deployed(Path(settings.synthetic_model_dir))
    if v1["available"] and deployed and deployed.get("selected_candidate") == v1["selected_candidate"]:
        v1["threshold"] = deployed["threshold"]
    return {
        "source_type": "synthetic", "research_only": True, "notice": NOTICE,
        "deployed_model": deployed,
        "dataset": _dataset_overview(db, "synthetic-fiji-v1"),
        "v1": v1, "v2": v2, "v3": scenarios,
        "comparability_note": ("V1, V2 and each V3 scenario were trained on different simulated datasets with different "
                               "partitions and thresholds. Their metrics are shown side by side for transparency only and "
                               "must not be ranked against each other. Simulator results are not validated Fiji forecast skill."),
        "artifacts_dir_available": runs.is_dir(),
    }
