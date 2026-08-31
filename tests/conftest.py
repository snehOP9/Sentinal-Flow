from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression

from fraud_platform.api.app import create_app
from fraud_platform.api.service import FraudScoringService
from fraud_platform.config import Settings
from fraud_platform.database.repository import DecisionRepository
from fraud_platform.decisioning.policy import CostAssumptions, ThresholdPolicy
from fraud_platform.features.online_store import InMemoryFeatureStore
from fraud_platform.features.point_in_time import FEATURE_NAMES
from fraud_platform.models.bundle import ModelBundle


@pytest.fixture
def bundle() -> ModelBundle:
    rng = np.random.default_rng(9)
    x = pd.DataFrame(rng.normal(size=(80, len(FEATURE_NAMES))), columns=FEATURE_NAMES)
    y = np.array([0, 1] * 40)
    estimator = LogisticRegression(max_iter=500).fit(x, y)
    calibrator = CalibratedClassifierCV(FrozenEstimator(estimator), method="sigmoid").fit(x, y)
    policy = ThresholdPolicy(0.35, 0.70, CostAssumptions(), 100.0, 0.10)
    return ModelBundle(
        estimator=estimator,
        calibrator=calibrator,
        feature_baselines={name: 0.0 for name in FEATURE_NAMES},
        policy=policy,
        model_version="test-model",
        feature_version="pit-v1",
        dataset_fingerprint="test",
        trained_at=datetime.now(UTC).isoformat(),
        metrics={"test": {"pr_auc": 0.5}},
        validation_scores=[(0.1, 0), (0.9, 1), (0.5, 0), (0.8, 1)],
        reference_feature_samples={name: [0.0] * 10 for name in FEATURE_NAMES},
        reference_score_samples=[0.1] * 10,
    )


@pytest.fixture
def client(tmp_path, bundle: ModelBundle) -> TestClient:
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'api.db'}",
        model_path=tmp_path / "unused.joblib",
        cors_allowed_origins=["http://localhost:3000"],
        demo_auth_enabled=True,
        rate_limit_per_minute=500,
    )
    service = FraudScoringService(
        settings, DecisionRepository(settings.database_url), InMemoryFeatureStore(), bundle
    )
    with TestClient(create_app(settings, service)) as test_client:
        yield test_client
