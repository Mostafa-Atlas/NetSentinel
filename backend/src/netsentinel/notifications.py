"""Opt-in HTTPS webhook outbox for newly opened alerts."""

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from netsentinel.auth import CurrentSession, Db
from netsentinel.models import Alert, NotificationDelivery, utcnow
from netsentinel.timeutil import iso_utc

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


def webhook_url() -> str | None:
    raw = os.getenv("NETSENTINEL_WEBHOOK_URL", "")
    parsed = urlsplit(raw)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.fragment
        or any(char.isspace() for char in raw)
    ):
        return None
    return raw


def queue_alert(db: DBSession, alert: Alert) -> None:
    from netsentinel.monitoring import read_settings

    if read_settings(db).notification_enabled and webhook_url():
        db.add(
            NotificationDelivery(
                alert_id=alert.id,
                status="queued",
                attempts=0,
                next_attempt_at=utcnow(),
            )
        )


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def send_webhook(url: str, payload: bytes) -> None:
    token = os.getenv("NETSENTINEL_WEBHOOK_TOKEN", "")
    headers = {"Content-Type": "application/json", "User-Agent": "NetSentinel/0.1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=5) as response:
        if response.status < 200 or response.status >= 300:
            raise ValueError("Webhook returned a non-success status")


def deliver_pending(app, now: datetime | None = None, sender=send_webhook) -> int:
    from netsentinel.monitoring import read_settings

    now = now or utcnow()
    url = webhook_url()
    with app.state.session_factory() as db:
        if not read_settings(db).notification_enabled or not url:
            return 0
        due = db.scalars(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.status == "queued",
                NotificationDelivery.next_attempt_at <= now,
            )
            .order_by(NotificationDelivery.id)
            .limit(10)
        ).all()
        for row in due:
            alert = db.get(Alert, row.alert_id)
            if alert is None:
                row.status = "failed"
                row.error_summary = "Alert no longer exists"
                continue
            payload = json.dumps(
                {
                    "event": "alert.opened",
                    "delivery_id": row.id,
                    "alert_id": alert.id,
                    "device_id": alert.device_id,
                    "rule_key": alert.rule_key,
                    "severity": alert.severity,
                    "summary": alert.summary,
                    "created_at": iso_utc(alert.created_at),
                }
            ).encode("utf-8")
            row.attempts += 1
            row.last_attempt_at = now
            try:
                sender(url, payload)
                row.status = "delivered"
                row.delivered_at = now
                row.error_summary = None
            except (OSError, ValueError, urllib.error.URLError):
                row.error_summary = "Webhook request failed"
                if row.attempts >= 3:
                    row.status = "failed"
                else:
                    row.next_attempt_at = now + timedelta(minutes=5 * row.attempts)
        db.commit()
        return len(due)


@router.get("")
def notification_status(db: Db, _user: CurrentSession) -> dict:
    from netsentinel.monitoring import read_settings

    rows = db.scalars(
        select(NotificationDelivery).order_by(NotificationDelivery.id.desc()).limit(20)
    )
    return {
        "enabled": read_settings(db).notification_enabled,
        "configured": webhook_url() is not None,
        "deliveries": [
            {
                "id": row.id,
                "alert_id": row.alert_id,
                "status": row.status,
                "attempts": row.attempts,
                "last_attempt_at": iso_utc(row.last_attempt_at),
                "delivered_at": iso_utc(row.delivered_at),
                "error_summary": row.error_summary,
            }
            for row in rows
        ],
    }
