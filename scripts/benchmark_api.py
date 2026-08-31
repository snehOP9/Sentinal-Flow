from __future__ import annotations

import argparse
import asyncio
import statistics
import time
import uuid

import httpx


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8000/api/v1/transactions/score")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()
    semaphore = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient(timeout=20) as client:

        async def score(index: int) -> float:
            payload = {
                "transaction_id": f"bench-{uuid.uuid4()}",
                "customer_id": f"bench-customer-{index % 20}",
                "card_id": f"bench-card-{index % 20}",
                "merchant_id": "merchant-benchmark",
                "merchant_category": "digital_goods",
                "amount": 250.0,
                "channel": "online",
                "location": "ONLINE",
                "timestamp": "2026-01-01T12:00:00Z",
            }
            async with semaphore:
                start = time.perf_counter()
                response = await client.post(
                    args.url, json=payload, headers={"X-Demo-Role": "analyst"}
                )
                response.raise_for_status()
                return (time.perf_counter() - start) * 1_000

        timings = await asyncio.gather(*(score(index) for index in range(args.requests)))
    timings.sort()
    print(
        {
            "requests": args.requests,
            "p50_ms": statistics.median(timings),
            "p95_ms": timings[int(0.95 * len(timings)) - 1],
            "p99_ms": timings[int(0.99 * len(timings)) - 1],
        }
    )


if __name__ == "__main__":
    asyncio.run(main())
