"""Train next-day area models only on explicitly sourced observed flood labels.

Example (from backend):
python -m ai.area.train --features ai/data/area/features.csv \
  --labels path/to/verified_labels.csv --validation-start 2024-09-01 \
  --test-start 2025-05-01 --output ai/models/area

Labels: area_id,forecast_date,observed_flood,label_source,event_id,coverage_note.
0 requires documented non-flood monitoring; 1 requires a shared flood-event ID.
Blank outcomes are unknown and excluded. Do not label from rainfall thresholds,
warning issuance, sample alerts, or absence from an incomplete event catalogue.
"""

import argparse
import platform
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, average_precision_score, brier_score_loss, confusion_matrix,
    f1_score, fbeta_score, precision_score, recall_score, roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from ai.area.data import FEATURES, LABEL_COLUMNS, MODEL, TIMEZONE
from ai.inspection import dataset_sha256, write_json


INPUT_COLUMNS = FEATURES + ["area_id"]


def prepare_training_data(features: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    keys = ["area_id", "forecast_date"]
    required = set(INPUT_COLUMNS + ["forecast_date", "issued_at", "window_end", "latest_reference_time_bound", "weather_model", "forecast_offset_days"])
    if not required <= set(features) or not set(LABEL_COLUMNS) <= set(labels):
        raise ValueError("Expected area forecast features and the documented verified-label schema")
    for frame, name in ((features, "features"), (labels, "labels")):
        if frame[keys].isna().any().any() or frame.duplicated(keys).any():
            raise ValueError(f"Missing or duplicate area/day identifiers in {name}")
        if not frame["forecast_date"].astype(str).str.fullmatch(r"\d{4}-\d{2}-\d{2}").all():
            raise ValueError(f"Use YYYY-MM-DD forecast dates in {name}")
        pd.to_datetime(frame["forecast_date"], format="%Y-%m-%d", errors="raise")
    if not np.isfinite(features[FEATURES].to_numpy(dtype=float)).all():
        raise ValueError("Feature rows must contain complete finite forecasts")
    issue = pd.to_datetime(features["issued_at"], utc=True, errors="raise")
    window_end = pd.to_datetime(features["window_end"], utc=True, errors="raise")
    reference = pd.to_datetime(features["latest_reference_time_bound"], utc=True, errors="raise")
    if issue.isna().any() or window_end.isna().any() or reference.isna().any():
        raise ValueError("Forecast timing metadata cannot be missing")
    local_issue = issue.dt.tz_convert(TIMEZONE)
    if not (local_issue.dt.strftime("%Y-%m-%d") == features["forecast_date"]).all() or not (local_issue == local_issue.dt.normalize()).all():
        raise ValueError("Issue time must be midnight in Fiji on forecast_date")
    if not (window_end - issue == pd.Timedelta(hours=24)).all():
        raise ValueError("Prediction window must be exactly 24 hours")
    if not (reference == issue - pd.Timedelta(hours=24)).all():
        raise ValueError("Forecast references must precede issue time by the documented 24-hour bound")
    if not (features["weather_model"] == MODEL).all() or not (features["forecast_offset_days"] == 2).all():
        raise ValueError("Do not mix weather models or forecast offsets in this baseline")
    # Ignore researcher annotation columns, and prevent them shadowing predictors.
    labels = labels[LABEL_COLUMNS].copy()
    labels["observed_flood"] = pd.to_numeric(labels["observed_flood"], errors="raise")
    known = labels[labels["observed_flood"].notna()].copy()
    if known.empty:
        raise ValueError("No verified flood labels. Blank labels are unknown, not non-flood outcomes.")
    if not known["observed_flood"].isin([0, 1]).all():
        raise ValueError("Observed flood labels must be 0, 1, or blank")
    for column in ("label_source", "coverage_note"):
        if known[column].isna().any() or known[column].astype(str).str.strip().eq("").any():
            raise ValueError(f"Every known outcome requires {column}, including verified non-flood days")
    positives = known[known["observed_flood"] == 1]
    if positives["event_id"].isna().any() or positives["event_id"].astype(str).str.strip().eq("").any():
        raise ValueError("Positive observations require event_id shared across affected areas and days")
    known["event_id"] = known["event_id"].fillna("").astype(str).str.strip()
    features = features[list(required)].copy()
    joined = known.merge(features, on=keys, how="left", validate="one_to_one", indicator=True)
    if (joined["_merge"] != "both").any():
        raise ValueError("Some labelled area-days have no complete matching weather forecast")
    joined["observed_flood"] = joined["observed_flood"].astype(int)
    return joined.drop(columns="_merge").sort_values(["forecast_date", "area_id"]).reset_index(drop=True)


def temporal_split(frame: pd.DataFrame, validation_start: str, test_start: str, gap_days: int = 7, holdout_areas: tuple[str, ...] = ()) -> dict[str, pd.DataFrame]:
    validation_day, test_day = pd.Timestamp(validation_start), pd.Timestamp(test_start)
    if gap_days < 1 or validation_day >= test_day:
        raise ValueError("Use increasing split dates and a positive gap in days")
    unknown_areas = set(holdout_areas) - set(frame["area_id"])
    if unknown_areas:
        raise ValueError(f"Unknown holdout areas: {sorted(unknown_areas)}")
    dates = pd.to_datetime(frame["forecast_date"])
    seen = ~frame["area_id"].isin(holdout_areas)
    gap = pd.Timedelta(days=gap_days)
    splits = {
        "train": frame[seen & (dates < validation_day - gap)],
        "validation": frame[seen & (dates >= validation_day) & (dates < test_day - gap)],
        "test": frame[seen & (dates >= test_day)],
        "unseen_area_test": frame[~seen & (dates >= test_day)],
    }
    for name in ("train", "validation", "test"):
        if splits[name]["observed_flood"].nunique() != 2:
            raise ValueError(f"{name} needs independently observed flood and non-flood days; adjust dates or obtain more labels")
    events = {name: set(part.loc[part["event_id"] != "", "event_id"]) for name, part in splits.items()}
    for earlier, later in (("train", "validation"), ("train", "test"), ("validation", "test"), ("train", "unseen_area_test"), ("validation", "unseen_area_test")):
        if events[earlier] & events[later]:
            raise ValueError(f"Flood event crosses {earlier}/{later}; move boundaries or increase the gap")
    return splits


def make_pipeline(classifier) -> Pipeline:
    numeric = Pipeline([
        ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
        ("scale", StandardScaler()),
    ])
    preprocess = ColumnTransformer([
        ("numeric", numeric, FEATURES),
        ("area", OneHotEncoder(handle_unknown="ignore", sparse_output=False), ["area_id"]),
    ])
    return Pipeline([("preprocess", preprocess), ("classifier", classifier)])


def score(y: pd.Series, probabilities: np.ndarray, threshold: float) -> dict:
    predicted = probabilities >= threshold
    both_classes = y.nunique() == 2
    return {
        "rows": len(y), "flood_days": int(y.sum()), "flood_prevalence": float(y.mean()),
        "accuracy": float(accuracy_score(y, predicted)),
        "precision": float(precision_score(y, predicted, zero_division=0)),
        "recall": float(recall_score(y, predicted, zero_division=0)),
        "f1": float(f1_score(y, predicted, zero_division=0)),
        "f2": float(fbeta_score(y, predicted, beta=2, zero_division=0)),
        "roc_auc": float(roc_auc_score(y, probabilities)) if both_classes else None,
        "average_precision": float(average_precision_score(y, probabilities)) if both_classes else None,
        "brier_score": float(brier_score_loss(y, probabilities)),
        "confusion_matrix": confusion_matrix(y, predicted, labels=[0, 1]).tolist(),
    }


def train(features_path: Path, labels_path: Path, validation_start: str, test_start: str, output: Path, gap_days: int = 7, holdout_areas: tuple[str, ...] = ()) -> dict:
    features, labels = pd.read_csv(features_path), pd.read_csv(labels_path)
    data = prepare_training_data(features, labels)
    parts = temporal_split(data, validation_start, test_start, gap_days, holdout_areas)
    candidates = {
        "logistic_regression": LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42),
        "random_forest": RandomForestClassifier(n_estimators=300, max_depth=12, min_samples_leaf=5, class_weight="balanced_subsample", n_jobs=1, random_state=42),
        "gradient_boosting": HistGradientBoostingClassifier(max_iter=200, max_leaf_nodes=15, learning_rate=0.05, l2_regularization=1.0, class_weight="balanced", random_state=42, early_stopping=False),
    }
    pipelines, validation_results, validation_probabilities = {}, {}, {}
    training, validation, testing = parts["train"], parts["validation"], parts["test"]
    for name, classifier in candidates.items():
        pipeline = make_pipeline(classifier)
        pipeline.fit(training[INPUT_COLUMNS], training["observed_flood"])
        probabilities = pipeline.predict_proba(validation[INPUT_COLUMNS])[:, 1]
        pipelines[name] = pipeline
        validation_probabilities[name] = probabilities
        validation_results[name] = score(validation["observed_flood"], probabilities, 0.5)
    selected = max(validation_results, key=lambda name: (
        validation_results[name]["average_precision"], validation_results[name]["roc_auc"],
        -validation_results[name]["brier_score"],
    ))
    # Choose the decision threshold on validation only, never on final test rows.
    threshold = float(max(np.linspace(0.05, 0.95, 19), key=lambda value: (
        fbeta_score(validation["observed_flood"], validation_probabilities[selected] >= value, beta=2, zero_division=0), value,
    )))
    model = pipelines[selected]
    test_probability = model.predict_proba(testing[INPUT_COLUMNS])[:, 1]
    test_result = score(testing["observed_flood"], test_probability, threshold)
    baseline_probability = np.full(len(testing), training["observed_flood"].mean())
    baseline = score(testing["observed_flood"], baseline_probability, 0.5)
    per_area = {}
    for area_id in sorted(testing["area_id"].unique()):
        mask = (testing["area_id"] == area_id).to_numpy()
        per_area[area_id] = score(testing.loc[mask, "observed_flood"], test_probability[mask], threshold)
    unseen = parts["unseen_area_test"]
    report = {
        "model_version": "area-next24h-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "trained_at": datetime.now(timezone.utc).isoformat(), "selected_model": selected,
        "software": {"python": platform.python_version(), "sklearn": sklearn.__version__, "pandas": pd.__version__, "numpy": np.__version__},
        "features_sha256": dataset_sha256(features_path), "labels_sha256": dataset_sha256(labels_path),
        "input_columns": INPUT_COLUMNS, "decision_threshold": threshold,
        "target": "Observed flooding during 00:00–24:00 Pacific/Fiji on forecast_date",
        "weather_model": MODEL, "forecast_offset_days": 2, "development_only": True,
        "deployment_approved": False,
        "selection": "Validation average precision, then ROC-AUC, then lower Brier score. Validation F2 chooses threshold. No refit or selection on test data.",
        "split": {"validation_start": validation_start, "test_start": test_start, "gap_days": gap_days, "holdout_areas": list(holdout_areas)},
        "data": {"feature_rows": len(features), "verified_label_rows": len(data), "unknown_outcomes_excluded": len(features) - len(data), "rows_excluded_by_split": len(data) - sum(map(len, parts.values()))},
        "split_support": {name: {"rows": len(part), "flood_days": int(part["observed_flood"].sum()), "event_count": int(part.loc[part["event_id"] != "", "event_id"].nunique()), "first_date": part["forecast_date"].min() if len(part) else None, "last_date": part["forecast_date"].max() if len(part) else None} for name, part in parts.items()},
        "validation_models": validation_results,
        "validation_selected_threshold": score(validation["observed_flood"], validation_probabilities[selected], threshold),
        "test": test_result, "test_training_prevalence_baseline": baseline, "test_by_area": per_area,
        "unseen_area_test": score(unseen["observed_flood"], model.predict_proba(unseen[INPUT_COLUMNS])[:, 1], threshold) if not unseen.empty else None,
        "limitations": [
            "Probabilities are uncalibrated; the decision threshold is not an official MET warning threshold.",
            "Forecast inputs are from older archived runs, not the latest forecast available at each issue time.",
            "Results depend on verified area/day labels and their monitoring coverage, including negative days.",
            "Performance on unseen areas is not established unless an area holdout was supplied.",
            "This dataset/task differs from the India CSV: its scores are not a like-for-like improvement comparison.",
        ],
    }
    output.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": model, "metadata": report}, output / "area_flood_model.joblib", compress=3)
    write_json(output / "training_report.json", report)
    testing[["area_id", "forecast_date", "observed_flood", "event_id"]].assign(
        flood_probability=test_probability, predicted_flood=test_probability >= threshold,
    ).to_csv(output / "test_predictions.csv", index=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--validation-start", required=True)
    parser.add_argument("--test-start", required=True)
    parser.add_argument("--gap-days", type=int, default=7)
    parser.add_argument("--holdout-area", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = train(args.features, args.labels, args.validation_start, args.test_start, args.output, args.gap_days, tuple(args.holdout_area))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Training stopped: {error}\n")
    print(f"Selected {report['selected_model']}; untouched-test metrics: {report['test']}")


if __name__ == "__main__":
    main()
