# Synthetic V3 scenario study: results

**Status: research comparison only. Nothing in this study is promoted or deployed.**
The deployed model remains **V1** (`ml/artifacts/synthetic/v1`, served unchanged by
`/api/synthetic/*`). V2 remains a research candidate in `ml/runs/synthetic-v2`.
Promotion of any V3 candidate requires explicit human approval; no code path in this
repository can change the serving model.

Every number below comes from the simulator. These are **not** Fiji MET observations,
not validated forecast skill, and not emergency guidance. The protocol was
pre-registered in [docs/SYNTHETIC_V3_PROTOCOL.md](SYNTHETIC_V3_PROTOCOL.md) before any
V3 training ran.

## Scenarios

Three datasets from the extended simulator (`ml/synthetic/generate.py`, same 12-registry
locations, seeds controlled=5101 / realistic=5102 / stress=5103, 2021-01-01 → 2025-06-30,
hourly):

| Scenario | Rows | Flood events | Flood-within-24h prevalence | Rain missingness | Character |
|---|---|---|---|---|---|
| controlled | 525,888 | 353 | 1.67 % | ~0.1 % | Clean sensors, regular storms, mild drainage heterogeneity |
| realistic | 525,888 | 254 | 1.19 % | ~0.6 % | V1-style noise: gauge noise, imperfect sensors, varied catchments |
| stress | 525,888 | 752 | 3.81 % | ~7.1 % | OOD storm profiles, bursty dropouts, drift/spikes, drainage degradation, stronger tide coupling |

`realistic` is bit-identical to the original V1 generator (verified by golden hashes of
locations/observations/events/labels/scenarios files, seeds 7 and 314). Scenarios are
never pooled into a single score.

## Winners (selection partition, budget ≤ 1.7857 false alerts per detection)

| Scenario | Selected candidate | Calibration | Operating threshold |
|---|---|---|---|
| controlled | `catboost_tuned2` | none | 0.0542 |
| realistic | `random_forest_baseline` | isotonic | 0.0269 |
| stress | `lightgbm_weather_only` | isotonic | 0.1591 |

Notable outcomes:

- Tuned CatBoost wins under clean conditions, but the **untuned random-forest baseline
  wins under realistic noise** — the boosted candidates' tuning gains did not survive
  the selection partition under noise.
- Under **stress**, the **weather-only ablation wins**: with drainage degradation,
  blockage noise and sensor drift, engineered catchment/state features add noise rather
  than signal. This is the single most important robustness finding of the study.
- All thresholds are budget-feasible on the 2024 H1 threshold partition only; they are
  frozen before any test/held/storm scoring.

## Diagnostic and reserved evaluations (winner, own operating threshold)

Metrics on the flood-within-24h label. `prevalence` is the label rate in that partition;
`lift` = precision / prevalence.

