# API

The versioned operational API lives under `/api/v1`; FastAPI serves OpenAPI at `/docs`. Authentication uses a local session cookie and a CSRF token for mutations. List responses use `items` and pagination metadata. All errors carry a machine-readable `code` and human-readable `message`.
