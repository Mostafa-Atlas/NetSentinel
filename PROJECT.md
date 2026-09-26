# NetSentinel — Project and AI Build Brief

**Status:** planned
**Product:** self-hosted LAN inventory, monitoring, topology, and security alerts
**Delivery:** Phase 1 is a complete MVP; Phase 2 adds deeper, optional capabilities
**Working rule:** complete **all of Phase 1 (Periods 1–7) in one AI coding session**, committing and pushing each period plus coherent checkpoints as work progresses; stop after Phase 1
**GitHub repository:** private repository at <https://github.com/Mostafa-Atlas/NetSentinel>; use Git CLI with the owner's configured credentials
**Starting state:** the owner confirms the repository is empty. Build NetSentinel from scratch; Period 1 creates the first project files and Git history.

## 1. Vision

NetSentinel helps the owner of a home network or small lab answer four questions: **What is on my LAN? Is it reachable? What changed? Does anything need my attention?** It should discover devices within an explicitly approved local subnet, keep an understandable history of observations, show a useful network map, and alert when an unfamiliar device or a newly reachable service appears.

The product should feel like a calm operations console, not an alarm factory. Every finding must show the evidence, time, and limits of the observation. An inferred relationship on the map must be labeled as inferred. A device that did not answer one probe is *unconfirmed*, not automatically compromised or permanently offline. NetSentinel is for monitoring networks the user owns or is authorized to administer.

### Primary user journey

1. Install and open the local dashboard; create the first administrator account.
2. Explicitly enter and confirm an authorized private LAN range and scanning limits.
3. Run discovery; review detected devices and label familiar ones.
4. See current reachability, observed services, and a topology view.
5. Investigate a new-device or newly reachable-port alert and acknowledge it.
6. Return later to compare changes and review the event timeline.

### What success looks like

- A new user can reach a populated inventory and understandable map in under 10 minutes on a suitable LAN.
- Normal users can tell **observed**, **inferred**, and **unknown** apart at a glance.
- The app remains useful when ICMP, MAC discovery, or service identification is unavailable.
- Phase 1 can be installed and used without Phase 2 features.
- Data stays local by default; the dashboard never requires a cloud account.

### Scope boundaries

Phase 1 does **not** promise a physical switch-port map, vulnerability verdicts, intrusion detection, or complete discovery of every device. MAC addresses may be visible only on the local broadcast segment; client isolation and host firewalls can limit discovery. Port results indicate reachability at the time of a bounded probe, not proof of a specific application or a security flaw.

## 2. Product phases

| Capability | Phase 1 — MVP | Phase 2 — advanced |
| --- | --- | --- |
| Setup | Local admin, subnet allowlist, safe scan settings | Multiple named network profiles and configuration export |
| Discovery | Manual and scheduled bounded discovery using platform-available ARP/neighbors, ICMP, and TCP connect probes | Optional passive mDNS/SSDP enrichment and better identity reconciliation |
| Inventory | Devices, addresses, labels, first/last seen, confidence, notes | Tags, ownership, search filters, device change comparison |
| Monitoring | Reachability and latency history; small configured port list | Per-device checks, service health rules, richer retention controls |
| Map | Responsive, interactive map of observed devices with clearly inferred grouping | Saved layouts and higher-fidelity topology from optional user-supplied links/agent data |
| Alerts | New device, newly reachable port, offline threshold; acknowledge and resolve | Rule editor, severity tuning, optional outbound notifications |
| Timeline | Timestamped scans, observations, and alerts | Investigation view and historical comparisons |
| Integrations | None required | Optional authenticated host agent for Docker/service and host security status |

**Phase gate:** finish, test, and demonstrate Phase 1 before starting Phase 2. Phase 2 features must remain optional so the MVP works without agents, third-party APIs, or privileged packet capture.

## 3. Architecture

```text
Browser (React dashboard)
        │ same-origin HTTP / WebSocket or short polling
        ▼
FastAPI application ── authentication, validation, REST API, event stream
        │
        ├── discovery coordinator ── bounded probes / OS neighbor table
        ├── monitoring scheduler ── reachability and configured services
        ├── change detector ──────── observation comparison / alert rules
        └── persistence ──────────── SQLite + migrations

Optional Phase 2 host agent ── authenticated, outbound-only reports ──► API
```

