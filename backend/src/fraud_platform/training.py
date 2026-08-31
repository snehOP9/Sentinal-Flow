"""Reproducible temporal training and evaluation pipeline."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.calibration import CalibratedClassifierCV
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from fraud_platform.data.contracts import temporal_split, validate_transactions
from fraud_platform.decisioning.policy import optimize_thresholds
from fraud_platform.evaluation.metrics import classification_metrics
from fraud_platform.features.point_in_time import FEATURE_NAMES, build_offline_features
from fraud_platform.models.bundle import ModelBundle


def _git_commit() -> str:
    try:
        git = shutil.which("git")
        if git is None:
            return "unavailable"
        return subprocess.check_output([git, "rev-parse", "HEAD"], text=True).strip()  # noqa: S603
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def _candidate_models(seed: int, positive_weight: float) -> dict[str, Any]:
    return {
        "dummy_prior": DummyClassifier(strategy="prior"),
        "logistic_regression": make_pipeline(
            StandardScaler(),
            LogisticRegression(class_weight="balanced", max_iter=2_000, random_state=seed),
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=160,
            min_samples_leaf=4,
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=seed,
        ),
        "hist_gradient_boosting": HistGradientBoostingClassifier(
            max_iter=220, learning_rate=0.07, max_leaf_nodes=31, random_state=seed
        ),
        "lightgbm": LGBMClassifier(
            objective="binary",
            n_estimators=300,
            learning_rate=0.04,
            num_leaves=31,
            subsample=0.9,
            colsample_bytree=0.9,
            scale_pos_weight=positive_weight,
            random_state=seed,
            n_jobs=-1,
            verbosity=-1,
        ),
    }


def _fit_candidate(
    model: Any, name: str, x: pd.DataFrame, y: pd.Series, weights: np.ndarray
) -> Any:
    if name == "hist_gradient_boosting":
        model.fit(x, y, sample_weight=weights)
    else:
        model.fit(x, y)
    return model


def _calibrate(
    model: Any, x_validation: pd.DataFrame, y_validation: pd.Series
) -> tuple[Any, str, dict[str, float]]:
    raw = model.predict_proba(x_validation)[:, 1]
    candidates: list[tuple[str, Any, float]] = []
    for method in ("sigmoid", "isotonic"):
        # FrozenEstimator is the supported replacement for cv="prefit" in
        # scikit-learn 1.6+. It guarantees that validation labels calibrate a
        # model fitted only on the earlier training partition.
        calibrator = CalibratedClassifierCV(FrozenEstimator(model), method=method)
        calibrator.fit(x_validation, y_validation)
        probabilities = calibrator.predict_proba(x_validation)[:, 1]
        candidates.append(
            (method, calibrator, float(brier_score_loss(y_validation, probabilities)))
        )
    selected = min(candidates, key=lambda item: item[2])
    return (
        selected[1],
        selected[0],
        {
            "raw_brier": float(brier_score_loss(y_validation, raw)),
            "sigmoid_brier": next(score for method, _, score in candidates if method == "sigmoid"),
            "isotonic_brier": next(
                score for method, _, score in candidates if method == "isotonic"
            ),
        },
    )


def train(
    data_path: Path,
    artifact_path: Path,
    metrics_path: Path,
    seed: int = 20260830,
    tracking_uri: str | None = None,
) -> ModelBundle:
    frame = pd.read_csv(data_path)
    report = validate_transactions(frame)
    train_frame, validation_frame, test_frame = temporal_split(frame)
    all_features = build_offline_features(frame)
    x_train = all_features.loc[train_frame.index, FEATURE_NAMES]
    x_validation = all_features.loc[validation_frame.index, FEATURE_NAMES]
    x_test = all_features.loc[test_frame.index, FEATURE_NAMES]
    y_train = train_frame["is_fraud"].astype(int)
    y_validation = validation_frame["is_fraud"].astype(int)
    y_test = test_frame["is_fraud"].astype(int)
    positive_weight = max(1.0, float((y_train == 0).sum() / max((y_train == 1).sum(), 1)))
    weights = np.where(y_train.to_numpy() == 1, positive_weight, 1.0)

    comparison: dict[str, dict[str, float]] = {}
    fitted: dict[str, Any] = {}
    for name, candidate in _candidate_models(seed, positive_weight).items():
        fitted[name] = _fit_candidate(candidate, name, x_train, y_train, weights)
        probabilities = fitted[name].predict_proba(x_validation)[:, 1]
        comparison[name] = {
            "validation_pr_auc": float(average_precision_score(y_validation, probabilities)),
            "validation_brier": float(brier_score_loss(y_validation, probabilities)),
        }
    selected_name = max(comparison, key=lambda key: comparison[key]["validation_pr_auc"])
    calibrator, calibration_method, calibration_scores = _calibrate(
        fitted[selected_name], x_validation, y_validation
    )
    validation_probabilities = calibrator.predict_proba(x_validation)[:, 1]
    policy = optimize_thresholds(y_validation, validation_probabilities)
    start = time.perf_counter()
    test_probabilities = calibrator.predict_proba(x_test)[:, 1]
    latency_ms = (time.perf_counter() - start) * 1_000 / len(x_test)
    test_metrics = classification_metrics(
        y_test.to_numpy(), test_probabilities, policy.block_threshold
    )
    feature_importance = _feature_importance(fitted[selected_name])
    metrics: dict[str, Any] = {
        "dataset": report.__dict__,
        "git_commit": _git_commit(),
        "feature_version": "pit-v1",
        "split_boundaries": {
            "train": [str(train_frame.timestamp.min()), str(train_frame.timestamp.max())],
            "validation": [
                str(validation_frame.timestamp.min()),
                str(validation_frame.timestamp.max()),
            ],
            "test": [str(test_frame.timestamp.min()), str(test_frame.timestamp.max())],
        },
        "model_comparison": comparison,
        "selected_model": selected_name,
        "calibration": {"selected": calibration_method, **calibration_scores},
        "threshold_policy": policy.as_dict(),
        "feature_importance": feature_importance,
        "test": {**test_metrics, "mean_batch_inference_ms_per_transaction": latency_ms},
    }
    bundle = ModelBundle(
        estimator=fitted[selected_name],
        calibrator=calibrator,
        feature_baselines={name: float(x_train[name].median()) for name in FEATURE_NAMES},
        policy=policy,
        model_version=f"{selected_name}-{report.fingerprint[:12]}",
        feature_version="pit-v1",
        dataset_fingerprint=report.fingerprint,
        trained_at=datetime.now(UTC).isoformat(),
        metrics=metrics,
        validation_scores=[
            (float(probability), int(label))
            for probability, label in zip(validation_probabilities, y_validation, strict=True)
        ],
        reference_feature_samples={
            name: [float(value) for value in x_train[name].iloc[:2_000]] for name in FEATURE_NAMES
        },
        reference_score_samples=[float(value) for value in validation_probabilities],
    )
    bundle.save(artifact_path)
    bundle.write_metrics(metrics_path)
    _save_evaluation_plots(
        metrics, y_test.to_numpy(), test_probabilities, artifact_path.parent, feature_importance
    )
    _log_mlflow(metrics, bundle, artifact_path, metrics_path, tracking_uri)
    return bundle


def _feature_importance(estimator: Any) -> list[dict[str, float | str]]:
    """Return global model salience for governance, never a causal attribution."""
    base_estimator = estimator
    if hasattr(base_estimator, "named_steps"):
        base_estimator = list(base_estimator.named_steps.values())[-1]
    values = getattr(base_estimator, "feature_importances_", None)
    if values is None:
        coefficients = getattr(base_estimator, "coef_", None)
        values = (
            np.abs(coefficients[0]) if coefficients is not None else np.ones(len(FEATURE_NAMES))
        )
    ordered = np.argsort(np.asarray(values))[::-1]
    return [
        {"feature": FEATURE_NAMES[int(index)], "importance": float(values[int(index)])}
        for index in ordered
    ]


def _save_evaluation_plots(
    metrics: dict[str, Any],
    labels: np.ndarray,
    probabilities: np.ndarray,
    output_dir: Path,
    feature_importance: list[dict[str, float | str]],
) -> None:
    """Persist evaluation visuals alongside metrics; API/UI read the equivalent curve arrays."""
    import matplotlib.pyplot as plt

    plots_dir = output_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    curves = metrics["test"]["curves"]

    figure, axis = plt.subplots(figsize=(6, 4))
    axis.plot(curves["precision_recall"]["recall"], curves["precision_recall"]["precision"])
    axis.set(xlabel="Recall", ylabel="Precision", title="Precision–Recall curve")
    figure.tight_layout()
    figure.savefig(plots_dir / "precision_recall.png", dpi=140)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(6, 4))
    axis.plot(curves["roc"]["fpr"], curves["roc"]["tpr"])
    axis.plot([0, 1], [0, 1], linestyle="--", color="grey")
    axis.set(xlabel="False-positive rate", ylabel="True-positive rate", title="ROC curve")
    figure.tight_layout()
    figure.savefig(plots_dir / "roc.png", dpi=140)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(6, 4))
    axis.plot(curves["calibration"]["predicted"], curves["calibration"]["observed"], marker="o")
    axis.plot([0, 1], [0, 1], linestyle="--", color="grey")
    axis.set(xlabel="Mean predicted probability", ylabel="Observed fraud rate", title="Calibration")
    figure.tight_layout()
    figure.savefig(plots_dir / "calibration.png", dpi=140)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(6, 4))
    axis.hist(probabilities[labels == 0], bins=25, alpha=0.7, label="legitimate")
    axis.hist(probabilities[labels == 1], bins=25, alpha=0.7, label="fraud")
    axis.set(xlabel="Calibrated probability", ylabel="Transactions", title="Score distribution")
    axis.legend()
    figure.tight_layout()
    figure.savefig(plots_dir / "score_distribution.png", dpi=140)
    plt.close(figure)

    confusion = np.asarray(metrics["test"]["confusion_matrix"])
    figure, axis = plt.subplots(figsize=(5, 4))
    image = axis.imshow(confusion, cmap="Blues")
    axis.set(
        xticks=[0, 1],
        yticks=[0, 1],
        xticklabels=["Predicted legitimate", "Predicted fraud"],
        yticklabels=["Actual legitimate", "Actual fraud"],
        title="Confusion matrix at block threshold",
    )
    for row, column in np.ndindex(confusion.shape):
        axis.text(column, row, str(confusion[row, column]), ha="center", va="center")
    figure.colorbar(image, ax=axis)
    figure.tight_layout()
    figure.savefig(plots_dir / "confusion_matrix.png", dpi=140)
    plt.close(figure)

    thresholds = np.linspace(0, 1, 101)
    precision = [
        float(((probabilities >= threshold) & (labels == 1)).sum())
        / max(int((probabilities >= threshold).sum()), 1)
        for threshold in thresholds
    ]
    recall = [
        float(((probabilities >= threshold) & (labels == 1)).sum())
        / max(int((labels == 1).sum()), 1)
        for threshold in thresholds
    ]
    figure, axis = plt.subplots(figsize=(6, 4))
    axis.plot(thresholds, precision, label="Precision")
    axis.plot(thresholds, recall, label="Recall")
    axis.axvline(metrics["threshold_policy"]["block_threshold"], color="grey", linestyle="--")
    axis.set(xlabel="Block threshold", ylabel="Metric", title="Threshold trade-off")
    axis.legend()
    figure.tight_layout()
    figure.savefig(plots_dir / "threshold_tradeoff.png", dpi=140)
    plt.close(figure)

    top = feature_importance[:12][::-1]
    figure, axis = plt.subplots(figsize=(7, 5))
    axis.barh([str(item["feature"]) for item in top], [float(item["importance"]) for item in top])
    axis.set(xlabel="Model salience", title="Global feature importance (not causal)")
    figure.tight_layout()
    figure.savefig(plots_dir / "feature_importance.png", dpi=140)
    plt.close(figure)


def _log_mlflow(
    metrics: dict[str, Any],
    bundle: ModelBundle,
    artifact_path: Path,
    metrics_path: Path,
    tracking_uri: str | None,
) -> None:
    try:
        import mlflow

        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment("sentinelflow-temporal-fraud")
        with mlflow.start_run(run_name=bundle.model_version):
            mlflow.set_tags(
                {
                    "model_stage": "candidate",
                    "dataset_fingerprint": bundle.dataset_fingerprint,
                    "feature_version": bundle.feature_version,
                }
            )
            mlflow.log_params(
                {
                    "model": metrics["selected_model"],
                    "feature_version": bundle.feature_version,
                    "dataset_fingerprint": bundle.dataset_fingerprint,
                    "git_commit": metrics["git_commit"],
                    "calibration": metrics["calibration"]["selected"],
                    "allow_threshold": metrics["threshold_policy"]["allow_threshold"],
                    "block_threshold": metrics["threshold_policy"]["block_threshold"],
                }
            )
            mlflow.log_metrics(
                {
                    "test_pr_auc": metrics["test"]["pr_auc"],
                    "test_roc_auc": metrics["test"]["roc_auc"],
                    "test_brier": metrics["test"]["brier_score"],
                }
            )
            mlflow.log_artifact(str(artifact_path), artifact_path="model")
            mlflow.log_artifact(str(metrics_path), artifact_path="evaluation")
            plots_dir = artifact_path.parent / "plots"
            if plots_dir.exists():
                mlflow.log_artifacts(str(plots_dir), artifact_path="evaluation/plots")
    except Exception as exc:  # Tracking must not make local reproducibility fail.
        print(f"MLflow logging skipped: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/demo/transactions.csv"))
    parser.add_argument(
        "--artifact", type=Path, default=Path("artifacts/production/model_bundle.joblib")
    )
    parser.add_argument("--metrics", type=Path, default=Path("artifacts/production/metrics.json"))
    parser.add_argument("--seed", type=int, default=20260830)
    parser.add_argument("--tracking-uri", default=os.getenv("MLFLOW_TRACKING_URI"))
    args = parser.parse_args()
    bundle = train(args.data, args.artifact, args.metrics, args.seed, args.tracking_uri)
    print(
        json.dumps(
            {"model_version": bundle.model_version, "metrics": bundle.metrics["test"]}, indent=2
        )
    )


if __name__ == "__main__":
    main()
