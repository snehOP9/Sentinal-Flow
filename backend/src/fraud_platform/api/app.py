from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import numpy as np
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from fraud_platform.api.errors import Problem
from fraud_platform.api.schemas import (
    ApiKeyCreateRequest,
    CaseActionRequest,
    HealthResponse,
    OutcomeRequest,
    ScoreResponse,
    ThresholdSimulationRequest,
    TransactionRequest,
)
from fraud_platform.api.service import FraudScoringService
from fraud_platform.auth.permissions import Permission, Principal
from fraud_platform.auth.service import AuthenticationError, AuthenticationService
from fraud_platform.config import Settings, get_settings
from fraud_platform.database.repository import (
    ExternalTransactionConflictError,
    IdempotencyConflictError,
)
from fraud_platform.decisioning.policy import CostAssumptions, expected_cost, optimize_thresholds
from fraud_platform.evaluation.metrics import classification_metrics
from fraud_platform.monitoring.drift import population_stability_index
from fraud_platform.observability.logging import configure_structured_logging

logger = logging.getLogger("sentinelflow.api")
REQUESTS = Counter(
    "sentinelflow_http_requests_total", "HTTP requests", ["method", "path", "status"]
)
DECISIONS = Counter("sentinelflow_decisions_total", "Model recommendations", ["decision"])
LATENCY = Histogram("sentinelflow_score_latency_seconds", "End-to-end scoring latency")


