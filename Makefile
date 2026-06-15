SHELL := /bin/sh

PYTHON ?= python3
VENV := .venv
VENV_PYTHON := $(VENV)/bin/python
VENV_PIP := $(VENV)/bin/pip

.PHONY: setup setup-python setup-frontend db-upgrade test lint docker-build local-up local-down clean

setup: setup-python setup-frontend
	@echo "Setup complete. Copy .env.example to .env for local overrides when needed."

setup-python:
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	@$(VENV_PYTHON) -m pip install --upgrade pip
	@$(VENV_PIP) install -r requirements-dev.txt
	@$(VENV_PIP) install -e libs/common-python
	@$(VENV_PIP) install -e apps/control-plane-api
	@$(VENV_PIP) install -e apps/inference-service
	@$(VENV_PIP) install -e apps/rag-service
	@$(VENV_PIP) install -e pipelines/train-claims-risk

setup-frontend:
	@if command -v npm >/dev/null 2>&1; then \
		npm --prefix apps/web-console install; \
	else \
		echo "npm not found. Install Node.js LTS, then run: npm --prefix apps/web-console install"; \
	fi

db-upgrade: setup-python
	@$(VENV_PYTHON) -m careai_control_plane_api.migration_runner

test: setup-python
	@$(VENV_PYTHON) -m pytest

lint: setup-python
	@$(VENV_PYTHON) -m ruff check .
	@if command -v npm >/dev/null 2>&1 && test -d apps/web-console/node_modules; then \
		npm --prefix apps/web-console run lint; \
	else \
		echo "Skipping frontend lint. Run make setup with npm available to install frontend dependencies."; \
	fi

docker-build:
	@docker compose build

local-up:
	@docker compose up -d postgres redis mlflow azurite

local-down:
	@docker compose down

clean:
	@rm -rf $(VENV) .pytest_cache .ruff_cache
