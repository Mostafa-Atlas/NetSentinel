# API

The versioned operational API lives under `/api/v1`; FastAPI serves OpenAPI at `/docs`. Authentication uses a local session cookie and a CSRF token for mutations. List responses use `items` and pagination metadata. All errors carry a machine-readable `code` and human-readable `message`.

P2 provides `GET /auth/bootstrap-status`, `POST /auth/bootstrap`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `GET/POST /scopes`, and `PATCH /scopes/{id}`. The CSRF token is supplied by the `netsentinel_csrf` cookie and echoed in the `X-CSRF-Token` header for authenticated mutations. The session token stays in an HttpOnly cookie. All scope writes require an authenticated session and explicit approval of newly enabled ranges.

P3 adds `POST /scans` with `{ "scope_id": 1 }`, returning `202` with a job ID and `queued` status. `GET /scans/{id}` polls `queued`, `running`, `completed`, or `failed`; `GET /scans?limit=50&offset=0` lists history. A run's `host_count` is the number of addresses probed. Jobs are limited to four queued/running runs and one worker. A restart marks interrupted jobs failed with a reason.
