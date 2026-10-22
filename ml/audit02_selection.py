"""Read-only extension of training-02: matched comparisons, frozen before scoring."""
import argparse
import json
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve

from ml.config import FEATURES, TARGET
from ml.refinement import (FEATURE_SETS, calibrated, directory_hashes, recall_budget_threshold,
                           reliability, score, sha256, threshold_table)
from ml.report02 import markdown_table
from ml.train import pipeline, write_json
from ml.training02 import estimator, load_development, protect_paths, read

DEFAULT_SOURCE = Path("ml/runs/training-02")
DEFAULT_OUT = Path("ml/runs/training-02-selection-audit")
SAVED_BASES = ["catboost__hydrology__balanced", "catboost__baseline__balanced", "lightgbm__baseline__balanced"]


def transitions(y, old, new):
    y, old, new = np.asarray(y), np.asarray(old, dtype=bool), np.asarray(new, dtype=bool)
    return {"both_detected": int(((y == 1) & old & new).sum()),
            "lost_detection": int(((y == 1) & old & ~new).sum()),
            "recovered_detection": int(((y == 1) & ~old & new).sum()),
            "both_missed": int(((y == 1) & ~old & ~new).sum())}


def verify_source(out):
    plan = read(out / "plan.json")
    source = Path(plan["source"])
    if directory_hashes(source) != plan["source_hashes"]:
        raise ValueError("training-02 changed; refusing audit continuation")
    baseline = Path(read(source / "plan.json")["baseline_directory"])
    if directory_hashes(baseline) != plan["baseline_hashes"]:
        raise ValueError("training-01 changed; refusing audit continuation")
    return source, plan


