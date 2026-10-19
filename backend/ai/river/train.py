"""Train an observed US river flood-stage POC with chronological evaluation.

From backend: OMP_NUM_THREADS=1 python -m ai.river.train
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import platform

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import fbeta_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits

from ai.area.train import score
from ai.inspection import dataset_sha256, write_json
from ai.river.data import DATA_DIR, FEATURES, INPUT_COLUMNS

MODEL_DIR = Path(__file__).resolve().parents[1] / "models" / "river"
REPORT_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "river"
TARGET = "observed_flood_stage"


def validate_dataset(data: pd.DataFrame) -> pd.DataFrame:
    required = set(INPUT_COLUMNS + [TARGET, "river_system", "forecast_date", "issued_at", "window_end", "last_input_observed_at", "target_max_stage_ft", "approved_samples", "label_source", "threshold_source"])
    if not required <= set(data) or data.empty:
        raise ValueError("Expected a non-empty observed river dataset with timing and provenance")
    if data[list(required)].isna().any().any() or data.duplicated(["area_id", "forecast_date"]).any():
        raise ValueError("Missing data or duplicate area/day rows")
    if not np.isfinite(data[FEATURES + ["target_max_stage_ft"]].to_numpy(dtype=float)).all():
        raise ValueError("River measurements must be finite")
    if not data[TARGET].isin([0, 1]).all() or not data["approved_samples"].eq(96).all():
        raise ValueError("Labels require 96 approved quarter-hour observations")
    if not (data[TARGET] == (data["target_max_stage_ft"] >= data["flood_stage_ft"])).all():
        raise ValueError("Label does not match observed maximum and official threshold")
    for column in ("label_source", "threshold_source"):
        if not data[column].astype(str).str.startswith("https://").all():
            raise ValueError("Every label requires public observation and threshold sources")
    issue = pd.to_datetime(data["issued_at"], utc=True, errors="raise")
    end = pd.to_datetime(data["window_end"], utc=True, errors="raise")
    cutoff = pd.to_datetime(data["last_input_observed_at"], utc=True, errors="raise")
    if not issue.eq(issue.dt.normalize()).all() or not issue.dt.strftime("%Y-%m-%d").eq(data["forecast_date"]).all():
        raise ValueError("Issue time must be UTC midnight on forecast_date")
    if not (end - issue).eq(pd.Timedelta(hours=24)).all() or not (issue - cutoff).eq(pd.Timedelta(hours=24, minutes=15)).all():
        raise ValueError("Invalid 24-hour forecast window or historical input cutoff")
    return data.sort_values(["forecast_date", "area_id"]).reset_index(drop=True)


def split_dataset(data: pd.DataFrame, validation_start: str, test_start: str, gap_days: int = 30) -> dict[str, pd.DataFrame]:
    validation, test = pd.Timestamp(validation_start), pd.Timestamp(test_start)
    if validation >= test or gap_days < 8:
        raise ValueError("Use increasing dates and at least eight days of separation")
    dates = pd.to_datetime(data["forecast_date"])
    gap = pd.Timedelta(days=gap_days)
    data = data.copy()
    data["event_id"] = ""
    # Group positive dates separated by <=7 days within each river system.
    for river in data["river_system"].unique():
        in_river = data["river_system"].eq(river)
        flood_dates = sorted(dates[in_river & data[TARGET].eq(1)].unique())
        events, current, previous = {}, 0, None
        for day in flood_dates:
            if previous is None or day - previous > pd.Timedelta(days=7):
                current += 1
            events[day] = f"{river}-episode-{current}"
            previous = day
        data.loc[in_river, "event_id"] = dates[in_river].map(events).where(data.loc[in_river, TARGET].eq(1), "").fillna("")
    parts = {
        "train": data[dates < validation - gap],
        "validation": data[(dates >= validation) & (dates < test - gap)],
        "test": data[dates >= test],
    }
    for name, part in parts.items():
        if part[TARGET].nunique() != 2:
            raise ValueError(f"{name} needs observed days both above and below flood stage")
    event_sets = {name: set(part.loc[part["event_id"] != "", "event_id"]) for name, part in parts.items()}
    for a, b in (("train", "validation"), ("train", "test"), ("validation", "test")):
        if event_sets[a] & event_sets[b]:
            raise ValueError(f"River flood episode crosses {a}/{b}; increase the temporal gap")
    return parts


def make_pipeline(classifier) -> Pipeline:
    preprocess = ColumnTransformer([
        ("numeric", StandardScaler(), FEATURES),
        ("area", OneHotEncoder(handle_unknown="ignore", sparse_output=False), ["area_id"]),
    ])
    return Pipeline([("preprocess", preprocess), ("classifier", classifier)])


def train(dataset_path: Path, output: Path, validation_start: str = "2022-01-01", test_start: str = "2024-01-01", gap_days: int = 30) -> dict:
    data = validate_dataset(pd.read_csv(dataset_path, dtype={"usgs_id": str}))
    parts = split_dataset(data, validation_start, test_start, gap_days)
    training, validation, testing = parts["train"], parts["validation"], parts["test"]
    candidates = {
        "logistic_regression": LogisticRegression(C=1, max_iter=2000, class_weight="balanced", random_state=42),
        "random_forest": RandomForestClassifier(n_estimators=300, min_samples_leaf=5, max_depth=10, class_weight="balanced_subsample", random_state=42, n_jobs=1),
        "gradient_boosting": HistGradientBoostingClassifier(max_iter=200, max_leaf_nodes=15, learning_rate=0.05, l2_regularization=1, random_state=42, early_stopping=False),
    }
    models, results, probabilities = {}, {}, {}
    with threadpool_limits(limits=1):
        for name, classifier in candidates.items():
            model = make_pipeline(classifier)
            model.fit(training[INPUT_COLUMNS], training[TARGET])
            prob = model.predict_proba(validation[INPUT_COLUMNS])[:, 1]
            models[name], probabilities[name] = model, prob
            results[name] = score(validation[TARGET], prob, 0.5)
        selected = max(results, key=lambda name: (results[name]["average_precision"], results[name]["roc_auc"], -results[name]["brier_score"]))
        threshold = float(max(np.linspace(0.05, 0.95, 19), key=lambda t: (
            fbeta_score(validation[TARGET], probabilities[selected] >= t, beta=2, zero_division=0), t,
        )))
        model = models[selected]
        test_prob = model.predict_proba(testing[INPUT_COLUMNS])[:, 1]
    persistence = (testing["margin_lag2_ft"] >= 0).to_numpy(dtype=float)
    report = {
        "model_version": "us-river-next24h-poc-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "geography": "Iowa River at Marengo, Iowa City and Wapello; Passaic River at Little Falls NJ, United States",
        "target": "Maximum observed river stage reaches NOAA minor flood stage in the next UTC 24 hours",
        "dataset_sha256": dataset_sha256(dataset_path), "dataset_rows": len(data),
        "software": {"python": platform.python_version(), "sklearn": sklearn.__version__, "pandas": pd.__version__, "numpy": np.__version__},
        "input_columns": INPUT_COLUMNS, "target_column": TARGET,
        "input_cutoff_hours_before_issue": 24.25,
        "selected_model": selected, "decision_threshold": threshold,
        "selection": "Validation average precision, ROC-AUC, then lower Brier score; threshold maximizes validation F2. No refit or model selection on final test.",
        "split": {"validation_start": validation_start, "test_start": test_start, "gap_days": gap_days},
        "split_support": {name: {
            "rows": len(part), "flood_stage_days": int(part[TARGET].sum()),
            "below_stage_days": int(part[TARGET].eq(0).sum()),
            "flood_episodes": int(part.loc[part["event_id"] != "", "event_id"].nunique()),
            "first_date": part["forecast_date"].min(), "last_date": part["forecast_date"].max(),
        } for name, part in parts.items()},
        "validation_models": results,
        "validation_selected_threshold": score(validation[TARGET], probabilities[selected], threshold),
        "test": score(testing[TARGET], test_prob, threshold),
        "test_persistence_baseline": score(testing[TARGET], persistence, 0.5),
        "test_always_below_stage_baseline": score(testing[TARGET], np.zeros(len(testing)), 0.5),
        "test_by_area": {}, "test_when_latest_input_below_stage": None,
        "development_only": True, "fiji_validated": False, "deployment_approved": False,
        "limitations": [
            "Gauge flood-stage exceedance is the observed target, not every type of flooding in a town.",
            "No evidence of transfer to Fiji; its gauge observations and flood thresholds are still needed.",
            "Three areas share the Iowa River; spatial transfer and performance on new river systems are not evaluated.",
            "Approved retrospective observations can be revised; real-time publication history was not reconstructed.",
            "Quarter-hour sampling can miss intervening peaks; incomplete or estimated days are excluded.",
            "Probabilities are uncalibrated; these are retrospective proof-of-concept results.",
            "Persistent multi-day flooding can make overall accuracy high; compare the persistence baseline and flood recall.",
            "The India CSV is a different task and population, so its scores are not directly comparable.",
        ],
    }
    for area in sorted(testing["area_id"].unique()):
        mask = testing["area_id"].eq(area).to_numpy()
        report["test_by_area"][area] = score(testing.loc[mask, TARGET], test_prob[mask], threshold)
    new_mask = testing["margin_lag2_ft"].lt(0).to_numpy()
    if new_mask.any():
        report["test_when_latest_input_below_stage"] = score(testing.loc[new_mask, TARGET], test_prob[new_mask], threshold)
    output.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": model, "metadata": report}, output / "river_flood_model.joblib", compress=3)
    write_json(output / "training_report.json", report)
    predictions = testing[["area_id", "forecast_date", "issued_at", "window_end", TARGET, "event_id"]].copy()
    predictions["flood_stage_probability"] = test_prob
    predictions["predicted_flood_stage"] = (test_prob >= threshold).astype(int)
    predictions["persistence_prediction"] = persistence.astype(int)
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
            {"model": "persistence_baseline", **report["test_persistence_baseline"]},
            {"model": "always_below_stage_baseline", **report["test_always_below_stage_baseline"]},
        ]).drop(columns="confusion_matrix").to_csv(args.report_dir / "test_comparison.csv", index=False)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"River training failed: {error}\n")
    print(f"Selected {report['selected_model']}; untouched 24-hour river test: {report['test']}")
    print("US river proof of concept only; not validated for Fiji.")


if __name__ == "__main__":
    main()
