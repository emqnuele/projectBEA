.DEFAULT_GOAL := help
.PHONY: help install setup update docker docker-up docker-down run web node lock clean test lint migrate model doctor

help: ## show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## create the venv and install python deps
	uv sync

setup: install ## interactive first-run setup: writes .env and config.json
	uv run bea --setup

update: ## pull the new version, keeping your prompts, config and memory
	uv run bea --update

doctor: ## check this machine: keys, voice, ears, body, and what to fix
	uv run bea --doctor

docker: ## build the image and run the setup wizard inside it
	@# a missing bind-mount target makes docker create a directory in its place
	@test -f config.json || cp config.example.json config.json
	@test -f .env || touch .env
	docker compose build
	docker compose run --rm setup

docker-up: ## start the dashboard in docker on http://127.0.0.1:8000
	docker compose up -d
	@echo '  dashboard: http://127.0.0.1:8000'

docker-down: ## stop the container
	docker compose down

migrate: ## one-shot: move the old json/chroma stores into data/bea.db
	# chromadb is only ever needed to read an old store, so it is fetched for
	# this command instead of living in the lockfile with its 28 dependencies
	uv run --with chromadb python tools/migrate_to_sqlite.py --dry-run
	@echo "--- re-run without --dry-run to apply ---"

run: ## start the engine in CLI mode
	uv run bea

web: node ## build the javascript and start the web dashboard
	uv run bea --web

node: ## install the dashboard and the discord bot (needs node 20+)
	uv run bea --install-node

test: ## run the test suite
	uv run pytest -q

lint: ## static checks
	uv run ruff check src tests

model: ## download the free sample 3d model and clip into data/
	uv run python tools/fetch_model.py

lock: ## refresh uv.lock after changing dependencies
	uv lock

clean: ## remove the virtual environment and build artifacts
	rm -rf .venv src/web/frontend/dist
