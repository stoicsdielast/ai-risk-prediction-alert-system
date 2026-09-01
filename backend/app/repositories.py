from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session


# -----------------------------
# LOCATIONS
# -----------------------------

def get_all_locations(db: Session):
    try:
        result = db.execute(
            text("""
                SELECT
                    id,
                    name,
                    latitude,
                    longitude,
                    created_at
                FROM locations
                ORDER BY name;
            """)
        )

        return [dict(row._mapping) for row in result]

    except SQLAlchemyError as error:
        raise RuntimeError(
            "Unable to retrieve locations from the database."
        ) from error


def get_location_by_id(db: Session, location_id: int):
    try:
        result = db.execute(
            text("""
                SELECT
                    id,
                    name,
                    latitude,
                    longitude,
                    created_at
                FROM locations
                WHERE id = :location_id;
            """),
            {"location_id": location_id},
        )

        row = result.fetchone()

        if row is None:
            return None

        return dict(row._mapping)

    except SQLAlchemyError as error:
        raise RuntimeError(
            "Unable to retrieve the requested location."
        ) from error

    # -----------------------------
# WEATHER RECORDS
# -----------------------------

def create_weather_record(
    db: Session,
    location_id: int,
    rainfall: float,
    temperature: float,
    humidity: float,
    river_level: float,
    recorded_at,
):
    try:
        result = db.execute(
            text("""
                INSERT INTO weather_records (
                    location_id,
                    rainfall,
                    temperature,
                    humidity,
                    river_level,
                    recorded_at
                )
                VALUES (
                    :location_id,
                    :rainfall,
                    :temperature,
                    :humidity,
                    :river_level,
                    :recorded_at
                )
                RETURNING
                    id,
                    location_id,
                    rainfall,
                    temperature,
                    humidity,
                    river_level,
                    recorded_at;
            """),
            {
                "location_id": location_id,
                "rainfall": rainfall,
                "temperature": temperature,
                "humidity": humidity,
                "river_level": river_level,
                "recorded_at": recorded_at,
            },
        )

        row = result.fetchone()
        db.commit()

        return dict(row._mapping)

    except IntegrityError as error:
        db.rollback()

        raise ValueError(
            "A weather record already exists for this location and timestamp."
        ) from error

    except SQLAlchemyError as error:
        db.rollback()

        raise RuntimeError(
            "Unable to save the weather record."
        ) from error


def get_latest_weather(db: Session, location_id: int):
    try:
        result = db.execute(
            text("""
                SELECT
                    id,
                    location_id,
                    rainfall,
                    temperature,
                    humidity,
                    river_level,
                    recorded_at
                FROM weather_records
                WHERE location_id = :location_id
                ORDER BY recorded_at DESC
                LIMIT 1;
            """),
            {"location_id": location_id},
        )

        row = result.fetchone()

        if row is None:
            return None

        return dict(row._mapping)

    except SQLAlchemyError as error:
        raise RuntimeError(
            "Unable to retrieve the latest weather record."
        ) from error

    # -----------------------------
# PREDICTIONS
# -----------------------------

def create_prediction(
    db: Session,
    location_id: int,
    risk_score: float,
    risk_level: str,
    generated_at,
):
    try:
        result = db.execute(
            text("""
                INSERT INTO predictions (
                    location_id,
                    risk_score,
                    risk_level,
                    generated_at
                )
                VALUES (
                    :location_id,
                    :risk_score,
                    :risk_level,
                    :generated_at
                )
                RETURNING
                    id,
                    location_id,
                    risk_score,
                    risk_level,
                    generated_at;
            """),
            {
                "location_id": location_id,
                "risk_score": risk_score,
                "risk_level": risk_level,
                "generated_at": generated_at,
            },
        )

        row = result.fetchone()
        db.commit()

        return dict(row._mapping)

    except IntegrityError as error:
        db.rollback()

        raise ValueError(
            "Unable to create prediction. Check the location, risk level, or timestamp."
        ) from error

    except SQLAlchemyError as error:
        db.rollback()

        raise RuntimeError(
            "Unable to save the prediction."
        ) from error


def get_latest_prediction(db: Session, location_id: int):
    try:
        result = db.execute(
            text("""
                SELECT
                    id,
                    location_id,
                    risk_score,
                    risk_level,
                    generated_at
                FROM predictions
                WHERE location_id = :location_id
                ORDER BY generated_at DESC
                LIMIT 1;
            """),
            {"location_id": location_id},
        )

        row = result.fetchone()

        if row is None:
            return None

        return dict(row._mapping)

    except SQLAlchemyError as error:
        raise RuntimeError(
            "Unable to retrieve the latest prediction."
        ) from error

    # -----------------------------
