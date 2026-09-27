"""Conservative device identity and authenticated inventory API."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from netsentinel.alerts import add_event
from netsentinel.auth import Csrf, CurrentSession, Db, error
from netsentinel.discovery import ProbeResult
from netsentinel.models import (
    Alert,
    Device,
    DeviceAddress,
    DeviceHint,
    Observation,
    ServiceObservation,
    utcnow,
)
from netsentinel.monitoring import read_settings
from netsentinel.timeutil import iso_utc

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


def reconcile_device(
    db: DBSession, result: ProbeResult, now: datetime | None = None, profile_id: int | None = None
) -> Device:
    """Prefer an observed MAC; retain a separate provisional identity without one.

    An IP change alone never merges a MAC-bearing device with another identity.
    MACs can be spoofed or randomized, so this is still observed confidence.
    """
    now = now or utcnow()
    profile_filter = (
        Device.profile_id.is_(None) if profile_id is None else Device.profile_id == profile_id
    )
    if result.mac:
        address = db.scalar(
            select(DeviceAddress)
            .join(Device, Device.id == DeviceAddress.device_id)
            .where(profile_filter)
            .where(DeviceAddress.mac == result.mac, DeviceAddress.ip == result.ip)
            .order_by(DeviceAddress.last_seen_at.desc(), DeviceAddress.id.desc())
        )
        if address is None:
            address = db.scalar(
                select(DeviceAddress)
                .join(Device, Device.id == DeviceAddress.device_id)
                .where(profile_filter)
                .where(DeviceAddress.mac == result.mac)
                .order_by(DeviceAddress.last_seen_at.desc(), DeviceAddress.id.desc())
            )
    else:
        address = db.scalar(
            select(DeviceAddress)
            .join(Device, Device.id == DeviceAddress.device_id)
            .where(profile_filter)
            .where(DeviceAddress.ip == result.ip, DeviceAddress.mac.is_(None))
            .order_by(DeviceAddress.last_seen_at.desc(), DeviceAddress.id.desc())
        )
    if address is None:
        device = Device(
            profile_id=profile_id,
            display_name=result.ip,
            identity_confidence="observed_mac" if result.mac else "provisional",
            known_state="unknown",
            notes="",
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(device)
        db.flush()
        db.add(
            DeviceAddress(
                device_id=device.id,
                ip=result.ip,
                mac=result.mac,
                first_seen_at=now,
                last_seen_at=now,
            )
        )
    else:
        existing = db.get(Device, address.device_id)
        if existing is None:
            raise RuntimeError("Device address has no owner")
        device = existing
        if address.ip == result.ip:
            address.last_seen_at = now
        else:
            db.add(
                DeviceAddress(
                    device_id=device.id,
                    ip=result.ip,
                    mac=result.mac,
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
        if result.mac:
            device.identity_confidence = "observed_mac"
        device.last_seen_at = now
    return device


class DeviceUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)
    known_state: Literal["known", "unknown"] | None = None


def device_out(db: DBSession, device: Device) -> dict:
    addresses = db.scalars(
        select(DeviceAddress)
        .where(DeviceAddress.device_id == device.id)
        .order_by(DeviceAddress.last_seen_at.desc(), DeviceAddress.id.desc())
    ).all()
    latest = db.scalar(
        select(Observation)
        .where(Observation.device_id == device.id)
        .order_by(Observation.observed_at.desc(), Observation.id.desc())
    )
    threshold = read_settings(db).offline_threshold
    recent = db.scalars(
        select(Observation.reachable)
        .where(Observation.device_id == device.id)
        .order_by(Observation.observed_at.desc(), Observation.id.desc())
        .limit(threshold)
    ).all()
    status = (
        "online"
        if latest and latest.reachable is True
        else "offline"
        if len(recent) >= threshold and all(value is False for value in recent)
        else "unconfirmed"
    )
    return {
        "id": device.id,
        "profile_id": device.profile_id,
        "display_name": device.display_name,
        "identity_confidence": device.identity_confidence,
        "known_state": device.known_state,
        "notes": device.notes,
        "first_seen_at": iso_utc(device.first_seen_at),
        "last_seen_at": iso_utc(device.last_seen_at),
        "status": status,
        "last_observed_at": iso_utc(latest.observed_at) if latest else None,
        "addresses": [
            {
                "ip": address.ip,
                "mac": address.mac,
                "hostname": address.hostname,
                "first_seen_at": iso_utc(address.first_seen_at),
                "last_seen_at": iso_utc(address.last_seen_at),
            }
            for address in addresses
        ],
    }


def get_device(db: DBSession, device_id: int) -> Device:
    device = db.get(Device, device_id)
    if device is None:
        error("not_found", "Device not found", 404)
    return device


@router.get("")
def list_devices(
    db: Db,
    _user: CurrentSession,
    search: str = "",
    known_state: str | None = None,
    status: str | None = None,
    alert_filter: str = "all",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    if limit < 1 or limit > 100 or offset < 0 or len(search) > 100:
        error("invalid_pagination", "Use limit 1–100, nonnegative offset, and a short search")
    if (
        known_state not in (None, "known", "unknown")
        or alert_filter not in ("all", "open", "clear")
        or status
        not in (
            None,
            "online",
            "offline",
            "unconfirmed",
        )
    ):
        error("invalid_filter", "Invalid device filter")
    devices = db.scalars(
        select(Device).order_by(Device.last_seen_at.desc(), Device.id.desc())
    ).all()
    items = [device_out(db, device) for device in devices]
    if search:
        term = search.casefold()
        items = [
            item
            for item in items
            if term in item["display_name"].casefold()
            or any(term in address["ip"] for address in item["addresses"])
        ]
    if known_state:
        items = [item for item in items if item["known_state"] == known_state]
    if status:
        items = [item for item in items if item["status"] == status]
    if alert_filter != "all":
        open_ids = set(
            db.scalars(select(Alert.device_id).where(Alert.status.in_(["active", "acknowledged"])))
        )
        items = [item for item in items if (item["id"] in open_ids) == (alert_filter == "open")]
    return {
        "items": items[offset : offset + limit],
        "total": len(items),
        "limit": limit,
        "offset": offset,
    }


@router.get("/{device_id}")
def device_detail(device_id: int, db: Db, _user: CurrentSession) -> dict:
    return device_out(db, get_device(db, device_id))


@router.patch("/{device_id}")
def update_device(
    device_id: int, payload: DeviceUpdate, db: Db, _user: CurrentSession, _csrf: Csrf
) -> dict:
    device = get_device(db, device_id)
    if payload.display_name is not None:
        device.display_name = payload.display_name.strip() or error(
            "invalid_name", "Name cannot be blank"
        )
    if payload.notes is not None:
        device.notes = payload.notes
    if payload.known_state is not None:
        device.known_state = payload.known_state
    add_event(
        db,
        "device_updated",
        f"Updated device #{device.id} owner details",
        device_id=device.id,
        actor=_user.user.username,
    )
    db.commit()
    return device_out(db, device)


@router.get("/{device_id}/observations")
def observations(
    device_id: int, db: Db, _user: CurrentSession, limit: int = 50, offset: int = 0
) -> dict:
    get_device(db, device_id)
    if limit < 1 or limit > 100 or offset < 0:
        error("invalid_pagination", "Use limit 1–100 and nonnegative offset")
    total = (
        db.scalar(select(func.count(Observation.id)).where(Observation.device_id == device_id)) or 0
    )
    rows = db.scalars(
        select(Observation)
        .where(Observation.device_id == device_id)
        .order_by(Observation.observed_at.desc(), Observation.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return {
        "items": [
            {
                "id": row.id,
                "scan_run_id": row.scan_run_id,
                "observed_at": iso_utc(row.observed_at),
                "source": row.source,
                "reachable": row.reachable,
                "latency_ms": row.latency_ms,
                "raw_summary": row.raw_summary,
            }
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{device_id}/services")
def services(
    device_id: int, db: Db, _user: CurrentSession, limit: int = 50, offset: int = 0
) -> dict:
    get_device(db, device_id)
    if limit < 1 or limit > 100 or offset < 0:
        error("invalid_pagination", "Use limit 1–100 and nonnegative offset")
    total = (
        db.scalar(
            select(func.count(ServiceObservation.id)).where(
                ServiceObservation.device_id == device_id
            )
        )
        or 0
    )
    rows = db.scalars(
        select(ServiceObservation)
        .where(ServiceObservation.device_id == device_id)
        .order_by(ServiceObservation.observed_at.desc(), ServiceObservation.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return {
        "items": [
            {
                "id": row.id,
                "scan_run_id": row.scan_run_id,
                "ip": row.ip,
                "port": row.port,
                "protocol": row.protocol,
                "state": row.state,
                "observed_at": iso_utc(row.observed_at),
            }
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{device_id}/hints")
def hints(device_id: int, db: Db, _user: CurrentSession, limit: int = 50, offset: int = 0) -> dict:
    get_device(db, device_id)
    if limit < 1 or limit > 100 or offset < 0:
        error("invalid_pagination", "Use limit 1–100 and nonnegative offset")
    total = (
        db.scalar(select(func.count(DeviceHint.id)).where(DeviceHint.device_id == device_id)) or 0
    )
    rows = db.scalars(
        select(DeviceHint)
        .where(DeviceHint.device_id == device_id)
        .order_by(DeviceHint.observed_at.desc(), DeviceHint.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return {
        "items": [
            {
                "id": row.id,
                "scan_run_id": row.scan_run_id,
                "ip": row.ip,
                "source": row.source,
                "kind": row.kind,
                "value": row.value,
                "confidence": "unverified_advertisement",
                "observed_at": iso_utc(row.observed_at),
            }
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
