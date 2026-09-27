from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from netsentinel.check_rules import _suppressed, evaluate_scan_rules
from netsentinel.db import Base
from netsentinel.discovery import ProbeResult
from netsentinel.inventory import reconcile_device
from netsentinel.main import create_app
from netsentinel.models import (
    Alert,
    MonitorCheck,
    MonitorRule,
    NetworkScope,
    ScanRun,
    ServiceObservation,
    utcnow,
)


def setup(path: Path) -> tuple[TestClient, int, int]:
    app = create_app(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory() as db:
        scope = NetworkScope(
            name="Test",
            cidr="10.0.0.0/28",
            enabled=True,
            approved_at=utcnow(),
            max_concurrency=1,
            connect_timeout_ms=100,
            ports="80",
        )
        db.add(scope)
        db.flush()
        device = reconcile_device(
            db,
            ProbeResult(
                ip="10.0.0.7",
                reachable=True,
                latency_ms=1,
                mac=None,
                source="tcp",
                services={80: "reachable"},
            ),
        )
        db.commit()
        scope_id, device_id = scope.id, device.id
    client = TestClient(app)
    assert (
        client.post(
            "/api/v1/auth/bootstrap", json={"username": "owner", "password": "a-long-test-password"}
        ).status_code
        == 201
    )
    return client, scope_id, device_id


def csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["netsentinel_csrf"]}


def add_check(client: TestClient, scope_id: int, device_id: int, state: str) -> None:
    with client.app.state.session_factory() as db:
        scope = db.get(NetworkScope, scope_id)
        run = ScanRun(scope_id=scope_id, type="manual", status="running", host_count=1)
        db.add(run)
        db.flush()
        db.add(
            ServiceObservation(
                device_id=device_id,
                scan_run_id=run.id,
                ip="10.0.0.7",
                port=80,
                protocol="tcp",
                state=state,
                observed_at=utcnow(),
            )
        )
        db.flush()
        evaluate_scan_rules(db, run, scope)
        db.commit()


def test_rule_contract_and_approved_port(tmp_path: Path) -> None:
    client, _, device_id = setup(tmp_path / "rules.db")
    path = f"/api/v1/devices/{device_id}/check-rules"
    assert client.post(path, json={"port": 80}).status_code == 403
    assert client.post(path, json={"port": 8080}, headers=csrf(client)).status_code == 400
    assert (
        client.post(
            path, json={"port": 80, "quiet_start_hour": 4}, headers=csrf(client)
        ).status_code
        == 400
    )
    created = client.post(path, json={"port": 80, "failure_threshold": 2}, headers=csrf(client))
    assert created.status_code == 201
    rule_id = created.json()["id"]
    assert client.get(path).json()[0]["port"] == 80
    assert (
        client.patch(
            f"/api/v1/check-rules/{rule_id}",
            json={"enabled": None},
            headers=csrf(client),
        ).status_code
        == 400
    )
    assert client.post(path, json={"port": 80}, headers=csrf(client)).status_code == 409
    assert (
        client.patch(
            f"/api/v1/check-rules/{rule_id}",
            json={"quiet_start_hour": 22, "quiet_end_hour": 6},
            headers=csrf(client),
        ).status_code
        == 200
    )


def test_threshold_quiet_and_recovery_from_scan_evidence(tmp_path: Path) -> None:
    client, scope_id, device_id = setup(tmp_path / "states.db")
    rule_id = client.post(
        f"/api/v1/devices/{device_id}/check-rules",
        json={"port": 80, "failure_threshold": 2},
        headers=csrf(client),
    ).json()["id"]
    add_check(client, scope_id, device_id, "unreachable")
    with client.app.state.session_factory() as db:
        assert (
            db.scalars(select(Alert).where(Alert.rule_key == f"check_rule:{rule_id}")).all() == []
        )
    add_check(client, scope_id, device_id, "unknown")
    with client.app.state.session_factory() as db:
        alert = db.scalar(select(Alert).where(Alert.rule_key == f"check_rule:{rule_id}"))
        assert alert is not None and alert.status == "active"
    add_check(client, scope_id, device_id, "reachable")
    with client.app.state.session_factory() as db:
        alert = db.scalar(select(Alert).where(Alert.rule_key == f"check_rule:{rule_id}"))
        assert alert is not None and alert.status == "resolved"
        assert len(db.scalars(select(MonitorCheck)).all()) == 3
    history = client.get(f"/api/v1/check-rules/{rule_id}/history").json()
    assert history["total"] == 3
    assert history["items"][0]["state"] == "reachable"
    until = (utcnow() + timedelta(hours=1)).isoformat()
    assert (
        client.patch(
            f"/api/v1/check-rules/{rule_id}",
            json={"maintenance_until": until},
            headers=csrf(client),
        ).status_code
        == 200
    )
    add_check(client, scope_id, device_id, "unknown")
    add_check(client, scope_id, device_id, "unknown")
    with client.app.state.session_factory() as db:
        checks = db.scalars(select(MonitorCheck).order_by(MonitorCheck.id.desc()).limit(2)).all()
        assert all(check.suppressed for check in checks)
        assert (
            len(db.scalars(select(Alert).where(Alert.rule_key == f"check_rule:{rule_id}")).all())
            == 1
        )
        rule = db.get(MonitorRule, rule_id)
        assert rule is not None and rule.maintenance_until is not None
    expired = (utcnow() - timedelta(minutes=1)).isoformat()
    assert (
        client.patch(
            f"/api/v1/check-rules/{rule_id}",
            json={"maintenance_until": expired},
            headers=csrf(client),
        ).status_code
        == 200
    )
    add_check(client, scope_id, device_id, "unknown")
    with client.app.state.session_factory() as db:
        alerts = db.scalars(select(Alert).where(Alert.rule_key == f"check_rule:{rule_id}")).all()
        assert len(alerts) == 2 and alerts[-1].status == "active"


def test_quiet_hours_support_overnight_utc_window() -> None:
    rule = MonitorRule(
        device_id=1,
        port=80,
        enabled=True,
        failure_threshold=2,
        quiet_start_hour=22,
        quiet_end_hour=6,
    )
    assert _suppressed(rule, datetime(2026, 9, 27, 23, tzinfo=UTC)) is True
    assert _suppressed(rule, datetime(2026, 9, 28, 5, tzinfo=UTC)) is True
    assert _suppressed(rule, datetime(2026, 9, 28, 12, tzinfo=UTC)) is False
