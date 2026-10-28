.DEFAULT_GOAL := help

UV ?= uv
HOST ?= 127.0.0.1
PORT ?= 8000
MATTER ?= M12205
CATEGORY ?= Other Documents
LIMIT ?= 10
OUTPUT ?= ./downloads

export HOST PORT MATTER CATEGORY LIMIT OUTPUT

.PHONY: help setup env install browser run fetch test live-test lint format check \
        build up down restart logs health

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "; print "Usage: make <target>\n"} /^[a-z-]+:.*## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf '\nFetch example: make fetch MATTER=M12205 CATEGORY="Other Documents" LIMIT=1 OUTPUT=./downloads/run-1\n'

setup: env browser ## Install dependencies and Chromium; create .env if absent

env: ## Copy .env.example only when .env does not exist
	@if [ ! -e .env ]; then cp .env.example .env; fi

install: ## Install locked Python and development dependencies
	$(UV) sync --frozen

browser: install ## Install Chromium and its system dependencies (may require sudo)
	$(UV) run --frozen playwright install --with-deps chromium

run: ## Run the API and worker locally (HOST=127.0.0.1 PORT=8000)
	$(UV) run --frozen uvicorn senpilot.main:app --host "$$HOST" --port "$$PORT" --workers 1

fetch: ## Fetch a matter's documents and ZIP without email
	@$(UV) run --frozen python -m senpilot.cli fetch "$$MATTER" "$$CATEGORY" --limit "$$LIMIT" --output "$$OUTPUT"

test: ## Run the offline test suite (requires installed Chromium)
	$(UV) run --frozen pytest -q

live-test: ## Run the opt-in M12205 smoke test against the real website
	SENPILOT_LIVE_TEST=1 $(UV) run --frozen pytest -q tests/test_browser.py -k live

lint: ## Check lint and formatting without changing files
	$(UV) run --frozen ruff check .
	$(UV) run --frozen ruff format --check .

format: ## Format Python source and tests
	$(UV) run --frozen ruff format .

check: lint test ## Run lint, formatting checks, and offline tests

build: ## Build the Docker Compose image
	docker compose build

up: ## Build and start the Docker Compose service in the background
	docker compose up -d --build

down: ## Stop Docker Compose; preserve the SQLite volume
	docker compose down

restart: ## Recreate containers to apply .env changes; preserve the SQLite volume
	docker compose up -d --force-recreate

logs: ## Follow Docker Compose application logs
	docker compose logs -f agent

health: ## Check the local API at http://127.0.0.1:PORT/health
	curl --fail --silent --show-error "http://127.0.0.1:$$PORT/health"
	@printf '\n'
