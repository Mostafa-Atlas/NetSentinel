# NetSentinel

Self-hosted inventory and monitoring for a network you own or administer. The dashboard starts on localhost and performs no discovery until an administrator explicitly approves a private IPv4 scope.

## Local development

Requirements: Python 3.12+, Node 24+, and pnpm 11. From `backend`, create a virtual environment, run `pip install -r requirements.lock` and `pip install -e . --no-deps`, then run `alembic upgrade head` and `uvicorn netsentinel.main:app --reload --host 127.0.0.1`. From `frontend`, run `pnpm install --frozen-lockfile` and `pnpm dev`. Open <http://127.0.0.1:5173>.

On Windows PowerShell, use `py -3.12 -m venv .venv`, `& .\.venv\Scripts\python.exe -m pip install -r requirements.lock`, `& .\.venv\Scripts\python.exe -m pip install -e . --no-deps`, `& .\.venv\Scripts\alembic.exe upgrade head`, and `& .\.venv\Scripts\uvicorn.exe netsentinel.main:app --reload --host 127.0.0.1`. Linux uses `python3.12 -m venv .venv` and `.venv/bin/` equivalents.

## Checks

Backend: `ruff check src tests`, `ruff format --check src tests`, `mypy src`, `pytest`. Frontend: `pnpm lint`, `pnpm format:check`, `pnpm test`, `pnpm build`.

## Deployment and safety

`compose.yaml` provides a single application instance with persistent local SQLite data. Keep the default localhost bind or place a trusted HTTPS reverse proxy in front of it. Docker bridge networking may hide LAN MACs and neighbor details; host networking is an explicit opt-in. Discovery is limited to explicitly approved private IPv4 ranges, a maximum of 256 addresses, conservative concurrency and timeouts, and configured TCP ports. See [safety](docs/safety.md) and [architecture](docs/architecture.md).

Back up the SQLite database while the service is stopped, or use SQLite's online backup command. Restore into an empty data directory before starting the same app version, then run migrations. Keep backups private: they contain network inventory and account hashes.

On first load, create the single local administrator. Choose a strong password; NetSentinel ships no default credentials. In Settings, enter a canonical RFC 1918 IPv4 CIDR of at most 256 addresses, then explicitly confirm authorization before saving it. Scans cannot run without an enabled approved scope. Session cookies are HttpOnly and SameSite; changes require a CSRF token. For HTTPS reverse proxy deployments, set `NETSENTINEL_SECURE_COOKIES=true`.

Once a scope is approved, its **Run discovery** action shows the maximum probe volume before queueing. The API returns a job ID immediately; the Settings screen polls its status. Discovery uses unprivileged OS neighbor information, optional ICMP ping, and TCP connect attempts on ports 22, 80, and 443 by default. A missing response is unconfirmed, not automatically offline. Only observed hosts enter the inventory; a neighbor hint can create a provisional device with unknown reachability.

The Devices screen lets you search observed names and IPs, filter by familiarity and reachability, inspect address history and probe evidence, and add your own name and notes. A repeated MAC observation can link IP changes, while a different MAC on the same IP remains a separate identity. IP-only devices remain provisional. MACs can be randomized or spoofed, so no inferred identity is presented as certain.

Automatic monitoring is disabled by default. Settings can opt in to a schedule no faster than every 15 minutes and require at least two consecutive missed scans before labeling a device offline. Per-scope policy permits 1–16 explicit TCP ports, at most 32 concurrent hosts, and at most a 1-second connect timeout; changing that policy requires renewed approval. Device detail shows recent latency samples and a text summary. The scheduler is intended for one application process, as supplied by Compose.

Overview metrics show the last evidence update rather than implying continuous live telemetry. The network map groups observed devices under approved subnets. Every dashed line is an inferred IP-to-subnet relationship, not a verified router, Wi-Fi, cable, or switch-port path. A keyboard-operable device list exposes the same device details if graph rendering is unavailable.
