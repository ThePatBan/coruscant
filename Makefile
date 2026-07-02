PYTHON ?= python

.PHONY: setup test api worker lint format up down prod backup smoke

# Post-deploy operational smoke test against a running instance.
# Override the target with SMOKE_URL, e.g.  make smoke SMOKE_URL=https://app.example.com
SMOKE_URL ?= http://localhost:8000

setup:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest

api:
	$(PYTHON) -m uvicorn coruscant.apps.api:app --reload

worker:
	$(PYTHON) -m coruscant.apps.worker

lint:
	$(PYTHON) -m ruff check src tests
	$(PYTHON) -m mypy src

format:
	$(PYTHON) -m ruff format src tests

up:
	docker compose up --build -d

down:
	docker compose down

prod:
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d

backup:
	$(PYTHON) -m coruscant.apps.cli backup

smoke:
	./scripts/smoke.sh $(SMOKE_URL)
