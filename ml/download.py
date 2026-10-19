"""Download only one dataset and small audit sources, all pinned to one commit."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen

from ml.config import ARTIFACTS, COMMIT, DATA_BLOB, DATA_PATH, RAW, REPOSITORY


def fetch(url):
    with urlopen(Request(url, headers={"User-Agent": "is314-research-audit"}), timeout=120) as response:
        return response.read()


def download(offline=False):
    RAW.mkdir(parents=True, exist_ok=True)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    tree_path = RAW / "source/tree.json"
    tree_path.parent.mkdir(exist_ok=True)
    if not offline:
        tree_path.write_bytes(fetch(f"https://api.github.com/repos/Srabon-bot/Bangladesh-flood-data-set/git/trees/{COMMIT}?recursive=1"))
    tree = json.loads(tree_path.read_text())
    if tree.get("sha") != COMMIT or tree.get("truncated"):
        raise ValueError("Cannot verify complete source tree against the pinned commit")
    entries = {entry["path"]: entry for entry in tree["tree"]}
    files = {"all_stations.parquet": DATA_PATH, "source/README.md": "README.md",
             "source/build_features.py": "train/build_features.py", "source/stations.py": "train/stations.py"}
    hashes = {}
    for local, remote in files.items():
        destination = RAW / local
        if not offline:
            data = fetch(f"https://raw.githubusercontent.com/Srabon-bot/Bangladesh-flood-data-set/{COMMIT}/{remote}")
            temporary = destination.with_suffix(destination.suffix + ".part")
            temporary.write_bytes(data)
        else:
            data = destination.read_bytes()
        git_hash = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        expected = DATA_BLOB if local == "all_stations.parquet" else entries[remote]["sha"]
        if git_hash != expected:
            raise ValueError(f"Git blob integrity failure: {remote}")
        if not offline:
            temporary.replace(destination)
        hashes[local] = {"bytes": len(data), "git_blob_sha1": git_hash, "sha256": hashlib.sha256(data).hexdigest()}
    import pyarrow.parquet as pq
    table = pq.read_table(RAW / "all_stations.parquet")  # Full decode, not only magic bytes.
    if table.num_rows != 839340 or table.num_columns != 49:
        raise ValueError("Unexpected source dataset shape")
    licenses = [name for name in entries if name.rsplit("/", 1)[-1].lower().startswith(("license", "licence", "copying"))]
    provenance = {
        "repository": REPOSITORY, "commit": COMMIT, "path": DATA_PATH,
        "verified_at": datetime.now(timezone.utc).isoformat(), "files": hashes,
        "parquet_full_decode": True, "license_files": licenses,
        "license_status": "No repository license found; permission to reuse/redistribute is unresolved. Public access is not a license.",
        "upstream_terms": "Individual reanalysis, GFMS, event archive, and MERIT Hydro terms also require review.",
        "source_reliability": "Community-built virtual gauges; reanalysis/modelled hydrology and mixed remote-sensing/event labels. Not Fiji MET or physical-gauge truth.",
    }
    (ARTIFACTS / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    return provenance


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Verify previously downloaded pinned files")
    args = parser.parse_args()
    try:
        print(json.dumps(download(args.offline), indent=2))
    except Exception as error:
        raise SystemExit(
            f"Dataset unavailable or verification failed: {error}. No data manufactured. "
            "Monthly-resolution fallback: https://github.com/n-gauhar/Flood-prediction; "
            "it requires a different monthly task and cannot supply a 24-hour target."
        ) from error
