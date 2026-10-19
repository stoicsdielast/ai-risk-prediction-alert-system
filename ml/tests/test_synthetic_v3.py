"""Synthetic V3: episode-metric edge cases, scenario separation and publish checks."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from ml.synthetic.generate import SimulationConfig, scenario_settings, simulate
from ml.synthetic.metrics_v3 import episode_metrics, block_bootstrap, evaluate
from ml.synthetic.train_v3 import inner_splits

V3_DATASET = Path("ml/data/synthetic_fiji/v3/realistic")
V3_RUN = Path("ml/runs/synthetic-v3/realistic")


def _frame(hours=48, location=1):
    return pd.DataFrame({
        "location_id": location,
        "timestamp": pd.date_range("2024-03-01", periods=hours, freq="h", tz="UTC"),
        "flood_within_24h": 0,
    })


def _events(rows):
    return pd.DataFrame(rows, columns=["location_id", "event_start", "event_end"])


def test_episode_metrics_survives_partitions_without_true_alarms():
    data = _frame()
    probability = np.ones(len(data)) * 0.9
    events = _events([(1, pd.Timestamp("2024-03-10", tz="UTC"), pd.Timestamp("2024-03-10 05:00", tz="UTC"))])
    result = episode_metrics(data, probability, 0.5, events)
    assert result["alarm_episodes"] == 1
    assert result["true_alarm_episodes"] == 0 and result["false_alarm_episodes"] == 1
    assert result["episode_median_lead_hours"] is None


def test_episode_metrics_counts_cooldown_suppression_and_lead_time():
    times = pd.date_range("2024-03-01", periods=24 * 10, freq="h", tz="UTC")
    data = pd.DataFrame({"location_id": 1, "timestamp": times, "flood_within_24h": 0})
    probability = np.zeros(len(data))
    onset = times[24 * 5]
    for hour in (24 * 4 + 1, 24 * 4 + 10):  # two episodes before the onset, gap > merge window
        probability[hour] = 0.9
    events = _events([(1, onset, onset + pd.Timedelta("3h"))])
    result = episode_metrics(data, probability, 0.5, events)
    assert result["true_alarm_episodes"] == 1
    assert result["false_alarm_episodes"] == 0
    assert result["suppressed_duplicate_episodes"] == 1
    assert result["episode_median_lead_hours"] == pytest.approx((onset - times[24 * 4 + 1]) / pd.Timedelta("1h"))


def test_block_bootstrap_reports_single_class_partitions_as_unavailable():
    data = _frame()
    result = block_bootstrap(data, np.zeros(len(data)), 0.5)
    assert result["recall"]["low"] is None and result["recall"]["replicates"] == 0


def test_evaluate_never_leaks_truth_columns_into_predictions():
    data = _frame()
    data["flood_occurred"] = False
    probability = np.linspace(0, 1, len(data))
    result = evaluate(data, probability, 0.5, _events([]), include_bootstrap=False)
    assert "flood_occurred" not in result and "flood_within_24h" not in result


def test_scenario_settings_define_distinct_regimes():
    controlled = scenario_settings("controlled")
    realistic = scenario_settings("realistic")
    stress = scenario_settings("stress")
    assert controlled.rain_threshold_noise < realistic.rain_threshold_noise < stress.rain_threshold_noise
    assert controlled.met_noise < realistic.met_noise < stress.met_noise
    assert controlled.missing_scale < realistic.missing_scale < stress.missing_scale
    assert controlled.drainage_heterogeneity == 0.0 < stress.drainage_heterogeneity
    assert controlled.ood_profile_prob == realistic.ood_profile_prob == 0.0 < stress.ood_profile_prob
    assert stress.sensor_drift > realistic.sensor_drift == 0.0


def test_scenario_simulations_are_separated_by_regime():
    common = dict(start="2021-01-01", end="2021-03-01", seed=7)
    _, controlled_obs, _, _, _ = simulate(SimulationConfig(**common, scenario="controlled"))
    _, stress_obs, _, _, _ = simulate(SimulationConfig(**common, scenario="stress"))
    missing = stress_obs.rainfall_mm.isna().mean()
    assert missing > controlled_obs.rainfall_mm.isna().mean()
    assert not stress_obs.equals(controlled_obs)


def test_same_seed_reproduces_identical_observations():
    _, first, _, _, _ = simulate(SimulationConfig(start="2021-01-01", end="2021-02-01", seed=11, scenario="realistic"))
    _, second, _, _, _ = simulate(SimulationConfig(start="2021-01-01", end="2021-02-01", seed=11, scenario="realistic"))
    pd.testing.assert_frame_equal(first, second)


def test_inner_splits_are_chronological_embargoed_and_storm_grouped():
    times = pd.date_range("2021-01-01", periods=24 * 400, freq="h", tz="UTC")
    train = pd.DataFrame({"location_id": 1, "timestamp": times, "flood_within_24h": 0})
    train.loc[:: 24 * 7, "flood_within_24h"] = 1  # weekly positives everywhere
    # Storm straddles the boundary between fitting block 0 and validation block 1.
    storm_start = pd.Timestamp("2021-04-10 12:00", tz="UTC")
    storm_end = storm_start + pd.Timedelta("36h")
    scenarios = pd.DataFrame([{"scenario_id": "s1", "start": storm_start, "end": storm_end}])
    folds = inner_splits(train, scenarios)
    assert len(folds) == 3
    for fold in folds:
        assert fold["fit"].timestamp.max() < fold["validation"].timestamp.min()
        assert fold["fit"].flood_within_24h.nunique() == 2
        assert fold["validation"].flood_within_24h.nunique() == 2
    boundary = folds[0]
    assert boundary["validation_excluded_storm_rows"] > 0
    assert not boundary["validation"].timestamp.between(storm_start, storm_end).any()
    assert boundary["validation"].timestamp.min() > storm_end


@pytest.mark.skipif(not (V3_DATASET.exists() and V3_RUN.exists()),
                    reason="V3 realistic dataset and run are required")
def test_finalize_v3_publishes_verified_truth_separated_bundle(tmp_path):
    from ml.synthetic.finalize_v3 import package, TRUTH_COLUMNS

    out = tmp_path / "realistic"
    result = package(V3_DATASET, V3_RUN, out)
    assert result["scenario"] == "realistic"
    manifest = json.loads((out / "research_manifest.json").read_text())
    for name in ("research_model.joblib", "research_features.parquet", "research_truth.parquet",
                 "research_events.csv", "research_locations.csv", "research_scenario.json"):
        assert (out / name).exists() and name in manifest["hashes"]
    scenario_meta = json.loads((out / "research_scenario.json").read_text())
    import joblib
    bundle = joblib.load(out / "research_model.joblib")
    assert not (set(bundle["features"]) & TRUTH_COLUMNS)
    assert scenario_meta["research_only"] and scenario_meta["ground_truth_policy"]
    truth = pd.read_parquet(out / "research_truth.parquet")
    assert {"flood_occurred", "flood_within_24h", "event_id", "stage"} <= set(truth.columns)
    features = pd.read_parquet(out / "research_features.parquet", columns=None)
    assert not (set(features.columns) & {"flood_occurred", "flood_within_24h", "event_id"})
    with pytest.raises(ValueError, match="Bundle exists"):
        package(V3_DATASET, V3_RUN, out)


def test_transfer_helpers_hydrological_rule_and_majority():
    from ml.synthetic.transfer_v3 import RULE_FEATURES, hydrological_rule, majority_probability
    from ml.synthetic.features_v2 import build_features_v2

    frame = pd.DataFrame(
        {
            "rainfall_mm_total_24h": [100.0, 80.0, 80.1, np.nan],
            "soil_moisture_pct": [80.0, 76.0, 74.0, 90.0],
        }
    )
    # strictly greater-than on both features; NaN compares False
    assert hydrological_rule(frame).tolist() == [1.0, 0.0, 0.0, 0.0]
    assert majority_probability(pd.Series([0, 0, 1, 1, 0])) == 0.4

    # both rule features must be produced by the real feature builder
    obs = pd.DataFrame({
        "location_id": 1,
        "timestamp": pd.date_range("2024-01-01", periods=48, freq="h", tz="UTC"),
        "rainfall_mm": 5.0, "temperature_c": 26.0, "humidity_pct": 80.0,
        "pressure_hpa": 1010.0, "wind_speed_ms": 3.0, "wind_direction_deg": 90.0,
        "river_level_m": 2.0, "river_discharge_m3s": 50.0, "soil_moisture_pct": 70.0,
        "upstream_rainfall_mm": 5.0, "coastal_tide_m": 0.5,
    })
    locations = pd.DataFrame({
        "location_id": [1], "name": ["Suva"], "latitude": [-18.14], "longitude": [178.44],
        "elevation_m": [10.0], "slope_pct": [2.0], "catchment_area_km2": [50.0],
        "river_proximity_km": [1.0], "coastal_influence": [0.5],
        "drainage_capacity_mm_h": [30.0], "soil_moisture_capacity_pct": [85.0],
    })
    frame, extended, _weather = build_features_v2(obs, locations)
    assert set(RULE_FEATURES) <= set(frame.columns)
    assert set(RULE_FEATURES) <= set(extended)


@pytest.mark.skipif(not (V3_DATASET.exists() and V3_RUN.exists()),
                    reason="V3 realistic dataset and run are required")
def test_transfer_v3_applies_frozen_realistic_winner():
    """OOD transfer reuses the frozen bundle; no refit, threshold unchanged."""
    import joblib
    from ml.synthetic.transfer_v3 import transfer

    bundle = joblib.load(V3_RUN / "candidate_model.joblib")
    result = transfer(V3_RUN.parent, source="realistic")
    assert result["threshold"] == bundle["threshold"]
    assert result["calibration"] == bundle["calibration"]
    assert set(result["ood_scenarios"]) == {"controlled", "stress"}
    for stage in ("threshold", "test", "held_location"):
        row = result["ood_scenarios"]["stress"][stage]
        assert 0.0 <= row["recall"] <= 1.0
        assert 0.0 <= row["precision"] <= 1.0
