#!/bin/bash
# Check code quality without making changes

set -e  # Exit on error

echo "Checking formatting with Black..."
uv run black --check --diff backend/

echo "Checking import order with isort..."
uv run isort --check-only --diff backend/

echo "✓ All checks passed!"
