from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from netsentinel.db import Base
from netsentinel.main import create_app
from netsentinel.models import User


def client_for(path: Path) -> TestClient:
    app = create_app(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(app.state.engine)
    return TestClient(app)


def bootstrap(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/bootstrap", json={"username": "owner", "password": "a-long-test-password"}
    )
    assert response.status_code == 201


def csrf_headers(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies["netsentinel_csrf"]}


def test_bootstrap_auth_and_scope_validation(tmp_path: Path) -> None:
    client = client_for(tmp_path / "test.db")
    assert client.get("/api/v1/auth/bootstrap-status").json() == {"needs_setup": True}
    assert client.get("/api/v1/scopes").status_code == 401
    bootstrap(client)
    assert client.get("/api/v1/auth/bootstrap-status").json() == {"needs_setup": False}
    assert client.get("/api/v1/auth/me").json() == {"username": "owner"}
    assert (
        client.post(
            "/api/v1/auth/bootstrap",
            json={"username": "other", "password": "another-long-password"},
        ).status_code
        == 409
    )

    for cidr in (
        "8.8.8.0/24",
        "127.0.0.0/24",
        "169.254.0.0/24",
        "192.168.0.0/23",
        "192.168.1.7/24",
        "2001:db8::/64",
    ):
        result = client.post(
            "/api/v1/scopes",
            json={"name": "bad", "cidr": cidr, "approved": True},
            headers=csrf_headers(client),
        )
        assert result.status_code == 422, (cidr, result.json())
    payload = {"name": "Home", "cidr": "192.168.1.0/24", "approved": False}
    assert (
        client.post("/api/v1/scopes", json=payload, headers=csrf_headers(client)).status_code == 400
    )
    payload["approved"] = True
    assert client.post("/api/v1/scopes", json=payload).status_code == 403
    created = client.post("/api/v1/scopes", json=payload, headers=csrf_headers(client))
    assert created.status_code == 201
    assert created.json()["cidr"] == "192.168.1.0/24"
    assert len(client.get("/api/v1/scopes").json()) == 1
    assert (
        client.post("/api/v1/scopes", json=payload, headers=csrf_headers(client)).status_code == 409
    )
    assert (
        client.patch(
            "/api/v1/scopes/1", json={"enabled": False}, headers=csrf_headers(client)
        ).status_code
        == 200
    )
    assert (
        client.patch(
            "/api/v1/scopes/1", json={"enabled": True}, headers=csrf_headers(client)
        ).status_code
        == 400
    )
    assert (
        client.patch(
            "/api/v1/scopes/1",
            json={"enabled": True, "approved": True},
            headers=csrf_headers(client),
        ).status_code
        == 200
    )
    assert client.post("/api/v1/auth/logout", headers=csrf_headers(client)).status_code == 200
    assert client.get("/api/v1/scopes").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "owner", "password": "a-long-test-password"}
        ).status_code
        == 200
    )


def test_login_rate_limit_and_origin(tmp_path: Path) -> None:
    client = client_for(tmp_path / "test.db")
    bootstrap(client)
    bad = {"username": "owner", "password": "incorrect-password"}
    for _ in range(5):
        assert client.post("/api/v1/auth/login", json=bad).status_code == 401
    assert client.post("/api/v1/auth/login", json=bad).status_code == 429
    assert (
        client.post(
            "/api/v1/auth/login", json=bad, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )


def test_database_enforces_one_administrator(tmp_path: Path) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory() as db:
        db.add(User(username="first", password_hash="test"))
        db.commit()
        db.add(User(username="second", password_hash="test"))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        else:
            raise AssertionError("A second administrator was accepted")
