"""Prepare next-24-hour flood-stage observations from public USGS gauge records.

From backend: python -m ai.river.data --start 2020-01-01 --end 2025-12-31
Target: maximum observed gauge stage during a complete UTC day >= the documented
NOAA minor-flood threshold. Inputs end at least 24 hours before that day begins.
This verifies gauge flood-stage exceedance, not all flooding in a town.
"""

import argparse
import gzip
import json
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from ai.inspection import dataset_sha256, write_json

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT.parent / "data" / "river"
USGS_URL = "https://waterservices.usgs.gov/nwis/iv/"
NOAA_URL = "https://api.water.noaa.gov/nwps/v1/gauges/"
FEATURES = [
    "margin_lag2_ft", "margin_lag3_ft", "margin_lag4_ft",
    "margin_lag7_ft", "mean_margin_lag2_ft", "range_lag2_ft",
    "rise_1d_ft", "rise_2d_ft", "week_max_margin_ft", "week_mean_margin_ft",
    "season_sin", "season_cos", "flood_stage_ft",
]
INPUT_COLUMNS = FEATURES + ["area_id"]


def read_sites(path: Path) -> pd.DataFrame:
    sites = pd.read_csv(path, dtype={"usgs_id": str})
    required = {"area_id", "name", "usgs_id", "noaa_id", "flood_stage_ft", "threshold_source", "river_system"}
    if not required <= set(sites) or sites.empty or sites[list(required)].isna().any().any():
        raise ValueError("Sites need identifiers, a flood threshold and its source")
    if sites["area_id"].duplicated().any() or sites["usgs_id"].duplicated().any():
        raise ValueError("Each area and USGS gauge must be unique")
    if not sites["usgs_id"].str.fullmatch(r"\d{8}").all():
        raise ValueError("Preserve eight-digit USGS identifiers including leading zeros")
    if not pd.to_numeric(sites["flood_stage_ft"], errors="raise").gt(0).all():
        raise ValueError("Flood stages must be positive feet above the gauge datum")
    return sites


def extract_observations(payload: dict, site_id: str) -> pd.Series:
    matching = [s for s in payload["value"]["timeSeries"]
                if s["sourceInfo"]["siteCode"][0]["value"] == site_id
                and s["variable"]["variableCode"][0]["value"] == "00065"]
    if len(matching) != 1:
        raise ValueError(f"Expected exactly one gauge-height series for {site_id}")
    series = matching[0]
    if series["variable"]["unit"]["unitCode"] != "ft":
        raise ValueError("Gauge measurements must use feet to match NOAA thresholds")
    if len(series["values"]) != 1:
        raise ValueError("Ambiguous gauge measurement methods")
    values = series["values"][0]["value"]
    if not values:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([], tz="UTC"))
    frame = pd.DataFrame(values)
    times = pd.to_datetime(frame["dateTime"], utc=True, errors="raise")
    if times.duplicated().any():
        raise ValueError("Duplicate observation timestamps")
    numbers = pd.to_numeric(frame["value"], errors="coerce")
    # Only approved, non-estimated observations support this POC's labels.
    approved = frame["qualifiers"].map(lambda items: "A" in items and "e" not in items)
    valid = approved & np.isfinite(numbers) & numbers.ne(series["variable"]["noDataValue"])
    return pd.Series(numbers.where(valid).to_numpy(), index=times).sort_index()


def daily_observations(observations: pd.Series, start: str, end: str) -> pd.DataFrame:
    """Require every 15-minute UTC slot, with no interpolation or filled gaps."""
    index = pd.date_range(start, pd.Timestamp(end) + pd.Timedelta(days=1), freq="15min", inclusive="left", tz="UTC")
    quarter_hour = observations.reindex(index)
    grouped = quarter_hour.resample("D")
    daily = grouped.agg(["count", "max", "min", "mean"])
    complete = daily["count"].eq(96)
    daily.loc[~complete, ["max", "min", "mean"]] = np.nan
    daily["complete"] = complete
    return daily


