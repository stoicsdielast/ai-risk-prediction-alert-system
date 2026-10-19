"""Execute Training-03 with fresh station-fold fits and frozen diagnostic policies."""
import argparse
import ast
import json
from pathlib import Path
import time

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve

from ml.config import TARGET
from ml.refinement import FEATURE_SETS, recall_budget_threshold, reliability, score, sha256, threshold_table
from ml.train import write_json
from ml.training02 import read
from ml.training03 import (apply_sigmoid, context_sample, fit_sigmoid, preflight, run_worker,
                           station_macro_recall, verify)

CODE = ["ml/benchmark03.py", "ml/foundation_worker.py", "ml/training03.py"]


def code_hashes():
    return {p: sha256(Path(p)) for p in CODE}


def data_for(out):
    data = pd.read_parquet(out / "development.parquet").reset_index(drop=True)
    data["row_id"] = np.arange(len(data))
    return data


def model_asset(variant, assets):
    if variant["model"] == "classical":
        return {"python": "backend/.venv/bin/python", "spec": variant["spec"]}
    return assets[variant["model"]]


def limits_for(plan, variant):
    limits = dict(plan["resource_limits"])
    limits["device"] = variant.get("device", limits["device"])
    if variant["model"] == "classical": limits["device"] = "cpu"
    return limits


def configure(out, assets_path, device):
    base = verify(out)
    if (out / "execution_plan.json").exists(): raise ValueError("Execution protocol already exists")
    variants = list(base["variants"])
    smokes = read(out / "smoke_results.json")
    for variant in variants:
        variant["device"] = smokes.get(f"smoke__{variant['model']}__{variant['context_cap']}", {}).get("device", device)
    old = read(Path(base["source"]) / "candidate_models.json")
    for family in ["logistic", "catboost", "lightgbm"]:
        for feature_set in FEATURE_SETS:
            spec = old[f"{family}__{feature_set}__balanced__none"]
            for cap in [100, 12049]:
                variants.append({"id": f"{family}__{feature_set}__{cap}", "model": "classical", "family": family,
                    "feature_set": feature_set, "context_cap": cap, "arm": "matched_100" if cap == 100 else "full_training",
                    "spec": {k: spec[k] for k in ["family", "balanced", "parameters"]}})
    plan = {"prepared_plan_sha256": sha256(out / "plan.json"), "assets_sha256": sha256(assets_path),
        "variants": variants, "inner_station_folds": base["inner_station_folds"],
        "false_alert_budget": base["false_alert_budget"],
        "resource_limits": {**base["resource_limits"], "device": device, "validation_total_seconds": 7200},
        "changes_before_any_validation_scores": ["Hardware-confirmed GPU execution where available; CPU for classical models",
            "Two-hour validation envelope for 22 recipes including classical controls; unchanged 600-second per-job cap",
            "TabFM GPU uses official bfloat16 compute to accommodate 6.56 GB float32 checkpoint; CPU fallback uses float32",
            "Classical parameters frozen from training-02; refit excluding each inner query fold; matched-100 and full-training arms",
            "Family winners and overall winner chosen on H1 only; all their thresholds frozen on H2 before diagnostic labels read",
            "A family with no feasible H1 candidate gets an AP-ranked diagnostic representative only; it cannot win the benchmark",
            "Infeasible H2 policy gets an explicit no-alert diagnostic threshold, never a replacement winner"],
        "selection": base["selection_rule"], "calibration": ["none", "sigmoid"],
        "independence": "Fresh station-excluded model fits; existing development labels have historical use. No new independently untouched final set exists.",
        "diagnostic": "Per-family H1 winners plus old fixed references, scored on identical old outer records; no selection from diagnostics"}
    write_json(out / "execution_plan.json", plan)


def verify_execution(out, assets_path):
    verify(out)
    plan = read(out / "execution_plan.json")
    if plan["prepared_plan_sha256"] != sha256(out / "plan.json"): raise ValueError("Prepared plan changed")
    if plan["assets_sha256"] != sha256(assets_path): raise ValueError("Model assets changed")
    return plan


