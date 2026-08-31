from __future__ import annotations

import pytest

from fraud_platform.features.online_store import InMemoryFeatureStore


@pytest.mark.asyncio
async def test_online_store_is_idempotent_and_handles_out_of_order_reads() -> None:
    store = InMemoryFeatureStore()
    later = {
        "transaction_id": "tx-later",
        "customer_id": "customer-a",
        "card_id": "card-a",
        "merchant_id": "m1",
        "location": "CA",
        "amount": 20.0,
        "timestamp": "2025-01-01T12:00:00Z",
    }
    earlier = {**later, "transaction_id": "tx-earlier", "timestamp": "2025-01-01T11:00:00Z"}
    assert await store.record_if_absent(later)
    assert not await store.record_if_absent(later)
    assert await store.record_if_absent(earlier)
    context = await store.context(later)
    assert [
        event.transaction_id
        for event in context.customer_events
        if event.timestamp.isoformat().startswith("2025-01-01T11")
    ] == ["tx-earlier"]
