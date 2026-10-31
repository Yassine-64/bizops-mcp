.PHONY: check test lint
check: lint test
lint:
	uv run ruff check . && uv run ruff format --check . && uv run mypy
test:
	uv run pytest -q
