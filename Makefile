.PHONY: setup test lint fmt typecheck api worker web dev migrate ingest audit

PY ?= .venv/bin/python

setup:
	python3 -m venv .venv
	$(PY) -m pip install -r requirements-dev.txt mypy
	cd frontend && npm ci

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check src scripts tests migrations

audit:
	$(PY) -m pip_audit -r requirements.txt

fmt:
	$(PY) -m ruff format src/jobai/product
	$(PY) -m ruff check --fix src scripts tests migrations

typecheck:
	$(PY) -m mypy src/jobai/product
	cd frontend && npx tsc --noEmit

api:
	$(PY) scripts/product/run_api.py

worker:
	$(PY) scripts/product/run_worker.py

web:
	cd frontend && npm run dev

dev:
	docker compose up --build

migrate:
	$(PY) -m alembic upgrade head

ingest:
	$(PY) scripts/product/ingest_catalog.py
