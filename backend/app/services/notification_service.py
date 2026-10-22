"""Post-commit logging hook. Durable queueing lives in notification_outbox (enqueued inside the
approval transaction); this hook sends nothing and there is no Web Push or service worker."""

import logging

from app.models.alert import Alert, AlertStatus

logger = logging.getLogger(__name__)


def notify_users_for_approved_alert(alert: Alert) -> None:
    if alert.status != AlertStatus.APPROVED:
        raise ValueError("Notification hooks may only receive approved alerts")
    logger.info(
        "Notification hook invoked for approved alert #%s; "
        "delivery is open-browser polling of the notification outbox only.",
        alert.id,
    )