def build_area_dataset(daily: pd.DataFrame, site: dict) -> pd.DataFrame:
    """All lag/rolling operations happen on a full calendar, before dropping gaps."""
    threshold = float(site["flood_stage_ft"])
    margin = daily["max"] - threshold
    result = pd.DataFrame(index=daily.index)
    result["area_id"] = site["area_id"]
    result["river_system"] = site["river_system"]
    result["forecast_date"] = daily.index.strftime("%Y-%m-%d")
    result["issued_at"] = daily.index.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    result["window_end"] = (daily.index + pd.Timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    # Latest used sample is 23:45 on day D-2, 24h15m before issue.
    result["last_input_observed_at"] = (daily.index - pd.Timedelta(hours=24, minutes=15)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    for lag in (2, 3, 4, 7):
        result[f"margin_lag{lag}_ft"] = margin.shift(lag)
    result["mean_margin_lag2_ft"] = (daily["mean"] - threshold).shift(2)
    result["range_lag2_ft"] = (daily["max"] - daily["min"]).shift(2)
    result["rise_1d_ft"] = margin.shift(2) - margin.shift(3)
    result["rise_2d_ft"] = margin.shift(2) - margin.shift(4)
    result["week_max_margin_ft"] = margin.shift(2).rolling(7, min_periods=7).max()
    result["week_mean_margin_ft"] = margin.shift(2).rolling(7, min_periods=7).mean()
    angle = 2 * np.pi * (daily.index.dayofyear - 1) / np.where(daily.index.is_leap_year, 366, 365)
    result["season_sin"], result["season_cos"] = np.sin(angle), np.cos(angle)
    result["flood_stage_ft"] = threshold
    result["target_max_stage_ft"] = daily["max"]
    result["observed_flood_stage"] = (daily["max"] >= threshold).astype(float).where(daily["complete"])
    result["approved_samples"] = daily["count"]
    result["usgs_id"] = site["usgs_id"]
    result["label_source"] = f"https://waterdata.usgs.gov/monitoring-location/{site['usgs_id']}/"
    result["threshold_source"] = site["threshold_source"]
    result = result.dropna(subset=FEATURES + ["observed_flood_stage"])
    result["observed_flood_stage"] = result["observed_flood_stage"].astype(int)
    return result.reset_index(drop=True)


def download(sites_path: Path, start: str, end: str, output: Path) -> dict:
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first < date(2020, 1, 1) or last < first or last >= datetime.now(timezone.utc).date():
        raise ValueError("Use completed dates from 2020 onward, after the documented 2019 threshold changes")
    sites = read_sites(sites_path)
    raw = output / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    provenance = []
    chunks = {site_id: [] for site_id in sites["usgs_id"]}
    with httpx.Client(timeout=180, follow_redirects=True) as client:
        for site in sites.to_dict(orient="records"):
            path = raw / f"noaa-{site['noaa_id'].lower()}.json"
            if not path.exists():
                response = client.get(NOAA_URL + site["noaa_id"].lower())
                response.raise_for_status()
                write_json(path, {"url": str(response.url), "retrieved_at": datetime.now(timezone.utc).isoformat(), "payload": response.json()})
            metadata = json.loads(path.read_text())["payload"]
            if metadata["usgsId"] != site["usgs_id"] or metadata["flood"]["stageUnits"] != "ft" or metadata["flood"]["categories"]["minor"]["stage"] != site["flood_stage_ft"]:
                raise ValueError(f"NOAA/USGS threshold or gauge mismatch for {site['area_id']}")
            provenance.append({"file": str(path.relative_to(output)), "sha256": dataset_sha256(path), "url": NOAA_URL + site["noaa_id"].lower()})
        for year in range(first.year, last.year + 1):
            chunk_start = max(first, date(year, 1, 1)).isoformat()
            chunk_end = (pd.Timestamp(min(last, date(year, 12, 31))) + pd.Timedelta(days=1)).date().isoformat()
            url = str(httpx.URL(USGS_URL, params={
                "format": "json", "sites": ",".join(sites["usgs_id"]), "parameterCd": "00065",
                "startDT": chunk_start + "T00:00Z", "endDT": chunk_end + "T00:00Z", "siteStatus": "all",
            }))
            path = raw / f"usgs-{'-'.join(sites['usgs_id'])}-{chunk_start}-{chunk_end}.json.gz"
            if not path.exists():
                response = client.get(url)
                response.raise_for_status()
                cached = {"url": url, "retrieved_at": datetime.now(timezone.utc).isoformat(), "payload": response.json()}
                temporary = path.with_suffix(".tmp")
                with gzip.open(temporary, "wt", encoding="utf-8") as handle:
                    json.dump(cached, handle)
                temporary.replace(path)
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                cached = json.load(handle)
            if cached["url"] != url:
                raise ValueError("Cached gauge request changed; choose another output directory")
            for site_id in sites["usgs_id"]:
                values = extract_observations(cached["payload"], site_id)
                chunks[site_id].append(values[(values.index >= pd.Timestamp(chunk_start, tz="UTC")) & (values.index < pd.Timestamp(chunk_end, tz="UTC"))])
            provenance.append({"file": str(path.relative_to(output)), "url": url, "sha256": dataset_sha256(path), "retrieved_at": cached["retrieved_at"]})
            print(f"Downloaded and validated gauge observations for {year}", flush=True)
    frames, coverage = [], []
    for site in sites.to_dict(orient="records"):
        observations = pd.concat(chunks[site["usgs_id"]]).sort_index()
        if observations.index.duplicated().any():
            raise ValueError("Overlapping gauge archive chunks")
        daily = daily_observations(observations, start, end)
        frame = build_area_dataset(daily, site)
        frames.append(frame)
        coverage.append({"area_id": site["area_id"], "calendar_days": len(daily), "complete_observed_days": int(daily["complete"].sum()), "usable_rows_with_history": len(frame), "positive_rows": int(frame["observed_flood_stage"].sum())})
    dataset = pd.concat(frames, ignore_index=True).sort_values(["forecast_date", "area_id"])
    if dataset.empty:
        raise ValueError("No complete observation windows and input history")
    dataset.to_csv(output / "dataset.csv", index=False)
    report = {
        "dataset": "USGS approved 15-minute gauge observations with NOAA flood thresholds",
        "target": "At least one observed stage >= NOAA minor-flood stage during next UTC 24 hours",
        "geography": "Iowa River and Passaic River gauges, United States; not Fiji",
        "start": start, "end": end, "rows": len(dataset),
        "positive_rows": int(dataset["observed_flood_stage"].sum()),
        "negative_rows": int(dataset["observed_flood_stage"].eq(0).sum()),
        "dataset_sha256": dataset_sha256(output / "dataset.csv"), "coverage": coverage,
        "quality": "All 96 quarter-hour slots approved and non-estimated; gaps exclude the entire target day and affected lag windows",
        "input_cutoff": "Latest measurement is 24 hours 15 minutes before issue; revised archival data are not a real-time availability audit",
        "threshold_policy": "Fixed NOAA thresholds from the documented Iowa 2019 change and Passaic historical flood summary, cross-checked against retrieved gauge metadata",
        "limitations": ["Station-specific river flood-stage exceedance, not town-wide inundation or flash-flood ground truth.", "Peaks between quarter-hour samples may be missed.", "Approved records can include retrospective revisions.", "Some gauges share a river and are correlated; geographical transfer is not demonstrated."],
        "sources": provenance,
    }
    write_json(output / "manifest.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sites", type=Path, default=ROOT / "sites.csv")
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--output", type=Path, default=DATA_DIR)
    args = parser.parse_args()
    try:
        report = download(args.sites, args.start, args.end, args.output)
    except (ValueError, KeyError, OSError, httpx.HTTPError) as error:
        parser.exit(1, f"River data preparation failed: {error}\n")
    print(f"Prepared {report['rows']} area-days: {report['positive_rows']} flood-stage and {report['negative_rows']} below-stage observations.")


if __name__ == "__main__":
    main()