| Scenario | Partition | Recall | Precision | F1 | PR-AUC | Brier | ECE(10) | Prev. | Lift | True/false alarm episodes | Median lead |
|---|---|---|---|---|---|---|---|---|---|---|---|
| controlled | selection | 1.000 | 0.074 | 0.137 | 0.340 | 0.0036 | 0.0094 | 0.0028 | 26.3× | 4 / 120 | 1 h |
| controlled | threshold | 0.775 | 0.361 | 0.493 | 0.632 | 0.0160 | 0.0060 | 0.0282 | 12.8× | 28 / 97 | 1 h |
| controlled | **test** | **0.850** | **0.265** | **0.404** | **0.495** | 0.0102 | 0.0032 | 0.0148 | 17.9× | 64 / 386 | 1 h |
| controlled | held location | 0.773 | 0.121 | 0.209 | 0.252 | 0.0081 | 0.0088 | 0.0061 | 19.7× | 9 / 109 | 1 h |
| controlled | storm holdout | 0.819 | 0.071 | 0.131 | 0.113 | 0.0084 | 0.0116 | 0.0063 | 11.2× | 3 / 69 | 1 h |
| realistic | selection | 0.542 | 0.079 | 0.138 | 0.297 | 0.0064 | 0.0071 | 0.0073 | 10.8× | 10 / 212 | 1 h |
| realistic | threshold | 0.763 | 0.369 | 0.497 | 0.644 | 0.0247 | 0.0185 | 0.0399 | 9.2× | 47 / 203 | 1 h |
| realistic | **test** | **0.698** | **0.139** | **0.232** | **0.448** | 0.0067 | 0.0043 | 0.0096 | 14.5× | 39 / 549 | 1 h |
| realistic | held location | 0.757 | 0.145 | 0.243 | 0.547 | 0.0054 | 0.0052 | 0.0088 | 16.3× | 12 / 192 | 1 h |
| realistic | storm holdout | 0.758 | 0.515 | 0.613 | 0.553 | 0.0369 | 0.0310 | 0.0508 | 10.1× | 31 / 48 | 1 h |
| stress | selection | 0.502 | 0.499 | 0.500 | 0.439 | 0.0166 | 0.0107 | 0.0221 | 22.6× | 25 / 56 | 1 h |
| stress | threshold | 0.619 | 0.362 | 0.457 | 0.502 | 0.0487 | 0.0241 | 0.0719 | 5.0× | 73 / 79 | 1 h |
| stress | **test** | **0.555** | **0.361** | **0.437** | **0.395** | 0.0256 | 0.0038 | 0.0347 | 10.4× | 141 / 325 | 1 h |
| stress | held location | 0.505 | 0.244 | 0.329 | 0.267 | 0.0184 | 0.0069 | 0.0224 | 10.9× | 31 / 116 | 1 h |
| stress | storm holdout | 0.410 | 0.704 | 0.518 | 0.505 | 0.0842 | 0.0778 | 0.1145 | 6.2× | 50 / 13 | 1 h |

Episode convention (pre-registered): hourly positives merged at ≤ 6 h gaps; a true alarm
requires a same-location event onset in `(episode_end, episode_end + 24 h]`; a 12 h
cooldown suppresses duplicates. Lead time is onset − episode end; it is exactly 1 h in
essentially all true alarms because the simulator's flood onset follows the peak hour —
the models fire late within the 24 h horizon, so episodes are informative about
false-alarm load, not early warning.

Stress has a **4× higher test prevalence** (3.47 % vs 0.96 %), so its higher raw
precision must be read together with prevalence and the precision-lift column, as
pre-registered.

### Block-bootstrap 95 % intervals on test (200 day-block replicates, seed 314)

| Scenario | Recall | Precision | F1 | PR-AUC |
|---|---|---|---|---|
| controlled | [0.716, 0.949] | [0.170, 0.350] | [0.285, 0.497] | [0.329, 0.639] |
| realistic | [0.588, 0.810] | [0.053, 0.247] | [0.098, 0.359] | [0.253, 0.571] |
| stress | [0.470, 0.674] | [0.281, 0.439] | [0.366, 0.507] | [0.315, 0.485] |

Intervals are wide where events are few (realistic has 254 events); point estimates
should not be over-read.

### Per-location test results (9 non-held locations; the 3 held locations are never in test)

