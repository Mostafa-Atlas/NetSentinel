# NetSentinel

Self-hosted inventory and monitoring for a network you own or administer. The dashboard starts on localhost and performs no discovery until an administrator explicitly approves a private IPv4 scope.

## Local development

Requirements: Python 3.12+, Node 24+, and pnpm 11. From `backend`, create a virtual environment, run `pip install -r requirements.lock` and `pip install -e . --no-deps`, then run `alembic upgrade head` and `uvicorn netsentinel.main:app --reload --host 127.0.0.1`. From `frontend`, run `pnpm install --frozen-lockfile` and `pnpm dev`. Open <http://127.0.0.1:5173>.

On Windows PowerShell, use `py -3.12 -m venv .venv`, `& .\.venv\Scripts\python.exe -m pip install -r requirements.lock`, `& .\.venv\Scripts\python.exe -m pip install -e . --no-deps`, `& .\.venv\Scripts\alembic.exe upgrade head`, and `& .\.venv\Scripts\uvicorn.exe netsentinel.main:app --reload --host 127.0.0.1`. Linux uses `python3.12 -m venv .venv` and `.venv/bin/` equivalents.

## Checks

Backend: `ruff check src tests`, `ruff format --check src tests`, `mypy src`, `pytest`. Frontend: `pnpm lint`, `pnpm format:check`, `pnpm test`, `pnpm build`.

Build the frontend before backend `pytest` to run the controlled Chrome browser test. That test uses a migrated temporary database and a fake probe; it does not send packets to a LAN. Chrome and the pinned Playwright development dependency are required for this gate.

## Deployment and safety

`compose.yaml` provides a single application instance with persistent local SQLite data. Keep the default localhost bind or place a trusted HTTPS reverse proxy in front of it. Docker bridge networking may hide LAN MACs and neighbor details; host networking is an explicit opt-in. Discovery is limited to explicitly approved private IPv4 ranges, a maximum of 256 addresses, conservative concurrency and timeouts, and configured TCP ports. See [safety](docs/safety.md) and [architecture](docs/architecture.md).

Use the verified SQLite backup helper for online backups and stopped-service restoration. Exact native and Compose commands are in [operations](docs/operations.md). Keep backups private: they contain network inventory and account hashes.

On first load, create the single local administrator. Choose a strong password; NetSentinel ships no default credentials. In Settings, enter a canonical RFC 1918 IPv4 CIDR of at most 256 addresses, then explicitly confirm authorization before saving it. Scans cannot run without an enabled approved scope. Session cookies are HttpOnly and SameSite; changes require a CSRF token. For HTTPS reverse proxy deployments, set `NETSENTINEL_SECURE_COOKIES=true`.

Once a scope is approved, its **Run discovery** action shows the maximum probe volume before queueing. The API returns a job ID immediately; the Settings screen polls its status. Discovery uses unprivileged OS neighbor information, optional ICMP ping, and TCP connect attempts on ports 22, 80, and 443 by default. A missing response is unconfirmed, not automatically offline. Only observed hosts enter the inventory; a neighbor hint can create a provisional device with unknown reachability.

The Devices screen lets you search observed names and IPs, filter by familiarity, reachability, and open alerts, inspect address history, probe evidence, and device events, and add your own name and notes. A repeated MAC observation can link IP changes, while a different MAC on the same IP remains a separate identity. IP-only devices remain provisional. MACs can be randomized or spoofed, so no inferred identity is presented as certain.

Phase 2 P8 adds named network profiles in Settings. Each approved range belongs to one profile, and the same private CIDR can be used in separate profiles without combining their device identities. A profile export contains its private CIDRs and probe settings; keep it private and explicitly approve every range before configuring it on another installation. Device detail offers identity review. An owner can merge a provisional identity after comparing evidence, or split a distinct address when observations record its IP. A conflicting observed MAC blocks a merge, and ambiguous historical evidence blocks a split.

Phase 2 P9 adds an optional per-scope listener for mDNS and SSDP advertisements during a scan. It is off by default and changing it requires renewed scope approval. The listener sends no discovery request, keeps only bounded messages from the approved range, and attaches hints only to devices already observed by a probe or neighbor entry. Device detail labels each hint with its protocol, timestamp, and **unverified** confidence. Multicast availability varies by OS and Docker networking; an unavailable listener does not stop the normal bounded scan.

Phase 2 P10 adds per-device TCP check rules in device detail. A rule can use only a port already approved for an enabled scope containing that device. It evaluates results from normal manual or scheduled scans; it does not start an additional probe or use a separate interval. Set a threshold of 2–10 consecutive misses, optional UTC quiet hours, or a maintenance end time up to 30 days ahead. Quiet and maintenance periods suppress new rule alerts while retaining check history; a responding check resolves an open rule alert.

Phase 2 P11 adds an optional outbound host agent. Enroll a device in its detail screen and copy the one-time token to that host. The token is stored as a hash on the server, expires, and can be revoked. Set `NETSENTINEL_AGENT_TOKEN` in the host environment, then run `python backend/scripts/host_agent.py --server https://your-trusted-net-sentinel-origin` for one report. Use `--include-docker` only if you want to send local container names and states. The script refuses remote HTTP and redirects; the server accepts remote reports only over HTTPS. Loopback HTTP is allowed for same-host development. Reports identify the credential used, not the physical host independently. The agent never accepts dashboard commands.

Automatic monitoring is disabled by default. Settings can opt in to a schedule no faster than every 15 minutes and require at least two consecutive missed scans before labeling a device offline. Per-scope policy permits 1–16 explicit TCP ports, at most 32 concurrent hosts, and at most a 1-second connect timeout; changing that policy requires renewed approval. Device detail shows recent latency samples and a text summary. The scheduler is intended for one application process, as supplied by Compose.

Overview metrics show the last evidence update rather than implying continuous live telemetry. The network map groups observed devices under approved subnets. Every dashed line is an inferred IP-to-subnet relationship, not a verified router, Wi-Fi, cable, or switch-port path. A keyboard-operable device list exposes the same device details if graph rendering is unavailable.

The Alerts screen records first-responding devices, newly reachable configured TCP ports after an earlier baseline, and offline status only after the configured consecutive missed-scan threshold. Findings include scan evidence and explain their limits. Acknowledging or resolving an alert is an owner action recorded in the Timeline. The Overview shows recent events with timestamps. Probe observations older than the configured retention period are removed daily, except evidence cited by open alerts; alert and event history is retained.
