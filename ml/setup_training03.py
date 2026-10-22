"""Install local research environments and publicly accessible pinned weights."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
import venv

from ml.foundation_worker import asset_digest
from ml.refinement import directory_hashes
from ml.train import write_json

OUT = Path("ml/runs/training-03")
REPOS = {"tabfm": "google/tabfm-1.0.0-pytorch", "tabicl": "jingang/TabICL"}
FILES = {"tabfm": ["LICENSE", "README.md", "classification/config.json", "classification/model.safetensors"],
         "tabicl": ["README.md", "tabicl-classifier-v2-20260212.ckpt"]}


def get(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def setup(out):
    installation = out / "installation"; installation.mkdir(exist_ok=True)
    archive = out / "pre_execution"
    if not archive.exists():
        archive.mkdir()
        for p in out.glob("*.json"): shutil.copy2(p, archive / p.name)
        write_json(archive / "app_hashes.json", {str(p): directory_hashes(p) for p in
                   [Path("backend/app"), Path("frontend/src"), Path("ml/artifacts")]})
        (archive / "backend_freeze.txt").write_text(subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True))
    hardware = {"python": sys.version, "platform": platform.platform(), "cpu": platform.processor()}
    for name, cmd in {"gpu": ["nvidia-smi"], "ram": ["free", "-b"], "cpu_details": ["lscpu"]}.items():
        probe = subprocess.run(cmd, capture_output=True, text=True)
        hardware[name] = {"returncode": probe.returncode, "stdout": probe.stdout, "stderr": probe.stderr}
    write_json(out / "hardware.json", hardware)
    sources = json.loads(Path("ml/foundation/sources.json").read_text())
    assets = json.loads(Path("ml/foundation/assets.example.json").read_text())
    statuses = {}
    for name, repo in REPOS.items():
        started = time.monotonic()
        try:
            metadata = json.loads(get("https://huggingface.co/api/models/" + repo))
            write_json(installation / (name + "_checkpoint_metadata.json"), metadata)
            if metadata.get("gated"): raise RuntimeError("Checkpoint requires authenticated access")
            weight_dir = Path("ml/foundation/weights") / name; weight_dir.mkdir(parents=True, exist_ok=True)
            for filename in FILES[name]:
                dest = weight_dir / filename; dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists():
                    print("Downloading", name, filename, flush=True)
                    url = f"https://huggingface.co/{repo}/resolve/{metadata['sha']}/{filename}?download=true"
                    with urllib.request.urlopen(url, timeout=120) as response, dest.with_suffix(dest.suffix + ".partial").open("wb") as target:
                        shutil.copyfileobj(response, target)
                    dest.with_suffix(dest.suffix + ".partial").rename(dest)
            for filename in ["LICENSE", "pyproject.toml"]:
                url = f"https://raw.githubusercontent.com/{sources[name]['repository'].split('github.com/')[1]}/{sources[name]['commit']}/{filename}"
                (installation / (name + "_" + filename)).write_bytes(get(url))
            python = Path(assets[name]["python"])
            if not python.exists(): venv.EnvBuilder(with_pip=True).create(python.parent.parent)
            env = {**os.environ, "PIP_CACHE_DIR": str(Path("ml/envs/.pip-cache").resolve()), "PIP_DISABLE_PIP_VERSION_CHECK": "1"}
            command = [str(python), "-m", "pip", "install", "-r", f"ml/foundation/requirements-{name}-cuda.txt"]
            print("Installing", name, "into", python.parent.parent, flush=True)
            with (installation / (name + "_install.log")).open("w") as log:
                subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
            (installation / (name + "_resolved.txt")).write_text(subprocess.check_output([str(python), "-m", "pip", "freeze"], env=env, text=True))
            probe = subprocess.run([str(python), "-c", "import torch,json; print(json.dumps({'torch':torch.__version__,'cuda':torch.version.cuda,'available':torch.cuda.is_available(),'gpu':torch.cuda.get_device_name() if torch.cuda.is_available() else None}))"], capture_output=True, text=True)
            (installation / (name + "_torch_probe.txt")).write_text(probe.stdout + probe.stderr)
            checkpoint = weight_dir / ("classification" if name == "tabfm" else FILES[name][-1])
            assets[name].update(path=str(checkpoint.resolve()), sha256=asset_digest(checkpoint))
            statuses[name] = {"status": "installed", "seconds": time.monotonic()-started,
                              "checkpoint_revision": metadata["sha"], "source_commit": sources[name]["commit"]}
        except Exception as error:
            statuses[name] = {"status": "unavailable", "error": str(error), "seconds": time.monotonic()-started}
        write_json(installation / "status.json", statuses)
        write_json(Path("ml/foundation/assets.json"), assets)
    statuses["tabpfn"] = {"status": "skipped", "reason": "Prepared TabPFN-2.5 weights require Prior Labs login and model-license acceptance. No authenticated local checkpoint configured; public HF metadata probe returned HTTP 401.",
        "official_access_documentation": "https://docs.priorlabs.ai/models/accessing-model-weights",
        "environment_token_present": bool(os.environ.get("TABPFN_TOKEN"))}
    write_json(installation / "status.json", statuses)
    print(json.dumps(statuses, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT)
    setup(parser.parse_args().out)
