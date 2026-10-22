"""v3 evaluation metrics: alert episodes, lead time and block-bootstrap intervals.

All functions consume only evaluation partitions (labels + predictions). They
never see simulator hidden state. Episode and bootstrap conventions are the
ones pre-registered in docs/SYNTHETIC_V3_PROTOCOL.md.
"""
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score

from ml.refinement import score

MERGE_GAP_HOURS = 6
ALERT_WINDOW_HOURS = 24
COOLDOWN_HOURS = 12
BOOTSTRAP_REPLICATES = 200
BOOTSTRAP_SEED = 314


def episode_metrics(data, probability, threshold, events, merge_gap=MERGE_GAP_HOURS,
                    alert_window=ALERT_WINDOW_HOURS, cooldown=COOLDOWN_HOURS):
    """Alarm-episode accounting for one evaluation partition.

    Hourly positive predictions are merged into an episode when the gap between
    positive hours is <= ``merge_gap``. An episode is a true alarm when an event
    onset of the same location starts in ``(episode_end, episode_end + alert_window]``.
    A true alarm starts a ``cooldown`` window during which further episodes are
    suppressed as duplicates rather than counted as false alarms.
    """
    probability = np.asarray(probability, dtype=float)
    frame = data.assign(_warning=probability >= threshold)
    onsets = {}
    for location_id, group in events.groupby("location_id"):
        onsets[int(location_id)] = np.sort(
            pd.to_datetime(group.event_start).to_numpy(dtype="datetime64[ns]").astype("int64"))
    rows, total_rows = [], len(frame)
    for location_id, group in frame.groupby("location_id"):
        group = group.sort_values("timestamp")
        times = group.timestamp.to_numpy(dtype="datetime64[ns]").astype("int64")
        warning = group._warning.to_numpy()
        positive = np.flatnonzero(warning)
        episodes = []
        if len(positive):
            start = prev = positive[0]
            for index in positive[1:]:
                gap_hours = (times[index] - times[prev]) / (3600 * 10**9)
                if gap_hours <= merge_gap:
                    prev = index
                else:
                    episodes.append((start, prev)); start = prev = index
            episodes.append((start, prev))
        local = onsets.get(int(location_id), np.array([], dtype="int64"))
        suppressed_until = -np.inf
        for start, end in episodes:
            episode_start, episode_end = times[start], times[end]
            if episode_start < suppressed_until:
                rows.append({"location_id": location_id, "episode_start_hours": episode_start, "kind": "suppressed_duplicate"})
                continue
            horizon_end = episode_end + alert_window * 3600 * 10**9
            soon = local[(local > episode_end) & (local <= horizon_end)]
            if len(soon):
                suppressed_until = episode_end + cooldown * 3600 * 10**9
                lead = (soon[0] - episode_end) / (3600 * 10**9)
                rows.append({"location_id": location_id, "episode_start_hours": episode_start,
                             "kind": "true_alarm", "lead_hours": float(lead)})
            else:
                rows.append({"location_id": location_id, "episode_start_hours": episode_start, "kind": "false_alarm"})
    episodes = pd.DataFrame(rows)
    false_alarms = int((episodes.kind == "false_alarm").sum()) if len(episodes) else 0
    true_alarms = int((episodes.kind == "true_alarm").sum()) if len(episodes) else 0
    suppressed = int((episodes.kind == "suppressed_duplicate").sum()) if len(episodes) else 0
    leads = (episodes.loc[episodes.kind == "true_alarm", "lead_hours"]
             if len(episodes) and "lead_hours" in episodes.columns else pd.Series(dtype=float))
    return {
        "alarm_episodes": true_alarms + false_alarms,
        "true_alarm_episodes": true_alarms,
        "false_alarm_episodes": false_alarms,
        "suppressed_duplicate_episodes": suppressed,
        "false_alarm_episodes_per_1000": 1000.0 * false_alarms / total_rows if total_rows else None,
        "episode_median_lead_hours": float(leads.median()) if len(leads) else None,
    }


def day_blocks(data):
    return pd.factorize(pd.to_datetime(data.timestamp).dt.floor("D"))[1]


def block_bootstrap(data, probability, threshold, n_boot=BOOTSTRAP_REPLICATES,
                    seed=BOOTSTRAP_SEED, metrics=("pr_auc_average_precision", "recall", "precision", "f1")):
    """95% percentile intervals from a bootstrap over whole days.

    Days (not rows) are resampled, so temporally correlated hours inside one
    episode stay together. Returns ``{metric: {low, high, mean}}``.
    """
    frame = data.reset_index(drop=True)
    y = frame.flood_within_24h.astype(int).to_numpy()
    p = np.asarray(probability, dtype=float)
    if len(np.unique(y)) < 2 or len(frame) < 400:
        return {m: {"low": None, "high": None, "mean": None, "replicates": 0} for m in metrics}
    codes, uniques = pd.factorize(pd.to_datetime(frame.timestamp).dt.floor("D"))
    order = [np.flatnonzero(codes == i) for i in range(len(uniques))]
    rng = np.random.default_rng(seed)
    draws = {m: [] for m in metrics}
    for _ in range(n_boot):
        picked = rng.integers(0, len(order), len(order))
        index = np.concatenate([order[i] for i in picked])
        if len(np.unique(y[index])) < 2:
            continue
        predicted = p[index] >= threshold
        values = {
            "pr_auc_average_precision": average_precision_score(y[index], p[index]),
            "recall": recall_score(y[index], predicted, zero_division=0),
            "precision": precision_score(y[index], predicted, zero_division=0),
            "f1": f1_score(y[index], predicted, zero_division=0),
        }
        for m in metrics:
            draws[m].append(float(values[m]))
    return {m: {"low": float(np.percentile(v, 2.5)) if v else None,
                "high": float(np.percentile(v, 97.5)) if v else None,
                "mean": float(np.mean(v)) if v else None,
                "replicates": len(v)} for m, v in draws.items()}


def evaluate(data, probability, threshold, events, include_bootstrap=True, include_episodes=True):
    """Classification + event + episode metrics for one partition."""
    result = dict(score(data.flood_within_24h, probability, threshold))
    result["balanced_accuracy"] = None
    result["accuracy"] = None
    y = data.flood_within_24h.astype(int).to_numpy()
    predicted = np.asarray(probability) >= threshold
    if len(np.unique(y)) == 2:
        from sklearn.metrics import accuracy_score, balanced_accuracy_score
        result["accuracy"] = float(accuracy_score(y, predicted))
        result["balanced_accuracy"] = float(balanced_accuracy_score(y, predicted))
    from ml.synthetic.train import event_metrics
    result.update(event_metrics(data, probability, threshold, events))
    if include_episodes and len(data):
        result.update(episode_metrics(data, probability, threshold, events))
    prevalence = result.get("prevalence")
    if prevalence:
        result["precision_lift_over_prevalence"] = (result["precision"] / prevalence
                                                    if result.get("precision") is not None else None)
    if include_bootstrap and len(data):
        result["bootstrap_95ci"] = block_bootstrap(data, probability, threshold)
    return result
