"""Persisted, bounded scan jobs and their API contract."""

import asyncio
from ipaddress import IPv4Address, IPv4Network

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from netsentinel.alerts import add_event, resolve_rule, upsert_alert
from netsentinel.auth import Csrf, CurrentSession, Db, error
from netsentinel.discovery import ProbeResult
from netsentinel.inventory import reconcile_device
from netsentinel.models import (
    Device,
    DeviceAddress,
    NetworkScope,
    Observation,
    ScanRun,
    ServiceObservation,
    utcnow,
)
from netsentinel.monitoring import read_settings, service_became_reachable
from netsentinel.timeutil import iso_utc

router = APIRouter(prefix="/api/v1/scans", tags=["scans"])


class ScanCreate(BaseModel):
    scope_id: int = Field(gt=0)


class ScanOut(BaseModel):
    id: int
    scope_id: int
    type: str
    status: str
    started_at: str | None
    finished_at: str | None
    host_count: int
    error_summary: str | None


def scan_out(scan: ScanRun) -> ScanOut:
    return ScanOut(
        id=scan.id,
        scope_id=scan.scope_id,
        type=scan.type,
        status=scan.status,
        started_at=iso_utc(scan.started_at),
        finished_at=iso_utc(scan.finished_at),
        host_count=scan.host_count,
        error_summary=scan.error_summary,
    )


def recover_interrupted(app) -> None:
    with app.state.session_factory() as db:
        interrupted = db.scalars(
            select(ScanRun).where(ScanRun.status.in_(["queued", "running"]))
        ).all()
        db.execute(
            update(ScanRun)
            .where(ScanRun.status.in_(["queued", "running"]))
            .values(
                status="failed",
                finished_at=utcnow(),
                error_summary="Interrupted by application restart",
            )
        )
        for run in interrupted:
            add_event(
                db,
                "scan_failed",
                f"Scan #{run.id} interrupted by restart",
                evidence_ref=f"scan:{run.id}",
            )
        db.commit()


def evaluate_reachability(db, observation: Observation) -> None:
    if observation.reachable is True:
        resolve_rule(db, observation.device_id, "offline")
    elif observation.reachable is False:
        threshold = read_settings(db).offline_threshold
        recent = db.scalars(
            select(Observation.reachable)
            .where(Observation.device_id == observation.device_id)
            .order_by(Observation.observed_at.desc(), Observation.id.desc())
            .limit(threshold)
        ).all()
        if len(recent) >= threshold and all(value is False for value in recent):
            device = db.get(Device, observation.device_id)
            name = device.display_name if device else f"Device #{observation.device_id}"
            upsert_alert(
                db,
                device_id=observation.device_id,
                rule_key="offline",
                summary=f"No response from {name}",
                details=(
                    f"No ICMP or configured TCP port responded in {threshold} consecutive scans. "
                    "Firewalls or client isolation can also cause this result."
                ),
                evidence_ref=f"observation:{observation.id}",
            )


