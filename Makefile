# FinFlow — Makefile
# Common entry points. `make help` lists targets.

.PHONY: help install install-dbt install-dashboard demo-data test lint typecheck ci clean repo-stats

help:
	@grep -E '^## |^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}' 2>/dev/null || true

## Install the package + dev tooling into the current environment
install:
	pip install -e ".[dev]"

## Install dbt Core + dbt-duckdb adapter
install-dbt:
	pip install -e ".[dbt]"

## Install dashboard dependencies (Streamlit + Plotly)
install-dashboard:
	pip install -e ".[dashboard]"

## Generate the synthetic demo dataset (defaults: seed 42, trailing 12 months) into data/sample/
demo-data:
	python -m finflow.datagen.run --out data/sample --seed 42

## Drop the most recent month of synthetic statements into data/incoming/ (pipeline demo scenario)
demo-incoming:
	python -m finflow.datagen.run --out data/sample --seed 42 --scenario incoming

## Run the full test suite
test:
	pytest

## Run lint checks
lint:
	ruff check src tests

## Run type checks
typecheck:
	mypy

## Run everything CI runs
ci: lint typecheck test

## Remove generated build/test artifacts
clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +

## Quick repo statistics
repo-stats:
	@echo "Python files:" && find src tests -name "*.py" | wc -l
	@echo "Lines of code:" && find src tests -name "*.py" -exec cat {} + | wc -l
