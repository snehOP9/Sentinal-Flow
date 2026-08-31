from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from fraud_platform.features.point_in_time import HistoricalEvent, VelocityContext


class OnlineFeatureStore(ABC):
    @abstractmethod
    async def context(self, transaction: dict[str, Any]) -> VelocityContext: ...

    @abstractmethod
    async def record_if_absent(self, transaction: dict[str, Any]) -> bool: ...

    @abstractmethod
    async def healthy(self) -> bool: ...


class InMemoryFeatureStore(OnlineFeatureStore):
    """Deterministic development/test implementation with the same strict-time semantics."""

    def __init__(self) -> None:
        self.customers: dict[str, list[HistoricalEvent]] = defaultdict(list)
        self.cards: dict[str, list[HistoricalEvent]] = defaultdict(list)
        self.processed: set[str] = set()

    @staticmethod
    def _scoped(transaction: dict[str, Any], key: str) -> str:
        return f"{transaction.get('organization_id', 'org_demo')}:{transaction[key]}"

    @staticmethod
    def _event(transaction: dict[str, Any]) -> HistoricalEvent:
        from fraud_platform.features.point_in_time import _timestamp

        return HistoricalEvent(
            transaction_id=str(transaction["transaction_id"]),
            timestamp=_timestamp(transaction["timestamp"]),
            amount=float(transaction["amount"]),
            merchant_id=str(transaction["merchant_id"]),
            location=str(transaction["location"]),
        )

    async def context(self, transaction: dict[str, Any]) -> VelocityContext:
        return VelocityContext.from_events(
            self.customers[self._scoped(transaction, "customer_id")],
            self.cards[self._scoped(transaction, "card_id")],
        )

    async def record_if_absent(self, transaction: dict[str, Any]) -> bool:
        transaction_id = self._scoped(transaction, "transaction_id")
        if transaction_id in self.processed:
            return False
        self.processed.add(transaction_id)
        event = self._event(transaction)
        self.customers[self._scoped(transaction, "customer_id")].append(event)
        self.cards[self._scoped(transaction, "card_id")].append(event)
        return True

    async def healthy(self) -> bool:
        return True


class RedisFeatureStore(OnlineFeatureStore):
    """Redis sorted-set store. Reads use score `< transaction timestamp`, never `<=`."""

    retention = timedelta(days=8)

    def __init__(self, redis_url: str) -> None:
        import redis.asyncio as redis

        self.client: Any = redis.from_url(  # type: ignore[no-untyped-call]
            redis_url, decode_responses=True
        )

    @staticmethod
    def _key(organization_id: str, kind: str, value: str) -> str:
        return f"sentinelflow:pit:v1:{organization_id}:{kind}:{value}:events"

    async def _events(self, key: str, before: datetime) -> list[HistoricalEvent]:
        raw = await self.client.zrangebyscore(key, "-inf", f"({before.timestamp()}")
        events = [json.loads(value) for value in raw]
        return [
            HistoricalEvent(
                transaction_id=event["transaction_id"],
                timestamp=datetime.fromisoformat(event["timestamp"]),
                amount=float(event["amount"]),
                merchant_id=event["merchant_id"],
                location=event["location"],
            )
            for event in events
        ]

    async def context(self, transaction: dict[str, Any]) -> VelocityContext:
        from fraud_platform.features.point_in_time import _timestamp

        before = _timestamp(transaction["timestamp"])
        organization_id = str(transaction.get("organization_id", "org_demo"))
        customer_key = self._key(organization_id, "customer", str(transaction["customer_id"]))
        card_key = self._key(organization_id, "card", str(transaction["card_id"]))
        customer, card = (
            await self._events(customer_key, before),
            await self._events(card_key, before),
        )
        return VelocityContext.from_events(customer, card)

    async def record_if_absent(self, transaction: dict[str, Any]) -> bool:
        """Atomically reserve an idempotency marker and record both entity histories."""
        from fraud_platform.features.point_in_time import _timestamp

        transaction_id = str(transaction["transaction_id"])
        now = _timestamp(transaction["timestamp"])
        payload = json.dumps(
            {
                "transaction_id": transaction_id,
                "timestamp": now.isoformat(),
                "amount": float(transaction["amount"]),
                "merchant_id": str(transaction["merchant_id"]),
                "location": str(transaction["location"]),
            },
            separators=(",", ":"),
        )
        organization_id = str(transaction.get("organization_id", "org_demo"))
        marker = f"sentinelflow:pit:v1:{organization_id}:processed:{transaction_id}"
        user_key = self._key(organization_id, "customer", str(transaction["customer_id"]))
        card_key = self._key(organization_id, "card", str(transaction["card_id"]))
        script = """
        if redis.call('SET', KEYS[1], '1', 'NX', 'EX', ARGV[1]) == false then return 0 end
        redis.call('ZADD', KEYS[2], ARGV[2], ARGV[3])
        redis.call('ZADD', KEYS[3], ARGV[2], ARGV[3])
        redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', ARGV[4])
        redis.call('ZREMRANGEBYSCORE', KEYS[3], '-inf', ARGV[4])
        redis.call('EXPIRE', KEYS[2], ARGV[1])
        redis.call('EXPIRE', KEYS[3], ARGV[1])
        return 1
        """
        result = await self.client.eval(
            script,
            3,
            marker,
            user_key,
            card_key,
            int(self.retention.total_seconds()),
            now.timestamp(),
            payload,
            (now - self.retention).timestamp(),
        )
        return bool(result)

    async def healthy(self) -> bool:
        return bool(await self.client.ping())