def prepare(source, out):
    protect_paths(out, source)
    if out.exists(): raise ValueError("Audit output exists; choose a new directory")
    data, parts = load_development(source)
    candidates = read(source / "candidate_models.json")
    original_threshold = read(source / "thresholds.json")["original_baseline_threshold"]
    predictions = pd.read_parquet(source / "development_predictions.parquet")
    keys = ["date", "station_id", "stage", TARGET]
    pd.testing.assert_frame_equal(data[keys].reset_index(drop=True), predictions[keys].reset_index(drop=True))
    if not np.isfinite(predictions.drop(columns=keys).to_numpy()).all():
        raise ValueError("Candidate predictions have missing/different evaluation rows")
    out.mkdir(parents=True)
    baseline = Path(read(source / "plan.json")["baseline_directory"])
    plan = {"source": str(source.resolve()), "source_hashes": directory_hashes(source),
            "baseline_hashes": directory_hashes(baseline), "candidate_bases": SAVED_BASES,
            "matched_controls": ["catboost_baseline_depth6_l2_10", "catboost_hydrology_depth4_l2_5"],
            "matched_parameters": "Existing two CatBoost configurations only; no new search, same 350 iterations/.04 learning rate/seed/weights/training rows",
            "selection": "No winner selected in this audit; every predeclared candidate reported",
            "threshold": "Per-candidate maximum 2023 H2 recall under the same original baseline validation FP/TP budget",
            "test_caveat": "Additional scoring of previously inspected frozen temporal/spatial records is retrospective diagnostic reuse, not a new untouched test. No final labels optimize any model, calibrator or threshold.",
            "original_threshold_coverage": "All 43 models had the same threshold block at .5; only chosen CatBoost and original LR had optimized thresholds in training-02"}
    write_json(out / "plan.json", plan)
    split_checks = []
    for stage, group in data.groupby("stage", sort=False):
        key_hash = __import__("hashlib").sha256(group[["date", "station_id"]].to_csv(index=False).encode()).hexdigest()
        split_checks.append(dict(stage=stage, rows=len(group), positives=int(group[TARGET].sum()),
                                 all_43_prediction_columns_same_rows=True, row_key_sha256=key_hash))
    pd.DataFrame(split_checks).to_csv(out / "split_identity.csv", index=False)
    models, dev_probabilities = {}, {}
    for base_id in SAVED_BASES:
        for method in ("none", "sigmoid", "isotonic"):
            model_id = base_id + "__" + method
            models[model_id] = {**candidates[model_id], "file": str((source / candidates[model_id]["file"]).resolve()), "new_fit": False}
            dev_probabilities[model_id] = predictions[model_id].to_numpy()
    # These two predeclared train-only fits separate feature additions from the
    # different depth/regularization chosen by tuning. Never use final labels.
    for feature_set, depth, regularization in [("baseline", 6, 10.), ("hydrology", 4, 5.)]:
        features = FEATURE_SETS[feature_set]
        spec = dict(family="catboost", feature_set=feature_set, balanced=True, parameters={"depth": depth, "l2_leaf_reg": regularization})
        fitted = pipeline(estimator(spec)).fit(parts["train"][features], parts["train"][TARGET].astype(int))
        for method in ("none", "sigmoid", "isotonic"):
            model_id = f"matched__{feature_set}__depth{depth}__{method}"
            model = calibrated(fitted, parts["calibration"], features, method)
            file = out / (model_id + ".joblib"); joblib.dump(model, file)
            models[model_id] = {"file": str(file.resolve()), "features": features, "method": method,
                                "feature_set": feature_set, "family": "catboost", "parameters": spec["parameters"], "new_fit": True}
            dev_probabilities[model_id] = model.predict_proba(data[features])[:, 1]
    threshold_mask = data.stage.eq("threshold").to_numpy()
    reference = score(data.loc[threshold_mask, TARGET], predictions.loc[threshold_mask, "original_baseline"], original_threshold)
    budget = reference["false_alerts_per_detection"]
    locked, rows, table_rows = {}, [], []
    for model_id, p in dev_probabilities.items():
        operating = threshold_table(data.loc[threshold_mask, TARGET], p[threshold_mask])
        try:
            choice = recall_budget_threshold(operating, budget)
            threshold, feasible = float(choice["threshold"]), True
        except ValueError:
            threshold, feasible = float(np.nextafter(1., 2.)), False
        # Nonfeasible controls are explicitly research no-alert policies, not API
        # threshold configurations. No forced recall or model substitution.
        locked[model_id] = {"threshold": threshold, "feasible": feasible, "model_sha256": sha256(models[model_id]["file"])}
        for stage in ["train", "tuning", "calibration", "selection", "threshold"]:
            mask = data.stage.eq(stage).to_numpy()
            rows.append(dict(model_id=model_id, stage=stage, policy="same_budget", **score(data.loc[mask, TARGET], p[mask], threshold)))
        for policy, t in [("default_0_5", .5), ("same_budget", threshold)]:
            table_rows.append(dict(model_id=model_id, policy=policy, **score(data.loc[threshold_mask, TARGET], p[threshold_mask], t)))
        operating.assign(model_id=model_id).to_csv(out / (model_id + "__thresholds.csv"), index=False)
    write_json(out / "models.json", models)
    pd.DataFrame(rows).to_csv(out / "development_comparison.csv", index=False)
    pd.DataFrame(table_rows).to_csv(out / "validation_threshold_comparison.csv", index=False)
    lock = {"models": locked, "budget": budget, "original_validation": reference, "original_threshold": original_threshold,
            "plan_sha256": sha256(out / "plan.json"), "holdout_sha256": sha256(source / "evaluation_holdout.parquet"),
            "code_sha256": sha256(__file__)}
    write_json(out / "comparison_lock.json", lock)
    verify_source(out)
    print("Audit comparisons and validation-only thresholds frozen; no final holdout read.", flush=True)


