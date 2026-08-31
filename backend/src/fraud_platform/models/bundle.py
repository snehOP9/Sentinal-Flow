from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import joblib
import numpy as np
import pandas as pd

from fraud_platform.decisioning.policy import ThresholdPolicy
from fraud_platform.features.point_in_time import FEATURE_NAMES


@dataclass
class ModelBundle:
    """All artefacts necessary for a traceable, consistent online decision."""

    estimator: Any
    calibrator: Any
    feature_baselines: dict[str, float]
    policy: ThresholdPolicy
    model_version: str
    feature_version: str
    dataset_fingerprint: str
    trained_at: str
    metrics: dict[str, Any]
    validation_scores: list[tuple[float, int]]
    reference_feature_samples: dict[str, list[float]]
    reference_score_samples: list[float]

    def predict_proba(self, feature_row: dict[str, float]) -> float:
        matrix = pd.DataFrame(
            [[feature_row[name] for name in FEATURE_NAMES]], columns=FEATURE_NAMES
        )
        return float(self.calibrator.predict_proba(matrix)[:, 1][0])

    def explain(self, feature_row: dict[str, float], limit: int = 4) -> list[dict[str, object]]:
        """Fast local perturbation contributions, explicitly not causal claims.

        Only globally salient model features are perturbed; this keeps the request path
        bounded while retaining model-specific signals instead of a handcrafted reason.
        """
        baseline_probability = self.predict_proba(feature_row)
        contributions: list[tuple[str, float, float]] = []
        for name in self._salient_features(limit * 2):
            counterfactual = dict(feature_row)
            counterfactual[name] = self.feature_baselines.get(name, 0.0)
            delta = baseline_probability - self.predict_proba(counterfactual)
            contributions.append((name, delta, float(feature_row[name])))
        contributions.sort(key=lambda item: abs(item[1]), reverse=True)
        return [
            {
                "feature": name,
                "value": round(value, 4),
                "direction": "raises" if delta >= 0 else "lowers",
                "contribution": round(delta, 4),
                "label": _signal_label(name, value),
            }
            for name, delta, value in contributions[:limit]
        ]

    def _salient_features(self, count: int) -> list[str]:
        estimator = self.estimator
        if hasattr(estimator, "named_steps"):
            estimator = list(estimator.named_steps.values())[-1]
        importances = getattr(estimator, "feature_importances_", None)
        if importances is None:
            coefficients = getattr(estimator, "coef_", None)
            importances = np.abs(coefficients[0]) if coefficients is not None else None
        if importances is None:
            fallback = [
                "amount_to_customer_average",
                "customer_txn_count_1h",
                "customer_txn_count_24h",
                "amount_deviation_zscore",
                "high_risk_category",
                "new_merchant_for_customer",
                "amount",
                "channel_online",
            ]
            return fallback[:count]
        positions = np.argsort(np.asarray(importances))[-count:][::-1]
        return [FEATURE_NAMES[int(position)] for position in positions]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @classmethod
    def load(cls, path: Path) -> ModelBundle:
        return cast(ModelBundle, joblib.load(path))

    def write_metrics(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.metrics, indent=2), encoding="utf-8")


def _signal_label(name: str, value: float) -> str:
    labels = {
        "amount": f"Transaction amount: {value:.2f}",
        "amount_to_customer_average": f"Amount is {value:.1f}x the customer historical average",
        "customer_txn_count_1h": f"{value:.0f} prior customer transactions in the last hour",
        "customer_txn_count_24h": f"{value:.0f} prior customer transactions in the last 24 hours",
        "seconds_since_customer_previous_transaction": (
            f"{value:.0f} seconds since the prior customer transaction"
        ),
        "new_merchant_for_customer": "Merchant has not appeared in the available customer history",
        "high_risk_category": "Merchant category is in a configured higher-risk segment",
    }
    return labels.get(name, name.replace("_", " ").capitalize())
