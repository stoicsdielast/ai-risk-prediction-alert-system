"""Read-only report for the completed training-02 experiment."""
import json
from pathlib import Path

import pandas as pd

from ml.config import DISCLAIMER


def markdown_table(frame, columns):
    result = ["| " + " | ".join(columns) + " |", "|" + "|".join(["---"] * len(columns)) + "|"]
    for _, row in frame.iterrows():
        values = []
        for column in columns:
            value = row[column]
            values.append("N/A" if pd.isna(value) else f"{value:.4f}" if isinstance(value, float) else str(value))
        result.append("| " + " | ".join(values) + " |")
    return result


def render(out):
    out = Path(out)
    read = lambda name: json.loads((out / name).read_text())
    plan, selection, threshold = read("plan.json"), read("selection_lock.json"), read("thresholds.json")
    evaluation = pd.read_csv(out / "evaluation_table.csv")
    development = pd.read_csv(out / "development_metrics.csv")
    summary = pd.read_csv(out / "partition_summary.csv")
    selected_id = selection["model_id"]
    test = evaluation[evaluation.stage.eq("test")].set_index("policy")
    old, new = test.loc["original_baseline"], test.loc["selected_recall_budget"]
    station = evaluation[evaluation.stage.eq("holdout_station")].set_index("policy")
    paired = development[development.model_id.str.startswith("fixed_C1__baseline") & development.stage.eq("selection")]
    models = read("candidate_models.json")
    feature_comparison = development[development.stage.eq("selection")].copy()
    for field in ["family", "feature_set", "balanced", "method"]:
        feature_comparison[field] = feature_comparison.model_id.map(lambda key: models[key][field])
    feature_comparison = feature_comparison.sort_values("brier").groupby(["family", "feature_set", "balanced"], as_index=False).first()
    feature_comparison.to_csv(out / "feature_set_comparison.csv", index=False)
    incidence = pd.read_csv(out / "cluster_incidence.csv")
    cluster_profiles = pd.read_csv(out / "cluster_weather_profiles.csv")
    domain_rows = []
    for policy in test.index:
        domain_rows.append({"policy": policy, **{key + "_spatial_minus_temporal": float(station.loc[policy, key] - test.loc[policy, key])
                            for key in ["precision", "recall", "f1", "pr_auc_average_precision", "roc_auc", "brier"]}})
    pd.DataFrame(domain_rows).to_csv(out / "spatial_generalization_differences.csv", index=False)
    lines = ["# training-02: calibration, recall tradeoffs and spatial generalization", "", DISCLAIMER, "",
        "## Read this result correctly", "",
        "training-01 was read and preserved byte for byte. The same original 30k selection keys and final temporal/station evaluation rows are used for paired comparisons. "
        "No final-test or held-out-station record fits preprocessing, classifiers, calibrators, thresholds or KMeans. " + plan["reuse_caveat"], "",
        "The old validation period was also previously used by training-01 for selection and thresholding. "
        "Dividing it into new internal roles does not make it historically unused data; this study's stages are disjoint within training-02 only.", "",
        f"**Outcome:** temporal Brier {old.brier:.4f} → {new.brier:.4f}, recall {old.recall:.4f} → {new.recall:.4f}, "
        f"F1 {old.f1:.4f} → {new.f1:.4f}; unseen-station AP {station.loc['original_baseline', 'pr_auc_average_precision']:.4f} → "
        f"{station.loc['selected_recall_budget', 'pr_auc_average_precision']:.4f}. "
        "Calibration improved substantially, but recall/F1 and spatial AP declined. This is not an overall improvement or a deployment recommendation.", "",
        "This study improves the research workflow; it cannot turn proxy labels into verified non-flood truth or establish live Fiji forecasting. "
        "No server setting or production artifact pointer is changed, and no emergency notification is activated.", "",
        "## Audit and staged design", "",
        "The saved classifier SHA256, all baseline files and pinned source checksums were verified before work. Label filtering, raw duplicate checks, daily completeness, "
        "station membership, original feature reconstruction, overlapping forecast windows and extra-feature missingness were checked. "
        "The original `observed`-only screen is retained; unknown and positive-only regimes are excluded. Source coverage does not independently prove physical absence of flood. "
        "There was no observed answer-derived feature in the explicit X allowlist. Reanalysis publication times and source time-zone alignment remain unverified.", "",
        "Training retains original pre-2022 rows. Original validation is divided into four chronological blocks, each separated by a three-day embargo: "
        "2022 H1 tuning, 2022 H2 calibration, 2023 H1 model/calibration selection, 2023 H2 threshold selection. "
        "The six predeclared stations remain absent from every development stage. Original evaluation starts in 2024. "
        "Past-only rainfall/discharge histories can cross a split boundary; target windows cannot. Three days exceed the 24h target's overlap and cover the source's longest 72h horizon.", ""]
    lines += markdown_table(summary, ["stage", "rows", "positives", "prevalence"])
    lines += ["", "**Seasonality and sample size:** 2023 H1 model selection has only 31 proxy-positive rows and 2022 H2 calibration has 95. "
        "Half-year blocks differ strongly in monsoon prevalence. Sigmoid/isotonic estimates and winner choice can therefore be unstable. "
        "No row-independent confidence interval is claimed; adjacent days, overlapping histories and nearby virtual gauges share events/grids. "
        "A future study needs full-season rolling-origin development, independent events/basins and fresh prospective test data. "
        "These limitations were identified in the split audit, not fixed using final-test outcomes.", "",
        "See [split audit](split_audit.json), [source audit](audit/audit.json), [feature availability/ranges](feature_audit.csv), "
        "[partition plan](plan.json) and the local row manifest.", "",
        "## Feature evaluation and controlled model search", "",
        "Two feature sets compete without changing record selection: original 30 inputs and 38 hydrology inputs. "
        "The latter adds local/upstream trailing 72h rainfall totals, a 3-day discharge mean, signed discharge changes over 1/3/7 days, "
        "a relative 3-day discharge change (denominator bounded below by 1 m³/s) and a signed 7-day soil-water change. "
        "The source daily rain is the 24h total; original 7-day sums are the 7-day totals. "
        "Soil moisture, elevation, HAND, upstream rain, lags and approximate location coordinates remain available. "
        "All rolling calculations require full windows within the same station, include only current/earlier closed days, and are rebuilt before sampling. "
        "This establishes offline temporal causality, not real-time availability.", "",
        "A predeclared 28-configuration search compares C=.1/1/10 logistic regression, two regularized LightGBM configurations and two regularized CatBoost configurations, "
        "on both feature sets, with unweighted/balanced training. Hyperparameters use only tuning AP. No validation/evaluation oversampling or weighting occurs. "
        "The best base model in each family/feature/weight group is frozen. Sigmoid and isotonic calibrators fit only calibration rows; no base estimator is refitted. "
        "C=1 paired logistic models on identical original features are also preserved for a direct weight comparison.", "",
        "Candidate/calibration selection minimizes 2023 H1 Brier while retaining at least 95% of original baseline AP on that same validation block. "
        "The 5% AP tolerance is a declared research ranking guard, not a safety criterion. The test does not select candidates. "
        "[All search results](hyperparameter_search.csv), [all train/validation metrics](development_metrics.csv), "
        "[selection comparison](selection_metrics.csv) and [fitted candidate specifications](candidate_models.json) are retained.", "",
        "Train metrics are in-sample; calibrator metrics on the calibration block are also in-sample for calibrated candidates. "
        "Tuning metrics participated in hyperparameter selection. The separately identified selection/threshold blocks supply the within-study validation comparisons.", "",
        "Paired C=1 logistic calibration comparison on model-selection validation:", ""]
    lines += markdown_table(paired, ["model_id", "brier", "mean_probability", "pr_auc_average_precision", "ece_equal_width_10_bins"])
    lines += ["", "Validation feature-set comparison (minimum Brier within each family/feature/weight group; descriptive and not a second final-test search):", ""]
    lines += markdown_table(feature_comparison, ["family", "feature_set", "balanced", "method", "brier", "pr_auc_average_precision"])
    lines += ["", f"Selected pipeline: **{selected_id}**.", "",
        "![Validation PR, reliability and score distributions](validation_pr_calibration.png)", "",
        "## Recall policy and false-alert cost", "",
        "The user chose the original baseline's false-alerts-per-detection budget. Its old threshold is applied to the 2023 H2 threshold block, "
        "then the selected pipeline's threshold maximizes recall subject to FP/TP no larger than that budget. "
        "No target recall was forced. Ties favor fewer false positives, then the higher threshold. "
        "This is an empirical validation constraint; it cannot guarantee the same budget under future distribution shift, nor does a ratio cap absolute FP volume.", "",
        f"Validation budget: **{threshold['false_alerts_per_detection_budget']:.4f} false alerts per detected proxy flood**. "
        f"Selected threshold: **{threshold['binary_threshold']:.6f}**; original threshold **{threshold['original_baseline_threshold']:.6f}**. "
        "F1-optimal and default .5 policies are reported as comparisons. A separate original-model threshold-only change isolates the effect of changing the operating point. "
        "Cost ratios 1:1, 2:1, 5:1 and 10:1 are exploratory sensitivity scenarios, not alternative model-selection rules.", "",
        f"On threshold validation, original recall was {threshold['baseline_validation']['recall']:.4f}; selected feasible recall was "
        f"{threshold['selected_validation_operating_point']['recall']:.4f}. Original TP/FP were "
        f"{threshold['baseline_validation']['confusion_matrix_tn_fp_fn_tp'][3]}/{threshold['baseline_validation']['confusion_matrix_tn_fp_fn_tp'][1]}; "
        f"selected TP/FP were {int(threshold['selected_validation_operating_point']['tp'])}/{int(threshold['selected_validation_operating_point']['fp'])}. "
        "The selected model did not improve validation recall within the budget; this was retained and disclosed, rather than forcing a target.", "",
        "![Validation precision/recall and false-alert tradeoffs](validation_threshold_tradeoffs.png)", "",
        "See [every validation operating point](threshold_tradeoffs.csv), [selected policy](thresholds.json) and [cost sensitivity](cost_sensitivity.json).", "",
        "## Frozen temporal evaluation", ""]
    lines += markdown_table(test.reset_index(), ["policy", "threshold", "precision", "recall", "f1", "pr_auc_average_precision", "roc_auc", "brier", "false_alerts_per_detection", "false_alerts_per_1000"])
    improvements = []
    for key in ["precision", "recall", "f1", "pr_auc_average_precision", "roc_auc", "brier"]:
        delta = float(new[key] - old[key])
        better = delta < 0 if key == "brier" else delta > 0
        improvements.append(f"{key}: {old[key]:.4f} → {new[key]:.4f} ({'improved' if better else 'unchanged' if abs(delta) < 1e-12 else 'degraded'}, Δ={delta:+.4f})")
    lines += [""] + ["- " + value for value in improvements]
    train_prevalence = float(evaluation.loc[(evaluation.policy.eq("original_baseline")) & evaluation.stage.eq("train"), "prevalence"].iloc[0])
    prevalence = float(old.prevalence)
    constant_brier = prevalence*(1-train_prevalence)**2 + (1-prevalence)*train_prevalence**2
    lines += ["", f"Training-prevalence constant Brier reference on the same temporal rows: **{constant_brier:.4f}**; "
        f"original weighted-model Brier **{old.brier:.4f}**; selected Brier **{new.brier:.4f}**. "
        "Brier is the mean squared probability error, rather than a threshold accuracy metric. "
        "Class weighting changes the fitted effective prior; unweighted logistic and disjoint calibrators may correct its overconfident scores. "
        "Reliability bins, log loss, ECE and mean predicted probability accompany Brier. Calibration remains an empirical description of proxy-label frequencies, not physical flood certainty.", "",
        f"Original [TN, FP, FN, TP]: {old.confusion_matrix_tn_fp_fn_tp}. Selected: {new.confusion_matrix_tn_fp_fn_tp}.", "",
        "## Entire station holdout", ""]
    lines += markdown_table(station.reset_index(), ["policy", "precision", "recall", "f1", "pr_auc_average_precision", "roc_auc", "brier", "false_alerts_per_detection"])
    lines += ["", "Held-out stations: " + ", ".join(read("split_audit.json")["entirely_held_out_stations"]) + ". "
        "[Per-station metrics](per_station_metrics.csv) and [paired station differences](per_station_differences.csv) expose local degradation as well as gains. "
        "Single-class station AUCs are null. The original baseline reproduced its exact original evaluation on the same temporal and spatial records. "
        "[Spatial-minus-temporal differences](spatial_generalization_differences.csv) quantify the domain drop for each policy. "
        "Unseen-station performance is not evidence of independent-basin or Fiji transfer.", "",
        "![Final PR, calibration and selected confusion matrices](final_comparison.png)", "",
        "## Feature importance and weather clusters", "",
        "[Permutation importance](validation_permutation_importance.csv) uses only model-selection validation, with five repeats. "
        "[Native coefficients/importances](native_feature_importance.csv) come from the selected base estimator; they do not explain a calibrator as an independent physical model. "
        "Correlated lag/rolling features can share importance, and coefficients are not causal effects.", "",
        "![Selection-validation feature importance](feature_importance.png)", "",
        "KMeans compares k=2..6 on training-only silhouette, after log1p and standardization of nonnegative weather/hydrology inputs. "
        "No target enters scaling, k selection or fitting. Held-out records get assignments from the frozen model. "
        "Source proxy incidence is then summarized by cluster and partition, after final evaluation has been locked. "
        "[Weather profiles](cluster_weather_profiles.csv) describe physical patterns; [cluster incidence](cluster_incidence.csv) is post-hoc association, "
        "not verified flood-risk categories. HDBSCAN remains optional and was not run.", "",
        "Training weather profiles:", ""]
    lines += markdown_table(cluster_profiles, ["cluster", "rainfall_local_mm", "rainfall_upstream_mm", "soil_moisture_local", "river_discharge_m3s"])
    lines += ["", "Proxy-label incidence by cluster:", ""]
    lines += markdown_table(incidence[incidence.stage.isin(["train", "test", "holdout_station"])], ["stage", "cluster", "rows", "positives", "incidence"])
    wetter = cluster_profiles.sort_values("rainfall_local_mm").iloc[-1]
    drier = cluster_profiles.sort_values("rainfall_local_mm").iloc[0]
    lines += ["", f"Cluster {int(wetter.cluster)} has wetter soil, greater rainfall and higher discharge in the training means than cluster {int(drier.cluster)}. "
        "Its proxy-positive incidence is higher across the reported partitions. This association can reflect season, source coverage and shared grids; "
        "it is not a calibrated probability or proof of a distinct flood mechanism. Incidence also shifts between temporal and unseen-station samples.", "",
        "![Cluster count and weather centroids](clustering.png)", "", "![Post-hoc cluster incidence](cluster_incidence.png)", "",
        "## Reproducibility and compatibility", "",
        "[Reproducibility manifest](reproducibility.json) records baseline/source/data hashes, environment versions, seed, threads and the model/threshold/code selection lock. "
        "audit → fit → select → evaluate → report are separate commands, with final records physically separate from development data. "
        "A completed evaluation cannot be overwritten. This does not claim an independent second reproduction that was not performed.", "",
        "The artifact retains the existing FastAPI feature-schema/threshold/metadata contract; calibrated estimators are standard scikit-learn objects. "
        "Signed trend features have names distinct from nonnegative physical measurement fields. Existing app settings continue to serve their original model. "
        "No automatic deployment, real notifications, routes, authentication or Fiji alert records were changed. "
        "Tests and exact commands are documented in `docs/TRAINING_02.md`. The raw source's redistribution license, independent negative labels, publication latency, "
        "calibration stability, proper full-season validation, fresh unseen test data and Fiji MET validation remain unresolved.", ""]
    if (out / "verification.json").exists():
        lines += ["## Executed checks", ""]
        for name, value in read("verification.json").items(): lines.append(f"- {name}: {value}")
        lines.append("")
    (out / "technical_report.md").write_text("\n".join(lines))
