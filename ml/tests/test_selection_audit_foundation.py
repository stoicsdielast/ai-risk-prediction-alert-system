import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.audit02_selection import transitions
from ml.config import HOLDOUT_STATIONS, TARGET
from ml.foundation_worker import asset_digest, predict_request
from ml.refinement import FEATURE_SETS
from ml.training03 import context_sample, inner_folds, station_macro_recall


def test_detection_transition_counts_distinguish_losses_and_recoveries():
    actual = transitions([1, 1, 1, 1, 0], [True, True, False, False, True], [True, False, True, False, False])
    assert actual == {"both_detected": 1, "lost_detection": 1, "recovered_detection": 1, "both_missed": 1}


def fixture_development():
    rows = []
    for station in ["A", "B", "C", "D", "E", "F", "G", "H"]:
        for i in range(8):
            rows.append({"station_id": station, "date": pd.Timestamp("2021-01-01") + pd.Timedelta(days=i),
                         "stage": "train", "selection_hash": str(i) + station, TARGET: i % 2})
    rows.append({"station_id": "A", "date": pd.Timestamp("2023-01-01"), "stage": "selection", "selection_hash": "000", TARGET: 1})
    return pd.DataFrame(rows)


def test_inner_contexts_exclude_query_stations_outer_stations_and_future_records():
    data = fixture_development(); folds = inner_folds(data)
    assert len(folds) == 4 and set(sum(folds.values(), [])) == set("ABCDEFGH")
    for held in folds.values():
        context = context_sample(data, FEATURE_SETS["baseline"], 10, held)
        assert not context.station_id.isin(held).any()
        assert context.stage.eq("train").all() and context.date.lt("2022-01-01").all()
    bad = data.copy(); bad.loc[0, "station_id"] = HOLDOUT_STATIONS[0]
    with pytest.raises(ValueError, match="Outer holdout"):
        inner_folds(bad)


def test_context_keys_are_target_independent_and_identical_across_feature_sets():
    data = fixture_development()
    first = context_sample(data, FEATURE_SETS["baseline"], 12)
    data[TARGET] = 1 - data[TARGET]
    second = context_sample(data.sample(frac=1, random_state=8), FEATURE_SETS["hydrology"], 12)
    assert first.selection_hash.tolist() == second.selection_hash.tolist()


def test_macro_recall_reports_positive_station_denominator():
    data = pd.DataFrame({"station_id": ["A", "A", "B", "C"], TARGET: [1, 1, 1, 0]})
    macro, count = station_macro_recall(data, [.9, .1, .9, .1], .5)
    assert macro == .75 and count == 2


def test_worker_context_labels_never_include_query_labels_and_class_order_is_checked(tmp_path):
    context = pd.DataFrame({"rainfall_local_mm": [1., 2., 3., 4.], "label": [0, 0, 1, 1]})
    query = pd.DataFrame({"rainfall_local_mm": [10., 11.], "row_id": [9, 5]})
    context.to_parquet(tmp_path / "context.parquet"); query.to_parquet(tmp_path / "query.parquet")
    captured = {}
    class FakeEstimator:
        classes_ = np.array([1, 0])  # Confirm positive-class index is not assumed.
        def fit(self, x, y):
            captured["training_values"] = x.rainfall_local_mm.tolist(); captured["labels"] = y.tolist()
            return self
        def predict_proba(self, x): return np.tile([.7, .3], (len(x), 1))
    request = {"features": ["rainfall_local_mm"], "context": str(tmp_path/"context.parquet"),
               "query": str(tmp_path/"query.parquet"), "model": "tabfm", "asset": {}, "device": "cpu", "query_batch_rows": 1}
    result = predict_request(request, lambda *args: FakeEstimator())
    assert captured == {"training_values": [1., 2., 3., 4.], "labels": [0, 0, 1, 1]}
    assert result.row_id.tolist() == [9, 5] and result.probability.tolist() == [.7, .7]
    query["label"] = [1, 0]; query.to_parquet(tmp_path/"query.parquet")
    with pytest.raises(ValueError, match="query labels are forbidden"):
        predict_request(request, lambda *args: FakeEstimator())


