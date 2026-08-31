# Operational runbooks

## Redis unavailable

1. The scoring API returns a retryable dependency error; it does not create a
   score with missing velocity features.
2. Inspect `/api/v1/health`, `/api/v1/monitoring`, Redis availability, and
   outbox counts.
3. Restore Redis, then run the outbox worker/reconciliation process until pending
   state updates are drained. Investigate any `dead_letter` event before replay.

## Database unavailable

1. Treat scoring success as unavailable. Do not accept a client response as
   durable when PostgreSQL cannot be checked.
2. Restore the authoritative database, run the migration compatibility check,
   and verify readiness before reopening traffic.

## Bad model or policy behavior

1. Stop external actions at the gateway/integration layer; the current demo never
   sends them automatically.
2. Switch to the customer-approved fallback policy only after risk-owner approval.
3. Preserve the model/policy version, request IDs, cases, and outcomes for review.
4. Document the incident and do not infer real-world fraud quality from synthetic data.

## Compromised API key

1. Revoke the key through the tenant-bound API-key endpoint.
2. Review `API_KEY_CREATED`/`API_KEY_REVOKED` audit events and integration logs.
3. Issue a least-privilege replacement, update the integration, and record the incident.

These are operating procedures for a reference implementation. Recovery time and
recovery point objectives remain customer/deployment design decisions, not tested
service commitments.
