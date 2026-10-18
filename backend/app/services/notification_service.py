"""Development hook only: no subscription lookup, queue, or notification delivery."""

import logging

from app.models.alert import Alert, AlertStatus

logger = logging.getLogger(__name__)


def notify_users_for_approved_alert(alert: Alert) -> None:
    if alert.status != AlertStatus.APPROVED:
        raise ValueError("Notification hooks may only receive approved alerts")
    logger.info(
        "Notification hook invoked for approved alert #%s; "
        "no delivery provider or subscription service is configured.",
        alert.id,
    )
