"""Synthetic fixtures exercise software invariants, never model performance claims."""
import numpy as np
import pandas as pd
import pytest

from ml.config import BASE, FEATURES, HOLDOUT_STATIONS, REGIME, TARGET
from ml.data import build_features, representative_subset, screen_labels, split_rows, validate_raw
from ml.train import fit_candidates, metrics


def series(days=45, station_ids=("A", "B"), start="2013-01-01"):
    frames, registry = [], {}
    for i, sid in enumerate(station_ids):
        frame = pd.DataFrame({"date": pd.date_range(start, periods=days), "station_id": sid,
                              REGIME: "observed", TARGET: np.arange(days) % 7 == 0,
                              "elevation_m": 5.0, "hand_m": 2.0})
        for column in BASE:
            frame[column] = 0.2 if column.startswith("soil") else np.arange(days) + 1.0
        registry[sid] = {"latitude": 23 + i * .01, "longitude": 90}
        frames.append(frame)
    return pd.concat(frames, ignore_index=True), registry


def test_unknown_and_positive_only_labels_never_become_negatives():
    raw, _ = series(days=5, station_ids=("A",))
    raw[TARGET] = raw[TARGET].astype(float)
    raw.loc[0, TARGET] = np.nan
    raw.loc[1, REGIME] = "unobserved_positive"
    raw.loc[1, TARGET] = 1.0
    raw.loc[2, "date"] = pd.Timestamp("2001-01-01")
    assert screen_labels(raw).tolist() == [False, False, False, True, True]


def test_duplicate_and_gapped_daily_series_fail_closed():
    raw, registry = series()
    with pytest.raises(ValueError, match="Duplicate"):
        validate_raw(pd.concat([raw, raw.iloc[:1]]))
    with pytest.raises(ValueError, match="Daily series"):
        build_features(raw.drop(index=15), registry)


def test_future_and_target_changes_cannot_change_prior_features_or_other_station():
    raw, registry = series()
    original = build_features(raw, registry)
    changed = raw.copy()
    changed.loc[40, BASE] = [10000, 10000, .9, 10000]
    changed[TARGET] = ~changed[TARGET]
    changed["flood_byStor"] = 999
    rebuilt = build_features(changed, registry)
    pd.testing.assert_frame_equal(original.loc[original.index < 40, FEATURES], rebuilt.loc[rebuilt.index < 40, FEATURES])
    pd.testing.assert_frame_equal(original.loc[original.station_id.eq("B"), FEATURES], rebuilt.loc[rebuilt.station_id.eq("B"), FEATURES])
    assert rebuilt.loc[14, "rainfall_local_mm_lag1d"] == 14
    assert rebuilt.loc[14, "rainfall_local_mm_sum14d"] == sum(range(2, 16))
    assert not any(any(word in c.lower() for word in ("flood", "regime", "target", "future")) for c in FEATURES)


def test_time_boundaries_embargo_and_station_holdout():
    dates = ["2021-12-28", "2021-12-29", "2022-01-01", "2023-12-28", "2023-12-29", "2024-01-01"]
    frame = pd.DataFrame({"date": pd.to_datetime(dates), "station_id": "A"})
    assert split_rows(frame).tolist() == ["train", "excluded", "validation", "validation", "excluded", "test"]
    frame["station_id"] = HOLDOUT_STATIONS[0]
    assert split_rows(frame).tolist() == ["excluded"] * 5 + ["holdout_station"]


def test_subset_is_deterministic_and_independent_of_target():
    raw, registry = series(days=4800, station_ids=tuple(f"S{i}" for i in range(10)))
    full = build_features(raw, registry)
    first = representative_subset(full, rows=20000)
    full[TARGET] = ~full[TARGET]
    second = representative_subset(full.sample(frac=1, random_state=9), rows=20000)
    assert first.selection_hash.tolist() == second.selection_hash.tolist()
    assert len(first) == 20000 and first.station_id.nunique() == 10
    assert first[FEATURES].notna().all().all()


def test_four_models_training_smoke_and_train_only_preprocessing():
    rng = np.random.default_rng(314)
    frame = pd.DataFrame(rng.normal(size=(160, len(FEATURES))), columns=FEATURES)
    frame[TARGET] = np.tile([0, 0, 0, 1], 40)
    train, validation = frame.iloc[:120].copy(), frame.iloc[120:].copy()
    train.loc[0, FEATURES[0]] = np.nan
    validation[FEATURES[0]] += 10000
    models, _ = fit_candidates(train, validation, smoke=True)
    assert set(models) == {"logistic_regression", "random_forest", "lightgbm", "catboost"}
    for fitted in models.values():
        preprocessing = fitted["pipeline"].named_steps
        assert preprocessing["imputer"].statistics_[0] == pytest.approx(train[FEATURES[0]].median())
        assert abs(preprocessing["scale"].mean_[0]) < 10  # No validation outlier entered the fit.
        probabilities = fitted["pipeline"].predict_proba(validation[FEATURES])[:, 1]
        assert np.isfinite(probabilities).all()
        assert 0 <= fitted["threshold"] <= 1


def test_single_class_metrics_report_invalid_auc():
    report = metrics([0, 0], [.1, .2], .5)
    assert report["roc_auc"] is None and report["pr_auc_average_precision"] is None
    assert report["confusion_matrix_tn_fp_fn_tp"] == [2, 0, 0, 0]
