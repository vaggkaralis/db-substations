#!/usr/bin/env bash
set -euo pipefail

python -m pip install --upgrade pip
if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
if [ -f requirements-dev.txt ]; then pip install -r requirements-dev.txt; else pip install pytest pytest-cov; fi

pytest -q
