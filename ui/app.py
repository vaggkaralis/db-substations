"""Adapter module to expose `SubstationApp` while refactoring.

This module lazily imports `DBrun` and re-exports the `SubstationApp` class.
It allows other parts of the codebase to import `ui.app.SubstationApp`
during an incremental refactor without breaking immediate imports.
"""
from importlib import import_module

try:
    _db = import_module("DBrun")
    SubstationApp = getattr(_db, "SubstationApp")
except Exception:
    class SubstationApp:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("SubstationApp is not available: failed to import DBrun")

__all__ = ["SubstationApp"]
