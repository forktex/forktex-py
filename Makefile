.DEFAULT_GOAL := help
PROJECT_NAME := forktex
COVERAGE_FLOOR := 97

help: ## Self-documenting target listing
	@grep -E '^[a-zA-Z_@-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

format: ## Source code conforms to a consistent, auto-enforced style
	poetry run python3 -m ruff format src/ tests/

format-check: ## Check formatting without rewriting files
	poetry run python3 -m ruff format --check src/ tests/

lint: ## Static analysis catches bugs, anti-patterns, and security smells
	poetry run python3 -m ruff check src/ tests/

lint-fix: ## Apply every auto-fixable lint finding
	poetry run python3 -m ruff check --fix src/ tests/

typecheck: ## Static type system verifies interface correctness (pyright)
	poetry run python3 -m pyright src/

test: ## Automated tests verify behaviour, with a coverage floor
	@# The floor is the measured figure, floored: raise it with real coverage, never lower it.
	@# --cov-precision=2, so the floor compares the unrounded figure.
	poetry run python3 -m pytest tests/ -q --cov=src/forktex \
		--cov-report=term-missing --cov-precision=2 --cov-fail-under=$(COVERAGE_FLOOR)

audit: ## Scan the project venv for known CVEs in installed deps
	poetry run python3 -m pip_audit --skip-editable --timeout 30

license-check: ## Verify every source file carries the dual-license header (CI gate)
	poetry run python3 scripts/license_headers.py check

license-fix: ## Add or update the dual-license header on every source file
	poetry run python3 scripts/license_headers.py fix

install: ## Bootstrap the project to a runnable state
	poetry install --with dev
	@# The venv's own pip lags and fails `make audit` on its own advisories.
	poetry run python3 -m pip install -q --upgrade "pip>=26.1.2"

build: ## Build sdist + wheel into dist/ and verify metadata with twine check
	rm -rf dist/
	poetry run python3 -m build
	poetry run python3 -m twine check dist/*

smoke: ## Install the BUILT wheel into a throwaway venv and import every module
	@# The only step that tests the packaged artefact rather than the source tree.
	@set -e; \
	WHL=$$(ls dist/forktex-*-py3-none-any.whl 2>/dev/null | head -1); \
	if [ -z "$$WHL" ]; then echo "  no wheel in dist/ — run 'make build' first"; exit 1; fi; \
	PY=$$(poetry run python3 -c 'import sys; print(sys.executable)'); \
	TMP=$$(mktemp -d); trap 'rm -rf $$TMP' EXIT; \
	echo "smoke: install from $$WHL (interpreter $$PY)"; \
	$$PY -m venv $$TMP/venv >/dev/null; \
	$$TMP/venv/bin/pip install -q "$$WHL"; \
	$$TMP/venv/bin/python -c "import forktex" || { echo "  ✗ import forktex"; exit 1; }; \
	for m in api cache database error iso log storage types; do \
		$$TMP/venv/bin/python -c "import forktex; forktex.$$m" || { echo "  ✗ forktex.$$m"; exit 1; }; \
		echo "  forktex.$$m OK"; \
	done; \
	echo "smoke: one install delivers every module"

publish-test: ## Upload dist/ to TestPyPI for rehearsal
	poetry run python3 -m twine upload -r testpypi dist/*

publish: ## Upload dist/ to production PyPI (irreversible per-version)
	poetry run python3 -m twine upload dist/*

clean: ## Build artifacts and caches removable from project tree
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name dist -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name htmlcov -exec rm -rf {} + 2>/dev/null; true
	find . -type f -name .coverage -delete 2>/dev/null; true

lock-check: ## The lock file resolves the current pyproject.toml
	@# Catches a pyproject.toml edit that was never locked.
	poetry check --lock

ci: ## Aggregate quality gate before publish
	@$(MAKE) lock-check
	@$(MAKE) format-check
	@$(MAKE) lint
	@$(MAKE) license-check
	@$(MAKE) typecheck
	@$(MAKE) audit
	@$(MAKE) test
	@$(MAKE) build
	@$(MAKE) smoke
	@echo ''
	@echo 'CI passed for $(PROJECT_NAME) — safe to: make publish-test  /  make publish'

.PHONY: help format format-check lint lint-fix typecheck test audit license-check lock-check \
	license-fix install build smoke publish-test publish clean ci
