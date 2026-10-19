"""Research-policy invariants; synthetic data are never reported as flood skill."""
import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression

from ml.config import FEATURES, HOLDOUT_STATIONS, TARGET
from ml.refinement import (EXTRA_FEATURES, assert_disjoint, calibrated, development_stages, extended_features,
                           recall_budget_threshold, score, selection_choice, threshold_table)
from ml.tests.test_research_pipeline import series
from ml.train import pipeline
from ml.training02 import protect_paths, specifications


def test_extended_features_are_causal_with_correct_daily_units():
    raw, registry = series()
    first = extended_features(raw, registry)
    changed = raw.copy()
    changed.loc[40, "rainfall_local_mm"] = 10000.
    changed.loc[40, "river_discharge_m3s"] = 90000.
    changed[TARGET] = ~changed[TARGET]
    second = extended_features(changed, registry)
    columns = FEATURES + EXTRA_FEATURES
    pd.testing.assert_frame_equal(first.loc[first.index < 40, columns], second.loc[second.index < 40, columns])
    pd.testing.assert_frame_equal(first.loc[first.station_id.eq("B"), columns], second.loc[second.station_id.eq("B"), columns])
    assert first.loc[14, "rainfall_local_mm_sum3d"] == 13 + 14 + 15
    assert first.loc[14, "discharge_change_3d"] == 3
    assert first.loc[14, "river_discharge_m3s_mean3d"] == 14
    assert np.isnan(first.loc[0, "rainfall_local_mm_sum3d"])


def test_four_validation_blocks_keep_three_day_embargo():
    dates = ["2022-06-27", "2022-06-28", "2022-07-01", "2022-12-28", "2022-12-29", "2023-01-01", "2023-06-27", "2023-06-28", "2023-07-01"]
    frame = pd.DataFrame({"date": pd.to_datetime(dates), "station_id": "A", "partition": "validation"})
    assert development_stages(frame).tolist() == ["tuning", "embargo", "calibration", "calibration", "embargo", "selection", "selection", "embargo", "threshold"]
    frame["station_id"] = HOLDOUT_STATIONS[0]
    with pytest.raises(ValueError, match="Held-out station"):
        development_stages(frame)


def test_development_guard_rejects_test_dates_and_overlapping_periods():
    dates = ["2021-01-01", "2022-01-01", "2022-07-01", "2023-01-01", "2023-07-01"]
    parts = {name: pd.DataFrame({"date": pd.to_datetime([stamp, stamp]), "station_id": "A", TARGET: [0, 1]})
             for name, stamp in zip(["train", "tuning", "calibration", "selection", "threshold"], dates)}
    assert_disjoint(parts)
    parts["threshold"]["date"] = pd.Timestamp("2024-02-01")
    with pytest.raises(ValueError, match="Evaluation records"):
        assert_disjoint(parts)
    parts["threshold"]["date"] = pd.Timestamp("2023-01-01")
    with pytest.raises(ValueError, match="embargo"):
        assert_disjoint(parts)


@pytest.mark.parametrize("method", ["sigmoid", "isotonic"])
def test_calibrator_does_not_refit_base_model_or_preprocessing(method):
    rng = np.random.default_rng(314)
    x = pd.DataFrame(rng.normal(size=(100, 3)), columns=["a", "b", "c"])
    y = (x.a + rng.normal(size=100) > 0).astype(int)
    base = pipeline(LogisticRegression()).fit(x.iloc[:60], y.iloc[:60])
    coefficients = base.named_steps["classifier"].coef_.copy()
    mean = base.named_steps["scale"].mean_.copy()
    calibration = x.iloc[60:80].copy(); calibration[TARGET] = y.iloc[60:80]
    model = calibrated(base, calibration, ["a", "b", "c"], method)
    np.testing.assert_array_equal(base.named_steps["classifier"].coef_, coefficients)
    np.testing.assert_array_equal(base.named_steps["scale"].mean_, mean)
    p = model.predict_proba(x.iloc[80:])[:, 1]
    assert np.isfinite(p).all() and ((p >= 0) & (p <= 1)).all()
    assert list(model.feature_names_in_) == ["a", "b", "c"]


def test_threshold_table_matches_direct_counts_even_with_ties():
    y, p = np.array([0, 1, 1, 0, 1]), np.array([.1, .2, .8, .8, 1.])
    table = threshold_table(y, p)
    assert table.iloc[0].tp == table.iloc[0].fp == 0
    for _, row in table.iterrows():
        expected = score(y, p, row.threshold)["confusion_matrix_tn_fp_fn_tp"]
        assert expected == [row.tn, row.fp, row.fn, row.tp]


def test_recall_policy_respects_false_alert_budget_without_forced_target():
    table = threshold_table([1, 0, 1, 0, 1, 0], [.9, .8, .7, .6, .5, .4])
    choice = recall_budget_threshold(table, .5)
    assert choice["false_alerts_per_detection"] <= .5
    assert choice["recall"] == pytest.approx(2/3)
    with pytest.raises(ValueError, match="No nontrivial threshold"):
        recall_budget_threshold(threshold_table([0, 1], [.9, .2]), 0.)


def test_brier_selection_uses_validation_ranking_guard():
    candidates = pd.DataFrame({"model_id": ["baseline", "calibrated", "all_safe"],
                               "pr_auc_average_precision": [.3, .29, .04], "brier": [.14, .04, .03]})
    assert selection_choice(candidates, .3) == "calibrated"


def test_output_paths_cannot_modify_original_run(tmp_path):
    baseline = tmp_path / "training-01"
    for out in [baseline, baseline / "child", tmp_path]:
        with pytest.raises(ValueError, match="separate"):
            protect_paths(out, baseline)
    protect_paths(tmp_path / "training-02", baseline)
    assert len(specifications()) == 28
