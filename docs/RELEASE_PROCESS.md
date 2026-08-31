# Release process

1. Run formatter, lint, type checks, Python tests, frontend lint/test/build, and
   regenerate OpenAPI.
2. Review Alembic migration and downgrade implications; run it in staging before
   application rollout.
3. Build/scan immutable serving, worker, and frontend images; attach SBOM and
   provenance when the deployment platform supports them.
4. Deploy migrations, then worker/API, then frontend. Verify readiness, auth,
   outbox health, and rollback path.
5. Record approved policy/model versions, test evidence, and customer change
   approval. Training never deploys a model by itself.

Image scans, SBOMs, provenance, staging automation, and model approval records are
not implemented in this repository; this document is a required operating process,
not evidence that those controls ran.
