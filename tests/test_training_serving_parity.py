from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from fraud_platform.features.online_store import InMemoryFeatureStore
from fraud_platform.features.point_in_time import (
    FEATURE_NAMES,
    build_feature_row,
    build_offline_features,
)


@pytest.mark.asyncio
async def test_offline_and_online_features_are_numerically_identical() -> None:
    frame = pd.DataFrame(
        [
            {
                "transaction_id": "txn-0001",
                "timestamp": "2025-01-01T10:00:00Z",
                "customer_id": "customer-a",
                "card_id": "card-a",
                "merchant_id": "m1",
                "merchant_category": "grocery",
                "amount": 18.0,
                "channel": "chip",
                "location": "CA",
                "is_fraud": 0,
            },
            {
                "transaction_id": "txn-0002",
                "timestamp": "2025-01-01T10:05:00Z",
                "customer_id": "customer-a",
                "card_id": "card-a",
                "merchant_id": "m1",
                "merchant_category": "grocery",
                "amount": 21.0,
                "channel": "chip",
                "location": "CA",
                "is_fraud": 0,
            },
            {
                "transaction_id": "txn-0003",
                "timestamp": "2025-01-01T10:07:00Z",
                "customer_id": "customer-a",
                "card_id": "card-a",
                "merchant_id": "m2",
                "merchant_category": "digital_goods",
                "amount": 300.0,
                "channel": "online",
                "location": "ONLINE",
                "is_fraud": 1,
            },
        ]
    )
    offline = build_offline_features(frame)
    store = InMemoryFeatureStore()
    for index, row in frame.iterrows():
        transaction = row.to_dict()
        online = build_feature_row(transaction, await store.context(transaction))
        np.testing.assert_allclose(
            [offline.loc[index, name] for name in FEATURE_NAMES],
            [online[name] for name in FEATURE_NAMES],
        )
        assert await store.record_if_absent(transaction)
