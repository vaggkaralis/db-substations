import subprocess
import sys
import pytest


def tool_available(module_name):
    try:
        # Try running as a module (same as CI: `python -m <tool>`)
        proc = subprocess.run([sys.executable, "-m", module_name, "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return proc.returncode == 0
    except Exception:
        return False


def run_module(cmd_parts):
    subprocess.check_call([sys.executable, "-m"] + cmd_parts)


def test_ruff_checks():
    if not tool_available("ruff"):
        pytest.skip("ruff not installed; install -r requirements-dev.txt to enable CI lint checks")

    # mirror CI: format --check and check for repo
    # exclude local virtualenvs and this test file so local dev envs don't fail
    excludes = ".venv,venv,scripts,tests/test_ci_checks.py"
    run_module(["ruff", "format", "--check", ".", "--exclude", excludes])
    run_module(["ruff", "check", ".", "--exclude", excludes])


def test_ruff_scripts_file():
    if not tool_available("ruff"):
        pytest.skip("ruff not installed; install -r requirements-dev.txt to enable CI lint checks")
    run_module(["ruff", "format", "--check", "scripts/access_gate_utils.py"])
    run_module(["ruff", "check", "scripts/access_gate_utils.py"])


def test_flake8_checks():
    if not tool_available("flake8"):
        pytest.skip("flake8 not installed; install -r requirements-dev.txt to enable CI lint checks")

    run_module(["flake8", "--max-line-length=88", "--exclude=.venv,venv,scripts,.dist,dist,tests/_shims"])
    run_module(["flake8", "--max-line-length=88", "scripts/access_gate_utils.py"])