| Location | controlled R/P/AP | realistic R/P/AP | stress R/P/AP |
|---|---|---|---|
| Suva | 0.875 / 0.314 / 0.537 | 0.583 / 0.115 / 0.315 | 0.569 / 0.315 / 0.343 |
| Nausori | 0.838 / 0.318 / 0.530 | 0.656 / 0.097 / 0.464 | 0.587 / 0.356 / 0.415 |
| Nadi | 0.856 / 0.300 / 0.610 | 0.677 / 0.123 / 0.435 | 0.427 / 0.444 / 0.419 |
| Lautoka | 0.771 / 0.114 / 0.427 | 0.708 / 0.127 / 0.475 | 0.593 / 0.410 / 0.407 |
| Ba | 0.899 / 0.266 / 0.516 | 0.667 / 0.115 / 0.430 | 0.617 / 0.469 / 0.501 |
| Sigatoka | 0.910 / 0.221 / 0.430 | 0.692 / 0.153 / 0.466 | 0.616 / 0.370 / 0.419 |
| Rakiraki | 0.823 / 0.288 / 0.586 | 0.785 / 0.213 / 0.506 | 0.590 / 0.233 / 0.320 |
| Labasa | 0.792 / 0.168 / 0.311 | 0.781 / 0.203 / 0.559 | 0.538 / 0.351 / 0.416 |
| Levuka | 0.818 / 0.300 / 0.424 | 0.688 / 0.135 / 0.473 | 0.487 / 0.258 / 0.291 |

Held locations (Navua, Savusavu, Vunisea) are scored only in the `held_location`
partition. Lautoka is the weakest controlled location (prevalence 0.4 %); Rakiraki and
Labasa are the most robust under realistic noise.

## Fixed baselines (pre-registered)

Majority (train-prevalence constant) and the v1 hydrological rule
(`rainfall_mm_total_24h > 80 and soil_moisture_pct > 75`), scored with the same
`evaluate` metrics. Majority AP equals prevalence; the rule is nearly unusable at the
operating threshold (recall ≤ 8 % everywhere). Every learned winner beats both baselines
by a wide margin, which is the pipeline-correctness check the controlled scenario was
built for.

| Scenario | Partition | Majority AP | Rule recall | Rule precision | Rule AP | Rule F1 |
|---|---|---|---|---|---|---|
| controlled | threshold | 0.028 | 0.046 | 0.456 | 0.048 | 0.084 |
| controlled | test | 0.015 | 0.076 | 0.227 | 0.031 | 0.113 |
| realistic | threshold | 0.040 | 0.011 | 0.300 | 0.043 | 0.021 |
| realistic | test | 0.010 | 0.017 | 0.203 | 0.013 | 0.032 |
| stress | threshold | 0.072 | 0.020 | 0.246 | 0.075 | 0.037 |
| stress | test | 0.035 | 0.041 | 0.391 | 0.049 | 0.074 |

## Out-of-distribution transfer (realistic winner applied unchanged)

The **realistic** winner (`random_forest_baseline`, isotonic, threshold 0.0269) is
applied to the controlled and stress datasets with features, calibrator and threshold
untouched — the single cross-scenario transfer pre-registered in the protocol
(`ml/synthetic/transfer_v3.py`, `ml/runs/synthetic-v3/transfer_v3.json`).

| OOD target | Partition | Recall | Precision | F1 | AP | Target prevalence |
|---|---|---|---|---|---|---|
| controlled | threshold | 0.695 | 0.239 | 0.356 | 0.395 | 0.028 |
| controlled | test | 0.857 | 0.202 | 0.327 | 0.361 | 0.015 |
| controlled | held location | 0.870 | 0.085 | 0.155 | 0.282 | 0.006 |
| controlled | storm holdout | 1.000 | 0.079 | 0.146 | 0.180 | 0.006 |
| stress | threshold | 0.387 | 0.511 | 0.440 | 0.378 | 0.072 |
| stress | test | 0.368 | 0.356 | 0.362 | 0.243 | 0.035 |
| stress | held location | 0.420 | 0.253 | 0.316 | 0.216 | 0.022 |
| stress | storm holdout | 0.400 | 0.820 | 0.537 | 0.480 | 0.114 |

Reading: the realistic winner **transfers acceptably to controlled** (AP 0.361 vs
controlled's own winner 0.495 on test) but **degrades on stress** (AP 0.243 vs 0.395,
recall 0.368 vs 0.555) — its threshold is calibrated for a 1 % prevalence world and
under-fires in the 3.5 % stress world. This is the quantitative case for
scenario-specific thresholds and for not promoting a single model across regimes without
recalibration.

