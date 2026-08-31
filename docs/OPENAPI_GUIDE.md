# OpenAPI guide

`docs/openapi.json` is generated from the FastAPI application with:

```bash
python scripts/export_openapi.py
```

CI regenerates it and rejects an uncommitted contract diff. Clients should use the
versioned `/api/v1` paths, preserve `X-Request-ID` if supplied, honor `Retry-After`,
and not automatically retry writes unless they have an idempotency key.
