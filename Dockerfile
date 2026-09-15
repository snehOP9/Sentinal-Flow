FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY backend ./backend
COPY scripts ./scripts

RUN pip install --no-cache-dir --prefix=/install '.[training]'
RUN PYTHONPATH=/install/lib/python3.11/site-packages python scripts/generate_demo_transactions.py --output data/demo/transactions.csv \
    && PYTHONPATH=/install/lib/python3.11/site-packages python -m fraud_platform.training \
        --data data/demo/transactions.csv \
        --artifact artifacts/production/model_bundle.joblib \
        --metrics artifacts/production/metrics.json

FROM python:3.11-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 sentinel \
    && mkdir /mlartifacts \
    && chown sentinel:sentinel /mlartifacts

WORKDIR /app
COPY --from=builder /install /usr/local
COPY --from=builder /build/artifacts ./artifacts
COPY --from=builder /build/data/demo ./data/demo
COPY --from=builder /build/backend ./backend
COPY alembic.ini ./
COPY alembic ./alembic

USER sentinel
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/backend/src

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD curl --fail http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "fraud_platform.main:app", "--host", "0.0.0.0", "--port", "8000"]
