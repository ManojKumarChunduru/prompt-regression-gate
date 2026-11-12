# Every target runs offline: no model, no key, no network, no socket. `make verify` is the one
# promise the README makes, and it must pass from a fresh clone.

PY ?= python3

.PHONY: install install-api lint test coverage experiments receipts evidence verify clean

install:
	$(PY) -m pip install -e ".[dev]"

install-api:
	$(PY) -m pip install -e ".[dev,api]"

lint:
	ruff check .
	ruff format --check .

test:
	$(PY) -m pytest

coverage:
	$(PY) -m pytest --junitxml=docs/test-results.xml --cov=prg --cov-report=json:coverage.json --cov-report=term

experiments:
	$(PY) experiments/exp01_review_census.py
	$(PY) experiments/exp02_noise_floor.py
	$(PY) experiments/exp03_grounding_census.py
	$(PY) experiments/exp04_reviewer_blind_spot.py
	$(PY) experiments/exp05_gate_matrix.py

receipts: coverage experiments
	$(PY) tools/collect_metrics.py
	$(PY) tools/check_numbers.py

evidence:
	$(PY) tools/render_architecture.py
	$(PY) tools/capture_screenshots.py
	$(PY) tools/record_demo.py

verify: lint receipts

clean:
	rm -rf coverage.json docs/test-results.xml .pytest_cache .ruff_cache build src/*.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
