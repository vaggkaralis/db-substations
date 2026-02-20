import importlib
from pathlib import Path


def test_import_top_level_modules():
    root = Path(__file__).resolve().parent.parent
    py_files = [p for p in root.glob('*.py')]
    blacklist = {
        'build_exe', 'build', 'Run', 'run_headless_debug', 'build',
        'change_log', 'VERSION',
    }

    failures = []
    for p in sorted(py_files):
        name = p.stem
        if name.startswith('.') or name.startswith('_'):
            continue
        if name in blacklist:
            continue
        try:
            mod = importlib.import_module(name)
        except Exception as exc:
            failures.append(f'{name}: {exc!r}')
        else:
            assert mod is not None

    if failures:
        raise AssertionError('Import failures:\n' + '\n'.join(failures))
