"""Application configuration management.

Handles persistent settings stored in app_settings.json:
- Language preference (el/en)
- Database path selection
- Current user session (login state)
"""

import json
import os


APP_NAME = "SubstationManager"
_DEFAULT_SETTINGS_FILE_NAME = "app_settings.json"
_DEFAULT_TEMPLATE_FILE_NAME = "app_settings.default.json"
_PATH_SETTING_KEYS = (
    "db_path",
    "sync_root_path",
    "backup_root_path",
)


def _get_app_data_dir() -> str:
    explicit_dir = (os.environ.get("APP_SETTINGS_DIR") or "").strip()
    if explicit_dir:
        return os.path.abspath(os.path.expanduser(explicit_dir))

    if os.name == "nt":
        local_app_data = (os.environ.get("LOCALAPPDATA") or "").strip()
        if local_app_data:
            return os.path.join(local_app_data, APP_NAME)

    home = os.path.expanduser("~")
    return os.path.join(home, f".{APP_NAME.lower()}")


APP_DATA_DIR = _get_app_data_dir()

# Prefer a project-local settings file (developer / portable install).
# Fall back to the per-user app-data directory for installed EXE users.
_PROJECT_SETTINGS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), _DEFAULT_SETTINGS_FILE_NAME
)
_APPDATA_SETTINGS_FILE = os.path.join(APP_DATA_DIR, _DEFAULT_SETTINGS_FILE_NAME)

SETTINGS_FILE = os.environ.get(
    "APP_SETTINGS_PATH",
    _PROJECT_SETTINGS_FILE
    if os.path.exists(_PROJECT_SETTINGS_FILE)
    else _APPDATA_SETTINGS_FILE,
)
DEFAULT_TEMPLATE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), _DEFAULT_TEMPLATE_FILE_NAME
)

# Language constants
DEFAULT_LANGUAGE = "el"
SUPPORTED_LANGUAGES = ("el", "en")


def _default_settings() -> dict:
    return {
        "language": DEFAULT_LANGUAGE,
        "db_path": "substations.db",
        "sync_root_path": "sync_exchange",
        "backup_root_path": "backups_auto",
        "sync_auto_cycle_enabled": True,
        "sync_auto_cycle_minutes": 60,
        # PDF normalization settings
        "pdf_normalize_async": False,
        # Size threshold in KB above which normalization may be performed asynchronously
        "pdf_normalize_size_threshold_kb": 1024,
        "sync_backup_on_change": True,
        "backup_hot_keep": 3,
        "setup_wizard_completed": False,
    }


def _load_default_template() -> dict:
    defaults = _default_settings()
    try:
        with open(DEFAULT_TEMPLATE_FILE, "r", encoding="utf-8") as fh:
            template = json.load(fh)
        if isinstance(template, dict):
            defaults.update(template)
    except Exception:
        pass
    return defaults


