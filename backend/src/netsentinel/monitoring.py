"""Opt-in single-instance scheduling and validated monitoring settings."""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from netsentinel.alerts import add_event
from netsentinel.auth import Csrf, CurrentSession, Db
from netsentinel.models import NetworkScope, ScanRun, Setting, utcnow

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])
logger = logging.getLogger(__name__)


class MonitoringSettings(BaseModel):
    schedule_enabled: bool = False
    interval_minutes: int = Field(default=30, ge=15, le=1440)
    offline_threshold: int = Field(default=2, ge=2, le=10)
    retention_days: int = Field(default=30, ge=7, le=365)


class SettingsPatch(BaseModel):
    schedule_enabled: bool | None = None
    interval_minutes: int | None = Field(default=None, ge=15, le=1440)
    offline_threshold: int | None = Field(default=None, ge=2, le=10)
    retention_days: int | None = Field(default=None, ge=7, le=365)


def read_settings(db: DBSession) -> MonitoringSettings:
    saved = {row.key: json.loads(row.value) for row in db.scalars(select(Setting))}
    return MonitoringSettings.model_validate(saved)


def service_became_reachable(previous_state: str | None, current_state: str) -> bool:
    """The first observation establishes a baseline; later transitions matter."""
    return previous_state in ("unreachable", "unknown") and current_state == "reachable"


def ensure_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def schedule_once(app, now: datetime | None = None) -> int:
    now = now or utcnow()
    queue: asyncio.Queue[int] | None = getattr(app.state, "scan_queue", None)
    if queue is None or queue.full():
        return 0
    created = 0
    with app.state.session_factory() as db:
        settings = read_settings(db)
        if not settings.schedule_enabled:
            return 0
        scopes = db.scalars(select(NetworkScope).where(NetworkScope.enabled.is_(True))).all()
        for scope in scopes:
            if queue.full():
                break
            latest = db.scalar(
                select(ScanRun).where(ScanRun.scope_id == scope.id).order_by(ScanRun.id.desc())
            )
            if latest and latest.status in ("queued", "running"):
                continue
            last_time = (latest.finished_at or latest.started_at) if latest else None
            if last_time and now - ensure_utc(last_time) < timedelta(
                minutes=settings.interval_minutes
            ):
                continue
            run = ScanRun(scope_id=scope.id, type="scheduled", status="queued", host_count=0)
            db.add(run)
            db.flush()
            add_event(
                db,
                "scan_queued",
                f"Scheduled scan #{run.id} queued for {scope.cidr}",
                evidence_ref=f"scan:{run.id}",
            )
            db.commit()
            queue.put_nowait(run.id)
            created += 1
    return created


async def scheduler_loop(app) -> None:
    from netsentinel.retention import purge_probe_history

    last_retention_at: datetime | None = None
    while True:
        try:
            schedule_once(app)
            now = utcnow()
            if last_retention_at is None or now - last_retention_at >= timedelta(days=1):
                purge_probe_history(app, now)
                last_retention_at = now
        except Exception:
            logger.exception("scheduler_tick_failed")
        await asyncio.sleep(30)


@router.get("")
def get_settings(db: Db, _user: CurrentSession) -> MonitoringSettings:
    return read_settings(db)


@router.patch("")
def patch_settings(
    payload: SettingsPatch, db: Db, _user: CurrentSession, _csrf: Csrf
) -> MonitoringSettings:
    current = read_settings(db).model_dump()
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            current[key] = value
    settings = MonitoringSettings.model_validate(current)
    for key, value in settings.model_dump().items():
        row = db.get(Setting, key)
        if row is None:
            row = Setting(key=key, value=json.dumps(value), updated_at=utcnow())
            db.add(row)
        else:
            row.value = json.dumps(value)
            row.updated_at = utcnow()
    add_event(db, "settings_updated", "Monitoring settings updated", actor=_user.user.username)
    db.commit()
    return settings
