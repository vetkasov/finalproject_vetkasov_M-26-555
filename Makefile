.PHONY: install project lint format build package-install

UV_TOOL_DIR ?= $(CURDIR)/.tools/uv
UV_TOOL_BIN_DIR ?= $(CURDIR)/.tools/bin

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
	UV_TOOL_DIR="$(UV_TOOL_DIR)" UV_TOOL_BIN_DIR="$(UV_TOOL_BIN_DIR)" \
		uv tool install --reinstall dist/*.whl
