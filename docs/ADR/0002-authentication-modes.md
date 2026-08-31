# ADR 0002: Explicit demo and OIDC authentication modes

## Decision

Permit labelled demo authentication only in `development`/`test`; require OIDC
JWT validation in staging/production. Map roles to permissions in the backend.

## Rationale

A browser-selectable role is useful for a synthetic portfolio demo but is not
identity. Configuration validation prevents it being silently carried into an
internet-facing environment.

## Consequences

An actual issuer, session strategy, key rotation process, and gateway deployment
are still required. The frontend never replaces backend authorization.
