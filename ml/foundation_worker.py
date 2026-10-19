"""Isolated, offline foundation-model inference. No final labels are accepted."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import resource
import time

import numpy as np
import pandas as pd


def asset_digest(path):
    path = Path(path)
    def digest(file):
        with file.open("rb") as stream: return hashlib.file_digest(stream, "sha256").hexdigest()
    if path.is_file(): return digest(path)
    if not path.is_dir(): raise FileNotFoundError(path)
    hashes = {str(p.relative_to(path)): digest(p) for p in sorted(path.rglob("*")) if p.is_file()}
    if not hashes: raise ValueError("Empty checkpoint directory")
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()


def make_estimator(name, asset, device="cpu"):
    if name == "classical":
        from ml.train import pipeline
        from ml.training02 import estimator
        return pipeline(estimator(asset["spec"]))
    if asset_digest(asset["path"]) != asset["sha256"]:
        raise ValueError("Pretrained checkpoint digest differs from asset manifest")
    import torch
    torch.set_num_threads(2)
    torch.manual_seed(314)
    if device.startswith("cuda"):
        torch.cuda.set_per_process_memory_fraction(.85)
    if name == "tabfm":
        from tabfm import TabFMClassifier, tabfm_v1_0_0_pytorch
        model = tabfm_v1_0_0_pytorch.load(model_type="classification", checkpoint_path=asset["path"], device=device,
                                        dtype=torch.bfloat16 if device.startswith("cuda") else None)
        return TabFMClassifier(model=model, n_estimators=4, max_num_rows=100, random_state=314,
                               batch_size=1, binary_calibration_method=None, enable_nnls=False,
                               use_amp=device.startswith("cuda"), cache_context=True, maybe_quantize_kv_cache=False)
    if name == "tabpfn":
        from tabpfn import TabPFNClassifier
        from tabpfn.constants import ModelVersion
        return TabPFNClassifier.create_default_for_version(ModelVersion.V2_5, model_path=asset["path"], device=device,
            n_estimators=4, auto_scale_n_estimators=False, random_state=314, fit_mode="low_memory",
            n_preprocessing_jobs=1, balance_probabilities=False)
    if name == "tabicl":
        from tabicl import TabICLClassifier
        return TabICLClassifier(model_path=asset["path"], allow_auto_download=False,
            checkpoint_version="tabicl-classifier-v2-20260212.ckpt", device=device,
            n_estimators=4, batch_size=1, random_state=314, n_jobs=2, kv_cache=asset.get("kv_cache", False))
    raise ValueError("Unsupported foundation model")


def predict_request(request, factory=make_estimator):
    features = request["features"]
    if any(any(word in name.lower() for word in ["flood", "target", "future", "regime"]) for name in features):
        raise ValueError("Answer-derived feature in worker request")
    context = pd.read_parquet(request["context"])
    query = pd.read_parquet(request["query"])
    if set(context) != set(features + ["label"]) or set(query) != set(features + ["row_id"]):
        raise ValueError("Worker accepts only context labels; query labels are forbidden")
    if context.label.nunique() != 2: raise ValueError("Selected context has one class; no target-driven resampling allowed")
    if not np.isfinite(context[features].to_numpy()).all() or not np.isfinite(query[features].to_numpy()).all():
        raise ValueError("Incomplete worker features")
    model = factory(request["model"], request["asset"], request["device"])
    model.fit(context[features], context.label.astype(int))
    classes = list(model.classes_)
    if sorted(classes) != [0, 1]: raise ValueError("Unexpected classifier class schema")
    probabilities = []
    for start in range(0, len(query), request.get("query_batch_rows", 64)):
        chunk = query.iloc[start:start+request.get("query_batch_rows", 64)]
        probability = np.asarray(model.predict_proba(chunk[features]))[:, classes.index(1)]
        if not np.isfinite(probability).all() or not ((probability >= 0) & (probability <= 1)).all():
            raise ValueError("Invalid foundation-model probabilities")
        probabilities.extend(probability.tolist())
    return pd.DataFrame({"row_id": query.row_id.to_numpy(), "probability": probabilities})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    args = parser.parse_args()
    request = json.loads(args.request.read_text())
    # No implicit downloads, browser authentication, or remote inference.
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", TABPFN_NO_BROWSER="1")
    memory = request.get("memory_gb", 16) * 1024**3
    # CUDA reserves a large virtual address range. Parent enforces resident RAM
    # for GPU workers; a virtual-address cap incorrectly rejects CUDA startup.
    if request["model"] == "classical":
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_CPU, (request.get("timeout_seconds", 600), request.get("timeout_seconds", 600)))
    started = time.monotonic()
    result = predict_request(request)
    result.to_parquet(request["output"], index=False)
    versions = {}
    for name in ["torch", "pandas", "numpy", "scikit-learn", "tabfm", "tabpfn", "tabicl"]:
        try: versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: pass
    Path(request["output"] + ".environment.json").write_text(json.dumps(versions, indent=2))
    usage = {"inference_seconds": time.monotonic()-started,
             "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
             "device": request["device"]}
    if request["model"] != "classical":
        import torch
        usage.update(torch_version=torch.__version__, cuda_version=torch.version.cuda,
                     cuda_available=torch.cuda.is_available())
        if request["device"].startswith("cuda"):
            usage.update(gpu_name=torch.cuda.get_device_name(),
                         peak_gpu_allocated_mib=torch.cuda.max_memory_allocated()/1024**2,
                         peak_gpu_reserved_mib=torch.cuda.max_memory_reserved()/1024**2)
    Path(request["output"] + ".usage.json").write_text(json.dumps(usage, indent=2))


if __name__ == "__main__": main()
