import secrets
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from netsentinel.db import Base
from netsentinel.discovery import ProbeResult
from netsentinel.inventory import reconcile_device
from netsentinel.main import create_app
from netsentinel.models import AgentReport
from scripts.host_agent import server_url


def setup(path: Path) -> tuple[TestClient, int]:
    app = create_app(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory() as db:
        device = reconcile_device(
            db,
            ProbeResult(
                ip="10.0.0.7", reachable=True, latency_ms=1, mac=None, source="tcp", services={}
            ),
        )
        db.commit()
        device_id = device.id
    client = TestClient(app, base_url="https://testserver")
    assert (
        client.post(
            "/api/v1/auth/bootstrap", json={"username": "owner", "password": "a-long-test-password"}
        ).status_code
        == 201
    )
    return client, device_id


def csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["netsentinel_csrf"]}


def agent_headers(
    token: str, nonce: str | None = None, timestamp: int | None = None
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Agent-Nonce": nonce or secrets.token_hex(16),
        "X-Agent-Timestamp": str(timestamp if timestamp is not None else int(time.time())),
    }


def test_scoped_agent_enrollment_transport_replay_and_revoke(tmp_path: Path) -> None:
    client, device_id = setup(tmp_path / "agents.db")
    path = f"/api/v1/devices/{device_id}/agent-enrollments"
    assert client.post(path, json={"name": "Desk"}).status_code == 403
    issued = client.post(path, json={"name": "Desk", "expires_days": 30}, headers=csrf(client))
    assert issued.status_code == 201
    token = issued.json()["token"]
    enrollment_id = issued.json()["id"]
    assert "token" not in client.get(path).json()[0]
    body = {"hostname": "desk", "os_name": "Linux", "load_1m": 0.5, "containers": []}
    nonce = secrets.token_hex(16)
    remote_http = TestClient(client.app, base_url="http://remote.test")
    assert (
        remote_http.post(
            "/api/v1/agent/reports",
            json=body,
            headers={**agent_headers(token, nonce), "X-Forwarded-Proto": "https"},
        ).status_code
        == 403
    )
    created = client.post("/api/v1/agent/reports", json=body, headers=agent_headers(token, nonce))
    assert created.status_code == 201, created.text
    assert created.json()["device_id"] == device_id
    assert (
        client.post(
            "/api/v1/agent/reports", json=body, headers=agent_headers(token, nonce)
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v1/agent/reports",
            json=body,
            headers=agent_headers(token, timestamp=int(time.time()) - 600),
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v1/agent/reports",
            json={**body, "device_id": 999},
            headers=agent_headers(token),
        ).status_code
        == 422
    )
    with client.app.state.session_factory() as db:
        assert len(db.scalars(select(AgentReport)).all()) == 1
    reports = client.get(f"/api/v1/devices/{device_id}/agent-reports").json()
    assert reports["total"] == 1
    assert reports["items"][0]["hostname"] == "desk"
    assert (
        client.post(
            f"/api/v1/agent-enrollments/{enrollment_id}/revoke", headers=csrf(client)
        ).status_code
        == 200
    )
    assert (
        client.post("/api/v1/agent/reports", json=body, headers=agent_headers(token)).status_code
        == 401
    )


def test_agent_report_bounds_and_invalid_token(tmp_path: Path) -> None:
    client, device_id = setup(tmp_path / "invalid.db")
    issued = client.post(
        f"/api/v1/devices/{device_id}/agent-enrollments",
        json={"name": "Desk"},
        headers=csrf(client),
    )
    token = issued.json()["token"]
    path = "/api/v1/agent/reports"
    body = {"hostname": "desk", "os_name": "Linux", "containers": []}
    assert client.post(path, json=body, headers=agent_headers("nsagent_1_bad")).status_code == 401
    assert (
        client.post(path, json=body, headers=agent_headers(token, nonce="short")).status_code == 400
    )
    assert (
        client.post(
            path,
            json={**body, "containers": [{"name": "x", "state": "running"}] * 33},
            headers=agent_headers(token),
        ).status_code
        == 422
    )


def test_host_agent_rejects_insecure_or_credentialed_server_url() -> None:
    assert server_url("https://sentinel.example") == "https://sentinel.example"
    assert server_url("http://127.0.0.1:8000") == "http://127.0.0.1:8000"
    with pytest.raises(ValueError):
        server_url("http://sentinel.example")
    with pytest.raises(ValueError):
        server_url("https://token@sentinel.example")
    with pytest.raises(ValueError):
        server_url("https://sentinel.example/path")
