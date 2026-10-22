"""Render the frozen run's measured results without fitting or selecting anything."""
import argparse
import json
from pathlib import Path

import pandas as pd

from ml.config import ARTIFACTS, DISCLAIMER, FEATURES


def render(directory=ARTIFACTS):
    directory = Path(directory)
    read = lambda name: json.loads((directory / name).read_text())
    audit, evaluation, metadata = read("audit.json"), read("evaluation.json"), read("model_metadata.json")
    provenance, sampling, clusters = read("provenance.json"), read("sampling.json"), read("clustering.json")
    winner = evaluation["selected_by_validation_ap"]
    selected = evaluation["candidates"][winner]
    lines = ["# Bangladesh historical flood research report", "", DISCLAIMER, "",
             "## Repository review and scope", "",
             "The existing five modules remain: dashboard, weather management, prediction, flood map, and alert/testing. "
             "The repository implements React/Vite views, JWT/approved-user authentication, SQLAlchemy/PostgreSQL locations and alert approval, "
             "plus separate India, weather, river and area prototypes. The new `ml/` benchmark is isolated from these older feature schemas. "
             "New historical inference uses approved-user auth and a separate `research_predictions` table. Bangladesh data never enters Fiji location or alert records.", "",
             "## Dataset integrity, provenance and license", "",
             f"Source: [{provenance['repository']}]({provenance['repository']}/tree/{provenance['commit']}). "
             f"Pinned commit `{provenance['commit']}`; path `{provenance['path']}`.", "",
             f"Downloaded bytes: {provenance['files']['all_stations.parquet']['bytes']:,}. SHA256: `{provenance['files']['all_stations.parquet']['sha256']}`. "
             "Dataset, README, station definitions and label-building source were checked against Git blob hashes; the complete Parquet file decoded successfully.", "",
             provenance["license_status"], "", provenance["upstream_terms"], "",
             "Only the daily classification dataset was downloaded. No regression or spatial data was substituted. "
             "Raw data, individual derived records, and binaries are excluded from Git; this does not establish permission for reuse or redistribution.", "",
             "## Audit and label-quality decision", "",
             f"Shape: {audit['shape'][0]:,} × {audit['shape'][1]}; {audit['stations']} stations; {audit['date_start']} to {audit['date_end']}. "
             f"Full duplicate rows: {audit['duplicate_rows']}; duplicate station/date keys: {audit['duplicate_station_dates']}. "
             f"Unknown 24h labels: {audit['unknown_24h']:,}; source-qualified observed rows: {audit['screened_label_rows']:,}.", "",
             "The label code uses detections on t+1 for 24h (and any t+1..t+2/t+3 for the other horizons). "
             "It treats absence of a GFMS detection as negative only when the entire future window is in its claimed coverage: "
             "2013-01-01–2016-03-31 or 2021-01-01–2026-02-02. We recheck this next-day condition, keep only `observed` 0/1, "
             "and exclude unknown and `unobserved_positive` rows. Unknowns are never converted to 0.", "",
             "**The requested independently verified non-flood target cannot be established from this source.** "
             "This benchmark predicts the dataset's source-qualified proxy label. A zero means no detection under the source coverage rule; "
             "a one means a positive source signal, potentially including archive matches. Source coverage and event matching were inspected in code, "
             "not independently confirmed against physical gauges or cloud-free daily observations. This qualification also applies to every metric below.", "",
             "Audit outputs: [dtypes and validation](audit.json), [all label regimes/horizons](label_regimes.csv), "
             "[labels by year](labels_by_year.csv), [labels by station](labels_by_station.csv), "
             "[missingness by feature](missingness.csv), [missingness by year](missingness_by_year.csv).", "",
             "Missingness is not evidence of no flood. Raw reanalysis gaps are substantial in early years; screened current values and required histories must be present. "
             "Upstream-reference columns with structural missingness, trend ratios, SWI, and soil delta are excluded from this first benchmark. "
             "The source README describes terrain differently from the station code: the latter identifies MERIT Hydro for the model's elevation/HAND constants. "
             "Approximate virtual-gauge coordinates and mixed source reliability limit geographic interpretation.", "",
             "## Subset, partitions and leakage controls", "",
             f"After label screening and complete required-feature checks, {sampling['eligible_rows']:,} rows were eligible. "
             f"The smallest SHA256(station_id:date:314) keys select {sampling['subset_rows']:,} rows without consulting targets. "
             f"Eligible prevalence is {sampling['screened_prevalence']:.3%}; subset prevalence is {sampling['subset_prevalence']:.3%}. "
             "No target-based balancing, oversampling or prevalence adjustment occurs in validation/test.", "",
             "| Partition | Rows | Positives | Natural sampled prevalence |", "|---|---:|---:|---:|"]
    for part, row in pd.read_csv(directory / "partition_summary.csv", index_col=0).iterrows():
        lines.append(f"| {part} | {int(row['count']):,} | {int(row['sum']):,} | {row['mean']:.3%} |")
    lines += ["", "Training ends before 2021-12-29; validation runs 2022-01-01 through 2023-12-28; "
              "chronological test begins 2024-01-01. Three excluded days before each boundary exceed the 24h target window and "
              "cover the longest supplied 72h horizon. Historical rolling windows may use already observed past days across a boundary; "
              "no future labels or future measurements enter features. Source daily time-zone/release latency is unknown, so UTC end-of-day is a replay convention only.", "",
              f"Held-out station IDs, predeclared across basins: {', '.join(sampling['holdout_stations'])}. "
              "No rows from these stations fit preprocessing, classification or KMeans, or select hyperparameters/thresholds. "
              "Only their dates from 2024 onward are evaluated. Earlier holdout rows and embargo rows remain in the 30k manifest marked excluded. "
              "The station split does not make nearby reanalysis grids independent; stronger basin/event holdouts remain future work.", "",
              "Each input is explicitly allowlisted. Within-station histories are reconstructed from raw current/past measurements on the complete daily series "
              "before screening/sampling. All `flood_byStor` variants, horizons, label regimes, future discharge targets, IDs/names and date fields are excluded from X. "
              "Latitude/longitude describe source geography; they are static and can encode regional differences, so station holdout is reported separately.", "",
              "| Feature | Availability at replay origin and units |", "|---|---|"]
    for feature in FEATURES:
        if feature in ("latitude", "longitude"): availability = "Static approximate source station coordinate, degrees; validated against registry"
        elif feature in ("elevation_m", "hand_m"): availability = "Static source terrain, metres; geographic transfer unverified"
        elif "_lag" in feature: availability = "Measurement from the named prior day within this station; same units as base"
        elif "_sum" in feature: availability = "Trailing inclusive rainfall sum over 7/14 complete days, mm"
        elif "_mean" in feature: availability = "Trailing inclusive discharge mean over 7/14 complete days, m³/s"
        elif feature.startswith("rainfall"): availability = "Closed feature-day rainfall total, mm; retrospective reanalysis, live latency unverified"
        elif feature.startswith("soil"): availability = "Closed feature-day reanalysis volumetric soil-water fraction; live latency unverified"
        else: availability = "Closed feature-day GloFAS modelled discharge, m³/s; live latency unverified"
        lines.append(f"| `{feature}` | {availability} |")
    lines += ["", "## Classifier comparison and calibration", "",
              "Median imputation and scaling are fitted on training only; required inputs are nevertheless complete at serving time. "
              "The predeclared small search compares logistic class_weight None/balanced, RF depths 6/12, LightGBM leaves 7/15 and CatBoost depths 4/6. "
              "Training-only class weighting competes without weighting validation/test. Hyperparameters and the winner use validation average precision (reported PR-AUC); "
              "the binary threshold maximizes validation F1. Pipelines are not refitted on validation. After choices are frozen, each model is evaluated on test and station holdout. "
              "No accuracy target, post-test calibration or test-driven retuning is used.", "",
              "| Model | Validation AP | Test precision | Recall | F1 | PR-AUC (AP) | ROC-AUC | Brier |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, values in evaluation["candidates"].items():
        m = values["test"]
        lines.append(f"| {name} | {values['validation']['pr_auc_average_precision']:.4f} | {m['precision']:.4f} | {m['recall']:.4f} | {m['f1']:.4f} | {m['pr_auc_average_precision']:.4f} | {m['roc_auc']:.4f} | {m['brier']:.4f} |")
    train_prevalence = selected["train"]["prevalence"]
    test_prevalence = selected["test"]["prevalence"]
    constant_brier = test_prevalence * (1 - train_prevalence)**2 + (1 - test_prevalence) * train_prevalence**2
    held = selected["holdout_station"]
    lines += ["", f"Validation selected **{winner}**, parameters `{selected['parameters']}`, binary threshold **{selected['threshold']:.6f}**. "
              f"Confusion matrix [TN, FP, FN, TP]: {selected['test']['confusion_matrix_tn_fp_fn_tp']}.", "",
              f"On unseen stations: precision {held['precision']:.4f}, recall {held['recall']:.4f}, F1 {held['f1']:.4f}, "
              f"AP {held['pr_auc_average_precision']:.4f}, ROC-AUC {held['roc_auc']:.4f}, Brier {held['brier']:.4f}; "
              f"confusion matrix {held['confusion_matrix_tn_fp_fn_tp']}.", "",
              f"The selected class-weighted logistic model ranks examples reasonably but has **poor probability calibration**: "
              f"test Brier {selected['test']['brier']:.4f}, compared with {constant_brier:.4f} for always predicting the training prevalence. "
              "Its near-1 outputs must not be interpreted as near-certain real floods. Selection was fixed by AP, so the model was not swapped after seeing calibration/test results. "
              "Calibration or a different selection objective requires a new predeclared study and fresh evaluation data.", "",
              "All metrics and search candidates are in [evaluation.json](evaluation.json); per-station metrics are in "
              "[test](metrics_per_station_test.json) and [unseen-station](metrics_per_station_holdout_station.json) files. "
              "Single-class stations have null AUCs with an explanation. Daily/event correlation prevents treating row counts as independent sample counts. "
              "No independent-event uncertainty interval is claimed.", "",
              "![PR curves, confusion matrix and reliability](performance.png)", "",
              "## Unsupervised weather patterns", "",
              f"KMeans uses training-only median/scaling and weather/hydrological inputs. k=2,3,4,5 compete on training silhouette; selected k={clusters['selected_k']}. "
              "The saved model assigns the same clusters to held-out dates/stations without refitting. Counts, profiles and individual assignments are saved. "
              "Cluster IDs are arbitrary; neither flood labels nor class thresholds are used in fitting or naming them.", ""]
    for key, descriptions in clusters["weather_patterns"].items(): lines.append(f"- Cluster {key}: " + "; ".join(descriptions) + ".")
    lines += ["", "![Cluster count comparison and weather centroids](clustering.png)", "",
              "## Advanced model status", "",
              "TabFM was not benchmarked and has no reported score. The optional experiment requires a separate compatible environment, "
              "a bounded training-only context (upstream defaults to 100 rows), fixed resource limits, and separate pretrained-weight license review. "
              "[Upstream TabFM](https://github.com/google-research/tabfm) distinguishes its Apache-2.0 code from default non-commercial/non-production weights. "
              "No weights were downloaded and no operational use is enabled. TimesFM was not used for classification.", "",
              "## Integration, demonstration and outstanding issues", "",
              "The API returns probability, provisional tier, 24h horizon, model version, replay timestamp, source and research_mode. "
              "Approved users can persist runs; missing artifacts/history return data_unavailable with no invented measurements/probability. "
              "Model-info and held-out examples are read-only. Request features exclude labels/expected outputs. "
              "Browser alerts need an explicit permission click and a separate demo-alert action; internal alerts also require an explicit click. "
              "Neither action writes public emergency alerts. A dedicated Bangladesh map is embedded beside the preserved Fiji map and dashboards.", "",
              "Replay examples are the held-out test minimum/maximum model score, chosen only after evaluation. They are cherry-picked UI demonstrations, "
              "not representative performance evidence. Exact dates, stations, provenance and selection rule are retained in local replay artifacts.", "",
              "Outstanding: independently verified negative labels; source/weight licensing clearance; source release/time-zone validation; "
              "event/basin independence and uncertainty; probability calibration; official Fiji MET data and prospective Fiji validation. "
              "The optional TabFM experiment remains unrun. PostgreSQL deployment and a real-browser notification demonstration require the local operator environment; "
              "automated API tests use isolated SQLite. No public warnings were sent.", "",
              "See [reproduction and API instructions](../../docs/RESEARCH_BANGLADESH.md).", ""]
    verification_path = directory / "verification.json"
    if verification_path.exists():
        verification = read("verification.json")
        lines += ["## Executed verification", "", "| Check | Result |", "|---|---|"]
        for check, result in verification["checks"].items():
            lines.append(f"| {check} | {result} |")
        lines += ["", "The six skipped PostgreSQL migration checks need TEST_DATABASE_URL. "
                  "API behavior and persistence were tested on isolated SQLite, including real saved-artifact inference. "
                  "The independent reproduction produced byte-identical subset, classifier, thresholds and clustering results "
                  "and identical evaluation metrics (wall time excluded); see [reproduction checks](reproducibility.json).", ""]
    (directory / "technical_report.md").write_text("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ARTIFACTS)
    render(parser.parse_args().out)