Keep scanning and scheduling out of request handlers: API requests create jobs, and a supervised worker executes them with concurrency and timeout limits. Start with a single application instance and one scheduler. Avoid duplicate jobs after restart by persisting job state and defining how interrupted runs become `failed` or `cancelled`. Store timestamps in UTC; render in the browser's local timezone. Treat network observations as immutable evidence and maintain current device state as a derived view or carefully updated record.

**Discovery strategy:** Use ARP/neighbor information when available, then bounded ICMP and TCP connect probes to determine reachability. Do not require raw sockets for the baseline. Treat hostname/vendor/service hints as optional enrichment. Identifying a device by MAC is useful only when the MAC is trustworthy and visible; otherwise retain an IP-based provisional identity and expose uncertainty rather than silently merging unrelated devices. Never turn a port number into an asserted product name without evidence.

**Deployment:** Support local development on Windows and Linux. Target a documented Linux host or small server for production deployment. Provide native development commands and a Compose deployment. Explain that Docker networking, OS permissions, VLANs, VPNs, and Wi-Fi client isolation can limit discovery. Any host-network or elevated capability must be an explicit, documented opt-in; the standard web app should start without it.

## 4. Recommended stack

| Layer | Choice | Reason |
| --- | --- | --- |
| Backend | Python 3.12+, FastAPI, Pydantic v2 | Clear API contracts and strong validation |
| Database | SQLite, SQLAlchemy 2, Alembic | Simple self-hosting with explicit migrations |
| Worker | Python `asyncio` with bounded queues; one scheduler process | Enough for a single-site MVP without adding a broker |
| Frontend | React, TypeScript, Vite | Fast iteration and typed UI |
| Data/UI | TanStack Query, Cytoscape.js, Recharts | Server state, interactive map, readable history charts |
| Styling | Tailwind CSS with a small token system and accessible components | Consistent responsive interface |
| Tests | pytest, Vitest/Testing Library, Playwright for critical flows | Meaningful backend, UI, and end-to-end checks |
| Packaging | Docker Compose plus documented native setup | Practical home-server installation |

Pin dependencies and commit lockfiles. Select exact package versions during bootstrap using current compatible releases; record material choices in `docs/decisions/`. Keep the backend modular and the frontend component-based. Do not add a broker, microservices, or cloud database unless measured need justifies them.

## 5. UI and UX direction

Use a restrained dark interface: near-black/navy surfaces, clear typography, cool blue/cyan for healthy states, amber for attention, and red only for urgent failures. Avoid decorative “hacker” noise. Build a responsive layout with a left navigation on desktop and a compact navigation pattern on mobile.

### Main screens

- **Overview:** devices online, devices needing review, active alerts, latest scan, and a short change timeline. Show the last update time on every live-looking metric.
- **Network map:** pan/zoom, keyboard-reachable device list alternative, status and identity badges, detail drawer. Group by network/subnet and display inferred links with a distinct style and legend. Do not draw a router-to-device line as a verified physical connection.
- **Devices:** searchable inventory with filters for status, known/unknown, and alerts. Device detail shows addresses, evidence, reachability chart, service observations, notes, and event history.
- **Alerts:** severity, trigger, evidence, first/last seen, acknowledgment, resolution, and a link to the device. Empty states should explain what is being monitored.
- **Settings:** authorized ranges, probe limits, schedules, retention, account security, and a clear “run discovery” action.

Use progressive disclosure: dashboard first, evidence one click away. Include loading, empty, partial-data, and error states. Support keyboard navigation, visible focus, sufficient contrast, reduced motion, and chart summaries in text. Never fabricate sample “live” devices after setup; any demo mode must be plainly labeled and isolated from real data.

## 6. Data model

Use migrations and foreign keys. The following is the conceptual schema; names can change when implementation warrants it, with the change recorded.

