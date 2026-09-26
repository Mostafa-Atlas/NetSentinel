# Architecture

The browser uses the same origin for the API in production; Vite proxies API requests during development. FastAPI owns authenticated API routes, a bounded asynchronous scan worker, a single scheduler, and SQLite persistence. API handlers queue scan jobs and return promptly. UTC timestamps are rendered in the browser's local timezone. Observations remain immutable; current status is derived from recent evidence.

Run one process in the standard deployment. Multiple web workers would each start a scheduler, so horizontal scaling needs an external scheduler and job coordination that are outside Phase 1.

Device identity is deliberately conservative. Repeated observations with the same observed MAC can update one device across IP changes, but a new MAC on an old IP creates a separate device. Without a MAC, the app maintains a separate provisional IP identity. The dashboard shows this confidence rather than silently merging uncertain records. Address rows preserve first and last observation times.

The single scheduler checks enabled approved scopes every 30 seconds only when the owner has enabled automatic discovery. It enqueues at most one due run per scope and respects a minimum 15-minute interval. Existing queued/running jobs and a recent finished job prevent duplicate scheduling after restart. A device becomes offline only after the configured number of consecutive no-response observations; a single miss remains unconfirmed. The first service observation establishes a baseline, while a later transition to reachable is a change candidate.
