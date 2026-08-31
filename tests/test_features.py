from __future__ import annotations

import pandas as pd
import pytest

from fraud_platform.data.contracts import DataContractError, temporal_split, validate_transactions
from fraud_platform.features.point_in_time import build_offline_features


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "transaction_id": "tx-001",
                "timestamp": "2025-01-01T10:00:00Z",
                "customer_id": "customer-a",
                "card_id": "card-a",
                "merchant_id": "merchant-a",
                "merchant_category": "grocery",
                "amount": 10.0,
                "channel": "chip",
                "location": "CA",
                "is_fraud": 0,
            },
            {
                "transaction_id": "tx-002",
                "timestamp": "2025-01-01T10:00:00Z",
                "customer_id": "customer-a",
                "card_id": "card-a",
                "merchant_id": "merchant-b",
                "merchant_category": "grocery",
                "amount": 20.0,
                "channel": "online",
                "location": "CA",
                "is_fraud": 0,
            },
            {
                "transaction_id": "tx-003",
                "timestamp": "2025-01-01T11:00:00Z",
                "customer_id": "customer-a",
                "card_id": "card-a",
                "merchant_id": "merchant-c",
                "merchant_category": "digital_goods",
                "amount": 90.0,
                "channel": "online",
                "location": "ONLINE",
                "is_fraud": 1,
            },
        ]
    )


def test_equal_timestamp_events_cannot_observe_each_other() -> None:
    features = build_offline_features(_frame())
    assert features.loc[0, "customer_txn_count_1h"] == 0
    assert features.loc[1, "customer_txn_count_1h"] == 0
    assert features.loc[2, "customer_txn_count_1h"] == 0  # strict 1h boundary
    assert features.loc[2, "customer_txn_count_24h"] == 2


def test_contract_rejects_duplicate_transaction_id() -> None:
    frame = _frame()
    frame.loc[1, "transaction_id"] = "tx-001"
    with pytest.raises(DataContractError, match="unique"):
        validate_transactions(frame)


def test_temporal_split_keeps_timestamp_groups_together() -> None:
    frame = pd.concat([_frame()] * 4, ignore_index=True)
    frame["transaction_id"] = [f"tx-{i:03d}" for i in range(len(frame))]
    frame["timestamp"] = pd.date_range("2025-01-01", periods=len(frame), freq="D", tz="UTC")
    train, validation, test = temporal_split(frame)
    assert train.timestamp.max() < validation.timestamp.min() < test.timestamp.min()
