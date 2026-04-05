#!/usr/bin/env bash
set -euo pipefail

# Installs development dependencies and pre-commit hooks for the project.
# Run inside your Python virtualenv (or system Python if you prefer):
#   ./scripts/dev_setup.sh

python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pre_commit install

echo "Dev setup complete. To validate hooks run: python -m pre_commit run --all-files"
