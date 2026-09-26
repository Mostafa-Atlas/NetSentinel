import asyncio
from ipaddress import IPv4Network

import pytest

from netsentinel import discovery
from netsentinel.models import NetworkScope, utcnow


def scope(cidr: str, concurrency: int = 2) -> NetworkScope:
    return NetworkScope(
        name="Controlled",
        cidr=cidr,
        enabled=True,
        approved_at=utcnow(),
        max_concurrency=concurrency,
        connect_timeout_ms=100,
        ports="22,80",
    )


def test_default_runner_bounds_mocked_network(monkeypatch: pytest.MonkeyPatch) -> None:
    active = 0
    peak = 0

    def fake_neighbors(_network: IPv4Network) -> dict[str, str]:
        return {"10.0.0.1": "aa:bb:cc:dd:ee:ff"}

    async def fake_ping(_ip: str) -> bool:
        return False

    async def fake_tcp(ip: str, port: int, _timeout: float) -> tuple[str, bool]:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        return ("reachable", True) if ip == "10.0.0.7" and port == 80 else ("unknown", False)

    monkeypatch.setattr(discovery, "neighbors", fake_neighbors)
    monkeypatch.setattr(discovery, "ping", fake_ping)
    monkeypatch.setattr(discovery, "tcp_state", fake_tcp)
    results = asyncio.run(discovery.DefaultProbeRunner().scan(scope("10.0.0.0/28")))
    assert len(results) == 14
    assert peak <= 2
    assert next(result for result in results if result.ip == "10.0.0.7").reachable is True
    neighbor = next(result for result in results if result.ip == "10.0.0.1")
    assert neighbor.source == "neighbor" and neighbor.reachable is None
    with pytest.raises(ValueError, match="safety cap"):
        asyncio.run(discovery.DefaultProbeRunner().scan(scope("10.0.0.0/23")))
