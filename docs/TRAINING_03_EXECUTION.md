# Executing Training-03

The executed benchmark extends the prepared protocol through
`ml/benchmark03.py`. It preserves `plan.json` and records execution settings in
`execution_plan.json` before validation scores are computed. The earlier
preparation files are retained under `pre_execution/`.

## Local environments and checkpoints

`ml/setup_training03.py` creates separate environments in `ml/envs/tabfm` and
`ml/envs/tabicl`, using Python 3.14 and PyTorch 2.12.1 with CUDA 13.0. It installs
the exact official source commits already declared during preparation. Backend
packages are not changed. Resolved dependencies, installation logs, checkpoint
revisions, license notices and hardware probes are stored in `installation/`.

The laptop's RTX 3050 has 4 GiB VRAM. The restricted tool sandbox hides the GPU,
so GPU stages must execute with actual device access (a normal local terminal
has this access). TabFM's checkpoint contains float32 weights; GPU inference
uses the official loader's bfloat16 mode. The worker limits its GPU allocator
to 85% of total VRAM and records peak allocated/reserved memory. Each worker
has a 16 GiB resident-memory budget, 600-second wall-time cap, two CPU threads
and 64-row query batches. CPU fallback is tested if a GPU smoke test fails.

Public checkpoint sources are
[Google TabFM](https://huggingface.co/google/tabfm-1.0.0-pytorch) and
[TabICLv2](https://huggingface.co/jingang/TabICL). Their licenses permit this
local academic benchmark; TabFM weights are restricted to non-commercial,
non-production use. No pretrained weights are redistributed with reports.
Prepared TabPFN-2.5 requires authenticated access and model-license acceptance
through [Prior Labs](https://docs.priorlabs.ai/models/accessing-model-weights).
No substitute TabPFN version is silently used.

## Comparability and model choice

All candidates use the same prepared binary labels, internal station folds,
temporal blocks and 30/38-feature schemas. Within each context cap and fold,
the context keys are identical and selected independently of labels. Both
100-row controls and larger contexts are reported; full-training classical
models and capped foundation models have unequal training exposure.

Logistic Regression, CatBoost and LightGBM are refit for each internal fold,
excluding every record from its query stations. Their hyperparameters are
fixed from Training-02. This is fresh station-excluded fitting, but the
underlying development labels and classical tuning results have historical
use; these are not wholly new independent validation data.

Calibration fits only on other stations' 2022 H2 records. Candidate choice uses
inner-held stations' 2023 H1 records and prioritizes station-macro recall under
the existing FP/TP budget, then pooled recall, AP and Brier. Stations without
positive labels are excluded from macro recall and their count is reported.
Family winners and the overall choice are written before 2023 H2 thresholds
are scored. H2 never selects a replacement winner. An infeasible H2 threshold
becomes an explicit no-alert diagnostic policy. A family with no feasible H1
candidate receives an H1-AP-ranked diagnostic representative; it cannot win.

All family contexts, calibrators and thresholds are frozen before outer
diagnostics. Previously inspected temporal and station holdouts are evaluated
on identical records, alongside immutable historical reference predictions.
These results cannot select or promote a model. No untouched independent final
set exists in the prepared data; prospective independent validation is still
required. The source labels remain research flood-detection proxies.

## Reproduction commands

From the repository root, the existing prepared run uses:

```bash
export MPLCONFIGDIR=/tmp/is314-mpl
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
backend/.venv/bin/python -m ml.setup_training03
backend/.venv/bin/python -m ml.benchmark03 smoke --device cuda
backend/.venv/bin/python -m ml.benchmark03 configure --device cuda
backend/.venv/bin/python -m ml.benchmark03 validate
backend/.venv/bin/python -m ml.benchmark03 diagnose
backend/.venv/bin/python -m ml.benchmark03 report
```

Execution jobs and model choices refuse overwrite. To reproduce after the
existing run is complete, prepare a new directory and pass that same `--out`
to every command above:

```bash
backend/.venv/bin/python -m ml.training03 prepare \
  --out ml/runs/training-03-reproduction
```

`installation/*_resolved.txt` records exact resolved dependencies for the
executed environments. The checkpoint manifest is `ml/foundation/assets.json`;
checkpoints remain local under `ml/foundation/weights/`. Real inference is
offline after installation. Smoke tests use 16 original tuning queries and
save no performance scores. Candidate validation begins only after smoke
testing and protocol configuration.

## Outputs

`benchmark_report.md` contains the complete results. CSVs include all internal
candidate metrics, H2 metrics at frozen thresholds, per-station results,
diagnostic confusion matrices, calibration bins, and execution times/hardware
usage. PR/calibration charts cover selection, threshold and both outer
diagnostic partitions. Raw predictions, exact context/query rows, model
recipes, checkpoint hashes, code locks and installation failures remain in
the run directory. No serving-model replacement is part of this benchmark.
