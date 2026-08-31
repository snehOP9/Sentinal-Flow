# Threat model

| Threat | Controls | Residual action |
|---|---|---|
| API abuse / denial of service | Request-size cap, per-client limiter, health checks, private service network | Use gateway/WAF limits and autoscaling in production. |
| Credential theft | No stored demo passwords, environment-first config, no secrets in code | Use managed OIDC, MFA, secret rotation, and short-lived tokens. |
| Inference scraping | Auth gate, rate limit, minimal response surface | Enforce tenant quotas and anomaly alerts. |
| PII exposure | Synthetic demo data, no PAN/CVV fields, redacted audit shape | Classify data, encrypt storage, establish retention/deletion policy. |
| Redis exposure | Not published by Compose; namespaced keys, TTL, atomic script | Use TLS/auth and private managed Redis. |
| Database compromise | Parameterized SQLAlchemy, non-root containers, no public DB port | TLS, managed backups, least-privilege DB role, encryption at rest. |
| Data poisoning | Versioned validated datasets, temporal pipeline, dataset fingerprint | Add approval workflow and source-provenance verification. |
| Supply-chain vulnerability | Pinned ranges, CI `pip-audit`/`npm audit`, multi-stage builds | Pin lock files and remediate advisories continuously. |

Never log authorization headers, secrets, card numbers, CVVs, or passwords. The service
adds request IDs and structured request metadata without raw request-body logging.
