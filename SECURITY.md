# Security policy

## Reporting

Please do not file public issues for potential vulnerabilities. Report them privately
to the repository owner with a reproducible description, affected version, and impact.
Do not include real payment data, credentials, or access tokens.

## Security posture

SentinelFlow is a production-oriented reference architecture, not a PCI-DSS-certified
payments product. It validates requests, limits request size and rate, uses parameterised
SQLAlchemy access, separates model probability from business policy, records redacted
audit metadata, and runs containers as non-root. Production deployments must supply
managed TLS, secret storage, network isolation, and an organization-specific identity
provider before handling non-synthetic data.

## Current dependency exception

`pip-audit` currently reports `PYSEC-2026-3552` for `cryptography 49.0.0`. MLflow 3.15.2
requires `cryptography <50`, while the advisory's fixed version is 50.0.0, making a secure
upgrade unsatisfiable without an upstream MLflow release. CI runs the scanner with this one
documented ID ignored; all other Python vulnerabilities fail CI. MLflow is internal-only in
the Compose topology and must not be exposed publicly. Remove the exception as soon as a
compatible MLflow release exists.
