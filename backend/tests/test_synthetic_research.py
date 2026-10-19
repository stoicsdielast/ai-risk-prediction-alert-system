"""Research-only V3 scenario routes: ground truth is display-only, V1 serving untouched."""

import json

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.core.config import get_settings
from app.services.synthetic_research import load_research_scenario

NOTICE = "Synthetic Data — Research Demonstration"
FEATURES = ["rainfall_mm", "soil_moisture_pct", "river_level_m"]


def _publish(scenario_dir, scenario="realistic"):
    scenario_dir.mkdir(parents=True, exist_ok=True)
    times = pd.date_range("2024-06-01", periods=72, freq="h", tz="UTC")
    frame = pd.DataFrame([(loc, t) for loc in (1, 2) for t in times],
                         columns=["location_id", "timestamp"])
    rng = np.random.default_rng(7)
    for name in FEATURES:
        frame[name] = rng.random(len(frame)) * 100
    frame["history_ready"] = True
    frame.loc[frame.groupby("location_id").tail(1).index, "history_ready"] = False

    model = Pipeline([("scale", StandardScaler()), ("classifier", LogisticRegression())]).fit(
        frame[FEATURES], (frame.river_level_m > frame.rainfall_mm).astype(int))
    joblib.dump({"model": model, "calibrator": None, "calibration": "none", "features": FEATURES,
                 "threshold": 0.5, "model_version": f"synthetic-fiji-v3-{scenario}-logistic_baseline__none",
                 "scenario": scenario, "source_type": "synthetic", "notice": NOTICE},
                scenario_dir / "research_model.joblib")

    frame[["location_id", "timestamp"] + FEATURES + ["history_ready"]].to_parquet(
        scenario_dir / "research_features.parquet", index=False)
    truth = frame[["location_id", "timestamp"]].copy()
    truth["flood_occurred"] = frame.river_level_m > 50
    truth["flood_within_24h"] = frame.soil_moisture_pct > 60
    truth["stage"] = "test"
    truth["event_id"] = None
    truth.loc[truth.flood_occurred, "event_id"] = "event-1"
    truth.to_parquet(scenario_dir / "research_truth.parquet", index=False)
    pd.DataFrame([{"event_id": "event-1", "location_id": 1, "name": "Suva", "slug": "suva",
                   "scenario_id": "storm-1", "event_start": times[10], "event_end": times[20],
                   "severity": "severe", "duration_hours": 10.0, "max_river_level_m": 55.0}]).to_csv(
        scenario_dir / "research_events.csv", index=False)
    pd.DataFrame([{"location_id": 1, "slug": "suva", "name": "Suva", "division": "CENTRAL",
                   "latitude": -18.14, "longitude": 178.44},
                  {"location_id": 2, "slug": "nausori", "name": "Nausori", "division": "CENTRAL",
                   "latitude": -18.02, "longitude": 178.55}]).to_csv(
        scenario_dir / "research_locations.csv", index=False)
    (scenario_dir / "research_scenario.json").write_text(json.dumps({
        "source_type": "synthetic", "notice": NOTICE, "research_only": True, "scenario": scenario,
        "model_version": f"synthetic-fiji-v3-{scenario}-logistic_baseline__none",
        "selected_candidate": "logistic_baseline", "calibration": "none", "threshold": 0.5,
        "n_features": len(FEATURES), "time_range": {"start": str(times[0]), "end": str(times[-1])},
        "observations": int(len(frame)), "weather_columns": FEATURES,
        "events": {"total": 1, "by_severity": {"severe": 1}},
        "partitions": {"test": {"min": str(times[0]), "max": str(times[-1])}},
        "held_location_ids": [2], "bootstrap_intervals": {}, "ground_truth_policy": "display only"}))
    (scenario_dir / "research_manifest.json").write_text(json.dumps(
        {"source_type": "synthetic", "scenario": scenario}))


@pytest.fixture
def research_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SYNTHETIC_RESEARCH_DIR", str(tmp_path))
    get_settings.cache_clear()
    load_research_scenario.cache_clear()
    yield tmp_path
    get_settings.cache_clear()
    load_research_scenario.cache_clear()


