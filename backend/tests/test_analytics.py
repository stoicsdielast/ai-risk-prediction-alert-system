"""Admin analytics are read-only, MET-admin only, and never mix genuine/sample/synthetic data."""
import csv
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.security import create_access_token
from app.models import Alert, Division, Location, UserRole
from app.models.prediction import Prediction
from app.models.risk import RiskLevel
from app.models.synthetic import SyntheticDataset, SyntheticPrediction
from app.services import analytics_service as service

NOW = datetime.now(timezone.utc)


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture
def admin(user_factory):
    return user_factory(email="analytics-admin@example.invalid", role=UserRole.MET_ADMIN)


@pytest.fixture
def world(session_factory):
    """Two locations; predictions are inserted explicitly by each test, never by the app."""
    with session_factory() as db:
        a = Location(slug="a", name="Alpha", division=Division.CENTRAL, latitude=-18, longitude=178)
        b = Location(slug="b", name="Bravo", division=Division.WESTERN, latitude=-17, longitude=177)
        db.add_all([a, b])
        db.commit()
        return a.id, b.id


def add_prediction(session_factory, location_id, hours_ago, probability, level, sample=False, version="unit-test-model"):
    with session_factory() as db:
        db.add(Prediction(location_id=location_id, risk_level=level, flood_probability=probability,
                          model_version=version, is_sample=sample, predicted_at=NOW - timedelta(hours=hours_ago)))
        db.commit()


def add_synthetic(session_factory, location_id, when, probability, category):
    with session_factory() as db:
        if db.get(SyntheticDataset, "synthetic-test") is None:
            db.add(SyntheticDataset(version="synthetic-test", metadata_json={}, observation_count=10))
            db.flush()
        db.add(SyntheticPrediction(dataset_version="synthetic-test", location_id=location_id, observed_at=when,
                                   model_version="synthetic-test-model", probability=probability, risk_category=category))
        db.commit()


@pytest.mark.parametrize("path", ["/api/admin/analytics/predictions/overview", "/api/admin/analytics/predictions/trend",
                                  "/api/admin/analytics/models/performance"])
def test_requires_met_admin(client, user_factory, path):
    assert client.get(path).status_code == 401
    community = user_factory(email="analytics-community@example.invalid")
    assert client.get(path, headers=auth(community)).status_code == 403


def test_empty_database_reports_zero_without_fabricating(client, admin):
    body = client.get("/api/admin/analytics/predictions/overview", headers=auth(admin)).json()
    for kind in ("genuine", "sample"):
        summary = body["operational"]["kinds"][kind]
        assert summary["total"] == 0 and summary["freshness"]["latest_at"] is None and summary["freshness"]["stale"] is None
        assert summary["window"]["high_risk"] == 0
    assert body["synthetic"]["total"] == 0 and body["synthetic"]["window_anchor"] is None
    trend = client.get("/api/admin/analytics/predictions/trend", headers=auth(admin)).json()
    assert trend["points"] == [] and trend["data_span"]["available_days"] is None


def test_overview_separates_kinds_and_counts_window(client, admin, world, session_factory):
    a, b = world
    add_prediction(session_factory, a, 2, .9, RiskLevel.VERY_HIGH, sample=True)
    add_prediction(session_factory, a, 30, .6, RiskLevel.HIGH)            # genuine, outside a 1-day window
    add_prediction(session_factory, b, 3, .1, RiskLevel.LOW)
    body = client.get("/api/admin/analytics/predictions/overview?days=1", headers=auth(admin)).json()
    genuine, sample = body["operational"]["kinds"]["genuine"], body["operational"]["kinds"]["sample"]
    assert (genuine["total"], sample["total"]) == (2, 1)
    assert genuine["by_risk"]["HIGH"] == 1 and sample["by_risk"]["VERY_HIGH"] == 1
    assert genuine["window"]["predictions"] == 1 and genuine["window"]["high_risk"] == 0
    assert sample["window"]["high_risk"] == 1 and sample["window"]["locations_with_predictions"] == 1
    assert body["synthetic"]["total"] == 0  # operational rows never leak into the synthetic block
    wider = client.get("/api/admin/analytics/predictions/overview?days=7", headers=auth(admin)).json()
    assert wider["operational"]["kinds"]["genuine"]["window"]["high_risk"] == 1


def test_stale_latest_prediction_is_flagged(client, admin, world, session_factory):
    add_prediction(session_factory, world[0], 60, .3, RiskLevel.MODERATE)
    freshness = client.get("/api/admin/analytics/predictions/overview", headers=auth(admin)).json()[
        "operational"]["kinds"]["genuine"]["freshness"]
    assert freshness["stale"] is True and freshness["age_hours"] > 59
    trend = client.get("/api/admin/analytics/predictions/trend?days=7", headers=auth(admin)).json()
    assert trend["freshness"]["stale"] is True and trend["data_span"]["available_days"] == 3


