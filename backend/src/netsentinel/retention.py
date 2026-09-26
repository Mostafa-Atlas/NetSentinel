"""Bounded probe-evidence retention; open alerts keep their cited evidence."""

from datetime import datetime, timedelta

from sqlalchemy import delete, select

from netsentinel.models import Alert, Observation, ServiceObservation, utcnow
from netsentinel.monitoring import read_settings


def purge_probe_history(app, now: datetime | None = None) -> tuple[int, int]:
    now = now or utcnow()
    with app.state.session_factory() as db:
        cutoff = now - timedelta(days=read_settings(db).retention_days)
        protected_observations: set[int] = set()
        protected_services: set[int] = set()
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
        db.commit()
        return observations_deleted, services_deleted
