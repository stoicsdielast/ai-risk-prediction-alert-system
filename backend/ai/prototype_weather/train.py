"""Train a retrospective next-day POC using exactly the six demo inputs."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import platform

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_curve
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from ai.area.train import score
from ai.inspection import dataset_sha256, write_json
from ai.prototype_weather.data import DATA_DIR, LABEL_COLUMNS
from ai.prototype_weather.schema import INPUT_COLUMNS, validate_inputs
from ai.river.train import split_dataset

MODEL_DIR = Path(__file__).resolve().parents[1] / "models" / "prototype_weather"
REPORT_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "prototype_weather"
TARGET = "observed_flood_stage"
MODEL_PREFIX = "prototype-weather-next24h-poc-"


def validate_dataset(data: pd.DataFrame) -> pd.DataFrame:
    required = set(INPUT_COLUMNS + LABEL_COLUMNS + [
        "weather_reference_at", "rain_window_start", "weather_source_kind", "reference_persistence",
    ])
    if data.empty or not required <= set(data):
        raise ValueError("Expected demo weather inputs with observed labels, timing and provenance")
    if data.columns.duplicated().any() or data[list(required)].isna().any().any() or data.duplicated(["area_id", "forecast_date"]).any():
        raise ValueError("Missing data or duplicate area/day rows or columns")
    inputs = validate_inputs(data)
    if not np.isfinite(data[["target_max_stage_ft", "flood_stage_ft"]].to_numpy(float)).all():
        raise ValueError("Observed stages and thresholds must be finite")
    if not data[TARGET].isin([0, 1]).all() or not data["approved_samples"].eq(96).all():
        raise ValueError("Labels require 96 approved quarter-hour observations")
    if not data[TARGET].eq(data["target_max_stage_ft"].ge(data["flood_stage_ft"])).all():
        raise ValueError("Label does not match observed maximum and official threshold")
    if not data["reference_persistence"].isin([0, 1]).all():
        raise ValueError("External persistence benchmark must be binary")
    for column in ("label_source", "threshold_source"):
        if not data[column].astype(str).str.startswith("https://").all():
            raise ValueError("Every label requires public observation and threshold sources")
    if not data["weather_source_kind"].eq("ERA5_REANALYSIS").all():
        raise ValueError("This evaluation expects explicitly identified ERA5 reanalysis")
    issue = pd.to_datetime(data["issued_at"], utc=True, errors="raise")
    end = pd.to_datetime(data["window_end"], utc=True, errors="raise")
    reference = pd.to_datetime(data["weather_reference_at"], utc=True, errors="raise")
    rain_start = pd.to_datetime(data["rain_window_start"], utc=True, errors="raise")
    if not issue.eq(issue.dt.normalize()).all() or not issue.dt.strftime("%Y-%m-%d").eq(data["forecast_date"]).all():
        raise ValueError("Issue time must be UTC midnight on forecast_date")
    if not (end - issue).eq(pd.Timedelta(hours=24)).all() or not reference.eq(issue).all() or not (issue - rain_start).eq(pd.Timedelta(hours=24)).all():
        raise ValueError("Weather must describe issue time and preceding 24 hours, with a next-24-hour target")
    result = data.copy()
    result[INPUT_COLUMNS] = inputs
    return result.sort_values(["forecast_date", "area_id"]).reset_index(drop=True)


def select_threshold(targets: pd.Series, probabilities: np.ndarray) -> float:
    """Maximize validation F2 across all observed score cutoffs, including <.05."""
    precision, recall, thresholds = precision_recall_curve(targets, probabilities)
    denominator = 4 * precision[:-1] + recall[:-1]
    f2 = np.divide(5 * precision[:-1] * recall[:-1], denominator,
                   out=np.zeros_like(denominator), where=denominator > 0)
    # Thresholds increase; the final exact tie is the most conservative cutoff.
    return float(thresholds[np.flatnonzero(f2 == f2.max())[-1]])


def train(dataset_path: Path, output: Path, validation_start: str = "2022-01-01", test_start: str = "2024-01-01", gap_days: int = 30) -> dict:
    data = validate_dataset(pd.read_csv(dataset_path))
    parts = split_dataset(data, validation_start, test_start, gap_days)
    training, validation, testing = parts["train"], parts["validation"], parts["test"]
    # Every fit and prediction receives only these six numeric columns.
    inputs = {name: validate_inputs(part) for name, part in parts.items()}
    candidates = {
        "logistic_regression": LogisticRegression(C=1, max_iter=2000, class_weight="balanced", random_state=42),
        "random_forest": RandomForestClassifier(n_estimators=300, min_samples_leaf=5, max_depth=10, class_weight="balanced_subsample", random_state=42, n_jobs=1),
        "gradient_boosting": HistGradientBoostingClassifier(max_iter=200, max_leaf_nodes=15, learning_rate=0.05, l2_regularization=1, random_state=42, early_stopping=False),
    }
    models, results, probabilities = {}, {}, {}
    with threadpool_limits(limits=1):
        for name, classifier in candidates.items():
            model = Pipeline([("scale", StandardScaler()), ("classifier", classifier)])
            model.fit(inputs["train"], training[TARGET])
            prob = model.predict_proba(inputs["validation"])[:, 1]
            models[name], probabilities[name] = model, prob
            results[name] = score(validation[TARGET], prob, 0.5)
        selected = max(results, key=lambda name: (results[name]["average_precision"], results[name]["roc_auc"], -results[name]["brier_score"]))
        threshold = select_threshold(validation[TARGET], probabilities[selected])
        model = models[selected]
        test_prob = model.predict_proba(inputs["test"])[:, 1]
    prevalence = float(training[TARGET].mean())
    report = {
        "model_version": MODEL_PREFIX + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "geography": "Iowa River at Marengo, Iowa City and Wapello; Passaic River at Little Falls NJ, United States",
        "target": "Maximum observed quarter-hour river stage reaches NOAA minor flood stage in the next UTC 24 hours",
        "feature_contract": "frontend/src/types/prototype.ts WeatherLocation numeric weather/location fields",
        "input_columns": INPUT_COLUMNS, "target_column": TARGET,
        "weather_semantics": "Preceding-24-hour rain total; instantaneous temperature/humidity/wind at issue; gauge coordinates",
        "evaluation_kind": "RETROSPECTIVE_REANALYSIS_POC",
        "dataset_sha256": dataset_sha256(dataset_path), "dataset_rows": len(data),
        "software": {"python": platform.python_version(), "sklearn": sklearn.__version__, "pandas": pd.__version__, "numpy": np.__version__},
        "selected_model": selected, "decision_threshold": threshold,
        "selection": "Validation average precision, ROC-AUC, then lower Brier score; threshold maximizes validation F2 across observed validation probabilities, ties prefer higher thresholds. No refit; test outcomes are not used in selection.",
        "split": {"validation_start": validation_start, "test_start": test_start, "gap_days": gap_days},
        "split_support": {name: {
            "rows": len(part), "flood_stage_days": int(part[TARGET].sum()),
            "below_stage_days": int(part[TARGET].eq(0).sum()),
            "flood_episodes": int(part.loc[part["event_id"] != "", "event_id"].nunique()),
            "first_date": part["forecast_date"].min(), "last_date": part["forecast_date"].max(),
        } for name, part in parts.items()},
        "training_input_ranges": {name: {"min": float(inputs["train"][name].min()), "max": float(inputs["train"][name].max())} for name in INPUT_COLUMNS},
        "validation_models": results,
        "validation_selected_threshold": score(validation[TARGET], probabilities[selected], threshold),
        "test": score(testing[TARGET], test_prob, threshold),
        "test_training_prevalence_baseline": score(testing[TARGET], np.full(len(testing), prevalence), 0.5),
        "test_always_below_stage_baseline": score(testing[TARGET], np.zeros(len(testing)), 0.5),
        "test_external_gauge_persistence": score(testing[TARGET], testing["reference_persistence"].to_numpy(float), 0.5),
        "external_benchmark_note": "Gauge persistence uses two-day-old river stage unavailable in the demo; it is a reference only and never a model input.",
        "test_by_area": {},
        "prototype_input_compatible": True, "development_only": True,
        "operational_forecast_validated": False, "fiji_validated": False, "calibrated": False,
        "limitations": [
            "ERA5 is retrospective reanalysis published after weather valid time; this is a hindcast association POC, not validated operational forecast skill.",
            "US gauge flood-stage exceedance does not establish flood or non-flood conditions throughout an area, or transfer to Fiji.",
            "Only four gauges across two river systems; no unseen-area or unseen-river validation.",
            "Very few independent flood episodes in training and validation make model selection and thresholds unstable; consult split_support.",
            "Test years were previously inspected for the river-input POC; this comparison is development evidence, not a fresh independent final evaluation.",
            "An initial weather run exposed a coarse fixed threshold grid that missed small scores; threshold search was corrected to all validation score cutoffs after that run. A fresh future evaluation is still required.",
            "The cohort inherits the earlier river pipeline's strict gauge coverage and history exclusions.",
            "Quarter-hour stage sampling can miss intervening peaks; incomplete or estimated observations are excluded.",
            "Local weather omits upstream rainfall, storage and river stage. Temperature/humidity/wind are snapshots, not future daily averages.",
            "Probabilities are uncalibrated. High accuracy can reflect rare floods; inspect precision, recall and average precision.",
            "The frontend still uses prototype weather fixtures; this training command does not connect a live weather feed or publish alerts.",
        ],
    }
    for area in sorted(testing["area_id"].unique()):
        mask = testing["area_id"].eq(area).to_numpy()
        report["test_by_area"][area] = score(testing.loc[mask, TARGET], test_prob[mask], threshold)
    output.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": model, "metadata": report}, output / "prototype_weather_model.joblib", compress=3)
    write_json(output / "training_report.json", report)
    predictions = testing[["area_id", "forecast_date", "issued_at", "window_end", TARGET, "event_id"]].copy()
    predictions["flood_stage_probability"] = test_prob
    predictions["predicted_flood_stage"] = (test_prob >= threshold).astype(int)
    predictions.to_csv(output / "test_predictions.csv", index=False)
    pd.DataFrame([{"model": name, **values} for name, values in results.items()]).drop(columns="confusion_matrix").to_csv(output / "validation_model_comparison.csv", index=False)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATA_DIR / "dataset.csv")
    parser.add_argument("--output", type=Path, default=MODEL_DIR)
    parser.add_argument("--validation-start", default="2022-01-01")
    parser.add_argument("--test-start", default="2024-01-01")
    parser.add_argument("--gap-days", type=int, default=30)
    parser.add_argument("--report-dir", type=Path, default=REPORT_DIR)
    args = parser.parse_args()
    try:
        report = train(args.dataset, args.output, args.validation_start, args.test_start, args.gap_days)
        write_json(args.report_dir / "training_report.json", report)
        pd.DataFrame([
            {"model": report["selected_model"], **report["test"]},
            {"model": "training_prevalence_baseline", **report["test_training_prevalence_baseline"]},
            {"model": "always_below_stage_baseline", **report["test_always_below_stage_baseline"]},
            {"model": "external_gauge_persistence", **report["test_external_gauge_persistence"]},
        ]).drop(columns="confusion_matrix").to_csv(args.report_dir / "test_comparison.csv", index=False)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"Demo weather training failed: {error}\n")
    print(f"Selected {report['selected_model']}; six-input retrospective test: {report['test']}")
    print("US proof of concept with retrospective weather; not validated for live forecasts or Fiji.")


if __name__ == "__main__":
    main()
