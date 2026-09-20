"""Validation and leakage-safe temporal splitting for transaction datasets."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = (
    "transaction_id",
    "timestamp",
    "customer_id",
    "card_id",
    "merchant_id",
    "merchant_category",
    "amount",
    "channel",
    "location",
    "is_fraud",
)


class DataContractError(ValueError):
    """Raised when a transaction dataset violates the training contract."""


@dataclass(frozen=True)
class DataContractReport:
    rows: int
    positive_rows: int
    fraud_rate: float
    min_timestamp: str
    max_timestamp: str
    fingerprint: str


def _normalized_frame(frame: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(set(REQUIRED_COLUMNS).difference(frame.columns))
    if missing:
        raise DataContractError(f"missing required columns: {missing}")
    if frame.empty:
        raise DataContractError("dataset must contain at least one transaction")

    normalized = frame.loc[:, REQUIRED_COLUMNS].copy()

    if normalized["transaction_id"].isna().any():
        raise DataContractError("transaction_id must not contain null values")
    normalized["transaction_id"] = normalized["transaction_id"].astype(str).str.strip()
    if (normalized["transaction_id"] == "").any():
        raise DataContractError("transaction_id must not contain empty values")
    if normalized["transaction_id"].duplicated().any():
        raise DataContractError("transaction_id must be unique")

    for column in ("customer_id", "card_id", "merchant_id", "merchant_category", "channel", "location"):
        if normalized[column].isna().any():
            raise DataContractError(f"{column} must not contain null values")
        normalized[column] = normalized[column].astype(str).str.strip()
        if (normalized[column] == "").any():
            raise DataContractError(f"{column} must not contain empty values")

    try:
        normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], utc=True, errors="raise")
    except (TypeError, ValueError) as exc:
        raise DataContractError("timestamp must contain valid datetimes") from exc
    if normalized["timestamp"].isna().any():
        raise DataContractError("timestamp must not contain null values")

    try:
        normalized["amount"] = pd.to_numeric(normalized["amount"], errors="raise").astype(float)
    except (TypeError, ValueError) as exc:
        raise DataContractError("amount must be numeric") from exc
    if not np.isfinite(normalized["amount"].to_numpy()).all():
        raise DataContractError("amount must contain only finite values")
    if (normalized["amount"] < 0).any():
        raise DataContractError("amount must be non-negative")

    try:
        labels = pd.to_numeric(normalized["is_fraud"], errors="raise")
    except (TypeError, ValueError) as exc:
        raise DataContractError("is_fraud must be binary") from exc
    if not labels.isin([0, 1]).all():
        raise DataContractError("is_fraud must contain only 0 or 1")
    normalized["is_fraud"] = labels.astype(int)

    return normalized


def validate_transactions(frame: pd.DataFrame) -> DataContractReport:
    """Validate the canonical transaction schema and return reproducibility metadata."""
    normalized = _normalized_frame(frame)
    ordered = normalized.sort_values(["timestamp", "transaction_id"], kind="stable").copy()
    ordered["timestamp"] = ordered["timestamp"].map(lambda value: value.isoformat())
    fingerprint = hashlib.sha256(
        ordered.to_csv(index=False, lineterminator="\n").encode("utf-8")
    ).hexdigest()

    positive_rows = int(normalized["is_fraud"].sum())
    return DataContractReport(
        rows=int(len(normalized)),
        positive_rows=positive_rows,
        fraud_rate=float(positive_rows / len(normalized)),
        min_timestamp=str(normalized["timestamp"].min()),
        max_timestamp=str(normalized["timestamp"].max()),
        fingerprint=fingerprint,
    )


def temporal_split(
    frame: pd.DataFrame,
    train_fraction: float = 0.60,
    validation_fraction: float = 0.20,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split chronologically without placing equal-timestamp events in different partitions."""
    if not 0 < train_fraction < 1:
        raise ValueError("train_fraction must be between 0 and 1")
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between 0 and 1")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("train_fraction + validation_fraction must be less than 1")

    work = _normalized_frame(frame)
    work = work.sort_values(["timestamp", "transaction_id"], kind="stable")

    timestamps = work["timestamp"].drop_duplicates().sort_values().tolist()
    if len(timestamps) < 3:
        raise DataContractError("temporal split requires at least three distinct timestamps")

    train_cut = max(1, int(len(timestamps) * train_fraction))
    validation_cut = max(train_cut + 1, int(len(timestamps) * (train_fraction + validation_fraction)))
    validation_cut = min(validation_cut, len(timestamps) - 1)

    train_end = timestamps[train_cut - 1]
    validation_end = timestamps[validation_cut - 1]

    train = work.loc[work["timestamp"] <= train_end].copy()
    validation = work.loc[
        (work["timestamp"] > train_end) & (work["timestamp"] <= validation_end)
    ].copy()
    test = work.loc[work["timestamp"] > validation_end].copy()

    if train.empty or validation.empty or test.empty:
        raise DataContractError("temporal split produced an empty partition")

    return train, validation, test
