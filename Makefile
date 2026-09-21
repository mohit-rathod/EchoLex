SHELL := /bin/bash

.PHONY: setup infra-up infra-down observability-up health ingest run test lint check clean

setup:
	cp -n .env.example .env || true
	uv sync --frozen --dev

infra-up:
	docker compose up -d

infra-down:
	docker compose down

observability-up:
	docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d

health:
	uv run echolex-health

ingest:
	@test -n "$(PDF)" || (echo "Usage: make ingest PDF=data/documents/file.pdf" && exit 1)
	uv run echolex-ingest "$(PDF)" --recreate

run:
	uv run echolex-bot -t webrtc

test:
	uv run pytest -q

lint:
	uv run ruff check src tests

check: lint test

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist htmlcov .coverage
	find src tests -type d -name __pycache__ -prune -exec rm -rf {} +
