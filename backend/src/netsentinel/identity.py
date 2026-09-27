"""Owner-confirmed identity review; never infer a merge from an IP alone."""

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from netsentinel.alerts import add_event, resolve_alert
from netsentinel.auth import Csrf, CurrentSession, Db, error
from netsentinel.models import (
    AgentEnrollment,
    AgentReport,
    Alert,
    Device,
    DeviceAddress,
    DeviceHint,
    Event,
    MonitorRule,
    Observation,
    ServiceObservation,
    TopologyLink,
)

router = APIRouter(prefix="/api/v1/devices", tags=["identity"])


class MergeRequest(BaseModel):
    source_id: int = Field(gt=0)
    confirmed: bool


class SplitRequest(BaseModel):
    address_id: int = Field(gt=0)
    confirmed: bool


@router.get("/{device_id}/identity-review")
def identity_review(device_id: int, db: Db, _user: CurrentSession) -> dict:
    device = db.get(Device, device_id)
    if device is None:
        error("not_found", "Device not found", 404)
    addresses = db.scalars(select(DeviceAddress).where(DeviceAddress.device_id == device_id)).all()
    ips = {address.ip for address in addresses}
    macs = {address.mac for address in addresses if address.mac}
    candidates = []
    for other in db.scalars(
        select(Device).where(Device.id != device_id, Device.profile_id == device.profile_id)
    ):
        other_addresses = db.scalars(
            select(DeviceAddress).where(DeviceAddress.device_id == other.id)
        ).all()
        shared_ips = ips.intersection(address.ip for address in other_addresses)
        shared_macs = macs.intersection(address.mac for address in other_addresses if address.mac)
        if shared_ips or shared_macs:
            candidates.append(
                {
                    "id": other.id,
                    "display_name": other.display_name,
                    "shared_ips": sorted(shared_ips),
                    "shared_macs": sorted(shared_macs),
                    "warning": "A shared IP alone does not establish identity.",
                }
            )
    return {
        "device_id": device_id,
        "candidates": candidates,
        "addresses": [
            {"id": address.id, "ip": address.ip, "mac": address.mac} for address in addresses
        ],
    }


@router.post("/{target_id}/merge")
def merge_devices(
    target_id: int, payload: MergeRequest, db: Db, user: CurrentSession, _csrf: Csrf
) -> dict:
    if not payload.confirmed:
        error("confirmation_required", "Confirm this identity merge")
    if target_id == payload.source_id:
        error("invalid_merge", "Choose two different devices")
    target, source = db.get(Device, target_id), db.get(Device, payload.source_id)
    if target is None or source is None:
        error("not_found", "Device not found", 404)
    if target.profile_id != source.profile_id:
        error("different_profiles", "Devices in different profiles cannot be merged", 409)
    target_macs = set(
        db.scalars(
            select(DeviceAddress.mac).where(
                DeviceAddress.device_id == target_id, DeviceAddress.mac.is_not(None)
            )
        )
    )
    source_macs = set(
        db.scalars(
            select(DeviceAddress.mac).where(
                DeviceAddress.device_id == source.id, DeviceAddress.mac.is_not(None)
            )
        )
    )
    if target_macs and source_macs and not target_macs.intersection(source_macs):
        error("conflicting_identity", "Different observed MACs require separate identities", 409)
    target_rule_ports = set(
        db.scalars(select(MonitorRule.port).where(MonitorRule.device_id == target_id))
    )
    source_rule_ports = set(
        db.scalars(select(MonitorRule.port).where(MonitorRule.device_id == source.id))
    )
    if target_rule_ports.intersection(source_rule_ports):
        error("conflicting_rules", "Resolve duplicate check rules before merging", 409)
    for source_alert in db.scalars(select(Alert).where(Alert.device_id == source.id)).all():
        if source_alert.status in ("active", "acknowledged"):
            duplicate = db.scalar(
                select(Alert).where(
                    Alert.device_id == target_id,
                    Alert.rule_key == source_alert.rule_key,
                    Alert.status.in_(["active", "acknowledged"]),
                )
            )
            if duplicate:
                resolve_alert(db, source_alert, actor=user.user.username)
                db.flush()
        source_alert.device_id = target_id
    for model in (DeviceAddress, Observation, ServiceObservation, Event):
        db.execute(update(model).where(model.device_id == source.id).values(device_id=target_id))
    for related_model in (DeviceHint, MonitorRule, AgentEnrollment, AgentReport):
        db.execute(
            update(related_model)
            .where(related_model.device_id == source.id)
            .values(device_id=target_id)
        )
    for link in db.scalars(
        select(TopologyLink).where(
            (TopologyLink.source_id == source.id) | (TopologyLink.target_id == source.id)
        )
    ).all():
        other_id = link.target_id if link.source_id == source.id else link.source_id
        if (
            other_id == target_id
            or db.scalar(
                select(TopologyLink.id).where(
                    TopologyLink.source_id == min(target_id, other_id),
                    TopologyLink.target_id == max(target_id, other_id),
                )
            )
            is not None
        ):
            db.delete(link)
        else:
            link.source_id, link.target_id = sorted((target_id, other_id))
    target.first_seen_at = min(target.first_seen_at, source.first_seen_at)
    target.last_seen_at = max(target.last_seen_at, source.last_seen_at)
    if source_macs:
        target.identity_confidence = "observed_mac"
    add_event(
        db,
        "identity_merged",
        f"Merged device #{source.id} into #{target_id} after owner review",
        device_id=target_id,
        actor=user.user.username,
    )
    db.delete(source)
    db.commit()
    return {"device_id": target_id, "merged_device_id": payload.source_id}


