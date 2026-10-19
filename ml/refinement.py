"""Time-safe features and policies for the second, isolated research study."""
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.metrics import log_loss

from ml.config import BASE, FEATURES, HOLDOUT_STATIONS, TARGET
from ml.data import build_features
from ml.train import metrics

EXTRA_FEATURES = ["rainfall_local_mm_sum3d", "rainfall_upstream_mm_sum3d",
                  "river_discharge_m3s_mean3d", "discharge_change_1d", "discharge_change_3d",
                  "discharge_change_7d", "discharge_relative_change_3d", "soil_water_change_7d"]
FEATURE_SETS = {"baseline": FEATURES, "hydrology": FEATURES + EXTRA_FEATURES}
VALIDATION_WINDOWS = {
    "tuning": ("2022-01-01", "2022-06-28"),
    "calibration": ("2022-07-01", "2022-12-29"),
    "selection": ("2023-01-01", "2023-06-28"),
    "threshold": ("2023-07-01", "2023-12-29"),
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def directory_hashes(directory):
    directory = Path(directory)
    return {str(p.relative_to(directory)): sha256(p) for p in sorted(directory.rglob("*")) if p.is_file()}


def extended_features(raw, registry):
    frame = build_features(raw, registry)
    for column in BASE[:2]:
        frame[column + "_sum3d"] = frame.groupby("station_id")[column].transform(lambda s: s.rolling(3, min_periods=3).sum())
    groups = frame.groupby("station_id")["river_discharge_m3s"]
    frame["river_discharge_m3s_mean3d"] = groups.transform(lambda s: s.rolling(3, min_periods=3).mean())
    for days in (1, 3, 7):
        frame[f"discharge_change_{days}d"] = frame.river_discharge_m3s - groups.shift(days)
    prior = groups.shift(3)
    frame["discharge_relative_change_3d"] = (frame.river_discharge_m3s - prior) / prior.abs().clip(lower=1.)
    frame["soil_water_change_7d"] = frame.soil_moisture_local - frame.groupby("station_id").soil_moisture_local.shift(7)
    return frame


def development_stages(frame):
    stages = frame.partition.copy()
    stages.loc[frame.partition.eq("validation")] = "embargo"
    for stage, (start, end) in VALIDATION_WINDOWS.items():
        mask = frame.partition.eq("validation") & frame.date.ge(start) & frame.date.lt(end)
        stages.loc[mask] = stage
    # Verify the assignment independently of the saved partition strings.
    fit_stages = stages.isin(["train", *VALIDATION_WINDOWS])
    if frame.loc[fit_stages, "station_id"].isin(HOLDOUT_STATIONS).any():
        raise ValueError("Held-out station appears in development")
    if frame.loc[fit_stages, "date"].ge("2024-01-01").any():
        raise ValueError("Final test date appears in development")
    return stages


def assert_disjoint(parts, embargo_days=3):
    names = ["train", "tuning", "calibration", "selection", "threshold"]
    for name in names:
        data = parts[name]
        if data.empty or data[TARGET].nunique() != 2:
            raise ValueError(f"{name} requires nonempty data with both classes")
        if data.station_id.isin(HOLDOUT_STATIONS).any() or data.date.ge("2024-01-01").any():
            raise ValueError("Evaluation records entered development")
    for earlier, later in zip(names, names[1:]):
        if parts[earlier].date.max() + pd.Timedelta(days=embargo_days) >= parts[later].date.min():
            raise ValueError(f"Insufficient embargo: {earlier} to {later}")


def calibrated(fitted, data, features, method):
    if method == "none":
        return fitted
    # FrozenEstimator prevents any refitting of the already-trained base model.
    estimator = CalibratedClassifierCV(FrozenEstimator(fitted), method=method, ensemble=False, n_jobs=1)
    return estimator.fit(data[features], data[TARGET].astype(int))


def reliability(y, probability, bins=10):
    y, probability = np.asarray(y, dtype=int), np.asarray(probability, dtype=float)
    memberships = np.minimum((probability * bins).astype(int), bins - 1)
    rows = []
    for i in range(bins):
        selected = memberships == i
        if selected.any():
            rows.append({"bin_low": i / bins, "bin_high": (i + 1) / bins,
                         "rows": int(selected.sum()), "mean_probability": float(probability[selected].mean()),
                         "positive_fraction": float(y[selected].mean())})
    return rows


def score(y, probability, threshold=.5):
    result = metrics(y, probability, threshold)
    if not result["rows"]:
        return result
    tn, fp, fn, tp = result["confusion_matrix_tn_fp_fn_tp"]
    result.update(mean_probability=float(np.mean(probability)),
                  log_loss=float(log_loss(y, np.clip(probability, 1e-12, 1 - 1e-12), labels=[0, 1])),
                  false_alerts_per_detection=float(fp / tp) if tp else None,
                  false_alerts_per_1000=float(1000 * fp / len(y)), predicted_positive=int(fp + tp),
                  f2=float(5 * tp / (5 * tp + 4 * fn + fp)) if tp + fn + fp else 0.)
    result["ece_equal_width_10_bins"] = float(sum(row["rows"] / len(y) * abs(row["mean_probability"] - row["positive_fraction"])
                                                  for row in reliability(y, probability)))
    return result


def threshold_table(y, probability):
    """Exact operating points, with ties kept together, in O(n log n)."""
    y, probability = np.asarray(y, dtype=int), np.asarray(probability, dtype=float)
    if not len(y) or not np.isfinite(probability).all() or not np.isin(y, [0, 1]).all():
        raise ValueError("Invalid threshold data")
    order = np.argsort(-probability, kind="stable")
    p, labels = probability[order], y[order]
    ends = np.r_[np.flatnonzero(np.diff(p)), len(p) - 1]
    tp = np.cumsum(labels)[ends]; fp = ends + 1 - tp
    positives = int(y.sum()); negatives = len(y) - positives
    precision = tp / (tp + fp)
    recall = tp / positives if positives else np.zeros(len(tp))
    table = pd.DataFrame({"threshold": p[ends], "tp": tp, "fp": fp, "fn": positives - tp, "tn": negatives - fp,
                         "precision": precision, "recall": recall,
                         "f1": 2 * tp / np.maximum(2 * tp + fp + positives - tp, 1),
                         "f2": 5 * tp / np.maximum(5 * tp + fp + 4 * (positives - tp), 1),
                         "false_alerts_per_detection": np.divide(fp, tp, out=np.full(len(fp), np.inf), where=tp > 0),
                         "false_alerts_per_1000": 1000 * fp / len(y)})
    # Sensitivity analyses must include the legitimate no-alert operating point.
    # It is excluded by the nontrivial TP>0 recall-budget policy.
    no_alert = dict(threshold=float(np.nextafter(1., 2.)), tp=0, fp=0, fn=positives, tn=negatives,
                    precision=0., recall=0., f1=0., f2=0., false_alerts_per_detection=np.inf, false_alerts_per_1000=0.)
    return pd.concat([pd.DataFrame([no_alert]), table], ignore_index=True)


def recall_budget_threshold(table, budget):
    if budget is None or not np.isfinite(budget) or budget < 0:
        raise ValueError("A finite baseline false-alerts-per-detection budget is required")
    feasible = table.loc[(table.tp > 0) & (table.false_alerts_per_detection <= budget + 1e-12)]
    if feasible.empty:
        raise ValueError("No nontrivial threshold meets the baseline false-alert budget; no recall target forced")
    return feasible.sort_values(["recall", "fp", "threshold"], ascending=[False, True, False]).iloc[0].to_dict()


def selection_choice(table, baseline_ap, tolerance=.05):
    """Predeclared probability criterion; never passed final-test metrics."""
    eligible = table[table.pr_auc_average_precision >= (1 - tolerance) * baseline_ap]
    if eligible.empty:
        raise ValueError("No model passes the validation AP retention guard")
    return eligible.sort_values(["brier", "pr_auc_average_precision", "model_id"], ascending=[True, False, True]).iloc[0].model_id
