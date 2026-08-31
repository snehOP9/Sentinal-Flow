from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TransactionRequest(BaseModel):
    """Synthetic, tokenised transaction event. Do not send PAN, CVV, or credentials."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    external_transaction_id: str = Field(
        alias="transaction_id", pattern=r"^[A-Za-z0-9._:-]{4,120}$"
    )
    program_id: str = Field(default="default", pattern=r"^[A-Za-z0-9._:-]{2,80}$")
    customer_id: str = Field(pattern=r"^[A-Za-z0-9._:-]{2,80}$")
    card_id: str = Field(pattern=r"^[A-Za-z0-9._:-]{2,80}$")
    merchant_id: str = Field(pattern=r"^[A-Za-z0-9._:-]{2,100}$")
    merchant_category: str = Field(min_length=2, max_length=64)
    # `amount` remains an input compatibility path. It is converted before durable
    # persistence; database rows always store integer minor units plus ISO currency.
    amount: Decimal | None = Field(default=None, gt=Decimal("0"), le=Decimal("1000000"))
    amount_minor: int | None = Field(default=None, ge=1, le=100_000_000)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    channel: Literal["online", "chip", "swipe"]
    location: str = Field(min_length=2, max_length=32)
    timestamp: datetime

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must include a timezone, for example 2026-01-01T12:00:00Z")
        return value

    @model_validator(mode="after")
    def normalize_money(self) -> TransactionRequest:
        if self.amount is None and self.amount_minor is None:
            raise ValueError("provide amount or amount_minor")
        if self.amount is not None:
            calculated_minor = int(
                (self.amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
            if self.amount_minor is not None and self.amount_minor != calculated_minor:
                raise ValueError("amount and amount_minor do not represent the same value")
            self.amount_minor = calculated_minor
        if self.amount is None and self.amount_minor is not None:
            self.amount = Decimal(self.amount_minor) / Decimal(100)
        return self


class DecisionReason(BaseModel):
    type: Literal["model_threshold", "rule", "degraded_mode"]
    code: str
    message: str


class ScoreResponse(BaseModel):
    transaction_id: str
    decision_id: str
    idempotent_replay: bool = False
    risk_probability: float
    decision: Literal["ALLOW", "REVIEW", "BLOCK"]
    policy_version: str
    model_version: str
    feature_version: str
    latency_ms: float
    thresholds: dict[str, float]
    velocity_context: dict[str, float]
    explanations: list[dict[str, Any]]
    decision_reasons: list[DecisionReason]
    degraded_mode: bool = False


class OutcomeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transaction_id: str = Field(pattern=r"^[A-Za-z0-9._:-]{4,120}$")
    confirmed_fraud: bool
    source: str = Field(default="analyst_review", min_length=3, max_length=80)


class CaseActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal[
        "approve",
        "decline_recommendation",
        "escalate",
        "request_information",
        "temporarily_hold",
        "duplicate",
    ]
    reason_code: str = Field(pattern=r"^[A-Z0-9_:-]{3,80}$")
    note: str | None = Field(default=None, max_length=2_000)


class ApiKeyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=3, max_length=120)
    permissions: list[str] = Field(min_length=1, max_length=20)
    expires_at: datetime | None = None

    @field_validator("expires_at")
    @classmethod
    def expiry_must_be_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("expires_at must include a timezone")
        return value


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checks: dict[str, bool]


class ThresholdSimulationRequest(BaseModel):
    fraud_loss: float = Field(gt=0, le=100_000)
    false_decline_cost: float = Field(ge=0, le=100_000)
    review_cost: float = Field(ge=0, le=100_000)
    review_capacity_fraction: float = Field(gt=0, le=1)
