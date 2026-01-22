SHELL := /usr/bin/env bash

ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
VENV := $(ROOT_DIR)/.venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
ALEMBIC := $(VENV)/bin/alembic

export PYTHONPATH := $(ROOT_DIR)/services/api:$(ROOT_DIR)/packages/sim:$(ROOT_DIR)/packages/rl:$(ROOT_DIR)/packages/shared

# Ops defaults
BASELINE ?= packs/default/v1/pack.json
CANDIDATE ?= packs/default/v1/pack.json
POOL_LIMIT ?= 8
OPPONENTS ?= 4
SEED_SET_COUNT ?= 3

.PHONY: dev api web bootstrap db-init seed-data seed-data-reset balance-report ops-clean ops-metrics-rollup test test-fast fmt handoff e2e
.PHONY: desktop-dev desktop-build
.PHONY: ops-preflight generate-pack
.PHONY: discord-register
.PHONY: prod-up prod-down prod-logs migrate deploy-up deploy-down deploy-logs deploy-smoke

dev: bootstrap db-init seed-data
	./scripts/dev.sh

api: bootstrap db-init
	./scripts/run_api.sh

web:
	cd apps/web && npm run dev -- --host 0.0.0.0 --port 3000

bootstrap:
	./scripts/bootstrap.sh

db-init: bootstrap
	./scripts/db_init.sh

migrate: db-init

seed-data: bootstrap
	$(PY) ./scripts/seed_data.py

seed-data-reset: bootstrap
	$(PY) ./scripts/seed_data.py --reset

balance-report: bootstrap
	$(PY) ./scripts/balance_report.py

ops-clean: bootstrap
	$(PY) ./scripts/cleanup_jobs.py

ops-metrics-rollup: bootstrap
	$(PY) ./scripts/metrics_rollup.py --range 30d

generate-pack: bootstrap
	$(PY) ./scripts/generate_pack.py

ops-preflight: bootstrap
	$(PY) ./scripts/patch_preflight.py --baseline "$(BASELINE)" --candidate "$(CANDIDATE)" --pool-limit "$(POOL_LIMIT)" --opponents "$(OPPONENTS)" --seed-set-count "$(SEED_SET_COUNT)"

test: bootstrap
	$(PY) -m pytest -q

test-fast:
	@if [[ ! -x "$(PY)" ]]; then echo "Missing .venv. Run 'make bootstrap' once."; exit 1; fi
	$(PY) -m pytest -q

fmt: bootstrap
	$(PY) -m ruff format .
	$(PY) -m ruff check . --fix

handoff:
	./scripts/handoff.sh

e2e: bootstrap
	./scripts/e2e.sh

desktop-dev:
	cd apps/web && npm ci && npm run build
	cd apps/desktop && npm ci && npm run dev

desktop-build:
	cd apps/web && npm ci && npm run build
	cd apps/desktop && npm ci && npm run dist

discord-register: bootstrap
	$(PY) ./scripts/discord_register_commands.py

prod-up:
	docker compose -f docker-compose.prod.yml up --build -d

prod-down:
	docker compose -f docker-compose.prod.yml down --remove-orphans

prod-logs:
	docker compose -f docker-compose.prod.yml logs -f --tail=200

deploy-up:
	docker compose -f docker-compose.deploy.yml --env-file .env.deploy up --build -d

deploy-down:
	docker compose -f docker-compose.deploy.yml --env-file .env.deploy down --remove-orphans

deploy-logs:
	docker compose -f docker-compose.deploy.yml --env-file .env.deploy logs -f --tail=200

deploy-smoke:
	./scripts/deploy_smoke.sh