def evaluate(out):
    if (out / "evaluation.csv").exists(): raise ValueError("Audit evaluation already completed")
    source, plan = verify_source(out)
    lock, models = read(out / "comparison_lock.json"), read(out / "models.json")
    if lock["code_sha256"] != sha256(__file__) or lock["plan_sha256"] != sha256(out / "plan.json"):
        raise ValueError("Audit code/plan changed after thresholds were frozen")
    if sha256(source / "evaluation_holdout.parquet") != lock["holdout_sha256"]: raise ValueError("Final records changed")
    final = pd.read_parquet(source / "evaluation_holdout.parquet")
    original = joblib.load(source / "original_baseline.joblib")
    old = original.predict_proba(final[FEATURES])[:, 1]
    predictions = final[["date", "station_id", "stage", TARGET]].copy()
    rows, station_rows, movements = [], [], []
    for model_id, config in models.items():
        if sha256(config["file"]) != lock["models"][model_id]["model_sha256"]: raise ValueError("Candidate changed")
        p = joblib.load(config["file"]).predict_proba(final[config["features"]])[:, 1]
        predictions[model_id] = p
        for policy, threshold in [("default_0_5", .5), ("same_budget", lock["models"][model_id]["threshold"])]:
            for stage in ("test", "holdout_station"):
                mask = final.stage.eq(stage).to_numpy()
                rows.append(dict(model_id=model_id, policy=policy, stage=stage, threshold=threshold, **score(final.loc[mask, TARGET], p[mask], threshold)))
                if policy == "same_budget":
                    for station_id, group in final.loc[mask].groupby("station_id"):
                        m = mask & final.station_id.eq(station_id).to_numpy()
                        station_rows.append(dict(model_id=model_id, stage=stage, station_id=station_id, **score(final.loc[m, TARGET], p[m], threshold)))
                    movements.append(dict(model_id=model_id, stage=stage, **transitions(final.loc[mask, TARGET], old[mask] >= lock["original_threshold"], p[mask] >= threshold)))
    for stage in ("test", "holdout_station"):
        m = final.stage.eq(stage).to_numpy()
        rows.append(dict(model_id="original_logistic", policy="original", stage=stage, threshold=lock["original_threshold"], **score(final.loc[m, TARGET], old[m], lock["original_threshold"])))
    pd.DataFrame(rows).to_csv(out / "evaluation.csv", index=False)
    pd.DataFrame(station_rows).to_csv(out / "per_station.csv", index=False)
    pd.DataFrame(movements).to_csv(out / "detection_transitions.csv", index=False)
    predictions.to_parquet(out / "predictions.parquet", index=False)
    # Verify that a monotone sigmoid map, with separately optimized operating
    # points on identical validation rows, preserves the same detections.
    invariance = []
    for base_id in SAVED_BASES:
        a, b = base_id + "__none", base_id + "__sigmoid"
        aa = predictions[a].to_numpy() >= lock["models"][a]["threshold"]
        bb = predictions[b].to_numpy() >= lock["models"][b]["threshold"]
        invariance.append(dict(base_id=base_id, evaluation_decision_disagreements=int((aa != bb).sum())))
    write_json(out / "sigmoid_operating_point_invariance.json", invariance)
    verify_source(out)
    render(out)


