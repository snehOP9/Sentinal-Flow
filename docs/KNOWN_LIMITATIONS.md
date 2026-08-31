# Known limitations

- All included data, outcomes, metrics, and scenarios are synthetic. No claim is
  made about real fraud capture, accuracy, fairness, loss prevention, or bank readiness.
- Repository tenant predicates are implemented; PostgreSQL row-level security is
  recommended before real multi-tenant customer data.
- OIDC/JWT validation is implemented, but no external identity provider, session
  refresh flow, SAML, SCIM, or production gateway is provisioned in this repository.
- The outbox persists and retries Redis feature-state events. A separately deployed
  worker, reconciliation scheduler, webhook delivery worker, and dead-letter UI
  are still required for production operations.
- Cases contain one transaction in this increment. Entity-linked multi-transaction
  cases, assignment/SLA queues, attachments, exports, and legal hold are planned.
- Policy and model version metadata are recorded, but a complete immutable policy
  registry, two-person approval, live canary release, model manifest verification,
  and rollback control plane remain planned.
- Cursor pagination, full audit export, distributed rate limiting, OpenTelemetry
  exporters, object storage, Terraform, SBOM/container scans, browser E2E, load
  testing, backup restore, and a staging deployment are not implemented or
  independently verified here.
