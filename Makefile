.DEFAULT_GOAL := help
.PHONY: help install install-all setup run web frontend lock clean test lint migrate

help: ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## create the venv and install python deps
	uv sync

install-all: ## install python deps including the optional minecraft skill
	uv sync --extra minecraft

setup: install ## interactive first-run setup: writes .env and config.json
	uv run bea --setup

migrate: ## one-shot: move the old json/chroma stores into data/bea.db
	uv sync --extra migrate
	uv run python tools/migrate_to_sqlite.py --dry-run
	@echo "--- re-run without --dry-run to apply ---"

run: ## start the engine in CLI mode
	uv run bea

web: frontend ## build the frontend and start the web dashboard
	uv run bea --web

frontend: ## install deps and build the react dashboard
	cd src/web/frontend && npm install && npm run build

test: ## run the test suite
	uv run pytest -q

lint: ## static checks
	uv run ruff check src tests

lock: ## refresh uv.lock after changing dependencies
	uv lock

clean: ## remove the virtual environment and build artifacts
	rm -rf .venv src/web/frontend/dist
