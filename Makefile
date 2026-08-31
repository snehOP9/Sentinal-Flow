.PHONY: setup generate-demo train test lint format up down benchmark migrate openapi outbox-once

setup:
	python -m pip install -e ".[dev]"

generate-demo:
	python scripts/generate_demo_transactions.py

train: generate-demo
	python -m fraud_platform.training

migrate:
	alembic upgrade head

openapi:
	python scripts/export_openapi.py

outbox-once:
	python -m fraud_platform.workers.outbox --once

test:
	pytest -q

lint:
	ruff check backend/src tests scripts
	ruff format --check backend/src tests scripts

format:
	ruff check --fix backend/src tests scripts
	ruff format backend/src tests scripts

up:
	docker compose up --build

down:
	docker compose down

benchmark:
	python scripts/benchmark_api.py
