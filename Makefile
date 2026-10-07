.DEFAULT_GOAL := help
BACKEND := backend

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

install: ## Install backend dependencies (requires uv)
	cd $(BACKEND) && uv sync

up: ## Start the full stack with Docker Compose
	docker compose up -d --build

down: ## Stop the stack
	docker compose down

dev: ## Run the API locally with auto-reload
	cd $(BACKEND) && uv run uvicorn app.main:app --reload

test: ## Run unit tests
	cd $(BACKEND) && uv run pytest -m "not integration"

test-integration: ## Run integration tests (needs Neo4j + PostgreSQL running)
	cd $(BACKEND) && uv run pytest -m integration

lint: ## Lint, format-check and type-check
	cd $(BACKEND) && uv run ruff check . && uv run ruff format --check . && uv run mypy app

lint-cypher: ## Syntax/semantic-check every Cypher query with Neo4j's parser (needs Node.js)
	cd scripts/cypher-lint && npm ci --silent
	cd $(BACKEND) && uv run python scripts/dump_cypher.py | node ../scripts/cypher-lint/lint.mjs

frontend-install: ## Install frontend dependencies
	cd frontend && npm ci

frontend-dev: ## Run the frontend dev server (proxies /api to localhost:8000)
	cd frontend && npm run dev

frontend-check: ## Type-check, lint and test the frontend
	cd frontend && npm run typecheck && npm run lint && npm test

api-types: ## Regenerate the OpenAPI schema and the frontend's TypeScript types
	cd $(BACKEND) && uv run python scripts/export_openapi.py --out ../frontend/openapi.json
	cd frontend && npm run api-types

format: ## Auto-format code
	cd $(BACKEND) && uv run ruff format . && uv run ruff check --fix .

.PHONY: help install up down dev test test-integration lint lint-cypher format frontend-install frontend-dev frontend-check api-types