## Research serving surface (lecturer view)

- Publish step: `backend/.venv/bin/python -m ml.synthetic.finalize_v3 --dataset … --run … --out ml/artifacts/synthetic/v3/<scenario>`
  verifies the run bundle reproduces the run's own test predictions (allclose 1e-10),
  forbids truth/label columns in the feature list, and writes a checksummed research
  bundle (model + full engineered feature frame + **separate** ground-truth file +
  events + locations + scenario metadata).
- Backend (read-only, no DB, cannot create alerts):
  `GET /api/synthetic/research/info`, `/frame`, `/storms`, `/series`
  (`backend/app/api/routes/synthetic_research.py`). Ground truth is served only under
  the `ground_truth` key with `research_view_only: true`; the scorer never receives it.
- Frontend: `/research` (`SyntheticResearchPage`) — scenario selector, hourly frame
  table for all 12 monitored locations (simulated weather, provisional probability and
  risk band, evaluation labels), and storm replay with a per-location timeline. Badge:
  **Synthetic Data — Research Demonstration**. The existing `/simulation` page, alert
  demo, notifications and V1 serving are untouched.
- Config: `SYNTHETIC_RESEARCH_DIR` (default `ml/artifacts/synthetic/v3`). V1 continues to
  use `SYNTHETIC_MODEL_DIR` (default `ml/artifacts/synthetic/v1`).

## Foundation-model benchmark (bounded)

Both foundation models were run on the **realistic** scenario only, through the offline
`ml.foundation_worker` contract (label-blind context rows, no query labels, no
downloads). Full training data cannot fit these models' context windows, so results are
a bounded comparison, not full-partition scores (`ml/synthetic/foundation_v3.py`;
outputs in `ml/runs/synthetic-v3/foundation-*-realistic/`). TabPFN was skipped: no
licensed checkpoint is present and the environment is absent.

**The two models ran at different budgets, so they are not comparable to each other.**
For each model the V3 realistic winner (`random_forest_baseline`) is re-scored on that
model's *identical* query rows, which is the only fair comparison. Scores are at the
pre-registered false-alert budget (FP/TP ≤ 1.7857).

| Model | Context / query rows | Query prevalence | Query AP (model vs V3 winner) | Recall @ budget | Precision @ budget | F1 @ budget | Inference |
|---|---|---|---|---|---|---|---|
| TabICL | 4,096 / 4,000 | 0.0103 | **0.573** vs 0.414 | 0.683 | 0.131 | 0.220 | 129 s, RTX 3050 (1.2 GiB) |
| TabFM | 100 / 400 | 0.0075 | 0.750 vs **0.767** | 0.667 | **0.333** | **0.444** | 240 s, CPU |

Reading:

- **TabICL** (4k context) ranks clearly better than the RF on the same 4,000 rows (AP
  0.573 vs 0.414) but converts that into *worse* budgeted precision (0.131 vs 0.157).
- **TabFM** was run at a much smaller budget: its attention cost grows with context
  rows, and the first attempt at 4,096 context / 4,000 query rows was OOM-killed by the
  host (SIGKILL, ~1 GB RSS before the kill, 20 GB free). It was re-run at 100 context /
  400 query rows. On that small slice (3 positive events) it matches the RF on ranking
  (0.750 vs 0.767) and beats it on budgeted precision (0.333 vs 0.094), but the slice is
  far too small and too rare-event-dominated to carry weight.
- Neither result is a promotion argument. Both models see at most a few thousand rows
  against a training partition of ~380k, and the query rows are a slice of the test
  partition, not the partition itself. Foundation tabular models are recorded here as a
  credible research baseline worth keeping in the loop — no more.

## Known issues and caveats

