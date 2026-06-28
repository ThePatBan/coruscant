PYTHON ?= python

.PHONY: setup test api worker lint format

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
