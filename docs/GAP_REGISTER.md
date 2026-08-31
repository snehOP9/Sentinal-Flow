# Gap register — 2026-08-31

| Severity | Gap | Status / dependency |
| --- | --- | --- |
| Critical | Production role spoofing | Closed in configuration: production rejects demo auth; demo browser role is an HttpOnly-cookie-only path. OIDC needs a real IdP deployment. |
| Critical | Global tenant namespace | Partially closed: tenant-scoped schema and repository predicates exist. Add PostgreSQL RLS before customer data. |
| High | Transaction ID used as sole idempotency key | Closed for score path: scoped idempotency keys hash canonical payloads; changed external IDs require correction workflow. |
| High | Redis update could be lost after durable decision | Partially closed: transactional outbox, retries, and monitoring state exist; deploy worker/reconciliation scheduler. |
| High | Float money persistence | Closed for new writes: currency plus integer minor units. Legacy float column is read-compatible during migration only. |
| High | No analyst workflow | Closed for initial single-transaction cases and immutable advisory actions. Extend to linked entities and queue SLA. |
| High | Browser contains API hostname and demo role | Closed: same-origin Next BFF proxy and server-held demo cookie. Production OIDC UI session handoff remains deployment work. |
| Medium | `create_all` in production startup | Closed by environment validation; Compose has an Alembic migration service. |
| Medium | Policy/model approvals | Open: current policy/model governance is metadata and documentation, not a customer approval control plane. |
| Medium | Full operational assurance | Open: build/test evidence exists locally; integration, E2E, load, backup, SBOM, SAST/container scans, IaC, and staging remain required. |
