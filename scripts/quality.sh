#!/bin/bash
# Run all quality checks (for CI/CD)

set -e  # Exit on error

echo "===== CODE QUALITY CHECKS ====="
echo

echo "1. Checking code formatting..."
uv run black --check backend/
echo "✓ Black passed"
echo

echo "2. Checking import order..."
uv run isort --check-only backend/
echo "✓ isort passed"
echo

echo "3. Running linter..."
uv run ruff check backend/
echo "✓ Ruff passed"
echo

echo "4. Running tests..."
cd backend && uv run pytest
echo "✓ Tests passed"
echo

echo "===== ALL CHECKS PASSED ====="
echo
echo "Note: Type checking with mypy is available via ./scripts/lint.sh"
echo "      but has known type issues that need to be fixed incrementally."