class SlidingRateLimiter:
    """Development fallback only; production should enforce distributed limits at gateway/Redis."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.events: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        recent = [event for event in self.events.get(key, []) if now - event < 60]
        self.events[key] = recent
        if len(recent) >= self.limit:
            return False
        recent.append(now)
        return True


def create_app(
    settings: Settings | None = None, service: FraudScoringService | None = None
) -> FastAPI:
    runtime_settings = settings or get_settings()
    configure_structured_logging(runtime_settings.log_level)
    runtime_service = service or FraudScoringService.from_settings(runtime_settings)
    auth = AuthenticationService(runtime_settings, runtime_service.repository)
    limiter = SlidingRateLimiter(runtime_settings.rate_limit_per_minute)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await runtime_service.start()
        yield
        await runtime_service.close()

    app = FastAPI(
        title="SentinelFlow API",
        version="0.2.0",
        description=(
            "Tenant-aware, synthetic-data fraud-risk intelligence API. Scores are "
            "probabilities and policy recommendations, never proof of fraud or payment actions."
        ),
        lifespan=lifespan,
    )
    app.state.settings = runtime_settings
    app.state.service = runtime_service
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime_settings.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-API-Key",
            "Idempotency-Key",
            "X-Request-ID",
            "X-Demo-Role",
        ],
    )

    def problem_response(problem: Problem, request_id: str) -> JSONResponse:
        payload: dict[str, Any] = {
            "type": f"https://sentinelflow.local/errors/{problem.code}",
            "code": problem.code,
            "title": problem.title,
            "detail": str(problem.detail),
            "status": problem.status_code,
            "request_id": request_id,
            "retryable": problem.retryable,
        }
        if problem.fields:
            payload["fields"] = problem.fields
        return JSONResponse(
            status_code=problem.status_code, content=payload, headers=problem.headers
        )

    @app.exception_handler(Problem)
    async def problem_handler(request: Request, exc: Problem) -> JSONResponse:
        return problem_response(exc, getattr(request.state, "request_id", "unknown"))

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return problem_response(
            Problem(
                422,
                "VALIDATION_ERROR",
                "Request validation failed",
                "One or more request fields are invalid.",
                fields=[
                    {"path": list(error["loc"]), "message": error["msg"]} for error in exc.errors()
                ],
            ),
            getattr(request.state, "request_id", "unknown"),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return problem_response(
            Problem(
                exc.status_code,
                "HTTP_ERROR",
                "Request failed",
                str(exc.detail),
                retryable=exc.status_code >= 500,
                headers=dict(exc.headers) if exc.headers else None,
            ),
            getattr(request.state, "request_id", "unknown"),
        )

    @app.middleware("http")
    async def security_and_observability(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        if (
            request.method == "POST"
            and int(request.headers.get("content-length", "0") or 0)
            > runtime_settings.request_max_bytes
        ):
            return problem_response(
                Problem(413, "REQUEST_TOO_LARGE", "Request body too large", "Reduce request size."),
                request_id,
            )
        client = request.client.host if request.client else "unknown"
        if request.url.path.startswith("/api/") and not limiter.allow(
            f"{client}:{request.url.path}"
        ):
            return problem_response(
                Problem(
                    429,
                    "RATE_LIMITED",
                    "Rate limit exceeded",
                    "Retry after one minute.",
                    retryable=True,
                    headers={"Retry-After": "60"},
                ),
                request_id,
            )
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("Unhandled request error", extra={"request_id": request_id})
            response = problem_response(
                Problem(
                    500, "INTERNAL_ERROR", "Internal server error", "An unexpected error occurred."
                ),
                request_id,
            )
        elapsed = (time.perf_counter() - started) * 1_000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        response.headers["Cache-Control"] = "no-store"
        if runtime_settings.environment in {"staging", "production"}:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        REQUESTS.labels(request.method, request.url.path, response.status_code).inc()
        logger.info(
            "request_complete",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "status": response.status_code,
                "latency_ms": round(elapsed, 2),
            },
        )
        return response

    def require_permission(permission: Permission) -> Callable[[Request], Awaitable[Principal]]:
        async def dependency(request: Request) -> Principal:
            try:
                principal = await auth.authenticate(request)
            except AuthenticationError as exc:
                raise Problem(
                    401, "AUTHENTICATION_REQUIRED", "Authentication required", str(exc)
                ) from exc
            if not principal.allows(permission):
                raise Problem(
                    403,
                    "PERMISSION_DENIED",
                    "Permission denied",
                    f"The authenticated principal lacks {permission.value}.",
                )
            return principal

        return dependency

    monitoring_reader = Depends(require_permission(Permission.MONITORING_READ))
    transaction_scorer = Depends(require_permission(Permission.TRANSACTION_SCORE))
    transaction_reader = Depends(require_permission(Permission.TRANSACTION_READ))
    outcome_writer = Depends(require_permission(Permission.OUTCOME_WRITE))
    case_reader = Depends(require_permission(Permission.CASE_READ))
    case_decider = Depends(require_permission(Permission.CASE_DECIDE))
    model_reader = Depends(require_permission(Permission.MODEL_READ))
    policy_reader = Depends(require_permission(Permission.POLICY_READ))
    integration_manager = Depends(require_permission(Permission.INTEGRATION_MANAGE))

    @app.get("/api/v1/health", response_model=HealthResponse, tags=["operations"])
    async def health() -> dict[str, Any]:
        checks = await runtime_service.healthy()
        return {"status": "ok" if all(checks.values()) else "degraded", "checks": checks}

    @app.get("/api/v1/ready", response_model=HealthResponse, tags=["operations"])
    async def ready() -> Response | dict[str, Any]:
        checks = await runtime_service.healthy()
        if not all(checks.values()):
            return JSONResponse(status_code=503, content={"status": "degraded", "checks": checks})
        return {"status": "ok", "checks": checks}

    @app.get("/metrics", include_in_schema=False)
    async def metrics(_: Principal = monitoring_reader) -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.post(
        "/api/v1/transactions/score",
        response_model=ScoreResponse,
        tags=["transactions"],
        summary="Score one tokenised synthetic transaction",
    )
    async def score_transaction(
        payload: TransactionRequest,
        request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=255),
        principal: Principal = transaction_scorer,
    ) -> dict[str, Any]:
        try:
            with LATENCY.time():
                record, created = await runtime_service.score(
                    payload.model_dump(by_alias=True),
                    principal,
                    idempotency_key=idempotency_key,
                    request_id=request.state.request_id,
                )
        except IdempotencyConflictError as exc:
            raise Problem(409, "IDEMPOTENCY_CONFLICT", "Idempotency conflict", str(exc)) from exc
        except ExternalTransactionConflictError as exc:
            raise Problem(
                409, "EXTERNAL_TRANSACTION_CONFLICT", "Transaction correction required", str(exc)
            ) from exc
        except RuntimeError as exc:
            raise Problem(
                503,
                "SCORING_DEPENDENCY_UNAVAILABLE",
                "Scoring dependency unavailable",
                str(exc),
                retryable=True,
            ) from exc
        if created:
            DECISIONS.labels(record["decision"]).inc()
        return runtime_service.response(record, idempotent_replay=not created)

    @app.get("/api/v1/transactions/{transaction_id}", tags=["transactions"])
    async def get_transaction(
        transaction_id: str,
        principal: Principal = transaction_reader,
    ) -> dict[str, Any]:
        record = await runtime_service.repository.get(principal.organization_id, transaction_id)
        if not record:
            raise Problem(
                404,
                "TRANSACTION_NOT_FOUND",
                "Transaction not found",
                "No transaction exists in this organization.",
            )
        return record

    @app.get("/api/v1/transactions", tags=["transactions"])
    async def list_transactions(
        limit: int = 50,
        offset: int = 0,
        decision: str | None = None,
        search: str | None = None,
        principal: Principal = transaction_reader,
    ) -> dict[str, Any]:
        if not 1 <= limit <= 100 or offset < 0:
            raise Problem(
                422,
                "INVALID_PAGINATION",
                "Invalid pagination",
                "limit must be 1..100 and offset non-negative",
            )
        if decision and decision not in {"ALLOW", "REVIEW", "BLOCK"}:
            raise Problem(
                422,
                "INVALID_FILTER",
                "Invalid decision filter",
                "decision must be ALLOW, REVIEW, or BLOCK",
            )
        records, total = await runtime_service.repository.list(
            principal.organization_id, limit, offset, decision, search
        )
        return {"items": records, "total": total, "limit": limit, "offset": offset}

    @app.post("/api/v1/outcomes", tags=["outcomes"])
    async def record_outcome(
        payload: OutcomeRequest,
        principal: Principal = outcome_writer,
    ) -> dict[str, Any]:
        try:
            record = await runtime_service.repository.record_outcome(
                principal.organization_id,
                payload.transaction_id,
                payload.confirmed_fraud,
                payload.source,
                principal.subject,
            )
        except ExternalTransactionConflictError as exc:
            raise Problem(
                409, "OUTCOME_CORRECTION_REQUIRED", "Outcome correction required", str(exc)
            ) from exc
        if not record:
            raise Problem(
                404,
                "TRANSACTION_NOT_FOUND",
                "Transaction not found",
                "No transaction exists in this organization.",
            )
        return record

    @app.post("/api/v1/api-keys", tags=["integrations"], status_code=201)
    async def create_api_key(
        payload: ApiKeyCreateRequest,
        principal: Principal = integration_manager,
    ) -> dict[str, Any]:
        try:
            permissions = [Permission(value).value for value in payload.permissions]
        except ValueError as exc:
            raise Problem(
                422,
                "INVALID_API_KEY_SCOPE",
                "Invalid API key scope",
                "Each scope must be a documented SentinelFlow permission.",
            ) from exc
        if not set(Permission(scope) for scope in permissions).issubset(principal.permissions):
            raise Problem(
                403,
                "API_KEY_SCOPE_ESCALATION",
                "Permission denied",
                "An API key cannot be granted a permission its creator does not hold.",
            )
        metadata, raw_key = await runtime_service.repository.create_api_key(
            principal.organization_id,
            name=payload.name,
            permissions=permissions,
            expires_at=payload.expires_at,
            actor_id=principal.subject,
        )
        return {
            "api_key": raw_key,
            "metadata": metadata,
            "warning": "Copy this API key now. Its raw value is never stored or shown again.",
        }

    @app.post("/api/v1/api-keys/{api_key_id}/revoke", tags=["integrations"])
    async def revoke_api_key(
        api_key_id: str,
        principal: Principal = integration_manager,
    ) -> dict[str, bool]:
        revoked = await runtime_service.repository.revoke_api_key(
            principal.organization_id, api_key_id, principal.subject
        )
        if not revoked:
            raise Problem(404, "API_KEY_NOT_FOUND", "API key not found", "No API key exists here.")
        return {"revoked": True}

    @app.get("/api/v1/cases", tags=["cases"])
    async def list_cases(
        limit: int = 50,
        status_filter: str | None = None,
        queue: str | None = None,
        principal: Principal = case_reader,
    ) -> dict[str, Any]:
        if not 1 <= limit <= 100:
            raise Problem(422, "INVALID_PAGINATION", "Invalid pagination", "limit must be 1..100")
        return {
            "items": await runtime_service.repository.list_cases(
                principal.organization_id, limit, status_filter, queue
            )
        }

    @app.get("/api/v1/cases/{case_id}", tags=["cases"])
    async def get_case(
        case_id: str,
        principal: Principal = case_reader,
    ) -> dict[str, Any]:
        result = await runtime_service.repository.case_detail(principal.organization_id, case_id)
        if result is None:
            raise Problem(
                404, "CASE_NOT_FOUND", "Case not found", "No case exists in this organization."
            )
        return result

    @app.post("/api/v1/cases/{case_id}/actions", tags=["cases"])
    async def record_case_action(
        case_id: str,
        payload: CaseActionRequest,
        principal: Principal = case_decider,
    ) -> dict[str, Any]:
        result = await runtime_service.repository.record_review_action(
            principal.organization_id,
            case_id,
            action=payload.action,
            reason_code=payload.reason_code,
            note=payload.note,
            actor_id=principal.subject,
        )
        if result is None:
            raise Problem(
                404, "CASE_NOT_FOUND", "Case not found", "No case exists in this organization."
            )
        return result

    @app.get("/api/v1/dashboard/summary", tags=["dashboard"])
    async def dashboard_summary(
        principal: Principal = transaction_reader,
    ) -> dict[str, Any]:
        return await runtime_service.repository.summary(principal.organization_id)

    @app.get("/api/v1/dashboard/timeseries", tags=["dashboard"])
    async def dashboard_timeseries(
        days: int = 14,
        principal: Principal = transaction_reader,
    ) -> list[dict[str, Any]]:
        if not 1 <= days <= 90:
            raise Problem(422, "INVALID_RANGE", "Invalid range", "days must be 1..90")
        return await runtime_service.repository.timeseries(principal.organization_id, days)

    @app.get("/api/v1/model/info", tags=["model"])
    async def model_info(
        _: Principal = model_reader,
    ) -> dict[str, Any]:
        bundle = runtime_service.bundle
        if bundle is None:
            raise Problem(
                503,
                "MODEL_UNAVAILABLE",
                "Model unavailable",
                "No approved model release is loaded.",
                retryable=True,
            )
        return {
            "model_version": bundle.model_version,
            "feature_version": bundle.feature_version,
            "dataset_fingerprint": bundle.dataset_fingerprint,
            "trained_at": bundle.trained_at,
            "threshold_policy": bundle.policy.as_dict(),
            "release_status": "demo_active",
            "limitation": (
                "A model release registry and independent approval workflow remain planned."
            ),
        }

    @app.get("/api/v1/model/metrics", tags=["model"])
    async def model_metrics(
        _: Principal = model_reader,
    ) -> dict[str, Any]:
        if runtime_service.bundle is None:
            raise Problem(
                503,
                "MODEL_UNAVAILABLE",
                "Model unavailable",
                "No approved model release is loaded.",
                retryable=True,
            )
        return runtime_service.bundle.metrics

    @app.post("/api/v1/decisioning/simulate", tags=["decisioning"])
    async def simulate_thresholds(
        payload: ThresholdSimulationRequest,
        _: Principal = policy_reader,
    ) -> dict[str, Any]:
        bundle = runtime_service.bundle
        if bundle is None or not bundle.validation_scores:
            raise Problem(
                503,
                "VALIDATION_ARTIFACT_UNAVAILABLE",
                "Validation artifact unavailable",
                "No validation artifact is loaded.",
                retryable=True,
            )
        assumptions = CostAssumptions(**payload.model_dump())
        probabilities = np.array([score for score, _ in bundle.validation_scores])
        labels = np.array([label for _, label in bundle.validation_scores])
        policy = optimize_thresholds(labels, probabilities, assumptions)
        cost, review_rate = expected_cost(
            labels, probabilities, policy.allow_threshold, policy.block_threshold, assumptions
        )
        stats = classification_metrics(labels, probabilities, policy.block_threshold)
        return {
            "policy": policy.as_dict(),
            "expected_cost": cost,
            "review_rate": review_rate,
            "fraud_capture": stats["recall"],
            "false_positive_rate": stats["confusion_matrix"][0][1]
            / max(sum(stats["confusion_matrix"][0]), 1),
            "transactions_reviewed": int(review_rate * len(labels)),
            "context": (
                "Synthetic validation scenario estimate; not booked loss prevention or "
                "production policy performance."
            ),
        }

    @app.get("/api/v1/monitoring", tags=["monitoring"])
    async def monitoring(
        principal: Principal = monitoring_reader,
    ) -> dict[str, Any]:
        bundle = runtime_service.bundle
        if bundle is None:
            raise Problem(
                503,
                "MODEL_UNAVAILABLE",
                "Model unavailable",
                "No approved model release is loaded.",
                retryable=True,
            )
        observations, scores = await runtime_service.repository.recent_observations(
            principal.organization_id
        )
        feature_psi = {
            name: population_stability_index(
                bundle.reference_feature_samples.get(name, []),
                [float(observation.get(name, 0.0)) for observation in observations],
            )
            for name in bundle.reference_feature_samples
        }
        score_psi = population_stability_index(bundle.reference_score_samples, scores)
        alerts = [name for name, value in feature_psi.items() if value is not None and value >= 0.2]
        if score_psi is not None and score_psi >= 0.2:
            alerts.append("prediction_score")
        dependencies = await runtime_service.healthy()
        return {
            "status": "alert" if alerts else "normal",
            "sample_size": len(observations),
            "prediction_score_psi": score_psi,
            "feature_psi": feature_psi,
            "alerts": alerts,
            "dependencies": dependencies,
            "outbox": await runtime_service.repository.outbox_health(principal.organization_id),
            "message": (
                "Label-based performance is withheld until mature delayed outcomes exist; "
                "PSI is a synthetic-data distribution signal."
            ),
        }

    return app


app = create_app()
