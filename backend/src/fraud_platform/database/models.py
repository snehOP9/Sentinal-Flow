from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (
        UniqueConstraint("key_prefix", name="uq_api_key_prefix"),
        Index("ix_api_keys_organization_status", "organization_id", "revoked_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    permissions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TransactionDecision(Base):
    """Immutable scoring decision; `id` maps to the legacy physical PK name."""

    __tablename__ = "transaction_decisions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "external_transaction_id",
            name="uq_decision_org_external_transaction",
        ),
        CheckConstraint("amount_minor >= 0", name="ck_decision_amount_minor_nonnegative"),
        CheckConstraint("length(currency) = 3", name="ck_decision_currency_iso4217"),
        Index("ix_decisions_org_created", "organization_id", "created_at"),
        Index("ix_decisions_org_decision_created", "organization_id", "decision", "created_at"),
        Index("ix_decisions_org_customer_created", "organization_id", "customer_id", "created_at"),
    )

    id: Mapped[str] = mapped_column("transaction_id", String(80), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    external_transaction_id: Mapped[str] = mapped_column(String(120), nullable=False)
    program_id: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    customer_id: Mapped[str] = mapped_column(String(80), nullable=False)
    card_id: Mapped[str] = mapped_column(String(80), nullable=False)
    merchant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    merchant_category: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    location: Mapped[str] = mapped_column(String(32), nullable=False)
    # Kept read-compatible with predecessor data; new writes use minor units only.
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    risk_probability: Mapped[float] = mapped_column(Float, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(64), nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    client_id: Mapped[str] = mapped_column(String(120), nullable=False)
    feature_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    explanations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    state_update_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    confirmed_fraud: Mapped[bool | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "endpoint",
            "client_id",
            "idempotency_key",
            name="uq_idempotency_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    endpoint: Mapped[str] = mapped_column(String(160), nullable=False)
    client_id: Mapped[str] = mapped_column(String(120), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("transaction_decisions.transaction_id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class RiskCase(Base):
    __tablename__ = "cases"
    __table_args__ = (
        Index("ix_cases_org_queue_opened", "organization_id", "queue", "status", "opened_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("transaction_decisions.transaction_id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    queue: Mapped[str] = mapped_column(String(80), nullable=False, default="risk-review")
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    assigned_to: Mapped[str | None] = mapped_column(String(160))
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CaseEvent(Base):
    __tablename__ = "case_events"
    __table_args__ = (
        Index("ix_case_events_org_case_created", "organization_id", "case_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(160), nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReviewAction(Base):
    __tablename__ = "review_actions"
    __table_args__ = (
        Index("ix_review_actions_org_case_created", "organization_id", "case_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="RESTRICT"), nullable=False
    )
    actor_id: Mapped[str] = mapped_column(String(160), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    advisory_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Outcome(Base):
    __tablename__ = "outcomes"
    __table_args__ = (
        UniqueConstraint("organization_id", "transaction_id", name="uq_outcome_transaction"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("transaction_decisions.transaction_id", ondelete="RESTRICT"), nullable=False
    )
    confirmed_fraud: Mapped[bool] = mapped_column(Boolean, nullable=False)
    maturity_state: Mapped[str] = mapped_column(String(24), nullable=False, default="observed")
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    recorded_by: Mapped[str] = mapped_column(String(160), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_org_status_available", "organization_id", "status", "available_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("transaction_decisions.transaction_id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_org_created", "organization_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    transaction_id: Mapped[str | None] = mapped_column(String(80), index=True)
    case_id: Mapped[str | None] = mapped_column(String(36), index=True)
    actor_id: Mapped[str] = mapped_column(String(160), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(80))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
