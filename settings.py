import os
import sys

# Canonical database filename used by the application. Override with
# the environment variable `DATABASE_PATH` if present.
DB_FILENAME = os.environ.get("DATABASE_FILENAME", "substations.db")
# Full DB path used by code; can be set via `DATABASE_PATH` env var to point
# to an alternate location. If unset, defaults to a path next to the script
# (development) or next to the executable (frozen app), not the current cwd.
if getattr(sys, "frozen", False):
    _RUNTIME_BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    _RUNTIME_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(_RUNTIME_BASE_DIR, DB_FILENAME))

# Android-specific default path hint used in the Android UI file picker.
ANDROID_DEFAULT_DB_PATH = os.environ.get(
    "ANDROID_DEFAULT_DB_PATH", f"/storage/emulated/0/Download/{DB_FILENAME}"
)
