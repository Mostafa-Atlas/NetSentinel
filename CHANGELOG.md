# Changelog

## Unreleased

- P8: Added named network profiles, per-profile scope grouping and private configuration export. Device identities now remain separate across overlapping profiles. Added explicit owner-confirmed identity merge and address split review with provenance checks.
- P9: Added optional passive mDNS and SSDP listening during approved scans. Bounded, in-scope advertisements are stored as unverified hints with source and time, and shown in device detail. The feature is off by default and needs renewed policy approval to enable.
- P1: Created the backend and frontend application shells, health checks, migration scaffold, and local setup instructions.
- P2: Added first-admin setup, local sessions, CSRF-protected changes, approved private network scopes, and setup/settings screens.
- P3: Added queued bounded discovery, optional OS neighbor and ICMP hints, TCP connect observations, scan status polling, and persisted evidence.
- P4: Added conservative device identity reconciliation, address history, inventory search and filters, evidence detail, and editable owner labels and notes.
- P5: Added opt-in scheduled scans, safe per-scope TCP probe policy, consecutive missed-scan status, latency history, and service-change baseline logic.
- P6: Added an evidence-timestamped overview, interactive subnet map, clearly inferred links, and a keyboard-accessible map list.
- P7: Added evidence-backed new-device, newly reachable-port, and offline alerts with deduplication, acknowledgment, resolution, and an owner event timeline. Added daily probe-evidence retention, a controlled browser end-to-end test, and install/backup/restore instructions.
