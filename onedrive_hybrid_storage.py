import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable

from config_manager import get_app_setting
from strings_proxy import STRINGS as S


_MEDIA_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".gif",
    ".webp",
    ".heic",
    ".heif",
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".wmv",
    ".m4v",
}

_DEFAULT_SHARED_ROOT_NAME = "Κοινή Βάση Υποσταθμών"
_LEGACY_SHARED_ROOT_NAME = "shared_substations"

# Canonical Greek folder labels
_DIR_GATE_1 = "ΠΥΛΗ 1"
_DIR_GATE_2 = "ΠΥΛΗ 2"
_DIR_GATE_3 = "ΠΥΛΗ 3"
_DIR_GATE_UNKNOWN = "ΠΥΛΗ Άγνωστη"
_DIR_INTERCONNECTIONS = "Διασυνδέσεις"

_DIR_MAINTENANCE_PARTS = ("Συντηρήσεις", "Βλάβες")
_DIR_INSPECTIONS = "Επιθεωρήσεις"
_DIR_DGA_PARTS = ("Φυσικοχημικές", "Αεριοχρωματογραφία")

_DIR_MEDIA = "Φωτογραφίες_Video"
_DIR_REPORTS = "Αναφορές"
_DIR_REPORTS_BREAKERS_HV = "Διακόπτες ΥΤ"
_DIR_REPORTS_BREAKERS_MV = "Διακόπτες ΜΤ"
_DIR_REPORTS_TRANSFORMERS = "Μετασχηματιστές"
_DIR_REPORTS_OTHER = "Λοιπά"


def _join_parts(parts: tuple[str, ...] | list[str] | str) -> str:
    if isinstance(parts, str):
        return parts
    return os.path.join(*parts)


