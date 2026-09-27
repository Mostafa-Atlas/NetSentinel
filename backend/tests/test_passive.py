import asyncio
import struct
from ipaddress import IPv4Network
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from netsentinel import discovery
from netsentinel.db import Base
from netsentinel.discovery import ProbeResult
from netsentinel.main import create_app
from netsentinel.models import DeviceHint, NetworkScope, ScanRun, utcnow
from netsentinel.passive import PassiveHint, parse_mdns, parse_ssdp
from netsentinel.scans import persist_result

NETWORK = IPv4Network("10.0.0.0/28")


def mdns_a_packet(name: bytes, ip: bytes) -> bytes:
    return (
        struct.pack("!HHHHHH", 0, 0x8400, 0, 1, 0, 0)
        + name
        + struct.pack("!HHIH", 1, 1, 120, 4)
        + ip
    )


def test_strict_passive_parsers_reject_untrusted_or_malformed_data() -> None:
    packet = mdns_a_packet(b"\x04desk\x05local\x00", b"\x0a\x00\x00\x07")
    assert parse_mdns(packet, "10.0.0.7", NETWORK) == [
        PassiveHint("10.0.0.7", "mdns", "hostname", "desk.local")
    ]
    assert parse_mdns(packet, "10.0.0.8", NETWORK) == []
    assert parse_mdns(packet, "10.0.1.7", NETWORK) == []
    assert parse_mdns(mdns_a_packet(b"\xc0\x0c", b"\x0a\x00\x00\x07"), "10.0.0.7", NETWORK) == []
    advertised_type = "urn:schemas-upnp-org:device:MediaServer:1"
    alive = (
        b"NOTIFY * HTTP/1.1\r\n"
        b"NT: urn:schemas-upnp-org:device:MediaServer:1\r\n"
        b"NTS: ssdp:alive\r\n\r\n"
    )
    assert parse_ssdp(alive, "10.0.0.7", NETWORK) == [
        PassiveHint("10.0.0.7", "ssdp", "advertised_type", advertised_type)
    ]
    assert parse_ssdp(alive.replace(b"ssdp:alive", b"ssdp:byebye"), "10.0.0.7", NETWORK) == []
    assert parse_ssdp(alive, "10.0.1.7", NETWORK) == []
    assert parse_ssdp(alive + b"x" * 2048, "10.0.0.7", NETWORK) == []


def test_passive_listener_requires_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    async def fake_collect(_network: IPv4Network) -> list[PassiveHint]:
        nonlocal called
        called = True
        return []

    async def fake_ping(_ip: str) -> bool:
        return False

    async def fake_tcp(_ip: str, _port: int, _timeout: float) -> tuple[str, bool]:
        return "unknown", False

    monkeypatch.setattr(discovery, "collect_hints", fake_collect)
    monkeypatch.setattr(discovery, "neighbors", lambda _network: {})
    monkeypatch.setattr(discovery, "ping", fake_ping)
    monkeypatch.setattr(discovery, "tcp_state", fake_tcp)
    scope = NetworkScope(
        name="Test",
        cidr="10.0.0.0/30",
        enabled=True,
        approved_at=utcnow(),
        max_concurrency=1,
        connect_timeout_ms=100,
        ports="80",
        passive_enabled=False,
    )
    asyncio.run(discovery.DefaultProbeRunner().scan(scope))
    assert called is False
    scope.passive_enabled = True
    asyncio.run(discovery.DefaultProbeRunner().scan(scope))
    assert called is True


def test_hints_attach_only_to_observed_device_and_are_labeled_unverified(tmp_path: Path) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'hints.db').as_posix()}")
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
            passive_enabled=True,
        )
        db.add(scope)
        db.flush()
        run = ScanRun(scope_id=scope.id, type="manual", status="completed", host_count=1)
        db.add(run)
        db.flush()
        result = ProbeResult(
            ip="10.0.0.7",
            reachable=True,
            latency_ms=1,
            mac=None,
            source="tcp",
            services={},
            hints=(
                PassiveHint("10.0.0.7", "mdns", "hostname", "desk.local"),
                PassiveHint("10.0.1.9", "ssdp", "advertised_type", "bad"),
            ),
        )
        device_id = persist_result(db, run, result)
        scope.passive_enabled = False
        persist_result(
            db,
            run,
            ProbeResult(
                ip="10.0.0.8",
                reachable=True,
                latency_ms=1,
                mac=None,
                source="tcp",
                services={},
                hints=(PassiveHint("10.0.0.8", "mdns", "hostname", "ignored.local"),),
            ),
        )
        db.commit()
        assert device_id is not None
        assert len(db.scalars(select(DeviceHint)).all()) == 1
    client = TestClient(app)
    assert client.get(f"/api/v1/devices/{device_id}/hints").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/bootstrap", json={"username": "owner", "password": "a-long-test-password"}
        ).status_code
        == 201
    )
    hints = client.get(f"/api/v1/devices/{device_id}/hints").json()["items"]
    assert hints[0]["source"] == "mdns"
    assert hints[0]["confidence"] == "unverified_advertisement"


def test_enabling_passive_listener_requires_renewed_approval(tmp_path: Path) -> None:
    app = create_app(f"sqlite:///{(tmp_path / 'approval.db').as_posix()}")
    Base.metadata.create_all(app.state.engine)
    client = TestClient(app)
    assert (
        client.post(
            "/api/v1/auth/bootstrap", json={"username": "owner", "password": "a-long-test-password"}
        ).status_code
        == 201
    )
    headers = {"X-CSRF-Token": client.cookies["netsentinel_csrf"]}
    scope = client.post(
        "/api/v1/scopes",
        json={"name": "Test", "cidr": "10.0.0.0/28", "approved": True},
        headers=headers,
    ).json()
    assert scope["passive_enabled"] is False
    assert (
        client.patch(
            f"/api/v1/scopes/{scope['id']}",
            json={"passive_enabled": True},
            headers=headers,
        ).status_code
        == 400
    )
    enabled = client.patch(
        f"/api/v1/scopes/{scope['id']}",
        json={"passive_enabled": True, "approved": True},
        headers=headers,
    )
    assert enabled.status_code == 200
    assert enabled.json()["passive_enabled"] is True
