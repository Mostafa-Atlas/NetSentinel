"""Optional outbound host reports with scoped, revocable credentials."""

import hashlib
import hmac
import json
import re
import secrets
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from netsentinel.alerts import add_event
from netsentinel.auth import Csrf, CurrentSession, Db, error
from netsentinel.models import AgentEnrollment, AgentNonce, AgentReport, Device, utcnow
from netsentinel.timeutil import iso_utc

devices_router = APIRouter(prefix="/api/v1/devices", tags=["agents"])
enrollments_router = APIRouter(prefix="/api/v1/agent-enrollments", tags=["agents"])
reports_router = APIRouter(prefix="/api/v1/agent", tags=["agents"])
TOKEN_PATTERN = re.compile(r"nsagent_(\d+)_([A-Za-z0-9_-]{32,80})\Z")
NONCE_PATTERN = re.compile(r"[0-9a-fA-F]{32,64}\Z")


class EnrollmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    expires_days: int = Field(default=90, ge=1, le=365)


class ContainerStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    state: Literal["running", "stopped", "unknown"]


class HostReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hostname: str = Field(min_length=1, max_length=255)
    os_name: str = Field(min_length=1, max_length=100)
    load_1m: float | None = Field(default=None, ge=0, le=1000, allow_inf_nan=False)
    containers: list[ContainerStatus] = Field(default_factory=list, max_length=32)


def enrollment_out(row: AgentEnrollment) -> dict:
    return {
        "id": row.id,
        "device_id": row.device_id,
        "name": row.name,
        "created_at": iso_utc(row.created_at),
        "expires_at": iso_utc(row.expires_at),
        "revoked_at": iso_utc(row.revoked_at),
    }


@devices_router.get("/{device_id}/agent-enrollments")
def list_enrollments(device_id: int, db: Db, _user: CurrentSession) -> list[dict]:
    if db.get(Device, device_id) is None:
        error("not_found", "Device not found", 404)
    return [
        enrollment_out(row)
        for row in db.scalars(
            select(AgentEnrollment)
            .where(AgentEnrollment.device_id == device_id)
            .order_by(AgentEnrollment.id.desc())
        )
    ]


@devices_router.post("/{device_id}/agent-enrollments", status_code=201)
def create_enrollment(
    device_id: int, payload: EnrollmentCreate, db: Db, user: CurrentSession, _csrf: Csrf
) -> dict:
    if db.get(Device, device_id) is None:
        error("not_found", "Device not found", 404)
    name = payload.name.strip()
    if not name:
        error("invalid_name", "Agent name cannot be blank")
    row = AgentEnrollment(
        device_id=device_id,
        name=name,
        token_hash=secrets.token_hex(32),
        created_at=utcnow(),
        expires_at=utcnow() + timedelta(days=payload.expires_days),
    )
    db.add(row)
    db.flush()
    token = f"nsagent_{row.id}_{secrets.token_urlsafe(32)}"
    row.token_hash = hashlib.sha256(token.encode()).hexdigest()
    add_event(
        db,
        "agent_enrolled",
        f"Enrolled host agent {name}",
        device_id=device_id,
        actor=user.user.username,
    )
    db.commit()
    return {**enrollment_out(row), "token": token}


@enrollments_router.post("/{enrollment_id}/revoke")
def revoke_enrollment(enrollment_id: int, db: Db, user: CurrentSession, _csrf: Csrf) -> dict:
    row = db.get(AgentEnrollment, enrollment_id)
    if row is None:
        error("not_found", "Agent enrollment not found", 404)
    if row.revoked_at is None:
        row.revoked_at = utcnow()
        add_event(
            db,
            "agent_revoked",
            f"Revoked host agent {row.name}",
            device_id=row.device_id,
            actor=user.user.username,
        )
        db.commit()
    return enrollment_out(row)


def _secure_transport(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    try:
        return bool(request.client and ip_address(request.client.host).is_loopback)
    except ValueError:
        return False


def _agent_enrollment(request: Request, db: Db) -> AgentEnrollment:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    match = TOKEN_PATTERN.fullmatch(token) if scheme.lower() == "bearer" else None
    if match is None:
        error("agent_unauthorized", "Valid agent credential required", 401)
    row = db.get(AgentEnrollment, int(match.group(1)))
    hashed = hashlib.sha256(token.encode()).hexdigest()
    if row is None or not hmac.compare_digest(row.token_hash, hashed):
        error("agent_unauthorized", "Valid agent credential required", 401)
    if row.revoked_at is not None or row.expires_at.replace(tzinfo=UTC) <= utcnow():
        error("agent_unauthorized", "Agent credential expired or revoked", 401)
    return row


@reports_router.post("/reports", status_code=201)
def submit_report(payload: HostReport, request: Request, db: Db) -> dict:
    if not _secure_transport(request):
        error("tls_required", "Agent reports require HTTPS except on loopback", 403)
    enrollment = _agent_enrollment(request, db)
    nonce = request.headers.get("x-agent-nonce", "")
    timestamp = request.headers.get("x-agent-timestamp", "")
    if not NONCE_PATTERN.fullmatch(nonce):
        error("invalid_nonce", "A fresh 16-byte or longer hex nonce is required")
    try:
        sent_at = datetime.fromtimestamp(int(timestamp), UTC)
    except (ValueError, OverflowError):
        error("invalid_timestamp", "Valid Unix timestamp required")
    if abs((utcnow() - sent_at).total_seconds()) > 300:
        error("stale_report", "Agent timestamp is outside the five-minute window", 409)
    row = AgentReport(
        enrollment_id=enrollment.id,
        device_id=enrollment.device_id,
        received_at=utcnow(),
        hostname=payload.hostname,
        os_name=payload.os_name,
        load_1m=payload.load_1m,
        containers_json=json.dumps([item.model_dump() for item in payload.containers]),
    )
    db.add(AgentNonce(enrollment_id=enrollment.id, nonce=nonce, used_at=utcnow()))
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        error("replayed_report", "This agent nonce was already used", 409)
    return {
        "id": row.id,
        "device_id": enrollment.device_id,
        "received_at": iso_utc(row.received_at),
    }


@devices_router.get("/{device_id}/agent-reports")
def list_reports(
    device_id: int, db: Db, _user: CurrentSession, limit: int = 20, offset: int = 0
) -> dict:
    if db.get(Device, device_id) is None:
        error("not_found", "Device not found", 404)
    if limit < 1 or limit > 100 or offset < 0:
        error("invalid_pagination", "Use limit 1–100 and nonnegative offset")
    total = (
        db.scalar(select(func.count(AgentReport.id)).where(AgentReport.device_id == device_id)) or 0
    )
    rows = db.scalars(
        select(AgentReport)
        .where(AgentReport.device_id == device_id)
        .order_by(AgentReport.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return {
        "items": [
            {
                "id": row.id,
                "device_id": row.device_id,
                "received_at": iso_utc(row.received_at),
                "hostname": row.hostname,
                "os_name": row.os_name,
                "load_1m": row.load_1m,
                "containers": json.loads(row.containers_json),
            }
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