# ALERTS
# -----------------------------

VALID_ALERT_STATUSES = {
    "PENDING",
    "APPROVED",
    "SUPPRESSED",
    "RESOLVED",
}


def create_alert(
    db: Session,
    location_id: int,
    prediction_id: int,
    message: str,
    severity: str,
):
    try:
        result = db.execute(
            text("""
                INSERT INTO alerts (
                    location_id,
                    prediction_id,
                    message,
                    severity,
                    status
                )
                VALUES (
                    :location_id,
                    :prediction_id,
                    :message,
                    :severity,
                    'PENDING'
                )
                RETURNING
                    id,
                    location_id,
                    prediction_id,
                    message,
                    severity,
                    status,
                    suppression_reason,
                    created_at,
                    approved_at;
            """),
            {
                "location_id": location_id,
                "prediction_id": prediction_id,
                "message": message,
                "severity": severity,
            },
        )

        row = result.fetchone()
        db.commit()

        return dict(row._mapping)

    except IntegrityError as error:
        db.rollback()

        raise ValueError(
            "Unable to create alert. Check the location and prediction."
        ) from error

    except SQLAlchemyError as error:
        db.rollback()

        raise RuntimeError(
            "Unable to save the alert."
        ) from error


def get_alert_by_id(db: Session, alert_id: int):
    try:
        result = db.execute(
            text("""
                SELECT
                    id,
                    location_id,
                    prediction_id,
                    message,
                    severity,
                    status,
                    suppression_reason,
                    created_at,
                    approved_at
                FROM alerts
                WHERE id = :alert_id;
            """),
            {"alert_id": alert_id},
        )

        row = result.fetchone()

        if row is None:
            return None

        return dict(row._mapping)

    except SQLAlchemyError as error:
        raise RuntimeError(
            "Unable to retrieve the alert."
        ) from error


def update_alert_status(
    db: Session,
    alert_id: int,
    status: str,
    suppression_reason: str | None = None,
):
    status = status.upper()

    if status not in VALID_ALERT_STATUSES:
        raise ValueError(
            "Invalid alert status. Use PENDING, APPROVED, SUPPRESSED, or RESOLVED."
        )

    if status == "SUPPRESSED" and not suppression_reason:
        raise ValueError(
            "A suppression reason is required when suppressing an alert."
        )

    try:
        if status == "APPROVED":
            query = text("""
                UPDATE alerts
                SET
                    status = 'APPROVED',
                    suppression_reason = NULL,
                    approved_at = CURRENT_TIMESTAMP
                WHERE id = :alert_id
                RETURNING
                    id,
                    location_id,
                    prediction_id,
                    message,
                    severity,
                    status,
                    suppression_reason,
                    created_at,
                    approved_at;
            """)

            params = {
                "alert_id": alert_id
            }

        elif status == "SUPPRESSED":
            query = text("""
                UPDATE alerts
                SET
                    status = 'SUPPRESSED',
                    suppression_reason = :suppression_reason,
                    approved_at = NULL
                WHERE id = :alert_id
                RETURNING
                    id,
                    location_id,
                    prediction_id,
                    message,
                    severity,
                    status,
                    suppression_reason,
                    created_at,
                    approved_at;
            """)

            params = {
                "alert_id": alert_id,
                "suppression_reason": suppression_reason,
            }

        elif status == "RESOLVED":
            query = text("""
                UPDATE alerts
                SET
                    status = 'RESOLVED',
                    suppression_reason = NULL
                WHERE id = :alert_id
                RETURNING
                    id,
                    location_id,
                    prediction_id,
                    message,
                    severity,
                    status,
                    suppression_reason,
                    created_at,
                    approved_at;
            """)

            params = {
                "alert_id": alert_id
            }

        else:
            query = text("""
                UPDATE alerts
                SET
                    status = 'PENDING',
                    suppression_reason = NULL,
                    approved_at = NULL
                WHERE id = :alert_id
                RETURNING
                    id,
                    location_id,
                    prediction_id,
                    message,
                    severity,
                    status,
                    suppression_reason,
                    created_at,
                    approved_at;
            """)

            params = {
                "alert_id": alert_id
            }

        result = db.execute(query, params)

        row = result.fetchone()

        if row is None:
            db.rollback()
            raise ValueError(
                f"Alert with ID {alert_id} was not found."
            )

        db.commit()

        return dict(row._mapping)

    except ValueError:
        db.rollback()
        raise

    except SQLAlchemyError as error:
        db.rollback()

        raise RuntimeError(
            "Unable to update the alert status."
        ) from error