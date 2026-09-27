"""Short, opt-in passive mDNS/SSDP listening for unverified LAN hints."""

import asyncio
import logging
import re
import socket
from dataclasses import dataclass
from ipaddress import IPv4Address, IPv4Network

logger = logging.getLogger(__name__)
NAME_LABEL = re.compile(r"[A-Za-z0-9_-]{1,63}\Z")
SSDP_TYPE = re.compile(r"[A-Za-z0-9:._-]{1,120}\Z")


@dataclass(frozen=True)
class PassiveHint:
    ip: str
    source: str
    kind: str
    value: str


def _dns_name(packet: bytes, start: int) -> tuple[str, int] | None:
    labels: list[str] = []
    offset = start
    next_offset: int | None = None
    visited: set[int] = set()
    for _ in range(24):
        if offset >= len(packet) or offset in visited:
            return None
        visited.add(offset)
        length = packet[offset]
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(packet):
                return None
            target = ((length & 0x3F) << 8) | packet[offset + 1]
            if target >= len(packet):
                return None
            if next_offset is None:
                next_offset = offset + 2
            offset = target
            continue
        if length & 0xC0 or length > 63:
            return None
        offset += 1
        if length == 0:
            name = ".".join(labels)
            return (name, next_offset if next_offset is not None else offset)
        if offset + length > len(packet):
            return None
        try:
            label = packet[offset : offset + length].decode("ascii")
        except UnicodeDecodeError:
            return None
        if not NAME_LABEL.fullmatch(label):
            return None
        labels.append(label)
        if sum(len(part) + 1 for part in labels) > 253:
            return None
        offset += length
    return None


def parse_mdns(packet: bytes, sender: str, network: IPv4Network) -> list[PassiveHint]:
    if len(packet) < 12 or len(packet) > 2048:
        return []
    try:
        sender_ip = IPv4Address(sender)
    except ValueError:
        return []
    if sender_ip not in network or packet[2] & 0x80 == 0:
        return []
    questions = int.from_bytes(packet[4:6], "big")
    records = sum(int.from_bytes(packet[index : index + 2], "big") for index in (6, 8, 10))
    if questions > 32 or records > 64:
        return []
    offset = 12
    for _ in range(questions):
        parsed = _dns_name(packet, offset)
        if parsed is None or parsed[1] + 4 > len(packet):
            return []
        offset = parsed[1] + 4
    found: list[PassiveHint] = []
    for _ in range(records):
        parsed = _dns_name(packet, offset)
        if parsed is None or parsed[1] + 10 > len(packet):
            return []
        name, offset = parsed
        kind = int.from_bytes(packet[offset : offset + 2], "big")
        record_class = int.from_bytes(packet[offset + 2 : offset + 4], "big") & 0x7FFF
        ttl = int.from_bytes(packet[offset + 4 : offset + 8], "big")
        length = int.from_bytes(packet[offset + 8 : offset + 10], "big")
        offset += 10
        if offset + length > len(packet):
            return []
        data = packet[offset : offset + length]
        offset += length
        if kind == 1 and record_class == 1 and ttl > 0 and length == 4:
            ip = IPv4Address(data)
            if ip == sender_ip and name.lower().endswith(".local"):
                found.append(PassiveHint(str(ip), "mdns", "hostname", name[:255]))
    return found


def parse_ssdp(packet: bytes, sender: str, network: IPv4Network) -> list[PassiveHint]:
    if len(packet) > 2048:
        return []
    try:
        if IPv4Address(sender) not in network:
            return []
        message = packet.decode("ascii")
    except (ValueError, UnicodeDecodeError):
        return []
    lines = message.split("\r\n")
    if not lines or lines[0] != "NOTIFY * HTTP/1.1" or len(lines) > 40:
        return []
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            break
        if ":" not in line:
            return []
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    advertised = headers.get("nt", "")
    if headers.get("nts", "").lower() != "ssdp:alive" or not SSDP_TYPE.fullmatch(advertised):
        return []
    return [PassiveHint(sender, "ssdp", "advertised_type", advertised)]


def _open_multicast_socket(group: str, port: int) -> socket.socket | None:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    except OSError:
        logger.info("passive_listener_unavailable", extra={"port": port})
        return None
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", port))
        membership = socket.inet_aton(group) + socket.inet_aton("0.0.0.0")
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
        sock.setblocking(False)
        return sock
    except OSError:
        sock.close()
        logger.info("passive_listener_unavailable", extra={"port": port})
        return None


async def collect_hints(network: IPv4Network, seconds: float = 3.0) -> list[PassiveHint]:
    """Listen briefly; send no discovery packets and retain only in-scope hints."""
    listeners = [
        ("224.0.0.251", 5353, parse_mdns),
        ("239.255.255.250", 1900, parse_ssdp),
    ]
    sockets = [
        (sock, parser)
        for group, port, parser in listeners
        if (sock := _open_multicast_socket(group, port))
    ]
    if not sockets:
        return []
    loop = asyncio.get_running_loop()
    deadline = loop.time() + min(max(seconds, 0.1), 3.0)
    found: set[PassiveHint] = set()

    async def read(sock: socket.socket, parser) -> None:
        count = 0
        while count < 128:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                packet, sender = await asyncio.wait_for(loop.sock_recvfrom(sock, 2049), remaining)
            except (TimeoutError, OSError):
                break
            count += 1
            if len(packet) <= 2048:
                found.update(parser(packet, sender[0], network))

    try:
        await asyncio.gather(*(read(sock, parser) for sock, parser in sockets))
    finally:
        for sock, _ in sockets:
            sock.close()
    return list(found)[:128]
