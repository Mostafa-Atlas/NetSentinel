"""Per-device service rules evaluated from approved scan evidence."""

from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address, IPv4Network

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from netsentinel.alerts import add_event, resolve_rule, upsert_alert
from netsentinel.auth import Csrf, CurrentSession, Db, error
from netsentinel.models import (
    Device,
    DeviceAddress,
    MonitorCheck,
    MonitorRule,
    NetworkScope,
    ScanRun,
    ServiceObservation,
    utcnow,
)
from netsentinel.timeutil import iso_utc

devices_router = APIRouter(prefix="/api/v1/devices", tags=["check-rules"])
rules_router = APIRouter(prefix="/api/v1/check-rules", tags=["check-rules"])


class RuleCreate(BaseModel):
    port: int = Field(ge=1, le=65535)
    failure_threshold: int = Field(default=2, ge=2, le=10)
    quiet_start_hour: int | None = Field(default=None, ge=0, le=23)
    quiet_end_hour: int | None = Field(default=None, ge=0, le=23)
    maintenance_until: datetime | None = None


class RulePatch(BaseModel):
    enabled: bool | None = None
    failure_threshold: int | None = Field(default=None, ge=2, le=10)
    quiet_start_hour: int | None = Field(default=None, ge=0, le=23)
    quiet_end_hour: int | None = Field(default=None, ge=0, le=23)
    maintenance_until: datetime | None = None


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def validate_windows(start: int | None, end: int | None, maintenance: datetime | None) -> None:
    if (start is None) != (end is None) or (start is not None and start == end):
        error("invalid_quiet_hours", "Set two different UTC hours, or clear both")
    if maintenance is not None:
        if maintenance.tzinfo is None:
            error("invalid_maintenance", "Maintenance time must include a timezone")
        if maintenance > utcnow() + timedelta(days=30):
            error("invalid_maintenance", "Maintenance may be set at most 30 days ahead")


def rule_out(rule: MonitorRule) -> dict:
    return {
        "id": rule.id,
        "device_id": rule.device_id,
        "port": rule.port,
        "enabled": rule.enabled,
        "failure_threshold": rule.failure_threshold,
        "quiet_start_hour": rule.quiet_start_hour,
        "quiet_end_hour": rule.quiet_end_hour,
        "maintenance_until": iso_utc(rule.maintenance_until),
        "created_at": iso_utc(rule.created_at),
        "updated_at": iso_utc(rule.updated_at),
    }


def _rule(db: DBSession, rule_id: int) -> MonitorRule:
    rule = db.get(MonitorRule, rule_id)
    if rule is None:
        error("not_found", "Check rule not found", 404)
    return rule


def _approved_port_for_device(db: DBSession, device: Device, port: int) -> bool:
    addresses = db.scalars(
        select(DeviceAddress.ip).where(DeviceAddress.device_id == device.id)
    ).all()
    scopes = db.scalars(
        select(NetworkScope).where(
            NetworkScope.profile_id == device.profile_id, NetworkScope.enabled.is_(True)
        )
    ).all()
    return any(
        port in {int(value) for value in scope.ports.split(",")}
        and any(IPv4Address(ip) in IPv4Network(scope.cidr) for ip in addresses)
        for scope in scopes
    )


def _suppressed(rule: MonitorRule, now: datetime) -> bool:
    if rule.maintenance_until is not None and _aware(rule.maintenance_until) > now:
        return True
    start, end = rule.quiet_start_hour, rule.quiet_end_hour
    if start is None or end is None:
        return False
    return start <= now.hour < end if start < end else now.hour >= start or now.hour < end


def evaluate_scan_rules(db: DBSession, run: ScanRun, scope: NetworkScope) -> None:
    """Create one check per rule/run after all probe results have been stored."""
    now = utcnow()
    ports = {int(value) for value in scope.ports.split(",")}
    rules = db.scalars(
        select(MonitorRule)
        .join(Device, Device.id == MonitorRule.device_id)
        .where(MonitorRule.enabled.is_(True), Device.profile_id == scope.profile_id)
    ).all()
    for rule in rules:
        if rule.port not in ports:
            continue
        states = db.scalars(
            select(ServiceObservation.state).where(
                ServiceObservation.scan_run_id == run.id,
                ServiceObservation.device_id == rule.device_id,
                ServiceObservation.port == rule.port,
            )
        ).all()
        if not states:
            continue
        state = (
            "reachable"
            if "reachable" in states
            else "unreachable"
            if "unreachable" in states
            else "unknown"
        )
        check = MonitorCheck(
            rule_id=rule.id,
            scan_run_id=run.id,
            observed_at=now,
            state=state,
            suppressed=_suppressed(rule, now),
        )
        db.add(check)
        db.flush()
        key = f"check_rule:{rule.id}"
        if state == "reachable":
            resolve_rule(db, rule.device_id, key)
            continue
        recent = db.scalars(
            select(MonitorCheck.state)
            .where(MonitorCheck.rule_id == rule.id)
            .order_by(MonitorCheck.id.desc())
            .limit(rule.failure_threshold)
        ).all()
        if check.suppressed or len(recent) < rule.failure_threshold or "reachable" in recent:
            continue
        device = db.get(Device, rule.device_id)
        name = device.display_name if device else f"Device #{rule.device_id}"
        upsert_alert(
            db,
            device_id=rule.device_id,
            rule_key=key,
            summary=f"TCP {rule.port} check missed on {name}",
            details=(
                f"TCP {rule.port} was not reachable in {rule.failure_threshold} consecutive "
                "approved scans. Firewalls, sleep, or isolation can cause this."
            ),
            evidence_ref=f"check:{check.id}",
        )


