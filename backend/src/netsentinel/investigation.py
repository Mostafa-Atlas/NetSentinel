"""Read-only comparisons and explicit owner topology annotations."""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select

from netsentinel.alerts import add_event
from netsentinel.auth import Csrf, CurrentSession, Db, error
from netsentinel.inventory import device_out, get_device
from netsentinel.models import Device, ServiceObservation, TopologyLink, utcnow
from netsentinel.timeutil import iso_utc

router = APIRouter(prefix="/api/v1", tags=["investigation"])


class LinkInput(BaseModel):
    source_id: int = Field(gt=0)
    target_id: int = Field(gt=0)
    label: str = Field(min_length=1, max_length=100)
    note: str = Field(default="", max_length=500)


def link_out(link: TopologyLink) -> dict:
    return {
        "id": link.id,
        "source_id": link.source_id,
        "target_id": link.target_id,
        "label": link.label,
        "note": link.note,
        "provenance": "owner_supplied_unverified",
        "created_at": iso_utc(link.created_at),
        "updated_at": iso_utc(link.updated_at),
    }


def current_services(db: Db, device_id: int) -> list[dict]:
    rows = db.scalars(
        select(ServiceObservation)
        .where(ServiceObservation.device_id == device_id)
        .order_by(ServiceObservation.observed_at.desc(), ServiceObservation.id.desc())
    )
    seen: set[tuple[str, int]] = set()
    result = []
    for row in rows:
        key = (row.protocol, row.port)
        if key not in seen:
            seen.add(key)
            result.append(
                {
                    "protocol": row.protocol,
                    "port": row.port,
                    "state": row.state,
                    "observed_at": iso_utc(row.observed_at),
                    "ip": row.ip,
                }
            )
    return sorted(result, key=lambda item: (item["protocol"], item["port"]))


@router.get("/devices/compare")
def compare_devices(left_id: int, right_id: int, db: Db, _user: CurrentSession) -> dict:
    if left_id == right_id or left_id < 1 or right_id < 1:
        error("invalid_comparison", "Choose two different devices")
    left, right = get_device(db, left_id), get_device(db, right_id)
    if left.profile_id != right.profile_id:
        error("different_profiles", "Compare devices within one network profile", 409)
    return {
        "left": {**device_out(db, left), "services": current_services(db, left.id)},
        "right": {**device_out(db, right), "services": current_services(db, right.id)},
        "provenance": "Latest persisted observations for each device; capture times may differ",
    }


@router.get("/topology/annotations")
def list_links(db: Db, _user: CurrentSession) -> list[dict]:
    return [link_out(row) for row in db.scalars(select(TopologyLink).order_by(TopologyLink.id))]


@router.post("/topology/annotations", status_code=201)
def create_link(payload: LinkInput, db: Db, user: CurrentSession, _csrf: Csrf) -> dict:
    if payload.source_id == payload.target_id:
        error("invalid_link", "Choose two different devices")
    source_id, target_id = sorted((payload.source_id, payload.target_id))
    source, target = db.get(Device, source_id), db.get(Device, target_id)
    if source is None or target is None:
        error("not_found", "Device not found", 404)
    if source.profile_id != target.profile_id:
        error("different_profiles", "Links must stay within one profile", 409)
    if (
        db.scalar(
            select(TopologyLink.id).where(
                TopologyLink.source_id == source_id, TopologyLink.target_id == target_id
            )
        )
        is not None
    ):
        error("duplicate_link", "This device pair already has an annotation", 409)
    label = payload.label.strip()
    if not label:
        error("invalid_label", "Label cannot be blank")
    link = TopologyLink(
        source_id=source_id,
        target_id=target_id,
        label=label,
        note=payload.note.strip(),
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(link)
    db.flush()
    add_event(
        db,
        "topology_link_added",
        f"Added owner link #{link.id}: {label}",
        actor=user.user.username,
        evidence_ref=f"topology_link:{link.id}",
    )
    db.commit()
    return link_out(link)


@router.delete("/topology/annotations/{link_id}")
def delete_link(link_id: int, db: Db, user: CurrentSession, _csrf: Csrf) -> dict:
    link = db.get(TopologyLink, link_id)
    if link is None:
        error("not_found", "Link annotation not found", 404)
    add_event(
        db,
        "topology_link_removed",
        f"Removed owner link #{link.id}: {link.label}",
        actor=user.user.username,
    )
    db.delete(link)
    db.commit()
    return {"deleted": True}
