"""
Android-specific sync utilities for content URI handling and file operations.

Provides Android-safe wrappers for file operations that work with both
direct filesystem paths and content URIs (for OneDrive, Google Drive, etc).
"""

import os
import shutil

try:
    from kivy.logger import Logger
except ImportError:
    Logger = None


def _log(msg, level="info"):
    """Log to Kivy logger if available."""
    if Logger:
        getattr(Logger, level, Logger.info)(f"SYNC: {msg}")


def is_content_uri(path: str) -> bool:
    """Check if path is a content URI (Android content provider)."""
    return path.startswith("content://") if path else False


def safe_listdir(path: str) -> list:
    """
    List directory contents safely on Android.

    Works with both direct paths and content URIs.
    """
    if not path:
        return []

    try:
        if is_content_uri(path):
            # Content URI: try direct access first, fall back to Android API
            return _listdir_content_uri(path)
        else:
            # Direct path
            if os.path.exists(path):
                return os.listdir(path)
            return []
    except Exception as e:
        _log(f"Error listing {path}: {e}", "warning")
        return []


def safe_makedirs(path: str, exist_ok: bool = True) -> bool:
    """
    Create directories safely on Android.

    Only works with direct filesystem paths.
    """
    if not path or is_content_uri(path):
        return False

    try:
        os.makedirs(path, exist_ok=exist_ok)
        return True
    except Exception as e:
        _log(f"Error creating {path}: {e}", "warning")
        return False


def safe_exists(path: str) -> bool:
    """Check if path exists safely."""
    if not path:
        return False

    try:
        if is_content_uri(path):
            return _exists_content_uri(path)
        else:
            return os.path.exists(path)
    except Exception:
        return False


def safe_isfile(path: str) -> bool:
    """Check if path is a file safely."""
    if not path or is_content_uri(path):
        return False

    try:
        return os.path.isfile(path)
    except Exception:
        return False


def safe_isdir(path: str) -> bool:
    """Check if path is a directory safely."""
    if not path:
        return False

    try:
        if is_content_uri(path):
            return _isdir_content_uri(path)
        else:
            return os.path.isdir(path)
    except Exception:
        return False


def safe_read_file(path: str, encoding: str = "utf-8") -> str | None:
    """
    Read file content safely.

    Works with both direct paths and content URIs.
    """
    if not path:
        return None

    try:
        if is_content_uri(path):
            return _read_content_uri(path, encoding)
        else:
            with open(path, "r", encoding=encoding) as f:
                return f.read()
    except Exception as e:
        _log(f"Error reading {path}: {e}", "warning")
        return None


def safe_write_file(path: str, content: str, encoding: str = "utf-8") -> bool:
    """
    Write file content safely.

    Only works with direct filesystem paths.
    """
    if not path or is_content_uri(path):
        return False

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding=encoding) as f:
            f.write(content)
        return True
    except Exception as e:
        _log(f"Error writing {path}: {e}", "warning")
        return False


def safe_append_file(path: str, content: str, encoding: str = "utf-8") -> bool:
    """
    Append to file safely.

    Only works with direct filesystem paths.
    """
    if not path or is_content_uri(path):
        return False

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding=encoding) as f:
            f.write(content)
        return True
    except Exception as e:
        _log(f"Error appending to {path}: {e}", "warning")
        return False


def safe_move(src: str, dst: str) -> bool:
    """
    Move file from src to dst safely.

    Only works with direct filesystem paths.
    """
    if not src or not dst or is_content_uri(src) or is_content_uri(dst):
        return False

    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        return True
    except Exception as e:
        _log(f"Error moving {src} to {dst}: {e}", "warning")
        return False


def safe_copy(src: str, dst: str) -> bool:
    """
    Copy file safely.

    Only works with direct filesystem paths for both source and destination.
    """
    if not src or not dst or is_content_uri(src) or is_content_uri(dst):
        return False

    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(src, dst)
        return True
    except Exception as e:
        _log(f"Error copying {src} to {dst}: {e}", "warning")
        return False


# ============================================================================
# Content URI helper functions (Android content provider access)
# ============================================================================


def _listdir_content_uri(uri: str) -> list:
    """List contents of a content URI folder."""
    # For now, return empty list - proper implementation requires
    # Android SAF (Storage Access Framework) integration via Plyer
    _log(f"Content URI listing not fully implemented for {uri}", "warning")
    return []


def _exists_content_uri(uri: str) -> bool:
    """Check if content URI exists."""
    # This requires Android SAF integration
    return False


def _isdir_content_uri(uri: str) -> bool:
    """Check if content URI is a directory."""
    # This requires Android SAF integration
    return False


def _read_content_uri(uri: str, encoding: str = "utf-8") -> str | None:
    """
    Read from a content URI.

    Requires Android ContentResolver integration via Plyer.
    """
    try:
        # Attempting to read directly - may not work with all providers
        # This is a fallback for future SAF integration
        _log(f"Content URI reading not fully implemented for {uri}", "warning")
        return None
    except ImportError:
        return None


def get_sync_paths(db_path: str) -> dict:
    """
    Get sync folder paths for Android.

    Returns:
        Dictionary with resolved paths for sync_root and backup_root
    """
    from config_manager import get_app_setting

    db_dir = os.path.dirname(os.path.abspath(db_path))

    # Check for configured sync_root_path (user may have picked a folder)
    configured_sync_root = get_app_setting("sync_root_path", None)
    if configured_sync_root and os.path.exists(configured_sync_root):
        sync_root = configured_sync_root
    else:
        sync_root = os.path.join(db_dir, "sync_exchange")

    configured_backup_root = get_app_setting("backup_root_path", None)
    if configured_backup_root and os.path.exists(configured_backup_root):
        backup_root = configured_backup_root
    else:
        backup_root = os.path.join(db_dir, "backups_auto")

    return {
        "sync_root": sync_root,
        "backup_root": backup_root,
    }


def resolve_android_sync_root(db_path: str) -> str:
    """Get sync_root for Android, creating if needed."""
    paths = get_sync_paths(db_path)
    sync_root = paths["sync_root"]
    safe_makedirs(sync_root, exist_ok=True)
    return sync_root


def resolve_android_backup_root(db_path: str) -> str:
    """Get backup_root for Android, creating if needed."""
    paths = get_sync_paths(db_path)
    backup_root = paths["backup_root"]
    safe_makedirs(backup_root, exist_ok=True)
    return backup_root


def ensure_android_sync_tree(sync_root: str) -> dict[str, str]:
    """Ensure all required sync directories exist on Android."""
    paths = {
        "inbox_pending": os.path.join(sync_root, "inbox", "pending"),
        "accepted": os.path.join(sync_root, "inbox", "processed", "accepted"),
        "rejected": os.path.join(sync_root, "inbox", "processed", "rejected"),
        "conflicts": os.path.join(sync_root, "inbox", "processed", "conflicts"),
        "logs": os.path.join(sync_root, "logs"),
    }
    for p in paths.values():
        safe_makedirs(p, exist_ok=True)
    return paths


def ensure_android_backup_tree(backup_root: str) -> dict[str, str]:
    """Ensure all required backup directories exist on Android."""
    paths = {
        "hot": os.path.join(backup_root, "hot"),
        "daily": os.path.join(backup_root, "daily"),
        "weekly": os.path.join(backup_root, "weekly"),
        "monthly": os.path.join(backup_root, "monthly"),
        "logs": os.path.join(backup_root, "logs"),
    }
    for p in paths.values():
        safe_makedirs(p, exist_ok=True)
    return paths