@devices_router.get("/{device_id}/check-rules")
def list_device_rules(device_id: int, db: Db, _user: CurrentSession) -> list[dict]:
    if db.get(Device, device_id) is None:
        error("not_found", "Device not found", 404)
    return [
        rule_out(rule)
        for rule in db.scalars(
            select(MonitorRule).where(MonitorRule.device_id == device_id).order_by(MonitorRule.port)
        )
    ]


@devices_router.post("/{device_id}/check-rules", status_code=201)
def create_rule(
    device_id: int, payload: RuleCreate, db: Db, user: CurrentSession, _csrf: Csrf
) -> dict:
    device = db.get(Device, device_id)
    if device is None:
        error("not_found", "Device not found", 404)
    if not _approved_port_for_device(db, device, payload.port):
        error("unapproved_port", "Use a TCP port in an enabled approved scope for this device")
    validate_windows(payload.quiet_start_hour, payload.quiet_end_hour, payload.maintenance_until)
    rule = MonitorRule(
        device_id=device_id,
        port=payload.port,
        enabled=True,
        failure_threshold=payload.failure_threshold,
        quiet_start_hour=payload.quiet_start_hour,
        quiet_end_hour=payload.quiet_end_hour,
        maintenance_until=payload.maintenance_until,
    )
    db.add(rule)
    try:
        db.flush()
        add_event(
            db,
            "check_rule_created",
            f"Added TCP {rule.port} check rule",
            device_id=device_id,
            actor=user.user.username,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        error("duplicate_rule", "This device already has a rule for that port", 409)
    return rule_out(rule)


@rules_router.patch("/{rule_id}")
def update_rule(
    rule_id: int, payload: RulePatch, db: Db, user: CurrentSession, _csrf: Csrf
) -> dict:
    rule = _rule(db, rule_id)
    data = payload.model_dump(exclude_unset=True)
    if any(data.get(key) is None for key in ("enabled", "failure_threshold") if key in data):
        error("invalid_rule", "Enabled and threshold cannot be cleared")
    if not data:
        return rule_out(rule)
    start = data.get("quiet_start_hour", rule.quiet_start_hour)
    end = data.get("quiet_end_hour", rule.quiet_end_hour)
    maintenance = data.get("maintenance_until", rule.maintenance_until)
    validate_windows(start, end, maintenance)
    if data.get("enabled") is True:
        device = db.get(Device, rule.device_id)
        if device is None or not _approved_port_for_device(db, device, rule.port):
            error("unapproved_port", "The device port is no longer in an approved scope")
    for key, value in data.items():
        setattr(rule, key, value)
    rule.updated_at = utcnow()
    if rule.enabled is False:
        resolve_rule(db, rule.device_id, f"check_rule:{rule.id}", actor=user.user.username)
    add_event(
        db,
        "check_rule_updated",
        f"Updated TCP {rule.port} check rule",
        device_id=rule.device_id,
        actor=user.user.username,
    )
    db.commit()
    return rule_out(rule)


@rules_router.get("/{rule_id}/history")
def check_history(
    rule_id: int, db: Db, _user: CurrentSession, limit: int = 50, offset: int = 0
) -> dict:
    _rule(db, rule_id)
    if limit < 1 or limit > 100 or offset < 0:
        error("invalid_pagination", "Use limit 1–100 and nonnegative offset")
    total = (
        db.scalar(select(func.count(MonitorCheck.id)).where(MonitorCheck.rule_id == rule_id)) or 0
    )
    checks = db.scalars(
        select(MonitorCheck)
        .where(MonitorCheck.rule_id == rule_id)
        .order_by(MonitorCheck.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return {
        "items": [
            {
                "id": check.id,
                "scan_run_id": check.scan_run_id,
                "observed_at": iso_utc(check.observed_at),
                "state": check.state,
                "suppressed": check.suppressed,
            }
            for check in checks
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