@router.post("/{device_id}/split")
def split_device(
    device_id: int, payload: SplitRequest, db: Db, user: CurrentSession, _csrf: Csrf
) -> dict:
    if not payload.confirmed:
        error("confirmation_required", "Confirm this identity split")
    source = db.get(Device, device_id)
    address = db.get(DeviceAddress, payload.address_id)
    if source is None or address is None or address.device_id != device_id:
        error("not_found", "Device or address not found", 404)
    addresses = db.scalars(select(DeviceAddress).where(DeviceAddress.device_id == device_id)).all()
    if len(addresses) < 2:
        error("invalid_split", "A split requires at least two addresses", 409)
    if any(other.id != address.id and other.ip == address.ip for other in addresses):
        error("ambiguous_history", "This IP has multiple address records", 409)
    if db.scalar(
        select(Observation.id)
        .where(Observation.device_id == device_id, Observation.ip.is_(None))
        .limit(1)
    ):
        error("ambiguous_history", "Historical observations lack address provenance", 409)
    if any(
        db.scalar(select(model.id).where(model.device_id == device_id).limit(1))
        for model in (MonitorRule, AgentEnrollment, AgentReport)
    ):
        error(
            "ambiguous_configuration",
            "Remove device-scoped checks and agent enrollment before splitting",
            409,
        )
    new_device = Device(
        profile_id=source.profile_id,
        display_name=address.ip,
        identity_confidence="observed_mac" if address.mac else "provisional",
        known_state="unknown",
        notes="",
        first_seen_at=address.first_seen_at,
        last_seen_at=address.last_seen_at,
    )
    db.add(new_device)
    db.flush()
    moved_observations = db.scalars(
        select(Observation).where(Observation.device_id == device_id, Observation.ip == address.ip)
    ).all()
    moved_services = db.scalars(
        select(ServiceObservation).where(
            ServiceObservation.device_id == device_id, ServiceObservation.ip == address.ip
        )
    ).all()
    moved_hints = db.scalars(
        select(DeviceHint).where(DeviceHint.device_id == device_id, DeviceHint.ip == address.ip)
    ).all()
    moved_refs = {f"observation:{row.id}" for row in moved_observations} | {
        f"service:{row.id}" for row in moved_services
    }
    for alert in db.scalars(select(Alert).where(Alert.device_id == device_id)).all():
        if alert.evidence_ref in moved_refs:
            alert.device_id = new_device.id
    address.device_id = new_device.id
    for observation in moved_observations:
        observation.device_id = new_device.id
    for service in moved_services:
        service.device_id = new_device.id
    for hint in moved_hints:
        hint.device_id = new_device.id
    remaining = [item for item in addresses if item.id != address.id]
    source.first_seen_at = min(item.first_seen_at for item in remaining)
    source.last_seen_at = max(item.last_seen_at for item in remaining)
    add_event(
        db,
        "identity_split",
        f"Split address {address.ip} from device #{device_id} into #{new_device.id}",
        device_id=new_device.id,
        actor=user.user.username,
    )
    db.commit()
    return {"device_id": new_device.id, "source_device_id": device_id}
