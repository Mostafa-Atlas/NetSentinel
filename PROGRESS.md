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
Commits and push status: checkpoint `774e19d` and final `c9a35e6` pushed to `origin/main`.

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
Commits and push status: checkpoint `eb84e76` and final `6b3ba1e` pushed to `origin/main`.

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

## Period P4 — Inventory
Status: complete
Human work time: not recorded
Commits and push status: checkpoint `268beb5` and final `e34957b` pushed to `origin/main`.

### Delivered
- Conservative identity reconciliation that preserves separate devices when a reused IP has a different observed MAC.
- Stable device IDs, address history, editable display names, familiarity, and notes.
- Searchable/filterable inventory, device detail, reachability and TCP service evidence.

### Checks
- Backend format, lint, mypy, pytest — pass (12 tests).
- Frontend format, lint, tests, typechecked build — pass (4 tests).
- UI browser inspection unavailable because the in-app browser helper exited during sandbox setup; UI behavior tested in jsdom.

### Decisions and limitations
- MAC associations are labeled observed, not verified. IP-only devices remain provisional and may require manual review when a MAC later appears.
- List queries are optimized for a small LAN and paginate responses; larger deployments would need query-level filtering.

### Next
- P5 — scheduled monitoring, reachability history, and service change detection.

## Period P5 — Monitoring
Status: complete
Human work time: not recorded
Commits and push status: checkpoint `e7102a6` and final `2822ad4` pushed to `origin/main`.

### Delivered
- Opt-in single-instance scheduler with a 15-minute minimum interval and no duplicate queued job after restart.
- Safe per-scope TCP port/concurrency/timeout policy requiring explicit approval on changes.
- No-response observations, configurable consecutive-failure offline status, latency history chart with text summary, and service-change baseline comparison.

### Checks
- Backend format, lint, mypy, pytest — pass (15 tests).
- Frontend format, lint, tests, typechecked build — pass (5 tests).
- No live LAN scan was performed. The in-app browser helper still cannot start in this sandbox; browser visual verification remains unavailable.

### Decisions and limitations
- Scheduling is disabled by default. The owner enables it only after approving a scope.
- `retention_days` is stored but enforcement is scheduled for P7; the UI does not present it yet.
- The first observed service state is a baseline and does not by itself imply a newly opened service.

### Next
- P6 — inferred network map and overview dashboard.

## Period P6 — Map and overview
Status: complete
Human work time: not recorded
Commits and push status: checkpoint `49ca92a` and final `44a7ef6` pushed to `origin/main`.

### Delivered
- Timestamped overview metrics, latest scan, recent scan history, and honest empty state.
- Interactive subnet/device map with dashed inferred links and provenance; keyboard-reachable device list and graph-unavailable fallback.
- Responsive layouts and separately loaded map/inventory bundles.

### Checks
- Backend format, lint, mypy, pytest — pass (16 tests).
- Frontend format, lint, tests, typechecked build — pass (8 tests).
- Browser visual check remains unverified because the in-app browser helper cannot start in this sandbox.

### Decisions and limitations
- Subnet grouping is an inference from observed IPs. No physical router or switch connection is asserted.
- The overview's active-alert count is prepared for P7 and is zero until alert persistence is added.

### Next
- P7 — alert workflow, event timeline, retention, release checks, and end-to-end flow.

## Period P7 — Alerts and release
Status: implementation complete; authorized field validation pending
Human work time: not recorded
Commit and push status: checkpoint `7ed84cd` pushed and verified on `origin/main`. The final release commit and remote verification are reported in the session handoff.

### Delivered locally
- Evidence-backed new-device, newly reachable TCP port, and consecutive-miss offline alerts; deduplicated active findings, owner acknowledgment and resolution, and an event timeline.
- Daily probe-evidence retention with open-alert references preserved; configurable 7–365 day setting.
- Alerts and Timeline screens, overview recent changes, device inspection links, an inventory alert filter, per-device event history, and accessible empty/loading/error states.
- Controlled Chrome browser flow from first setup through scope approval, mocked queued scan, inventory/map/history, alert acknowledgment, and timeline. No LAN traffic is generated by this test.
- Reproducible backend/frontend install inputs and documented native/Compose backup and restoration with a verified SQLite copy helper.

### Checks
- Backend Ruff format/lint, mypy, and pytest pass (20 tests), including fresh Alembic migrations, a backup/restore drill, alert transitions, retention, and the Chrome flow. The browser test runs after the frontend build so its static files are stable.
- Frontend Prettier, ESLint, Vitest (11 tests), and production build pass.
- Docker CLI is installed, but the Docker Desktop Linux daemon is unavailable, so a Compose runtime smoke test remains unverified.

### Release limits
- No real LAN scan was run because no owner-approved range was configured in this session. The field portion of the Phase 1 exit gate remains for an authorized network.
- The owner explicitly approved the P7 commits and normal push after automatic approval review initially rejected publication. Phase 2 has not started.
