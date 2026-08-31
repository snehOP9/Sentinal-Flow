"""Generate an entirely fictional, deterministic fraud-demo dataset.

No names, card numbers, account numbers, addresses, or real financial events are used.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


def generate(rows: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    customers = np.array([f"cust_{index:04d}" for index in range(550)])
    cards = {customer: f"card_{index:04d}" for index, customer in enumerate(customers)}
    merchants = np.array([f"merchant_{index:03d}" for index in range(90)])
    categories = np.array(
        [
            "grocery",
            "fuel",
            "restaurant",
            "digital_goods",
            "money_transfer",
            "gambling",
            "jewelry",
            "travel",
        ]
    )
    locations = np.array(["NY", "CA", "TX", "IL", "FL", "ONLINE", "WA"])
    channels = np.array(["chip", "swipe", "online"])
    base = datetime(2025, 1, 1, tzinfo=UTC)
    customer_clock = {
        customer: base + timedelta(minutes=int(rng.integers(0, 240))) for customer in customers
    }
    records: list[dict[str, object]] = []
    for index in range(rows):
        customer = str(rng.choice(customers))
        rapid = rng.random() < 0.08
        minutes = int(rng.exponential(9 if rapid else 560))
        customer_clock[customer] += timedelta(minutes=minutes)
        timestamp = customer_clock[customer]
        category = str(rng.choice(categories, p=[0.25, 0.13, 0.18, 0.10, 0.05, 0.04, 0.05, 0.20]))
        channel = str(rng.choice(channels, p=[0.36, 0.31, 0.33]))
        new_merchant = rng.random() < 0.14
        merchant = f"new_{index:06d}" if new_merchant else str(rng.choice(merchants))
        amount = float(np.clip(rng.lognormal(mean=3.6, sigma=0.85), 1, 3_500))
        location = "ONLINE" if channel == "online" else str(rng.choice(locations[:-1]))
        # Deliberately noisy but learnable simulated fraud process: it rewards a model
        # that combines point-in-time velocity with transaction context, rather than
        # pretending a random label is predictable.
        risk_logit = -5.0
        risk_logit += (
            2.0 if category in {"money_transfer", "digital_goods", "gambling", "jewelry"} else 0
        )
        risk_logit += 1.0 if channel == "online" else 0
        risk_logit += 1.4 if amount > 500 else 0
        risk_logit += 1.5 if rapid else 0
        risk_logit += 0.8 if new_merchant else 0
        probability = 1 / (1 + np.exp(-risk_logit))
        records.append(
            {
                "transaction_id": f"demo_{index:07d}",
                "timestamp": timestamp.isoformat(),
                "customer_id": customer,
                "card_id": cards[customer],
                "merchant_id": merchant,
                "merchant_category": category,
                "amount": round(amount, 2),
                "channel": channel,
                "location": location,
                "is_fraud": int(rng.random() < probability),
            }
        )
    return pd.DataFrame(records).sort_values(["timestamp", "transaction_id"], kind="stable")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=24_000)
    parser.add_argument("--seed", type=int, default=20260830)
    parser.add_argument("--output", type=Path, default=Path("data/demo/transactions.csv"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    generate(args.rows, args.seed).to_csv(args.output, index=False)
    print(f"Wrote synthetic demo data to {args.output}")


if __name__ == "__main__":
    main()
