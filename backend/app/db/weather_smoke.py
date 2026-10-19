"""Exercise real configured PostgreSQL and API with a temporary synthetic reading.

Requires an existing approved MET admin and migrated schema. Removes only its own
unique-source demo reading; never inserts invented measurements into genuine storage.
"""
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.security import create_access_token
from app.db.session import get_session_factory
from app.main import app
from app.models import AccountStatus, DemoWeatherObservation, Location, User, UserRole


def main():
    factory = get_session_factory()
    source = "smoke-" + uuid4().hex
    with factory() as db:
        admin = db.scalar(select(User).where(User.role == UserRole.MET_ADMIN,
                          User.status == AccountStatus.APPROVED, User.is_active.is_(True)))
        ids = list(db.scalars(select(Location.id).where(Location.is_active.is_(True))))
        if admin is None or not ids:
            raise RuntimeError("An approved MET admin and monitored locations are required")
        token = create_access_token(admin.id)
    try:
        with TestClient(app) as client:
            for location_id in ids:
                data = {"location_id": location_id, "observed_at": datetime.now(timezone.utc).isoformat(),
                        "source": source, "source_type": "synthetic", "rainfall_mm": 12.5,
                        "rainfall_period_minutes": 60, "temperature_c": 27.2}
                response = client.post("/api/admin/weather/observations", json=data,
                                       headers={"Authorization": f"Bearer {token}"})
                assert response.status_code == 201, response.text
                with factory() as db:
                    stored = db.get(DemoWeatherObservation, response.json()["id"])
                    assert stored.rainfall_mm == 12.5
                url = f"/api/weather/latest?location_id={location_id}&dataset=synthetic&source={source}"
                result = client.get(url).json()
                assert result["observation"]["id"] == response.json()["id"]
                assert client.get(f"/api/weather/observations?location_id={location_id}&dataset=synthetic&source={source}").json()["observations"]
                assert client.get(f"/api/weather/latest?location_id={location_id}&source={source}").json()["status"] == "no_data"
                print(f"location={location_id} POST=201 separate-session=persisted GET=200 source_type=synthetic rainfall_mm=12.5")
    finally:
        with factory() as db:
            db.execute(delete(DemoWeatherObservation).where(DemoWeatherObservation.source == source))
            db.commit()
    print(f"Verified {len(ids)} locations; temporary synthetic readings cleaned up.")


if __name__ == "__main__":
    main()
