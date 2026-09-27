from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from netsentinel.db import Base
from netsentinel.discovery import ProbeResult
from netsentinel.inventory import reconcile_device
from netsentinel.main import create_app
from netsentinel.models import DeviceAddress, NetworkScope, Observation, ScanRun, utcnow


def configured_client(path: Path) -> TestClient:
    app = create_app(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(app.state.engine)
    client = TestClient(app)
    assert (
        client.post(
            "/api/v1/auth/bootstrap", json={"username": "owner", "password": "a-long-test-password"}
        ).status_code
        == 201
    )
    return client


def csrf(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["netsentinel_csrf"]}


def result(ip: str, mac: str | None) -> ProbeResult:
    return ProbeResult(
        ip=ip, mac=mac, reachable=True, latency_ms=1, source="tcp", services={80: "reachable"}
    )


def test_profiles_require_auth_and_scope_approval(tmp_path: Path) -> None:
    client = configured_client(tmp_path / "profiles.db")
    assert client.post("/api/v1/profiles", json={"name": "Lab"}).status_code == 403
    profile = client.post(
        "/api/v1/profiles", json={"name": "Lab", "description": "Bench"}, headers=csrf(client)
    )
    assert profile.status_code == 201
    profile_id = profile.json()["id"]
    assert profile_id != 1
    assert client.get("/api/v1/profiles").json()[0]["name"] == "Default"
    assert (
        client.post(
            "/api/v1/scopes",
            json={
                "name": "Bench",
                "cidr": "10.5.0.0/28",
                "profile_id": profile_id,
                "approved": False,
            },
            headers=csrf(client),
        ).status_code
        == 400
    )
    created = client.post(
        "/api/v1/scopes",
        json={"name": "Bench", "cidr": "10.5.0.0/28", "profile_id": profile_id, "approved": True},
        headers=csrf(client),
    )
    assert created.status_code == 201
    assert created.json()["profile_id"] == profile_id
    other_profile_id = client.post(
        "/api/v1/profiles", json={"name": "Second lab"}, headers=csrf(client)
    ).json()["id"]
    assert (
        client.post(
            "/api/v1/scopes",
            json={
                "name": "Same range elsewhere",
                "cidr": "10.5.0.0/28",
                "profile_id": other_profile_id,
                "approved": True,
            },
            headers=csrf(client),
        ).status_code
        == 201
    )
    exported = client.get(f"/api/v1/profiles/{profile_id}/export").json()
    assert exported["requires_approval"] is True
    assert exported["scopes"][0]["cidr"] == "10.5.0.0/28"
    assert "approved_at" not in exported["scopes"][0]
    assert (
        client.post("/api/v1/profiles", json={"name": "Lab"}, headers=csrf(client)).status_code
        == 409
    )


def test_same_ip_in_different_profiles_stays_separate(tmp_path: Path) -> None:
    client = configured_client(tmp_path / "isolated.db")
    first = client.post("/api/v1/profiles", json={"name": "Home"}, headers=csrf(client)).json()[
        "id"
    ]
    second = client.post("/api/v1/profiles", json={"name": "Lab"}, headers=csrf(client)).json()[
        "id"
    ]
    with client.app.state.session_factory() as db:
        left = reconcile_device(db, result("10.0.0.7", None), profile_id=first)
        right = reconcile_device(db, result("10.0.0.7", None), profile_id=second)
        assert left.id != right.id
        db.commit()


def test_review_merge_and_split_preserve_provenance(tmp_path: Path) -> None:
    client = configured_client(tmp_path / "identity.db")
    app = client.app
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
        run = ScanRun(scope_id=scope.id, type="manual", status="completed", host_count=2)
        db.add(run)
        db.flush()
        target = reconcile_device(db, result("10.0.0.7", "aa:bb:cc:dd:ee:01"))
        source = reconcile_device(db, result("10.0.0.8", None))
        db.add(
            Observation(
                device_id=source.id,
                scan_run_id=run.id,
                observed_at=utcnow(),
                source="tcp",
                ip="10.0.0.8",
                reachable=True,
                latency_ms=1,
                raw_summary="mock",
            )
        )
        db.commit()
        target_id, source_id = target.id, source.id
    review = client.get(f"/api/v1/devices/{target_id}/identity-review")
    assert review.status_code == 200
    assert (
        client.post(
            f"/api/v1/devices/{target_id}/merge",
            json={"source_id": source_id, "confirmed": False},
            headers=csrf(client),
        ).status_code
        == 400
    )
    merged = client.post(
        f"/api/v1/devices/{target_id}/merge",
        json={"source_id": source_id, "confirmed": True},
        headers=csrf(client),
    )
    assert merged.status_code == 200
    assert client.get(f"/api/v1/devices/{source_id}").status_code == 404
    review = client.get(f"/api/v1/devices/{target_id}/identity-review").json()
    address = next(item for item in review["addresses"] if item["ip"] == "10.0.0.8")
    split = client.post(
        f"/api/v1/devices/{target_id}/split",
        json={"address_id": address["id"], "confirmed": True},
        headers=csrf(client),
    )
    assert split.status_code == 200, split.text
    new_id = split.json()["device_id"]
    assert new_id != target_id
    with app.state.session_factory() as db:
        assert (
            db.scalar(select(DeviceAddress.device_id).where(DeviceAddress.id == address["id"]))
            == new_id
        )
        assert (
            db.scalar(select(Observation.device_id).where(Observation.ip == "10.0.0.8")) == new_id
        )


def test_merge_refuses_conflicting_observed_macs(tmp_path: Path) -> None:
    client = configured_client(tmp_path / "conflict.db")
    with client.app.state.session_factory() as db:
        first = reconcile_device(db, result("10.0.0.7", "aa:bb:cc:dd:ee:01"))
        second = reconcile_device(db, result("10.0.0.7", "aa:bb:cc:dd:ee:02"))
        db.commit()
        first_id, second_id = first.id, second.id
    response = client.post(
        f"/api/v1/devices/{first_id}/merge",
        json={"source_id": second_id, "confirmed": True},
        headers=csrf(client),
    )
    assert response.status_code == 409
