from __future__ import annotations

import uuid

from fastapi import HTTPException

from fraud_platform.api.errors import Problem


def test_internal_problem_detail_and_fields_are_not_exposed(client):
    marker = "postgres://finance:secret@internal-db"
    path = f"/_regression/internal-{uuid.uuid4().hex}"

    def fail():
        raise Problem(
            503,
            "DEPENDENCY_FAILURE",
            "Dependency unavailable",
            marker,
            retryable=True,
            fields=[{"path": ["secret"], "message": marker}],
        )

    client.app.add_api_route(path, fail)
    response = client.get(path)
    assert response.status_code == 503
    assert response.json()["code"] == "DEPENDENCY_FAILURE"
    assert response.json()["retryable"] is True
    assert response.json()["request_id"]
    assert "fields" not in response.json()
    assert marker not in response.text


def test_http_exception_5xx_is_sanitized(client):
    marker = "token=do-not-return"
    path = f"/_regression/http-{uuid.uuid4().hex}"

    def fail():
        raise HTTPException(503, detail=marker)

    client.app.add_api_route(path, fail)
    response = client.get(path)
    assert response.status_code == 503
    assert marker not in response.text
    assert response.json()["request_id"]


def test_controlled_client_errors_keep_usable_details(client):
    path = f"/_regression/conflict-{uuid.uuid4().hex}"

    def fail():
        raise Problem(409, "CONFLICT", "Resource conflict", "Choose a different ID.")

    client.app.add_api_route(path, fail)
    response = client.get(path)
    assert response.status_code == 409
    assert response.json()["detail"] == "Choose a different ID."
