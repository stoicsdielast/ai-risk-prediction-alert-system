# Training-03: foundation-model benchmark prepared for spatial flood detection

The [training-02 selection audit](TRAINING_02_SELECTION_AUDIT.md) is completed
first. `ml/runs/training-03/` contains a prepared protocol and preflight, not
foundation-model performance results. No heavy model environment or pretrained
weights were installed/downloaded during preparation.

## Preserved data and the detection objective

The original development data, dates, embargoes, sampling keys and six entire
outer holdout stations remain unchanged. Prior runs and audit files are hashed
and checked. The existing serving model and all five app modules are untouched.

Four deterministic internal station folds are added **within the 24 development
stations**. For each fold:

- Model context contains original pre-2022 training rows from the other stations.
- A sigmoid calibrator, when used, fits only 2022 H2 calibration predictions at
  the other stations. It never fits on the query fold or outer holdout.
- 2023 H1 selection and 2023 H2 threshold queries use internal held-out stations.
  Each validation row is queried exactly once, with its entire station absent
  from context. Calibration labels are absent from foundation-model context.
- Candidates rank by station-macro recall at a feasible pooled-recall operating
  point under the approved FP/TP budget, then pooled recall, AP and lower Brier.
  Station recall is undefined without positives; the contributing station count
  is reported. No accuracy criterion or Brier eligibility gate drives selection.
- After candidate choice, its threshold is fixed using internal held-out 2023 H2
  predictions and the same budget. The final context uses original training
  stations only, and the final calibrator uses 2022 H2. No model/calibrator or
  threshold fits on the outer temporal or station evaluation.
  If the chosen candidate has no feasible positive-detection threshold on H2,
  the study stops; H2 feasibility never selects a different candidate.

This prioritizes validation of station transfer. It cannot recreate a blind
test from previously viewed outer outcomes. The original selection period still
has only 31 positives, half-year seasonality differs, and probability scales
can shift between internal folds and final context. Fresh prospective data and
Fiji MET validation remain necessary.

## Model versions, resources and source terms

Official source revisions are pinned in
[`sources.json`](../ml/foundation/sources.json):

| Model | Explicit recipe | Source and weight references |
|---|---|---|
| Google TabFM | PyTorch v1.0.0 classification; four ensembles; at most 100 context rows | [Official code](https://github.com/google-research/tabfm/tree/fbb665569425fd2f490c6576b3af967876fe11ff), [weight card](https://huggingface.co/google/tabfm-1.0.0-pytorch) |
| TabPFN | Explicit `ModelVersion.V2_5`, four ensembles; 100-row control and 2,048-row cap | [Official code](https://github.com/PriorLabs/TabPFN/tree/417c9877dbfe657afdbe0aee70af2a05ffe4abba), [model/version documentation](https://docs.priorlabs.ai/models) |
| TabICLv2 | Explicit `tabicl-classifier-v2-20260212.ckpt`, four ensembles; 100-row control and 4,096-row cap | [Official code](https://github.com/soda-inria/tabicl/tree/c91f00df184a5097e584cb376f7e699e9f3444c4), [weight card](https://huggingface.co/jingang/TabICL) |

Code and weights have separate terms. TabFM weights are non-commercial and
non-production; TabPFN-2.5 weights have upstream non-commercial/license-access
requirements. TabICL's official code and weight card identify BSD-3-Clause.
The pinned source and checkpoint identity are explicit; no moving model default
is substituted. The original Bangladesh data's redistribution terms remain
unresolved regardless of the model license.

Both 30-feature original and 38-feature hydrology schemas are prepared. Context
sampling uses the lowest original hashes, independently of labels and query
features. Rows are not resampled to obtain positives. Single-class contexts
fail explicitly. Matched-100 comparisons isolate a common context budget;
larger capped-context comparisons are different resource recipes, not equal
training exposure. Classical training-02 models used more training rows.

The prepared protocol is CPU-only because the NVIDIA driver was unavailable.
Each worker has a 16 GiB virtual-memory limit, 600-second maximum, two CPU
threads and 64-row query batches. Total validation is capped at one hour.
Timeouts, missing dependencies/weights and failed or infeasible candidates are
reported without fabricated scores. Internal model calibration/search is
disabled where exposed; explicit external calibration uses the separate block.

## Commands

From `/home/mohanx13/UNI/cs314/fiji-flood-risk-system`, the preparation already run
was:

```bash
MPLCONFIGDIR=/tmp/is314-mpl backend/.venv/bin/python -m ml.training03 prepare
MPLCONFIGDIR=/tmp/is314-mpl backend/.venv/bin/python -m ml.training03 preflight \
  --assets ml/foundation/assets.example.json
```

The second command records the actual missing environments/checkpoints. Running
prepare again refuses overwrite. For a separate preparation use a new `--out`
at every subsequent stage.

Install each model into its own environment, leaving the backend environment
unchanged. These heavyweight environment specifications have not yet been
executed or runtime-validated; retain the install log and resolved `pip freeze`.

```bash
for foundation_model in tabfm tabpfn tabicl; do
  backend/.venv/bin/python -m venv "ml/envs/$foundation_model"
  "ml/envs/$foundation_model/bin/python" -m pip install \
    -r "ml/foundation/requirements-$foundation_model.txt"
  "ml/envs/$foundation_model/bin/python" -m pip freeze \
    > "ml/envs/$foundation_model/resolved.txt"
done
```

Obtain permitted local classification checkpoints from the official sources.
The benchmark never launches a browser, accepts license terms on your behalf,
calls remote inference or downloads weights. Copy and fill the local manifest:

```bash
cp ml/foundation/assets.example.json ml/foundation/assets.json
```

For each model, set `python`, local checkpoint `path`, and `sha256`. TabFM uses a
directory containing its classification config/weights; TabPFN/TabICL use local
checkpoint files. Compute the required digest with the helper (directory
digests hash a sorted mapping of relative filenames to file SHA256s):

```bash
backend/.venv/bin/python -c \
  "from ml.foundation_worker import asset_digest; print(asset_digest('/absolute/checkpoint/path'))"
```

Then run the stages:

```bash
export MPLCONFIGDIR=/tmp/is314-mpl
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
backend/.venv/bin/python -m ml.training03 preflight
backend/.venv/bin/python -m ml.training03 validate
backend/.venv/bin/python -m ml.training03 finalize
backend/.venv/bin/python -m ml.training03 evaluate
```

`validate` runs bounded internal spatial workers and locks the detection-based
choice. `finalize` records the final context, calibrator and already selected
threshold before reading final evaluation. `evaluate` scores only that frozen
recipe on the old temporal and station holdouts, writes aggregate/per-station
metrics, and performs no selection or notification. Partial validation failures
remain local; use a fresh output directory after changing environments/assets.

Artifacts retain exact context keys, labels for permitted training only, query
features without query labels, raw probabilities, environment versions,
checkpoint/code/data hashes, worker logs and the final recipe. Foundation-model
workers run offline. Their code can execute in separate Python environments;
these are not drop-in binaries for the current FastAPI serving environment.
No deployment is part of this benchmark preparation.

## Verification

```bash
MPLCONFIGDIR=/tmp/is314-mpl OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
  backend/.venv/bin/python -m pytest ml/tests -q
```

Synthetic worker tests verify context/query separation and class-probability
column handling; they are software tests, not foundation-model skill results.
Actual TabFM/TabPFN/TabICLv2 runtime and performance remain unmeasured until
their real environments and licensed checkpoints are configured.
