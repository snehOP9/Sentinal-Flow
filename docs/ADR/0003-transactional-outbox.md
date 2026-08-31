# ADR 0003: Transactional outbox for online feature state

## Decision

Persist the decision, audit event, and feature-state outbox event in one database
transaction. Process Redis updates from the outbox with idempotent markers,
retries, and dead-letter status.

## Rationale

A durable score must not silently lose its velocity-state update after a Redis or
process failure. Database commit is authoritative; Redis is derived online state.

## Consequences

The demo makes a fast-path processing attempt. A deployed worker and reconciliation
schedule are required to guarantee recovery after downtime.
