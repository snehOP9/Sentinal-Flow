# API guide

The generated contract is [openapi.json](openapi.json); interactive documentation
is available at `/docs` on a running backend. API paths are versioned under
`/api/v1`. Responses use a correlated problem envelope with `code`, `title`,
`detail`, `request_id`, and `retryable` when an operation fails.

Authentication is tenant-bound. Production requires a validated OIDC bearer token
or a scoped API key. The local demo accepts `X-Demo-Role` only when its server-side
configuration explicitly allows demo mode; the web console normally supplies it
through its server proxy, not browser JavaScript.

| Method | Path | Permission | Purpose |
| --- | --- | --- | --- |
| POST | `/transactions/score` | `transaction.score` | Score one tokenised event and create its durable outbox state. |
| GET | `/transactions`, `/transactions/{id}` | `transaction.read` | List or retrieve only records in the caller’s organization. |
| GET/POST | `/cases`, `/cases/{id}`, `/cases/{id}/actions` | `case.read` / `case.decide` | Work an advisory review case and append its immutable events. |
| POST | `/outcomes` | `outcome.write` | Record an observed outcome with source provenance. |
| POST | `/api-keys`, `/api-keys/{id}/revoke` | `integration.manage` | Issue a one-time scoped service credential or revoke it. |
| GET | `/dashboard/*`, `/monitoring` | read/monitoring capability | Tenant-scoped operational metrics and current outbox/dependency state. |
| GET/POST | `/model/*`, `/decisioning/simulate` | model/policy capability | Read model metadata or run a synthetic validation scenario. |
| GET | `/health`, `/ready` | none | Liveness and real dependency readiness checks. |

## Scoring request and idempotency

Use a customer-provided external `transaction_id` plus a unique `Idempotency-Key`
for a retriable integration operation. The API hashes canonical meaningful input.
The same scoped key and payload returns the original decision; the same key with a
different payload returns `409 IDEMPOTENCY_CONFLICT`. Reusing an external ID with
meaningfully changed data returns `409 EXTERNAL_TRANSACTION_CONFLICT`; a governed
correction endpoint is intentionally not implemented yet.

```bash
curl http://localhost:8000/api/v1/transactions/score \
  -H 'Content-Type: application/json' \
  -H 'X-Demo-Role: analyst' \
  -H 'Idempotency-Key: demo-score-0001' \
  -d '{"transaction_id":"demo-0001","customer_id":"customer-01","card_id":"card-01","merchant_id":"merchant-01","merchant_category":"digital_goods","amount_minor":85000,"currency":"USD","channel":"online","location":"ONLINE","timestamp":"2026-08-30T12:00:00Z"}'
```

The response contains a model probability, policy recommendation, policy/model/
feature versions, contribution signals, and point-in-time velocity context. It
does not contain a final payment action or evidence that fraud occurred.
