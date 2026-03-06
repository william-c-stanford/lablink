.PHONY: help dev test lint format migrate seed clean check install

PYTHON   ?= python
UV       ?= uv
APP_MOD  ?= lablink.main:app
HOST     ?= 0.0.0.0
PORT     ?= 8000

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

install: ## Install project and dev dependencies via uv
	$(UV) sync --all-extras

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------

dev: ## Run FastAPI dev server with auto-reload
	$(UV) run uvicorn $(APP_MOD) --reload --host $(HOST) --port $(PORT)

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

test: ## Run test suite with pytest
	$(UV) run pytest tests/ -v --tb=short

test-cov: ## Run tests with coverage report
	$(UV) run pytest tests/ -v --tb=short --cov=lablink --cov-report=term-missing --cov-report=html

# ---------------------------------------------------------------------------
# Code quality
# ---------------------------------------------------------------------------

lint: ## Run ruff linter checks
	$(UV) run ruff check src/ tests/
	$(UV) run ruff format --check src/ tests/

format: ## Auto-format code with ruff
	$(UV) run ruff format src/ tests/
	$(UV) run ruff check --fix src/ tests/

check: lint test ## Run lint + test (CI entrypoint)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

migrate: ## Run Alembic migrations (head)
	$(UV) run alembic upgrade head

migrate-new: ## Create a new migration: make migrate-new MSG="add users table"
	$(UV) run alembic revision --autogenerate -m "$(MSG)"

migrate-down: ## Downgrade one migration revision
	$(UV) run alembic downgrade -1

# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

seed: ## Load seed / fixture data into the database
	$(UV) run python -m lablink.scripts.seed

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

clean: ## Remove build artifacts, caches, and temp files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf htmlcov .coverage dist build *.egg-info
