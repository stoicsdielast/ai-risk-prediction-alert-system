import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from ml.synthetic.generate import SimulationConfig, simulate
from ml.synthetic.features_v2 import build_features_v2, HYDRO_CHANNELS


def _small(seed=7):
    loc, obs, _, _, _ = simulate(SimulationConfig(start="2021-01-01", end="2021-02-20", seed=seed))
    return loc, obs


def test_v2_features_are_causal_and_window_recomputable():
    loc, obs = _small()
    full, extended, _ = build_features_v2(obs, loc)
    start = pd.Timestamp("2021-01-20", tz="UTC")
    window = obs[obs.timestamp >= start]
    partial, ext2, _ = build_features_v2(window, loc)
    assert extended == ext2
    # Rows at least 336 h into the window must equal the full computation.
    warm = partial.groupby("location_id").cumcount() >= 336
    left = partial[warm].reset_index(drop=True)
    merged = full.merge(window[["location_id", "timestamp"]], on=["location_id", "timestamp"])
    merged = merged[merged.groupby("location_id").cumcount() >= 336].reset_index(drop=True)
    pd.testing.assert_frame_equal(left[extended], merged[extended], check_dtype=False)


def test_v2_features_unchanged_when_only_future_weather_changes():
    loc, obs = _small()
    cutoff = pd.Timestamp("2021-02-01", tz="UTC")
    before, names, weather = build_features_v2(obs, loc)
    changed = obs.copy()
    changed.loc[changed.timestamp > cutoff, "rainfall_mm"] = 999
    changed.loc[changed.timestamp > cutoff, "river_level_m"] += 5
    after, names2, _ = build_features_v2(changed, loc)
    assert names == names2
    keep = before.timestamp <= cutoff
    pd.testing.assert_frame_equal(before[keep].reset_index(drop=True),
                                  after[after.timestamp <= cutoff].reset_index(drop=True),
                                  check_dtype=False)
    assert not any(any(x in c for x in ["flood", "event", "scenario", "hidden", "future", "target"]) for c in names)


def test_weather_only_set_has_no_hydrological_channels():
    loc, obs = _small()
    _, extended, weather = build_features_v2(obs, loc)
    assert set(weather) < set(extended)
    for channel in HYDRO_CHANNELS:
        assert not any(c == channel or c.startswith(channel + "_") for c in weather)
        assert any(c == channel or c.startswith(channel + "_") for c in extended)


_RUN = Path("ml/runs/synthetic-v2")


@pytest.mark.skipif(not (_RUN / "metrics.csv").exists(), reason="v2 run artifacts not present")
def test_operating_threshold_comes_from_threshold_partition_only():
    thresholds = json.loads((_RUN / "thresholds.json").read_text())
    metrics = pd.read_csv(_RUN / "metrics.csv")
    for candidate, info in thresholds.items():
        observed = metrics[metrics.candidate.eq(candidate)].threshold.unique()
        assert len(observed) == 1
        assert np.isclose(observed[0], info["threshold"])
