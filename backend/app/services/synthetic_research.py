"""Research-only scenario inference for Synthetic V3.

Loads per-scenario research bundles published by ``ml.synthetic.finalize_v3``
and serves predictions for the lecturer-facing research view. Ground truth is
loaded from a separate file and is never a model input; the deployed V1
serving path in ``app.services.synthetic_inference`` is untouched.
"""
from functools import lru_cache
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.services.synthetic_inference import NOTICE, risk_category

SCENARIOS = ("controlled", "realistic", "stress")
TRUTH_COLUMNS = {"flood_occurred", "flood_within_24h", "flood_within_48h",
                 "flood_within_72h", "forecast_eligible", "event_id", "scenario_id", "stage"}


def research_root() -> Path:
    return Path(get_settings().synthetic_research_dir).resolve()


def scenario_path(scenario: str) -> Path:
    return research_root() / scenario


def list_scenarios():
    entries = []
    for scenario in SCENARIOS:
        meta_path = scenario_path(scenario) / "research_scenario.json"
        if not meta_path.exists():
            entries.append({"scenario": scenario, "status": "not_published", "research_only": True})
            continue
        meta = json.loads(meta_path.read_text())
        entries.append({"scenario": scenario, "status": "ready", "research_only": True,
                        "model_version": meta["model_version"], "selected_candidate": meta["selected_candidate"],
                        "calibration": meta["calibration"], "threshold": meta["threshold"],
                        "n_features": meta["n_features"], "time_range": meta["time_range"],
                        "observations": meta["observations"], "events": meta["events"],
                        "partitions": meta["partitions"], "held_location_ids": meta["held_location_ids"],
                        "bootstrap_intervals": meta["bootstrap_intervals"],
                        "ground_truth_policy": meta["ground_truth_policy"]})
    return entries


