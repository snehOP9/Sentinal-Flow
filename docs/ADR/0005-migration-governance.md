# ADR 0005: Alembic is the deployed schema path

## Decision

Use Alembic migrations in Compose and non-development environments. Allow
`create_all` only as an explicitly configured test/local convenience.

## Rationale

Application startup must not create unknown schema drift in an operational
database. A separate migration job makes rollout ordering explicit.

## Consequences

The migration job must be run and monitored during deployment. A PostgreSQL
migration upgrade/downgrade CI job remains an outstanding quality gate.
