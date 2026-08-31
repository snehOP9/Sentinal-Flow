# Security architecture

## Identity and authorization

`ENVIRONMENT=production` or `staging` fails validation if demo authentication or
`schema_management=create_all` is selected. Those modes require OIDC issuer,
audience, and JWKS configuration. The backend validates bearer-token signature,
issuer, audience, expiry, issued-at time, subject, organisation claim, and a
configured role claim before creating a principal.

In the local synthetic demo, the Next.js server sets an HttpOnly same-site cookie
after a user selects a labelled demo role. The browser calls same-origin routes;
the proxy alone reads that cookie and forwards `X-Demo-Role` to the backend. This
is a usability mechanism, not production authentication.

Roles map to capabilities such as `transaction.score`, `case.decide`,
`outcome.write`, `model.read`, and `integration.manage`. The frontend may hide
actions, but every API endpoint authorizes the capability server-side.

## Service accounts

Tenant administrators can issue a scoped API key once. Only its SHA-256 verifier,
prefix, scopes, expiry, revocation timestamp, and last-used timestamp are stored.
The raw key is returned only at creation, and revocation is audited. For rotation,
create a replacement with a bounded expiry, update the integration, verify it,
then revoke the old key. Use a dedicated integration identity; never place a key
in browser code.

## Tenant boundary

This portfolio implementation uses repository-enforced organization predicates
with tenant-scoping tests. It is appropriate for the demo/pilot architecture but
not a substitute for defence-in-depth in a high-assurance deployment. Add
PostgreSQL row-level security, restricted database roles, and independent tenant
isolation tests before handling customer data.

## Runtime safeguards

API responses have request IDs, structured problem envelopes, no-store caching,
baseline security headers, bounded request size, and a local rate-limit fallback.
Use gateway or Redis-backed rate limits in production. The API never claims a
durable score if the database fails. Redis read failure rejects scoring rather
than substituting fake zero velocity values; failed state updates are retried via
the durable outbox and surfaced in monitoring.