def smoke(out, assets_path, device):
    verify(out)
    check = preflight(out, assets_path)
    data, assets = data_for(out), read(assets_path)
    results = {}
    for name, status in check["models"].items():
        if status["status"] != "ready":
            results[name] = {"status": "skipped", "reason": status["problems"]}; continue
        for cap in sorted({100, read(out / "plan.json")["sources"][name]["context_cap"]}):
            key = f"smoke__{name}__{cap}"
            variant = {"model": name, "feature_set": "hydrology", "context_cap": cap}
            context = context_sample(data, FEATURE_SETS["hydrology"], cap)
            query = data[data.stage.eq("tuning")].head(16)
            try:
                p = run_worker(out, key, context, query, variant, assets[name],
                    {"device": device, "memory_gb": 16, "timeout_seconds": 600, "query_batch_rows": 64})
                results[key] = {"status": "passed", "device": device, "context_rows": len(context), "query_rows": len(p),
                                "probabilities_finite": bool(np.isfinite(p).all()), "scores": None}
            except (RuntimeError, ValueError, TimeoutError, OSError) as error:
                results[key] = {"status": "failed", "reason": str(error)}
                if device == "cuda":
                    print(key, "GPU smoke failed; trying CPU", flush=True)
                    try:
                        p = run_worker(out, key + "__cpu_fallback", context, query, variant, assets[name],
                            {"device": "cpu", "memory_gb": 16, "timeout_seconds": 600, "query_batch_rows": 64})
                        results[key] = {"status": "passed", "device": "cpu", "gpu_failure": str(error),
                            "context_rows": len(context), "query_rows": len(p), "probabilities_finite": bool(np.isfinite(p).all()), "scores": None}
                    except (RuntimeError, ValueError, TimeoutError, OSError) as cpu_error:
                        results[key]["cpu_failure"] = str(cpu_error)
            write_json(out / "smoke_results.json", results)
            print(key, results[key], flush=True)
    write_json(out / "smoke_results.json", results)
    classical_smoke(out)


def classical_smoke(out):
    data = data_for(out)
    old = read(Path(read(out / "plan.json")["source"]) / "candidate_models.json")
    results = {}
    for family in ["logistic", "catboost", "lightgbm"]:
        spec = old[f"{family}__baseline__balanced__none"]
        variant = {"model": "classical", "feature_set": "baseline", "spec": {k: spec[k] for k in ["family", "balanced", "parameters"]}}
        context = context_sample(data, FEATURE_SETS["baseline"], 100)
        query = data[data.stage.eq("tuning")].head(16)
        p = run_worker(out, "smoke__" + family, context, query, variant, model_asset(variant, {}),
                       {"device": "cpu", "memory_gb": 16, "timeout_seconds": 600, "query_batch_rows": 64})
        results[family] = {"status": "passed", "query_rows": len(p), "scores": None}
    write_json(out / "classical_smoke_results.json", results)


def feasible_policy(data, p, budget):
    try:
        return recall_budget_threshold(threshold_table(data[TARGET], p), budget), True
    except ValueError:
        return {"threshold": float(np.nextafter(1., 2.)), "recall": 0., "tp": 0, "fp": 0}, False


def select_choices(table):
    ranked = table[table.feasible].sort_values(
        ["station_macro_recall", "recall", "pr_auc_average_precision", "brier", "candidate"],
        ascending=[False, False, False, True, True])
    families, ineligible = {}, []
    for family, group in table.groupby("family", sort=True):
        eligible = ranked[ranked.family.eq(family)]
        if len(eligible): families[family] = eligible.iloc[0].candidate
        else:
            representative = group.sort_values(["pr_auc_average_precision", "brier", "candidate"], ascending=[False, True, True]).iloc[0].candidate
            families[family] = representative; ineligible.append(representative)
    return {"overall": None if ranked.empty else ranked.iloc[0].candidate,
            "families": families, "diagnostic_only_ineligible_on_H1": ineligible}


