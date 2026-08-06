.PHONY: setup run validate score test clean

VENV = .venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip

setup:
	python3 -m venv $(VENV)
	$(PIP) install -r requirements.txt

run:
	$(PYTHON) scripts/run_pipeline.py

validate:
	$(PYTHON) scripts/validate_submission.py

score:
	$(PYTHON) scripts/score.py

test:
	$(PYTHON) -m pytest tests/

clean:
	rm -rf __pycache__ .pytest_cache
	find . -type d -name "__pycache__" -exec rm -r {} +
