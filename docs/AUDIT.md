# Upstream audit — 2026-08-30

This audit records findings from the prior codebase. It is a verified code audit, not a
restatement of a project README.

## CRITICAL

- `src/ml/feature_store.py` used a time-based rolling window that included the current
  row by default. The API read Redis state before adding the transaction. Thus offline
  velocity features and online velocity features disagreed at the same event time.
- The online Redis implementation used expiring counters, not event-time windows. It
  could not correctly score delayed or out-of-order transactions, and it reset window
  expiry with each increment.
- There was no database uniqueness constraint or request idempotency. A retry could
  increment velocity state and create a second decision.

## HIGH

- Risk thresholds were hard-coded (`pend=0.4`, `reject=0.8`) without validation-cost
  evidence.
- The frontend was a one-line Streamlit placeholder, while the README described a UI.
- The API used `allow_origins=["*"]` together with credentials and returned a made-up
  `PEND` decision with score `0.5` on internal errors.
- The PostgreSQL audit write was detached in a background task; an HTTP success did not
  establish that the decision had been retained.
- The feature engine silently filled missing serving-time fields with zero, hiding
  training-serving mismatch. It also used feature-store velocity columns only when
  present, which ensured online scoring omitted trained velocity features.

## MEDIUM

- Training performed a timestamp sort but did not protect equal-timestamp feature
  groups, did not compare baselines, did not evaluate calibration, and evaluated only
  ROC-AUC/PR-AUC plus a fixed `0.5` threshold.
- The feature store included a historical merchant fraud-rate feature described in the
  README, but there was no leak-safe target-encoding implementation or proof of its
  temporal availability.
- Kafka startup was attempted as an undocumented background side effect. No reliable
  delivery or consumer lifecycle semantics were demonstrated.
- There was no schema/data contract, dataset fingerprint, migration system, model card,
  threat model, health readiness distinction, monitoring, or dependency scan.

## LOW

- `Makefile` was empty. Dockerfiles duplicated each other and did not construct a full
  local system. Required configuration was spread across Aiven/GCP-specific variables.
- README included claims that could not be reproduced because no data or reproducible
  training command was committed.

## GOOD PRACTICE

- The upstream code attempted a chronological split, used class weighting, loaded model
  artefacts rather than re-training in each request, and placed state read before update.
  SentinelFlow retains those intentions but replaces the implementation.

## License finding

No upstream `LICENSE`/`COPYING` file was present. `NOTICE.md` records this fact. New
SentinelFlow code is a clean implementation; upstream files are not represented as
permissively licensed or suitable for proprietary redistribution.
