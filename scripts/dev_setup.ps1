#!/usr/bin/env pwsh
Set-StrictMode -Version Latest

Write-Host "Installing development dependencies and pre-commit hooks..."

python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pre_commit install

Write-Host "Dev setup complete. To validate hooks run: python -m pre_commit run --all-files"