- `features_v2.dry_spell_hours` is scaled ×1e-3 (pandas 3 microsecond epoch quirk). It is
  **deliberately not fixed** because V1 training/serving compatibility depends on it;
  tree models are insensitive to the monotone rescale.
- Episode lead times are ~1 h by construction of the simulator's onset timing; do not
  present them as early-warning capability.
- Thresholds are tuned per scenario on 2024 H1 only; applying a threshold from one
  scenario to another is out-of-distribution behaviour and is labelled as such.
- Stress prevalence is 4× realistic; compare precision only with prevalence and lift.
- All three scenarios share the location registry and generator code; they are not
  independent real-world datasets.
- TabFM at the default 4,096-context budget is host-OOM-killed (SIGKILL, no worker
  stderr). Reproducing it requires `--query-rows 400 --context-rows 100`, and those are
  the only numbers reported here. Do not compare the TabICL and TabFM rows to each
  other.

## Reproduce

```bash
# datasets (fresh directories; outputs refuse overwrite)
backend/.venv/bin/python -m ml.synthetic.generate --start 2021-01-01 --end 2025-06-30 \
  --seed 5101 --scenario controlled --out ml/data/synthetic_fiji/v3/controlled
backend/.venv/bin/python -m ml.synthetic.generate --start 2021-01-01 --end 2025-06-30 \
  --seed 5102 --scenario realistic --out ml/data/synthetic_fiji/v3/realistic
backend/.venv/bin/python -m ml.synthetic.generate --start 2021-01-01 --end 2025-06-30 \
  --seed 5103 --scenario stress --out ml/data/synthetic_fiji/v3/stress

# training (24 CatBoost + 18 LightGBM Optuna trials per scenario, seed 314)
for s in controlled realistic stress; do
  backend/.venv/bin/python -m ml.synthetic.train_v3 \
    --dataset ml/data/synthetic_fiji/v3/$s --out ml/runs/synthetic-v3/$s
done

# publish research bundles (verifies reproducibility and truth separation)
for s in controlled realistic stress; do
  backend/.venv/bin/python -m ml.synthetic.finalize_v3 \
    --dataset ml/data/synthetic_fiji/v3/$s --run ml/runs/synthetic-v3/$s \
    --out ml/artifacts/synthetic/v3/$s
done

# baselines + pre-registered OOD transfer (realistic winner applied unchanged)
backend/.venv/bin/python -m ml.synthetic.transfer_v3

# bounded foundation comparison (optional)
ml/envs/tabicl/bin/python -m ml.synthetic.foundation_v3 --model tabicl \
  --dataset ml/data/synthetic_fiji/v3/realistic --run ml/runs/synthetic-v3/realistic \
  --out ml/runs/synthetic-v3/foundation-tabicl-realistic
# tabfm needs the reduced budget; the 4096-context default is host-OOM-killed
ml/envs/tabfm/bin/python -m ml.synthetic.foundation_v3 --model tabfm \
  --dataset ml/data/synthetic_fiji/v3/realistic --run ml/runs/synthetic-v3/realistic \
  --out ml/runs/synthetic-v3/foundation-tabfm-realistic \
  --query-rows 400 --context-rows 100
```

Tests: `backend/.venv/bin/python -m pytest ml/tests -q` (includes
`test_synthetic_v3.py`) and, for the serving routes,
`cd backend && .venv/bin/python -m pytest tests/test_synthetic_research.py -q`.

## Artefacts (gitignored)

- Datasets: `ml/data/synthetic_fiji/v3/{controlled,realistic,stress}/`
- Runs: `ml/runs/synthetic-v3/{controlled,realistic,stress}/` (metrics, bootstrap,
  per-location tables, predictions, Optuna trials, PR/calibration plots, bundles)
- Foundation: `ml/runs/synthetic-v3/foundation-{tabicl,tabfm}-realistic/`
- Published research bundles: `ml/artifacts/synthetic/v3/{controlled,realistic,stress}/`
