# Scanning safety

Use NetSentinel only on a network you own or are authorized to administer. The administrator must enter and approve a private IPv4 CIDR before any probe runs. The baseline refuses public, loopback, multicast, and ranges larger than 256 addresses. Scans use TCP connect probes with a one-second timeout and bounded concurrency. No exploit, credential, stealth, or packet-capture functionality is included. Results are time-bounded observations, not vulnerability findings.
