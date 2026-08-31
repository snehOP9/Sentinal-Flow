"""A single feature definition used by offline training and online scoring.

The invariant is deliberate: `features(event)` can read only events whose timestamp is
strictly less than `event.timestamp`. Equal timestamp events are treated as concurrent
and therefore cannot observe one another in either path.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from math import log1p
from typing import Any, cast

import numpy as np
import pandas as pd

WINDOW_SECONDS = {"5m": 300, "1h": 3_600, "24h": 86_400, "7d": 604_800}
FEATURE_NAMES = [
    "amount",
    "log_amount",
    "hour",
    "day_of_week",
    "is_weekend",
    "channel_online",
    "channel_chip",
    "channel_swipe",
    "high_risk_category",
    "customer_txn_count_5m",
    "customer_txn_count_1h",
    "customer_txn_count_24h",
    "customer_txn_count_7d",
    "customer_amount_sum_1h",
    "customer_amount_sum_24h",
    "card_txn_count_1h",
    "card_amount_sum_24h",
    "customer_historical_avg_amount",
    "amount_to_customer_average",
    "amount_deviation_zscore",
    "seconds_since_customer_previous_transaction",
    "customer_merchant_diversity_24h",
    "customer_location_diversity_24h",
    "new_merchant_for_customer",
]
HIGH_RISK_CATEGORIES = {"money_transfer", "digital_goods", "gambling", "jewelry"}


def _timestamp(value: Any) -> datetime:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        parsed = parsed.tz_localize("UTC")
    return cast(datetime, parsed.to_pydatetime())


@dataclass(frozen=True)
class HistoricalEvent:
    transaction_id: str
    timestamp: datetime
    amount: float
    merchant_id: str
    location: str


@dataclass
class VelocityContext:
    customer_events: list[HistoricalEvent] = field(default_factory=list)
    card_events: list[HistoricalEvent] = field(default_factory=list)

    @classmethod
    def from_events(
        cls, customer_events: Iterable[HistoricalEvent], card_events: Iterable[HistoricalEvent]
    ) -> VelocityContext:
        return cls(list(customer_events), list(card_events))


def _in_window(
    events: Iterable[HistoricalEvent], now: datetime, seconds: int
) -> list[HistoricalEvent]:
    cutoff = now.timestamp() - seconds
    return [event for event in events if cutoff < event.timestamp.timestamp() < now.timestamp()]


def build_feature_row(transaction: dict[str, Any], history: VelocityContext) -> dict[str, float]:
    """Create a numeric feature vector from a transaction and strictly-prior history."""
    timestamp = _timestamp(transaction["timestamp"])
    amount = float(transaction["amount"])
    customer_events = [e for e in history.customer_events if e.timestamp < timestamp]
    card_events = [e for e in history.card_events if e.timestamp < timestamp]
    channel = str(transaction.get("channel", "online")).lower()

    def customer_window(name: str) -> list[HistoricalEvent]:
        return _in_window(customer_events, timestamp, WINDOW_SECONDS[name])

    window_1h = customer_window("1h")
    window_24h = customer_window("24h")
    card_1h = _in_window(card_events, timestamp, WINDOW_SECONDS["1h"])
    card_24h = _in_window(card_events, timestamp, WINDOW_SECONDS["24h"])
    past_amounts = np.asarray([event.amount for event in customer_events], dtype=float)
    average = float(past_amounts.mean()) if len(past_amounts) else amount
    stddev = float(past_amounts.std()) if len(past_amounts) > 1 else 0.0
    previous = max(customer_events, key=lambda event: event.timestamp, default=None)
    return {
        "amount": amount,
        "log_amount": log1p(amount),
        "hour": float(timestamp.hour),
        "day_of_week": float(timestamp.weekday()),
        "is_weekend": float(timestamp.weekday() >= 5),
        "channel_online": float(channel == "online"),
        "channel_chip": float(channel == "chip"),
        "channel_swipe": float(channel == "swipe"),
        "high_risk_category": float(
            str(transaction.get("merchant_category", "")).lower() in HIGH_RISK_CATEGORIES
        ),
        "customer_txn_count_5m": float(len(customer_window("5m"))),
        "customer_txn_count_1h": float(len(window_1h)),
        "customer_txn_count_24h": float(len(window_24h)),
        "customer_txn_count_7d": float(len(customer_window("7d"))),
        "customer_amount_sum_1h": float(sum(event.amount for event in window_1h)),
        "customer_amount_sum_24h": float(sum(event.amount for event in window_24h)),
        "card_txn_count_1h": float(len(card_1h)),
        "card_amount_sum_24h": float(sum(event.amount for event in card_24h)),
        "customer_historical_avg_amount": average,
        "amount_to_customer_average": float(amount / max(average, 1.0)),
        "amount_deviation_zscore": float((amount - average) / max(stddev, 1.0)),
        "seconds_since_customer_previous_transaction": float(
            (timestamp - previous.timestamp).total_seconds() if previous else 604_800
        ),
        "customer_merchant_diversity_24h": float(len({event.merchant_id for event in window_24h})),
        "customer_location_diversity_24h": float(len({event.location for event in window_24h})),
        "new_merchant_for_customer": float(
            not any(
                event.merchant_id == str(transaction["merchant_id"]) for event in customer_events
            )
        ),
    }


def build_offline_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Produce features with no present/future event leakage.

    Events sharing a timestamp are evaluated against the same snapshot and added only
    after the whole timestamp group has been transformed.
    """
    required = {
        "transaction_id",
        "timestamp",
        "customer_id",
        "card_id",
        "amount",
        "merchant_id",
        "location",
    }
    missing = required.difference(frame.columns)
    if missing:
        raise KeyError(f"Cannot build features; missing {sorted(missing)}")
    work = frame.copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True)
    work = work.sort_values(["timestamp", "transaction_id"], kind="stable")
    customer_history: dict[str, deque[HistoricalEvent]] = defaultdict(deque)
    card_history: dict[str, deque[HistoricalEvent]] = defaultdict(deque)
    result: list[dict[str, float]] = []
    for _, group in work.groupby("timestamp", sort=True):
        rows = group.to_dict(orient="records")
        for row in rows:
            result.append(
                build_feature_row(
                    row,
                    VelocityContext.from_events(
                        customer_history[str(row["customer_id"])], card_history[str(row["card_id"])]
                    ),
                )
            )
        for row in rows:
            event = HistoricalEvent(
                transaction_id=str(row["transaction_id"]),
                timestamp=_timestamp(row["timestamp"]),
                amount=float(row["amount"]),
                merchant_id=str(row["merchant_id"]),
                location=str(row["location"]),
            )
            customer_history[str(row["customer_id"])].append(event)
            card_history[str(row["card_id"])].append(event)
    engineered = pd.DataFrame(result, index=work.index)
    engineered = engineered.loc[frame.index]
    return engineered[FEATURE_NAMES]