| Entity | Core fields | Notes |
| --- | --- | --- |
| `users` | id, username, password_hash, created_at, last_login_at | One local administrator in Phase 1; no default password |
| `network_scopes` | id, name, CIDR, enabled, approved_at, probe_policy | Explicit allowlist; private ranges only by default |
| `scan_runs` | id, scope_id, type, status, started_at, finished_at, host_count, error_summary | Auditable job history |
| `devices` | id, display_name, identity_confidence, known_state, notes, first_seen_at, last_seen_at | Stable internal ID; do not use IP as sole permanent identity |
| `device_addresses` | id, device_id, IP, MAC nullable, hostname nullable, first_seen_at, last_seen_at | Addresses change; retain history |
| `observations` | id, device_id, scan_run_id, observed_at, source, reachable, latency_ms nullable, raw_summary | Immutable, bounded evidence; avoid storing unnecessary packet data |
| `service_observations` | id, device_id, IP, port, protocol, state, observed_at, scan_run_id | State is `reachable`, `unreachable`, or `unknown`; product hint optional |
| `alerts` | id, device_id nullable, rule_key, severity, status, evidence_ref, created_at, last_seen_at, acknowledged_at, resolved_at | Deduplicate repeated findings; preserve audit trail |
| `events` | id, device_id nullable, event_type, occurred_at, actor, summary, evidence_ref | Timeline of scans, settings changes, and user actions |
| `settings` | key, value, updated_at | Typed validation at API boundary; never store plaintext secrets |

Phase 2 may add `monitor_checks`, `topology_links`, `notification_destinations`, and `agent_enrollments`. Define retention and indexes as data grows. Favor explicit schema evolution over a JSON-only database.

## 7. API outline

Version API paths under `/api/v1`. Return typed JSON and consistent errors (`code`, `message`, optional `details`, `request_id`). Document them with OpenAPI. Require authentication for every operational endpoint. Use pagination for history lists.

