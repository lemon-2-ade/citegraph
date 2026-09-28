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

format: ## Auto-format code
	cd $(BACKEND) && uv run ruff format . && uv run ruff check --fix .

.PHONY: help install up down dev test test-integration lint format