def validate(out, assets_path):
    plan = verify_execution(out, assets_path)
    if (out / "benchmark_validation_lock.json").exists(): raise ValueError("Benchmark validation is locked")
    if (out / "validation_choices.json").exists(): raise ValueError("Choices already frozen; do not rerun selection")
    check, assets, data = preflight(out, assets_path), read(assets_path), data_for(out)
    smoke_results = read(out / "smoke_results.json")
    started = time.monotonic(); rows, policies, statuses = [], {}, {}
    for variant in plan["variants"]:
        name, model = variant["id"], variant["model"]
        if model != "classical" and (check["models"][model]["status"] != "ready" or
            smoke_results.get(f"smoke__{model}__{variant['context_cap']}", {}).get("status") != "passed"):
            statuses[name] = "skipped: unavailable or failed smoke"; continue
        print("Validation", name, flush=True)
        pieces = []
        try:
            for fold, stations in plan["inner_station_folds"].items():
                if time.monotonic()-started > plan["resource_limits"]["validation_total_seconds"]:
                    raise TimeoutError("Validation envelope exhausted")
                context = context_sample(data, FEATURE_SETS[variant["feature_set"]], variant["context_cap"], stations)
                held = data.station_id.isin(stations)
                query = data[(~held & data.stage.eq("calibration")) | (held & data.stage.isin(["selection", "threshold"]))]
                job_id = "benchmark__" + name + "__fold" + fold
                raw = run_worker(out, job_id, context, query, variant, model_asset(variant, assets), limits_for(plan, variant))
                calibration = query[query.stage.eq("calibration")]
                sigmoid = fit_sigmoid(raw.loc[calibration.row_id], calibration[TARGET])
                joblib.dump(sigmoid, out / "jobs" / job_id / "sigmoid.joblib")
                part = query[query.stage.isin(["selection", "threshold"])][["row_id", "station_id", "date", "stage", TARGET]].copy()
                part["none"] = raw.loc[part.row_id].to_numpy(); part["sigmoid"] = apply_sigmoid(sigmoid, part["none"])
                part["fold"] = fold; pieces.append(part)
            joined = pd.concat(pieces, ignore_index=True).sort_values("row_id")
            expected = data[data.stage.isin(["selection", "threshold"])].row_id.tolist()
            if joined.row_id.tolist() != expected: raise ValueError("Incomplete or duplicate station-fold query coverage")
            joined.to_parquet(out / (name + "__oof.parquet"), index=False)
            selection = joined[joined.stage.eq("selection")]
            for method in ["none", "sigmoid"]:
                policy, feasible = feasible_policy(selection, selection[method], plan["false_alert_budget"])
                macro, n = station_macro_recall(selection, selection[method], policy["threshold"])
                candidate = name + "__" + method
                rows.append({"candidate": candidate, "family": variant.get("family", model), "arm": variant["arm"],
                    "feasible": feasible, "station_macro_recall": macro, "positive_label_stations": n,
                    **score(selection[TARGET], selection[method], policy["threshold"])})
                policies[candidate] = {"variant": variant, "calibration": method, "selection_threshold": policy["threshold"]}
            statuses[name] = "completed"
        except (RuntimeError, ValueError, TimeoutError, OSError) as error:
            statuses[name] = f"failed: {error}"
        write_json(out / "benchmark_validation_status.json", statuses)
        pd.DataFrame(rows).to_csv(out / "benchmark_validation.csv", index=False)
    if not rows: raise ValueError("No model completed internal validation")
    choices = select_choices(pd.DataFrame(rows))
    # This file is committed before H2 labels are scored for any chosen policy.
    write_json(out / "validation_choices.json", {**choices, "chosen_from": "internal-held-station 2023 H1 only"})
    frozen = {}
    for candidate in sorted(set(choices["families"].values())):
        policy = policies[candidate]
        joined = pd.read_parquet(out / (policy["variant"]["id"] + "__oof.parquet"))
        threshold = joined[joined.stage.eq("threshold")]
        chosen, feasible = feasible_policy(threshold, threshold[policy["calibration"]], plan["false_alert_budget"])
        frozen[candidate] = {**policy, "threshold": chosen["threshold"], "threshold_feasible": feasible,
            "threshold_validation": score(threshold[TARGET], threshold[policy["calibration"]], chosen["threshold"])}
    write_json(out / "benchmark_validation_lock.json", {"choices": choices, "policies": frozen,
        "code_sha256": code_hashes(), "execution_plan_sha256": sha256(out / "execution_plan.json"),
        "assets_sha256": sha256(assets_path), "seconds": time.monotonic()-started})
    print("Frozen selection:", choices, flush=True)


def checked_lock(out, assets_path):
    plan = verify_execution(out, assets_path); lock = read(out / "benchmark_validation_lock.json")
    if lock["code_sha256"] != code_hashes(): raise ValueError("Benchmark code changed after selection")
    if lock["execution_plan_sha256"] != sha256(out / "execution_plan.json"): raise ValueError("Execution protocol changed")
    if lock["assets_sha256"] != sha256(assets_path): raise ValueError("Assets changed")
    return plan, lock