| Endpoint | Purpose |
| --- | --- |
| `POST /auth/bootstrap`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` | First-user setup and local session management |
| `GET/POST /scopes`, `PATCH /scopes/{id}` | View and manage approved network ranges |
| `POST /scans`, `GET /scans`, `GET /scans/{id}` | Queue and inspect a bounded discovery run |
| `GET /devices`, `GET /devices/{id}`, `PATCH /devices/{id}` | Inventory and owner labels/notes |
| `GET /devices/{id}/observations`, `GET /devices/{id}/services` | Evidence and history |
| `GET /topology` | Nodes, optional inferred links, and link provenance |
| `GET /alerts`, `GET /alerts/{id}`, `POST /alerts/{id}/acknowledge`, `POST /alerts/{id}/resolve` | Alert workflow |
| `GET /events`, `GET /overview` | Timeline and dashboard summaries |
| `GET/PATCH /settings` | Validated schedule and retention settings |

Use `POST /scans` for manual runs and return a job ID promptly; never hold an HTTP request open for a full sweep. Provide a polling status contract in Phase 1. Phase 2 may add a server event stream if it improves the UI. API tests should cover invalid CIDRs, unauthorized requests, job limits, duplicate alerts, and state transitions.

## 8. Security, privacy, and scanning safety

1. **Authorization and scope:** Scan only ranges the owner explicitly entered and approved. Default to RFC 1918 private IPv4 ranges. Reject public, multicast, loopback, and oversized ranges by default. Do not accept arbitrary per-request targets that bypass the allowlist. Warn before enabling scanning of a new range.
2. **Bounded probes:** Set conservative defaults: maximum 256 addresses per scope, 32 concurrent probes, 1-second connect timeout, a small explicit TCP port set, and a minimum schedule interval of 15 minutes. Make limits configurable only within documented safe caps. No stealth, evasion, brute force, exploit checks, or credential guessing.
3. **Secure app:** Hash passwords with a current password hashing scheme (for example Argon2id). Use HttpOnly, SameSite cookies, CSRF protection for cookie-authenticated mutations, login rate limiting, and secure cookies under HTTPS. Bind to localhost by default; document TLS through a trusted reverse proxy for remote access. Never ship a default admin credential.
4. **Local data:** Keep observations local, collect only what the feature needs, and provide configurable retention. Protect secrets in environment variables or a protected local config, redact them from logs, and never commit them. Backups must be documented and restorable.
5. **Trust boundaries:** Validate every API input. Treat hostnames, mDNS names, banners, and agent reports as untrusted text; escape them in the UI. Agent enrollment in Phase 2 must use scoped credentials, replay protection, and transport security. Do not run remote shell commands from the dashboard.
6. **Honest interpretation:** An open port, missing response, or vendor guess is an observation, not a vulnerability finding. Each alert needs evidence and a clear explanation. No automatic firewall changes, isolation, or destructive remediation.

Before using this toward a hackathon or hours program, check that program's current rules on eligibility, AI assistance, and time logging. Record **actual hands-on work** and clearly disclose AI help where required; estimates in this document are planning aids, not earned hours.

## 9. Recommended repository structure

```text
netsentinel/
├── PROJECT.md                 # this brief, copied to repo root
├── README.md                  # setup, supported environments, limitations
├── CHANGELOG.md               # user-visible changes by period
├── PROGRESS.md                # period handoffs and actual time log
├── .env.example               # placeholders only
├── compose.yaml
├── docs/
│   ├── architecture.md
│   ├── safety.md
│   ├── api.md
│   └── decisions/             # short architecture decision records
├── backend/
│   ├── pyproject.toml
│   ├── alembic/
│   ├── src/netsentinel/
│   │   ├── api/
│   │   ├── auth/
│   │   ├── db/
│   │   ├── discovery/
│   │   ├── monitoring/
│   │   ├── alerts/
│   │   └── core/
│   └── tests/
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── features/
│   │   ├── lib/
│   │   └── styles/
│   └── tests/
└── scripts/                   # small reproducible setup/check helpers
```

Avoid empty scaffolding for distant features. Add directories when their first real implementation is ready.

## 10. Milestone plan and estimated effort

These are **planning estimates**, not a target to fill artificially. A period should contain a coherent, testable slice, usually about 3–6 hours of real development. If the work takes less or more time, record the actual time. In the initial coding session, complete P1 through P7 in order without stopping between them. Commit and push coherent checkpoints after every few related changes, then make a final commit and push for each completed period after its checks and logs are complete. The full roadmap has ample legitimate work beyond 40 hours; the feature and quality gates determine completion.

### Phase 1 — useful MVP (Periods 1–7; roughly 28–42 hours)

| Period | Deliverable and acceptance checkpoint | Estimate | Example commit |
| --- | --- | ---: | --- |
| **P1 — Bootstrap** | Repo, stack, lint/test commands, migration skeleton, basic app shells, Compose/native instructions; local smoke checks pass | 3–5 h | `chore: bootstrap NetSentinel workspace` |
| **P2 — Secure setup** | First-admin flow, login/logout/session protection, scope validation and approval; invalid/public CIDRs rejected | 4–6 h | `feat: add admin setup and approved network scopes` |
| **P3 — Discovery** | Bounded scan job, safe probes, neighbor enrichment, persisted runs and observations; mocked-network tests | 5–7 h | `feat: discover approved LAN devices` |
| **P4 — Inventory** | Device reconciliation with uncertainty, editable names/notes/known state, list/detail API and UI; address history | 4–6 h | `feat: build device inventory and history` |
| **P5 — Monitoring** | Scheduler, reachability/latency history, small port policy, baseline change detection; no duplicate job on restart | 5–7 h | `feat: monitor reachability and service changes` |
| **P6 — Map and overview** | Responsive map with inferred-link legend, dashboard counts, loading/empty/partial states, keyboard alternative | 4–6 h | `feat: add network map and overview dashboard` |
| **P7 — Alerts and release** | New-device/new-port/offline alerts, acknowledge/resolve, event timeline, end-to-end flow, install and restore docs | 5–7 h | `feat: ship Phase 1 alerts and release flow` |

**Phase 1 exit gate:** A clean install allows an owner to create an account, approve a private subnet, run discovery, inspect devices and the map, observe monitoring history, and acknowledge a real change alert. Automated checks pass and the README describes limitations. A short manual demonstration uses the owner's authorized LAN or a controlled test network.

### Phase 2 — advanced, optional features (Periods 8–13; roughly 24–36 hours)

| Period | Deliverable and acceptance checkpoint | Estimate | Example commit |
| --- | --- | ---: | --- |
| **P8 — Identity and profiles** | Multiple network profiles, improved address/device reconciliation, explicit merge/split review; regression tests | 4–6 h | `feat: add network profiles and identity review` |
| **P9 — Passive enrichment** | Optional mDNS/SSDP metadata with strict parsing and off switch; confidence and source shown in UI | 4–6 h | `feat: enrich devices with passive metadata` |
| **P10 — Check rules** | Per-device service checks and thresholds, maintenance/quiet periods, rule editor with validation | 4–6 h | `feat: configure service monitoring rules` |
| **P11 — Host agent** | Optional outbound authenticated agent reports for host/Docker status; scoped enrollment and replay tests | 5–7 h | `feat: add optional host status agent` |
| **P12 — Investigation** | Device comparison, richer timeline and saved topology annotations with provenance; accessible interaction | 4–6 h | `feat: add investigation and topology annotations` |
| **P13 — Notifications and hardening** | Optional notification destination, retention controls, load checks, backup/restore drill, final docs and release checks | 4–6 h | `feat: add notifications and retention controls` |

**Phase 2 exit gate:** Every optional feature can be disabled; Phase 1 flows still work. Sensitive integrations have tests, documentation, and an explicit opt-in. The app performs acceptably on a representative small LAN and a populated test database.

## 11. Acceptance criteria and verification

### Functional

- A scan cannot start without an approved scope and cannot reach outside it.
- Scan jobs expose queued/running/completed/failed states and bounded errors.
- Repeated scans update history without creating duplicate devices or repeated identical active alerts.
- Devices and alerts survive restart; migrations preserve data.
- A new or changed observation appears in the overview and timeline with its source and timestamp.
- The map clearly identifies inferred links; the UI still works without a graph-capable browser or pointer device.
- An offline alert requires a configurable consecutive-failure threshold; one missed probe is insufficient by default.

### Quality

- Backend unit/integration tests cover scope validation, job limits, identity rules, alert deduplication, and authentication.
- Frontend tests cover setup, empty/loading/error states, device detail, and alert actions.
- At least one browser end-to-end test covers setup → approve scope → run a controlled/mock scan → inspect device → acknowledge alert.
- Formatting, linting, type checks, tests, and build pass before every completed-period commit.
- README gives reproducible native and Compose setup, safe scan defaults, known limitations, and backup/restore steps.

### Manual checks

Use a controlled test subnet or the owner's authorized LAN. Confirm the approved range, expected probe volume, and network impact before a live scan. Verify an offline/unresponsive device is represented honestly. Test at desktop and mobile widths; check keyboard operation and reduced motion. Capture evidence in `PROGRESS.md` without publishing sensitive IPs or MACs.

## 12. Coding standards

- Prefer small, single-purpose modules and explicit interfaces between API, worker, database, and UI.
- Use strict TypeScript; use Python type hints and validation at boundaries. Keep domain logic independently testable from the network and database.
- Make network operations injectable/fakeable for deterministic tests. Never depend on a live LAN in routine CI.
- Use migrations for schema changes, and document non-obvious tradeoffs in `docs/decisions/`.
- Do not swallow errors or show a success state for partial failure. Log structured, redacted diagnostics with a request or job ID.
- Keep dependencies minimal, pinned, and reviewed. No committed secrets, real device inventories, or personal network details.
- Add tests for behavior that could regress; avoid tests that only mirror the implementation.
- Maintain clear user-facing copy and accessible interaction as part of feature completion.

## 13. AI coding-agent execution protocol

The following instructions are meant to be pasted with this document into a coding agent. **The owner authorizes normal commits and pushes to the NetSentinel GitHub repository above as part of this build.** The owner still controls approved scan ranges and any deployment or publication outside that repository.

### Standing instructions for a phase build

1. Use **Git CLI**, not a public webpage check, for this private repository. The initial Phase 1 session starts from an empty repo, so create `README.md`, `PROGRESS.md`, and `CHANGELOG.md` during P1; later sessions read them, `PROJECT.md`, the latest commits, and the current code before editing. Verify that `origin` points to `https://github.com/Mostafa-Atlas/NetSentinel.git` (or its equivalent SSH URL), identify the current branch and remote default branch, and fetch before publishing. A private repository can return 404 to an unauthenticated browser. If Git access is denied, report that accurately; never replace a different remote or overwrite remote history.
2. For the initial build, complete **all of Phase 1: P1, P2, P3, P4, P5, P6, and P7 in order in the same session**. Each period remains a separate tested, logged, committed, and pushed checkpoint. After finishing one period, continue directly to the next without waiting for a fresh prompt. If a period is incomplete or tests fail, finish/fix it before proceeding. **Do not start Phase 2** in the Phase 1 session.
3. State a short implementation plan and the period's acceptance checkpoint. Preserve working behavior. Refactor only where necessary for the period and verify affected flows; do not rewrite working features for style or novelty.
4. Make small, reviewable changes. Add migrations and focused tests for new behavior. Keep scanning disabled or mocked in tests; require explicit owner approval of a scope before any live probe.
5. After roughly **2–4 related changes**, or when a coherent working slice is complete, run focused checks for that slice, review the diff for secrets, private LAN identifiers, generated artifacts, unrelated edits, and unsafe scan defaults, then stage only relevant files. Make a descriptive checkpoint commit and **push it to the same branch on `origin`** with a normal, non-force push. Do this throughout the period; never create empty or meaningless commits just to meet a count. If the branch has diverged, fetch and reconcile safely before pushing; never force-push or overwrite someone else's work.
6. Before the final period commit, run the repository's formatting, lint, type-check, test, and build commands that apply to changed code. Fix failures. Do a short manual check when the period changes visible UI or deployment. Never claim a check passed if it was not run. Intermediate commits require passing relevant focused checks; the final commit requires the full applicable gate.
7. Update `CHANGELOG.md` with user-visible changes and `PROGRESS.md` with period status, decisions, checks with results, limitations, next period, and **actual human work time if supplied by the owner**. Do not invent hours or imply AI runtime is the owner's work. Create a clear final period commit using the example style in Section 10, adjusted to the actual work, and push it. Verify that the remote branch points to the final local commit. If pushing fails, preserve local commits and report the exact blocker and unpushed hashes.
8. After P7, run the Phase 1 exit gate in Section 10 and a final end-to-end review, then **stop after the Phase 1 final push and remote verification**. In the handoff, report the period commits, remote branch and verified final hash, completed scope, checks and results, and any limitations. Tell the owner that Phase 2 is next and wait for a fresh prompt before starting it.

