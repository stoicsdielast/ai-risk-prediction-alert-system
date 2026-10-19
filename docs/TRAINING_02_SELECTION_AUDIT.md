# Why training-02 selected a different model from the tuning winner

The comprehensive, measured report is
[`model_selection_report.md`](../ml/runs/training-02-selection-audit/model_selection_report.md).
It includes split-key verification, calibration/threshold comparisons, fixed-depth
feature ablations, per-station results and detection transitions. Neither
`training-01` nor `training-02` was modified.

## Findings

1. **Different objectives and periods selected different winners.** Balanced
   hydrology CatBoost, depth 6/L2 10, led 2022 H1 tuning AP at **0.430607**.
   That only chose hyperparameters within its group. Final selection minimized
   2023 H1 Brier subject to AP >= **0.154161** (95% of original logistic AP on
   that block). Hydrology raw/sigmoid AP was **0.121098**, so it was ineligible.
   Baseline depth-4/L2-5 CatBoost with sigmoid had AP **0.173391**, Brier
   **0.021454**, and passed. Balanced baseline LightGBM also passed, with AP
   **0.181529**, but its Brier **0.021588** was slightly higher. The study
   selected probability error ahead of recall under the alert budget.
2. **Row comparisons were identical; threshold optimization was not applied to
   everyone.** All 43 candidates shared the same tuning, calibration, selection
   and threshold-block rows, with no missing prediction columns. However, their
   development metrics used .5; only the selected model and original logistic
   baseline received optimized thresholds. The original experiment did not
   compare every model's best feasible detection policy before choosing one.
3. **Calibration is not recall.** Changing models changed ranking. Sigmoid
   changed the probability scale, and the budget chose an operating point.
   Selected temporal TP fell **126→105**, while FP fell **225→160**. Its Brier
   improved substantially, but recall fell **44.84%→37.37%**. Of original true
   detections, **39 were lost** and **18 new detections were recovered**.
   In the controlled audit, raw and sigmoid versions of each saved tuning
   winner produced **zero decision disagreements** after each received a
   validation-only budget threshold. Thus sigmoid alone did not cause that loss.
4. **The spatial policy did not transfer well.** Selected CatBoost caught
   **11/46** positives versus logistic **13/46**: four detections were lost and
   two recovered. Spatial AP fell **0.2351→0.1769**. Threshold-block prevalence
   was **7.34%**, compared with **3.03%** at outer held-out stations. Selected
   spatial FP/TP was **4.0**, exceeding both the validation budget **1.7857** and
   original spatial FP/TP **3.5385**. ROC-AUC improved slightly despite poorer
   early-positive detection; it is not an adequate selection objective here.
5. **The threshold helped relative to .5, but not relative to the original
   model.** Selected calibrated CatBoost's validation recall increased
   **12.50%→36.54%** after budget thresholding. But original logistic achieved
   **40.38%** on those same records. The constrained maximum was found for the
   chosen score vector; it was not the maximum achievable across all models.
   No target recall was forced beyond the budget.

The 2023 H1 selection block has only 31 positive labels, and its season differs
from tuning and calibration. Scores are unstable, and all labels remain
source-qualified flood-detection proxies rather than verified physical truth.

## Frozen, identical-procedure comparison

Saved raw/sigmoid/isotonic models were reused. Each received its own threshold
chosen on the same 2023 H2 records under the same original FP/TP budget. The
models, checkpoints, thresholds and holdout hashes were frozen before scoring.
Two additional train-only CatBoost controls match depth and L2 across original
and hydrology feature sets, to avoid attributing tree-complexity effects to
features. They use existing configurations, not a new parameter search.

| Frozen model, sigmoid calibration | Temporal recall | Temporal AP | Unseen-station recall | Unseen-station AP |
|---|---:|---:|---:|---:|
| Original logistic, original threshold | 0.4484 | 0.3701 | 0.2826 | 0.2351 |
| Baseline CatBoost, selected in training-02 | 0.3737 | 0.3720 | 0.2391 | 0.1769 |
| Hydrology CatBoost, tuning winner | 0.3665 | 0.3426 | 0.3043 | 0.1967 |
| Baseline LightGBM, strongest baseline tuning AP | 0.3310 | 0.3824 | 0.1739 | 0.2000 |

Hydrology CatBoost caught 14 unseen-station positives, one more than logistic
and three more than selected CatBoost. This is a useful hypothesis for future
spatial validation, not a valid post-test selection rule. It still had lower
spatial AP than original logistic.

## Separating feature, calibration and decision effects

The winners differ in tree complexity as well as features. Fixed-depth controls
use the same training rows, weighting, iterations, learning rate and calibration
block. Each receives its own threshold from the same validation budget. The
following are hydrology minus original-feature differences, with sigmoid:

| Matched configuration | Temporal recall change | Unseen-station recall change | Temporal AP change | Unseen-station AP change |
|---|---:|---:|---:|---:|
| Depth 4, L2 5 | +0.0071 | +0.0217 | +0.0091 | +0.0362 |
| Depth 6, L2 10 | +0.0320 | +0.0652 | -0.0122 | +0.0104 |

These paired results suggest useful spatial signal in the additional features,
but show that higher recall need not coincide with higher AP. They do not
establish a general gain or authorize selection using the outer results.

Calibration comparisons below use the saved tuning winners and separately
validation-optimized budget thresholds. Brier is independent of the threshold.

| Model | Calibration | Temporal Brier | Temporal recall | Unseen-station Brier | Unseen-station recall |
|---|---|---:|---:|---:|---:|
| Baseline CatBoost | None | 0.1184 | 0.3737 | 0.1075 | 0.2391 |
| Baseline CatBoost | Sigmoid | 0.0392 | 0.3737 | 0.0313 | 0.2391 |
| Baseline CatBoost | Isotonic | 0.0447 | 0.3203 | 0.0385 | 0.1522 |
| Hydrology CatBoost | None | 0.0962 | 0.3665 | 0.0865 | 0.3043 |
| Hydrology CatBoost | Sigmoid | 0.0398 | 0.3665 | 0.0319 | 0.3043 |
| Hydrology CatBoost | Isotonic | 0.0413 | 0.3523 | 0.0337 | 0.3043 |

Sigmoid substantially reduces probability error while retaining the same
budget-constrained decisions. Isotonic merges scores into ties, changing the
available operating points; its additional flexibility did not improve these
saved winners' Brier scores over sigmoid. All calibration fits use disjoint
2022 H2 records. These outer scores are descriptive, not calibration selection
criteria. Full train/validation, default-cutoff and budget-cutoff results are in
the generated report's accompanying CSV files.

The original outer outcomes were already inspected. Additional evaluation is
**retrospective diagnostic reuse**, not a new blind test. No final-test or outer
station label optimized parameters, calibration or thresholds, and no model was
promoted from these additional scores.

## Reproduce the audit

From the repository root, use a new output directory for a fresh audit:

```bash
export MPLCONFIGDIR=/tmp/is314-mpl
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
backend/.venv/bin/python -m ml.audit02_selection prepare --out ml/runs/selection-audit-reproduction
backend/.venv/bin/python -m ml.audit02_selection evaluate --out ml/runs/selection-audit-reproduction
```

For read-only report regeneration of the existing completed audit:

```bash
MPLCONFIGDIR=/tmp/is314-mpl backend/.venv/bin/python -m ml.audit02_selection report
```

Next: [training-03 foundation-model benchmark preparation](TRAINING_03.md).
