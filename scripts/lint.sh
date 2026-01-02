#!/bin/bash
# Run linters to find issues

set -e  # Exit on error

echo "Running Ruff linter..."
uv run ruff check backend/

echo "Running mypy type checker..."
uv run mypy backend/

echo "✓ Linting complete!"
