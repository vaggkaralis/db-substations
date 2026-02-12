import os

# Canonical database filename used by the application. Override with
# the environment variable `DATABASE_PATH` if present.
DB_FILENAME = os.environ.get("DATABASE_FILENAME", "substations_backup.db")
# Full DB path used by code; can be set via `DATABASE_PATH` env var to point
# to an alternate location. If unset, falls back to `DB_FILENAME` in cwd.
DB_PATH = os.environ.get("DATABASE_PATH", DB_FILENAME)

# Android-specific default path hint used in the Android UI file picker.
ANDROID_DEFAULT_DB_PATH = os.environ.get(
    "ANDROID_DEFAULT_DB_PATH", f"/storage/emulated/0/Download/{DB_FILENAME}"
)
