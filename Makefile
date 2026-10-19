# glossarian quality gates. `uv run` syncs the dev group (pytest, ruff, mypy) on demand.
.PHONY: check test lint typecheck install-test install-shims

check: test lint typecheck

test:
	uv run pytest

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

typecheck:
	uv run mypy src

install-test:
	bash glossarian_install_test.sh

install-shims:
	bash glossarian_install.sh
