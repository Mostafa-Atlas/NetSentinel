# API

The versioned operational API lives under `/api/v1`; FastAPI serves OpenAPI at `/docs`. Authentication uses a local session cookie and a CSRF token for mutations. List responses use `items` and pagination metadata. All errors carry a machine-readable `code` and human-readable `message`.

P2 provides `GET /auth/bootstrap-status`, `POST /auth/bootstrap`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `GET/POST /scopes`, and `PATCH /scopes/{id}`. The CSRF token is supplied by the `netsentinel_csrf` cookie and echoed in the `X-CSRF-Token` header for authenticated mutations. The session token stays in an HttpOnly cookie. All scope writes require an authenticated session and explicit approval of newly enabled ranges.

P3 adds `POST /scans` with `{ "scope_id": 1 }`, returning `202` with a job ID and `queued` status. `GET /scans/{id}` polls `queued`, `running`, `completed`, or `failed`; `GET /scans?limit=50&offset=0` lists history. A run's `host_count` is the number of addresses probed. Jobs are limited to four queued/running runs and one worker. A restart marks interrupted jobs failed with a reason.

P4 adds `GET /devices` with `search`, `known_state`, `status`, `limit`, and `offset`; `GET/PATCH /devices/{id}`; and paginated `GET /devices/{id}/observations` and `/services`. `PATCH` accepts `display_name`, `notes`, and `known_state` (`known` or `unknown`) and requires a CSRF token. The detail response includes address history and an identity-confidence label.

P5 adds `GET/PATCH /settings` for opt-in scheduling (`schedule_enabled`, `interval_minutes` at least 15) and `offline_threshold` (2–10). `PATCH /scopes/{id}` can update `ports` (1–16 unique TCP ports), `max_concurrency` (1–32), and `connect_timeout_ms` (100–1000); policy changes require `approved: true`. `retention_days` is validated and stored for the P7 retention implementation.

P6 adds `GET /overview` with device/review/status counts, latest scan, recent runs, and a last-evidence timestamp. `GET /topology` returns subnet and device nodes plus `kind: "inferred"` links with provenance. The link means subnet membership from an observed IP only.
