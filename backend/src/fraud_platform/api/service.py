from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from fraud_platform.auth.permissions import Principal
from fraud_platform.config import Settings
from fraud_platform.database.repository import (
    DecisionRepository,
    ExternalTransactionConflictError,
    IdempotencyConflictError,
)
from fraud_platform.features.online_store import (
    InMemoryFeatureStore,
    OnlineFeatureStore,
    RedisFeatureStore,
)
from fraud_platform.features.point_in_time import build_feature_row
from fraud_platform.models.bundle import ModelBundle


class FraudScoringService:
    def __init__(
        self,
        settings: Settings,
        repository: DecisionRepository,
        store: OnlineFeatureStore,
        bundle: ModelBundle | None,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.store = store
        self.bundle = bundle

    @classmethod
    def from_settings(cls, settings: Settings) -> FraudScoringService:
        bundle = ModelBundle.load(settings.model_path) if settings.model_path.exists() else None
        store: OnlineFeatureStore = (
            RedisFeatureStore(settings.redis_url) if settings.redis_url else InMemoryFeatureStore()
        )
        return cls(
            settings,
            DecisionRepository(
                settings.database_url, settings.schema_management, settings.expected_schema_revision
            ),
            store,
            bundle,
        )

    async def start(self) -> None:
        await self.repository.initialize(
            self.settings.demo_organization_id if self.settings.demo_auth_enabled else None,
            self.settings.demo_organization_name if self.settings.demo_auth_enabled else None,
        )

    async def close(self) -> None:
        await self.repository.close()

    async def healthy(self) -> dict[str, bool]:
        return {
            "model": self.bundle is not None,
            "database": await self.repository.healthy(),
            "online_feature_store": await self.store.healthy(),
        }

    @staticmethod
    def request_fingerprint(transaction: dict[str, Any]) -> str:
        meaningful = {
            key: value
            for key, value in transaction.items()
            if key not in {"amount"}  # amount_minor is canonical durable money input
        }
        canonical = json.dumps(meaningful, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def score(
        self,
        transaction: dict[str, Any],
        principal: Principal,
        *,
        idempotency_key: str | None,
        request_id: str | None,
    ) -> tuple[dict[str, Any], bool]:
        if self.bundle is None:
            raise RuntimeError("Model artifact is unavailable; scoring is not durably acknowledged")
        transaction = dict(transaction)
        transaction["organization_id"] = principal.organization_id
        external_id = str(transaction["transaction_id"])
        fingerprint = self.request_fingerprint(transaction)
        endpoint = "/api/v1/transactions/score"
        client_id = principal.api_key_id or principal.subject

        if idempotency_key:
            existing_key = await self.repository.find_idempotency(
                principal.organization_id, endpoint, client_id, idempotency_key
            )
            if existing_key:
                if existing_key[0] != fingerprint:
                    raise IdempotencyConflictError(
                        "Idempotency-Key is already bound to a different canonical request"
                    )
                existing = await self.repository.get(principal.organization_id, existing_key[1])
                if existing:
                    return existing, False

        existing = await self.repository.get(principal.organization_id, external_id)
        if existing:
            # Legacy callers without an idempotency key retain a safe replay only
            # for the same canonical data. Corrections require a future explicit API.
            if existing["decision_id"] and await self._fingerprint_matches(
                principal.organization_id, external_id, fingerprint
            ):
                return existing, False
            raise ExternalTransactionConflictError(
                "External transaction ID is already present with different meaningful data"
            )

        # A failed Redis read is a controlled dependency failure. It never silently
        # replaces behaviour features with zeros, because this model was trained with
        # those features present.
        history = await self.store.context(transaction)
        started = time.perf_counter()
        features = build_feature_row(transaction, history)
        probability = self.bundle.predict_proba(features)
        decision, _reason = self.bundle.policy.decide(probability)
        explanations = self.bundle.explain(features)
        latency_ms = (time.perf_counter() - started) * 1_000
        payload = {
            "organization_id": principal.organization_id,
            "external_transaction_id": external_id,
            "program_id": str(transaction["program_id"]),
            "customer_id": str(transaction["customer_id"]),
            "card_id": str(transaction["card_id"]),
            "merchant_id": str(transaction["merchant_id"]),
            "merchant_category": str(transaction["merchant_category"]),
            "channel": str(transaction["channel"]),
            "location": str(transaction["location"]),
            "amount_minor": int(transaction["amount_minor"]),
            "currency": str(transaction["currency"]),
            "event_timestamp": transaction["timestamp"],
            "risk_probability": probability,
            "decision": decision,
            "policy_version": "validation-derived-v1",
            "model_version": self.bundle.model_version,
            "feature_version": self.bundle.feature_version,
            "latency_ms": latency_ms,
            "request_fingerprint": fingerprint,
            "client_id": client_id,
            "feature_snapshot": features,
            "explanations": explanations,
            "state_update_status": "pending",
        }
        record, created = await self.repository.persist(
            payload,
            idempotency_key=idempotency_key,
            endpoint=endpoint,
            actor_id=principal.subject,
            request_id=request_id,
        )
        if created:
            # Fast-path worker attempt for the local demo. The durable outbox remains
            # the source of truth when Redis is unavailable or the process exits.
            await self.process_outbox(limit=1)
            refreshed = await self.repository.get(principal.organization_id, external_id)
            if refreshed:
                record = refreshed
        return record, created

    async def _fingerprint_matches(
        self, organization_id: str, external_transaction_id: str, fingerprint: str
    ) -> bool:
        # The externally shaped record intentionally omits fingerprints. Querying
        # through the idempotency-aware storage boundary keeps it non-user-visible.
        async with self.repository.sessions() as session:
            from sqlalchemy import select

            from fraud_platform.database.models import TransactionDecision

            stored = await session.scalar(
                select(TransactionDecision.request_fingerprint).where(
                    TransactionDecision.organization_id == organization_id,
                    TransactionDecision.external_transaction_id == external_transaction_id,
                )
            )
            return stored == fingerprint

    async def process_outbox(self, limit: int = 25) -> int:
        processed = 0
        for _ in range(limit):
            event = await self.repository.claim_next_outbox()
            if event is None:
                break
            try:
                if event["event_type"] != "FEATURE_STATE_UPDATE":
                    raise RuntimeError(f"Unsupported outbox event {event['event_type']}")
                updated = await self.store.record_if_absent(event["payload"])
                await self.repository.mark_state_status(
                    event["organization_id"],
                    event["transaction_id"],
                    "applied" if updated else "already_applied",
                    "Online velocity state updated from durable outbox",
                )
                await self.repository.complete_outbox(event["id"])
                processed += 1
            except Exception as exc:
                await self.repository.mark_state_status(
                    event["organization_id"],
                    event["transaction_id"],
                    "retrying",
                    f"Outbox feature-state update deferred: {type(exc).__name__}",
                )
                await self.repository.defer_outbox(event["id"], type(exc).__name__)
        return processed

    def response(self, record: dict[str, Any], idempotent_replay: bool) -> dict[str, Any]:
        if self.bundle is None:
            raise RuntimeError("No bundle")
        decision = str(record["decision"])
        reasons = [
            {
                "type": "model_threshold",
                "code": f"{decision}_BAND",
                "message": {
                    "ALLOW": "Risk probability is below the active review threshold.",
                    "REVIEW": "Risk probability falls within the active review band.",
                    "BLOCK": "Risk probability is at or above the active block threshold.",
                }[decision],
            }
        ]
        return {
            "transaction_id": record["transaction_id"],
            "decision_id": record["decision_id"],
            "idempotent_replay": idempotent_replay,
            "risk_probability": record["risk_probability"],
            "decision": decision,
            "policy_version": record["policy_version"],
            "model_version": record["model_version"],
            "feature_version": record["feature_version"],
            "latency_ms": round(record["latency_ms"], 2),
            "thresholds": {
                "allow": self.bundle.policy.allow_threshold,
                "block": self.bundle.policy.block_threshold,
            },
            "velocity_context": record["features"],
            "explanations": record["explanations"],
            "decision_reasons": reasons,
            "degraded_mode": False,
        }
