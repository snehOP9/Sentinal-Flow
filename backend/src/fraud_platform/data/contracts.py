"""Input validation and leakage-safe temporal dataset splitting."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

import pandas as pd


REQUIRED_COLUMNS = {
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
}


class DataContractError(ValueError):
    """Raised when a transaction frame violates the training data contract."""


@dataclass(frozen=True)
class DataValidationReport:
    rows: int
    columns: int
    fraud_rows: int
    fraud_rate: float
    min_timestamp: str
    max_timestamp: str
    fingerprint: str


def validate_transactions(frame: pd.DataFrame) -> DataValidationReport:
    """Validate the schema and basic invariants required by the training pipeline."""
    missing = sorted(REQUIRED_COLUMNS.difference(frame.columns))
    if missing:
        raise DataContractError(f"missing required columns: {missing}")
    if frame.empty:
        raise DataContractError("transaction dataset must not be empty")
    if frame["transaction_id"].isna().any() or not frame["transaction_id"].is_unique:
        raise DataContractError("transaction_id must be unique and non-null")
    timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    if timestamps.isna().any():
        raise DataContractError("timestamp contains invalid or missing values")
    amounts = pd.to_numeric(frame["amount"], errors="coerce")
    if amounts.isna().any() or (~amounts.ge(0)).any():
        raise DataContractError("amount must contain finite non-negative values")
    if not amounts.map(pd.api.types.is_number).all():
        raise DataContractError("amount must contain numeric values")
    labels = pd.to_numeric(frame["is_fraud"], errors="coerce")
    if labels.isna().any() or not labels.isin([0, 1]).all():
        raise DataContractError("is_fraud must contain only 0 or 1")
    for column in ("customer_id", "card_id", "merchant_id"):
        if frame[column].isna().any():
            raise DataContractError(f"{column} must not contain missing values")
    canonical = frame.sort_values("transaction_id", kind="stable").copy()
    canonical["timestamp"] = timestamps.loc[canonical.index].astype(str)
    fingerprint = sha256(canonical.to_csv(index=False).encode("utf-8")).hexdigest()
    fraud_rows = int(labels.sum())
    return DataValidationReport(
        rows=len(frame),
        columns=len(frame.columns),
        fraud_rows=fraud_rows,
        fraud_rate=fraud_rows / len(frame),
        min_timestamp=str(timestamps.min()),
        max_timestamp=str(timestamps.max()),
        fingerprint=fingerprint,
    )


def temporal_split(
    frame: pd.DataFrame,
    train_fraction: float = 0.6,
    validation_fraction: float = 0.2,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split chronologically while keeping identical timestamps in one partition."""
    if not 0 < train_fraction < 1:
        raise ValueError("train_fraction must be between 0 and 1")
    if not 0 < validation_fraction < 1 or train_fraction + validation_fraction >= 1:
        raise ValueError("validation_fraction must leave room for the test partition")
    if frame.empty:
        raise DataContractError("cannot split an empty dataset")
    work = frame.copy()
    work["timestamp"] = pd.to_datetime(work["timestamp"], utc=True, errors="coerce")
    if work["timestamp"].isna().any():
        raise DataContractError("timestamp contains invalid or missing values")
    timestamps = work["timestamp"].drop_duplicates().sort_values().tolist()
    if len(timestamps) < 3:
        raise DataContractError("at least three distinct timestamps are required")
    train_end = max(1, min(len(timestamps) - 2, int(len(timestamps) * train_fraction)))
    validation_size = max(1, int(len(timestamps) * validation_fraction))
    validation_end = min(len(timestamps) - 1, train_end + validation_size)
    train_times = set(timestamps[:train_end])
    validation_times = set(timestamps[train_end:validation_end])
    test_times = set(timestamps[validation_end:])
    train = frame.loc[work["timestamp"].isin(train_times)].copy()
    validation = frame.loc[work["timestamp"].isin(validation_times)].copy()
    test = frame.loc[work["timestamp"].isin(test_times)].copy()
    if train.empty or validation.empty or test.empty:
        raise DataContractError("temporal split produced an empty partition")
    return train, validation, test
