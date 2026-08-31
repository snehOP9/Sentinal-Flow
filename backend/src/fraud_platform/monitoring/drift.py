from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def population_stability_index(
    reference: Sequence[float], observed: Sequence[float], bins: int = 10
) -> float | None:
    """PSI for numeric feature/score drift; return None without enough observations."""
    baseline = np.asarray(reference, dtype=float)
    current = np.asarray(observed, dtype=float)
    if len(baseline) < bins or len(current) < bins:
        return None
    edges = np.unique(np.quantile(baseline, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0
    baseline_counts, _ = np.histogram(baseline, bins=edges)
    current_counts, _ = np.histogram(current, bins=edges)
    epsilon = 1e-6
    baseline_share = baseline_counts / max(baseline_counts.sum(), 1) + epsilon
    current_share = current_counts / max(current_counts.sum(), 1) + epsilon
    return float(np.sum((current_share - baseline_share) * np.log(current_share / baseline_share)))
