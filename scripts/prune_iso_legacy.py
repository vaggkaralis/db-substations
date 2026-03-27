import json
import os
import shutil
from pathlib import Path


def win_path(path: str) -> str:
    abs_path = os.path.abspath(path)
    if os.name != "nt" or abs_path.startswith("\\\\?\\"):
        return abs_path
    if abs_path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + abs_path[2:]
    return "\\\\?\\" + abs_path


def is_dir(path: Path) -> bool:
    return os.path.isdir(win_path(str(path)))


def list_entries(path: Path):
    try:
        with os.scandir(win_path(str(path))) as it:
            return [entry.name for entry in it]
    except Exception:
        return []


def prune_empty(path: Path, stop_at: Path):
    current = path
    while is_dir(current) and current != stop_at:
        if list_entries(current):
            break
        os.rmdir(win_path(str(current)))
        current = current.parent


repo_root = Path(__file__).resolve().parents[1]
settings_path = repo_root / "app_settings.json"
settings = json.loads(settings_path.read_text(encoding="utf-8"))
sync_root = Path(settings["sync_root_path"])

legacy_dirs = []
for dirpath, dirnames, filenames in os.walk(win_path(str(sync_root)), topdown=False):
    current = Path(dirpath.replace("\\\\?\\UNC\\", "\\").replace("\\\\?\\", ""))
    if current.name.startswith("ISO_"):
        legacy_dirs.append(current)

renamed = []
merged = []
deleted = []
skipped = []

for legacy in sorted(legacy_dirs, key=lambda item: len(str(item)), reverse=True):
    try:
        if not is_dir(legacy):
            continue

        target = legacy.with_name(legacy.name.replace("ISO_", "Απομ_", 1))
        if is_dir(target):
            for entry_name in list_entries(legacy):
                src = legacy / entry_name
                dest = target / entry_name
                if dest.exists():
                    continue
                shutil.move(win_path(str(src)), win_path(str(dest)))
            merged.append(str(legacy))
        else:
            shutil.move(win_path(str(legacy)), win_path(str(target)))
            renamed.append(f"{legacy} -> {target}")
            continue

        prune_empty(legacy, sync_root)
        if not is_dir(legacy):
            deleted.append(str(legacy))
    except Exception as exc:
        skipped.append((str(legacy), str(exc)))

print("RENAMED_COUNT:", len(renamed))
for item in renamed:
    print("RENAMED:", item)

print("MERGED_COUNT:", len(merged))
for item in merged:
    print("MERGED:", item)

print("DELETED_COUNT:", len(deleted))
for item in deleted:
    print("DELETED:", item)

print("SKIPPED_COUNT:", len(skipped))
for path, err in skipped:
    print("SKIPPED:", path, "ERROR:", err)
