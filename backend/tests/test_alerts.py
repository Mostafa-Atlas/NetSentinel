import asyncio
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from netsentinel.db import Base
from netsentinel.discovery import ProbeResult
from netsentinel.main import create_app
from netsentinel.models import Alert, Event, Observation, ScanRun, ServiceObservation, utcnow
from netsentinel.retention import purge_probe_history
from netsentinel.scans import execute_scan


class FakeProbe:
    def __init__(self, result: ProbeResult):
        self.result = result

    async def scan(self, _scope):
        return [self.result]


def run_fake(app, result: ProbeResult) -> None:
    app.state.prober = FakeProbe(result)
    with app.state.session_factory() as db:
        run = ScanRun(scope_id=1, type="manual", status="queued", host_count=0)
        db.add(run)
        db.commit()
        run_id = run.id
    asyncio.run(execute_scan(app, run_id))
    with app.state.session_factory() as db:
        assert db.get(ScanRun, run_id).status == "completed"


def test_alert_deduplication_workflow_and_timeline(tmp_path: Path) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    Base.metadata.create_all(app.state.engine)
    client = TestClient(app)
    assert client.get("/api/v1/alerts").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/bootstrap", json={"username": "owner", "password": "a-long-test-password"}
        ).status_code
        == 201
    )
    headers = {"X-CSRF-Token": client.cookies["netsentinel_csrf"]}
    assert (
        client.post(
            "/api/v1/scopes",
            json={"name": "Controlled", "cidr": "10.0.0.0/28", "approved": True, "ports": [80]},
            headers=headers,
        ).status_code
        == 201
    )
    reachable_closed = ProbeResult(
        "10.0.0.7", True, 2.0, "aa:bb:cc:dd:ee:ff", "tcp", {80: "unreachable"}
    )
    reachable_open = ProbeResult(
        "10.0.0.7", True, 2.0, "aa:bb:cc:dd:ee:ff", "tcp", {80: "reachable"}
    )
    missed = ProbeResult("10.0.0.7", None, None, None, "probe", {80: "unknown"})
    run_fake(app, reachable_closed)
    alerts = client.get("/api/v1/alerts?status=all").json()["items"]
    assert len(alerts) == 1 and alerts[0]["rule_key"] == "new_device"
    assert client.get("/api/v1/devices?alert_filter=open").json()["total"] == 1
    assert client.get("/api/v1/devices?alert_filter=clear").json()["total"] == 0
    assert client.get("/api/v1/devices?alert_filter=bogus").status_code == 400
    assert client.get("/api/v1/events?device_id=1").json()["total"] >= 1
    assert "Identity is" in alerts[0]["details"]
    run_fake(app, reachable_open)
    run_fake(app, reachable_open)
    alerts = client.get("/api/v1/alerts?status=all").json()["items"]
    assert len(alerts) == 2
    assert {item["rule_key"] for item in alerts} == {"new_device", "new_port:tcp:80"}
    device_alert = next(item for item in alerts if item["rule_key"] == "new_device")
    assert client.post(f"/api/v1/alerts/{device_alert['id']}/acknowledge").status_code == 403
    acknowledged = client.post(f"/api/v1/alerts/{device_alert['id']}/acknowledge", headers=headers)
    assert acknowledged.status_code == 200 and acknowledged.json()["status"] == "acknowledged"
    assert (
        client.post(f"/api/v1/alerts/{device_alert['id']}/acknowledge", headers=headers).status_code
        == 200
    )
    resolved = client.post(f"/api/v1/alerts/{device_alert['id']}/resolve", headers=headers)
    assert resolved.status_code == 200 and resolved.json()["status"] == "resolved"
    assert (
        client.post(f"/api/v1/alerts/{device_alert['id']}/acknowledge", headers=headers).status_code
        == 409
    )
    run_fake(app, reachable_open)
    assert client.get("/api/v1/alerts?status=all").json()["total"] == 2
    run_fake(app, missed)
    assert client.get("/api/v1/alerts?status=all").json()["total"] == 2
    run_fake(app, missed)
    assert client.get("/api/v1/alerts?status=all").json()["total"] == 3
    run_fake(app, missed)
    assert client.get("/api/v1/alerts?status=all").json()["total"] == 3
    offline = next(
        item
        for item in client.get("/api/v1/alerts?status=open").json()["items"]
        if item["rule_key"] == "offline"
    )
    assert "consecutive scans" in offline["details"]
    run_fake(app, reachable_open)
    assert client.get(f"/api/v1/alerts/{offline['id']}").json()["status"] == "resolved"
    assert client.get("/api/v1/overview").json()["active_alert_count"] == 1
    events = client.get("/api/v1/events").json()["items"]
    assert {event["event_type"] for event in events} >= {
        "alert_triggered",
        "alert_acknowledged",
        "alert_resolved",
        "scan_completed",
    }
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count(Alert.id))) == 3
        assert db.scalar(select(func.count(Event.id))) >= 10


