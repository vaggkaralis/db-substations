"""Database versioning and compatibility management.

Handles database schema versioning and app/DB compatibility checking.
Metadata is stored in db_metadata.json.
"""

import json
import os
from datetime import datetime

DB_METADATA_PATH = os.environ.get(
    "DB_METADATA_PATH",
    os.path.join(os.path.dirname(__file__), "db_metadata.json"),
)

# Define app version → DB version compatibility matrix
# Maps app versions to the min/max DB versions they can work with
DB_COMPATIBILITY = {
    "0.5.0": {"min_db": "1.0.0", "max_db": "1.0.0"},
    "0.5.1": {"min_db": "1.0.0", "max_db": "1.0.0"},
    "0.6.0": {"min_db": "1.0.0", "max_db": "1.0.0"},
    "0.7.0": {"min_db": "1.0.0", "max_db": "1.0.0"},
    "2.0.0": {"min_db": "1.0.0", "max_db": "1.0.0"},
    "2.1.0": {"min_db": "1.0.0", "max_db": "1.0.0"},
    "3.0.0": {"min_db": "1.0.0", "max_db": "1.0.0"},
}


def _get_db_metadata() -> dict:
    """Load database metadata from db_metadata.json.

    Returns:
        Dictionary with db_version, last_migration, created_at, app_version_created
    """
    try:
        with open(DB_METADATA_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except Exception:
        # If metadata doesn't exist yet, return defaults for initial version
        return {
            "db_version": "1.0.0",
            "last_migration": "000_initial_schema",
            "created_at": datetime.now().isoformat(),
            "app_version_created": get_app_version_string(),
        }


def _save_db_metadata(metadata: dict) -> None:
    """Save database metadata to db_metadata.json.

    Args:
        metadata: Dictionary with database version information
    """
    try:
        with open(DB_METADATA_PATH, "w", encoding="utf-8") as fh:
            json.dump(metadata, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_app_version_string() -> str:
    """Get the current application version.

    Returns:
        Version string (e.g., '0.4.0')
    """
    return os.environ.get("APP_VERSION", "0.7.0")


def get_db_version_string() -> str:
    """Get the current database version.

    Returns:
        Version string (e.g., '1.0.0')
    """
    metadata = _get_db_metadata()
    return metadata.get("db_version", "1.0.0")


def is_db_compatible(app_version: str = None, db_version: str = None) -> dict:
    """Check if the database version is compatible with the app version.

    Args:
        app_version: App version to check (defaults to current APP_VERSION)
        db_version: DB version to check (defaults to current db version)

    Returns:
        Dictionary with keys:
            - 'compatible': bool - True if versions are compatible
            - 'app_version': str - The app version checked
            - 'db_version': str - The db version checked
            - 'message': str - Human-readable compatibility message
    """
    if app_version is None:
        app_version = get_app_version_string()
    if db_version is None:
        db_version = get_db_version_string()

    # Get compatibility requirements for this app version
    compat_spec = DB_COMPATIBILITY.get(app_version, {})
    if not compat_spec:
        return {
            "compatible": False,
            "app_version": app_version,
            "db_version": db_version,
            "message": f"App version {app_version} not recognized in compatibility matrix",
        }

    min_db = compat_spec.get("min_db", "1.0.0")
    max_db = compat_spec.get("max_db", "1.0.0")

    # Simple version comparison (assumes MAJOR.MINOR.PATCH format)
    def parse_version(v_str):
        try:
            parts = v_str.split(".")
            return tuple(int(p) for p in parts)
        except (ValueError, AttributeError):
            return (0, 0, 0)

    db_tuple = parse_version(db_version)
    min_tuple = parse_version(min_db)
    max_tuple = parse_version(max_db)

    is_compatible = min_tuple <= db_tuple <= max_tuple

    if is_compatible:
        message = f"Compatible: App {app_version} with DB {db_version}"
    else:
        message = f"Incompatible: App {app_version} requires DB {min_db}-{max_db}, but DB is {db_version}"

    return {
        "compatible": is_compatible,
        "app_version": app_version,
        "db_version": db_version,
        "message": message,
    }