def render(out):
    source, plan = verify_source(out)
    locked = read(out / "comparison_lock.json")
    development = pd.read_csv(out / "development_comparison.csv")
    final = pd.read_csv(out / "evaluation.csv")
    threshold = pd.read_csv(out / "validation_threshold_comparison.csv")
    gate = .95 * read(source / "model_choice.json")["baseline_selection_ap"]
    models = read(out / "models.json")
    selection = pd.read_csv(source / "selection_metrics.csv")
    selected_ids = [base + "__" + method for base in SAVED_BASES for method in ("none", "sigmoid", "isotonic")]
    eligibility = selection[selection.model_id.isin(selected_ids)].copy()
    eligibility["AP_floor"] = gate
    eligibility["eligible"] = eligibility.pr_auc_average_precision >= gate
    eligibility.to_csv(out / "selection_eligibility.csv", index=False)
    # Within fixed depth/regularization/method, these differences isolate adding
    # the eight hydrology features. They are descriptive, never new selection.
    contrasts = []
    for depth in (4, 6):
        for method in ("none", "sigmoid", "isotonic"):
            baseline_id = ("catboost__baseline__balanced__" if depth == 4 else "matched__baseline__depth6__") + method
            hydrology_id = ("matched__hydrology__depth4__" if depth == 4 else "catboost__hydrology__balanced__") + method
            for stage in ("tuning", "selection", "threshold", "test", "holdout_station"):
                table = development if stage in ("tuning", "selection", "threshold") else final[final.policy.eq("same_budget")]
                a = table[table.model_id.eq(baseline_id) & table.stage.eq(stage)].iloc[0]
                b = table[table.model_id.eq(hydrology_id) & table.stage.eq(stage)].iloc[0]
                contrasts.append({"depth": depth, "method": method, "stage": stage,
                                  **{key + "_hydrology_minus_baseline": float(b[key] - a[key]) for key in ["recall", "f1", "brier", "pr_auc_average_precision"]}})
    pd.DataFrame(contrasts).to_csv(out / "matched_hydrology_effect.csv", index=False)
    lines = ["# Audit of training-02 model selection", "",
        "Research proof of concept on Bangladesh source-qualified proxy labels; not validated for Fiji or operational warnings.", "",
        "## 1. Why the tuning winner was not selected", "",
        "The highest tuning AP was 0.430607 for balanced depth-6 hydrology CatBoost. Tuning AP selected hyperparameters only within each family/feature/weight group. "
        "The final selection rule was a different objective on a different time block: minimize 2023 H1 Brier, provided AP >=95% of original LR AP. "
        f"That floor was {gate:.6f}. Hydrology CatBoost's raw/sigmoid AP on selection was 0.121098, so it was ineligible despite leading 2022 H1 tuning. "
        "Baseline depth-4 CatBoost with sigmoid had selection AP 0.173391 and Brier 0.021454; it passed and narrowly beat eligible alternatives by Brier. "
        "The strongest original-feature candidate by tuning AP across families was balanced LightGBM (0.4209), not the selected CatBoost (0.4120). "
        "This is not a hidden switch of datasets, but it is an objective mismatch with prioritizing detection: tuning ranks AP; final selection prioritizes probability error, not recall under a false-alert budget.", ""]
    lines += markdown_table(eligibility, ["model_id", "pr_auc_average_precision", "brier", "AP_floor", "eligible"])
    lines += ["", "## 2. Were comparisons made on identical records?", "",
        "Yes for the training-02 cohort and validation roles: all 43 candidates have the same finite prediction matrix indexed by the same station/date/stage rows. "
        "Row-key hashes and counts are saved in split_identity.csv. Tuning is 2022 H1 (1,463 rows/80 positives), calibration 2022 H2 (1,461/95), "
        "model selection 2023 H1 (1,376/31), and threshold selection 2023 H2 (1,417/104), with three-day boundary embargoes. "
        "Preprocessing/classifiers fit original training only. Frozen calibrators fit the calibration block only. No holdout station enters development.", "",
        "However, **not all candidates had optimized thresholds in training-02**. The development comparison used .5 for everyone; only the chosen CatBoost and original LR "
        "received threshold optimization. Model choice happened before inspecting recall under a candidate-specific budget threshold. The study therefore did not identify "
        "the highest-recall feasible model among all alternatives. Also, calibration metrics on their fit block are in-sample, unlike selection/threshold metrics.", "",
        "The original training-01 selection used the full original validation period; these new roles are disjoint within training-02, not historically unseen data. "
        "Selection has only 31 positives and half-year monsoon prevalence differs sharply. A high AP in one block need not persist across seasons. "
        "Hydrology depth-6 train AP 0.7874 versus selection AP 0.1211 suggests overfitting and/or temporal distribution shift, but does not prove a causal explanation.", "",
        "## 3. Why temporal-test recall fell despite calibration improvement", "",
        "A better Brier score does not imply higher recall. Changing from logistic regression to CatBoost changed ranking; calibrating changed its score scale; "
        "a validation FP/TP constraint then chose a conservative operating point. Selected CatBoost TP fell 126→105 and FN rose 155→176, while FP fell 225→160. "
        "Recall fell 44.84%→37.37%, despite Brier improving .1419→.0392. Threshold .403711 on calibrated CatBoost cannot be compared numerically with .866584 on weighted logistic regression.", "",
        "For the same base model, a strictly monotonic sigmoid map preserves ranking and feasible threshold operating points. The saved raw/sigmoid predictions have identical AP; "
        "the audit compares independently validation-optimized raw/sigmoid policies and records any decision disagreements. Thus sigmoid alone is not evidence of a detection loss. "
        "Isotonic calibration can merge scores into ties and remove possible operating points. Comparing .5 before and after calibration confounds a changed decision rule with calibration quality.", "",
        "## 4. Why entirely unseen-station recall fell", "",
        "The original model caught 13/46 proxy positives; selected CatBoost caught 11/46. FN rose 33→35; FP fell only 46→44. "
        "The selected model's spatial AP also fell .2351→.1769, even though ROC-AUC improved .8604→.8753. ROC-AUC is not sufficient for early positive detection under rare floods. "
        "Threshold validation prevalence was 7.34%, versus 3.03% on unseen stations. Precision and FP/TP do not transfer automatically across prevalence/feature shifts: "
        "selected unseen-station FP/TP was 4.0, above both its validation budget 1.7857 and original spatial ratio 3.5385. "
        "No spatial-generalization criterion selected the original winner; six outer stations were correctly withheld. Per-station and lost/recovered-detection tables show the exact changes, "
        "but 46 correlated positive days cannot establish a general mechanism or a statistically reliable deployment gain.", "",
        "## 5. Did the threshold policy genuinely improve recall?", "",
        "It increased recall for selected CatBoost compared with that calibrated model at .5: on threshold validation .1250→.3654, and on temporal test .2740→.3737. "
        "But it did **not** improve over the original model under the same validation budget: original 42 TP/75 FP (recall .4038), selected 38 TP/54 FP (.3654). "
        "The constrained maximum was found for the chosen score vector; the constraint was not violated or a recall target forced. The weakness is selecting that score vector by Brier first. "
        "A ratio budget also permits different absolute false-alert counts and counts daily records rather than independent public-warning events.", "",
        "## Controlled extension and full comparisons", "",
        plan["test_caveat"], "",
        "Saved tuning winners are compared without refitting. Two additional CatBoost controls are trained only on original train rows, using the two existing configurations: "
        "baseline depth 6/L2 10 and hydrology depth 4/L2 5. This separates feature changes from the depth/regularization difference between winners. "
        "All three calibration methods use the same disjoint calibration block; each threshold is frozen using the same threshold block and FP/TP budget before any final records are read. "
        "No model is selected from the resulting final tables, and no prior artifact is overwritten.", ""]
    lines += markdown_table(threshold[threshold.model_id.isin([base + "__sigmoid" for base in SAVED_BASES])],
                            ["model_id", "policy", "precision", "recall", "false_alerts_per_detection", "false_alerts_per_1000"])
    lines += ["", "Retrospective evaluation, with candidate-specific validation-only budget thresholds:", ""]
    primary = final[(final.model_id.isin([base + "__sigmoid" for base in SAVED_BASES]) & final.policy.eq("same_budget")) | final.model_id.eq("original_logistic")]
    lines += markdown_table(primary, ["model_id", "stage", "precision", "recall", "f1", "pr_auc_average_precision", "brier"])
    lines += ["", "Files: evaluation.csv includes all calibrated/raw/isotonic controls and .5/budget policies; development_comparison.csv includes train/validation; "
        "matched_hydrology_effect.csv reports paired feature differences at fixed depth; per_station.csv and detection_transitions.csv show local effects. "
        "comparison_lock.json records model/data/threshold hashes before evaluation. sigmoid_operating_point_invariance.json checks equivalent score rankings.", "",
        "## Implications for training-03", "",
        "Do not promote a model merely for the lowest Brier or the highest AP on one seasonal slice. Keep the outer temporal/station split fixed, "
        "and add internal station-held-out validation within the development stations. Rank foundation-model candidates by feasible flood recall and station-macro recall, "
        "with the user-approved empirical false-alert budget; report AP/Brier as separate metrics. A new model must not be selected from the already viewed outer station holdout. "
        "Preserving splits cannot recreate a blind test: fresh prospective records and official Fiji MET validation remain necessary.", ""]
    (out / "model_selection_report.md").write_text("\n".join(lines))
    plot(out, final)


def plot(out, final):
    predictions = pd.read_parquet(out / "predictions.parquet")
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for axis, stage in zip(axes, ["test", "holdout_station"]):
        mask = predictions.stage.eq(stage)
        for base in SAVED_BASES:
            precision, recall, _ = precision_recall_curve(predictions.loc[mask, TARGET], predictions.loc[mask, base + "__sigmoid"])
            axis.plot(recall, precision, label=base.replace("__balanced", ""))
        axis.set(title=stage + " (retrospective diagnostic)", xlabel="Recall", ylabel="Precision")
        axis.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(out / "frozen_candidate_pr.png", dpi=160); plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare", "evaluate", "report", "all"])
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    for stage in (["prepare", "evaluate"] if args.stage == "all" else [args.stage]):
        if stage == "prepare": prepare(args.source, args.out)
        elif stage == "evaluate": evaluate(args.out)
        else: render(args.out)


if __name__ == "__main__": main()