def _resolve_path_value(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    expanded = os.path.expandvars(os.path.expanduser(text))
    if os.path.isabs(expanded):
        return os.path.abspath(expanded)
    # settings file (project root in dev, %LOCALAPPDATA%/… in production).
    settings_dir = os.path.dirname(os.path.abspath(SETTINGS_FILE))
    return os.path.abspath(os.path.join(settings_dir, expanded))


def _normalize_settings(settings: dict) -> tuple[dict, bool]:
    """Fill in missing keys from the default template.

    Path values are intentionally kept as stored (relative or absolute);
    resolution against the settings-file directory happens at use-time via
    _resolve_path_value(), so the on-disk file stays clean and portable.
    """
    normalized = dict(settings or {})
    changed = False

    defaults = _load_default_template()
    for key, default_value in defaults.items():
        if key not in normalized:
            normalized[key] = default_value
            changed = True

    language = normalized.get("language", DEFAULT_LANGUAGE)
    if language not in SUPPORTED_LANGUAGES:
        normalized["language"] = DEFAULT_LANGUAGE
        changed = True

    return normalized, changed


def _load_app_settings() -> dict:
    """Load application settings from JSON file.

    Returns:
        Dictionary with settings, or empty dict if file doesn't exist
    """
    data = {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
            loaded = json.load(fh)
            data = loaded if isinstance(loaded, dict) else {}
    except Exception:
        data = {}

    normalized, changed = _normalize_settings(data)

    if changed or not os.path.exists(SETTINGS_FILE):
        _save_app_settings(normalized)

    return normalized


def _save_app_settings(settings: dict) -> None:
    """Save application settings to JSON file.

    Args:
        settings: Dictionary of settings to save
    """
    try:
        settings_dir = os.path.dirname(SETTINGS_FILE)
        if settings_dir:
            os.makedirs(settings_dir, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as fh:
            json.dump(settings, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass


# Language management
_settings = _load_app_settings()
CURRENT_LANGUAGE = _settings.get("language", DEFAULT_LANGUAGE)
if CURRENT_LANGUAGE not in SUPPORTED_LANGUAGES:
    CURRENT_LANGUAGE = DEFAULT_LANGUAGE


def get_current_language() -> str:
    """Get the currently selected language code.

    Returns:
        Language code ("el" or "en")
    """
    return CURRENT_LANGUAGE


def set_current_language(language: str) -> bool:
    """Set the preferred language and save to settings.

    Args:
        language: Language code ("el" or "en")

    Returns:
        True if successful, False otherwise
    """
    global CURRENT_LANGUAGE
    if language not in SUPPORTED_LANGUAGES:
        return False
    CURRENT_LANGUAGE = language
    settings = _load_app_settings()
    settings["language"] = language
    _save_app_settings(settings)
    return True


# User session management
def get_current_user() -> dict | None:
    """Return the current logged-in user dict with keys: id, name, role.

    Returns:
        Dict with user info or None if no user is logged in
    """
    settings = _load_app_settings()
    user_data = settings.get("current_user")
    if not user_data or not isinstance(user_data, dict):
        return None
    # Validate required fields
    if not all(k in user_data for k in ("id", "name", "role")):
        return None
    return user_data


def set_current_user(user_id: int, name: str, role: str) -> bool:
    """Set the current logged-in user and save to settings.

    Args:
        user_id: Database ID of the person
        name: Full name of the person
        role: Role of the person

    Returns:
        True if successful, False otherwise
    """
    try:
        settings = _load_app_settings()
        settings["current_user"] = {
            "id": int(user_id),
            "name": str(name),
            "role": str(role),
        }
        _save_app_settings(settings)
        return True
    except Exception:
        return False


def clear_current_user() -> bool:
    """Clear the current logged-in user (logout).

    Returns:
        True if successful, False otherwise
    """
    try:
        settings = _load_app_settings()
        if "current_user" in settings:
            del settings["current_user"]
        _save_app_settings(settings)
        return True
    except Exception:
        return False


# Database path management
def get_db_path() -> str | None:
    """Get the current database path setting.

    Returns:
        Database path from app_settings.json, or None if not set (uses default)
    """
    settings = _load_app_settings()
    return _resolve_path_value(settings.get("db_path"))


def set_db_path(db_path: str) -> bool:
    """Save a database path setting.

    Args:
        db_path: Full path to the database file

    Returns:
        True if successful, False otherwise
    """
    try:
        settings = _load_app_settings()
        settings["db_path"] = str(db_path)
        _save_app_settings(settings)
        return True
    except Exception:
        return False


def clear_db_path() -> bool:
    """Clear the saved database path setting (revert to default).

    Returns:
        True if successful, False otherwise
    """
    try:
        settings = _load_app_settings()
        if "db_path" in settings:
            del settings["db_path"]
        _save_app_settings(settings)
        return True
    except Exception:
        return False


# Generic app settings helpers


def get_app_setting(key: str, default=None):
    """Get a raw setting value by key.

    Args:
        key: Setting key
        default: Returned when key doesn't exist

    Returns:
        Stored value or default
    """
    settings = _load_app_settings()
    return settings.get(key, default)


def set_app_setting(key: str, value) -> bool:
    """Set a raw setting value by key.

    Args:
        key: Setting key
        value: JSON-serializable setting value

    Returns:
        True if saved, False otherwise
    """
    try:
        settings = _load_app_settings()
        settings[key] = value
        _save_app_settings(settings)
        return True
    except Exception:
        return False


def clear_app_setting(key: str) -> bool:
    """Remove a setting key if present.

    Args:
        key: Setting key to remove

    Returns:
        True if saved, False otherwise
    """
    try:
        settings = _load_app_settings()
        if key in settings:
            del settings[key]
        _save_app_settings(settings)
        return True
    except Exception:
        return False