If blocked before a period's acceptance checkpoint, work on safe, independent tasks within Phase 1 while seeking only the input truly needed to continue. If Phase 1 cannot be completed, document the blocker and current state in the handoff; do not mark unfinished periods complete or fabricate final period commits. Accurately report completed checkpoint commits and pushes. If pre-existing uncommitted user changes exist, preserve them and coordinate before staging overlapping files.

### Suggested initial-session prompt

> Build NetSentinel Phase 1 from scratch using `PROJECT.md` in my empty private repository, `https://github.com/Mostafa-Atlas/NetSentinel`. Complete P1 through P7 in order in this session. After every few related changes, run relevant checks, commit, and push; at the end of each period, run all applicable checks, update the logs, commit and push that period, and continue to the next. After P7, verify the complete Phase 1 flow and the final remote hash, then stop and give me a full handoff. Do not start Phase 2.

### `PROGRESS.md` entry template

```md
## Period Pn — Title
Status: planned | in progress | complete | blocked
Human work time: [owner-provided actual time, or "not recorded"]
Commits and push status: [checkpoint hashes, final hash, remote branch; or blocker]

### Delivered
- ...

### Checks
- `command` — pass/fail/not run; reason if not run

### Decisions and limitations
- ...

### Next
- Pn+1 — ...
```