def test_trend_filters_locations_window_and_labels(client, admin, world, session_factory):
    a, b = world
    add_prediction(session_factory, a, 5, .7, RiskLevel.HIGH)
    add_prediction(session_factory, a, 24 * 10, .2, RiskLevel.MODERATE)
    add_prediction(session_factory, b, 4, .5, RiskLevel.HIGH, sample=True, version="sample-demo-not-a-model-result")
    both = client.get(f"/api/admin/analytics/predictions/trend?days=7&location_id={a}&location_id={b}", headers=auth(admin)).json()
    assert {p["kind"] for p in both["points"]} == {"sample", "genuine"}
    by_kind = {p["kind"]: p for p in both["points"]}
    assert by_kind["genuine"]["horizon_hours"] == 24 and by_kind["genuine"]["model_version"] == "unit-test-model"
    assert by_kind["sample"]["horizon_hours"] is None            # sample rows claim no forecast horizon
    assert len(both["points"]) == 2                                # the 10-day-old row is outside the 7-day window
    only_a = client.get(f"/api/admin/analytics/predictions/trend?days=30&location_id={a}", headers=auth(admin)).json()
    assert {p["location_id"] for p in only_a["points"]} == {a} and len(only_a["points"]) == 2
    assert only_a["points"] == sorted(only_a["points"], key=lambda p: p["timestamp"])
    assert only_a["data_span"]["stored_predictions"] == 2 and only_a["data_span"]["available_days"] == 11  # smallest whole-day window covering a >10-day span


def test_trend_validation(client, admin, world):
    h = auth(admin)
    assert client.get("/api/admin/analytics/predictions/trend?location_id=999", headers=h).status_code == 404
    assert client.get("/api/admin/analytics/predictions/trend?days=0", headers=h).status_code == 422
    assert client.get("/api/admin/analytics/predictions/trend?source=bogus", headers=h).status_code == 422


def test_trend_truncates_instead_of_returning_unbounded_rows(client, admin, world, session_factory, monkeypatch):
    monkeypatch.setattr(service, "MAX_TREND_POINTS", 2)
    for hours in (1, 2, 3):
        add_prediction(session_factory, world[0], hours, .4, RiskLevel.MODERATE)
    body = client.get("/api/admin/analytics/predictions/trend", headers=auth(admin)).json()
    assert len(body["points"]) == 2 and body["truncated"] is True


def test_synthetic_trend_is_separate_and_anchored_to_simulated_time(client, admin, world, session_factory, tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "synthetic_model_dir", tmp_path / "no-model")
    a, _ = world
    add_prediction(session_factory, a, 1, .6, RiskLevel.HIGH)
    when = datetime(2021, 1, 25, 1, tzinfo=timezone.utc)
    add_synthetic(session_factory, a, when, .95, "VERY_HIGH")
    synthetic = client.get("/api/admin/analytics/predictions/trend?source=synthetic&days=7", headers=auth(admin)).json()
    assert synthetic["source_type"] == "synthetic" and len(synthetic["points"]) == 1
    point = synthetic["points"][0]
    assert point["kind"] == "synthetic" and point["risk_level"] == "VERY_HIGH" and point["horizon_hours"] == 24
    assert synthetic["window_end"].startswith("2021-01-25") and "simulated" in synthetic["anchor_kind"]
    assert "Research Demonstration" in synthetic["notice"]
    assert synthetic["risk_band_thresholds"] is None   # no deployed-model metadata configured in this test
    operational = client.get("/api/admin/analytics/predictions/trend?days=7", headers=auth(admin)).json()
    assert [p["kind"] for p in operational["points"]] == ["genuine"]
    overview = client.get("/api/admin/analytics/predictions/overview", headers=auth(admin)).json()
    assert overview["synthetic"]["total"] == 1 and overview["operational"]["kinds"]["genuine"]["total"] == 1


def test_analytics_are_read_only(client, admin, world, session_factory):
    add_prediction(session_factory, world[0], 1, .6, RiskLevel.HIGH)
    for path in ("overview", "trend"):
        assert client.get(f"/api/admin/analytics/predictions/{path}", headers=auth(admin)).status_code == 200
    assert client.get("/api/admin/analytics/models/performance", headers=auth(admin)).status_code == 200
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Prediction)) == 1
        assert db.scalar(select(func.count()).select_from(Alert)) == 0
        assert db.scalar(select(func.count()).select_from(SyntheticPrediction)) == 0
    for method in (client.post, client.put, client.delete, client.patch):
        assert method("/api/admin/analytics/predictions/overview", headers=auth(admin)).status_code == 405


# ----------------------------------------------------------------------- model performance

HEADER = ["candidate", "stage", "rows", "positives", "prevalence", "precision", "recall", "f1",
          "pr_auc_average_precision", "roc_auc", "brier", "confusion_matrix_tn_fp_fn_tp", "event_recall",
          "median_warning_lead_hours"]


