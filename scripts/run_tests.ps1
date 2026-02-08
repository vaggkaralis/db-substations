Param([switch]$FailOnError)

python -m pip install --upgrade pip
if (Test-Path -Path 'requirements.txt') { pip install -r requirements.txt }
if (Test-Path -Path 'requirements-dev.txt') { pip install -r requirements-dev.txt } else { pip install pytest pytest-cov }

& pytest -q
if ($LASTEXITCODE -ne 0 -and $FailOnError) { exit $LASTEXITCODE }
