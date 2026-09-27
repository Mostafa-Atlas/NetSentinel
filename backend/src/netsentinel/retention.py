"""Bounded probe-evidence retention; open alerts keep their cited evidence."""

from datetime import datetime, timedelta

from sqlalchemy import delete, or_, select

from netsentinel.models import (
    AgentNonce,
    AgentReport,
    Alert,
    DeviceHint,
    MonitorCheck,
    NotificationDelivery,
    Observation,
    ServiceObservation,
    utcnow,
)
from netsentinel.monitoring import read_settings


def purge_probe_history(app, now: datetime | None = None) -> tuple[int, int]:
    now = now or utcnow()
    with app.state.session_factory() as db:
        cutoff = now - timedelta(days=read_settings(db).retention_days)
        protected_observations: set[int] = set()
        protected_services: set[int] = set()
        protected_checks: set[int] = set()
        refs = db.scalars(
            select(Alert.evidence_ref).where(Alert.status.in_(["active", "acknowledged"]))
        )
        for ref in refs:
            kind, _, value = ref.partition(":")
            if value.isdigit():
                if kind == "observation":
                    protected_observations.add(int(value))
                elif kind == "service":
                    protected_services.add(int(value))
                elif kind == "check":
                    protected_checks.add(int(value))
        observations_query = delete(Observation).where(Observation.observed_at < cutoff)
        services_query = delete(ServiceObservation).where(ServiceObservation.observed_at < cutoff)
        if protected_observations:
            observations_query = observations_query.where(
                Observation.id.not_in(protected_observations)
            )
        if protected_services:
            services_query = services_query.where(ServiceObservation.id.not_in(protected_services))
        services_deleted = db.execute(services_query).rowcount or 0
        observations_deleted = db.execute(observations_query).rowcount or 0
        checks_query = delete(MonitorCheck).where(MonitorCheck.observed_at < cutoff)
        if protected_checks:
            checks_query = checks_query.where(MonitorCheck.id.not_in(protected_checks))
        db.execute(checks_query)
        db.execute(delete(DeviceHint).where(DeviceHint.observed_at < cutoff))
        db.execute(delete(AgentReport).where(AgentReport.received_at < cutoff))
        db.execute(delete(AgentNonce).where(AgentNonce.used_at < cutoff))
        db.execute(
            delete(NotificationDelivery).where(
                NotificationDelivery.status.in_(["delivered", "failed", "cancelled"]),
                or_(
                    NotificationDelivery.last_attempt_at < cutoff,
                    NotificationDelivery.last_attempt_at.is_(None)
                    & (NotificationDelivery.next_attempt_at < cutoff),
                ),
            )
        )
        db.commit()
        return observations_deleted, services_deleted