def write_run(run, selected="cat", threshold=None):
    run.mkdir(parents=True)
    rows = [
        [selected, "test", 100, 10, .1, .5, .4, .44, .3, .9, .05, "[80, 10, 6, 4]", .75, 6],
        [selected, "train", 400, 40, .1, .9, .9, .9, .9, .99, .01, "[300, 60, 4, 36]", "", ""],
        ["other", "test", 100, 10, .1, .99, .99, .99, .99, .99, .01, "[90, 0, 0, 10]", "", ""],  # must be ignored
    ]
    with (run / "metrics.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(rows)
    (run / "selection_lock.json").write_text(json.dumps({"selected": selected, "dataset_sha256": "abc"}))
    (run / "partition_summary.csv").write_text("stage,rows,positives\ntest,100,10\ntrain,400,40\n")
    (run / "feature_importance.csv").write_text("feature,importance\nrain,30\nsoil,10\nbad,\n")
    if threshold is not None:
        (run / "run_summary.json").write_text(json.dumps({"threshold": threshold}))


@pytest.fixture
def runs_dir(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    monkeypatch.setattr(get_settings(), "research_runs_dir", runs)
    monkeypatch.setattr(get_settings(), "synthetic_model_dir", tmp_path / "no-model")
    return runs


def test_model_performance_without_artifacts_does_not_invent_results(client, admin, runs_dir):
    body = client.get("/api/admin/analytics/models/performance", headers=auth(admin)).json()
    assert body["artifacts_dir_available"] is False and body["deployed_model"] is None
    assert body["v1"]["available"] is False and body["v2"]["available"] is False
    assert [s["available"] for s in body["v3"]] == [False, False, False]
    assert "metrics" not in body["v1"]


def test_model_performance_reads_only_selected_candidate_from_saved_artifacts(client, admin, runs_dir):
    write_run(runs_dir / "synthetic-v1", threshold=0.2)
    write_run(runs_dir / "synthetic-v3" / "stress", selected="lgbm")
    body = client.get("/api/admin/analytics/models/performance", headers=auth(admin)).json()
    v1 = body["v1"]
    assert v1["available"] and v1["selected_candidate"] == "cat" and v1["role"] == "deployed"
    assert [m["stage"] for m in v1["metrics"]] == ["train", "test"]          # chronological stage order, 'other' ignored
    test = v1["metrics"][1]
    assert test["confusion"] == {"tn": 80, "fp": 10, "fn": 6, "tp": 4}
    assert (test["precision"], test["recall"], test["f1"], test["pr_auc"], test["roc_auc"]) == (.5, .4, .44, .3, .9)
    assert v1["metrics"][0]["event_recall"] is None                          # blank CSV cell stays null, not zero
    assert v1["partitions"][0]["stage"] == "train" and v1["partitions"][0]["prevalence"] == .1
    assert [f["feature"] for f in v1["feature_importance"]] == ["rain", "soil"]
    assert v1["feature_importance"][0]["share_percent"] == 75.0             # unparsable value skipped, shares normalised
    assert body["v2"]["available"] is False
    stress = next(s for s in body["v3"] if s["scenario"] == "stress")
    assert stress["available"] and stress["selected_candidate"] == "lgbm"
    assert "must not be ranked" in body["comparability_note"]


def test_model_performance_ignores_corrupt_artifacts(client, admin, runs_dir):
    run = runs_dir / "synthetic-v1"
    write_run(run)
    (run / "selection_lock.json").write_text("{not json")
    body = client.get("/api/admin/analytics/models/performance", headers=auth(admin)).json()
    assert body["v1"]["available"] is False


def test_deployed_model_metadata_and_dataset_overview(client, admin, runs_dir, tmp_path, session_factory, monkeypatch):
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "model_metadata.json").write_text(json.dumps({
        "model_version": "synthetic-fiji-v1-test", "selected_candidate": "cat", "threshold": 0.4,
        "features": ["a", "b"], "source_type": "synthetic", "risk_tiers": "tiers"}))
    monkeypatch.setattr(get_settings(), "synthetic_model_dir", model_dir)
    write_run(runs_dir / "synthetic-v1")
    with session_factory() as db:
        db.add(SyntheticDataset(version="synthetic-fiji-v1", observation_count=525888,
                                metadata_json={"config": {"seed": 314, "start": "2021-01-01"}, "notice": "n"}))
        db.commit()
    body = client.get("/api/admin/analytics/models/performance", headers=auth(admin)).json()
    assert body["deployed_model"]["n_features"] == 2 and body["deployed_model"]["model_version"] == "synthetic-fiji-v1-test"
    assert body["v1"]["threshold"] == 0.4                                    # taken from deployed metadata
    assert body["dataset"]["observation_count"] == 525888
    bands = client.get("/api/admin/analytics/predictions/trend?source=synthetic", headers=auth(admin)).json()["risk_band_thresholds"]
    assert bands["moderate_from"] == pytest.approx(0.2) and bands["high_from"] == 0.4 and bands["very_high_from"] == pytest.approx(0.6)
    assert client.get("/api/admin/analytics/predictions/trend", headers=auth(admin)).json()["risk_band_thresholds"] is None and body["dataset"]["config"]["seed"] == 314
