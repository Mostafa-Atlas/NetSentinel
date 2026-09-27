import json
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from netsentinel.alerts import upsert_alert
from netsentinel.db import Base
from netsentinel.main import create_app
from netsentinel.models import Device, NotificationDelivery, Setting, utcnow
from netsentinel.notifications import deliver_pending, webhook_url
from netsentinel.retention import purge_probe_history


def setup(tmp_path: Path):
    app = create_app(f"sqlite:///{(tmp_path / 'notifications.db').as_posix()}")
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory() as db:
        device = Device(
            display_name="Desk",
            identity_confidence="provisional",
            known_state="unknown",
            notes="",
            first_seen_at=utcnow(),
            last_seen_at=utcnow(),
        )
        db.add(device)
        db.commit()
        device_id = device.id
    client = TestClient(app)
    assert (
        client.post(
            "/api/v1/auth/bootstrap", json={"username": "owner", "password": "a-long-test-password"}
        ).status_code
        == 201
    )
    return app, client, device_id


def test_notification_opt_in_outbox_and_retry(tmp_path: Path, monkeypatch) -> None:
    app, client, device_id = setup(tmp_path)
    headers = {"X-CSRF-Token": client.cookies["netsentinel_csrf"]}
    assert (
        client.patch(
            "/api/v1/settings", json={"notification_enabled": True}, headers=headers
        ).status_code
        == 400
    )
    monkeypatch.setenv("NETSENTINEL_WEBHOOK_URL", "http://example.test/hook")
    assert webhook_url() is None
    monkeypatch.setenv("NETSENTINEL_WEBHOOK_URL", "https://example.test/hook")
    monkeypatch.setenv("NETSENTINEL_WEBHOOK_TOKEN", "a-test-secret")
    assert (
        client.patch(
            "/api/v1/settings", json={"notification_enabled": True}, headers=headers
        ).status_code
        == 200
    )
    with app.state.session_factory() as db:
        alert, created = upsert_alert(
            db,
            device_id=device_id,
            rule_key="test",
            summary="Desk alert",
            details="Test",
            evidence_ref="test:1",
        )
        assert created
        db.commit()
        alert_id = alert.id
        _, created = upsert_alert(
            db,
            device_id=device_id,
            rule_key="test",
            summary="Desk alert",
            details="Test",
            evidence_ref="test:2",
        )
        assert not created
        db.commit()
        assert len(db.scalars(select(NotificationDelivery)).all()) == 1
    sent = []

    def fail(_url, _payload):
        raise OSError("private failure detail")

    now = utcnow()
    assert deliver_pending(app, now, sender=fail) == 1
    assert deliver_pending(app, now, sender=fail) == 0

    def success(url, payload):
        sent.append((url, json.loads(payload)))

    assert deliver_pending(app, now + timedelta(minutes=6), sender=success) == 1
    assert sent[0][1]["alert_id"] == alert_id
    status = client.get("/api/v1/notifications").json()
    assert status["deliveries"][0]["status"] == "delivered"
    assert "a-test-secret" not in json.dumps(status)
    assert "example.test" not in json.dumps(status)
    assert purge_probe_history(app, now + timedelta(days=40)) == (0, 0)
    with app.state.session_factory() as db:
        assert db.scalars(select(NotificationDelivery)).all() == []


def test_notification_disabled_by_default(tmp_path: Path, monkeypatch) -> None:
    app, _, device_id = setup(tmp_path)
    monkeypatch.setenv("NETSENTINEL_WEBHOOK_URL", "https://example.test/hook")
    with app.state.session_factory() as db:
        upsert_alert(
            db,
            device_id=device_id,
            rule_key="test",
            summary="Test",
            details="Test",
            evidence_ref="test:1",
        )
        db.commit()
        assert db.scalars(select(NotificationDelivery)).all() == []
        assert db.get(Setting, "notification_enabled") is None


def test_disabling_notifications_cancels_pending(tmp_path: Path, monkeypatch) -> None:
    app, client, device_id = setup(tmp_path)
    monkeypatch.setenv("NETSENTINEL_WEBHOOK_URL", "https://example.test/hook")
    headers = {"X-CSRF-Token": client.cookies["netsentinel_csrf"]}
    assert (
        client.patch(
            "/api/v1/settings", json={"notification_enabled": True}, headers=headers
        ).status_code
        == 200
    )
    with app.state.session_factory() as db:
        upsert_alert(
            db,
            device_id=device_id,
            rule_key="test",
            summary="Test",
            details="Test",
            evidence_ref="test:1",
        )
        db.commit()
    assert (
        client.patch(
            "/api/v1/settings", json={"notification_enabled": False}, headers=headers
        ).status_code
        == 200
    )
    assert (
        client.patch(
            "/api/v1/settings", json={"notification_enabled": True}, headers=headers
        ).status_code
        == 200
    )
    assert deliver_pending(app, sender=lambda *_: None) == 0
    assert client.get("/api/v1/notifications").json()["deliveries"][0]["status"] == "cancelled"
