"""Inspect, split, train, compare, and persist the standalone flood prototype."""

import argparse
import importlib.metadata
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

from .config import (
    ARTIFACTS_DIR, CATEGORICAL_FEATURES, DEFAULT_DATASET, EXCLUDED_FEATURES,
    FEATURE_COLUMNS, METADATA_PATH, MODEL_PATH, MODELS_DIR, NUMERIC_FEATURES,
    PROCESSED_DIR, PROTOTYPE_VERSION, RANDOM_STATE, RISK_THRESHOLDS, TARGET_COLUMN,
    TEST_SIZE,
)
from .evaluate import (
    SELECTION_PRIORITY, evaluate_model, print_model_comparison,
    save_confusion_matrix, save_feature_importance, select_best_model,
)
from .inspection import inspect_dataset, read_dataset, validate_dataset, write_json
from .predict import load_model, predict_flood_risk, print_test_prediction
from .preprocessing import build_model_pipeline


def distribution(target: pd.Series) -> dict[str, int]:
    return {str(label): int(count) for label, count in target.value_counts().sort_index().items()}


def train(dataset_path: Path = DEFAULT_DATASET) -> dict[str, Any]:
    frame = read_dataset(dataset_path)
    # Inspection is deliberately printed and saved before constructing preprocessing.
    inspection = inspect_dataset(frame, dataset_path)
    write_json(ARTIFACTS_DIR / "dataset_summary.json", inspection)
    validate_dataset(frame)
    features = frame[list(FEATURE_COLUMNS)]
    target = frame[TARGET_COLUMN].astype(int)
    try:
        x_train, x_test, y_train, y_test = train_test_split(
            features, target, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=target,
        )
    except ValueError as error:
        raise ValueError(f"Unable to make a stratified 80/20 split: {error}") from error
    if y_train.nunique() != 2 or y_test.nunique() != 2:
        raise ValueError("Both train and test splits need flood and non-flood records.")
    print("\nTRAIN/TEST SPLIT")
    print(f"Training records: {len(x_train)}; testing records: {len(x_test)}")
    print("Training target distribution:", distribution(y_train))
    print("Testing target distribution:", distribution(y_test))
    classifiers = {
        "Logistic Regression": LogisticRegression(
            max_iter=1000, class_weight="balanced", random_state=RANDOM_STATE,
        ),
        "Random Forest": RandomForestClassifier(
            n_estimators=200, min_samples_leaf=2, max_features="sqrt",
            # One worker keeps probability summation order reproducible, including near-ties.
            class_weight="balanced", random_state=RANDOM_STATE, n_jobs=1,
        ),
    }
    pipelines = {}
    results = {}
    for name, classifier in classifiers.items():
        print(f"\nTraining {name} (training rows only)...", flush=True)
        pipeline = build_model_pipeline(classifier)
        pipeline.fit(x_train, y_train)
        pipelines[name] = pipeline
        results[name] = evaluate_model(pipeline, x_test, y_test)
    comparison = print_model_comparison(results)
    comparison.to_csv(ARTIFACTS_DIR / "model_comparison.csv")
    selected_name = select_best_model(results)
    selected_result = results[selected_name]
    selection_reason = (
        f"Selected {selected_name} by lexicographic priority: flood recall, F1, ROC-AUC, "
        f"then accuracy. Winning values: "
        + ", ".join(f"{metric}={selected_result[metric]:.6f}" for metric in SELECTION_PRIORITY)
        + ". Exact ties keep model training order."
    )
    print("\nBEST MODEL:", selection_reason)
    print("The test split is used for selection; metrics are development comparisons, "
          "not an independent final assessment.")
    majority_class = int(y_train.mode().iloc[0])
    majority_accuracy = float((y_test == majority_class).mean())
    print(f"Majority-class reference (class {majority_class}): accuracy={majority_accuracy:.6f}")
    if all(result["roc_auc"] < 0.60 for result in results.values()):
        print("DATASET CONCERN: Both ROC-AUC values are below 0.60. "
              "Measured discrimination is weak; these results do not validate warning capability.")
    ranked = save_feature_importance(pipelines["Random Forest"], ARTIFACTS_DIR)
    save_confusion_matrix(selected_result, ARTIFACTS_DIR / "confusion_matrix.png")

    trained_at = datetime.now(timezone.utc).isoformat()
    versions = {package: importlib.metadata.version(package) for package in (
        "pandas", "numpy", "scikit-learn", "joblib", "matplotlib",
    )}
    model_version = (
        f"{PROTOTYPE_VERSION}-{inspection['dataset_sha256'][:12]}-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}"
    )
    metadata = {
        "model_type": selected_name,
        "training_datetime_utc": trained_at,
        "dataset_filename": dataset_path.name,
        "dataset_row_count": len(frame),
        "dataset_column_count": len(frame.columns),
        "dataset_sha256": inspection["dataset_sha256"],
        "feature_columns": list(FEATURE_COLUMNS),
        "numeric_features": list(NUMERIC_FEATURES),
        "categorical_features": list(CATEGORICAL_FEATURES),
        "excluded_features": EXCLUDED_FEATURES,
        "target_column": TARGET_COLUMN,
        "class_labels": {"0": "Non-flood", "1": "Flood"},
        "training_size": len(x_train),
        "testing_size": len(x_test),
        "training_target_distribution": distribution(y_train),
        "testing_target_distribution": distribution(y_test),
        "test_fraction": TEST_SIZE,
        "random_state": RANDOM_STATE,
        "stratified": True,
        "test_row_indices": x_test.index.tolist(),
        "model_version": model_version,
        "selection_priority": SELECTION_PRIORITY,
        "selection_reason": selection_reason,
        "evaluation_limitation": "Same test split used for comparison/selection; no independent final validation.",
        "prototype_risk_thresholds": list(RISK_THRESHOLDS),
        "probability_calibration": "Not calibrated; confidence_percent is only P(flood) times 100.",
        "development_data_only": True,
        "python_version": platform.python_version(),
        "dependency_versions": versions,
        **{name: selected_result[name] for name in ("accuracy", "precision", "recall", "f1", "roc_auc")},
    }
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_filenames = {
        "Logistic Regression": "logistic_regression.joblib",
        "Random Forest": "random_forest.joblib",
    }
    for name, pipeline in pipelines.items():
        # Metadata travels with each pipeline, keeping inference independent of other files.
        pipeline.flood_metadata_ = {
            **metadata, "model_type": name,
            **{key: results[name][key] for key in ("accuracy", "precision", "recall", "f1", "roc_auc")},
        }
        joblib.dump(pipeline, MODELS_DIR / model_filenames[name], compress=3)
    joblib.dump(pipelines[selected_name], MODEL_PATH, compress=3)
    write_json(METADATA_PATH, metadata)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    test_rows = x_test.assign(**{TARGET_COLUMN: y_test})
    test_rows.to_csv(PROCESSED_DIR / "test_split.csv", index=True, index_label="source_row_index")
    sample_row = x_test.iloc[0]
    sample = {
        "source_row_index": int(sample_row.name),
        "input_data": sample_row.to_dict(),
        "actual_label": int(y_test.iloc[0]),
        "model_version": model_version,
    }
    write_json(PROCESSED_DIR / "test_sample.json", sample)
    # Demonstrate inference from the actual persisted model, rather than an in-memory classifier.
    prediction = predict_flood_risk(sample["input_data"], model=load_model())
    print_test_prediction(sample, prediction)
    report = {
        "model_version": model_version,
        "dataset": inspection["shape"] | {"filename": dataset_path.name, "sha256": inspection["dataset_sha256"]},
        "split": {"train": len(x_train), "test": len(x_test), "random_state": RANDOM_STATE, "stratified": True},
        "models": results,
        "selected_model": selected_name,
        "selection_priority": SELECTION_PRIORITY,
        "selection_reason": selection_reason,
        "majority_class_reference": {"class": majority_class, "accuracy": majority_accuracy},
        "top_random_forest_features": ranked.head(10).to_dict(orient="records"),
        "example_prediction": {"sample": sample, "prediction": prediction},
        "limitations": inspection["concerns"] + [metadata["evaluation_limitation"], metadata["probability_calibration"]],
    }
    write_json(ARTIFACTS_DIR / "model_results.json", report)
    print("\nTRAINING MILESTONE REPORT")
    for step in (
        f"Dataset: {dataset_path.name} ({frame.shape[0]} rows, {frame.shape[1]} columns)",
        "Preprocessing: numeric median + scaling; category mode + one-hot, fitted on training only",
        f"Train/Test Split: {len(x_train)}/{len(x_test)}, stratified, seed {RANDOM_STATE}",
        "Models Trained: Logistic Regression and Random Forest",
        "Evaluation: accuracy, flood precision/recall/F1, ROC-AUC, reports, confusion matrices",
        f"Best Model: {selected_name} (flood recall first)",
        "Saved Model: backend/ai/models/flood_risk_model.joblib (complete pipeline)",
        f"Example Prediction: row {sample['source_row_index']}; "
        f"P(flood)={prediction['flood_probability']:.6f}, {prediction['risk_level']}, label={sample['actual_label']}",
    ):
        print(step)
        if not step.startswith("Example Prediction"):
            print("↓")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    args = parser.parse_args()
    try:
        train(args.dataset)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Training failed: {error}\n")


if __name__ == "__main__":
    main()