class ResearchScenario:
    """One published scenario: weather + model on one side, ground truth on the other."""

    def __init__(self, directory: Path, scenario: str):
        self.directory = Path(directory)
        self.scenario = scenario
        manifest = json.loads((self.directory / "research_manifest.json").read_text())
        if manifest.get("source_type") != "synthetic":
            raise ValueError("Not a synthetic research bundle")
        self.meta = json.loads((self.directory / "research_scenario.json").read_text())
        self.bundle = joblib.load(self.directory / "research_model.joblib")
        if self.bundle.get("source_type") != "synthetic":
            raise ValueError("Bundle is not marked synthetic")
        leaked = sorted(set(self.bundle["features"]) & TRUTH_COLUMNS)
        if leaked:
            raise ValueError(f"Feature list contains truth columns: {leaked}")
        self.weather = pd.read_parquet(self.directory / "research_features.parquet").set_index(
            ["location_id", "timestamp"]).sort_index()
        self.weather_columns = list(self.meta.get("weather_columns") or [])
        self.truth = pd.read_parquet(self.directory / "research_truth.parquet").set_index(
            ["location_id", "timestamp"]).sort_index()
        self.events = pd.read_csv(self.directory / "research_events.csv",
                                  parse_dates=["event_start", "event_end"])
        self.locations = pd.read_csv(self.directory / "research_locations.csv")
        self.location_index = {int(r.location_id): r for r in self.locations.itertuples()}

    def predict_row(self, row) -> dict:
        """Score one weather row. Takes no truth argument by construction."""
        if not bool(row.history_ready):
            return {"status": "insufficient_history", "probability": None, "risk_category": None}
        frame = pd.DataFrame([row[self.bundle["features"]].astype(float)])
        p = float(self.bundle["model"].predict_proba(frame)[:, 1][0])
        if self.bundle["calibrator"] is not None:
            if self.bundle.get("calibration") == "sigmoid":
                clipped = np.clip(p, 1e-6, 1 - 1e-6)
                p = float(self.bundle["calibrator"].predict_proba(
                    np.log(clipped / (1 - clipped)).reshape(-1, 1))[0, 1])
            else:
                p = float(self.bundle["calibrator"].predict([p])[0])
        return {"status": "ok", "probability": p,
                "risk_category": risk_category(p, self.bundle["threshold"])}

    def truth_row(self, location_id, timestamp) -> dict:
        key = (int(location_id), pd.Timestamp(timestamp))
        if key not in self.truth.index:
            return {"available": False, "research_view_only": True}
        r = self.truth.loc[key]
        return {"available": True, "flood_occurred": bool(r.flood_occurred),
                "flood_within_24h": bool(r.flood_within_24h),
                "event_id": None if pd.isna(r.event_id) else str(r.event_id),
                "partition": None if pd.isna(r.stage) else str(r.stage),
                "research_view_only": True}

    def weather_row(self, location_id, timestamp):
        key = (int(location_id), pd.Timestamp(timestamp))
        if key not in self.weather.index:
            raise ValueError("Timestamp or location is outside the published scenario")
        return self.weather.loc[key]

    def entry(self, location_id, timestamp) -> dict:
        row = self.weather_row(location_id, timestamp)
        location = self.location_index.get(int(location_id))
        result = {"source_type": "synthetic", "research_only": True, "notice": NOTICE,
                  "scenario": self.scenario, "model_version": self.bundle["model_version"],
                  "location_id": int(location_id),
                  "slug": None if location is None else location.slug,
                  "name": None if location is None else location.name,
                  "division": None if location is None else location.division,
                  "latitude": None if location is None else float(location.latitude),
                  "longitude": None if location is None else float(location.longitude),
                  "timestamp": pd.Timestamp(timestamp).isoformat(), "horizon_hours": 24,
                  "threshold": float(self.bundle["threshold"]), "provisional_risk": True,
                  "weather": {c: (None if pd.isna(row[c]) else float(row[c]))
                              for c in self.weather_columns},
                  **self.predict_row(row)}
        result["ground_truth"] = self.truth_row(location_id, timestamp)
        return result

    def frame(self, timestamp):
        stamp = pd.Timestamp(timestamp)
        entries = []
        for location_id in sorted(int(x) for x in self.weather.index.levels[0]):
            if (location_id, stamp) not in self.weather.index:
                continue
            entries.append(self.entry(location_id, stamp))
        return {"source_type": "synthetic", "research_only": True, "notice": NOTICE,
                "scenario": self.scenario, "model_version": self.bundle["model_version"],
                "threshold": float(self.bundle["threshold"]),
                "timestamp": stamp.isoformat(), "locations": entries}

    def series(self, location_id, start, end, max_days=62):
        start, end = pd.Timestamp(start), pd.Timestamp(end)
        if (end - start).total_seconds() > max_days * 86400:
            raise ValueError(f"Series window is capped at {max_days} days")
        window = self.weather.loc[int(location_id)].loc[start:end]
        rows = [self.entry(location_id, timestamp) for timestamp in window.index]
        return {"source_type": "synthetic", "research_only": True, "notice": NOTICE,
                "scenario": self.scenario, "location_id": int(location_id),
                "model_version": self.bundle["model_version"],
                "start": start.isoformat(), "end": end.isoformat(), "series": rows}

    def storms(self):
        storms = [{"event_id": r.event_id,
                   "scenario_id": None if pd.isna(r.scenario_id) else r.scenario_id,
                   "location_id": int(r.location_id), "name": r.name, "slug": r.slug,
                   "start": r.event_start.isoformat(), "end": r.event_end.isoformat(),
                   "severity": r.severity, "duration_hours": float(r.duration_hours),
                   "max_river_level_m": float(r.max_river_level_m)}
                  for r in self.events.itertuples()]
        storms.sort(key=lambda s: s["start"])
        return {"source_type": "synthetic", "research_only": True, "notice": NOTICE,
                "scenario": self.scenario, "model_version": self.bundle["model_version"],
                "storms": storms}


@lru_cache(maxsize=len(SCENARIOS))
def load_research_scenario(scenario: str, directory: str):
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario}")
    path = Path(directory)
    if not (path / "research_scenario.json").exists():
        raise FileNotFoundError(f"Scenario bundle not published at {path}")
    return ResearchScenario(path, scenario)


def get_research_scenario(scenario: str) -> ResearchScenario:
    try:
        return load_research_scenario(scenario, str(scenario_path(scenario)))
    except FileNotFoundError:
        raise
    except (OSError, ValueError, KeyError, ImportError) as exc:
        raise ValueError(f"Research bundle for {scenario} is unavailable: {exc}") from exc