def test_info_reports_unpublished_until_bundle_exists(client, research_dir):
    body = client.get("/api/synthetic/research/info").json()
    assert body["source_type"] == "synthetic" and body["research_only"] and body["v1_serving_unchanged"]
    assert {s["scenario"] for s in body["scenarios"]} == {"controlled", "realistic", "stress"}
    assert all(s["status"] == "not_published" for s in body["scenarios"])
    _publish(research_dir / "realistic")
    load_research_scenario.cache_clear()
    ready = {s["scenario"]: s for s in client.get("/api/synthetic/research/info").json()["scenarios"]}
    assert ready["realistic"]["status"] == "ready" and ready["stress"]["status"] == "not_published"


def test_frame_returns_weather_probability_and_display_only_ground_truth(client, research_dir):
    _publish(research_dir / "realistic")
    load_research_scenario.cache_clear()
    body = client.get("/api/synthetic/research/frame?scenario=realistic&timestamp=2024-06-01T10:00:00Z").json()
    assert body["notice"] == NOTICE and body["research_only"]
    assert len(body["locations"]) == 2
    entry = body["locations"][0]
    assert set(FEATURES) <= set(entry["weather"])
    assert entry["status"] == "ok" and 0 <= entry["probability"] <= 1
    assert entry["risk_category"] in ("LOW", "MODERATE", "HIGH", "VERY_HIGH")
    truth = entry["ground_truth"]
    assert truth["research_view_only"] and truth["available"]
    assert isinstance(truth["flood_occurred"], bool) and isinstance(truth["flood_within_24h"], bool)
    assert "flood_within_24h" not in entry and "flood_occurred" not in entry
    insufficient = client.get(
        "/api/synthetic/research/frame?scenario=realistic&timestamp=2024-06-03T23:00:00Z").json()
    assert {loc["status"] for loc in insufficient["locations"]} == {"insufficient_history"}


def test_storms_and_series_support_storm_replay(client, research_dir):
    _publish(research_dir / "stress")
    load_research_scenario.cache_clear()
    storms = client.get("/api/synthetic/research/storms?scenario=stress").json()
    assert storms["storms"][0]["event_id"] == "event-1" and storms["storms"][0]["name"] == "Suva"
    series = client.get(
        "/api/synthetic/research/series?scenario=stress&location_id=1"
        "&start=2024-06-01T00:00:00Z&end=2024-06-03T00:00:00Z").json()
    assert len(series["series"]) == 49 and series["series"][0]["ground_truth"]["research_view_only"]
    capped = client.get(
        "/api/synthetic/research/series?scenario=stress&location_id=1"
        "&start=2024-01-01T00:00:00Z&end=2024-12-31T00:00:00Z")
    assert capped.status_code == 422


def test_research_requests_reject_unpublished_unknown_and_naive_inputs(client, research_dir):
    assert client.get(
        "/api/synthetic/research/frame?scenario=realistic&timestamp=2024-06-01T10:00:00Z").status_code == 503
    _publish(research_dir / "realistic")
    load_research_scenario.cache_clear()
    assert client.get(
        "/api/synthetic/research/frame?scenario=nope&timestamp=2024-06-01T10:00:00Z").status_code == 422
    assert client.get(
        "/api/synthetic/research/frame?scenario=realistic&timestamp=2024-06-01T10:00:00").status_code == 422
    assert client.get(
        "/api/synthetic/research/frame?scenario=realistic&timestamp=2024-06-01T10:30:00Z").status_code == 422


def test_isotonic_calibrator_is_applied_to_probabilities(research_dir):
    from sklearn.isotonic import IsotonicRegression

    scenario_dir = research_dir / "stress"
    _publish(scenario_dir, scenario="stress")
    model_path = scenario_dir / "research_model.joblib"
    bundle = joblib.load(model_path)
    grid = np.linspace(0, 1, 21)
    bundle["calibrator"] = IsotonicRegression(out_of_bounds="clip").fit(grid, (grid > 0.5).astype(int))
    bundle["calibration"] = "isotonic"
    joblib.dump(bundle, model_path)
    load_research_scenario.cache_clear()

    scenario = load_research_scenario("stress", str(scenario_dir))
    row = scenario.weather_row(1, pd.Timestamp("2024-06-01T10:00:00Z"))
    result = scenario.predict_row(row)
    raw = bundle["model"].predict_proba(
        pd.DataFrame([row[FEATURES].astype(float)]))[:, 1][0]
    assert result["probability"] == pytest.approx(float(bundle["calibrator"].predict([raw])[0]))
    assert result["probability"] != pytest.approx(raw, abs=1e-9)
