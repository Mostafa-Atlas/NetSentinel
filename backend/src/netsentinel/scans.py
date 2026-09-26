"""Persisted, bounded scan jobs and their API contract."""

import asyncio
from ipaddress import IPv4Address, IPv4Network

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from netsentinel.auth import Csrf, CurrentSession, Db, error
from netsentinel.discovery import ProbeResult
from netsentinel.inventory import reconcile_device
from netsentinel.models import (
    NetworkScope,
    Observation,
    ScanRun,
    ServiceObservation,
    utcnow,
)
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
        db.execute(
            update(ScanRun)
            .where(ScanRun.status.in_(["queued", "running"]))
            .values(
                status="failed",
                finished_at=utcnow(),
                error_summary="Interrupted by application restart",
            )
        )
        db.commit()


def persist_result(db, run: ScanRun, result: ProbeResult) -> bool:
    """Store immutable observations for a conservatively reconciled device."""
    if result.reachable is not True and not result.mac:
        return False
    now = utcnow()
    device = reconcile_device(db, result, now)
    db.add(
        Observation(
            device_id=device.id,
            scan_run_id=run.id,
            observed_at=now,
            source=result.source,
            reachable=result.reachable,
            latency_ms=result.latency_ms,
            raw_summary=f"{result.source} observation; {len(result.services)} TCP ports tested",
        )
    )
    for port, state in result.services.items():
        db.add(
            ServiceObservation(
                device_id=device.id,
                scan_run_id=run.id,
                ip=result.ip,
                port=port,
                protocol="tcp",
                state=state,
                observed_at=now,
            )
        )
    return True


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
            db.commit()
            return
        network = IPv4Network(scope.cidr, strict=True)
        if network.num_addresses > 256:
            run.status = "failed"
            run.error_summary = "Scope exceeds safety cap"
            run.finished_at = utcnow()
            db.commit()
            return
        run.status = "running"
        run.started_at = utcnow()
        db.commit()
    try:
        results = await app.state.prober.scan(scope)
        if any(IPv4Address(result.ip) not in network for result in results):
            raise ValueError("Probe returned an out-of-scope address")
        with app.state.session_factory() as db:
            run = db.get(ScanRun, run_id)
            if run is None:
                return
            for result in results:
                persist_result(db, run, result)
            run.host_count = len(results)
            run.status = "completed"
            run.finished_at = utcnow()
            db.commit()
    except Exception as exc:
        with app.state.session_factory() as db:
            run = db.get(ScanRun, run_id)
            if run is not None:
                run.status = "failed"
                run.error_summary = str(exc)[:500]
                run.finished_at = utcnow()
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
