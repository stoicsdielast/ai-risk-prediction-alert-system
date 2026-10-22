# Bangladesh historical flood research report

Research Proof of Concept — Bangladesh historical replay. Not validated for Fiji or operational public warnings. Labels are source-qualified flood-detection proxies, not independently verified ground truth. Probability tiers are provisional presentation thresholds.

## Repository review and scope

The existing five modules remain: dashboard, weather management, prediction, flood map, and alert/testing. The repository implements React/Vite views, JWT/approved-user authentication, SQLAlchemy/PostgreSQL locations and alert approval, plus separate India, weather, river and area prototypes. The new `ml/` benchmark is isolated from these older feature schemas. New historical inference uses approved-user auth and a separate `research_predictions` table. Bangladesh data never enters Fiji location or alert records.

## Dataset integrity, provenance and license

Source: [https://github.com/Srabon-bot/Bangladesh-flood-data-set](https://github.com/Srabon-bot/Bangladesh-flood-data-set/tree/4d6ec74e22a63c1e33012d0f8d106e238dda4e1c). Pinned commit `4d6ec74e22a63c1e33012d0f8d106e238dda4e1c`; path `data/features/2026-08-07c/all_stations.parquet`.

Downloaded bytes: 44,212,305. SHA256: `8d15cd3bcccb7d79895452b2ca54bfbb186b8c607326f372aa9afa6f1c1b6c98`. Dataset, README, station definitions and label-building source were checked against Git blob hashes; the complete Parquet file decoded successfully.

No repository license found; permission to reuse/redistribute is unresolved. Public access is not a license.

Individual reanalysis, GFMS, event archive, and MERIT Hydro terms also require review.

Only the daily classification dataset was downloaded. No regression or spatial data was substituted. Raw data, individual derived records, and binaries are excluded from Git; this does not establish permission for reuse or redistribution.

## Audit and label-quality decision

Shape: 839,340 × 49; 30 stations; 1950-01-01 00:00:00 to 2026-08-07 00:00:00. Full duplicate rows: 0; duplicate station/date keys: 0. Unknown 24h labels: 738,490; source-qualified observed rows: 91,350.

The label code uses detections on t+1 for 24h (and any t+1..t+2/t+3 for the other horizons). It treats absence of a GFMS detection as negative only when the entire future window is in its claimed coverage: 2013-01-01–2016-03-31 or 2021-01-01–2026-02-02. We recheck this next-day condition, keep only `observed` 0/1, and exclude unknown and `unobserved_positive` rows. Unknowns are never converted to 0.

**The requested independently verified non-flood target cannot be established from this source.** This benchmark predicts the dataset's source-qualified proxy label. A zero means no detection under the source coverage rule; a one means a positive source signal, potentially including archive matches. Source coverage and event matching were inspected in code, not independently confirmed against physical gauges or cloud-free daily observations. This qualification also applies to every metric below.

Audit outputs: [dtypes and validation](audit.json), [all label regimes/horizons](label_regimes.csv), [labels by year](labels_by_year.csv), [labels by station](labels_by_station.csv), [missingness by feature](missingness.csv), [missingness by year](missingness_by_year.csv).

Missingness is not evidence of no flood. Raw reanalysis gaps are substantial in early years; screened current values and required histories must be present. Upstream-reference columns with structural missingness, trend ratios, SWI, and soil delta are excluded from this first benchmark. The source README describes terrain differently from the station code: the latter identifies MERIT Hydro for the model's elevation/HAND constants. Approximate virtual-gauge coordinates and mixed source reliability limit geographic interpretation.

## Subset, partitions and leakage controls

After label screening and complete required-feature checks, 91,350 rows were eligible. The smallest SHA256(station_id:date:314) keys select 30,000 rows without consulting targets. Eligible prevalence is 5.305%; subset prevalence is 5.240%. No target-based balancing, oversampling or prevalence adjustment occurs in validation/test.

| Partition | Rows | Positives | Natural sampled prevalence |
|---|---:|---:|---:|
| excluded | 4,616 | 217 | 4.701% |
| holdout_station | 1,520 | 46 | 3.026% |
| test | 6,025 | 281 | 4.664% |
| train | 12,049 | 707 | 5.868% |
| validation | 5,790 | 321 | 5.544% |

Training ends before 2021-12-29; validation runs 2022-01-01 through 2023-12-28; chronological test begins 2024-01-01. Three excluded days before each boundary exceed the 24h target window and cover the longest supplied 72h horizon. Historical rolling windows may use already observed past days across a boundary; no future labels or future measurements enter features. Source daily time-zone/release latency is unknown, so UTC end-of-day is a replay convention only.

Held-out station IDs, predeclared across basins: SW90, TE01, GA01, SW174, CH01, CO01. No rows from these stations fit preprocessing, classification or KMeans, or select hyperparameters/thresholds. Only their dates from 2024 onward are evaluated. Earlier holdout rows and embargo rows remain in the 30k manifest marked excluded. The station split does not make nearby reanalysis grids independent; stronger basin/event holdouts remain future work.

Each input is explicitly allowlisted. Within-station histories are reconstructed from raw current/past measurements on the complete daily series before screening/sampling. All `flood_byStor` variants, horizons, label regimes, future discharge targets, IDs/names and date fields are excluded from X. Latitude/longitude describe source geography; they are static and can encode regional differences, so station holdout is reported separately.

| Feature | Availability at replay origin and units |
|---|---|
| `rainfall_local_mm` | Closed feature-day rainfall total, mm; retrospective reanalysis, live latency unverified |
| `rainfall_upstream_mm` | Closed feature-day rainfall total, mm; retrospective reanalysis, live latency unverified |
| `soil_moisture_local` | Closed feature-day reanalysis volumetric soil-water fraction; live latency unverified |
| `river_discharge_m3s` | Closed feature-day GloFAS modelled discharge, m³/s; live latency unverified |
| `rainfall_local_mm_lag1d` | Measurement from the named prior day within this station; same units as base |
| `rainfall_local_mm_lag2d` | Measurement from the named prior day within this station; same units as base |
| `rainfall_local_mm_lag3d` | Measurement from the named prior day within this station; same units as base |
| `rainfall_local_mm_lag5d` | Measurement from the named prior day within this station; same units as base |
| `rainfall_upstream_mm_lag1d` | Measurement from the named prior day within this station; same units as base |
| `rainfall_upstream_mm_lag2d` | Measurement from the named prior day within this station; same units as base |
| `rainfall_upstream_mm_lag3d` | Measurement from the named prior day within this station; same units as base |
| `rainfall_upstream_mm_lag5d` | Measurement from the named prior day within this station; same units as base |
| `soil_moisture_local_lag1d` | Measurement from the named prior day within this station; same units as base |
| `soil_moisture_local_lag2d` | Measurement from the named prior day within this station; same units as base |
| `soil_moisture_local_lag3d` | Measurement from the named prior day within this station; same units as base |
| `soil_moisture_local_lag5d` | Measurement from the named prior day within this station; same units as base |
| `river_discharge_m3s_lag1d` | Measurement from the named prior day within this station; same units as base |
| `river_discharge_m3s_lag2d` | Measurement from the named prior day within this station; same units as base |
| `river_discharge_m3s_lag3d` | Measurement from the named prior day within this station; same units as base |
| `river_discharge_m3s_lag5d` | Measurement from the named prior day within this station; same units as base |
| `rainfall_local_mm_sum7d` | Trailing inclusive rainfall sum over 7/14 complete days, mm |
| `rainfall_local_mm_sum14d` | Trailing inclusive rainfall sum over 7/14 complete days, mm |
| `rainfall_upstream_mm_sum7d` | Trailing inclusive rainfall sum over 7/14 complete days, mm |
| `rainfall_upstream_mm_sum14d` | Trailing inclusive rainfall sum over 7/14 complete days, mm |
| `river_discharge_m3s_mean7d` | Trailing inclusive discharge mean over 7/14 complete days, m³/s |
| `river_discharge_m3s_mean14d` | Trailing inclusive discharge mean over 7/14 complete days, m³/s |
| `elevation_m` | Static source terrain, metres; geographic transfer unverified |
| `hand_m` | Static source terrain, metres; geographic transfer unverified |
| `latitude` | Static approximate source station coordinate, degrees; validated against registry |
| `longitude` | Static approximate source station coordinate, degrees; validated against registry |

## Classifier comparison and calibration

Median imputation and scaling are fitted on training only; required inputs are nevertheless complete at serving time. The predeclared small search compares logistic class_weight None/balanced, RF depths 6/12, LightGBM leaves 7/15 and CatBoost depths 4/6. Training-only class weighting competes without weighting validation/test. Hyperparameters and the winner use validation average precision (reported PR-AUC); the binary threshold maximizes validation F1. Pipelines are not refitted on validation. After choices are frozen, each model is evaluated on test and station holdout. No accuracy target, post-test calibration or test-driven retuning is used.

| Model | Validation AP | Test precision | Recall | F1 | PR-AUC (AP) | ROC-AUC | Brier |
|---|---:|---:|---:|---:|---:|---:|---:|
| logistic_regression | 0.3195 | 0.3590 | 0.4484 | 0.3987 | 0.3701 | 0.8945 | 0.1419 |
| random_forest | 0.2942 | 0.2671 | 0.6121 | 0.3719 | 0.3161 | 0.8970 | 0.0373 |
| lightgbm | 0.2840 | 0.2329 | 0.6299 | 0.3401 | 0.3345 | 0.8931 | 0.0370 |
| catboost | 0.3148 | 0.2629 | 0.5445 | 0.3546 | 0.3282 | 0.8977 | 0.0368 |

Validation selected **logistic_regression**, parameters `{'class_weight': 'balanced'}`, binary threshold **0.866584**. Confusion matrix [TN, FP, FN, TP]: [5519, 225, 155, 126].

On unseen stations: precision 0.2203, recall 0.2826, F1 0.2476, AP 0.2351, ROC-AUC 0.8604, Brier 0.1241; confusion matrix [1428, 46, 33, 13].

The selected class-weighted logistic model ranks examples reasonably but has **poor probability calibration**: test Brier 0.1419, compared with 0.0446 for always predicting the training prevalence. Its near-1 outputs must not be interpreted as near-certain real floods. Selection was fixed by AP, so the model was not swapped after seeing calibration/test results. Calibration or a different selection objective requires a new predeclared study and fresh evaluation data.

All metrics and search candidates are in [evaluation.json](evaluation.json); per-station metrics are in [test](metrics_per_station_test.json) and [unseen-station](metrics_per_station_holdout_station.json) files. Single-class stations have null AUCs with an explanation. Daily/event correlation prevents treating row counts as independent sample counts. No independent-event uncertainty interval is claimed.

![PR curves, confusion matrix and reliability](performance.png)

## Unsupervised weather patterns

KMeans uses training-only median/scaling and weather/hydrological inputs. k=2,3,4,5 compete on training silhouette; selected k=3. The saved model assigns the same clusters to held-out dates/stations without refitting. Counts, profiles and individual assignments are saved. Cluster IDs are arbitrary; neither flood labels nor class thresholds are used in fitting or naming them.

- Cluster 0: soil_moisture_local: above training mean (1.05 SD); rainfall_upstream_mm_sum14d: above training mean (1.00 SD); rainfall_local_mm_sum7d: above training mean (0.99 SD).
- Cluster 1: rainfall_upstream_mm_sum14d: below training mean (-0.62 SD); soil_moisture_local: below training mean (-0.61 SD); rainfall_local_mm_sum7d: below training mean (-0.52 SD).
- Cluster 2: river_discharge_m3s_mean7d: above training mean (2.84 SD); river_discharge_m3s: above training mean (2.83 SD); rainfall_upstream_mm_sum14d: above training mean (1.08 SD).

![Cluster count comparison and weather centroids](clustering.png)

## Advanced model status

TabFM was not benchmarked and has no reported score. The optional experiment requires a separate compatible environment, a bounded training-only context (upstream defaults to 100 rows), fixed resource limits, and separate pretrained-weight license review. [Upstream TabFM](https://github.com/google-research/tabfm) distinguishes its Apache-2.0 code from default non-commercial/non-production weights. No weights were downloaded and no operational use is enabled. TimesFM was not used for classification.

## Integration, demonstration and outstanding issues

The API returns probability, provisional tier, 24h horizon, model version, replay timestamp, source and research_mode. Approved users can persist runs; missing artifacts/history return data_unavailable with no invented measurements/probability. Model-info and held-out examples are read-only. Request features exclude labels/expected outputs. Browser alerts need an explicit permission click and a separate demo-alert action; internal alerts also require an explicit click. Neither action writes public emergency alerts. A dedicated Bangladesh map is embedded beside the preserved Fiji map and dashboards.

Replay examples are the held-out test minimum/maximum model score, chosen only after evaluation. They are cherry-picked UI demonstrations, not representative performance evidence. Exact dates, stations, provenance and selection rule are retained in local replay artifacts.

Outstanding: independently verified negative labels; source/weight licensing clearance; source release/time-zone validation; event/basin independence and uncertainty; probability calibration; official Fiji MET data and prospective Fiji validation. The optional TabFM experiment remains unrun. PostgreSQL deployment and a real-browser notification demonstration require the local operator environment; automated API tests use isolated SQLite. No public warnings were sent.

See [reproduction and API instructions](../../docs/RESEARCH_BANGLADESH.md).

## Executed verification

| Check | Result |
|---|---|
| Pinned dataset and provenance | Git blob hashes, SHA256 and full Parquet decode passed |
| ML validation/leakage/training smoke | 7 passed |
| Backend and legacy AI | 323 passed; 6 PostgreSQL migration checks skipped |
| Frontend | 59 passed |
| Frontend production build | passed |
| Frontend lint | passed with no warnings |
| Independent training reproduction | identical subset, classifier, thresholds, clustering and evaluation metrics |
| Real artifact inference | API probabilities match both held-out examples |
| Git diff whitespace check | passed |

The six skipped PostgreSQL migration checks need TEST_DATABASE_URL. API behavior and persistence were tested on isolated SQLite, including real saved-artifact inference. The independent reproduction produced byte-identical subset, classifier, thresholds and clustering results and identical evaluation metrics (wall time excluded); see [reproduction checks](reproducibility.json).
