"""Optional one-shot outbound host report. Configure the token in the environment."""

import argparse
import json
import os
import platform
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from ipaddress import ip_address
from urllib.parse import urlsplit


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def server_url(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Use an HTTPS server origin without credentials or query parameters")
    if parsed.path not in ("", "/"):
        raise ValueError("Use the server origin, without a path")
    if parsed.scheme == "https":
        return value.rstrip("/")
    try:
        loopback = parsed.hostname == "localhost" or ip_address(parsed.hostname).is_loopback
    except ValueError:
        loopback = parsed.hostname == "localhost"
    if parsed.scheme == "http" and loopback:
        return value.rstrip("/")
    raise ValueError("Remote agent reports require HTTPS")


def docker_containers() -> list[dict[str, str]]:
    try:
        process = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Names}}\t{{.State}}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return []
    if process.returncode != 0:
        return []
    entries = []
    for line in process.stdout.splitlines()[:32]:
        name, _, state = line.partition("\t")
        if not name or not state:
            continue
        entries.append(
            {
                "name": name[:100],
                "state": "running"
                if state == "running"
                else "stopped"
                if state == "exited"
                else "unknown",
            }
        )
    return entries


def host_report(include_docker: bool) -> dict:
    try:
        load_function = getattr(os, "getloadavg", None)
        load = load_function()[0] if load_function is not None else None
        if load is None:
            raise OSError("System load unavailable")
        if not 0 <= load <= 1000:
            load = None
    except (AttributeError, OSError):
        load = None
    return {
        "hostname": socket.gethostname()[:255],
        "os_name": f"{platform.system()} {platform.release()}"[:100],
        "load_1m": load,
        "containers": docker_containers() if include_docker else [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Send one optional NetSentinel host report")
    parser.add_argument(
        "--server", required=True, help="HTTPS NetSentinel origin, or loopback HTTP"
    )
    parser.add_argument(
        "--include-docker", action="store_true", help="Include local Docker names and states"
    )
    args = parser.parse_args()
    token = os.environ.get("NETSENTINEL_AGENT_TOKEN", "")
    if not token:
        parser.error("Set NETSENTINEL_AGENT_TOKEN in the environment")
    try:
        origin = server_url(args.server)
    except ValueError as exc:
        parser.error(str(exc))
    body = json.dumps(host_report(args.include_docker)).encode("utf-8")
    request = urllib.request.Request(
        f"{origin}/api/v1/agent/reports",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Agent-Timestamp": str(int(time.time())),
            "X-Agent-Nonce": secrets.token_hex(16),
        },
    )
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=10) as response:
            print(f"Report accepted (HTTP {response.status})")
        return 0
    except urllib.error.HTTPError as exc:
        print(f"Report rejected (HTTP {exc.code})", file=sys.stderr)
    except urllib.error.URLError:
        print("Report delivery failed", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
