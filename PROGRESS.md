# Phase 1 progress

Human work time is recorded only when provided by the owner. Automated build duration is not a substitute.

## Period P1 — Bootstrap
Status: complete
Human work time: not recorded
Commits and push status: checkpoint `368cf6a` and final `46cb6ac` pushed to `origin/main`.

### Delivered
- Local Python 3.12/FastAPI and Node 24/React/Vite shells, health endpoint, Alembic migration scaffold, pinned dependencies and lockfiles, Compose/native instructions, and safe defaults.

### Checks
- Backend `ruff format --check`, `ruff check`, `mypy`, `pytest` — pass (1 test).
- Frontend `pnpm test`, `pnpm build`, `pnpm lint` — pass (1 test).
- Frontend `prettier --write` — applied; final format check after generated-output ignore pending.
- `alembic upgrade head` and `alembic current` — pass at revision `0001`.
- Docker CLI is installed, but the Docker Desktop Linux daemon is unavailable; Compose runtime not verified.

### Decisions and limitations
- Single application instance and one scheduler are the MVP deployment target.
- No network probing in P1.

### Next
- P2 — secure setup and approved scopes.

## Period P2 — Secure setup
Status: complete
Human work time: not recorded
Commits and push status: backend checkpoint `774e19d` pushed to `origin/main`; final P2 commit pending.

### Delivered
- First administrator setup, Argon2 password hashing, local sessions and CSRF protection, login rate limiting, and private scope approval.
- Setup, sign-in, and network-scope UI with an explicit authorization checkbox.

### Checks
- Backend format, lint, mypy, pytest — pass (5 tests).
- Fresh Alembic migration test — pass.
- Frontend format, lint, tests, and production build — pass (2 tests).
- Local API and Vite dev servers started. In-app browser inspection unavailable because its helper exited during sandbox setup; visual check unverified.

### Decisions and limitations
- The standard app binds to localhost; remote access needs a trusted HTTPS reverse proxy and secure-cookie setting.
- No network probe has been run. The owner must approve a scope before discovery is possible.

### Next
- P3 — bounded discovery jobs and observations.

## Period P3 — Discovery
Status: complete
Human work time: not recorded
Commits and push status: working checkpoint `eb84e76` pushed to `origin/main`; final P3 commit pending.

### Delivered
- Bounded asynchronous probe runner using OS neighbor hints, ICMP where available, and TCP connect checks with no raw-socket requirement.
- Persisted scan jobs and evidence; queued scans return promptly and interrupted jobs fail on restart.
- Settings action confirms the probe volume and polls job status.

### Checks
- Backend format, lint, mypy, pytest — pass (10 tests, including direct mocked probe runner).
- Frontend format, lint, tests, build — pass (3 tests).
- Live scan — intentionally not run; no owner-approved range was configured for this session.

### Decisions and limitations
- Neighbor entries are hints with unknown reachability unless a probe responds.
- Identity matching is provisional in P3; P4 adds reconciliation and inventory presentation.

### Next
- P4 — inventory, address history, and editable labels.