def persist_result(db, run: ScanRun, result: ProbeResult) -> int | None:
    """Store immutable observations for a conservatively reconciled device."""
    if result.reachable is not True and not result.mac:
        return None
    now = utcnow()
    scope = db.get(NetworkScope, run.scope_id)
    device = reconcile_device(db, result, now, scope.profile_id if scope else None)
    prior = db.scalar(select(Observation.id).where(Observation.device_id == device.id).limit(1))
    prior_response = db.scalar(
        select(Observation.id)
        .where(Observation.device_id == device.id, Observation.reachable.is_(True))
        .limit(1)
    )
    reachable = result.reachable if result.reachable is True else False if prior else None
    response_text = "response" if reachable else "no probe response"
    summary = f"{result.source}; {len(result.services)} TCP ports; {response_text}"
    observation = Observation(
        device_id=device.id,
        scan_run_id=run.id,
        observed_at=now,
        source=result.source,
        ip=result.ip,
        reachable=reachable,
        latency_ms=result.latency_ms,
        raw_summary=summary,
    )
    db.add(observation)
    db.flush()
    if prior_response is None and reachable is True:
        upsert_alert(
            db,
            device_id=device.id,
            rule_key="new_device",
            summary=f"New device observed: {device.display_name}",
            details=(
                f"{result.ip} responded during scan #{run.id} via {result.source}. "
                f"Identity is {device.identity_confidence}; review before marking it familiar."
            ),
            evidence_ref=f"observation:{observation.id}",
        )
    evaluate_reachability(db, observation)
    for port, state in result.services.items():
        previous = db.scalar(
            select(ServiceObservation.state)
            .where(ServiceObservation.device_id == device.id, ServiceObservation.port == port)
            .order_by(ServiceObservation.observed_at.desc(), ServiceObservation.id.desc())
            .limit(1)
        )
        service = ServiceObservation(
            device_id=device.id,
            scan_run_id=run.id,
            ip=result.ip,
            port=port,
            protocol="tcp",
            state=state,
            observed_at=now,
        )
        db.add(service)
        db.flush()
        if service_became_reachable(previous, state):
            upsert_alert(
                db,
                device_id=device.id,
                rule_key=f"new_port:tcp:{port}",
                summary=f"TCP {port} became reachable on {device.display_name}",
                details=(
                    f"A bounded TCP connect succeeded at {result.ip}:{port} during scan #{run.id}. "
                    "This does not identify an application or prove a vulnerability."
                ),
                evidence_ref=f"service:{service.id}",
            )
    return device.id


async def execute_scan(app, run_id: int) -> None:
    with app.state.session_factory() as db:
        run = db.get(ScanRun, run_id)
        if run is None or run.status != "queued":
            return
        scope = db.get(NetworkScope, run.scope_id)
        if scope is None or not scope.enabled:
            run.status = "failed"
            run.error_summary = "Approved scope is no longer enabled"
            run.finished_at = utcnow()
            add_event(
                db,
                "scan_failed",
                f"Scan #{run.id} stopped: scope unavailable",
                evidence_ref=f"scan:{run.id}",
            )
            db.commit()
            return
        network = IPv4Network(scope.cidr, strict=True)
        if network.num_addresses > 256:
            run.status = "failed"
            run.error_summary = "Scope exceeds safety cap"
            run.finished_at = utcnow()
            add_event(
                db,
                "scan_failed",
                f"Scan #{run.id} stopped: safety cap",
                evidence_ref=f"scan:{run.id}",
            )
            db.commit()
            return
        run.status = "running"
        run.started_at = utcnow()
        add_event(
            db,
            "scan_started",
            f"Scan #{run.id} started for {scope.cidr}",
            evidence_ref=f"scan:{run.id}",
        )
        db.commit()
    try:
        results = await app.state.prober.scan(scope)
        if any(IPv4Address(result.ip) not in network for result in results):
            raise ValueError("Probe returned an out-of-scope address")
        with app.state.session_factory() as db:
            run = db.get(ScanRun, run_id)
            if run is None:
                return
            observed_ids: set[int] = set()
            for result in results:
                device_id = persist_result(db, run, result)
                if device_id is not None:
                    observed_ids.add(device_id)
            results_by_ip = {result.ip: result for result in results}
            missed_ids: set[int] = set()
            for address in db.scalars(
                select(DeviceAddress)
                .join(Device, Device.id == DeviceAddress.device_id)
                .where(Device.profile_id == scope.profile_id)
            ):
                if IPv4Address(address.ip) not in network:
                    continue
                result = results_by_ip.get(address.ip)
                if (
                    result is None
                    or result.reachable is True
                    or address.device_id in observed_ids
                    or address.device_id in missed_ids
                ):
                    continue
                missed_ids.add(address.device_id)
                now = utcnow()
                observation = Observation(
                    device_id=address.device_id,
                    scan_run_id=run.id,
                    observed_at=now,
                    source="bounded_probe",
                    ip=address.ip,
                    reachable=False,
                    latency_ms=None,
                    raw_summary="No ICMP or configured TCP port answered",
                )
                db.add(observation)
                db.flush()
                evaluate_reachability(db, observation)
                for port in [int(value) for value in scope.ports.split(",")]:
                    db.add(
                        ServiceObservation(
                            device_id=address.device_id,
                            scan_run_id=run.id,
                            ip=address.ip,
                            port=port,
                            protocol="tcp",
                            state="unknown",
                            observed_at=now,
                        )
                    )
            run.host_count = len(results)
            run.status = "completed"
            run.finished_at = utcnow()
            add_event(
                db,
                "scan_completed",
                f"Scan #{run.id} completed: {len(results)} addresses probed",
                evidence_ref=f"scan:{run.id}",
            )
            db.commit()
    except Exception as exc:
        with app.state.session_factory() as db:
            run = db.get(ScanRun, run_id)
            if run is not None:
                run.status = "failed"
                run.error_summary = str(exc)[:500]
                run.finished_at = utcnow()
                add_event(
                    db, "scan_failed", f"Scan #{run.id} failed", evidence_ref=f"scan:{run.id}"
                )
                db.commit()