def test_retention_preserves_open_alert_evidence(tmp_path: Path) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'retention.db').as_posix()}")
    Base.metadata.create_all(app.state.engine)
    client = TestClient(app)
    client.post(
        "/api/v1/auth/bootstrap", json={"username": "owner", "password": "a-long-test-password"}
    )
    headers = {"X-CSRF-Token": client.cookies["netsentinel_csrf"]}
    client.post(
        "/api/v1/scopes",
        json={"name": "Controlled", "cidr": "10.0.0.0/28", "approved": True, "ports": [80]},
        headers=headers,
    )
    run_fake(
        app, ProbeResult("10.0.0.7", True, 2.0, "aa:bb:cc:dd:ee:ff", "tcp", {80: "unreachable"})
    )
    run_fake(app, ProbeResult("10.0.0.7", True, 2.0, "aa:bb:cc:dd:ee:ff", "tcp", {80: "reachable"}))
    now = utcnow()
    with app.state.session_factory() as db:
        for row in db.scalars(select(Observation)):
            row.observed_at = now - timedelta(days=40)
        for row in db.scalars(select(ServiceObservation)):
            row.observed_at = now - timedelta(days=40)
        db.commit()
    assert purge_probe_history(app, now) == (1, 1)
    with app.state.session_factory() as db:
        refs = {alert.evidence_ref for alert in db.scalars(select(Alert))}
        assert refs == {
            f"observation:{db.scalar(select(Observation.id))}",
            f"service:{db.scalar(select(ServiceObservation.id))}",
        }
    for alert in client.get("/api/v1/alerts").json()["items"]:
        assert (
            client.post(f"/api/v1/alerts/{alert['id']}/resolve", headers=headers).status_code == 200
        )
    assert purge_probe_history(app, now) == (1, 1)


def test_first_response_after_neighbor_hint_triggers_new_device(tmp_path: Path) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'hint.db').as_posix()}")
    Base.metadata.create_all(app.state.engine)
    client = TestClient(app)
    client.post(
        "/api/v1/auth/bootstrap", json={"username": "owner", "password": "a-long-test-password"}
    )
    headers = {"X-CSRF-Token": client.cookies["netsentinel_csrf"]}
    client.post(
        "/api/v1/scopes",
        json={"name": "Controlled", "cidr": "10.0.0.0/28", "approved": True, "ports": [80]},
        headers=headers,
    )
    run_fake(
        app, ProbeResult("10.0.0.8", None, None, "aa:bb:cc:dd:ee:08", "neighbor", {80: "unknown"})
    )
    assert client.get("/api/v1/alerts").json()["total"] == 0
    run_fake(app, ProbeResult("10.0.0.8", True, 3.0, "aa:bb:cc:dd:ee:08", "tcp", {80: "reachable"}))
    alerts = client.get("/api/v1/alerts").json()["items"]
    assert any(item["rule_key"] == "new_device" for item in alerts)
