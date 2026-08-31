# Deployment guide

## Local synthetic demo

```bash
cp .env.example .env
docker compose up --build
```

Compose starts PostgreSQL and Redis on an internal network, runs `alembic upgrade
head`, then starts the API, the Next.js console, MLflow, and an outbox worker.
Open `http://localhost:3000` and choose a clearly labelled synthetic demo role.
Backend OpenAPI is at `http://localhost:8000/docs`.

Docker Desktop was unavailable in the implementation environment, so the Compose
configuration was validated but images/migrations were not executed here.

## Production-oriented target

Use a dynamic Next.js deployment (container or server-capable platform), a
FastAPI-serving deployment, a separately supervised outbox worker, managed
PostgreSQL, managed Redis, private networking, protected artifact/MLflow storage,
and a gateway/identity provider. Do not deploy a purely static frontend: the
same-origin API proxy is a server route handler and its upstream origin is a
runtime server setting.

1. Provision PostgreSQL, Redis, object storage, OIDC provider, secret manager,
   TLS gateway, logging/metrics destination, and backup policy.
2. Run the migration job with `SCHEMA_MANAGEMENT=migrate`; verify the version is
   `0002_operations_foundation` before starting API/worker processes.
3. Set `ENVIRONMENT=production`, `AUTH_MODE=oidc`, `DEMO_AUTH_ENABLED=false`,
   OIDC issuer/audience/JWKS settings, database/Redis URLs, model artifact path,
   CORS origin, and `SENTINELFLOW_API_ORIGIN` only in server-side configuration.
4. Start API and worker with non-root images and private database/Redis access.
   Start Next.js behind the same public gateway; do not expose Redis, PostgreSQL,
   MLflow, raw service credentials, or demo mode.
5. Verify readiness, outbox health, logs/request IDs, backup restore procedure,
   auth denial metrics, and customer-approved policy/model release before traffic.

## Required before customer data

This repository does not provision cloud credentials, Terraform, a staging
environment, customer legal/privacy review, production OIDC sessions, RLS,
distributed rate limiting, backups, observability exporters, image/SBOM scans,
or data-retention operations. Those require environment-specific authority and
must be completed before processing customer data.
