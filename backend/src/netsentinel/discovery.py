"""Conservative, unprivileged LAN observation using OS neighbors and connect probes."""

import asyncio
import platform
import re
import subprocess
import time
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network

from netsentinel.models import NetworkScope

MAC_PATTERN = re.compile(r"\b([0-9a-fA-F]{2}(?:[:-][0-9a-fA-F]{2}){5})\b")
IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


@dataclass(frozen=True)
class ProbeResult:
    ip: str
    reachable: bool | None
    latency_ms: float | None
    mac: str | None
    source: str
    services: dict[int, str]


def neighbors(network: IPv4Network) -> dict[str, str]:
    """Read available neighbor hints. They do not establish current reachability."""
    command = ["arp", "-a"] if platform.system() == "Windows" else ["ip", "neigh", "show"]
    try:
        output = subprocess.run(
            command, capture_output=True, text=True, timeout=3, check=False
        ).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return {}
    found: dict[str, str] = {}
    for line in output.splitlines():
        ip_match, mac_match = IP_PATTERN.search(line), MAC_PATTERN.search(line)
        if ip_match and mac_match:
            try:
                ip = IPv4Address(ip_match.group())
            except ValueError:
                continue
            if ip in network:
                found[str(ip)] = mac_match.group().replace("-", ":").lower()
    return found


async def ping(ip: str) -> bool | None:
    command = (
        ["ping", "-n", "1", "-w", "1000", ip]
        if platform.system() == "Windows"
        else ["ping", "-c", "1", "-W", "1", ip]
    )
    process = None
    try:
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
        await asyncio.wait_for(process.wait(), timeout=2)
        return process.returncode == 0
    except TimeoutError:
        if process is not None:
            process.kill()
            await process.wait()
        return None
    except (FileNotFoundError, OSError):
        return None


async def tcp_state(ip: str, port: int, timeout: float) -> tuple[str, bool]:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=timeout)
        del reader
        writer.close()
        await writer.wait_closed()
        return "reachable", True
    except ConnectionRefusedError:
        return "unreachable", True
    except (TimeoutError, OSError):
        return "unknown", False


class DefaultProbeRunner:
    async def scan(self, scope: NetworkScope) -> list[ProbeResult]:
        network = IPv4Network(scope.cidr, strict=True)
        if network.num_addresses > 256:
            raise ValueError("Scope exceeds the 256-address safety cap")
        neighbor_map = await asyncio.to_thread(neighbors, network)
        semaphore = asyncio.Semaphore(min(scope.max_concurrency, 32))
        ports = [int(port) for port in scope.ports.split(",")]
        timeout = min(scope.connect_timeout_ms, 1000) / 1000

        async def one(ip: str) -> ProbeResult:
            async with semaphore:
                started = time.monotonic()
                icmp = await ping(ip)
                latency = round((time.monotonic() - started) * 1000, 1) if icmp is True else None
                services: dict[int, str] = {}
                responded = False
                for port in ports:
                    state, answer = await tcp_state(ip, port, timeout)
                    services[port] = state
                    responded = responded or answer
                    if answer and latency is None:
                        latency = round((time.monotonic() - started) * 1000, 1)
                reachable = True if icmp is True or responded else None
                source = (
                    "icmp"
                    if icmp is True
                    else "tcp"
                    if responded
                    else "neighbor"
                    if ip in neighbor_map
                    else "probe"
                )
                return ProbeResult(
                    ip=ip,
                    reachable=reachable,
                    latency_ms=latency,
                    mac=neighbor_map.get(ip),
                    source=source,
                    services=services,
                )

        return await asyncio.gather(*(one(str(ip)) for ip in network.hosts()))
