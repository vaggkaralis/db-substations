"""Application configuration management.

Handles persistent settings stored in app_settings.json:
- Language preference (el/en)
- Database path selection
- Current user session (login state)
"""

import json
import os
from datetime import datetime


SETTINGS_FILE = os.environ.get(
    "APP_SETTINGS_PATH",
    os.path.join(os.path.dirname(__file__), "app_settings.json"),
)

# Language constants
DEFAULT_LANGUAGE = "el"
SUPPORTED_LANGUAGES = ("el", "en")


def _load_app_settings() -> dict:
    """Load application settings from JSON file.
    
    Returns:
        Dictionary with settings, or empty dict if file doesn't exist
    """
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_app_settings(settings: dict) -> None:
    """Save application settings to JSON file.
    
    Args:
        settings: Dictionary of settings to save
    """
    try:
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
    return settings.get("db_path")


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