def diagnose(out, assets_path):
    plan, lock = checked_lock(out, assets_path)
    if (out / "diagnostic_metrics.csv").exists(): raise ValueError("Diagnostics already completed")
    data, assets = data_for(out), read(assets_path)
    frozen = {}
    # Calibrators and context are frozen for every family before any outer read.
    for candidate, policy in lock["policies"].items():
        variant = policy["variant"]
        context = context_sample(data, FEATURE_SETS[variant["feature_set"]], variant["context_cap"])
        query = data[data.stage.eq("calibration")]
        job = "calibrate__" + candidate
        try:
            raw = run_worker(out, job, context, query, variant, model_asset(variant, assets), limits_for(plan, variant))
            calibrator = fit_sigmoid(raw.loc[query.row_id], query[TARGET]) if policy["calibration"] == "sigmoid" else None
            path = out / (candidate + "__calibrator.joblib"); joblib.dump(calibrator, path)
            context_path = out / (candidate + "__context.parquet"); context.to_parquet(context_path, index=False)
            frozen[candidate] = {**policy, "context_sha256": sha256(context_path), "calibrator_sha256": sha256(path)}
        except (RuntimeError, ValueError, TimeoutError, OSError) as error:
            write_json(out / (candidate + "__final_failure.json"), {"error": str(error)})
    write_json(out / "diagnostic_lock.json", {"policies": frozen, "holdout_sha256": read(out / "plan.json")["holdout_sha256"]})
    source = Path(read(out / "plan.json")["source"])
    if sha256(source / "evaluation_holdout.parquet") != read(out / "diagnostic_lock.json")["holdout_sha256"]:
        raise ValueError("Outer records changed")
    outer = pd.read_parquet(source / "evaluation_holdout.parquet").reset_index(drop=True)
    outer["row_id"] = np.arange(len(outer))
    probabilities = outer[["row_id", "station_id", "date", "stage", TARGET]].copy()
    rows, station_rows, failures = [], [], {}
    for candidate, policy in frozen.items():
        print("Diagnostic", candidate, flush=True)
        variant = policy["variant"]
        try:
            context = pd.read_parquet(out / (candidate + "__context.parquet"))
            raw = run_worker(out, "diagnose__" + candidate, context, outer, variant, model_asset(variant, assets), limits_for(plan, variant))
            calibrator = joblib.load(out / (candidate + "__calibrator.joblib"))
            p = apply_sigmoid(calibrator, raw.loc[outer.row_id]) if calibrator else raw.loc[outer.row_id].to_numpy()
            probabilities[candidate] = p
            collect_metrics(outer, p, policy["threshold"], candidate, rows, station_rows)
        except (RuntimeError, ValueError, TimeoutError, OSError) as error: failures[candidate] = str(error)
    # Fixed historical references use their original immutable predictions and thresholds.
    audit = Path("ml/runs/training-02-selection-audit")
    old = pd.read_parquet(audit / "predictions.parquet")
    keys = ["station_id", "date", "stage", TARGET]
    if old[keys].duplicated().any() or outer[keys].duplicated().any(): raise ValueError("Ambiguous diagnostic keys")
    old = outer[keys].merge(old, on=keys, how="left", validate="one_to_one", sort=False)
    original = pd.read_parquet(source / "all_predictions.parquet")
    original = outer[keys].merge(original[keys + ["original_baseline_probability"]], on=keys, how="left", validate="one_to_one", sort=False)
    comparison = pd.read_csv(audit / "evaluation.csv")
    for candidate in ["original_logistic", "catboost__baseline__balanced__sigmoid", "catboost__hydrology__balanced__sigmoid", "lightgbm__baseline__balanced__sigmoid"]:
        p = original.original_baseline_probability.to_numpy() if candidate == "original_logistic" else old[candidate].to_numpy()
        if not np.isfinite(p).all(): raise ValueError("Reference records differ")
        policy_name = "original" if candidate == "original_logistic" else "same_budget"
        threshold = float(comparison[(comparison.model_id == candidate) & comparison.policy.eq(policy_name)].iloc[0].threshold)
        label = "historical__" + candidate
        probabilities[label] = p
        collect_metrics(outer, p, threshold, label, rows, station_rows)
    probabilities.to_parquet(out / "diagnostic_predictions.parquet", index=False)
    pd.DataFrame(rows).to_csv(out / "diagnostic_metrics.csv", index=False)
    pd.DataFrame(station_rows).to_csv(out / "diagnostic_per_station.csv", index=False)
    write_json(out / "diagnostic_failures.json", failures)
    write_json(out / "status.json", {"status": "benchmarked_diagnostic_only", "independent_final_validation_required": True,
        "validation_choice": lock["choices"], "active_model_changed": False})
    verify(out)


