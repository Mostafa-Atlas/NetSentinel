# ADR 0001: Single instance scheduler

Phase 1 runs one FastAPI process with an in-process bounded job worker and scheduler. This avoids a broker for a small LAN while ensuring there is one schedule owner. Interrupted `running` jobs are marked `failed` on restart. Multiple process workers are unsupported until durable distributed coordination is added.
