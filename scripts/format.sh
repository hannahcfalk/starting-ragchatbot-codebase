#!/bin/bash
# Format all Python code automatically

set -e  # Exit on error

echo "Formatting Python code with Black..."
uv run black backend/

echo "Sorting imports with isort..."
uv run isort backend/

echo "✓ Formatting complete!"