async def scan_worker(app) -> None:
    while True:
        run_id = await app.state.scan_queue.get()
        try:
            await execute_scan(app, run_id)
        except Exception as exc:
            with app.state.session_factory() as db:
                run = db.get(ScanRun, run_id)
                if run is not None:
                    run.status = "failed"
                    run.error_summary = f"Worker error: {exc}"[:500]
                    run.finished_at = utcnow()
                    add_event(
                        db,
                        "scan_failed",
                        f"Scan #{run.id} worker error",
                        evidence_ref=f"scan:{run.id}",
                    )
                    db.commit()
        finally:
            app.state.scan_queue.task_done()


@router.post("", status_code=202)
async def create_scan(
    payload: ScanCreate, request: Request, db: Db, _user: CurrentSession, _csrf: Csrf
) -> ScanOut:
    scope = db.get(NetworkScope, payload.scope_id)
    if scope is None or not scope.enabled:
        error("scope_unavailable", "Choose an enabled approved range", 400)
    queue: asyncio.Queue[int] | None = getattr(request.app.state, "scan_queue", None)
    if queue is None:
        error("worker_unavailable", "Scan worker is not running", 503)
    active = (
        db.scalar(select(func.count(ScanRun.id)).where(ScanRun.status.in_(["queued", "running"])))
        or 0
    )
    if active >= 4 or queue.full():
        error("job_limit", "Too many scans are already queued or running", 429)
    run = ScanRun(scope_id=scope.id, type="manual", status="queued", host_count=0)
    db.add(run)
    db.flush()
    add_event(
        db,
        "scan_queued",
        f"Scan #{run.id} queued for {scope.cidr}",
        actor=_user.user.username,
        evidence_ref=f"scan:{run.id}",
    )
    db.commit()
    db.refresh(run)
    queue.put_nowait(run.id)
    return scan_out(run)


@router.get("")
def list_scans(db: Db, _user: CurrentSession, limit: int = 50, offset: int = 0) -> dict:
    if limit < 1 or limit > 100 or offset < 0:
        error("invalid_pagination", "Use limit 1–100 and nonnegative offset")
    total = db.scalar(select(func.count(ScanRun.id))) or 0
    items = db.scalars(select(ScanRun).order_by(ScanRun.id.desc()).limit(limit).offset(offset))
    return {
        "items": [scan_out(scan) for scan in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{run_id}")
def get_scan(run_id: int, db: Db, _user: CurrentSession) -> ScanOut:
    run = db.get(ScanRun, run_id)
    if run is None:
        error("not_found", "Scan not found", 404)
    return scan_out(run)
