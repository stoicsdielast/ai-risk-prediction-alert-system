"""Prepared spatial-detection benchmark for pinned TabFM/TabPFN/TabICLv2."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from ml.config import HOLDOUT_STATIONS, TARGET
from ml.foundation_worker import asset_digest
from ml.refinement import FEATURE_SETS, directory_hashes, recall_budget_threshold, score, sha256, threshold_table
from ml.train import write_json
from ml.training02 import load_development, protect_paths, read

SOURCES = Path(__file__).parent / "foundation/sources.json"
DEFAULT_OUT = Path("ml/runs/training-03")


def context_sample(data, features, cap, excluded_stations=()):
    context = data.loc[data.stage.eq("train") & ~data.station_id.isin(excluded_stations)].copy()
    # Natural training prevalence; identical keys for the two feature schemas.
    context = context.sort_values("selection_hash").head(cap)
    if context.station_id.isin(HOLDOUT_STATIONS).any() or context.date.ge("2022-01-01").any():
        raise ValueError("Invalid training context")
    return context


def inner_folds(data):
    stations = sorted(data.loc[data.stage.eq("train"), "station_id"].unique())
    if set(stations) & set(HOLDOUT_STATIONS): raise ValueError("Outer holdout entered inner folds")
    return {str(i): stations[i::4] for i in range(4)}


def verify(out):
    plan = read(out / "plan.json")
    for directory, hashes in plan["preserved_directories"].items():
        if directory_hashes(directory) != hashes: raise ValueError("A preserved run/audit changed")
    if sha256(out / "development.parquet") != plan["development_sha256"]: raise ValueError("Development rows changed")
    return plan


def prepare(out, source, audit):
    protect_paths(out, source)
    baseline = Path(read(source / "plan.json")["baseline_directory"])
    protect_paths(out, baseline); protect_paths(out, audit)
    if out.exists(): raise ValueError("training-03 output exists; prepare never overwrites a run")
    if not (audit / "model_selection_report.md").exists(): raise ValueError("Complete the training-02 selection audit first")
    from ml.audit02_selection import verify_source
    verify_source(audit)
    data, parts = load_development(source)
    sources = read(SOURCES)
    variants = []
    for name, facts in sources.items():
        for features in FEATURE_SETS:
            for cap in sorted({100, facts["context_cap"]}):
                variants.append({"id": f"{name}__{features}__{cap}", "model": name, "feature_set": features,
                                 "context_cap": cap, "arm": "matched_100" if cap == 100 else "resource_capped", "n_estimators": 4})
    out.mkdir(parents=True)
    shutil.copy2(source / "development.parquet", out / "development.parquet")
    plan = {"study": "training-03", "status": "prepared_not_benchmarked", "source": str(source.resolve()),
        "preserved_directories": {str(p.resolve()): directory_hashes(p) for p in [baseline, source, audit]},
        "development_sha256": sha256(out / "development.parquet"), "holdout_sha256": sha256(source / "evaluation_holdout.parquet"),
        "sources": sources, "variants": variants, "features": FEATURE_SETS, "inner_station_folds": inner_folds(data),
        "false_alert_budget": read(source / "thresholds.json")["false_alerts_per_detection_budget"],
        "outer_split": "Unchanged training-02 keys, dates, embargoes and six entire outer holdout stations",
        "inner_protocol": "Four fixed folds within the 24 development stations. Context excludes the query fold. Calibration uses other development stations in 2022 H2. Selection and threshold queries are 2023 H1/H2 at inner-held stations.",
        "selection_rule": "Maximize station-macro recall (positive-label stations only) at the maximum pooled-recall point satisfying the approved FP/TP budget on inner-held 2023 H1; ties pooled recall, AP, lower Brier",
        "threshold_rule": "After candidate selection, maximize pooled recall under the same budget on its inner-held 2023 H2 predictions. Freeze before outer evaluation.",
        "calibration": "none and sigmoid, using only disjoint 2022 H2 calibration predictions; no default internal model calibration/search",
        "context_policy": "Target-independent lowest original selection_hash training keys, no balancing or resampling, identical context keys within cap/fold across feature sets",
        "resource_limits": {"device": "cpu", "memory_gb": 16, "timeout_seconds": 600, "validation_total_seconds": 3600, "query_batch_rows": 64},
        "test_caveat": "Outer temporal and station outcomes have already been examined; unchanged split is a retrospective benchmark, not a fresh blind test. No outer label selects candidates or thresholds.",
        "limitations": ["31 positives in H1 model selection; station-macro recall excludes stations without positives and must report its denominator",
                        "Pretraining contamination cannot be ruled out from model cards alone", "Context-capped foundation models see fewer training rows than full-data classical references",
                        "Inner-fold probability calibration may not transfer exactly to the final context/calibrator", "Source labels and reanalysis availability remain research proxies"]}
    write_json(out / "plan.json", plan)
    write_json(out / "assets.example.json", read(Path(__file__).parent / "foundation/assets.example.json"))
    rows = []
    for fold, stations in plan["inner_station_folds"].items():
        for stage in ["selection", "threshold"]:
            d = data[data.stage.eq(stage) & data.station_id.isin(stations)]
            rows.append(dict(fold=fold, stage=stage, rows=len(d), positives=int(d[TARGET].sum()), stations=",".join(stations)))
    pd.DataFrame(rows).to_csv(out / "inner_fold_summary.csv", index=False)
    write_json(out / "status.json", {"status": "prepared_not_benchmarked", "scores": None,
        "reason": "Isolated model environments and licensed local checkpoint digests are not configured; no weights downloaded or model performance claimed"})
    print("training-03 prepared with unchanged outer splits and four inner station folds.")


def preflight(out, assets_path):
    plan = verify(out)
    assets = read(assets_path)
    statuses = {}
    for name, facts in plan["sources"].items():
        asset = assets.get(name, {})
        problems = []
        python = Path(asset.get("python", facts["python"]))
        if not python.is_file(): problems.append("isolated Python environment missing")
        path = Path(asset.get("path") or "/nonexistent/is314-checkpoint")
        if not path.exists(): problems.append("local pretrained checkpoint missing")
        elif not asset.get("sha256") or asset_digest(path) != asset["sha256"]: problems.append("checkpoint digest missing or mismatched")
        environment = None
        if python.is_file():
            script = "import json,importlib.metadata as m; d=m.distribution('" + name + "'); print(json.dumps({'version':d.version,'direct_url':json.loads(d.read_text('direct_url.json') or '{}'),'torch':m.version('torch')}))"
            probe = subprocess.run([str(python.absolute()), "-c", script], capture_output=True, text=True, timeout=30)
            if probe.returncode: problems.append("model/torch package missing or metadata probe failed")
            else:
                environment = json.loads(probe.stdout)
                if environment["direct_url"].get("vcs_info", {}).get("commit_id") != facts["commit"]:
                    problems.append("installed source is not the pinned official commit")
        statuses[name] = {"status": "ready" if not problems else "unavailable", "problems": problems,
                          "environment": environment, "source_commit": facts["commit"], "weight_license": facts["weight_license"]}
    result = {"models": statuses, "assets_sha256": sha256(assets_path), "scores": None,
              "hardware": "See hardware.json and installation/*_torch_probe.txt for measured device availability; execution_plan.json records the selected device"}
    write_json(out / "preflight.json", result)
    print(json.dumps(result, indent=2))
    return result


def run_worker(out, job_id, context, query, variant, asset, limits):
    job = out / "jobs" / job_id; job.mkdir(parents=True, exist_ok=False)
    features = FEATURE_SETS[variant["feature_set"]]
    context[features].assign(label=context[TARGET].astype(int).to_numpy()).to_parquet(job / "context.parquet", index=False)
    query[features + ["row_id"]].to_parquet(job / "query.parquet", index=False)
    request = {"model": variant["model"], "asset": asset, "features": features, "device": limits["device"],
               "context": str((job / "context.parquet").resolve()), "query": str((job / "query.parquet").resolve()),
               "output": str((job / "probabilities.parquet").resolve()), **limits}
    write_json(job / "request.json", request)
    write_json(job / "context_keys.json", context[["date", "station_id"]].assign(date=context.date.dt.strftime("%Y-%m-%d")).to_dict("records"))
    environment = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "TABPFN_NO_BROWSER": "1",
                   "OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2"}
    started = time.monotonic(); peak_rss = 0; failure = None
    with (job / "worker.log").open("w") as log:
        process = subprocess.Popen([str(Path(asset["python"]).absolute()), "-m", "ml.foundation_worker", str((job / "request.json").resolve())],
                                   stdout=log, stderr=subprocess.STDOUT, text=True, env=environment, start_new_session=True)
        while process.poll() is None:
            try:
                status = Path(f"/proc/{process.pid}/status").read_text()
                rss = next((int(line.split()[1]) * 1024 for line in status.splitlines() if line.startswith("VmRSS:")), 0)
                peak_rss = max(peak_rss, rss)
            except (FileNotFoundError, ProcessLookupError): pass
            if time.monotonic()-started > limits["timeout_seconds"]: failure = "wall-time budget exceeded"
            elif peak_rss > limits["memory_gb"] * 1024**3: failure = "resident-memory budget exceeded"
            if failure:
                os.killpg(process.pid, signal.SIGKILL); process.wait(); break
            time.sleep(.2)
    write_json(job / "execution.json", {"seconds": time.monotonic()-started, "peak_parent_observed_rss_mib": peak_rss/1024**2,
               "returncode": process.returncode, "failure": failure})
    if failure: raise TimeoutError(failure)
    if process.returncode: raise RuntimeError(f"Worker failed with code {process.returncode}; see {job}/worker.log")
    predictions = pd.read_parquet(job / "probabilities.parquet")
    if predictions.row_id.tolist() != query.row_id.tolist(): raise ValueError("Worker query order/schema mismatch")
    return predictions.set_index("row_id").probability


def fit_sigmoid(probability, labels):
    p = np.clip(np.asarray(probability), 1e-6, 1-1e-6)
    x = np.log(p/(1-p)).reshape(-1, 1)
    return LogisticRegression(C=1e6, random_state=314, max_iter=1000).fit(x, np.asarray(labels, dtype=int))


def apply_sigmoid(model, probability):
    p = np.clip(np.asarray(probability), 1e-6, 1-1e-6)
    return model.predict_proba(np.log(p/(1-p)).reshape(-1, 1))[:, 1]


def station_macro_recall(data, probability, threshold):
    rows = []
    for station in sorted(data.station_id.unique()):
        mask = data.station_id.eq(station).to_numpy()
        if data.loc[mask, TARGET].sum() > 0:
            rows.append(score(data.loc[mask, TARGET], np.asarray(probability)[mask], threshold)["recall"])
    return float(np.mean(rows)) if rows else None, len(rows)


def validate(out, assets_path):
    if (out / "validation_lock.json").exists(): raise ValueError("Validation is already locked")
    plan = verify(out); check = preflight(out, assets_path); assets = read(assets_path)
    if not any(r["status"] == "ready" for r in check["models"].values()):
        raise ValueError("All foundation models unavailable; configure isolated environments and local checkpoint digests before validation")
    data = pd.read_parquet(out / "development.parquet").reset_index(drop=True)
    data["row_id"] = np.arange(len(data))
    started = time.monotonic(); rows, policies, statuses = [], {}, {}
    for variant in plan["variants"]:
        name = variant["id"]
        if check["models"][variant["model"]]["status"] != "ready":
            statuses[name] = "unavailable: preflight"; continue
        pieces = []
        try:
            for fold, stations in plan["inner_station_folds"].items():
                if time.monotonic() - started >= plan["resource_limits"]["validation_total_seconds"]:
                    raise TimeoutError("Total validation time budget exhausted")
                context = context_sample(data, FEATURE_SETS[variant["feature_set"]], variant["context_cap"], stations)
                held = data.station_id.isin(stations)
                mask = (~held & data.stage.eq("calibration")) | (held & data.stage.isin(["selection", "threshold"]))
                query = data.loc[mask].copy()
                limits = {**plan["resource_limits"], "timeout_seconds": min(plan["resource_limits"]["timeout_seconds"],
                    max(1, int(plan["resource_limits"]["validation_total_seconds"] - (time.monotonic()-started))))}
                raw = run_worker(out, name + "__fold" + fold, context, query, variant, assets[variant["model"]], limits)
                calibration = query.loc[query.stage.eq("calibration")]
                sigmoid = fit_sigmoid(raw.loc[calibration.row_id], calibration[TARGET])
                joblib.dump(sigmoid, out / "jobs" / (name + "__fold" + fold) / "sigmoid.joblib")
                part = query.loc[query.stage.isin(["selection", "threshold"]), ["row_id", "station_id", "date", "stage", TARGET]].copy()
                part["none"] = raw.loc[part.row_id].to_numpy(); part["sigmoid"] = apply_sigmoid(sigmoid, part["none"])
                part["fold"] = fold; pieces.append(part)
            joined = pd.concat(pieces, ignore_index=True)
            if joined.row_id.duplicated().any(): raise ValueError("Duplicate inner-fold query records")
            joined.to_parquet(out / (name + "__inner_predictions.parquet"), index=False)
            for method in ("none", "sigmoid"):
                selection = joined[joined.stage.eq("selection")]
                a = recall_budget_threshold(threshold_table(selection[TARGET], selection[method]), plan["false_alert_budget"])
                macro, n = station_macro_recall(selection, selection[method], a["threshold"])
                candidate = name + "__" + method
                rows.append({"candidate": candidate, "station_macro_recall": macro, "positive_label_stations": n,
                             **score(selection[TARGET], selection[method], a["threshold"])})
                policies[candidate] = {"variant": variant, "calibration": method, "selection_threshold": a["threshold"]}
            statuses[name] = "completed"
        except (RuntimeError, ValueError, TimeoutError, OSError) as error:
            statuses[name] = f"unavailable_or_failed: {type(error).__name__}: {error}"
        write_json(out / "validation_status.json", statuses)
    if not rows: raise ValueError("No completed feasible candidate; no performance score or winner fabricated")
    table = pd.DataFrame(rows).sort_values(["station_macro_recall", "recall", "pr_auc_average_precision", "brier", "candidate"], ascending=[False, False, False, True, True])
    table.to_csv(out / "inner_station_validation.csv", index=False)
    candidate = table.iloc[0].candidate
    # Lock the identity before consulting threshold-period labels. An infeasible
    # threshold must stop the study, not silently change which model wins.
    write_json(out / "validation_choice.json", {"candidate": candidate, **policies[candidate],
        "chosen_before_threshold_period_scoring": True})
    selected = pd.read_parquet(out / (policies[candidate]["variant"]["id"] + "__inner_predictions.parquet"))
    threshold = selected[selected.stage.eq("threshold")]
    b = recall_budget_threshold(threshold_table(threshold[TARGET], threshold[policies[candidate]["calibration"]]), plan["false_alert_budget"])
    policies[candidate].update(threshold=b["threshold"], threshold_validation=b)
    write_json(out / "validation_lock.json", {"candidate": candidate, **policies[candidate],
        "assets_sha256": sha256(assets_path), "plan_sha256": sha256(out / "plan.json"),
        "code_sha256": {name: sha256(Path(__file__).parent / name) for name in ["training03.py", "foundation_worker.py"]},
        "note": "Chosen from internal spatial validation only, never the six outer stations"})
    print(table.to_string(index=False))


def finalize(out, assets_path):
    if (out / "final_lock.json").exists(): raise ValueError("Final model recipe already frozen")
    plan = verify(out); lock = read(out / "validation_lock.json")
    if lock["plan_sha256"] != sha256(out / "plan.json"): raise ValueError("Benchmark plan changed after validation")
    if lock["assets_sha256"] != sha256(assets_path): raise ValueError("Assets changed after validation")
    for name, expected in lock["code_sha256"].items():
        if sha256(Path(__file__).parent / name) != expected: raise ValueError("Benchmark code changed after validation")
    data = pd.read_parquet(out / "development.parquet").reset_index(drop=True); data["row_id"] = np.arange(len(data))
    variant = lock["variant"]; assets = read(assets_path)
    context = context_sample(data, FEATURE_SETS[variant["feature_set"]], variant["context_cap"])
    query = data[data.stage.eq("calibration")]
    raw = run_worker(out, "final_calibration", context, query, variant, assets[variant["model"]], plan["resource_limits"])
    calibrator = fit_sigmoid(raw.loc[query.row_id], query[TARGET]) if lock["calibration"] == "sigmoid" else None
    joblib.dump(calibrator, out / "final_calibrator.joblib")
    context.to_parquet(out / "final_context.parquet", index=False)
    write_json(out / "final_lock.json", {**lock, "context_sha256": sha256(out / "final_context.parquet"),
        "calibrator_sha256": sha256(out / "final_calibrator.joblib"), "holdout_sha256": plan["holdout_sha256"],
        "recipe": "Pinned local weights + exact context + frozen calibrator + inner-spatial validation threshold; not a serving deployment"})


def evaluate(out, assets_path):
    if (out / "evaluation.json").exists(): raise ValueError("Final benchmark already evaluated")
    plan = verify(out); lock = read(out / "final_lock.json")
    if lock["plan_sha256"] != sha256(out / "plan.json"): raise ValueError("Benchmark plan changed after validation")
    for name, expected in lock["code_sha256"].items():
        if sha256(Path(__file__).parent / name) != expected: raise ValueError("Benchmark code changed after validation")
    for file, key in [("final_context.parquet", "context_sha256"), ("final_calibrator.joblib", "calibrator_sha256")]:
        if sha256(out/file) != lock[key]: raise ValueError("Frozen final model recipe changed")
    if sha256(assets_path) != lock["assets_sha256"] or sha256(Path(plan["source"])/"evaluation_holdout.parquet") != lock["holdout_sha256"]:
        raise ValueError("Assets or final records changed")
    data = pd.read_parquet(Path(plan["source"])/"evaluation_holdout.parquet").reset_index(drop=True); data["row_id"] = np.arange(len(data))
    raw = run_worker(out, "final_evaluation", pd.read_parquet(out / "final_context.parquet"), data,
                     lock["variant"], read(assets_path)[lock["variant"]["model"]], plan["resource_limits"])
    calibrator = joblib.load(out / "final_calibrator.joblib")
    p = apply_sigmoid(calibrator, raw.loc[data.row_id]) if calibrator is not None else raw.loc[data.row_id].to_numpy()
    rows, station_rows = [], []
    for stage in ("test", "holdout_station"):
        mask = data.stage.eq(stage).to_numpy()
        rows.append({"stage": stage, **score(data.loc[mask, TARGET], p[mask], lock["threshold"])})
        for station in sorted(data.loc[mask, "station_id"].unique()):
            m = mask & data.station_id.eq(station).to_numpy()
            station_rows.append({"stage": stage, "station_id": station, **score(data.loc[m, TARGET], p[m], lock["threshold"])})
    pd.DataFrame(station_rows).to_csv(out / "per_station_metrics.csv", index=False)
    write_json(out / "evaluation.json", {"candidate": lock["candidate"], "results": rows, "test_caveat": plan["test_caveat"]})
    write_json(out / "status.json", {"status": "evaluated_research_only", "active_model_changed": False})
    verify(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare", "preflight", "validate", "finalize", "evaluate"])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--source", type=Path, default=Path("ml/runs/training-02"))
    parser.add_argument("--audit", type=Path, default=Path("ml/runs/training-02-selection-audit"))
    parser.add_argument("--assets", type=Path, default=Path("ml/foundation/assets.json"))
    args = parser.parse_args()
    if args.stage == "prepare": prepare(args.out, args.source, args.audit)
    elif args.stage == "preflight": preflight(args.out, args.assets)
    elif args.stage == "validate": validate(args.out, args.assets)
    elif args.stage == "finalize": finalize(args.out, args.assets)
    else: evaluate(args.out, args.assets)


if __name__ == "__main__": main()
