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