def test_checkpoint_digest_detects_changes(tmp_path):
    (tmp_path/"config.json").write_text('{}')
    (tmp_path/"weights.bin").write_bytes(b'first')
    first = asset_digest(tmp_path)
    (tmp_path/"weights.bin").write_bytes(b'second')
    assert asset_digest(tmp_path) != first


def test_saved_audit_reports_no_sigmoid_detection_loss_when_available():
    path = Path("ml/runs/training-02-selection-audit/sigmoid_operating_point_invariance.json")
    if not path.exists(): pytest.skip("Run the frozen selection audit")
    assert all(r["evaluation_decision_disagreements"] == 0 for r in json.loads(path.read_text()))


def test_pinned_foundation_sources_and_v2_checkpoint_are_explicit():
    sources = json.loads(Path("ml/foundation/sources.json").read_text())
    assert set(sources) == {"tabfm", "tabpfn", "tabicl"}
    assert all(len(r["commit"]) == 40 for r in sources.values())
    assert "v2-20260212" in sources["tabicl"]["checkpoint"]


def test_threshold_block_cannot_reselect_the_model_when_chosen_candidate_is_infeasible(tmp_path, monkeypatch):
    """Synthetic orchestration regression: H1 winner fails H2, so do not pick runner-up."""
    from ml import training03
    import time
    rows = []
    for sid in "ABCD":
        for stage, date in [("train", "2021-01-01"), ("calibration", "2022-07-01"),
                            ("selection", "2023-01-01"), ("threshold", "2023-07-01")]:
            for label in [0, 1]:
                row = {c: 1. for c in FEATURE_SETS["baseline"]}
                row.update(station_id=sid, stage=stage, date=pd.Timestamp(date), selection_hash=sid+str(label), **{TARGET: label})
                rows.append(row)
    pd.DataFrame(rows).to_parquet(tmp_path/"development.parquet", index=False)
    variants = [{"id": name, "model": name, "feature_set": "baseline", "context_cap": 100} for name in ["alpha", "beta"]]
    plan = {"variants": variants, "inner_station_folds": {str(i): [sid] for i, sid in enumerate("ABCD")},
            "false_alert_budget": 0., "resource_limits": {"validation_total_seconds": 60, "timeout_seconds": 10}}
    assets_path = tmp_path/"assets.json"; assets_path.write_text(json.dumps({"alpha": {}, "beta": {}}))
    monkeypatch.setattr(training03, "verify", lambda out: plan)
    monkeypatch.setattr(training03, "preflight", lambda *args: {"models": {name: {"status": "ready"} for name in ["alpha", "beta"]}})
    monkeypatch.setattr(training03, "fit_sigmoid", lambda *args: None)
    monkeypatch.setattr(training03, "apply_sigmoid", lambda model, p: np.asarray(p))
    def fake_worker(out, job_id, context, query, variant, asset, limits):
        (out/"jobs"/job_id).mkdir(parents=True)
        probabilities = []
        for _, row in query.iterrows():
            if row.stage == "threshold" and variant["id"] == "alpha":
                p = .1 if row[TARGET] else .9  # H2 alpha fails a zero-FP budget.
            elif row.stage == "selection" and variant["id"] == "beta":
                p = (.9 if row.station_id in "AB" else .05) if row[TARGET] else .5
            else: p = .9 if row[TARGET] else .1
            probabilities.append(p)
        return pd.Series(probabilities, index=query.row_id)
    monkeypatch.setattr(training03, "run_worker", fake_worker)
    with pytest.raises(ValueError, match="No nontrivial threshold"):
        training03.validate(tmp_path, assets_path)
    chosen = json.loads((tmp_path/"validation_choice.json").read_text())
    assert chosen["candidate"].startswith("alpha__")
    assert not (tmp_path/"validation_lock.json").exists()
