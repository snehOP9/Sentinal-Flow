from __future__ import annotations

import builtins
import hashlib
import secrets
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import case, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from fraud_platform.database.models import (
    ApiKey,
    AuditEvent,
    Base,
    CaseEvent,
    IdempotencyRecord,
    Organization,
    OutboxEvent,
    Outcome,
    ReviewAction,
    RiskCase,
    TransactionDecision,
)


class IdempotencyConflictError(Exception):
    pass


class ExternalTransactionConflictError(Exception):
    pass


class DecisionRepository:
    """Tenant-scoped operational persistence.

    Repository predicates are the primary multi-tenant boundary in this reference
    implementation. Production deployments should add PostgreSQL RLS as a second
    boundary; the repository deliberately never accepts an unverified tenant from
    a browser request.
    """

    def __init__(
        self,
        database_url: str,
        schema_management: str = "create_all",
        expected_schema_revision: str = "0002_operations_foundation",
    ) -> None:
        self.engine: AsyncEngine = create_async_engine(database_url, pool_pre_ping=True)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.schema_management = schema_management
        self.expected_schema_revision = expected_schema_revision

    async def initialize(
        self, demo_organization_id: str | None = None, demo_organization_name: str | None = None
    ) -> None:
        if self.schema_management == "create_all":
            async with self.engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
        else:
            # This is intentionally a real check rather than a successful no-op.
            async with self.engine.connect() as connection:
                revision = await connection.scalar(
                    text("SELECT version_num FROM alembic_version LIMIT 1")
                )
            if revision != self.expected_schema_revision:
                raise RuntimeError(
                    "Database migration revision is incompatible with this application "
                    f"(expected {self.expected_schema_revision!r}, found {revision!r})"
                )
        if demo_organization_id and demo_organization_name:
            await self.ensure_organization(demo_organization_id, demo_organization_name)

    async def close(self) -> None:
        await self.engine.dispose()

    async def healthy(self) -> bool:
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    async def ensure_organization(self, organization_id: str, name: str) -> None:
        async with self.sessions() as session:
            existing = await session.get(Organization, organization_id)
            if existing is None:
                session.add(Organization(id=organization_id, name=name))
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()

    @staticmethod
    def serialize(record: TransactionDecision) -> dict[str, Any]:
        return {
            "transaction_id": record.external_transaction_id,
            "decision_id": record.id,
            "organization_id": record.organization_id,
            "program_id": record.program_id,
            "customer_id": record.customer_id,
            "card_id": record.card_id,
            "merchant_id": record.merchant_id,
            "merchant_category": record.merchant_category,
            "channel": record.channel,
            "location": record.location,
            "amount_minor": record.amount_minor,
            "currency": record.currency,
            # A compatibility display value; never use it for durable money logic.
            "amount": record.amount_minor / 100,
            "timestamp": record.event_timestamp.isoformat(),
            "ingested_at": record.ingested_at.isoformat() if record.ingested_at else None,
            "risk_probability": record.risk_probability,
            "decision": record.decision,
            "policy_version": record.policy_version,
            "model_version": record.model_version,
            "feature_version": record.feature_version,
            "latency_ms": record.latency_ms,
            "features": record.feature_snapshot,
            "explanations": record.explanations,
            "state_update_status": record.state_update_status,
            "confirmed_fraud": record.confirmed_fraud,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }

    @staticmethod
    def serialize_case(
        case_record: RiskCase, decision: TransactionDecision | None = None
    ) -> dict[str, Any]:
        data: dict[str, Any] = {
            "case_id": case_record.id,
            "queue": case_record.queue,
            "priority": case_record.priority,
            "status": case_record.status,
            "assigned_to": case_record.assigned_to,
            "opened_at": case_record.opened_at.isoformat() if case_record.opened_at else None,
            "closed_at": case_record.closed_at.isoformat() if case_record.closed_at else None,
        }
        if decision:
            data["transaction"] = DecisionRepository.serialize(decision)
        return data

    async def get(
        self, organization_id: str, external_transaction_id: str
    ) -> dict[str, Any] | None:
        async with self.sessions() as session:
            record = await session.scalar(
                select(TransactionDecision).where(
                    TransactionDecision.organization_id == organization_id,
                    TransactionDecision.external_transaction_id == external_transaction_id,
                )
            )
            return self.serialize(record) if record else None

    async def _decision(
        self, session: Any, organization_id: str, external_transaction_id: str
    ) -> TransactionDecision | None:
        return cast(
            TransactionDecision | None,
            await session.scalar(
                select(TransactionDecision).where(
                    TransactionDecision.organization_id == organization_id,
                    TransactionDecision.external_transaction_id == external_transaction_id,
                ),
            ),
        )

    async def find_idempotency(
        self, organization_id: str, endpoint: str, client_id: str, idempotency_key: str
    ) -> tuple[str, str] | None:
        async with self.sessions() as session:
            record = await session.scalar(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.organization_id == organization_id,
                    IdempotencyRecord.endpoint == endpoint,
                    IdempotencyRecord.client_id == client_id,
                    IdempotencyRecord.idempotency_key == idempotency_key,
                )
            )
            if record is None:
                return None
            decision = await session.get(TransactionDecision, record.transaction_id)
            if decision is None:
                return None
            return record.request_fingerprint, decision.external_transaction_id

    async def persist(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None,
        endpoint: str,
        actor_id: str,
        request_id: str | None,
    ) -> tuple[dict[str, Any], bool]:
        """Persist decision + idempotency marker + outbox event atomically."""
        organization_id = str(payload["organization_id"])
        async with self.sessions() as session:
            record = TransactionDecision(**payload)
            session.add(record)
            await session.flush()
            if idempotency_key:
                session.add(
                    IdempotencyRecord(
                        organization_id=organization_id,
                        endpoint=endpoint,
                        client_id=record.client_id,
                        idempotency_key=idempotency_key,
                        request_fingerprint=record.request_fingerprint,
                        transaction_id=record.id,
                    )
                )
            session.add(
                OutboxEvent(
                    organization_id=organization_id,
                    transaction_id=record.id,
                    event_type="FEATURE_STATE_UPDATE",
                    payload={
                        "transaction_id": record.id,
                        "external_transaction_id": record.external_transaction_id,
                        "organization_id": organization_id,
                        "customer_id": record.customer_id,
                        "card_id": record.card_id,
                        "merchant_id": record.merchant_id,
                        "merchant_category": record.merchant_category,
                        "channel": record.channel,
                        "location": record.location,
                        "amount": record.amount_minor / 100,
                        "timestamp": record.event_timestamp.isoformat(),
                    },
                )
            )
            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    transaction_id=record.id,
                    actor_id=actor_id,
                    request_id=request_id,
                    event_type="SCORED",
                    detail="Scoring decision and feature-state outbox event persisted",
                )
            )
            if record.decision in {"REVIEW", "BLOCK"}:
                case_record = RiskCase(
                    organization_id=organization_id,
                    transaction_id=record.id,
                    priority="high" if record.decision == "BLOCK" else "normal",
                )
                session.add(case_record)
                await session.flush()
                session.add(
                    CaseEvent(
                        organization_id=organization_id,
                        case_id=case_record.id,
                        event_type="CASE_OPENED_FROM_RECOMMENDATION",
                        actor_id="system",
                        detail={"recommendation": record.decision, "advisory_only": True},
                    )
                )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = await self._decision(
                    session, organization_id, str(payload["external_transaction_id"])
                )
                if existing is not None:
                    if existing.request_fingerprint == str(payload["request_fingerprint"]):
                        return self.serialize(existing), False
                    raise ExternalTransactionConflictError(
                        "This external transaction ID already exists with different meaningful data"
                    ) from None
                if idempotency_key:
                    idem = await self.find_idempotency(
                        organization_id, endpoint, str(payload["client_id"]), idempotency_key
                    )
                    if idem and idem[0] != str(payload["request_fingerprint"]):
                        raise IdempotencyConflictError(
                            "Idempotency key was reused with a different payload"
                        ) from None
                raise
            await session.refresh(record)
            return self.serialize(record), True

    async def mark_state_status(
        self, organization_id: str, transaction_id: str, status: str, detail: str
    ) -> None:
        async with self.sessions() as session:
            record = await session.get(TransactionDecision, transaction_id)
            if record and record.organization_id == organization_id:
                record.state_update_status = status
                session.add(
                    AuditEvent(
                        organization_id=organization_id,
                        transaction_id=transaction_id,
                        actor_id="worker",
                        request_id=None,
                        event_type="FEATURE_STATE",
                        detail=detail,
                    )
                )
                await session.commit()

    async def claim_next_outbox(self) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        async with self.sessions() as session:
            event = await session.scalar(
                select(OutboxEvent)
                .where(OutboxEvent.status == "pending", OutboxEvent.available_at <= now)
                .order_by(OutboxEvent.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if event is None:
                return None
            event.status = "processing"
            event.attempts += 1
            await session.commit()
            return {
                "id": event.id,
                "organization_id": event.organization_id,
                "transaction_id": event.transaction_id,
                "event_type": event.event_type,
                "payload": event.payload,
                "attempts": event.attempts,
            }

    async def complete_outbox(self, event_id: str) -> None:
        async with self.sessions() as session:
            event = await session.get(OutboxEvent, event_id)
            if event:
                event.status = "processed"
                event.processed_at = datetime.now(UTC)
                event.last_error = None
                await session.commit()

    async def defer_outbox(self, event_id: str, error: str, max_attempts: int = 8) -> None:
        async with self.sessions() as session:
            event = await session.get(OutboxEvent, event_id)
            if event:
                event.last_error = error[:1000]
                if event.attempts >= max_attempts:
                    event.status = "dead_letter"
                else:
                    event.status = "pending"
                    event.available_at = datetime.now(UTC) + timedelta(
                        seconds=min(300, 2 ** min(event.attempts, 8))
                    )
                await session.commit()

    async def outbox_health(self, organization_id: str) -> dict[str, int]:
        async with self.sessions() as session:
            rows = (
                await session.execute(
                    select(OutboxEvent.status, func.count())
                    .where(OutboxEvent.organization_id == organization_id)
                    .group_by(OutboxEvent.status)
                )
            ).all()
        statuses = {str(status): int(count) for status, count in rows}
        return {
            "pending": statuses.get("pending", 0),
            "processing": statuses.get("processing", 0),
            "dead_letter": statuses.get("dead_letter", 0),
        }

    async def list(
        self,
        organization_id: str,
        limit: int,
        offset: int,
        decision: str | None,
        search: str | None,
    ) -> tuple[list[dict[str, Any]], int]:
        filters = [TransactionDecision.organization_id == organization_id]
        if decision:
            filters.append(TransactionDecision.decision == decision)
        if search:
            filters.append(TransactionDecision.external_transaction_id.contains(search))
        async with self.sessions() as session:
            count = int(
                (
                    await session.scalar(
                        select(func.count()).select_from(TransactionDecision).where(*filters)
                    )
                )
                or 0
            )
            records = (
                await session.scalars(
                    select(TransactionDecision)
                    .where(*filters)
                    .order_by(TransactionDecision.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                )
            ).all()
            return [self.serialize(record) for record in records], count

    async def summary(self, organization_id: str, days: int = 30) -> dict[str, Any]:
        since = datetime.now(UTC) - timedelta(days=days)
        async with self.sessions() as session:
            aggregate = (
                await session.execute(
                    select(
                        func.count(TransactionDecision.id),
                        func.coalesce(func.avg(TransactionDecision.latency_ms), 0),
                        func.coalesce(
                            func.sum(case((TransactionDecision.decision == "BLOCK", 1), else_=0)), 0
                        ),
                        func.coalesce(
                            func.sum(case((TransactionDecision.decision == "REVIEW", 1), else_=0)),
                            0,
                        ),
                        func.coalesce(
                            func.sum(case((TransactionDecision.decision == "ALLOW", 1), else_=0)), 0
                        ),
                    ).where(
                        TransactionDecision.organization_id == organization_id,
                        TransactionDecision.created_at >= since,
                    )
                )
            ).one()
            total, latency, blocks, reviews, allows = aggregate
            return {
                "transactions_screened": int(total),
                "fraud_alerts": int(blocks + reviews),
                "approval_rate": float(allows / total) if total else 0.0,
                "manual_review_rate": float(reviews / total) if total else 0.0,
                "average_inference_latency_ms": round(float(latency), 2),
                "estimated_loss_prevented": None,
                "false_positive_rate": None,
                "fraud_capture_rate": None,
                "metric_context": {
                    "range": f"last {days} days by ingestion time",
                    "population": "synthetic scored transactions in the authenticated organization",
                    "labels": "partial or absent unless outcomes were explicitly recorded",
                    "kind": "operational",
                    "data": "synthetic",
                    "point_in_time": True,
                },
            }

    async def timeseries(
        self, organization_id: str, days: int = 14
    ) -> builtins.list[dict[str, Any]]:
        since = datetime.now(UTC) - timedelta(days=days)
        async with self.sessions() as session:
            rows = (
                await session.execute(
                    select(
                        func.date(TransactionDecision.created_at).label("date"),
                        func.count().label("transactions"),
                        func.sum(case((TransactionDecision.decision != "ALLOW", 1), else_=0)).label(
                            "alerts"
                        ),
                    )
                    .where(
                        TransactionDecision.organization_id == organization_id,
                        TransactionDecision.created_at >= since,
                    )
                    .group_by(func.date(TransactionDecision.created_at))
                    .order_by(func.date(TransactionDecision.created_at))
                )
            ).all()
            return [
                {"date": str(date), "transactions": int(transactions), "alerts": int(alerts)}
                for date, transactions, alerts in rows
            ]

    async def record_outcome(
        self,
        organization_id: str,
        external_transaction_id: str,
        confirmed_fraud: bool,
        source: str,
        actor_id: str,
    ) -> dict[str, Any] | None:
        async with self.sessions() as session:
            record = await self._decision(session, organization_id, external_transaction_id)
            if not record:
                return None
            existing = await session.scalar(
                select(Outcome).where(
                    Outcome.organization_id == organization_id, Outcome.transaction_id == record.id
                )
            )
            if existing is not None:
                if existing.confirmed_fraud != confirmed_fraud:
                    raise ExternalTransactionConflictError(
                        "Outcome exists with a different value; record a governed correction "
                        "instead"
                    )
                return self.serialize(record)
            record.confirmed_fraud = confirmed_fraud
            session.add(
                Outcome(
                    organization_id=organization_id,
                    transaction_id=record.id,
                    confirmed_fraud=confirmed_fraud,
                    source=source,
                    recorded_by=actor_id,
                )
            )
            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    transaction_id=record.id,
                    actor_id=actor_id,
                    request_id=None,
                    event_type="OUTCOME_RECORDED",
                    detail=f"confirmed_fraud={confirmed_fraud}; source={source}",
                )
            )
            await session.commit()
            await session.refresh(record)
            return self.serialize(record)

    async def list_cases(
        self, organization_id: str, limit: int, status: str | None, queue: str | None
    ) -> builtins.list[dict[str, Any]]:
        filters = [RiskCase.organization_id == organization_id]
        if status:
            filters.append(RiskCase.status == status)
        if queue:
            filters.append(RiskCase.queue == queue)
        async with self.sessions() as session:
            rows = (
                await session.execute(
                    select(RiskCase, TransactionDecision)
                    .join(TransactionDecision, TransactionDecision.id == RiskCase.transaction_id)
                    .where(*filters)
                    .order_by(RiskCase.opened_at.desc())
                    .limit(limit)
                )
            ).all()
            return [self.serialize_case(case_record, decision) for case_record, decision in rows]

    async def case_detail(self, organization_id: str, case_id: str) -> dict[str, Any] | None:
        async with self.sessions() as session:
            row = (
                await session.execute(
                    select(RiskCase, TransactionDecision)
                    .join(TransactionDecision, TransactionDecision.id == RiskCase.transaction_id)
                    .where(RiskCase.organization_id == organization_id, RiskCase.id == case_id)
                )
            ).one_or_none()
            if row is None:
                return None
            case_record, decision = row
            events = (
                await session.scalars(
                    select(CaseEvent)
                    .where(
                        CaseEvent.organization_id == organization_id, CaseEvent.case_id == case_id
                    )
                    .order_by(CaseEvent.created_at)
                )
            ).all()
            actions = (
                await session.scalars(
                    select(ReviewAction)
                    .where(
                        ReviewAction.organization_id == organization_id,
                        ReviewAction.case_id == case_id,
                    )
                    .order_by(ReviewAction.created_at)
                )
            ).all()
            data = self.serialize_case(case_record, decision)
            data["events"] = [
                {
                    "id": event.id,
                    "type": event.event_type,
                    "actor": event.actor_id,
                    "detail": event.detail,
                    "created_at": event.created_at.isoformat(),
                }
                for event in events
            ]
            data["review_actions"] = [
                {
                    "id": action.id,
                    "action": action.action,
                    "reason_code": action.reason_code,
                    "note": action.note,
                    "actor": action.actor_id,
                    "advisory_only": action.advisory_only,
                    "created_at": action.created_at.isoformat(),
                }
                for action in actions
            ]
            return data

    async def record_review_action(
        self,
        organization_id: str,
        case_id: str,
        *,
        action: str,
        reason_code: str,
        note: str | None,
        actor_id: str,
    ) -> dict[str, Any] | None:
        async with self.sessions() as session:
            case_record = await session.scalar(
                select(RiskCase).where(
                    RiskCase.organization_id == organization_id, RiskCase.id == case_id
                )
            )
            if case_record is None:
                return None
            review = ReviewAction(
                organization_id=organization_id,
                case_id=case_id,
                actor_id=actor_id,
                action=action,
                reason_code=reason_code,
                note=note,
            )
            case_record.status = (
                "closed" if action in {"approve", "decline_recommendation", "duplicate"} else "open"
            )
            if case_record.status == "closed":
                case_record.closed_at = datetime.now(UTC)
            session.add(review)
            session.add(
                CaseEvent(
                    organization_id=organization_id,
                    case_id=case_id,
                    event_type="REVIEW_ACTION_RECORDED",
                    actor_id=actor_id,
                    detail={"action": action, "reason_code": reason_code, "advisory_only": True},
                )
            )
            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    transaction_id=case_record.transaction_id,
                    case_id=case_id,
                    actor_id=actor_id,
                    request_id=None,
                    event_type="CASE_REVIEW_ACTION",
                    detail=f"action={action}; reason_code={reason_code}; advisory_only=true",
                )
            )
            await session.commit()
        return await self.case_detail(organization_id, case_id)

    async def recent_observations(
        self, organization_id: str, limit: int = 1_000
    ) -> tuple[Sequence[dict[str, float]], Sequence[float]]:
        async with self.sessions() as session:
            records = (
                await session.scalars(
                    select(TransactionDecision)
                    .where(TransactionDecision.organization_id == organization_id)
                    .order_by(TransactionDecision.created_at.desc())
                    .limit(limit)
                )
            ).all()
            return (
                [record.feature_snapshot for record in records],
                [float(record.risk_probability) for record in records],
            )

    async def api_key_by_prefix(self, prefix: str) -> ApiKey | None:
        async with self.sessions() as session:
            return cast(
                ApiKey | None,
                await session.scalar(select(ApiKey).where(ApiKey.key_prefix == prefix)),
            )

    async def touch_api_key(self, api_key_id: str) -> None:
        async with self.sessions() as session:
            key = await session.get(ApiKey, api_key_id)
            if key:
                key.last_used_at = datetime.now(UTC)
                await session.commit()

    async def create_api_key(
        self,
        organization_id: str,
        *,
        name: str,
        permissions: builtins.list[str],
        expires_at: datetime | None,
        actor_id: str,
    ) -> tuple[dict[str, Any], str]:
        """Create a scoped service credential and return its secret exactly once."""
        prefix = f"sfk_{secrets.token_hex(4)}"
        raw_key = f"{prefix}_{secrets.token_urlsafe(32)}"
        record = ApiKey(
            organization_id=organization_id,
            name=name,
            key_prefix=prefix,
            key_hash=hashlib.sha256(raw_key.encode("utf-8")).hexdigest(),
            permissions=permissions,
            expires_at=expires_at,
        )
        async with self.sessions() as session:
            session.add(record)
            session.add(
                AuditEvent(
                    organization_id=organization_id,
                    transaction_id=None,
                    case_id=None,
                    actor_id=actor_id,
                    request_id=None,
                    event_type="API_KEY_CREATED",
                    detail=(
                        f"api_key_id={record.id}; prefix={prefix}; scopes={','.join(permissions)}"
                    ),
                )
            )
            await session.commit()
            await session.refresh(record)
        return (
            {
                "id": record.id,
                "name": record.name,
                "prefix": record.key_prefix,
                "permissions": record.permissions,
                "expires_at": record.expires_at.isoformat() if record.expires_at else None,
                "created_at": record.created_at.isoformat(),
            },
            raw_key,
        )

    async def revoke_api_key(self, organization_id: str, api_key_id: str, actor_id: str) -> bool:
        async with self.sessions() as session:
            record = await session.scalar(
                select(ApiKey).where(
                    ApiKey.organization_id == organization_id, ApiKey.id == api_key_id
                )
            )
            if record is None:
                return False
            if record.revoked_at is None:
                record.revoked_at = datetime.now(UTC)
                session.add(
                    AuditEvent(
                        organization_id=organization_id,
                        transaction_id=None,
                        case_id=None,
                        actor_id=actor_id,
                        request_id=None,
                        event_type="API_KEY_REVOKED",
                        detail=f"api_key_id={api_key_id}; prefix={record.key_prefix}",
                    )
                )
                await session.commit()
            return True
