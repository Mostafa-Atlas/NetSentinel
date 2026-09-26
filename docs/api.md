# API

The versioned operational API lives under `/api/v1`; FastAPI serves OpenAPI at `/docs`. Authentication uses a local session cookie and a CSRF token for mutations. List responses use `items` and pagination metadata. All errors carry a machine-readable `code` and human-readable `message`.

P2 provides `GET /auth/bootstrap-status`, `POST /auth/bootstrap`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `GET/POST /scopes`, and `PATCH /scopes/{id}`. The CSRF token is supplied by the `netsentinel_csrf` cookie and echoed in the `X-CSRF-Token` header for authenticated mutations. The session token stays in an HttpOnly cookie. All scope writes require an authenticated session and explicit approval of newly enabled ranges.