## 14. Phase 1 session bootstrap — start with P1, then continue through P7

1. Use Git CLI to clone the empty `https://github.com/Mostafa-Atlas/NetSentinel.git` repository with the owner's configured credentials. Copy this file to the clone's root as `PROJECT.md`, create or switch to `main`, and build the first project files from scratch. Confirm repository-local Git identity and an appropriate `.gitignore` before the first commit. Push the first checked commit to `origin/main` without forcing; do not assume a browser 404 means the private repository is missing. If Git access is denied, continue safely locally and report the push blocker.
2. Record the chosen Python/Node/package versions and platform assumptions. Create backend and frontend app shells, lockfiles, and a first Alembic migration. Use a simple `/health` backend endpoint and a frontend page that loads it. No live network probing in P1.
3. Add `README.md` with native Windows/Linux startup commands and a Compose path. Add `.env.example` with placeholders and safe defaults. Add `CHANGELOG.md`, `PROGRESS.md`, and a brief architecture decision for the single-instance scheduler.
4. Add minimal meaningful smoke tests: backend health endpoint and frontend API health rendering. Configure format, lint, type, test, and build commands. Check they all run on a clean local setup.
5. Commit and push a checked checkpoint after the initial runnable shells and another after the tooling/docs are ready, when those slices are genuinely complete. Review the final diff, update P1's progress entry, run all P1 checks, and make the final P1 commit as `chore: bootstrap NetSentinel workspace` (or an equally clear message). Push and verify the remote branch, then **continue directly to P2**. Repeat the checked period-commit-and-push cycle through P7. Stop only after the full Phase 1 exit gate and final remote verification.

**Owner reminder:** Use Git commits to make the build reviewable, not to manufacture hours. Keep a truthful personal time log and check the specific event's current AI-assistance and eligibility rules before submitting any work.
