# Architecture

```mermaid
flowchart LR
  Browser[Browser] -->|same-origin /api| BFF[Next.js route handler]
  BFF -->|OIDC bearer or demo cookie context| API[FastAPI API]
  API --> Auth[JWT/API-key + capability check]
  Auth --> Tenant[Tenant-bound application service]
  Tenant --> PIT[Strict-prior feature read]
  PIT --> Redis[(Redis event-time state)]
  PIT --> Model[Calibrated model bundle]
  Model --> Policy[Policy recommendation]
  Policy --> PG[(PostgreSQL)]
  PG --> Outbox[Transactional outbox]
  Outbox --> Worker[Outbox worker / retry]
  Worker --> Redis
  PG --> Cases[Cases, review actions, outcomes, audit]
  Trainer[Temporal training pipeline] --> MLflow[MLflow / artifacts]
  MLflow --> Model
```

## Score sequence

```mermaid
sequenceDiagram
  participant C as Integration or BFF
  participant A as API
  participant D as PostgreSQL
  participant R as Redis
  participant M as Model + policy
  C->>A: token, tenant identity, request, Idempotency-Key
  A->>A: validate identity, permission, currency, timestamp, contract
  A->>D: check tenant-scoped idempotency/external transaction
  A->>R: read only events strictly before T
  A->>M: construct features, score, apply recommendation
  A->>D: transaction: decision + audit + outbox (+ review case)
  A->>R: fast-path process durable outbox event
  A-->>C: probability + recommendation + version evidence
```

Equal timestamps are concurrent and cannot observe one another. Out-of-order
events are scored against the state strictly available before their event time.
The present design uses bounded eventual state application through the outbox; it
does not yet serialize concurrent entities with Redis locks or a partitioned
stream. That trade-off is intentional and must be reconsidered for a customer
latency/ordering contract.

## Storage boundary

PostgreSQL is authoritative for decisions, idempotency records, tenant context,
cases, outcomes, API-key verifiers, audit events, and outbox state. Redis stores
derived event-time feature state. If Redis is unavailable, scoring fails visibly;
the service never claims that fabricated zero velocity context is a valid score.

## Deployment profile

Compose is a local synthetic demo topology: Next.js, FastAPI, PostgreSQL, Redis,
MLflow, and a one-shot Alembic migration service. It is not a staging deployment.
For a pilot, place OIDC/TLS/rate limiting at a gateway, use managed PostgreSQL and
Redis in private networking, run migrations and workers as separately observed
jobs, and add row-level security, backups, monitoring exporters, and customer
security controls.
