**Purpose**: how to run the full test-suite locally and in CI.

- **Run all tests (Unix/macOS)**:

```bash
./scripts/run_tests.sh
```

- **Run all tests (Windows PowerShell)**:

```powershell
.\scripts\run_tests.ps1 -FailOnError
```

- **Run a single test file**:

```bash
pytest tests/test_some_file.py -q
```

- **CI**: GitHub Actions runs the tests on `push` to `main`, on `pull_request`, and when a `release` is created. The workflow is in `.github/workflows/python-tests.yml`.

- **Output**: The test runner writes `tests/results.xml` (JUnit) and coverage data (if `pytest-cov` available).

- **Add tests**: Place new tests under the `tests/` folder. Tests should be deterministic and runnable headless where possible.

- **Developer notes**:
  - Install the dev requirements with `pip install -r requirements-dev.txt`.
  - Use `scripts/run_tests.ps1` on Windows to ensure the same install steps as CI.
