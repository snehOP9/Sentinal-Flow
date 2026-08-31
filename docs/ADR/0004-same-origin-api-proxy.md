# ADR 0004: Same-origin frontend API proxy

## Decision

The browser calls `/api/v1/...` on the Next.js origin. A dynamic route handler
proxies to the server-side `SENTINELFLOW_API_ORIGIN` and forwards correlation,
idempotency, bearer, and demo-session context as appropriate.

## Rationale

This avoids a compiled browser backend hostname, CORS complexity, and client-held
demo authorization state across local, Compose, and deployment environments.

## Consequences

The proxy is not the authorization system. Production needs a secure OIDC session
handoff/gateway and must not enable demo mode.
