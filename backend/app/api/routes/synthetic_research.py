"""Lecturer-facing research view over the Synthetic V3 scenario bundles.

Read-only; creates no predictions of record, no alerts, and never mutates the
deployed V1 configuration. Ground truth is returned only under the
``ground_truth`` key for display and is never a model input.
"""
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.services.synthetic_inference import NOTICE
from app.services.synthetic_research import (
    SCENARIOS,
    ResearchScenario,
    get_research_scenario,
    list_scenarios,
)

router = APIRouter(prefix="/api/synthetic/research", tags=["synthetic research demonstration"])
ScenarioName = Literal["controlled", "realistic", "stress"]


def get_scenario(name: ScenarioName = Query(...)) -> ResearchScenario:
    try:
        return get_research_scenario(name)
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


def timestamp_utc(timestamp: datetime):
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise HTTPException(422, "Timestamp requires an explicit timezone")
    timestamp = timestamp.astimezone(timezone.utc)
    if timestamp.minute or timestamp.second or timestamp.microsecond:
        raise HTTPException(422, "Choose an exact hourly timestamp")
    return timestamp


@router.get("/info")
def info():
    return {"source_type": "synthetic", "research_only": True, "notice": NOTICE,
            "scenarios": list_scenarios(),
            "v1_serving_unchanged": True,
            "note": "Historical research replay against simulator outcomes. "
                    "Provisional research risk bands only; not a forecast, not an emergency warning."}


@router.get("/frame")
def frame(timestamp: datetime, scenario: ScenarioName = Query(...)):
    return get_scenario(scenario).frame(timestamp_utc(timestamp))


@router.get("/storms")
def storms(scenario: ScenarioName = Query(...)):
    return get_scenario(scenario).storms()


@router.get("/series")
def series(location_id: int = Query(..., ge=1, le=12), scenario: ScenarioName = Query(...),
           start: datetime = Query(...), end: datetime = Query(...)):
    start, end = timestamp_utc(start), timestamp_utc(end)
    if end <= start:
        raise HTTPException(422, "end must be after start")
    try:
        return get_scenario(scenario).series(location_id, start, end)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
