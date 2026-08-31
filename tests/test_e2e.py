from __future__ import annotations


def test_e2e_score_dashboard_and_threshold_simulator(client) -> None:
    headers = {"X-Demo-Role": "analyst"}
    response = client.post(
        "/api/v1/transactions/score",
        json={
            "transaction_id": "transaction-9999",
            "customer_id": "customer-e2e",
            "card_id": "card-e2e",
            "merchant_id": "merchant-e2e",
            "merchant_category": "gambling",
            "amount": 730.0,
            "channel": "online",
            "location": "ONLINE",
            "timestamp": "2025-01-01T12:00:00Z",
        },
        headers=headers,
    )
    assert response.status_code == 200
    assert (
        client.get("/api/v1/dashboard/summary", headers={"X-Demo-Role": "viewer"}).status_code
        == 200
    )
    simulation = client.post(
        "/api/v1/decisioning/simulate",
        json={
            "fraud_loss": 300,
            "false_decline_cost": 12,
            "review_cost": 3,
            "review_capacity_fraction": 0.5,
        },
        headers=headers,
    )
    assert simulation.status_code == 200
    assert (
        simulation.json()["policy"]["allow_threshold"]
        <= simulation.json()["policy"]["block_threshold"]
    )
    outcome = client.post(
        "/api/v1/outcomes",
        json={"transaction_id": "transaction-9999", "confirmed_fraud": True},
        headers=headers,
    )
    assert outcome.status_code == 200
    assert outcome.json()["confirmed_fraud"] is True
    monitoring = client.get("/api/v1/monitoring", headers={"X-Demo-Role": "viewer"})
    assert monitoring.status_code == 200
    assert monitoring.json()["message"].startswith("Label-based performance")
