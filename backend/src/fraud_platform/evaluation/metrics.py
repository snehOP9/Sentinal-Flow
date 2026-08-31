from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)


def _json_numbers(values: np.ndarray) -> list[float | None]:
    """Metrics endpoints must remain standards-compliant JSON (no Infinity/NaN)."""
    return [float(value) if np.isfinite(value) else None for value in values]


def classification_metrics(
    labels: np.ndarray, probabilities: np.ndarray, threshold: float
) -> dict[str, Any]:
    predictions = probabilities >= threshold
    fpr, tpr, roc_thresholds = roc_curve(labels, probabilities)
    precision, recall, pr_thresholds = precision_recall_curve(labels, probabilities)
    matrix = confusion_matrix(labels, predictions, labels=[0, 1]).tolist()
    recall_at_1pct = float(max(tpr[fpr <= 0.01], default=0.0))
    precision_at_80_recall = float(max(precision[recall >= 0.80], default=0.0))
    top_k = max(1, int(len(labels) * 0.05))
    top_indices = np.argsort(probabilities)[-top_k:]
    calibration_true, calibration_pred = calibration_curve(
        labels, probabilities, n_bins=10, strategy="quantile"
    )
    return {
        "fraud_prevalence": float(np.mean(labels)),
        "pr_auc": float(average_precision_score(labels, probabilities)),
        "roc_auc": float(roc_auc_score(labels, probabilities)),
        "brier_score": float(brier_score_loss(labels, probabilities)),
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recall": float(recall_score(labels, predictions, zero_division=0)),
        "f1": float(
            2
            * precision_score(labels, predictions, zero_division=0)
            * recall_score(labels, predictions, zero_division=0)
            / max(
                precision_score(labels, predictions, zero_division=0)
                + recall_score(labels, predictions, zero_division=0),
                1e-12,
            )
        ),
        "recall_at_1pct_fpr": recall_at_1pct,
        "precision_at_80pct_recall": precision_at_80_recall,
        "top_5pct_precision": float(np.mean(labels[top_indices])),
        "confusion_matrix": matrix,
        "curves": {
            "roc": {
                "fpr": _json_numbers(fpr),
                "tpr": _json_numbers(tpr),
                "thresholds": _json_numbers(roc_thresholds),
            },
            "precision_recall": {
                "precision": _json_numbers(precision),
                "recall": _json_numbers(recall),
                "thresholds": _json_numbers(pr_thresholds),
            },
            "calibration": {
                "observed": _json_numbers(calibration_true),
                "predicted": _json_numbers(calibration_pred),
            },
        },
    }
