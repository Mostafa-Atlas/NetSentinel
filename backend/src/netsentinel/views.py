"""Evidence-backed overview and inferred topology read models."""

from ipaddress import IPv4Address, IPv4Network

from fastapi import APIRouter
from sqlalchemy import func, select

from netsentinel.auth import CurrentSession, Db
from netsentinel.inventory import device_out
from netsentinel.models import Alert, Device, Event, NetworkScope, Observation, ScanRun
from netsentinel.scans import scan_out
from netsentinel.timeutil import iso_utc

router = APIRouter(prefix="/api/v1", tags=["views"])


@router.get("/overview")
def overview(db: Db, _user: CurrentSession) -> dict:
    devices = db.scalars(select(Device).order_by(Device.id)).all()
    summaries = [device_out(db, device) for device in devices]
    latest_scan = db.scalar(select(ScanRun).order_by(ScanRun.id.desc()))
    latest_observation = db.scalar(
        select(Observation).order_by(Observation.observed_at.desc(), Observation.id.desc())
    )
    recent_scans = db.scalars(select(ScanRun).order_by(ScanRun.id.desc()).limit(5)).all()
    recent_events = db.scalars(
        select(Event).order_by(Event.occurred_at.desc(), Event.id.desc()).limit(5)
    ).all()
    times = [
        value
        for value in (
            (latest_scan.finished_at or latest_scan.started_at) if latest_scan else None,
            latest_observation.observed_at if latest_observation else None,
            recent_events[0].occurred_at if recent_events else None,
        )
        if value
    ]
    updated_at = iso_utc(max(times)) if times else None
    return {
        "device_count": len(summaries),
        "online_count": sum(item["status"] == "online" for item in summaries),
        "review_count": sum(item["known_state"] == "unknown" for item in summaries),
        "offline_count": sum(item["status"] == "offline" for item in summaries),
        "active_alert_count": db.scalar(
            select(func.count(Alert.id)).where(Alert.status.in_(["active", "acknowledged"]))
        )
        or 0,
        "updated_at": updated_at,
        "latest_scan": scan_out(latest_scan) if latest_scan else None,
        "recent_scans": [scan_out(scan) for scan in recent_scans],
        "recent_events": [
            {
                "id": event.id,
                "summary": event.summary,
                "event_type": event.event_type,
                "occurred_at": iso_utc(event.occurred_at),
                "actor": event.actor,
            }
            for event in recent_events
        ],
    }


@router.get("/topology")
def topology(db: Db, _user: CurrentSession) -> dict:
    scopes = db.scalars(select(NetworkScope).order_by(NetworkScope.id)).all()
    devices = db.scalars(select(Device).order_by(Device.id)).all()
    nodes: list[dict[str, object]] = [
        {
            "id": f"scope:{scope.id}",
            "kind": "subnet",
            "label": f"{scope.name} · {scope.cidr}",
            "cidr": scope.cidr,
            "status": "group",
            "last_observed_at": None,
        }
        for scope in scopes
    ]
    links: list[dict[str, str]] = []
    for device in devices:
        summary = device_out(db, device)
        nodes.append(
            {
                "id": f"device:{device.id}",
                "kind": "device",
                "device_id": device.id,
                "label": device.display_name,
                "status": summary["status"],
                "identity_confidence": device.identity_confidence,
                "last_observed_at": summary["last_observed_at"],
                "addresses": [address["ip"] for address in summary["addresses"]],
            }
        )
        matches = []
        for address in summary["addresses"]:
            for scope in scopes:
                if IPv4Address(address["ip"]) in IPv4Network(scope.cidr):
                    matches.append(scope)
        if matches:
            scope = max(matches, key=lambda item: IPv4Network(item.cidr).prefixlen)
            links.append(
                {
                    "source": f"scope:{scope.id}",
                    "target": f"device:{device.id}",
                    "kind": "inferred",
                    "provenance": "IP observed in approved subnet; physical link unknown",
                }
            )
    return {
        "nodes": nodes,
        "links": links,
        "legend": {"inferred": "Subnet link inferred from IP; no physical connection verified"},
    }