def collect_metrics(data, p, threshold, candidate, rows, station_rows):
    for stage in sorted(data.stage.unique()):
        mask = data.stage.eq(stage).to_numpy()
        macro, n = station_macro_recall(data.loc[mask], np.asarray(p)[mask], threshold)
        rows.append({"candidate": candidate, "stage": stage, "station_macro_recall": macro,
                     "positive_label_stations": n, **score(data.loc[mask, TARGET], np.asarray(p)[mask], threshold)})
        for station in sorted(data.loc[mask, "station_id"].unique()):
            m = mask & data.station_id.eq(station).to_numpy()
            station_rows.append({"candidate": candidate, "stage": stage, "station_id": station,
                                 **score(data.loc[m, TARGET], np.asarray(p)[m], threshold)})


def report(out, assets_path):
    plan, lock = checked_lock(out, assets_path)
    diagnostics = pd.read_parquet(out / "diagnostic_predictions.parquet")
    calibration_rows = []
    for stage in sorted(diagnostics.stage.unique()):
        d = diagnostics[diagnostics.stage.eq(stage)]
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        for candidate in diagnostics.columns[5:]:
            precision, recall, _ = precision_recall_curve(d[TARGET], d[candidate])
            axes[0].plot(recall, precision, label=candidate)
            rel = reliability(d[TARGET], d[candidate])
            axes[1].plot([x["mean_probability"] for x in rel], [x["positive_fraction"] for x in rel], marker=".")
            calibration_rows.extend({"candidate": candidate, "stage": stage, **r} for r in rel)
        axes[0].axhline(d[TARGET].mean(), color="gray", linestyle=":")
        axes[0].set(xlabel="Recall", ylabel="Precision", title=stage + " (diagnostic)")
        axes[1].plot([0, 1], [0, 1], "k--"); axes[1].set(xlabel="Mean predicted probability", ylabel="Observed incidence", title="Calibration")
        axes[0].legend(fontsize=5); fig.tight_layout(); fig.savefig(out / (stage + "__pr_calibration.png"), dpi=170); plt.close(fig)
    pd.DataFrame(calibration_rows).to_csv(out / "calibration_bins.csv", index=False)
    internal_rows, internal_stations = [], []
    for candidate, policy in lock["policies"].items():
        d = pd.read_parquet(out / (policy["variant"]["id"] + "__oof.parquet"))
        collect_metrics(d, d[policy["calibration"]], policy["threshold"], candidate, internal_rows, internal_stations)
    pd.DataFrame(internal_rows).to_csv(out / "internal_metrics_at_frozen_threshold.csv", index=False)
    pd.DataFrame(internal_stations).to_csv(out / "internal_per_station.csv", index=False)
    for stage in ["selection", "threshold"]:
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        for candidate, policy in lock["policies"].items():
            d = pd.read_parquet(out / (policy["variant"]["id"] + "__oof.parquet"))
            d = d[d.stage.eq(stage)]; p = d[policy["calibration"]]
            precision, recall, _ = precision_recall_curve(d[TARGET], p)
            axes[0].plot(recall, precision, label=candidate)
            rel = reliability(d[TARGET], p)
            axes[1].plot([x["mean_probability"] for x in rel], [x["positive_fraction"] for x in rel], marker=".")
        axes[0].set(xlabel="Recall", ylabel="Precision", title="Inner held stations: " + stage)
        axes[1].plot([0, 1], [0, 1], "k--"); axes[1].set(xlabel="Mean predicted probability", ylabel="Observed incidence", title="Calibration")
        axes[0].legend(fontsize=6); fig.tight_layout(); fig.savefig(out / (stage + "__pr_calibration.png"), dpi=170); plt.close(fig)
    usage = []
    for path in sorted((out / "jobs").glob("*/execution.json")):
        row = {"job": path.parent.name, **read(path)}
        details = path.parent / "probabilities.parquet.usage.json"
        if details.exists(): row.update(read(details))
        usage.append(row)
    pd.DataFrame(usage).to_csv(out / "execution_times_hardware.csv", index=False)
    # Avoid tabulate as an extra backend dependency.
    def markdown(frame):
        return "| " + " | ".join(frame.columns) + " |\n|" + "|".join(["---"]*len(frame.columns)) + "|\n" + "\n".join("| " + " | ".join(f"{v:.6f}" if isinstance(v, float) else str(v) for v in row) + " |" for row in frame.itertuples(index=False, name=None))
    metrics = pd.read_csv(out / "diagnostic_metrics.csv")
    for stage, group in metrics.groupby("stage"):
        fig, axes = plt.subplots(2, (len(group)+1)//2, figsize=(16, 7), squeeze=False)
        for ax, row in zip(axes.flat, group.itertuples()):
            tn, fp, fn, tp = ast.literal_eval(row.confusion_matrix_tn_fp_fn_tp)
            matrix = np.array([[tn, fp], [fn, tp]])
            ax.imshow(matrix, cmap="Blues")
            for i in range(2):
                for j in range(2): ax.text(j, i, str(matrix[i, j]), ha="center", va="center", color="red")
            ax.set(xticks=[0, 1], yticks=[0, 1], xlabel="Predicted", ylabel="Observed", title=row.candidate.replace("__", "\n"))
            ax.title.set_fontsize(6)
        for ax in list(axes.flat)[len(group):]: ax.axis("off")
        fig.tight_layout(); fig.savefig(out / (stage + "__confusion_matrices.png"), dpi=170); plt.close(fig)
    columns = ["candidate", "stage", "precision", "recall", "f1", "pr_auc_average_precision", "brier", "confusion_matrix_tn_fp_fn_tp"]
    validation = pd.read_csv(out / "benchmark_validation.csv")
    text = "# Training-03 executed benchmark\n\n" + json.dumps(lock["choices"], indent=2) + "\n\n"
    text += "Selection used fresh station-excluded fits on the prepared internal folds, H1 labels only, and the approved FP/TP budget. H2 fixed thresholds afterwards. Outer results below are retrospective diagnostics; independent final validation is still required.\n\n"
    text += "## Internal station validation\n\n" + markdown(validation[["candidate", "feasible", "station_macro_recall", "recall", "precision", "f1", "pr_auc_average_precision", "brier"]])
    text += "\n\n## Identical-record outer diagnostics\n\n" + markdown(metrics[columns])
    text += "\n\n## Scope and reproducibility\n\nMatched-100 arms share exactly the same label-independent context rows within each fold. Full classical and capped foundation arms have unequal training exposure; their context sizes are explicit. Classical parameters were frozen from training-02, not retuned on outer records. All models use the same 30/38-feature schemas and binary target. Sigmoid calibration uses other stations in the disjoint 2022 H2 block. No fit sees its held-out query station.\n\n"
    text += "TabPFN-2.5 requires authenticated checkpoint access and was skipped. See installation/status.json and smoke_results.json for exact availability, installation and runtime issues. Every successful job records code/data/checkpoint provenance, elapsed time, CPU RAM and GPU allocation. No FastAPI/React deployment or notification activation occurred.\n\n"
    text += "Commands: `python -m ml.setup_training03`; `python -m ml.benchmark03 smoke --device cuda`; `python -m ml.benchmark03 configure --device cuda`; `python -m ml.benchmark03 validate`; `python -m ml.benchmark03 diagnose`; `python -m ml.benchmark03 report`. Use backend/.venv/bin/python as the orchestration interpreter; isolated model interpreters are selected by the asset manifest. Existing jobs are never overwritten. See docs/TRAINING_03.md for fresh-run preparation.\n"
    (out / "benchmark_report.md").write_text(text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["configure", "smoke", "validate", "diagnose", "report"])
    parser.add_argument("--out", type=Path, default=Path("ml/runs/training-03"))
    parser.add_argument("--assets", type=Path, default=Path("ml/foundation/assets.json"))
    parser.add_argument("--device", default="cuda", choices=["cpu", "cuda"])
    args = parser.parse_args()
    if args.stage in ["smoke", "configure"]: globals()[args.stage](args.out, args.assets, args.device)
    else: globals()[args.stage](args.out, args.assets)
