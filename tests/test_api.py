from __future__ import annotations

from fraud_platform.config import Settings


def payload() -> dict[str, object]:
    return {
        "transaction_id": "transaction-0001",
        "customer_id": "customer-1",
        "card_id": "card-1",
        "merchant_id": "merchant-1",
        "merchant_category": "digital_goods",
        "amount": 220.0,
        "channel": "online",
        "location": "ONLINE",
        "timestamp": "2025-01-01T12:00:00Z",
    }


def test_score_persists_and_replays_idempotently(client) -> None:
    headers = {"X-Demo-Role": "analyst"}
    first = client.post("/api/v1/transactions/score", json=payload(), headers=headers)
    second = client.post("/api/v1/transactions/score", json=payload(), headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["idempotent_replay"] is False
    assert second.json()["idempotent_replay"] is True
    stored = client.get("/api/v1/transactions/transaction-0001", headers={"X-Demo-Role": "viewer"})
    assert stored.status_code == 200
    assert stored.json()["state_update_status"] == "applied"


def test_request_validation_and_role_protection(client) -> None:
    invalid = client.post(
        "/api/v1/transactions/score",
        json={**payload(), "amount": -1},
        headers={"X-Demo-Role": "analyst"},
    )
    forbidden = client.post(
        "/api/v1/transactions/score", json=payload(), headers={"X-Demo-Role": "viewer"}
    )
    assert invalid.status_code == 422
    assert forbidden.status_code == 403


def test_settings_accepts_comma_separated_cors_origins(monkeypatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    settings = Settings(_env_file=None)
    assert settings.cors_allowed_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_production_configuration_rejects_demo_authentication() -> None:
    import pytest

    with pytest.raises(ValueError, match="demo authentication"):
        Settings(environment="production", demo_auth_enabled=True, auth_mode="demo")


def test_idempotency_key_cannot_bind_two_payloads(client) -> None:
    headers = {"X-Demo-Role": "analyst", "Idempotency-Key": "test-idempotency-key"}
    first = client.post("/api/v1/transactions/score", json=payload(), headers=headers)
    conflict = client.post(
        "/api/v1/transactions/score", json={**payload(), "amount": 221}, headers=headers
    )
    assert first.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_case_action_creates_an_immutable_review_event(client) -> None:
    response = client.post(
        "/api/v1/transactions/score", json=payload(), headers={"X-Demo-Role": "analyst"}
    )
    assert response.status_code == 200
    queue = client.get("/api/v1/cases", headers={"X-Demo-Role": "reviewer"})
    assert queue.status_code == 200
    case_id = queue.json()["items"][0]["case_id"]
    action = client.post(
        f"/api/v1/cases/{case_id}/actions",
        json={"action": "approve", "reason_code": "ANALYST_REVIEW", "note": "Synthetic review."},
        headers={"X-Demo-Role": "reviewer"},
    )
    assert action.status_code == 200
    assert action.json()["status"] == "closed"
    assert action.json()["review_actions"][0]["advisory_only"] is True


def test_scoped_api_key_is_hashed_and_revocable(client) -> None:
    created = client.post(
        "/api/v1/api-keys",
        json={"name": "synthetic scorer", "permissions": ["transaction.score"]},
        headers={"X-Demo-Role": "tenant_admin"},
    )
    assert created.status_code == 201
    raw_key = created.json()["api_key"]
    metadata = created.json()["metadata"]
    scored = client.post(
        "/api/v1/transactions/score",
        json={**payload(), "transaction_id": "transaction-key-0002"},
        headers={"X-API-Key": raw_key},
    )
    assert scored.status_code == 200
    revoked = client.post(
        f"/api/v1/api-keys/{metadata['id']}/revoke", headers={"X-Demo-Role": "tenant_admin"}
    )
    assert revoked.status_code == 200
    rejected = client.post(
        "/api/v1/transactions/score",
        json={**payload(), "transaction_id": "transaction-key-0003"},
        headers={"X-API-Key": raw_key},
    )
    assert rejected.status_code == 401
