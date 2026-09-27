# Install, backup, and restore

## Install

For a native install, use Python 3.12+, Node 24+, and pnpm 11. From `backend`, create a virtual environment, install `requirements.lock`, then install the package with `pip install -e . --no-deps`. Run `alembic upgrade head`, then `uvicorn netsentinel.main:app --host 127.0.0.1`. From `frontend`, run `pnpm install --frozen-lockfile` and `pnpm dev`; open <http://127.0.0.1:5173>. The default SQLite file is `backend/netsentinel.db` when the API starts from `backend`.

For a single-container installation, run `docker compose up -d --build` from the repository root and open <http://127.0.0.1:8000>. Compose binds only to localhost, persists `/data/netsentinel.db` in the `netsentinel-data` volume, applies migrations on start, and runs one API worker. Docker bridge networking can limit neighbor and MAC visibility. Do not expose port 8000 directly to an untrusted network.

Create the only administrator on first load. In Settings, approve a private IPv4 range you administer. Discovery and automatic monitoring stay off until those actions. If using a trusted HTTPS reverse proxy, set `NETSENTINEL_SECURE_COOKIES=true` and configure the proxy to preserve secure cookie handling.

For the optional host agent, enroll a specific device in its detail screen and copy the one-time token. Store it in `NETSENTINEL_AGENT_TOKEN` on that host; do not put it in a command-line argument or commit it. Run `python backend/scripts/host_agent.py --server https://your-trusted-origin` for one outbound report, then schedule that command with the host's scheduler if desired. Use `--include-docker` only after deciding to report container names and states. A local same-host installation may use `--server http://127.0.0.1:8000`. Remote reporting requires a trusted HTTPS endpoint and an application server configured to recognize the trusted proxy's HTTPS scheme; the API deliberately ignores a client-supplied `X-Forwarded-Proto` header. The host clock must be within five minutes of the server. Revoke a credential in device detail if it is no longer needed.

## Back up

The helper uses SQLite's online backup API, so a backup can be taken while the app runs. It verifies the resulting file with `PRAGMA integrity_check` and refuses to overwrite an existing backup unless explicitly instructed. Keep backup files private; they contain account hashes, network addresses, notes, and history.

Native example from the repository root:

```powershell
& .\.venv\Scripts\python.exe backend\scripts\sqlite_backup.py backend\netsentinel.db backups\netsentinel-2026-09-27.db
```

On Linux, use `.venv/bin/python` and `/` separators. For Compose, write a consistent backup inside the volume and copy it to the host:

```sh
docker compose exec netsentinel python /app/backend/scripts/sqlite_backup.py /data/netsentinel.db /data/netsentinel-backup.db
docker compose cp netsentinel:/data/netsentinel-backup.db ./netsentinel-backup.db
```

The Compose backup command needs the helper in the image; `Dockerfile` copies the backend directory. Remove temporary copies from `/data` when they are no longer needed, using a known exact filename.

## Restore

Stop the application before replacing its database. Keep the original database as a separate fallback. Restore a backup made by the same version, then run `alembic upgrade head` before starting the API. The helper's `--replace` flag is for this stopped-service step only.

Native example from the repository root:

```powershell
& .\.venv\Scripts\python.exe backend\scripts\sqlite_backup.py backups\netsentinel-2026-09-27.db backend\netsentinel.db --replace
Push-Location backend
& ..\.venv\Scripts\alembic.exe upgrade head
Pop-Location
```

Compose example, after saving `netsentinel-backup.db` in the repository root:

```sh
docker compose stop netsentinel
docker compose run --rm --no-deps -v "$(pwd)/netsentinel-backup.db:/backup/netsentinel.db:ro" --entrypoint python netsentinel /app/backend/scripts/sqlite_backup.py /backup/netsentinel.db /data/netsentinel.db --replace
docker compose up -d netsentinel
```

The startup command applies migrations. Sign in and check inventory, alerts, and timeline after restoration. Use a new filename for each backup to avoid accidental replacement.

## Release verification

Run backend format, lint, mypy, and pytest checks; build and test the frontend before running the Chrome browser test. The browser test serves the built UI against an ephemeral migrated database and a controlled fake probe. It does not contact a LAN. A final field demonstration on an authorized LAN remains necessary to assess real neighbor, ICMP, and TCP probe behavior on the owner's environment.
