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

## Period P8 — Identity and profiles
Status: complete locally; Phase 2 continues with P9
Human work time: not recorded
Commits and push status: implementation checkpoint `713331e` pushed to `origin/main`; final P8 documentation commit and remote verification are reported in the session handoff.

### Delivered
- Named profiles with per-profile approved scopes and authenticated configuration export. Existing data migrates to Default; overlapping private CIDRs in different profiles keep separate inventories.
- Identity review candidates plus owner-confirmed merge and address split. Conflicting observed MACs and ambiguous historical observations are refused; address provenance is recorded for new scans.
- Settings profile creation/selection/export and device-detail review controls.

### Checks
- Backend Ruff format/lint, mypy, and pytest pass (24 tests at implementation checkpoint). A further existing-database upgrade test passed after the checkpoint.
- Frontend Prettier, ESLint, Vitest (11 tests), and production build pass.
- Controlled browser flow runs in backend pytest; no live LAN scan was run. A manual visual browser check was not completed in this session.

### Decisions and limitations
- Existing observations without a recorded IP remain intact but cannot be assigned to a split address safely.
- Profile exports contain private network details and require explicit approval before use on another installation. Profile import is not part of P8.
- Phase 1's authorized-LAN field validation and Compose runtime smoke check remain outstanding; neither is claimed complete by P8.

### Next
- P9 — optional passive mDNS/SSDP enrichment with strict parsing and source confidence.

## Period P9 — Passive enrichment
Status: complete locally; Phase 2 continues with P10
Human work time: not recorded
Commits and push status: implementation checkpoint `a690a0e` pushed to `origin/main`; final P9 documentation commit and remote verification are reported in the session handoff.

### Delivered
- Opt-in mDNS/SSDP multicast listening during approved scans, with strict bounded parsing and no discovery requests sent by this listener.
- In-scope, unverified hostname and advertised-type hints attached only to already observed devices. Source, timestamp, scan, and confidence are visible in device detail and a paginated API.
- Renewed policy approval to change passive listening; default off. Listener failure does not block normal scans.

### Checks
- Backend Ruff format/lint, mypy, and pytest pass (29 tests). Parser, out-of-scope rejection, opt-in, persistence, CSRF, and policy approval are covered with controlled inputs.
- Frontend Prettier, ESLint, Vitest (11 tests), and production build pass.
- No live LAN scan or multicast capture was run; behavior on the owner's interface and under Compose remains unverified.

### Decisions and limitations
- Only mDNS A names and SSDP alive advertised types are retained. No XML description URL is fetched, and hints cannot create inventory entries or confirmed services.
- A device on another interface using the same private IP could send an ambiguous advertisement; every hint remains explicitly unverified.

### Next
- P10 — per-device checks, thresholds, maintenance windows, and rule editing.

## Period P10 — Check rules
Status: complete locally; Phase 2 continues with P11
Human work time: not recorded
Commits and push status: implementation checkpoint `3b48c24` pushed to `origin/main`; final P10 documentation commit and remote verification are reported in the session handoff.

### Delivered
- Per-device TCP service check rules limited to enabled approved scope ports, with 2–10 consecutive-miss thresholds and one persisted result per rule and scan.
- UTC quiet hours and bounded maintenance windows that suppress new alerts while preserving history; recovery resolves an open check-rule alert.
- Device-detail rule editor, check history, and validated authenticated API.

### Checks
- Backend Ruff format/lint, mypy, and pytest pass (32 tests), including rule validation, thresholds, recovery, suppression, and migrations.
- Frontend Prettier, ESLint, Vitest (11 tests), and production build pass.
- The controlled Chrome flow remains in backend pytest. No real LAN scan or visual manual check was performed for P10.

### Decisions and limitations
- Rules evaluate existing approved scan results. They do not add independent probes or a faster per-device interval.
- A missed TCP check is an observation, not a vulnerability finding; firewalls or sleep may explain it.

### Next
- P11 — optional authenticated outbound host agent and replay protection.

## Period P11 — Host agent
Status: complete locally; Phase 2 continues with P12
Human work time: not recorded
Commits and push status: implementation checkpoint `bc73b83` pushed to `origin/main`; final P11 documentation commit and remote verification are reported in the session handoff.

### Delivered
- Owner-created, one-device agent enrollments with one-time high-entropy tokens, hashed storage, expiration, revocation, and audit events.
- HTTPS-required remote report endpoint with bounded payload, timestamp and nonce replay rejection, and a standalone outbound-only one-shot host script. Optional Docker names/states are off by default.
- Device-detail enrollment, one-time token display, revocation, and recent host/Docker reports.

### Checks
- Backend Ruff format/lint, mypy, and pytest pass (35 tests), including remote HTTP rejection, replay, scope binding, revocation, payload bounds, and migration.
- Frontend Prettier, ESLint, Vitest (11 tests), and production build pass. A mobile-hidden token panel was corrected before the checkpoint.
- No real host-agent deployment or trusted reverse-proxy flow was performed; these remain field checks.

### Decisions and limitations
- The agent sends one report per invocation and can be scheduled by the host owner; the server does not initiate contact or issue commands.
- Reports authenticate the enrollment credential, not the physical host. Remote proxy setup must present a trusted HTTPS scheme to the app.

### Next
- P12 — device comparison, investigation, and saved topology annotations.

## Period P12 — Investigation
Status: complete locally; Phase 2 continues with P13
Human work time: not recorded
Commits and push status: implementation checkpoint `01f79fd` pushed to `origin/main`; final P12 documentation commit and remote verification are reported in the session handoff.

### Delivered
- Same-profile two-device comparison of saved reachability, addresses, and latest per-port service states with timestamps.
- Owner-supplied, unverified topology link labels and notes, visible separately from inferred subnet membership in the graph and keyboard-accessible text list.
- Device ID and event-type Timeline filtering. Identity merge now preserves Phase 2 records and refuses conflicting check-rule ports; split refuses ambiguous device-scoped configuration.

### Checks
- Backend Ruff lint/format, mypy, and pytest pass (36 tests), including migration, comparison, annotation validation, authentication, and CSRF.
- Frontend Prettier, ESLint, Vitest (11 tests), and production build pass.
- No real LAN or physical-link verification was run; owner annotations remain claims.

### Next
- P13 — optional notifications, retention controls, load checks, backup/restore drill, and release review.
