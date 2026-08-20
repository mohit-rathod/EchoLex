SHELL := /bin/bash

.PHONY: setup infra-up infra-down health ingest run test lint

setup:
	cp -n .env.example .env || true
	uv sync --dev

infra-up:
	docker compose up -d

infra-down:
	docker compose down

health:
	uv run echolex-health

ingest:
	@test -n "$(PDF)" || (echo "Usage: make ingest PDF=data/documents/file.pdf" && exit 1)
	uv run echolex-ingest "$(PDF)" --recreate

run:
	uv run python -m echolex.bot -t webrtc

test:
	uv run pytest -q

lint:
	uv run ruff check src tests
