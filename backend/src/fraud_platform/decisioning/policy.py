from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CostAssumptions:
    fraud_loss: float = 250.0
    false_decline_cost: float = 15.0
    review_cost: float = 4.0
    review_capture_rate: float = 0.72
    review_capacity_fraction: float = 0.15


@dataclass(frozen=True)
class ThresholdPolicy:
    allow_threshold: float
    block_threshold: float
    assumptions: CostAssumptions
    validation_expected_cost: float
    validation_review_rate: float

    def decide(self, probability: float) -> tuple[str, str]:
        if probability >= self.block_threshold:
            return "BLOCK", "Probability is above the validation-derived block threshold."
        if probability >= self.allow_threshold:
            return "REVIEW", "Probability falls inside the capacity-constrained review band."
        return "ALLOW", "Probability is below the validation-derived review threshold."

    def as_dict(self) -> dict[str, object]:
        return {
            "allow_threshold": self.allow_threshold,
            "block_threshold": self.block_threshold,
            "assumptions": asdict(self.assumptions),
            "validation_expected_cost": self.validation_expected_cost,
            "validation_review_rate": self.validation_review_rate,
        }


def expected_cost(
    labels: np.ndarray,
    probabilities: np.ndarray,
    allow_threshold: float,
    block_threshold: float,
    assumptions: CostAssumptions,
) -> tuple[float, float]:
    decisions = np.where(
        probabilities >= block_threshold,
        "BLOCK",
        np.where(probabilities >= allow_threshold, "REVIEW", "ALLOW"),
    )
    legitimate = labels == 0
    fraud = ~legitimate
    cost = 0.0
    cost += assumptions.false_decline_cost * np.sum((decisions == "BLOCK") & legitimate)
    cost += assumptions.review_cost * np.sum(decisions == "REVIEW")
    cost += assumptions.fraud_loss * np.sum((decisions == "ALLOW") & fraud)
    cost += (
        assumptions.fraud_loss
        * (1 - assumptions.review_capture_rate)
        * np.sum((decisions == "REVIEW") & fraud)
    )
    return float(cost), float(np.mean(decisions == "REVIEW"))


def optimize_thresholds(
    labels: pd.Series | np.ndarray,
    probabilities: np.ndarray,
    assumptions: CostAssumptions | None = None,
) -> ThresholdPolicy:
    """Choose a two-threshold policy on validation data, not an arbitrary probability."""
    assumptions = assumptions or CostAssumptions()
    y = np.asarray(labels, dtype=int)
    p = np.asarray(probabilities, dtype=float)
    candidates = np.unique(np.quantile(p, np.linspace(0.0, 1.0, 101)))
    best: tuple[float, float, float, float] | None = None
    for allow in candidates:
        for block in candidates:
            if block < allow:
                continue
            cost, review_rate = expected_cost(y, p, float(allow), float(block), assumptions)
            if review_rate > assumptions.review_capacity_fraction:
                continue
            candidate = (cost, float(allow), float(block), review_rate)
            if best is None or candidate[0] < best[0]:
                best = candidate
    if best is None:
        threshold = float(np.quantile(p, 1 - assumptions.review_capacity_fraction))
        cost, review_rate = expected_cost(y, p, threshold, threshold, assumptions)
        best = (cost, threshold, threshold, review_rate)
    return ThresholdPolicy(
        allow_threshold=best[1],
        block_threshold=best[2],
        assumptions=assumptions,
        validation_expected_cost=best[0],
        validation_review_rate=best[3],
    )
