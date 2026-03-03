.PHONY: venv install run test

VENV ?= .venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
UVICORN := $(VENV)/bin/uvicorn

venv:
	python3 -m venv $(VENV)

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -e .

run:
	$(UVICORN) madstation.app:app --reload

test:
	$(PYTHON) -m pytest -q