def _safe_name(value: str, fallback: str = "unknown") -> str:
    text = (value or "").strip()
    if not text:
        return fallback
    text = re.sub(r"[\\/:*?\"<>|]", "_", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or fallback


def _slug(value: str, fallback: str = "item") -> str:
    text = _safe_name(value, fallback=fallback)
    text = text.replace(" ", "_")
    text = re.sub(r"_+", "_", text)
    return text.strip("_") or fallback


def _resolve_default_shared_root(base_dir: str) -> str:
    new_root = os.path.abspath(os.path.join(base_dir, _DEFAULT_SHARED_ROOT_NAME))
    legacy_root = os.path.abspath(os.path.join(base_dir, _LEGACY_SHARED_ROOT_NAME))

    if os.path.isdir(legacy_root) and not os.path.exists(new_root):
        try:
            shutil.move(legacy_root, new_root)
        except Exception:
            return legacy_root

    if os.path.exists(new_root):
        return new_root
    if os.path.exists(legacy_root):
        return legacy_root
    return new_root


def _remap_legacy_shared_root(path: str | None, shared_root: str) -> str | None:
    """Remap a stored path from legacy shared root to the current shared root.

    This prevents re-creating the old ``shared_substations`` tree when older DB
    rows still reference it.
    """
    if not path:
        return path

    try:
        current_root = os.path.abspath(shared_root)
        legacy_root = os.path.abspath(
            os.path.join(os.path.dirname(current_root), _LEGACY_SHARED_ROOT_NAME)
        )
        abs_path = os.path.abspath(path)

        # Windows-safe case-insensitive prefix comparison.
        abs_norm = os.path.normcase(abs_path)
        legacy_norm = os.path.normcase(legacy_root)

        if abs_norm == legacy_norm:
            return current_root

        legacy_prefix = legacy_norm + os.sep
        if abs_norm.startswith(legacy_prefix):
            rel_tail = abs_path[len(legacy_root) :].lstrip("\\/")
            return os.path.join(current_root, rel_tail)

        # Fallback: legacy folder name appears as a path component in a path
        # rooted elsewhere (older explicit OneDrive roots). Replace that
        # component in-place so calls no longer create shared_substations.
        marker = os.sep + _LEGACY_SHARED_ROOT_NAME + os.sep
        if marker in abs_path:
            replacement = os.sep + _DEFAULT_SHARED_ROOT_NAME + os.sep
            return abs_path.replace(marker, replacement, 1)
    except Exception:
        return path

    return path


def resolve_shared_root(db_path: str | None = None) -> str:
    configured = get_app_setting("onedrive_shared_root_path", None)
    if configured:
        return os.path.abspath(configured)

    sync_root = get_app_setting("sync_root_path", None)
    if sync_root:
        return _resolve_default_shared_root(sync_root)

    if db_path:
        return _resolve_default_shared_root(os.path.dirname(db_path))

    return os.path.abspath(_DEFAULT_SHARED_ROOT_NAME)


def _bucket_for_gate(gate_value: str | None) -> tuple[str, str]:
    gate = (gate_value or "").strip().upper().replace(" ", "")

    if "1-2" in gate:
        return ("interconnections", "1-2")
    if "2-3" in gate:
        return ("interconnections", "2-3")

    match = re.search(r"([123])", gate)
    if match:
        return ("gate", match.group(1))

    return ("gate", "unknown")


def _gate_relative_path(bucket: tuple[str, str]) -> str:
    kind, value = bucket
    if kind == "interconnections":
        return os.path.join(_DIR_INTERCONNECTIONS, value)
    if value in {"1", "2", "3"}:
        return {
            "1": _DIR_GATE_1,
            "2": _DIR_GATE_2,
            "3": _DIR_GATE_3,
        }.get(value, _DIR_GATE_UNKNOWN)
    return _DIR_GATE_UNKNOWN


def _report_subfolder_name_for_element(element_type: str | None) -> str:
    t = (element_type or "").lower()
    if any(s in t for s in _TRANSFORMER_SUBSTRS):
        return _DIR_REPORTS_TRANSFORMERS
    if any(s in t for s in _HV_BREAKER_SUBSTRS):
        return _DIR_REPORTS_BREAKERS_HV
    if any(s in t for s in _MV_BREAKER_SUBSTRS):
        return _DIR_REPORTS_BREAKERS_MV
    return _DIR_REPORTS_OTHER


def _sanitize_element_name(name: str) -> str:
    """Compact an element name for use in a folder slug.

    Strips dashes, dots, leading/trailing spaces and collapses internal whitespace
    to a single underscore.  E.g. "Ρ-215" → "Ρ215", "Τ 101/Α" → "Τ101_Α".
    """
    text = (name or "").strip()
    # Remove forbidden Windows path characters and dashes/dots used as separators
    text = re.sub(r'[\\/:*?"<>|.\-]', "", text)
    # Collapse whitespace to underscores
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


# Substrings that identify element types by priority (Greek + English, lower-case)
_TRANSFORMER_SUBSTRS = ("μετασχηματιστ", "μ/σ", "transformer")
_HV_BREAKER_SUBSTRS  = ("διακόπτης υτ", "hv breaker")
_MV_BREAKER_SUBSTRS  = ("διακόπτης μτ", "mv breaker")

def _element_priority(element_type: str) -> int:
    """Return sort priority: 0=transformer, 1=HV breaker, 2=MV breaker, 3=other."""
    t = (element_type or "").lower()
    if any(s in t for s in _TRANSFORMER_SUBSTRS):
        return 0
    if any(s in t for s in _HV_BREAKER_SUBSTRS):
        return 1
    if any(s in t for s in _MV_BREAKER_SUBSTRS):
        return 2
    return 3


def _element_slug_for_folder(elements: list[tuple[str, str]]) -> str:
    """Build the element portion of the folder name.

    ``elements`` is a list of (element_type, element_name) tuples.
    Priority: transformer > HV breaker > MV breaker > others.
    When transformers are present only transformers are listed;
    similarly for HV/MV breakers.
    Up to 5 elements are named.
    - If exactly one extra element exists, include that element explicitly.
    - If more than one extra element exists, append "+Nmore".
    """
    if not elements:
        return ""

    sorted_elems = sorted(elements, key=lambda e: _element_priority(e[0]))
    top_priority = _element_priority(sorted_elems[0][0])

    # Keep only elements of the winning priority group
    winning = [e for e in sorted_elems if _element_priority(e[0]) == top_priority]

    MAX_SHOWN = 5
    shown = winning[:MAX_SHOWN]
    rest  = len(winning) - len(shown)

    parts = [_sanitize_element_name(name) for _, name in shown if _sanitize_element_name(name)]
    slug = "+".join(parts)
    if rest == 1:
        # Prefer explicit naming over "+1more" for readability.
        extra_name = _sanitize_element_name(winning[MAX_SHOWN][1]) if len(winning) > MAX_SHOWN else ""
        if extra_name:
            slug += f"+{extra_name}"
        else:
            slug += "+1more"
    elif rest > 1:
        slug += f"+{rest}more"
    return slug


def _instance_slug(
    date_time: str | None,
    substation_name: str | None = None,
    elements: list[tuple[str, str]] | None = None,
) -> str:
    """Build the maintenance instance folder name.

    Format: ``{YYYYMMDD_HHMM}_{substation_short}[_{element_slug}]``

    ``elements`` is a list of (element_type, element_name) tuples.
    """
    dt = None
    try:
        dt = datetime.fromisoformat((date_time or "").replace("Z", "+00:00"))
    except Exception:
        dt = None

    dt_part = dt.strftime("%Y%m%d_%H%M") if dt else datetime.now().strftime("%Y%m%d_%H%M")

    # Substation: take up to 25 chars, slug-ify
    sub_slug = ""
    if substation_name:
        safe = _safe_name(substation_name, fallback="")
        # strip parentheses content e.g. "ΔΟΞΑ (ΘΕΣΣΑΛΟΝΙΚΗ I)" → "ΔΟΞΑ ΘΕΣΣΑΛΟΝΙΚΗ I"
        safe = re.sub(r"[()]", "", safe).strip()
        safe = re.sub(r"\s+", "_", safe).strip("_")
        if len(safe) > 25:
            safe = safe[:25].rstrip("_")
        sub_slug = safe

    elem_slug = _element_slug_for_folder(elements or [])

    parts = [dt_part]
    if sub_slug:
        parts.append(sub_slug)
    if elem_slug:
        parts.append(elem_slug)
    return "_".join(parts)


def _instance_slug_short_fallback(
    date_time: str | None,
    substation_name: str | None,
    maintenance_id: int,
) -> str:
    """Compact fallback instance name for long-path edge cases."""
    dt = None
    try:
        dt = datetime.fromisoformat((date_time or "").replace("Z", "+00:00"))
    except Exception:
        dt = None
    dt_part = dt.strftime("%Y%m%d_%H%M") if dt else datetime.now().strftime("%Y%m%d_%H%M")

    sub = _safe_name(substation_name or "", fallback="substation")
    sub = re.sub(r"[()]", "", sub)
    sub = re.sub(r"\s+", "_", sub).strip("_")
    if len(sub) > 16:
        sub = sub[:16].rstrip("_")

    return f"{dt_part}_{sub}_M{maintenance_id}"


def _append_graph_queue(shared_root: str, payload: dict) -> None:
    queue_dir = os.path.join(shared_root, "_queue")
    os.makedirs(queue_dir, exist_ok=True)
    queue_file = os.path.join(queue_dir, "graph_jobs.jsonl")
    with open(queue_file, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _ensure_dir(path: str, *, queue_on_fail: bool = True, queue_payload: dict | None = None) -> None:
    try:
        os.makedirs(path, exist_ok=True)
    except Exception as exc:
        if queue_on_fail and queue_payload:
            if "path" not in queue_payload:
                queue_payload = dict(queue_payload)
                queue_payload["path"] = path
            _append_graph_queue(queue_payload.get("shared_root", path), queue_payload)
        raise RuntimeError(
            S["MESSAGES"].get(
                "ONEDRIVE_FOLDER_CREATE_FAILED_FMT",
                "Failed to create folder: {path}\n{error}",
            ).format(path=path, error=str(exc))
        ) from exc


def get_hybrid_queue_file(db_path: str | None = None) -> str:
    shared_root = resolve_shared_root(db_path)
    return os.path.join(shared_root, "_queue", "graph_jobs.jsonl")


def process_hybrid_queue(db_path: str | None = None, *, max_jobs: int = 100) -> dict:
    """Retry queued local/graph folder jobs.

    Current behavior retries local path creation jobs. Graph API execution can be
    added on top of this queue format later.
    """
    queue_file = get_hybrid_queue_file(db_path)
    if not os.path.exists(queue_file):
        return {
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "remaining": 0,
        }

    with open(queue_file, "r", encoding="utf-8") as fh:
        lines = [ln.strip() for ln in fh if ln.strip()]

    processed = 0
    succeeded = 0
    failed = 0
    remaining_rows = []

    for raw in lines:
        if processed >= max_jobs:
            remaining_rows.append(raw)
            continue

        processed += 1
        try:
            job = json.loads(raw)
        except Exception:
            failed += 1
            continue

        path = (job.get("path") or "").strip()
        if not path:
            failed += 1
            remaining_rows.append(raw)
            continue

        try:
            os.makedirs(path, exist_ok=True)
            succeeded += 1
        except Exception:
            failed += 1
            remaining_rows.append(raw)

    with open(queue_file, "w", encoding="utf-8") as fh:
        for row in remaining_rows:
            fh.write(row + "\n")

    return {
        "processed": processed,
        "succeeded": succeeded,
        "failed": failed,
        "remaining": len(remaining_rows),
    }


def _copy_media_to_targets(source_paths: Iterable[str], target_folders: Iterable[str]) -> int:
    copied = 0
    targets = [t for t in target_folders if t]
    for src in source_paths or []:
        if not src:
            continue
        try:
            src_path = Path(src)
            if not src_path.exists() or not src_path.is_file():
                continue
            if src_path.suffix.lower() not in _MEDIA_EXTENSIONS:
                continue
            for target in targets:
                os.makedirs(target, exist_ok=True)
                dest = Path(target) / src_path.name
                base = dest.stem
                ext = dest.suffix
                idx = 1
                while dest.exists():
                    dest = Path(target) / f"{base}_{idx}{ext}"
                    idx += 1
                shutil.copy2(str(src_path), str(dest))
                copied += 1
        except Exception:
            continue
    return copied


def _collect_gate_buckets(conn, element_ids: Iterable[int]) -> list[tuple[str, str]]:
    ids = [int(x) for x in (element_ids or []) if x is not None]
    if not ids:
        return []
    placeholders = ",".join(["?"] * len(ids))
    cur = conn.cursor()
    cur.execute(f"SELECT gate FROM elements WHERE id IN ({placeholders})", ids)
    rows = cur.fetchall()

    buckets = []
    seen = set()
    for row in rows:
        gate = row[0] if isinstance(row, (tuple, list)) else row["gate"]
        bucket = _bucket_for_gate(gate)
        if bucket not in seen:
            seen.add(bucket)
            buckets.append(bucket)

    if not buckets:
        buckets.append(("gate", "unknown"))
    return buckets


def ensure_substation_structure(conn, substation_id: int, *, db_path: str | None = None) -> dict:
    cur = conn.cursor()
    cur.execute("SELECT name FROM substations WHERE id=?", (substation_id,))
    row = cur.fetchone()
    if not row:
        raise RuntimeError(
            S["MESSAGES"].get(
                "SUBSTATION_FOLDER_BASE_NOT_FOUND",
                "Substation not found for folder structure creation.",
            )
        )

    substation_name = row[0] if isinstance(row, (tuple, list)) else row["name"]
    safe_substation = _safe_name(substation_name, fallback=f"substation_{substation_id}")
    shared_root = resolve_shared_root(db_path)

    queue_payload = {
        "kind": "ensure_substation_structure",
        "substation_id": substation_id,
        "substation_name": substation_name,
        "shared_root": shared_root,
        "created_at": datetime.now().isoformat(),
    }

    _ensure_dir(shared_root, queue_payload=queue_payload)
    substation_root = os.path.join(shared_root, safe_substation)
    _ensure_dir(substation_root, queue_payload=queue_payload)

    return {
        "shared_root": shared_root,
        "substation_name": substation_name,
        "substation_root": substation_root,
    }


def _is_dir_empty(path: str) -> bool:
    try:
        with os.scandir(path) as it:
            for _entry in it:
                return False
        return True
    except Exception:
        return False


def _merge_tree_into(src: str, dst: str) -> None:
    """Merge a source directory tree into destination without data loss."""
    if not os.path.isdir(src):
        return

    os.makedirs(dst, exist_ok=True)
    for name in list(os.listdir(src)):
        src_item = os.path.join(src, name)
        dst_item = os.path.join(dst, name)

        if os.path.isdir(src_item):
            if os.path.isdir(dst_item):
                _merge_tree_into(src_item, dst_item)
                try:
                    os.rmdir(src_item)
                except Exception:
                    pass
            elif os.path.exists(dst_item):
                base, ext = os.path.splitext(name)
                idx = 1
                candidate = os.path.join(dst, f"{base}_legacy{idx}{ext}")
                while os.path.exists(candidate):
                    idx += 1
                    candidate = os.path.join(dst, f"{base}_legacy{idx}{ext}")
                shutil.move(src_item, candidate)
            else:
                shutil.move(src_item, dst_item)
        else:
            if os.path.exists(dst_item):
                base, ext = os.path.splitext(name)
                idx = 1
                candidate = os.path.join(dst, f"{base}_legacy{idx}{ext}")
                while os.path.exists(candidate):
                    idx += 1
                    candidate = os.path.join(dst, f"{base}_legacy{idx}{ext}")
                shutil.move(src_item, candidate)
            else:
                shutil.move(src_item, dst_item)


def _merge_legacy_path(src: str, dst: str) -> bool:
    """Merge a legacy path into canonical path; return True when attempted."""
    if not os.path.isdir(src):
        return False

    if os.path.normcase(os.path.abspath(src)) == os.path.normcase(os.path.abspath(dst)):
        return False

    _merge_tree_into(src, dst)
    if os.path.isdir(src) and _is_dir_empty(src):
        try:
            os.rmdir(src)
        except Exception:
            try:
                shutil.rmtree(src)
            except Exception:
                pass
    return True


def _reconcile_legacy_gate_root_folders(substation_root: str) -> None:
    """Fold legacy English gate/interconnection folders into Greek folders."""
    pairs = [
        ("Gate_1", _DIR_GATE_1),
        ("Gate_2", _DIR_GATE_2),
        ("Gate_3", _DIR_GATE_3),
        ("Gate_unknown", _DIR_GATE_UNKNOWN),
        (os.path.join("Interconnections", "1-2"), os.path.join(_DIR_INTERCONNECTIONS, "1-2")),
        (os.path.join("Interconnections", "2-3"), os.path.join(_DIR_INTERCONNECTIONS, "2-3")),
    ]
    for src_rel, dst_rel in pairs:
        src = os.path.join(substation_root, src_rel)
        dst = os.path.join(substation_root, dst_rel)
        _merge_legacy_path(src, dst)

    _merge_legacy_path(
        os.path.join(substation_root, "Interconnections"),
        os.path.join(substation_root, _DIR_INTERCONNECTIONS),
    )


def _reconcile_legacy_gate_children(gate_root: str) -> None:
    """Fold legacy English gate child folders into canonical Greek folders."""
    pairs = [
        ("Maintenance", _join_parts(_DIR_MAINTENANCE_PARTS)),
        ("Inspections", _DIR_INSPECTIONS),
        ("DGA_Measurements", _join_parts(_DIR_DGA_PARTS)),
    ]
    for src_rel, dst_rel in pairs:
        src = os.path.join(gate_root, src_rel)
        dst = os.path.join(gate_root, dst_rel)
        _merge_legacy_path(src, dst)


def sync_substation_gate_folders(conn, substation_id: int, *, db_path: str | None = None) -> dict:
    """Ensure gate/interconnection folders match gates used by current elements.

    - Create folders for active gates.
    - Delete folders for inactive gates only when they are fully empty.
    """
    base = ensure_substation_structure(conn, substation_id, db_path=db_path)
    substation_root = base["substation_root"]
    _reconcile_legacy_gate_root_folders(substation_root)

    cur = conn.cursor()
    cur.execute("SELECT gate FROM elements WHERE substation_id=?", (substation_id,))
    rows = cur.fetchall() or []

    active_buckets = []
    seen = set()
    for row in rows:
        gate = row[0] if isinstance(row, (tuple, list)) else row["gate"]
        bucket = _bucket_for_gate(gate)
        if bucket not in seen:
            seen.add(bucket)
            active_buckets.append(bucket)

    created = []
    for bucket in active_buckets:
        gate_rel = _gate_relative_path(bucket)
        gate_root = os.path.join(substation_root, gate_rel)
        _reconcile_legacy_gate_children(gate_root)
        _ensure_dir(gate_root, queue_payload={"shared_root": base["shared_root"], "kind": "sync_gate", "substation_id": substation_id})
        _ensure_dir(os.path.join(gate_root, _join_parts(_DIR_MAINTENANCE_PARTS)), queue_payload={"shared_root": base["shared_root"], "kind": "sync_gate", "substation_id": substation_id})
        _ensure_dir(os.path.join(gate_root, _DIR_INSPECTIONS), queue_payload={"shared_root": base["shared_root"], "kind": "sync_gate", "substation_id": substation_id})
        _ensure_dir(os.path.join(gate_root, _join_parts(_DIR_DGA_PARTS)), queue_payload={"shared_root": base["shared_root"], "kind": "sync_gate", "substation_id": substation_id})
        created.append(gate_rel)

    active_rel = { _gate_relative_path(b) for b in active_buckets }

    removed = []
    known_candidates = [
        _DIR_GATE_1,
        _DIR_GATE_2,
        _DIR_GATE_3,
        _DIR_GATE_UNKNOWN,
        os.path.join(_DIR_INTERCONNECTIONS, "1-2"),
        os.path.join(_DIR_INTERCONNECTIONS, "2-3"),
        "Gate_1",
        "Gate_2",
        "Gate_3",
        "Gate_unknown",
        os.path.join("Interconnections", "1-2"),
        os.path.join("Interconnections", "2-3"),
    ]
    for rel in known_candidates:
        if rel in active_rel:
            continue
        candidate = os.path.join(substation_root, rel)
        if not os.path.isdir(candidate):
            continue

        # Delete only when all nested folders are empty to protect data.
        can_remove = True
        for root, dirs, files in os.walk(candidate, topdown=False):
            if files:
                can_remove = False
                break
            for d in dirs:
                dpath = os.path.join(root, d)
                if not _is_dir_empty(dpath):
                    can_remove = False
                    break
            if not can_remove:
                break

        if can_remove:
            try:
                shutil.rmtree(candidate)
                removed.append(rel)
            except Exception:
                pass

    # Remove Interconnections parent if empty
    for inter_dir in (_DIR_INTERCONNECTIONS, "Interconnections"):
        interconnections_root = os.path.join(substation_root, inter_dir)
        if os.path.isdir(interconnections_root) and _is_dir_empty(interconnections_root):
            try:
                os.rmdir(interconnections_root)
            except Exception:
                pass

    return {
        "created_or_ensured": created,
        "removed_empty": removed,
        "substation_root": substation_root,
    }


def ensure_maintenance_folders(
    conn,
    *,
    maintenance_id: int,
    substation_id: int,
    maintenance_name: str,
    maintenance_type: str,
    date_time: str,
    element_ids: Iterable[int],
    attachment_paths: Iterable[str] | None = None,
    db_path: str | None = None,
) -> dict:
    base = ensure_substation_structure(conn, substation_id, db_path=db_path)
    substation_root = base["substation_root"]
    shared_root = base["shared_root"]

    element_ids = list(element_ids)
    gate_buckets = _collect_gate_buckets(conn, element_ids)

    # Resolve substation name for folder naming
    cur = conn.cursor()
    cur.execute("SELECT name FROM substations WHERE id=?", (substation_id,))
    row = cur.fetchone()
    substation_name_for_slug = row[0] if row else None

    # Resolve element types + names for folder naming (only if IDs provided)
    elements_for_slug: list[tuple[str, str]] = []
    if element_ids:
        placeholders = ",".join("?" * len(element_ids))
        cur.execute(
            f"SELECT element_type, name FROM elements WHERE id IN ({placeholders})",
            element_ids,
        )
        elements_for_slug = [(r[0] or "", r[1] or "") for r in cur.fetchall()]

    instance_name = _instance_slug(
        date_time,
        substation_name=substation_name_for_slug,
        elements=elements_for_slug,
    )

    cur = conn.cursor()
    cur.execute(
        """
        SELECT gate_key, instance_folder, media_folder, reports_folder
        FROM maintenance_storage_paths
        WHERE maintenance_id=?
        """,
        (maintenance_id,),
    )
    existing_rows = cur.fetchall() or []
    existing_by_gate_key = {}
    for row in existing_rows:
        gate_key = row[0] if isinstance(row, (tuple, list)) else row["gate_key"]
        instance_folder = row[1] if isinstance(row, (tuple, list)) else row["instance_folder"]
        media_folder = row[2] if isinstance(row, (tuple, list)) else row["media_folder"]
        reports_folder = row[3] if isinstance(row, (tuple, list)) else row["reports_folder"]
        existing_by_gate_key[gate_key] = {
            "instance_folder": _remap_legacy_shared_root(instance_folder, shared_root),
            "media_folder": _remap_legacy_shared_root(media_folder, shared_root),
            "reports_folder": _remap_legacy_shared_root(reports_folder, shared_root),
        }

    created_rows = []
    media_targets = []

    for bucket in gate_buckets:
        gate_rel = _gate_relative_path(bucket)
        gate_key = f"{bucket[0]}:{bucket[1]}"
        gate_root = os.path.join(substation_root, gate_rel)
        _reconcile_legacy_gate_children(gate_root)
        maintenance_root = os.path.join(gate_root, _join_parts(_DIR_MAINTENANCE_PARTS))
        inspections_root = os.path.join(gate_root, _DIR_INSPECTIONS)
        dga_root = os.path.join(gate_root, _join_parts(_DIR_DGA_PARTS))

        queue_payload = {
            "kind": "ensure_gate_structure",
            "maintenance_id": maintenance_id,
            "substation_id": substation_id,
            "gate": gate_rel,
            "shared_root": shared_root,
            "created_at": datetime.now().isoformat(),
        }

        _ensure_dir(gate_root, queue_payload=queue_payload)
        _ensure_dir(maintenance_root, queue_payload=queue_payload)
        _ensure_dir(inspections_root, queue_payload=queue_payload)
        _ensure_dir(dga_root, queue_payload=queue_payload)

        existing = existing_by_gate_key.get(gate_key) or {}
        instance_root = existing.get("instance_folder") or os.path.join(
            maintenance_root, instance_name
        )
        reports_root = existing.get("reports_folder") or os.path.join(
            instance_root, _DIR_REPORTS
        )
        reports_breakers_hv = os.path.join(reports_root, _DIR_REPORTS_BREAKERS_HV)
        reports_breakers_mv = os.path.join(reports_root, _DIR_REPORTS_BREAKERS_MV)
        reports_transformers = os.path.join(reports_root, _DIR_REPORTS_TRANSFORMERS)
        reports_other = os.path.join(reports_root, _DIR_REPORTS_OTHER)
        media_root = existing.get("media_folder") or os.path.join(
            instance_root, _DIR_MEDIA
        )

        _ensure_dir(instance_root, queue_payload=queue_payload)
        _ensure_dir(reports_root, queue_payload=queue_payload)
        _ensure_dir(reports_breakers_hv, queue_payload=queue_payload)
        _ensure_dir(reports_breakers_mv, queue_payload=queue_payload)
        _ensure_dir(reports_transformers, queue_payload=queue_payload)
        _ensure_dir(reports_other, queue_payload=queue_payload)
        _ensure_dir(media_root, queue_payload=queue_payload)

        media_targets.append(media_root)
        created_rows.append(
            {
                "gate_key": gate_key,
                "gate_folder": gate_rel,
                "instance_folder": instance_root,
                "media_folder": media_root,
                "reports_folder": reports_root,
            }
        )

    copied_count = _copy_media_to_targets(attachment_paths or [], media_targets)

    cur = conn.cursor()
    for row in created_rows:
        cur.execute(
            """
            INSERT INTO maintenance_storage_paths
            (maintenance_id, gate_key, gate_folder, instance_folder, media_folder, reports_folder, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(maintenance_id, gate_key) DO UPDATE SET
                gate_folder=excluded.gate_folder,
                instance_folder=excluded.instance_folder,
                media_folder=excluded.media_folder,
                reports_folder=excluded.reports_folder
            """,
            (
                maintenance_id,
                row["gate_key"],
                row["gate_folder"],
                row["instance_folder"],
                row["media_folder"],
                row["reports_folder"],
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )

    primary_media = created_rows[0]["media_folder"] if created_rows else None
    return {
        "primary_media_folder": primary_media,
        "folders": created_rows,
        "copied_media_count": copied_count,
        "instance_name": instance_name,
    }


def get_transformer_report_targets(
    conn,
    *,
    maintenance_id: int,
    gate_value: str | None,
    db_path: str | None = None,
) -> list[str]:
    """Return ensured Reports folders for a maintenance instance.

    Prefers rows matching the specific gate bucket. Falls back to all stored rows for
    the maintenance when gate mapping is unavailable. Callers should append a report
    subfolder selected by ``_report_subfolder_name_for_element``.
    """
    bucket = _bucket_for_gate(gate_value)
    gate_key = f"{bucket[0]}:{bucket[1]}"
    cur = conn.cursor()

    cur.execute(
        """
        SELECT reports_folder
        FROM maintenance_storage_paths
        WHERE maintenance_id=? AND gate_key=?
        """,
        (maintenance_id, gate_key),
    )
    rows = cur.fetchall() or []

    if not rows:
        cur.execute(
            """
            SELECT reports_folder
            FROM maintenance_storage_paths
            WHERE maintenance_id=?
            """,
            (maintenance_id,),
        )
        rows = cur.fetchall() or []

    shared_root = resolve_shared_root(db_path)
    queue_payload = {
        "kind": "ensure_reports_root",
        "maintenance_id": maintenance_id,
        "gate_key": gate_key,
        "shared_root": shared_root,
        "created_at": datetime.now().isoformat(),
    }

    targets: list[str] = []
    seen: set[str] = set()
    for row in rows:
        reports_root_raw = row[0] if isinstance(row, (tuple, list)) else row["reports_folder"]
        reports_root = _remap_legacy_shared_root(reports_root_raw, shared_root)
        if not reports_root:
            continue
        if reports_root in seen:
            continue
        _ensure_dir(reports_root, queue_payload=queue_payload)
        seen.add(reports_root)
        targets.append(reports_root)

    return targets


def ensure_dga_folder(
    conn,
    *,
    substation_id: int,
    gate_value: str | None,
    element_name: str,
    measurement_date: str | None,
    db_path: str | None = None,
) -> dict:
    base = ensure_substation_structure(conn, substation_id, db_path=db_path)
    substation_root = base["substation_root"]
    shared_root = base["shared_root"]

    bucket = _bucket_for_gate(gate_value)
    gate_rel = _gate_relative_path(bucket)
    gate_root = os.path.join(substation_root, gate_rel)
    dga_root = os.path.join(gate_root, _join_parts(_DIR_DGA_PARTS))

    queue_payload = {
        "kind": "ensure_dga_folder",
        "substation_id": substation_id,
        "gate": gate_rel,
        "shared_root": shared_root,
        "created_at": datetime.now().isoformat(),
    }

    _ensure_dir(gate_root, queue_payload=queue_payload)
    _ensure_dir(dga_root, queue_payload=queue_payload)

    try:
        dt = datetime.fromisoformat((measurement_date or "").replace("Z", "+00:00"))
        dt_part = dt.strftime("%Y%m%d")
    except Exception:
        dt_part = datetime.now().strftime("%Y%m%d")

    folder_name = f"{dt_part}_{_slug(element_name, fallback='transformer')}"
    folder_path = os.path.join(dga_root, folder_name)
    _ensure_dir(folder_path, queue_payload=queue_payload)

    raw_data = os.path.join(folder_path, "Raw_Data")
    _ensure_dir(raw_data, queue_payload=queue_payload)

    return {
        "gate_folder": gate_rel,
        "dga_root": dga_root,
        "folder_path": folder_path,
        "raw_data_path": raw_data,
    }


def delete_maintenance_folders(conn, maintenance_id: int) -> int:
    cur = conn.cursor()
    cur.execute(
        "SELECT instance_folder FROM maintenance_storage_paths WHERE maintenance_id=?",
        (maintenance_id,),
    )
    rows = cur.fetchall() or []

    deleted = 0
    for row in rows:
        path = row[0] if isinstance(row, (tuple, list)) else row["instance_folder"]
        if not path:
            continue
        try:
            if os.path.isdir(path):
                shutil.rmtree(path)
                deleted += 1
        except Exception:
            continue

    cur.execute("DELETE FROM maintenance_storage_paths WHERE maintenance_id=?", (maintenance_id,))
    return deleted


def upsert_maintenance_report_path(
    conn,
    *,
    maintenance_id: int,
    element_id: int,
    report_path: str,
    report_type: str = "pdf",
) -> None:
    """Persist report path for a maintenance-element pair."""
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        """
        INSERT INTO maintenance_report_paths
        (maintenance_id, element_id, report_type, report_path, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(maintenance_id, element_id, report_type) DO UPDATE SET
            report_path=excluded.report_path,
            updated_at=excluded.updated_at
        """,
        (maintenance_id, element_id, report_type, report_path, now, now),
    )


def get_maintenance_report_path(
    conn,
    *,
    maintenance_id: int,
    element_id: int,
    report_type: str = "pdf",
    verify_exists: bool = True,
) -> str | None:
    """Return tracked report path for a maintenance-element pair."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT report_path
        FROM maintenance_report_paths
        WHERE maintenance_id=? AND element_id=? AND report_type=?
        """,
        (maintenance_id, element_id, report_type),
    )
    row = cur.fetchone()
    if not row:
        return None
    path = row[0] if isinstance(row, (tuple, list)) else row["report_path"]
    if verify_exists and (not path or not os.path.exists(path)):
        return None
    return path


def relink_existing_maintenance_assets(conn, *, db_path: str | None = None, progress_callback = None) -> dict:
    """Relink existing folder/media/report paths into DB if missing.

    This does not create new files. It discovers existing paths under maintained
    folder structures and stores missing DB links.
    
    Args:
        conn: Database connection
        db_path: Path to database file
        progress_callback: Optional callable(operation, substation, current, total) for progress
    """
    cur = conn.cursor()

    # Relink media folder link on maintenance table when missing.
    cur.execute(
        """
        SELECT m.id, m.onedrive_media_folder_link, msp.media_folder, s.name
        FROM maintenance m
        JOIN maintenance_storage_paths msp ON msp.maintenance_id = m.id
        JOIN substations s ON s.id = m.substation_id
        ORDER BY m.id
        """
    )
    media_rows = cur.fetchall() or []
    media_linked = 0
    seen_media = set()
    current_work = 0
    
    for row in media_rows:
        maintenance_id = row[0] if isinstance(row, (tuple, list)) else row["id"]
        existing_link = row[1] if isinstance(row, (tuple, list)) else row["onedrive_media_folder_link"]
        media_folder = row[2] if isinstance(row, (tuple, list)) else row["media_folder"]
        substation_name = row[3] if isinstance(row, (tuple, list)) else row["name"]
        
        current_work += 1
        if progress_callback:
            progress_callback(
                operation="Relinking media folders",
                substation=substation_name,
                current=current_work,
                total=total_work
            )
        
        if maintenance_id in seen_media:
            continue
        seen_media.add(maintenance_id)
        if existing_link:
            continue
        if media_folder and os.path.isdir(media_folder):
            cur.execute(
                "UPDATE maintenance SET onedrive_media_folder_link=? WHERE id=?",
                (media_folder, maintenance_id),
            )
            media_linked += 1

    # Relink maintenance PDFs into maintenance_report_paths.
    cur.execute(
        """
        SELECT m.id, me.element_id, e.name, e.element_type, e.gate, s.name
        FROM maintenance m
        JOIN maintenance_elements me ON me.maintenance_id = m.id
        JOIN elements e ON e.id = me.element_id
        JOIN substations s ON s.id = m.substation_id
        ORDER BY m.id DESC
        """
    )
    rows = cur.fetchall() or []
    # total_work now covers the media phase (one tick per row) plus the report
    # phase (one tick per 5 rows, rounded up), so current never exceeds total.
    total_work = len(media_rows) + (len(rows) + 4) // 5
    report_linked = 0
    report_already = 0
    report_missing = 0

    for idx, row in enumerate(rows):
        maintenance_id = row[0] if isinstance(row, (tuple, list)) else row["id"]
        element_id = row[1] if isinstance(row, (tuple, list)) else row["element_id"]
        element_name = row[2] if isinstance(row, (tuple, list)) else row["name"]
        element_type = row[3] if isinstance(row, (tuple, list)) else row["element_type"]
        gate = row[4] if isinstance(row, (tuple, list)) else row["gate"]
        substation_name = row[5] if isinstance(row, (tuple, list)) else row["name"]
        
        if progress_callback and idx % 5 == 0:  # Update every 5 records to avoid too many UI updates
            progress_callback(
                operation="Relinking report files",
                substation=substation_name,
                current=current_work + (idx // 5),
                total=total_work
            )

        tracked = get_maintenance_report_path(
            conn,
            maintenance_id=maintenance_id,
            element_id=element_id,
            report_type="pdf",
            verify_exists=True,
        )
        if tracked:
            report_already += 1
            continue

        targets = get_transformer_report_targets(
            conn,
            maintenance_id=maintenance_id,
            gate_value=gate,
            db_path=db_path,
        )
        if not targets:
            report_missing += 1
            continue

        reports_root = targets[0]
        subfolder = os.path.join(reports_root, _report_subfolder_name_for_element(element_type))
        if not os.path.isdir(subfolder):
            report_missing += 1
            continue

        safe_name = (element_name or "").replace("/", "-").replace("\\", "-").replace(":", "-")
        canonical = os.path.join(subfolder, f"Maintenance_M{maintenance_id}_E{element_id}_{safe_name}.pdf")

        found_path = canonical if os.path.isfile(canonical) else None
        if not found_path:
            legacy_matches = []
            prefix = f"Maintenance_{safe_name}_"
            try:
                for fname in os.listdir(subfolder):
                    if fname.lower().endswith(".pdf") and fname.startswith(prefix):
                        legacy_matches.append(os.path.join(subfolder, fname))
            except Exception:
                legacy_matches = []
            if legacy_matches:
                legacy_matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)
                found_path = legacy_matches[0]

        if not found_path:
            report_missing += 1
            continue

        upsert_maintenance_report_path(
            conn,
            maintenance_id=maintenance_id,
            element_id=element_id,
            report_type="pdf",
            report_path=found_path,
        )
        report_linked += 1

    return {
        "media_linked": media_linked,
        "reports_linked": report_linked,
        "reports_already": report_already,
        "reports_missing": report_missing,
    }


def _replace_prefix_ci(path: str | None, old_prefix: str | None, new_prefix: str | None) -> str | None:
    """Replace path prefix with case-insensitive matching (Windows friendly)."""
    if not path or not old_prefix or not new_prefix:
        return path
    try:
        p = os.path.abspath(path)
        oldp = os.path.abspath(old_prefix)
        newp = os.path.abspath(new_prefix)
        p_norm = os.path.normcase(p)
        old_norm = os.path.normcase(oldp)
        if p_norm == old_norm:
            return newp
        old_pref = old_norm + os.sep
        if p_norm.startswith(old_pref):
            tail = p[len(oldp) :].lstrip("\\/")
            return os.path.join(newp, tail)
    except Exception:
        return path
    return path


def retrofit_maintenance_instance_folder_names(
    conn,
    *,
    db_path: str | None = None,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict:
    """Rename existing maintenance instance folders to the new naming scheme.

    - Recomputes target instance name with current ``_instance_slug`` logic.
    - Renames existing folders when needed.
    - Rewrites related DB paths in:
      maintenance_storage_paths, maintenance.onedrive_media_folder_link,
      maintenance_report_paths.report_path.

    Returns migration statistics.
    """
    shared_root = resolve_shared_root(db_path)
    cur = conn.cursor()

    q = """
        SELECT m.id, m.substation_id, m.date_time, s.name
        FROM maintenance m
        JOIN substations s ON s.id = m.substation_id
        WHERE EXISTS (
            SELECT 1 FROM maintenance_storage_paths msp WHERE msp.maintenance_id = m.id
        )
        ORDER BY m.id
    """
    if limit:
        q += f" LIMIT {int(limit)}"
    cur.execute(q)
    maint_rows = cur.fetchall() or []

    scanned = 0
    renamed_folders = 0
    folder_conflicts = 0
    storage_rows_updated = 0
    maintenance_links_updated = 0
    report_paths_updated = 0
    errors = []

    for row in maint_rows:
        scanned += 1
        maintenance_id = row[0] if isinstance(row, (tuple, list)) else row["id"]
        substation_id = row[1] if isinstance(row, (tuple, list)) else row["substation_id"]
        date_time = row[2] if isinstance(row, (tuple, list)) else row["date_time"]
        substation_name = row[3] if isinstance(row, (tuple, list)) else row["name"]

        cur.execute(
            """
            SELECT DISTINCT e.element_type, e.name
            FROM maintenance_elements me
            JOIN elements e ON e.id = me.element_id
            WHERE me.maintenance_id = ?
            """,
            (maintenance_id,),
        )
        elements = [(r[0] or "", r[1] or "") for r in (cur.fetchall() or [])]
        target_instance_name = _instance_slug(
            date_time,
            substation_name=substation_name,
            elements=elements,
        )

        cur.execute(
            """
            SELECT gate_key, instance_folder, media_folder, reports_folder
            FROM maintenance_storage_paths
            WHERE maintenance_id = ?
            """,
            (maintenance_id,),
        )
        path_rows = cur.fetchall() or []

        for prow in path_rows:
            gate_key = prow[0] if isinstance(prow, (tuple, list)) else prow["gate_key"]
            old_instance_raw = prow[1] if isinstance(prow, (tuple, list)) else prow["instance_folder"]
            old_media_raw = prow[2] if isinstance(prow, (tuple, list)) else prow["media_folder"]
            old_reports_raw = prow[3] if isinstance(prow, (tuple, list)) else prow["reports_folder"]

            old_instance_mapped = _remap_legacy_shared_root(old_instance_raw, shared_root)
            old_media_mapped = _remap_legacy_shared_root(old_media_raw, shared_root)
            old_reports_mapped = _remap_legacy_shared_root(old_reports_raw, shared_root)

            instance_parent = os.path.dirname(old_instance_mapped or old_instance_raw or "")
            if not instance_parent:
                continue
            target_instance = os.path.join(instance_parent, target_instance_name)

            current_base = os.path.basename(os.path.normpath(old_instance_mapped or old_instance_raw or ""))
            needs_rename = current_base != target_instance_name

            # Resolve collisions by adding maintenance id suffix.
            final_target = target_instance
            if needs_rename and os.path.exists(final_target):
                same = os.path.normcase(os.path.abspath(final_target)) == os.path.normcase(
                    os.path.abspath(old_instance_mapped or old_instance_raw or final_target)
                )
                if not same:
                    folder_conflicts += 1
                    final_target = f"{target_instance}_M{maintenance_id}"

            # Choose source path to rename (prefer mapped new-root path).
            source_path = None
            for candidate in [old_instance_mapped, old_instance_raw]:
                if candidate and os.path.isdir(candidate):
                    source_path = candidate
                    break

            # If DB already points to a renamed/missing path, try discovering a
            # legacy Email_instance_* folder for this maintenance under the same
            # Maintenance root.
            if needs_rename and not source_path and instance_parent and os.path.isdir(instance_parent):
                try:
                    legacy_suffix = f"Email_instance_{maintenance_id}"
                    for name in os.listdir(instance_parent):
                        cand = os.path.join(instance_parent, name)
                        if os.path.isdir(cand) and name.endswith(legacy_suffix):
                            source_path = cand
                            break
                except Exception:
                    pass

            if needs_rename and source_path and os.path.normcase(os.path.abspath(source_path)) != os.path.normcase(os.path.abspath(final_target)):
                try:
                    if not dry_run:
                        os.makedirs(os.path.dirname(final_target), exist_ok=True)
                        shutil.move(source_path, final_target)
                    renamed_folders += 1
                except Exception as exc:
                    errors.append(f"maintenance {maintenance_id} gate {gate_key}: {exc}")
                    # Retry with a compact fallback name to avoid long-path errors.
                    try:
                        fallback_name = _instance_slug_short_fallback(
                            date_time,
                            substation_name,
                            maintenance_id,
                        )
                        fallback_target = os.path.join(instance_parent, fallback_name)
                        if fallback_target != final_target and not os.path.exists(fallback_target):
                            if not dry_run:
                                os.makedirs(os.path.dirname(fallback_target), exist_ok=True)
                                shutil.move(source_path, fallback_target)
                            renamed_folders += 1
                            final_target = fallback_target
                    except Exception:
                        # Keep going so DB links can still be normalized away from
                        # legacy naming even when the old folder is missing.
                        pass

            # Compute updated DB paths by prefix replacement from old->new.
            new_instance = final_target if needs_rename else (old_instance_mapped or old_instance_raw)
            new_media = _replace_prefix_ci(old_media_mapped or old_media_raw, old_instance_mapped or old_instance_raw, new_instance)
            new_reports = _replace_prefix_ci(old_reports_mapped or old_reports_raw, old_instance_mapped or old_instance_raw, new_instance)

            if (
                (new_instance or "") != (old_instance_raw or "")
                or (new_media or "") != (old_media_raw or "")
                or (new_reports or "") != (old_reports_raw or "")
            ):
                if not dry_run:
                    cur.execute(
                        """
                        UPDATE maintenance_storage_paths
                        SET instance_folder=?, media_folder=?, reports_folder=?
                        WHERE maintenance_id=? AND gate_key=?
                        """,
                        (new_instance, new_media, new_reports, maintenance_id, gate_key),
                    )
                storage_rows_updated += 1

            # Update primary media link in maintenance table for this maintenance.
            cur.execute(
                "SELECT onedrive_media_folder_link FROM maintenance WHERE id=?",
                (maintenance_id,),
            )
            mrow = cur.fetchone()
            old_link = mrow[0] if mrow and isinstance(mrow, (tuple, list)) else (mrow["onedrive_media_folder_link"] if mrow else None)
            new_link = _replace_prefix_ci(old_link, old_instance_raw, new_instance)
            new_link = _replace_prefix_ci(new_link, old_instance_mapped, new_instance)
            if (new_link or "") != (old_link or ""):
                if not dry_run:
                    cur.execute(
                        "UPDATE maintenance SET onedrive_media_folder_link=? WHERE id=?",
                        (new_link, maintenance_id),
                    )
                maintenance_links_updated += 1

            # Update tracked report paths for this maintenance.
            cur.execute(
                "SELECT id, report_path FROM maintenance_report_paths WHERE maintenance_id=?",
                (maintenance_id,),
            )
            rrows = cur.fetchall() or []
            for rrow in rrows:
                rid = rrow[0] if isinstance(rrow, (tuple, list)) else rrow["id"]
                old_report_path = rrow[1] if isinstance(rrow, (tuple, list)) else rrow["report_path"]
                new_report_path = _replace_prefix_ci(old_report_path, old_instance_raw, new_instance)
                new_report_path = _replace_prefix_ci(new_report_path, old_instance_mapped, new_instance)
                if (new_report_path or "") != (old_report_path or ""):
                    if not dry_run:
                        cur.execute(
                            "UPDATE maintenance_report_paths SET report_path=?, updated_at=? WHERE id=?",
                            (new_report_path, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), rid),
                        )
                    report_paths_updated += 1

    if not dry_run:
        conn.commit()

    return {
        "scanned": scanned,
        "renamed_folders": renamed_folders,
        "folder_conflicts": folder_conflicts,
        "storage_rows_updated": storage_rows_updated,
        "maintenance_links_updated": maintenance_links_updated,
        "report_paths_updated": report_paths_updated,
        "errors": errors,
    }


def _map_folder_labels_in_path(path: str | None, *, element_type: str | None = None) -> str | None:
    """Map legacy English folder labels in a Windows path to canonical Greek labels."""
    if not path:
        return path
    try:
        drive, tail = os.path.splitdrive(path)
        parts = [p for p in re.split(r"[\\/]+", tail.strip("\\/")) if p]
        mapped: list[str] = []
        for i, part in enumerate(parts):
            low = part.lower()
            if low == "gate_1":
                mapped.append(_DIR_GATE_1)
            elif low == "gate_2":
                mapped.append(_DIR_GATE_2)
            elif low == "gate_3":
                mapped.append(_DIR_GATE_3)
            elif low == "gate_unknown":
                mapped.append(_DIR_GATE_UNKNOWN)
            elif low == "interconnections":
                mapped.append(_DIR_INTERCONNECTIONS)
            elif low == "maintenance":
                mapped.extend(_DIR_MAINTENANCE_PARTS)
            elif low == "inspections":
                mapped.append(_DIR_INSPECTIONS)
            elif low == "dga_measurements":
                mapped.extend(_DIR_DGA_PARTS)
            elif low == "photos_videos":
                mapped.append(_DIR_MEDIA)
            elif low == "reports":
                mapped.append(_DIR_REPORTS)
            elif low == "transformers":
                mapped.append(_DIR_REPORTS_TRANSFORMERS)
            elif low == "other":
                mapped.append(_DIR_REPORTS_OTHER)
            elif low == "breakers":
                if element_type:
                    mapped.append(_report_subfolder_name_for_element(element_type))
                else:
                    # Filesystem-only retrofits may not know element_type.
                    # Infer from nearby path parts and default to HV breakers.
                    tail_low = " ".join(p.lower() for p in parts[i + 1 :])
                    if ("μτ" in tail_low) or (" mt" in tail_low) or ("mv" in tail_low):
                        mapped.append(_DIR_REPORTS_BREAKERS_MV)
                    else:
                        mapped.append(_DIR_REPORTS_BREAKERS_HV)
            else:
                mapped.append(part)

        return (drive + os.sep if drive else "") + os.sep.join(mapped)
    except Exception:
        return path


def retrofit_folder_labels_to_greek(
    conn,
    *,
    db_path: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Retrospectively convert English storage folder labels to Greek labels."""
    cur = conn.cursor()
    scanned = 0
    moved = 0
    updated_storage = 0
    updated_media_links = 0
    updated_report_paths = 0
    errors: list[str] = []

    cur.execute(
        """
        SELECT maintenance_id, gate_key, instance_folder, media_folder, reports_folder
        FROM maintenance_storage_paths
        ORDER BY maintenance_id, gate_key
        """
    )
    rows = cur.fetchall() or []

    for row in rows:
        scanned += 1
        maintenance_id = row[0] if isinstance(row, (tuple, list)) else row["maintenance_id"]
        gate_key = row[1] if isinstance(row, (tuple, list)) else row["gate_key"]
        old_instance = row[2] if isinstance(row, (tuple, list)) else row["instance_folder"]
        old_media = row[3] if isinstance(row, (tuple, list)) else row["media_folder"]
        old_reports = row[4] if isinstance(row, (tuple, list)) else row["reports_folder"]

        new_instance = _map_folder_labels_in_path(old_instance)
        new_media = _map_folder_labels_in_path(old_media)
        new_reports = _map_folder_labels_in_path(old_reports)

        try:
            if old_instance and new_instance and os.path.normcase(os.path.abspath(old_instance)) != os.path.normcase(os.path.abspath(new_instance)):
                if os.path.isdir(old_instance):
                    if not dry_run:
                        os.makedirs(os.path.dirname(new_instance), exist_ok=True)
                        if not os.path.exists(new_instance):
                            shutil.move(old_instance, new_instance)
                    moved += 1
        except Exception as exc:
            errors.append(f"maintenance {maintenance_id} gate {gate_key}: {exc}")

        if (
            (new_instance or "") != (old_instance or "")
            or (new_media or "") != (old_media or "")
            or (new_reports or "") != (old_reports or "")
        ):
            if not dry_run:
                cur.execute(
                    """
                    UPDATE maintenance_storage_paths
                    SET instance_folder=?, media_folder=?, reports_folder=?
                    WHERE maintenance_id=? AND gate_key=?
                    """,
                    (new_instance, new_media, new_reports, maintenance_id, gate_key),
                )
            updated_storage += 1

    cur.execute("SELECT id, onedrive_media_folder_link FROM maintenance")
    for row in cur.fetchall() or []:
        mid = row[0] if isinstance(row, (tuple, list)) else row["id"]
        old_link = row[1] if isinstance(row, (tuple, list)) else row["onedrive_media_folder_link"]
        new_link = _map_folder_labels_in_path(old_link)
        if (new_link or "") != (old_link or ""):
            if not dry_run:
                cur.execute(
                    "UPDATE maintenance SET onedrive_media_folder_link=? WHERE id=?",
                    (new_link, mid),
                )
            updated_media_links += 1

    cur.execute(
        """
        SELECT mrp.id, mrp.report_path, e.element_type
        FROM maintenance_report_paths mrp
        JOIN elements e ON e.id = mrp.element_id
        """
    )
    for row in cur.fetchall() or []:
        rid = row[0] if isinstance(row, (tuple, list)) else row["id"]
        old_path = row[1] if isinstance(row, (tuple, list)) else row["report_path"]
        elem_type = row[2] if isinstance(row, (tuple, list)) else row["element_type"]
        new_path = _map_folder_labels_in_path(old_path, element_type=elem_type)
        if (new_path or "") != (old_path or ""):
            if not dry_run:
                cur.execute(
                    "UPDATE maintenance_report_paths SET report_path=?, updated_at=? WHERE id=?",
                    (new_path, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), rid),
                )
            updated_report_paths += 1

    if not dry_run:
        conn.commit()

    return {
        "scanned": scanned,
        "moved": moved,
        "updated_storage": updated_storage,
        "updated_media_links": updated_media_links,
        "updated_report_paths": updated_report_paths,
        "errors": errors,
    }


def sync_all_substation_structures(conn, *, db_path: str | None = None, quiet: bool = True, progress_callback = None) -> dict:
    """Ensure folder structure exists for all substations with elements.
    
    This creates the OneDrive folder hierarchy for all substations that have
    registered elements, ensuring the structure is ready for reports, maintenance
    records, inspections, and DGA measurements.
    
    Args:
        conn: Database connection
        db_path: Path to database file (for resolving shared root)
        quiet: If True, suppress exceptions for individual substations
        progress_callback: Optional callable(operation, substation, current, total) for progress reporting
        
    Returns:
        Dictionary with sync statistics: total, synced, failed, skipped
    """
    cur = conn.cursor()
    
    # Get all substations that have at least one element
    cur.execute("""
        SELECT DISTINCT s.id, s.name
        FROM substations s
        INNER JOIN elements e ON e.substation_id = s.id
        ORDER BY s.name
    """)
    substations = cur.fetchall()
    
    total = len(substations)
    synced = 0
    failed = 0
    skipped = 0
    
    for idx, row in enumerate(substations):
        substation_id = row[0] if isinstance(row, (tuple, list)) else row["id"]
        substation_name = row[1] if isinstance(row, (tuple, list)) else row["name"]
        
        if progress_callback:
            progress_callback(
                operation="Syncing substation folder structure",
                substation=substation_name,
                current=idx + 1,
                total=total
            )
        
        try:
            # Sync gate/interconnection folders based on actual elements
            sync_substation_gate_folders(conn, substation_id, db_path=db_path)
            synced += 1
        except Exception as exc:
            failed += 1
            if not quiet:
                raise RuntimeError(
                    f"Failed to sync folder structure for substation '{substation_name}' (ID: {substation_id}): {exc}"
                ) from exc
    
    return {
        "total": total,
        "synced": synced,
        "failed": failed,
        "skipped": skipped,
    }


def regenerate_maintenance_reports(conn, *, db_path: str | None = None, quiet: bool = True, limit: int = None, progress_callback = None) -> dict:
    """Generate missing PDF reports for existing maintenance records.

    Reports are created only when a canonical file for the specific
    (maintenance_id, element_id) pair does not already exist.
    
    Args:
        conn: Database connection
        db_path: Path to database file
        quiet: If True, suppress exceptions
        limit: Optional limit on number of records to process
        progress_callback: Optional callable(operation, substation, current, total) for progress
    """
    try:
        from pdf_reports import generate_maintenance_report
    except ImportError:
        return {
            "total": 0,
            "generated": 0,
            "skipped": 0,
            "failed": 0,
            "error": "pdf_reports module not available",
        }

    cur = conn.cursor()
    query = """
        SELECT DISTINCT m.id as maintenance_id, me.element_id, e.name as element_name,
               e.gate, e.element_type, m.substation_id, m.name as maintenance_name,
               m.maintenance_type, m.date_time, s.name as substation_name
        FROM maintenance m
        INNER JOIN maintenance_elements me ON me.maintenance_id = m.id
        INNER JOIN elements e ON e.id = me.element_id
        INNER JOIN substations s ON s.id = m.substation_id
        ORDER BY m.date_time DESC
    """
    if limit:
        query += f" LIMIT {int(limit)}"

    cur.execute(query)
    records = cur.fetchall()

    total = len(records)
    generated = 0
    skipped = 0
    failed = 0

    for idx, row in enumerate(records):
        maintenance_id = row[0] if isinstance(row, (tuple, list)) else row["maintenance_id"]
        element_id = row[1] if isinstance(row, (tuple, list)) else row["element_id"]
        element_name = row[2] if isinstance(row, (tuple, list)) else row["element_name"]
        gate = row[3] if isinstance(row, (tuple, list)) else row["gate"]
        element_type = row[4] if isinstance(row, (tuple, list)) else row["element_type"]
        substation_id = row[5] if isinstance(row, (tuple, list)) else row["substation_id"]
        maintenance_name = row[6] if isinstance(row, (tuple, list)) else row["maintenance_name"]
        maintenance_type = row[7] if isinstance(row, (tuple, list)) else row["maintenance_type"]
        date_time = row[8] if isinstance(row, (tuple, list)) else row["date_time"]
        substation_name = row[9] if isinstance(row, (tuple, list)) else row["substation_name"]
        
        if progress_callback:
            progress_callback(
                operation="Generating maintenance reports",
                substation=substation_name,
                current=idx + 1,
                total=total
            )

        try:
            ensure_maintenance_folders(
                conn,
                maintenance_id=maintenance_id,
                substation_id=substation_id,
                maintenance_name=maintenance_name,
                maintenance_type=maintenance_type,
                date_time=date_time,
                element_ids=[element_id],
                attachment_paths=[],
                db_path=db_path,
            )

            report_targets = get_transformer_report_targets(
                conn,
                maintenance_id=maintenance_id,
                gate_value=gate,
                db_path=db_path,
            )
            if not report_targets:
                skipped += 1
                continue

            reports_root = report_targets[0]
            subfolder = os.path.join(reports_root, _report_subfolder_name_for_element(element_type))
            os.makedirs(subfolder, exist_ok=True)

            safe_name = element_name.replace("/", "-").replace("\\", "-").replace(":", "-")
            canonical_name = f"Maintenance_M{maintenance_id}_E{element_id}_{safe_name}.pdf"
            output_path = os.path.join(subfolder, canonical_name)

            if os.path.exists(output_path):
                upsert_maintenance_report_path(
                    conn,
                    maintenance_id=maintenance_id,
                    element_id=element_id,
                    report_type="pdf",
                    report_path=output_path,
                )
                skipped += 1
                continue

            # Try canonical path first. If it fails (often due to path-length
            # limits on older/OneDrive-managed Windows paths), fall back to
            # progressively shorter destinations under the same reports root.
            generated_path = None
            candidates = [
                output_path,
                os.path.join(subfolder, f"M{maintenance_id}_E{element_id}.pdf"),
                os.path.join(reports_root, "_AUTO_SHORT", f"M{maintenance_id}_E{element_id}.pdf"),
            ]
            last_exc = None
            for cand in candidates:
                try:
                    os.makedirs(os.path.dirname(cand), exist_ok=True)
                    generate_maintenance_report(conn, maintenance_id, element_id, cand)
                    generated_path = cand
                    break
                except Exception as gen_exc:
                    last_exc = gen_exc

            if generated_path is None:
                if last_exc:
                    raise last_exc
                raise RuntimeError("Failed to generate maintenance report")

            upsert_maintenance_report_path(
                conn,
                maintenance_id=maintenance_id,
                element_id=element_id,
                report_type="pdf",
                report_path=generated_path,
            )
            generated += 1
        except Exception as exc:
            failed += 1
            if not quiet:
                raise RuntimeError(
                    f"Failed to generate report for maintenance {maintenance_id}, element {element_id} ({element_name}): {exc}"
                ) from exc

    return {
        "total": total,
        "generated": generated,
        "skipped": skipped,
        "failed": failed,
    }
