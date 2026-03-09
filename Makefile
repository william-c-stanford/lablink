.PHONY: help dev dev-local check-prereqs check-ports test test-cov e2e lint format migrate seed clean check install

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

dev-local: check-prereqs ## Start API + frontend together via honcho (no Docker)
	$(UV) run honcho start

check-prereqs: ## Verify local dev prerequisites are installed
	@which node >/dev/null 2>&1 || (echo "ERROR: node not found. Install Node.js >= 18." && exit 1)
	@which npm >/dev/null 2>&1 || (echo "ERROR: npm not found." && exit 1)
	@test -d frontend/node_modules || (echo "Installing frontend deps..." && cd frontend && npm install)
	@echo "Prerequisites OK."

check-ports: ## Check that ports 8000 and 5173 are free
	@lsof -ti:8000 >/dev/null 2>&1 && echo "WARNING: port 8000 in use" || echo "Port 8000 free"
	@lsof -ti:5173 >/dev/null 2>&1 && echo "WARNING: port 5173 in use" || echo "Port 5173 free"

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

test: ## Run unit + integration test suite with pytest (excludes e2e)
	$(UV) run pytest tests/ -v --tb=short

test-cov: ## Run tests with coverage report
	$(UV) run pytest tests/ -v --tb=short --cov=lablink --cov-report=term-missing --cov-report=html

e2e: ## Run end-to-end browser tests (requires Node.js + Playwright)
	@test -d frontend/node_modules || (echo "Installing frontend deps..." && cd frontend && npm install)
	$(UV) run pytest tests/e2e/ -v --tb=short -m e2e

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
