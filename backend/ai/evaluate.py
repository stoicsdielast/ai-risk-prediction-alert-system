"""Shared metrics, plots, and independent replay of saved-model evaluation."""

import argparse
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import (
    ConfusionMatrixDisplay, accuracy_score, classification_report,
    confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from .config import ARTIFACTS_DIR, DEFAULT_DATASET, MODEL_PATH, TARGET_COLUMN
from .inspection import dataset_sha256, read_dataset, write_json

METRIC_COLUMNS = ["accuracy", "precision", "recall", "f1", "roc_auc"]
SELECTION_PRIORITY = ["recall", "f1", "roc_auc", "accuracy"]


def flood_probabilities(model: Pipeline, features: pd.DataFrame) -> np.ndarray:
    classes = list(model.classes_)
    if 1 not in classes:
        raise ValueError("Saved classifier has no flood class (1).")
    return model.predict_proba(features)[:, classes.index(1)]


def evaluate_model(model: Pipeline, features: pd.DataFrame, target: pd.Series) -> dict[str, Any]:
    predicted = model.predict(features)
    probability = flood_probabilities(model, features)
    return {
        "accuracy": float(accuracy_score(target, predicted)),
        "precision": float(precision_score(target, predicted, pos_label=1, zero_division=0)),
        "recall": float(recall_score(target, predicted, pos_label=1, zero_division=0)),
        "f1": float(f1_score(target, predicted, pos_label=1, zero_division=0)),
        "roc_auc": float(roc_auc_score(target, probability)) if target.nunique() == 2 else None,
        "classification_report": classification_report(
            target, predicted, labels=[0, 1], target_names=["Non-flood (0)", "Flood (1)"],
            output_dict=True, zero_division=0,
        ),
        "confusion_matrix": confusion_matrix(target, predicted, labels=[0, 1]).tolist(),
    }


def select_best_model(results: dict[str, dict[str, Any]]) -> str:
    if not results:
        raise ValueError("No trained model results to compare.")
    return max(results, key=lambda name: tuple(
        results[name][metric] if results[name][metric] is not None else float("-inf")
        for metric in SELECTION_PRIORITY
    ))


def print_model_comparison(results: dict[str, dict[str, Any]]) -> pd.DataFrame:
    comparison = pd.DataFrame.from_dict(results, orient="index")[METRIC_COLUMNS]
    comparison.index.name = "model"
    print("\nMODEL COMPARISON (positive class = Flood, label 1)")
    print(comparison.to_string(float_format=lambda value: f"{value:.6f}"))
    for name, result in results.items():
        print(f"\n{name} classification report:")
        print(pd.DataFrame(result["classification_report"]).T.to_string())
        print("Confusion matrix [rows Actual, columns Predicted; order 0, 1]:")
        print(np.array(result["confusion_matrix"]))
    return comparison


def save_confusion_matrix(result: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    display = ConfusionMatrixDisplay(
        confusion_matrix=np.array(result["confusion_matrix"]),
        display_labels=["Non-flood (0)", "Flood (1)"],
    )
    display.plot()
    display.ax_.set_xlabel("Predicted")
    display.ax_.set_ylabel("Actual")
    display.ax_.set_title("Selected model — prototype test split")
    display.figure_.tight_layout()
    display.figure_.savefig(path)
    plt.close(display.figure_)


def save_feature_importance(model: Pipeline, directory: Path) -> pd.DataFrame:
    names = model.named_steps["preprocessor"].get_feature_names_out()
    importance = model.named_steps["classifier"].feature_importances_
    ranked = pd.DataFrame({"feature": names, "importance": importance}).sort_values(
        "importance", ascending=False, kind="stable",
    ).reset_index(drop=True)
    directory.mkdir(parents=True, exist_ok=True)
    ranked.to_csv(directory / "feature_importance.csv", index=False)
    print("\nTOP 10 RANDOM FOREST FEATURES (impurity importance; not causal effects)")
    print(ranked.head(10).to_string(index=False))
    top = ranked.head(10).iloc[::-1]
    figure, axis = plt.subplots(figsize=(9, 6))
    axis.barh(top["feature"], top["importance"])
    axis.set_xlabel("Random Forest impurity importance")
    axis.set_ylabel("Transformed feature")
    axis.set_title("Top 10 features — development dataset")
    figure.tight_layout()
    figure.savefig(directory / "feature_importance.png")
    plt.close(figure)
    return ranked


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--model", type=Path, default=MODEL_PATH)
    args = parser.parse_args()
    try:
        from .predict import load_model

        model = load_model(args.model)
        metadata = model.flood_metadata_
        if dataset_sha256(args.dataset) != metadata["dataset_sha256"]:
            raise ValueError("Dataset differs from the training source; use the original CSV.")
        frame = read_dataset(args.dataset)
        _, test_indices = train_test_split(
            frame.index.to_numpy(), test_size=metadata["test_fraction"],
            random_state=metadata["random_state"], stratify=frame[TARGET_COLUMN],
        )
        if test_indices.tolist() != metadata["test_row_indices"]:
            raise ValueError("Split differs from training; check dependency versions.")
        result = evaluate_model(
            model, frame.loc[test_indices, metadata["feature_columns"]],
            frame.loc[test_indices, TARGET_COLUMN],
        )
        print_model_comparison({metadata["model_type"]: result})
        write_json(ARTIFACTS_DIR / "selected_model_evaluation.json", {
            "model_version": metadata["model_version"], "testing_size": len(test_indices),
            "metrics": result,
        })
        save_confusion_matrix(result, ARTIFACTS_DIR / "confusion_matrix.png")
        print("Evaluation replayed on the original held-out rows; no model was retrained.")
        print("This split was also used for model selection; an independent validation set is still needed.")
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Evaluation failed: {error}\n")


if __name__ == "__main__":
    main()
