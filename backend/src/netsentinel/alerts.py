"""Evidence-backed alert deduplication and owner audit timeline."""

from datetime import datetime

from fastapi import APIRouter
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from netsentinel.auth import Csrf, CurrentSession, Db, error
from netsentinel.models import Alert, Device, Event, utcnow
from netsentinel.timeutil import iso_utc

alerts_router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])
events_router = APIRouter(prefix="/api/v1/events", tags=["events"])


def add_event(
    db: DBSession,
    event_type: str,
    summary: str,
    *,
    device_id: int | None = None,
    actor: str = "system",
    evidence_ref: str | None = None,
    occurred_at: datetime | None = None,
) -> Event:
    event = Event(
        device_id=device_id,
        event_type=event_type,
        occurred_at=occurred_at or utcnow(),
        actor=actor[:80],
        summary=summary[:255],
        evidence_ref=evidence_ref,
    )
    db.add(event)
    return event


def upsert_alert(
    db: DBSession,
    *,
    device_id: int,
    rule_key: str,
    summary: str,
    details: str,
    evidence_ref: str,
    severity: str = "attention",
) -> tuple[Alert, bool]:
    active = db.scalar(
        select(Alert).where(
            Alert.device_id == device_id,
            Alert.rule_key == rule_key,
            Alert.status.in_(["active", "acknowledged"]),
        )
    )
    now = utcnow()
    if active:
        active.last_seen_at = now
        active.evidence_ref = evidence_ref
        active.details = details
        return active, False
    alert = Alert(
        device_id=device_id,
        rule_key=rule_key,
        severity=severity,
        status="active",
        summary=summary[:255],
        details=details,
        evidence_ref=evidence_ref,
        created_at=now,
        last_seen_at=now,
    )
    db.add(alert)
    db.flush()
    add_event(db, "alert_triggered", summary, device_id=device_id, evidence_ref=f"alert:{alert.id}")
    return alert, True


def resolve_rule(db: DBSession, device_id: int, rule_key: str, *, actor: str = "system") -> bool:
    alert = db.scalar(
        select(Alert).where(
            Alert.device_id == device_id,
            Alert.rule_key == rule_key,
            Alert.status.in_(["active", "acknowledged"]),
        )
    )
    if alert is None:
        return False
    resolve_alert(db, alert, actor=actor)
    return True


def resolve_alert(db: DBSession, alert: Alert, *, actor: str = "system") -> None:
    alert.status = "resolved"
    alert.resolved_at = utcnow()
    add_event(
        db,
        "alert_resolved",
        f"Resolved: {alert.summary}",
        device_id=alert.device_id,
        actor=actor,
        evidence_ref=f"alert:{alert.id}",
    )


def alert_out(db: DBSession, alert: Alert) -> dict:
    device = db.get(Device, alert.device_id) if alert.device_id is not None else None
    return {
        "id": alert.id,
        "device_id": alert.device_id,
        "device_name": device.display_name if device else None,
        "rule_key": alert.rule_key,
        "severity": alert.severity,
        "status": alert.status,
        "summary": alert.summary,
        "details": alert.details,
        "evidence_ref": alert.evidence_ref,
        "created_at": iso_utc(alert.created_at),
        "last_seen_at": iso_utc(alert.last_seen_at),
        "acknowledged_at": iso_utc(alert.acknowledged_at),
        "resolved_at": iso_utc(alert.resolved_at),
    }


def get_alert(db: DBSession, alert_id: int) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        error("not_found", "Alert not found", 404)
    return alert


@alerts_router.get("")
def list_alerts(
    db: Db, _user: CurrentSession, status: str = "open", limit: int = 50, offset: int = 0
) -> dict:
    if status not in ("open", "active", "acknowledged", "resolved", "all"):
        error("invalid_filter", "Unknown alert status filter")
    if limit < 1 or limit > 100 or offset < 0:
        error("invalid_pagination", "Use limit 1–100 and nonnegative offset")
    condition = (
        Alert.status.in_(["active", "acknowledged"])
        if status == "open"
        else Alert.status == status
        if status != "all"
        else None
    )
    query = select(Alert).order_by(Alert.last_seen_at.desc(), Alert.id.desc())
    count = select(func.count(Alert.id))
    if condition is not None:
        query = query.where(condition)
        count = count.where(condition)
    total = db.scalar(count) or 0
    rows = db.scalars(query.limit(limit).offset(offset))
    return {
        "items": [alert_out(db, row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@alerts_router.get("/{alert_id}")
def detail(alert_id: int, db: Db, _user: CurrentSession) -> dict:
    return alert_out(db, get_alert(db, alert_id))


@alerts_router.post("/{alert_id}/acknowledge")
def acknowledge(alert_id: int, db: Db, user: CurrentSession, _csrf: Csrf) -> dict:
    alert = get_alert(db, alert_id)
    if alert.status == "resolved":
        error("invalid_state", "Resolved alerts cannot be acknowledged", 409)
    if alert.status == "active":
        alert.status = "acknowledged"
        alert.acknowledged_at = utcnow()
        add_event(
            db,
            "alert_acknowledged",
            f"Acknowledged: {alert.summary}",
            device_id=alert.device_id,
            actor=user.user.username,
            evidence_ref=f"alert:{alert.id}",
        )
        db.commit()
    return alert_out(db, alert)


@alerts_router.post("/{alert_id}/resolve")
def resolve(alert_id: int, db: Db, user: CurrentSession, _csrf: Csrf) -> dict:
    alert = get_alert(db, alert_id)
    if alert.status != "resolved":
        resolve_alert(db, alert, actor=user.user.username)
        db.commit()
    return alert_out(db, alert)


@events_router.get("")
def list_events(
    db: Db,
    _user: CurrentSession,
    limit: int = 50,
    offset: int = 0,
    device_id: int | None = None,
    event_type: str | None = None,
) -> dict:
    if limit < 1 or limit > 100 or offset < 0 or (device_id is not None and device_id < 1):
        error("invalid_pagination", "Use limit 1–100 and nonnegative offset")
    count = select(func.count(Event.id))
    query = select(Event).order_by(Event.occurred_at.desc(), Event.id.desc())
    if device_id is not None:
        count = count.where(Event.device_id == device_id)
        query = query.where(Event.device_id == device_id)
    if event_type is not None:
        if len(event_type) > 60 or not event_type.replace("_", "").isalnum():
            error("invalid_filter", "Invalid event type")
        count = count.where(Event.event_type == event_type)
        query = query.where(Event.event_type == event_type)
    total = db.scalar(count) or 0
    rows = db.scalars(query.limit(limit).offset(offset))
    return {
        "items": [
            {
                "id": row.id,
                "device_id": row.device_id,
                "event_type": row.event_type,
                "occurred_at": iso_utc(row.occurred_at),
                "actor": row.actor,
                "summary": row.summary,
                "evidence_ref": row.evidence_ref,
            }
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
