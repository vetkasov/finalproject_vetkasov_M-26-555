.PHONY: install project lint format build package-install

install:
	uv sync --locked

project:
	uv run --locked project

lint:
	uv run --locked ruff check .
	uv run --locked ruff format --check .

format:
	uv run --locked ruff format .

build:
	uv build --clear

package-install: build
	uv tool install --reinstall dist/*.whl
