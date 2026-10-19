"""Standalone polling worker: python -m app.services.weather_ingestion [--once]."""
import argparse
import logging
import time

import httpx
from pydantic import TypeAdapter
from sqlalchemy import select, text

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models.location import Location
from app.schemas.weather import WeatherCreate
from app.services.weather_service import insert_observation, observations, present

log = logging.getLogger(__name__)


def fetch(settings):
    if not settings.weather_feed_url:
        raise ValueError("WEATHER_FEED_URL is required when ingestion is enabled")
    headers = {}
    if settings.weather_feed_token:
        headers["Authorization"] = f"Bearer {settings.weather_feed_token.get_secret_value()}"
    with httpx.Client(timeout=settings.weather_timeout_seconds, follow_redirects=False) as client:
        response = client.get(settings.weather_feed_url, headers=headers)
        response.raise_for_status()
        payload = response.json()
    # Source identity is configuration-controlled, never accepted from the remote payload.
    if not isinstance(payload, list) or len(payload) > 1000:
        raise ValueError("Feed must contain at most 1000 observations")
    kind = "synthetic" if settings.weather_feed_synthetic else "provider"
    return TypeAdapter(list[WeatherCreate]).validate_python([
        {**item, "source": settings.weather_feed_source, "source_type": kind} for item in payload
    ])


def run_once(settings=None, factory=None, fetcher=fetch, sleep=time.sleep):
    settings = settings or get_settings()
    if not settings.weather_ingestion_enabled:
        log.info("Weather ingestion disabled")
        return {"status": "disabled"}
    factory = factory or get_session_factory()
    for attempt in range(settings.weather_retry_attempts):
        try:
            with factory() as db:
                # One transaction/poll across worker processes; released on commit/rollback.
                if db.bind.dialect.name == "postgresql" and not db.scalar(
                    text("SELECT pg_try_advisory_xact_lock(31420261020)")
                ):
                    return {"status": "busy"}
                records = fetcher(settings)
                created = sum(insert_observation(db, row)[1] for row in records)
                db.commit()
                stale_locations = []
                for location_id in db.scalars(select(Location.id).where(Location.is_active.is_(True))):
                    rows = observations(db, location_id, synthetic=settings.weather_feed_synthetic,
                                        source=settings.weather_feed_source, limit=1)
                    if not rows or present(rows[0]).stale:
                        stale_locations.append(location_id)
                if stale_locations:
                    log.warning("Weather feed missing/stale at location IDs %s", stale_locations)
                log.info("Weather poll succeeded: received=%s created=%s", len(records), created)
                return {"status": "ok", "received": len(records), "created": created,
                        "stale_location_ids": stale_locations}
        except Exception as error:
            # Do not log credential-bearing URLs, payloads, or exception text.
            log.error("Weather poll failed attempt=%s error_type=%s", attempt + 1, type(error).__name__)
            if attempt + 1 < settings.weather_retry_attempts:
                sleep(min(60, 2 ** attempt))
    return {"status": "failed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.weather_ingestion_enabled:
        log.info("Weather ingestion disabled; exiting")
        return
    while True:
        result = run_once(settings)
        if args.once:
            raise SystemExit(1 if result["status"] == "failed" else 0)
        time.sleep(settings.weather_poll_seconds)


if __name__ == "__main__":
    main()
