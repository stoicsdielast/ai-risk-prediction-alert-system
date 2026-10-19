"""Bounded foundation-model benchmark for Synthetic V3 (research comparison only).

Runs one foundation model per invocation through the offline ``ml.foundation_worker``
contract: label-blind context rows from the training partition, no query labels,
no downloads. The context window is hard-capped by the model (TabICL 4096, TabFM
100, TabPFN 2048) and the test scoring rows are a documented deterministic sample,
so this is a bounded comparison — never a full-partition score and never a
promotion candidate. TabPFN requires an operator-supplied licensed checkpoint.

Usage (repo root):
    ml/envs/tabicl/bin/python -m ml.synthetic.foundation_v3 --model tabicl \
        --dataset ml/data/synthetic_fiji/v3/realistic --run ml/runs/synthetic-v3/realistic \
        --out ml/runs/synthetic-v3/foundation-tabicl-realistic
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score

from ml.synthetic.train_v3 import BUDGET
from ml.synthetic.train_v2 import budget_values
from ml.train import write_json

CONTEXT_CAPS = {"tabicl": 4096, "tabfm": 100, "tabpfn": 2048}
ENV_PYTHONS = {"tabicl": "ml/envs/tabicl/bin/python", "tabfm": "ml/envs/tabfm/bin/python",
               "tabpfn": "ml/envs/tabpfn/bin/python"}
DEVICES = {"tabicl": "cuda", "tabfm": "cpu", "tabpfn": "cuda"}


def label_blind_sample(frame, size, seed):
    """Deterministic row sample that never inspects labels; retries only when a
    feasibility guard (both classes required by the worker) fails."""
    if len(frame) <= size:
        return frame.reset_index(drop=True), seed
    for attempt in range(5):
        rng = np.random.default_rng(seed + attempt)
        index = rng.choice(len(frame), size=size, replace=False)
        sample = frame.iloc[np.sort(index)].reset_index(drop=True)
        if sample.flood_within_24h.nunique() == 2:
            return sample, seed + attempt
    raise ValueError("No label-blind sample contains both classes; raise the sample size")


def score(y, p, threshold):
    predicted = p >= threshold
    return {"threshold": float(threshold), "prevalence": float(np.mean(y)),
            "recall": float(recall_score(y, predicted, zero_division=0)),
            "precision": float(precision_score(y, predicted, zero_division=0)),
            "f1": float(f1_score(y, predicted, zero_division=0)),
            "pr_auc_average_precision": float(average_precision_score(y, p)),
            "false_alerts_per_detection_budget": BUDGET}


def run_model(name, dataset, run, out, device=None, query_rows=4000, context_rows=None):
    run, out = Path(run), Path(out)
    if out.exists():
        raise ValueError("Output exists; use a fresh directory")
    _require_asset(name)
    features = pd.read_parquet(run / "features.parquet")
    splits = pd.read_parquet(run / "splits.parquet")
    frame = features.merge(splits[["location_id", "timestamp", "stage", "flood_within_24h"]],
                           on=["location_id", "timestamp"], validate="one_to_one")
    names = json.loads((run / "candidate_metadata.json").read_text())["features"]
    cap = context_rows or CONTEXT_CAPS[name]
    context, context_seed = label_blind_sample(frame[frame.stage.eq("train")], cap, 314)
    threshold_part, threshold_seed = label_blind_sample(
        frame[frame.stage.eq("threshold")], query_rows, 315)
    query, query_seed = label_blind_sample(frame[frame.stage.eq("test")], query_rows, 316)

    out.mkdir(parents=True)
    context[names].assign(label=context.flood_within_24h.astype(int)).to_parquet(
        out / "context.parquet", index=False)
    query_ids = query[["location_id", "timestamp"]].reset_index(drop=True)
    query_ids["row_id"] = np.arange(len(query_ids))
    query_ids.to_parquet(out / "query_index.parquet", index=False)
    # Worker contract: features + row_id only; query labels stay with the parent.
    worker_query = query[names].copy()
    worker_query.insert(0, "row_id", query_ids.row_id.to_numpy())
    worker_query.to_parquet(out / "query_features.parquet", index=False)

    request = {"model": name, "asset": {"path": _asset_path(name), "sha256": _asset_sha(name)},
               "device": device or DEVICES[name], "features": names,
               "context": str((out / "context.parquet").resolve()),
               "query": str((out / "query_features.parquet").resolve()),
               "output": str((out / "predictions.parquet").resolve()),
               "query_batch_rows": 64, "timeout_seconds": 1800}
    (out / "request.json").write_text(json.dumps(request, indent=2))

    started = time.monotonic()
    process = subprocess.run([ENV_PYTHONS[name], "-m", "ml.foundation_worker",
                              str((out / "request.json").resolve())],
                             capture_output=True, text=True)
    (out / "worker_stdout.txt").write_text(process.stdout)
    (out / "worker_stderr.txt").write_text(process.stderr)
    if process.returncode != 0:
        raise RuntimeError(f"Worker failed ({process.returncode}): {process.stderr[-2000:]}")

    predictions = pd.read_parquet(out / "predictions.parquet")
    joined = query_ids.merge(predictions, on="row_id", validate="one_to_one")
    y = query.flood_within_24h.astype(int).to_numpy()
    p = joined.probability.to_numpy()
    point = budget_values(threshold_part.flood_within_24h,
                          _threshold_probabilities(name, run, out, threshold_part, names))
    threshold = float(point["threshold"]) if point else float(np.nextafter(1.0, 2.0))

    winner = json.loads((run / "selection_lock.json").read_text())["selected"]
    tabular = pd.read_parquet(run / "predictions.parquet")
    tabular = tabular[(tabular.candidate == winner) & (tabular.stage == "test")].sort_values(
        ["location_id", "timestamp"]).reset_index(drop=True)
    same_rows = tabular.merge(query[["location_id", "timestamp"]], on=["location_id", "timestamp"])
    comparison = score(y, same_rows.probability.to_numpy(), same_rows.threshold.iloc[0])

    usage = json.loads((out / "predictions.parquet.usage.json").read_text())
    write_json(out / "metrics.json", {
        "source_type": "synthetic", "research_only": True, "model": name,
        "device": request["device"], "scenario": json.loads((run / "protocol.json").read_text())["scenario"],
        "context_rows": int(len(context)), "context_cap": cap, "context_seed": context_seed,
        "query_rows": int(len(query)), "query_seed": query_seed,
        "threshold_rows": int(len(threshold_part)), "threshold_seed": threshold_seed,
        "query_prevalence": float(np.mean(y)),
        "foundation": score(y, p, threshold),
        "v3_winner_same_rows": comparison, "v3_winner": winner,
        "selection": "Budget-feasible recall threshold chosen on a label-blind sample of the 2024 H1 threshold partition",
        "limitations": [
            "Context is hard-capped by the foundation model; most training rows are unseen.",
            "Query and threshold scores are deterministic samples, not full partitions.",
            "Class priors are not corrected; compare precision at matched prevalence only.",
            "Research comparison only; never a promotion candidate."],
        "inference_seconds": usage.get("inference_seconds"),
        "peak_gpu_allocated_mib": usage.get("peak_gpu_allocated_mib"),
        "wall_seconds": time.monotonic() - started})
    return json.loads((out / "metrics.json").read_text())


def _threshold_probabilities(name, run, out, threshold_part, names):
    """Foundation-model probabilities for the threshold sample via a second worker call."""
    query_ids = threshold_part[["location_id", "timestamp"]].reset_index(drop=True)
    query_ids["row_id"] = np.arange(len(query_ids))
    worker_query = threshold_part[names].copy()
    worker_query.insert(0, "row_id", query_ids.row_id.to_numpy())
    worker_query.to_parquet(out / "threshold_features.parquet", index=False)
    request = json.loads((out / "request.json").read_text())
    request.update(context=str((out / "context.parquet").resolve()),
                   query=str((out / "threshold_features.parquet").resolve()),
                   output=str((out / "threshold_predictions.parquet").resolve()))
    (out / "threshold_request.json").write_text(json.dumps(request, indent=2))
    process = subprocess.run([ENV_PYTHONS[name], "-m", "ml.foundation_worker",
                              str((out / "threshold_request.json").resolve())],
                             capture_output=True, text=True)
    if process.returncode != 0:
        raise RuntimeError(f"Threshold worker failed ({process.returncode}): {process.stderr[-2000:]}")
    predictions = pd.read_parquet(out / "threshold_predictions.parquet")
    return query_ids.merge(predictions, on="row_id", validate="one_to_one").probability.to_numpy()


def _asset_path(name):
    return json.loads(Path("ml/foundation/assets.json").read_text())[name]["path"]


def _asset_sha(name):
    return json.loads(Path("ml/foundation/assets.json").read_text())[name]["sha256"]


def _require_asset(name):
    if not _asset_path(name):
        raise ValueError(f"No permitted checkpoint is available for {name}; "
                         "supply a licensed checkpoint via ml/foundation/assets.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=sorted(CONTEXT_CAPS), required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", default=None)
    parser.add_argument("--query-rows", type=int, default=4000)
    parser.add_argument("--context-rows", type=int, default=None)
    args = parser.parse_args()
    result = run_model(args.model, args.dataset, args.run, args.out, args.device,
                       args.query_rows, args.context_rows)
    print(json.dumps(result, indent=2))
