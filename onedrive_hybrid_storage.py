import json
import os
import re
import shutil
import hashlib
import unicodedata
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
_LEGACY_SHARED_ROOT_ALIASES = (
    "Βάση Δεδομένων Κεντρική",
    "Κεντρική Βάση Δεδομένων",
)

# Canonical Greek folder labels
_DIR_GATE_1 = "ΠΥΛΗ 1"
_DIR_GATE_2 = "ΠΥΛΗ 2"
_DIR_GATE_3 = "ΠΥΛΗ 3"
_DIR_GATE_UNKNOWN = "ΠΥΛΗ Άγνωστη"
_DIR_INTERCONNECTIONS = "Διασυνδέσεις"

_DIR_MAINTENANCE = "Συντηρήσεις"
_DIR_FAULTS = "Βλάβες"
_DIR_INSPECTIONS = "Επιθεωρήσεις"
_DIR_ISOLATIONS = "Απομονώσεις"
_DIR_DGA_PARTS = ("Φυσικοχημικές", "Αεριοχρωματογραφία")
_DIR_DGA = "Φυσικοχημικές_Αεριοχρωματογραφία"
_MAINTENANCE_INSTANCE_PREFIX = "Συντ_"
_FAULT_INSTANCE_PREFIX = "Βλαβ_"
_ISOLATION_INSTANCE_PREFIX = "Απομ_"
_LEGACY_ISOLATION_INSTANCE_PREFIX = "ISO_"

_DIR_MEDIA = "Φωτογραφίες_Video"
_DIR_REPORTS = "Αναφορές"
_DIR_REPORTS_BREAKERS_HV = "Διακόπτες ΥΤ"
_DIR_REPORTS_BREAKERS_MV = "Διακόπτες ΜΤ"
_DIR_REPORTS_TRANSFORMERS = "Μετασχηματιστές"
_DIR_REPORTS_OTHER = "Λοιπά"
_REPORT_PREFIX = "Αναφ_"
_REPORT_FILENAME_MAX_STEM = 120
_REPORT_FULL_PATH_MAX = 258
_ISOLATION_OPEN_PATH_MAX = 240


def _join_parts(parts: tuple[str, ...] | list[str] | str) -> str:
    if isinstance(parts, str):
        return parts
    return os.path.join(*parts)


def _maintenance_root_relative_path(maintenance_type: str | None) -> str:
    text = (maintenance_type or "").strip().lower()
    if any(
        token in text
        for token in ("φυσικοχημ", "αεριο", "physicochemical", "gas chromat")
    ):
        return _DIR_DGA
    return ""


def _instance_prefix_for_maintenance_type(maintenance_type: str | None) -> str:
    text = (maintenance_type or "").strip().lower()
    text = "".join(
        ch
        for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )
    if any(
        token in text
        for token in (
            "βλαβ",
            "επισκευ",
            "αποκαταστ",
            "δυσλειτουργ",
            "βραχυκυκλ",
            "αστοχι",
            "fault",
            "failure",
            "repair",
            "restore",
            "outage",
        )
    ):
        return _FAULT_INSTANCE_PREFIX
    return _MAINTENANCE_INSTANCE_PREFIX


def _gate_relative_path_from_gate_key(gate_key: str | None) -> str:
    text = (gate_key or "").strip().lower()
    if text.startswith("interconnections:"):
        # Map legacy interconnection gate_key into the corresponding gate folder
        val = text.split(":", 1)[1] or ""
        bucket = _bucket_for_gate(val)
        return _gate_relative_path(bucket)
    if text.startswith("gate:"):
        return _gate_relative_path(("gate", text.split(":", 1)[1] or "unknown"))
    return _DIR_GATE_UNKNOWN


def _safe_name(value: str, fallback: str = "unknown") -> str:
    text = (value or "").strip()
    if not text:
        return fallback
    text = re.sub(r"[\\/:*?\"<>|]", "_", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or fallback


def _is_legacy_shared_root_alias(name: str | None) -> bool:
    text = str(name or "").strip()
    if not text:
        return False
    norm = os.path.normcase(text)
    return any(norm == os.path.normcase(alias) for alias in _LEGACY_SHARED_ROOT_ALIASES)


def _slug(value: str, fallback: str = "item") -> str:
    text = _safe_name(value, fallback=fallback)
    text = text.replace(" ", "_")
    text = re.sub(r"_+", "_", text)
    return text.strip("_") or fallback


def _win_path(path: str) -> str:
    abs_path = os.path.abspath(path)
    if os.name != "nt" or abs_path.startswith("\\\\?\\"):
        return abs_path
    if abs_path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + abs_path[2:]
    return "\\\\?\\" + abs_path


def _report_prefixed_name(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return _REPORT_PREFIX.rstrip("_")
    if text.startswith(_REPORT_PREFIX):
        return text
    return f"{_REPORT_PREFIX}{text}"


def ensure_reference_structure(
    shared_root: str,
    *,
    description_filename: str = "Περιγραφή.txt",
    reference_folder_name: str = "00_Αναφορά Δομής Φακέλων",
) -> dict:
    """Create a single top-level reference folder under `shared_root`.

    The example tree mirrors the live shared storage layout:
    substation -> gate -> prefixed maintenance/fault instances, with
    isolation requests stored under the substation root.
    """
    created = 0
    described = 0

    def _atomic_write(path: str, text: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        try:
            os.replace(tmp, path)
        except Exception:
            try:
                os.remove(tmp)
            except Exception:
                pass

    try:
        os.makedirs(shared_root, exist_ok=True)
    except Exception:
        return {"created": 0, "described": 0}

    nested_shared_root = os.path.join(shared_root, _DEFAULT_SHARED_ROOT_NAME)
    if os.path.normcase(os.path.abspath(nested_shared_root)) != os.path.normcase(
        os.path.abspath(shared_root)
    ):
        try:
            _merge_legacy_path(nested_shared_root, shared_root)
        except Exception:
            pass

    def _ensure_folder(path: str, description: str | None = None) -> None:
        nonlocal created, described
        try:
            if not os.path.isdir(path):
                os.makedirs(path, exist_ok=True)
                created += 1
        except Exception:
            return
        if description:
            try:
                _atomic_write(os.path.join(path, description_filename), description)
                described += 1
            except Exception:
                pass

    def _move_to_legacy(path: str, legacy_root: str) -> None:
        if not os.path.isdir(path):
            return
        name = os.path.basename(path.rstrip("\\/"))
        dest = os.path.join(legacy_root, name)
        try:
            os.makedirs(legacy_root, exist_ok=True)
            if os.path.exists(dest):
                dest = os.path.join(
                    legacy_root, f"{name}_moved_{int(datetime.now().timestamp())}"
                )
            shutil.move(path, dest)
        except Exception:
            pass

    reference_root = os.path.join(shared_root, reference_folder_name)
    legacy_reference_root = os.path.join(reference_root, "_legacy_moved")
    sample_substation_name = "Υποσταθμός_Δείγμα"
    allowed_root_names = {reference_folder_name}

    # Sanitize stray top-level gate/interconnection folders so they no longer
    # appear at the shared-root level.
    try:
        os.makedirs(reference_root, exist_ok=True)
    except Exception:
        pass
    try:
        for name in list(os.listdir(shared_root)):
            if name in allowed_root_names:
                continue
            low = name.strip().lower()
            if low.startswith("πυλη") or "διασυν" in low:
                src = os.path.join(shared_root, name)
                if not os.path.isdir(src):
                    continue
                _move_to_legacy(src, legacy_reference_root)
    except Exception:
        pass

    obsolete_reference_dirs = (
        _DIR_GATE_1,
        _DIR_GATE_2,
        _DIR_GATE_3,
        _DIR_GATE_UNKNOWN,
        _DIR_INTERCONNECTIONS,
        _DIR_MAINTENANCE,
        _DIR_FAULTS,
        _DIR_REPORTS,
        _DIR_MEDIA,
        _DIR_INSPECTIONS,
        _DIR_ISOLATIONS,
        _DIR_DGA_PARTS[0],
    )
    for obsolete_name in obsolete_reference_dirs:
        _move_to_legacy(
            os.path.join(reference_root, obsolete_name), legacy_reference_root
        )

    _ensure_folder(reference_root)

    top_readme = (
        "00_Αναφορά Δομής Φακέλων - Παράδειγμα δομής που μπορεί να δημιουργήσει η εφαρμογή.\n"
        "Η πραγματική δομή είναι: Υποσταθμός -> Πύλη -> φάκελοι περιστατικών με πρόθεμα (π.χ. Συντ_, Βλαβ_).\n"
        "Σε κάθε παράδειγμα φακέλου υπάρχει αρχείο Περιγραφή.txt με σύντομη περιγραφή του σκοπού του.\n"
        "Οι αναφορές PDF τοποθετούνται μέσα στον αντίστοιχο φάκελο περιστατικού και όχι σε γενικό φάκελο Αναφορές.\n"
    )
    try:
        _atomic_write(os.path.join(reference_root, "README.txt"), top_readme)
        described += 1
    except Exception:
        pass

    sample_root = os.path.join(reference_root, sample_substation_name)
    _ensure_folder(
        sample_root,
        "Παράδειγμα ρίζας υποσταθμού. Στον πραγματικό συγχρονισμό κάθε υποσταθμός εμφανίζεται ως ξεχωριστός φάκελος κάτω από την κοινή βάση.",
    )

    gate_descriptions = {
        _DIR_GATE_1: "Παράδειγμα πύλης. Οι φάκελοι περιστατικών δημιουργούνται απευθείας μέσα στην πύλη.",
        _DIR_GATE_2: "Παράδειγμα πύλης. Οι φάκελοι περιστατικών δημιουργούνται απευθείας μέσα στην πύλη.",
        _DIR_GATE_3: "Παράδειγμα πύλης. Οι φάκελοι περιστατικών δημιουργούνται απευθείας μέσα στην πύλη.",
    }
    report_example_dirs = [
        _report_prefixed_name(_DIR_REPORTS_BREAKERS_HV),
        _report_prefixed_name(_DIR_REPORTS_BREAKERS_MV),
        _report_prefixed_name(_DIR_REPORTS_TRANSFORMERS),
        _report_prefixed_name(_DIR_REPORTS_OTHER),
    ]

    for gate_name in (_DIR_GATE_1, _DIR_GATE_2, _DIR_GATE_3):
        gate_path = os.path.join(sample_root, gate_name)
        _ensure_folder(gate_path, gate_descriptions[gate_name])

        maintenance_example = os.path.join(
            gate_path,
            f"{_MAINTENANCE_INSTANCE_PREFIX}20260326_0800_Υποσταθμός_Δείγμα_M123",
        )
        _ensure_folder(
            maintenance_example,
            "Παράδειγμα φακέλου συντήρησης. Η συνοπτική PDF αναφορά της συντήρησης αποθηκεύεται απευθείας εδώ.",
        )
        media_example = os.path.join(maintenance_example, _DIR_MEDIA)
        _ensure_folder(
            media_example,
            "Φωτογραφίες και βίντεο μόνο για το συγκεκριμένο περιστατικό συντήρησης.",
        )
        try:
            _atomic_write(
                os.path.join(media_example, "Παραδείγματα_Ονομασίας.txt"),
                "Παράδειγμα ονομασίας φωτογραφίας/βίντεο:\nIMG_20260326_001.jpg\nVIDEO_20260326_001.mp4\n",
            )
            described += 1
        except Exception:
            pass
        try:
            _atomic_write(
                os.path.join(maintenance_example, "Παραδείγματα_Αναφορών.txt"),
                "Παραδείγματα αναφορών που μπορούν να εμφανιστούν στον φάκελο περιστατικού:\n"
                "Αναφ_Υποσταθμός_Δείγμα_M123_Overview.pdf\n"
                "Αναφ_Υποσταθμός_Δείγμα_Στοιχείο_M123.pdf\n",
            )
            described += 1
        except Exception:
            pass

        for report_dir in report_example_dirs:
            _ensure_folder(
                os.path.join(maintenance_example, report_dir),
                "Υποφάκελος αναφορών ανά κατηγορία στοιχείου. Δημιουργείται μόνο όταν υπάρχει αντίστοιχη αναφορά.",
            )

        fault_example = os.path.join(
            gate_path, f"{_FAULT_INSTANCE_PREFIX}20260326_1015_Υποσταθμός_Δείγμα_M124"
        )
        _ensure_folder(
            fault_example,
            "Παράδειγμα φακέλου βλάβης. Οι βλάβες αποθηκεύονται απευθείας στην πύλη με πρόθεμα Βλαβ_.",
        )
        _ensure_folder(
            os.path.join(fault_example, _DIR_MEDIA),
            "Φωτογραφίες και βίντεο μόνο για το συγκεκριμένο περιστατικό βλάβης.",
        )

        _ensure_folder(
            os.path.join(gate_path, _DIR_INSPECTIONS),
            "Φάκελος επιθεωρήσεων για την πύλη. Δημιουργείται όταν αποθηκευτούν σχετικά αρχεία.",
        )
        dga_root = os.path.join(gate_path, _DIR_DGA)
        _ensure_folder(
            dga_root,
            "Ενιαίος φάκελος για το κοινό Excel φυσικοχημικών και αεριοχρωματογραφίας.",
        )
        _ensure_folder(
            os.path.join(dga_root, "20260326_Μετασχηματιστής_Δείγμα"),
            "Παράδειγμα φακέλου μέτρησης DGA. Κάθε μέτρηση αποθηκεύεται ως ένας ενιαίος φάκελος με το κοινό Excel report.",
        )

    isolation_root = os.path.join(sample_root, _DIR_ISOLATIONS)
    _ensure_folder(
        isolation_root,
        "Οι αιτήσεις απομόνωσης ανήκουν στο επίπεδο του υποσταθμού και δημιουργούνται μόνο όταν υπάρχει σχετική αίτηση.",
    )
    isolation_example = os.path.join(
        isolation_root, "Απομ_20260326_1200_Υποσταθμός_Δείγμα_321"
    )
    _ensure_folder(isolation_example, "Παράδειγμα φακέλου αίτησης απομόνωσης.")

    return {"created": int(created), "described": int(described)}


def _legacy_reports_root(instance_root: str) -> str:
    return os.path.join(instance_root, _DIR_REPORTS)


def _normalize_reports_root_path(path: str | None) -> str | None:
    if not path:
        return path
    try:
        abs_path = os.path.abspath(path)
        if os.path.normcase(os.path.basename(abs_path)) == os.path.normcase(
            _DIR_REPORTS
        ):
            return os.path.dirname(abs_path)
        return abs_path
    except Exception:
        return path


def _report_stem_budget(parent_dir: str | None) -> int:
    budget = _REPORT_FILENAME_MAX_STEM
    if not parent_dir:
        return budget
    try:
        parent_len = len(os.path.abspath(parent_dir))
        path_budget = _REPORT_FULL_PATH_MAX - parent_len - 1 - len(".pdf")
        return max(8, min(budget, path_budget))
    except Exception:
        return budget


def _compact_report_stem(maintenance_id: int, digest: str, stem_budget: int) -> str:
    prefix = f"{_REPORT_PREFIX}M{maintenance_id}_"
    if stem_budget <= 0:
        return "M"
    if len(prefix) >= stem_budget:
        return prefix[:stem_budget].rstrip("_- ") or f"M{maintenance_id}"[:stem_budget]
    remainder = max(1, stem_budget - len(prefix))
    return f"{prefix}{digest[:remainder]}".rstrip("_- ")


def _canonical_report_filename(
    substation_name: str,
    element_name: str,
    maintenance_id: int,
    *,
    parent_dir: str | None = None,
) -> str:
    safe_sub = _safe_name(substation_name or "unknown", fallback="unknown")
    safe_elem = _safe_name(element_name or "element", fallback="element")
    stem_budget = _report_stem_budget(parent_dir)
    stem = _report_prefixed_name(
        f"{safe_sub}_{safe_elem}_Maintenance_M{maintenance_id}"
    )
    if len(stem) <= stem_budget:
        return stem + ".pdf"

    digest = hashlib.sha1(
        f"{safe_sub}|{safe_elem}|{maintenance_id}".encode("utf-8")
    ).hexdigest()[:10]
    suffix = f"_M{maintenance_id}_{digest}"
    budget = stem_budget - len(suffix)
    if budget >= 12:
        sub_budget = max(4, budget // 2)
        elem_budget = max(4, budget - sub_budget)
        short_sub = safe_sub[:sub_budget].rstrip(" _-")
        short_elem = safe_elem[:elem_budget].rstrip(" _-")
        short_stem = _report_prefixed_name(f"{short_sub}_{short_elem}{suffix}")
    else:
        short_stem = _compact_report_stem(maintenance_id, digest, stem_budget)
    short_stem = re.sub(r"_+", "_", short_stem).strip("_")
    if len(short_stem) > stem_budget:
        short_stem = _compact_report_stem(maintenance_id, digest, stem_budget)
    return short_stem + ".pdf"


def _canonical_overview_report_filename(
    substation_name: str,
    maintenance_id: int,
    *,
    parent_dir: str | None = None,
) -> str:
    safe_sub = _safe_name(substation_name or "unknown", fallback="unknown")
    stem_budget = _report_stem_budget(parent_dir)
    stem = _report_prefixed_name(f"{safe_sub}_Maintenance_M{maintenance_id}_Overview")
    if len(stem) <= stem_budget:
        return stem + ".pdf"

    digest = hashlib.sha1(
        f"{safe_sub}|overview|{maintenance_id}".encode("utf-8")
    ).hexdigest()[:10]
    suffix = f"_M{maintenance_id}_OV_{digest}"
    budget = stem_budget - len(suffix)
    if budget >= 6:
        short_sub = safe_sub[:budget].rstrip(" _-")
        short_stem = _report_prefixed_name(f"{short_sub}{suffix}")
    else:
        short_stem = _compact_report_stem(maintenance_id, digest, stem_budget)
    short_stem = re.sub(r"_+", "_", short_stem).strip("_")
    if len(short_stem) > stem_budget:
        short_stem = _compact_report_stem(maintenance_id, digest, stem_budget)
    return short_stem + ".pdf"


def _remap_legacy_shared_root(path: str | None, shared_root: str) -> str | None:
    """Remap a stored path from legacy shared root to the current shared root.

    This prevents re-creating the old ``shared_substations`` tree when older DB
    rows still reference it.
    """
    if not path:
        return path

    try:
        current_root = os.path.abspath(shared_root)
        abs_path = os.path.abspath(path)
        current_parent = os.path.abspath(os.path.dirname(current_root))
        equivalent_roots = [
            os.path.abspath(os.path.join(current_parent, _LEGACY_SHARED_ROOT_NAME)),
            os.path.abspath(os.path.join(current_parent, _DEFAULT_SHARED_ROOT_NAME)),
        ]
        for alias in _LEGACY_SHARED_ROOT_ALIASES:
            equivalent_roots.append(
                os.path.abspath(os.path.join(current_parent, alias))
            )

        # Windows-safe case-insensitive prefix comparison.
        abs_norm = os.path.normcase(abs_path)
        for legacy_root in equivalent_roots:
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

        for alias in _LEGACY_SHARED_ROOT_ALIASES:
            alias_marker = os.sep + alias + os.sep
            if alias_marker in abs_path:
                replacement = os.sep + _DEFAULT_SHARED_ROOT_NAME + os.sep
                return abs_path.replace(alias_marker, replacement, 1)

        # Generic fallback: if an old absolute path contains the canonical
        # shared-root segment anywhere, anchor it to the currently configured
        # shared root and preserve only the tail under that segment.
        parts = abs_path.split(os.sep)
        default_norm = os.path.normcase(_DEFAULT_SHARED_ROOT_NAME)
        for idx, part in enumerate(parts):
            if os.path.normcase(part) != default_norm:
                continue
            rel_tail = os.sep.join(parts[idx + 1 :]).lstrip("\\/")
            return os.path.join(current_root, rel_tail) if rel_tail else current_root

        for alias in _LEGACY_SHARED_ROOT_ALIASES:
            alias_norm = os.path.normcase(alias)
            for idx, part in enumerate(parts):
                if os.path.normcase(part) != alias_norm:
                    continue
                rel_tail = os.sep.join(parts[idx + 1 :]).lstrip("\\/")
                return (
                    os.path.join(current_root, rel_tail) if rel_tail else current_root
                )
    except Exception:
        return path

    return path


def _normalize_shared_root_relative(
    configured_value: str | None, sync_root: str
) -> str:
    """Normalize user setting to a relative folder path under sync_root.

    Backward compatibility:
    - absolute legacy values are mapped to a relative folder name
    - rooted values like "\\Folder" are treated as relative to sync_root
    """
    text = str(configured_value or "").strip()
    if not text:
        return _DEFAULT_SHARED_ROOT_NAME

    # Rooted path without drive (e.g. "\\Folder") should be treated as
    # "folder under sync_root", not as an absolute path on current drive.
    rooted_relative = text.startswith("\\") or text.startswith("/")
    if rooted_relative:
        rel = text.lstrip("\\/").strip()
        if _is_legacy_shared_root_alias(rel):
            return _DEFAULT_SHARED_ROOT_NAME
        return rel or _DEFAULT_SHARED_ROOT_NAME

    expanded = os.path.expandvars(os.path.expanduser(text))
    if os.path.isabs(expanded):
        abs_value = os.path.abspath(expanded)
        sync_abs = os.path.abspath(sync_root)
        try:
            common = os.path.commonpath([sync_abs, abs_value])
            if os.path.normcase(common) == os.path.normcase(sync_abs):
                rel = os.path.relpath(abs_value, sync_abs).strip("\\/")
                if _is_legacy_shared_root_alias(rel):
                    return _DEFAULT_SHARED_ROOT_NAME
                return rel or _DEFAULT_SHARED_ROOT_NAME
        except Exception:
            pass
        # Legacy absolute path outside sync_root: keep just folder label.
        base = os.path.basename(abs_value.rstrip("\\/"))
        if _is_legacy_shared_root_alias(base):
            return _DEFAULT_SHARED_ROOT_NAME
        return base or _DEFAULT_SHARED_ROOT_NAME

    rel = expanded.strip("\\/")
    if _is_legacy_shared_root_alias(rel):
        return _DEFAULT_SHARED_ROOT_NAME
    return rel or _DEFAULT_SHARED_ROOT_NAME


def resolve_shared_root(db_path: str | None = None) -> str:
    sync_root = get_app_setting("sync_root_path", None)
    if sync_root:
        sync_base = os.path.abspath(sync_root)
        base_name = os.path.basename(sync_base.rstrip("\\/"))
        if os.path.normcase(base_name) == os.path.normcase(
            _DEFAULT_SHARED_ROOT_NAME
        ) or _is_legacy_shared_root_alias(base_name):
            return sync_base
        if os.path.isdir(sync_base):
            try:
                sentinel_names = {
                    "00_Αναφορά Δομής Φακέλων",
                    _DIR_GATE_1,
                    _DIR_GATE_2,
                    _DIR_GATE_3,
                    _DIR_ISOLATIONS,
                }
                if sentinel_names & set(os.listdir(sync_base)):
                    return sync_base
            except Exception:
                pass
    elif db_path:
        sync_base = os.path.dirname(db_path)
    else:
        sync_base = os.getcwd()

    # Shared root is a fixed relative folder under sync_root
    rel = _DEFAULT_SHARED_ROOT_NAME
    return os.path.abspath(os.path.join(sync_base, rel))


def _bucket_for_gate(gate_value: str | None) -> tuple[str, str]:
    # Normalize and map interconnection pairs into the first-digit gate.
    gate = (gate_value or "").strip().lower().replace(" ", "")

    # Handle explicit interconnection pairs (accept either ordering)
    if "1-2" in gate or "2-1" in gate:
        return ("gate", "1")
    if "2-3" in gate or "3-2" in gate:
        return ("gate", "2")
    # Normalize 1-3 and 3-1 to gate 3 (user expects 1-3 -> 3-1 -> Gate 3)
    if "3-1" in gate or "1-3" in gate:
        return ("gate", "3")

    match = re.search(r"([123])", gate)
    if match:
        return ("gate", match.group(1))

    return ("gate", "unknown")


def _gate_relative_path(bucket: tuple[str, str]) -> str:
    kind, value = bucket
    if value in {"1", "2", "3"}:
        return {
            "1": _DIR_GATE_1,
            "2": _DIR_GATE_2,
            "3": _DIR_GATE_3,
        }.get(value, _DIR_GATE_UNKNOWN)
    return _DIR_GATE_UNKNOWN


def _report_bucket_label_for_element(
    element_type: str | None, breaker_category: str | None = None
) -> str:
    t = (element_type or "").lower()

    # Direct substring matches keep highest priority
    if any(s in t for s in _TRANSFORMER_SUBSTRS):
        return _DIR_REPORTS_TRANSFORMERS
    if any(s in t for s in _HV_BREAKER_SUBSTRS):
        return _DIR_REPORTS_BREAKERS_HV
    if any(s in t for s in _MV_BREAKER_SUBSTRS):
        return _DIR_REPORTS_BREAKERS_MV

    # If the element type is a generic breaker label, try to infer from
    # breaker_category (e.g. SF6 tends to be HV; Vacuum/Κενού tends to be MV).
    is_breaker_generic = any(
        token in t for token in ("διακόπτη", "διακόπτης", "breaker")
    )
    if is_breaker_generic or not t:
        # Fallback: prefer HV for breakers when ambiguous (matches prior behaviour)
        if is_breaker_generic:
            return _DIR_REPORTS_BREAKERS_HV

    return _DIR_REPORTS_OTHER


def _report_subfolder_name_for_element(
    element_type: str | None, breaker_category: str | None = None
) -> str:
    return _report_prefixed_name(
        _report_bucket_label_for_element(element_type, breaker_category)
    )


def _legacy_report_subfolder_name_for_element(
    element_type: str | None, breaker_category: str | None = None
) -> str:
    return _report_bucket_label_for_element(element_type, breaker_category)


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
_HV_BREAKER_SUBSTRS = ("διακόπτης υτ", "hv breaker")
_MV_BREAKER_SUBSTRS = ("διακόπτης μτ", "mv breaker")


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
    rest = len(winning) - len(shown)

    parts = [
        _sanitize_element_name(name)
        for _, name in shown
        if _sanitize_element_name(name)
    ]
    slug = "+".join(parts)
    if rest == 1:
        # Prefer explicit naming over "+1more" for readability.
        extra_name = (
            _sanitize_element_name(winning[MAX_SHOWN][1])
            if len(winning) > MAX_SHOWN
            else ""
        )
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

    dt_part = (
        dt.strftime("%Y%m%d_%H%M") if dt else datetime.now().strftime("%Y%m%d_%H%M")
    )

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
    dt_part = (
        dt.strftime("%Y%m%d_%H%M") if dt else datetime.now().strftime("%Y%m%d_%H%M")
    )

    sub = _safe_name(substation_name or "", fallback="substation")
    sub = re.sub(r"[()]", "", sub)
    sub = re.sub(r"\s+", "_", sub).strip("_")
    if len(sub) > 16:
        sub = sub[:16].rstrip("_")

    return f"{dt_part}_{sub}_M{maintenance_id}"


def _isolation_instance_short_fallback(
    start_datetime: str | None,
    substation_name: str | None,
    request_id: int,
) -> str:
    try:
        dt = datetime.strptime(start_datetime or "", "%Y-%m-%d %H:%M")
    except Exception:
        dt = None

    dt_part = (
        dt.strftime("%Y%m%d_%H%M") if dt else datetime.now().strftime("%Y%m%d_%H%M")
    )

    sub = _safe_name(substation_name or "", fallback="substation")
    sub = re.sub(r"[()]", "", sub)
    sub = re.sub(r"\s+", "_", sub).strip("_")
    if len(sub) > 16:
        sub = sub[:16].rstrip("_")

    return f"{dt_part}_{sub}_{request_id}"


def _isolation_instance_folder_name(
    start_datetime: str | None,
    *,
    substation_name: str | None,
    request_id: int,
    isolation_root: str | None = None,
) -> str:
    try:
        dt = datetime.strptime(start_datetime or "", "%Y-%m-%d %H:%M")
        slug_date = dt.strftime("%Y%m%d_%H%M")
    except Exception:
        slug_date = _slug(start_datetime or "unknown", fallback="unknown")

    prefixed = f"{_ISOLATION_INSTANCE_PREFIX}{slug_date}_{_slug(substation_name, fallback='substation')}_{request_id}"
    if not isolation_root:
        return prefixed

    projected_len = len(
        os.path.join(isolation_root, prefixed, f"Αίτηση_{request_id}.xlsx")
    )
    if projected_len <= _ISOLATION_OPEN_PATH_MAX:
        return prefixed

    fallback = _isolation_instance_short_fallback(
        start_datetime, substation_name, request_id
    )
    return f"{_ISOLATION_INSTANCE_PREFIX}{fallback}"


def _maintenance_instance_folder_name(
    date_time: str | None,
    *,
    substation_name: str | None,
    elements: list[tuple[str, str]] | None,
    maintenance_id: int,
    maintenance_type: str | None = None,
    gate_root: str | None = None,
) -> str:
    base_name = _instance_slug(
        date_time,
        substation_name=substation_name,
        elements=elements,
    )
    prefix = _instance_prefix_for_maintenance_type(maintenance_type)
    prefixed = f"{prefix}{base_name}"
    if not gate_root:
        return prefixed

    # Reserve space for the longest canonical report subfolder and a compact
    # report filename so Acrobat-safe Win32 paths remain under budget.
    report_folder_budget = max(
        len(_report_prefixed_name(_DIR_REPORTS_BREAKERS_HV)),
        len(_report_prefixed_name(_DIR_REPORTS_BREAKERS_MV)),
        len(_report_prefixed_name(_DIR_REPORTS_TRANSFORMERS)),
        len(_report_prefixed_name(_DIR_REPORTS_OTHER)),
    )
    compact_report_budget = max(
        20, len(f"{_REPORT_PREFIX}M{maintenance_id}_1234567890.pdf")
    )
    projected_len = (
        len(os.path.join(gate_root, prefixed))
        + 1
        + report_folder_budget
        + 1
        + compact_report_budget
    )
    if projected_len <= _REPORT_FULL_PATH_MAX:
        return prefixed

    fallback = _instance_slug_short_fallback(date_time, substation_name, maintenance_id)
    return f"{prefix}{fallback}"


def _append_graph_queue(shared_root: str, payload: dict) -> None:
    queue_dir = os.path.join(shared_root, "_queue")
    os.makedirs(_win_path(queue_dir), exist_ok=True)
    queue_file = os.path.join(queue_dir, "graph_jobs.jsonl")
    with open(_win_path(queue_file), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _ensure_dir(
    path: str, *, queue_on_fail: bool = True, queue_payload: dict | None = None
) -> None:
    try:
        os.makedirs(_win_path(path), exist_ok=True)
    except Exception as exc:
        if queue_on_fail and queue_payload:
            if "path" not in queue_payload:
                queue_payload = dict(queue_payload)
                queue_payload["path"] = path
            _append_graph_queue(queue_payload.get("shared_root", path), queue_payload)
        raise RuntimeError(
            S["MESSAGES"]
            .get(
                "ONEDRIVE_FOLDER_CREATE_FAILED_FMT",
                "Failed to create folder: {path}\n{error}",
            )
            .format(path=path, error=str(exc))
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
    current_shared_root = resolve_shared_root(db_path)
    _reconcile_legacy_shared_root_aliases(current_shared_root)
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

        # Guard against stale queued jobs that still reference legacy shared
        # folder aliases; always materialize under the currently resolved root.
        path = _remap_legacy_shared_root(path, current_shared_root) or path

        try:
            os.makedirs(_win_path(path), exist_ok=True)
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


def _copy_media_to_targets(
    source_paths: Iterable[str], target_folders: Iterable[str]
) -> int:
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
                os.makedirs(_win_path(target), exist_ok=True)
                dest = Path(target) / src_path.name
                base = dest.stem
                ext = dest.suffix
                idx = 1
                while dest.exists():
                    dest = Path(target) / f"{base}_{idx}{ext}"
                    idx += 1
                shutil.copy2(_win_path(str(src_path)), _win_path(str(dest)))
                copied += 1
        except Exception:
            continue
    return copied


def copy_files_to_folder(source_paths: Iterable[str], target_folder: str | None) -> int:
    if not target_folder:
        return 0

    copied = 0
    target = str(target_folder).strip()
    if not target:
        return 0

    for src in source_paths or []:
        if not src:
            continue
        try:
            src_path = Path(src)
            src_abs = str(src_path)
            if not os.path.exists(_win_path(src_abs)) or not os.path.isfile(
                _win_path(src_abs)
            ):
                continue

            os.makedirs(_win_path(target), exist_ok=True)
            dest = Path(target) / src_path.name
            base = dest.stem
            ext = dest.suffix
            idx = 1
            while dest.exists():
                dest = Path(target) / f"{base}_{idx}{ext}"
                idx += 1
            shutil.copy2(_win_path(str(src_path)), _win_path(str(dest)))
            copied += 1
        except Exception:
            continue

    return copied


def _move_files_to_folder(
    source_paths: Iterable[str], target_folder: str | None
) -> int:
    if not target_folder:
        return 0

    moved = 0
    target = str(target_folder).strip()
    if not target:
        return 0

    for src in source_paths or []:
        if not src:
            continue
        try:
            src_path = Path(src)
            src_abs = str(src_path)
            if not os.path.exists(_win_path(src_abs)) or not os.path.isfile(
                _win_path(src_abs)
            ):
                continue

            os.makedirs(_win_path(target), exist_ok=True)
            dest = Path(target) / src_path.name
            base = dest.stem
            ext = dest.suffix
            idx = 1
            while dest.exists() and os.path.normcase(str(dest)) != os.path.normcase(
                str(src_path)
            ):
                dest = Path(target) / f"{base}_{idx}{ext}"
                idx += 1

            if os.path.normcase(str(dest)) == os.path.normcase(str(src_path)):
                moved += 1
                continue

            shutil.move(_win_path(str(src_path)), _win_path(str(dest)))
            moved += 1
        except Exception:
            continue

    return moved


def _list_direct_files(folder_path: str | None) -> list[str]:
    if not folder_path:
        return []
    try:
        files = []
        with os.scandir(_win_path(folder_path)) as entries:
            for entry in entries:
                try:
                    if entry.is_file():
                        files.append(os.path.join(folder_path, entry.name))
                except Exception:
                    continue
        return sorted(files)
    except Exception:
        return []


def _canonical_isolation_attachment_name(
    request_id: int, index: int, suffix: str
) -> str:
    suffix_text = "" if index == 1 else f"_{index}"
    return f"Αίτηση_{request_id}{suffix_text}{suffix}"


def _normalize_isolation_attachment_files(
    folder_path: str | None, request_id: int
) -> list[str]:
    files = _list_direct_files(folder_path)
    if not files:
        return []

    normalized_files = []
    for index, src in enumerate(files, start=1):
        try:
            src_path = Path(src)
            suffix = src_path.suffix or ""
            candidate = Path(folder_path) / _canonical_isolation_attachment_name(
                request_id, index, suffix
            )
            candidate_index = index
            while candidate.exists() and os.path.normcase(
                str(candidate)
            ) != os.path.normcase(str(src_path)):
                candidate_index += 1
                candidate = Path(folder_path) / _canonical_isolation_attachment_name(
                    request_id, candidate_index, suffix
                )

            if os.path.normcase(str(candidate)) != os.path.normcase(str(src_path)):
                shutil.move(_win_path(str(src_path)), _win_path(str(candidate)))
                src_path = candidate
        except Exception:
            src_path = Path(src)

        normalized_files.append(str(src_path))

    return sorted(normalized_files)


_REPORT_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx"}


def _distribute_attachments_and_register(
    conn,
    source_paths: Iterable[str],
    created_rows: list[dict],
    maintenance_id: int,
    element_ids: Iterable[int],
):
    """Copy attachments to media or reports folders and register report paths.

    - Media files (images/videos) are copied to each `media_folder` in `created_rows`.
    - Report files (pdf/doc/xls) are copied into per-element report subfolders
      and persisted via `upsert_maintenance_report_path` for each element in
      `element_ids` that belongs to the same gate bucket.

    Returns: (copied_media_count, copied_reports_count)
    """
    copied_media = 0
    copied_reports = 0

    # Normalize created_rows by gate_key for quick lookup
    rows_by_gate = {r["gate_key"]: r for r in (created_rows or [])}

    # Map element_id -> (gate_key, element_type)
    elem_map = {}
    try:
        if element_ids:
            placeholders = ",".join(["?"] * len(element_ids))
            cur = conn.cursor()
            cur.execute(
                f"SELECT id, gate, element_type, breaker_category FROM elements WHERE id IN ({placeholders})",
                tuple(element_ids),
            )
            for row in cur.fetchall() or []:
                eid = row[0]
                gate = row[1] or ""
                etype = row[2] or ""
                bcat = row[3] or None
                bucket = _bucket_for_gate(gate)
                gate_key = f"{bucket[0]}:{bucket[1]}"
                elem_map[eid] = (gate_key, etype, bcat)
    except Exception:
        elem_map = {}

    # Targets for media copying
    media_targets = [
        r["media_folder"] for r in (created_rows or []) if r.get("media_folder")
    ]

    for src in source_paths or []:
        if not src:
            continue
        try:
            src_path = Path(src)
            if not src_path.exists() or not src_path.is_file():
                continue

            suffix = src_path.suffix.lower()
            if suffix in _REPORT_EXTENSIONS:
                # Copy into per-element report subfolders when possible
                if elem_map:
                    for eid, (gate_key, etype, bcat) in elem_map.items():
                        target_row = rows_by_gate.get(gate_key) or (
                            created_rows[0] if created_rows else None
                        )
                        if not target_row:
                            continue
                        reports_root = target_row.get("reports_folder")
                        subname = _report_subfolder_name_for_element(etype, bcat)
                        subfolder = os.path.join(reports_root, subname)
                        os.makedirs(_win_path(subfolder), exist_ok=True)
                        dest = Path(subfolder) / src_path.name
                        base = dest.stem
                        ext = dest.suffix
                        idx = 1
                        while dest.exists():
                            dest = Path(subfolder) / f"{base}_{idx}{ext}"
                            idx += 1
                        shutil.copy2(_win_path(str(src_path)), _win_path(str(dest)))
                        copied_reports += 1
                        try:
                            upsert_maintenance_report_path(
                                conn,
                                maintenance_id=maintenance_id,
                                element_id=int(eid),
                                report_path=str(dest),
                                report_type=ext.lstrip(".") or "pdf",
                            )
                        except Exception:
                            pass
                else:
                    # No element mapping: copy into a generic reports_other of the first row
                    # NOTE: by design we DO NOT register a DB row for generic reports
                    # (element_id=0) to avoid creating placeholder entries without
                    # a proper element mapping. Files are still copied for manual
                    # inspection in the shared folder.
                    if created_rows:
                        target_row = created_rows[0]
                        reports_root = target_row.get("reports_folder")
                        subfolder = os.path.join(
                            reports_root, _report_prefixed_name(_DIR_REPORTS_OTHER)
                        )
                        os.makedirs(_win_path(subfolder), exist_ok=True)
                        dest = Path(subfolder) / src_path.name
                        base = dest.stem
                        ext = dest.suffix
                        idx = 1
                        while dest.exists():
                            dest = Path(subfolder) / f"{base}_{idx}{ext}"
                            idx += 1
                        shutil.copy2(_win_path(str(src_path)), _win_path(str(dest)))
                        copied_reports += 1
            else:
                # Media file — copy to all media targets
                for target in media_targets:
                    try:
                        os.makedirs(_win_path(target), exist_ok=True)
                        dest = Path(target) / src_path.name
                        base = dest.stem
                        ext = dest.suffix
                        idx = 1
                        while dest.exists():
                            dest = Path(target) / f"{base}_{idx}{ext}"
                            idx += 1
                        shutil.copy2(_win_path(str(src_path)), _win_path(str(dest)))
                        copied_media += 1
                    except Exception:
                        continue
        except Exception:
            continue

    return copied_media, copied_reports


def _collect_gate_buckets(conn, element_ids: Iterable[int]) -> list[tuple[str, str]]:
    ids = [int(x) for x in (element_ids or []) if x is not None]
    if not ids:
        # No specific elements provided: default to a generic unknown gate bucket
        return [("gate", "unknown")]
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


def ensure_substation_structure(
    conn, substation_id: int, *, db_path: str | None = None
) -> dict:
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
    safe_substation = _safe_name(
        substation_name, fallback=f"substation_{substation_id}"
    )
    shared_root = resolve_shared_root(db_path)
    _reconcile_legacy_shared_root_aliases(shared_root)

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


def ensure_isolation_request_storage(
    conn,
    *,
    request_id: int,
    substation_id: int,
    start_datetime: str,
    attachment_paths: Iterable[str] | None = None,
    storage_folder_path: str | None = None,
    request_file_path: str | None = None,
    db_path: str | None = None,
) -> dict:
    base = ensure_substation_structure(conn, substation_id, db_path=db_path)
    substation_root = base["substation_root"]
    substation_name = base["substation_name"]

    queue_payload = {
        "kind": "ensure_isolation_structure",
        "request_id": request_id,
        "substation_id": substation_id,
        "created_at": datetime.now().isoformat(),
    }

    isolation_root = os.path.join(substation_root, _DIR_ISOLATIONS)
    instance_root = os.path.join(
        isolation_root,
        _isolation_instance_folder_name(
            start_datetime,
            substation_name=substation_name,
            request_id=request_id,
            isolation_root=isolation_root,
        ),
    )
    try:
        dt = datetime.strptime(start_datetime, "%Y-%m-%d %H:%M")
        slug_date = dt.strftime("%Y%m%d_%H%M")
    except Exception:
        slug_date = _slug(start_datetime or "unknown", fallback="unknown")
    legacy_instance_root = os.path.join(
        isolation_root,
        f"{_LEGACY_ISOLATION_INSTANCE_PREFIX}{slug_date}_{_slug(substation_name, fallback='substation')}_{request_id}",
    )
    attachments_root = instance_root

    _ensure_dir(isolation_root, queue_payload=queue_payload)
    _ensure_dir(instance_root, queue_payload=queue_payload)

    candidate_roots = []
    for candidate in (storage_folder_path, legacy_instance_root, instance_root):
        if not candidate:
            continue
        try:
            normalized = os.path.normcase(os.path.abspath(candidate))
        except Exception:
            normalized = str(candidate)
        if normalized not in candidate_roots:
            candidate_roots.append(normalized)

    normalized_to_path = {}
    for candidate in (storage_folder_path, legacy_instance_root, instance_root):
        if not candidate:
            continue
        try:
            normalized_to_path[os.path.normcase(os.path.abspath(candidate))] = candidate
        except Exception:
            normalized_to_path[str(candidate)] = candidate

    # Migrate legacy files from older folder names and from the old "Αίτηση" subfolder
    for candidate_key in candidate_roots:
        candidate_path = normalized_to_path.get(candidate_key)
        if not candidate_path or not os.path.isdir(_win_path(candidate_path)):
            continue

        legacy_attachment_dir = os.path.join(candidate_path, "Αίτηση")
        if os.path.isdir(legacy_attachment_dir):
            _move_files_to_folder(
                _list_direct_files(legacy_attachment_dir), attachments_root
            )
            _prune_empty_dir(legacy_attachment_dir, stop_at=isolation_root)

        if os.path.normcase(os.path.abspath(candidate_path)) != os.path.normcase(
            os.path.abspath(instance_root)
        ):
            _move_files_to_folder(_list_direct_files(candidate_path), attachments_root)
            _prune_empty_dir(candidate_path, stop_at=isolation_root)

    # Preserve a directly selected existing file even when the DB row has no request_file_path yet.
    if request_file_path and os.path.isfile(_win_path(request_file_path)):
        request_parent = os.path.dirname(os.path.abspath(request_file_path))
        if os.path.normcase(request_parent) != os.path.normcase(
            os.path.abspath(attachments_root)
        ):
            copy_files_to_folder([request_file_path], attachments_root)

    copy_files_to_folder(attachment_paths or [], attachments_root)

    stored_files = _normalize_isolation_attachment_files(attachments_root, request_id)

    return {
        "storage_folder": instance_root,
        "attachments_folder": attachments_root,
        "stored_files": stored_files,
    }


def _is_dir_empty(path: str) -> bool:
    try:
        with os.scandir(_win_path(path)) as it:
            for _entry in it:
                return False
        return True
    except Exception:
        return False


def _prune_empty_dir(path: str, *, stop_at: str | None = None) -> None:
    current = os.path.abspath(path)
    stop_norm = os.path.abspath(stop_at) if stop_at else None
    while os.path.isdir(current) and _is_dir_empty(current):
        if stop_norm and os.path.normcase(current) == os.path.normcase(stop_norm):
            break
        parent = os.path.dirname(current)
        try:
            os.rmdir(current)
        except Exception:
            break
        if not parent or parent == current:
            break
        current = parent


def _is_same_or_child_path(path: str | None, parent: str | None) -> bool:
    if not path or not parent:
        return False
    try:
        abs_path = os.path.normcase(os.path.abspath(path))
        abs_parent = os.path.normcase(os.path.abspath(parent))
    except Exception:
        return False
    return abs_path == abs_parent or abs_path.startswith(abs_parent + os.sep)


def _has_duplicated_substation_segment(path: str | None, *, shared_root: str) -> bool:
    if not path:
        return False
    try:
        rel = os.path.relpath(os.path.abspath(path), os.path.abspath(shared_root))
        parts = [part for part in rel.split(os.sep) if part and part != "."]
    except Exception:
        return False
    return len(parts) >= 2 and os.path.normcase(parts[0]) == os.path.normcase(parts[1])


def _normalize_storage_row_paths(
    *,
    shared_root: str,
    substation_root: str,
    maintenance_root: str,
    instance_name: str,
    existing_instance: str | None,
    existing_media: str | None,
    existing_reports: str | None,
) -> dict[str, str]:
    canonical_instance = os.path.join(maintenance_root, instance_name)
    canonical_reports = canonical_instance
    canonical_media = os.path.join(canonical_instance, _DIR_MEDIA)

    existing_instance = _remap_legacy_shared_root(existing_instance, shared_root)
    existing_media = _remap_legacy_shared_root(existing_media, shared_root)
    existing_reports = _remap_legacy_shared_root(existing_reports, shared_root)

    use_existing_instance = False
    if existing_instance:
        try:
            instance_parent = os.path.dirname(os.path.abspath(existing_instance))
            use_existing_instance = (
                os.path.normcase(instance_parent)
                == os.path.normcase(os.path.abspath(maintenance_root))
                and _is_same_or_child_path(existing_instance, substation_root)
                and not _has_duplicated_substation_segment(
                    existing_instance, shared_root=shared_root
                )
            )
        except Exception:
            use_existing_instance = False

    instance_root = existing_instance if use_existing_instance else canonical_instance

    use_existing_reports = False
    if existing_reports:
        try:
            use_existing_reports = os.path.normcase(
                os.path.abspath(existing_reports)
            ) == os.path.normcase(
                os.path.abspath(instance_root)
            ) and not _has_duplicated_substation_segment(
                existing_reports, shared_root=shared_root
            )
        except Exception:
            use_existing_reports = False

    use_existing_media = False
    if existing_media:
        try:
            use_existing_media = (
                os.path.normcase(os.path.basename(os.path.abspath(existing_media)))
                == os.path.normcase(_DIR_MEDIA)
                and os.path.normcase(os.path.dirname(os.path.abspath(existing_media)))
                == os.path.normcase(os.path.abspath(instance_root))
                and not _has_duplicated_substation_segment(
                    existing_media, shared_root=shared_root
                )
            )
        except Exception:
            use_existing_media = False

    return {
        "instance_folder": instance_root,
        "reports_folder": existing_reports
        if use_existing_reports
        else canonical_reports,
        "media_folder": existing_media if use_existing_media else canonical_media,
    }


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


def _reconcile_legacy_shared_root_aliases(shared_root: str) -> None:
    """Merge/remove legacy top-level shared-root aliases next to shared_root."""
    current_root = os.path.abspath(shared_root)
    parent = os.path.dirname(current_root)
    candidates = [_LEGACY_SHARED_ROOT_NAME, *_LEGACY_SHARED_ROOT_ALIASES]

    for alias in candidates:
        legacy_root = os.path.abspath(os.path.join(parent, alias))
        if os.path.normcase(legacy_root) == os.path.normcase(current_root):
            continue
        _merge_legacy_path(legacy_root, current_root)


def _reconcile_duplicate_shared_root(shared_root: str) -> None:
    """Merge accidental nested shared-root folders back into the actual root."""
    current_root = os.path.abspath(shared_root)
    for _ in range(4):
        nested_root = os.path.join(current_root, _DEFAULT_SHARED_ROOT_NAME)
        if os.path.normcase(os.path.abspath(nested_root)) == os.path.normcase(
            current_root
        ):
            break
        if not os.path.isdir(nested_root):
            break
        _merge_legacy_path(nested_root, current_root)


def _reconcile_legacy_gate_root_folders(substation_root: str) -> None:
    """Fold legacy English gate/interconnection folders into Greek folders."""
    pairs = [
        ("Gate_1", _DIR_GATE_1),
        ("Gate_2", _DIR_GATE_2),
        ("Gate_3", _DIR_GATE_3),
        ("Gate_unknown", _DIR_GATE_UNKNOWN),
    ]
    for src_rel, dst_rel in pairs:
        src = os.path.join(substation_root, src_rel)
        dst = os.path.join(substation_root, dst_rel)
        _merge_legacy_path(src, dst)

    for inter_dir in ("Interconnections", _DIR_INTERCONNECTIONS):
        inter_root = os.path.join(substation_root, inter_dir)
        if not os.path.isdir(inter_root):
            continue
        try:
            child_names = list(os.listdir(inter_root))
        except Exception:
            child_names = []
        for child_name in child_names:
            src = os.path.join(inter_root, child_name)
            if not os.path.isdir(src):
                continue
            gate_rel = _gate_relative_path(_bucket_for_gate(child_name))
            if gate_rel == _DIR_GATE_UNKNOWN:
                continue
            dst = os.path.join(substation_root, gate_rel)
            _merge_legacy_path(src, dst)
        if _is_dir_empty(inter_root):
            try:
                os.rmdir(inter_root)
            except Exception:
                pass


def _reconcile_legacy_gate_children(gate_root: str) -> None:
    """Fold legacy English gate child folders into canonical Greek folders."""
    pairs = [
        ("Inspections", _DIR_INSPECTIONS),
        ("DGA_Measurements", _DIR_DGA),
        (_join_parts(_DIR_DGA_PARTS), _DIR_DGA),
    ]
    for src_rel, dst_rel in pairs:
        src = os.path.join(gate_root, src_rel)
        dst = os.path.join(gate_root, dst_rel)
        _merge_legacy_path(src, dst)


def sync_substation_gate_folders(
    conn, substation_id: int, *, db_path: str | None = None
) -> dict:
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
        # Do not create an explicit ΠΥΛΗ Άγνωστη folder: unknown gates indicate
        # data issues and should be reported instead of auto-created.
        if gate_rel == _DIR_GATE_UNKNOWN:
            # Record a warning via the created list for later reporting.
            created.append(f"SKIPPED_UNKNOWN:{gate_rel}")
            continue
        _reconcile_legacy_gate_children(gate_root)
        _ensure_dir(
            gate_root,
            queue_payload={
                "shared_root": base["shared_root"],
                "kind": "sync_gate",
                "substation_id": substation_id,
            },
        )
        # NOTE: Inspection and DGA folders are created on-demand when content
        # is actually written. Maintenance instances now live directly under
        # the gate root with a Συντ_ prefix.
        created.append(gate_rel)

    active_rel = {_gate_relative_path(b) for b in active_buckets}

    removed = []
    known_candidates = [
        _DIR_GATE_1,
        _DIR_GATE_2,
        _DIR_GATE_3,
        _DIR_GATE_UNKNOWN,
        "Gate_1",
        "Gate_2",
        "Gate_3",
        "Gate_unknown",
        # Legacy interconnection folders are migrated into gate folders; no separate
        # Interconnections candidates are needed here.
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
        if os.path.isdir(interconnections_root) and _is_dir_empty(
            interconnections_root
        ):
            try:
                os.rmdir(interconnections_root)
            except Exception:
                pass

    # Prune empty legacy maintenance folders under any gate roots so old
    # structures disappear after migration or when the shared tree is reset.
    try:
        for name in os.listdir(substation_root):
            gate_candidate = os.path.join(substation_root, name)
            if not os.path.isdir(gate_candidate):
                continue
            maintenance_candidate = os.path.join(gate_candidate, _DIR_MAINTENANCE)
            if os.path.isdir(maintenance_candidate) and _is_dir_empty(
                maintenance_candidate
            ):
                try:
                    os.rmdir(maintenance_candidate)
                except Exception:
                    pass
    except Exception:
        pass

    # Additionally, remove empty gate roots (e.g. 'ΠΥΛΗ 2') when they contain
    # no files and no meaningful subfolders. This handles cases where a gate
    # folder was created but never populated.
    try:
        for name in os.listdir(substation_root):
            gate_dir = os.path.join(substation_root, name)
            if not os.path.isdir(gate_dir):
                continue

            # Consider gate roots and the Interconnections parent
            norm = name.strip().lower()
            if not (
                norm.startswith(_DIR_GATE_1.split()[0].lower())
                or norm.startswith("πυλη")
                or norm == _DIR_INTERCONNECTIONS.lower()
            ):
                continue

            # Walk the tree to see if any files exist or any non-empty directories
            has_content = False
            for root, dirs, files in os.walk(gate_dir):
                if files:
                    has_content = True
                    break
                for d in dirs:
                    dpath = os.path.join(root, d)
                    if not _is_dir_empty(dpath):
                        has_content = True
                        break
                if has_content:
                    break

            if not has_content:
                try:
                    shutil.rmtree(gate_dir)
                except Exception:
                    try:
                        os.rmdir(gate_dir)
                    except Exception:
                        pass
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
    persist_storage_rows: bool = False,
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
        instance_folder = (
            row[1] if isinstance(row, (tuple, list)) else row["instance_folder"]
        )
        media_folder = row[2] if isinstance(row, (tuple, list)) else row["media_folder"]
        reports_folder = (
            row[3] if isinstance(row, (tuple, list)) else row["reports_folder"]
        )
        existing_by_gate_key[gate_key] = {
            "instance_folder": instance_folder,
            "media_folder": media_folder,
            "reports_folder": reports_folder,
        }

    created_rows = []
    media_targets = []

    for bucket in gate_buckets:
        gate_rel = _gate_relative_path(bucket)
        gate_key = f"{bucket[0]}:{bucket[1]}"
        gate_root = os.path.join(substation_root, gate_rel)
        _reconcile_legacy_gate_children(gate_root)
        maintenance_root = os.path.join(
            gate_root,
            _maintenance_root_relative_path(maintenance_type),
        )
        instance_name = _maintenance_instance_folder_name(
            date_time,
            substation_name=substation_name_for_slug,
            elements=elements_for_slug,
            maintenance_id=maintenance_id,
            maintenance_type=maintenance_type,
            gate_root=gate_root,
        )
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
        # NOTE: Inspections and DGA folders created on-demand when actually used
        # Prevents empty folder clutter in OneDrive

        existing = existing_by_gate_key.get(gate_key) or {}
        normalized_paths = _normalize_storage_row_paths(
            shared_root=shared_root,
            substation_root=substation_root,
            maintenance_root=maintenance_root,
            instance_name=instance_name,
            existing_instance=existing.get("instance_folder"),
            existing_media=existing.get("media_folder"),
            existing_reports=existing.get("reports_folder"),
        )
        instance_root = normalized_paths["instance_folder"]
        reports_root = normalized_paths["reports_folder"]
        media_root = normalized_paths["media_folder"]

        # Defer creating the instance/reports/media folders until an actual
        # file is written. Copy routines _distribute_attachments_and_register
        # and copy_files_to_folder create their target folders as needed.
        # NOTE: Report subfolders are created ON-DEMAND in report_sync.py when
        # reports are actually generated. This avoids leaving empty folders
        # in the shared OneDrive tree for maintenances with no files.

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

    try:
        copied_media, copied_reports = _distribute_attachments_and_register(
            conn, attachment_paths or [], created_rows, maintenance_id, element_ids
        )
    except Exception:
        copied_media = _copy_media_to_targets(attachment_paths or [], media_targets)
        copied_reports = 0

    cur = conn.cursor()

    # If nothing was copied and there were no pre-existing storage rows,
    # avoid inserting placeholder DB rows unless the caller explicitly needs
    # persisted storage targets for later report generation.
    total_copied = (copied_media or 0) + (copied_reports or 0)
    if total_copied == 0 and not existing_rows and not persist_storage_rows:
        for row in created_rows:
            try:
                # Remove the instance folder tree if it's empty (prune up to substation root)
                instance_folder = row.get("instance_folder")
                if instance_folder:
                    _prune_empty_dir(
                        instance_folder, stop_at=os.path.dirname(instance_folder)
                    )
            except Exception:
                continue
        primary_media = None
    else:
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
        "copied_media_count": copied_media,
        "copied_reports_count": copied_reports,
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
        # Shared folder may have been wiped. Rebuild storage-path metadata on
        # demand so report generation can recreate the canonical folder tree
        # without leaving empty directories behind.
        try:
            cur.execute(
                """
                SELECT substation_id, name, maintenance_type, date_time
                FROM maintenance
                WHERE id=?
                """,
                (maintenance_id,),
            )
            maintenance_row = cur.fetchone()
            if maintenance_row:
                substation_id = (
                    maintenance_row[0]
                    if isinstance(maintenance_row, (tuple, list))
                    else maintenance_row["substation_id"]
                )
                maintenance_name = (
                    maintenance_row[1]
                    if isinstance(maintenance_row, (tuple, list))
                    else maintenance_row["name"]
                )
                maintenance_type = (
                    maintenance_row[2]
                    if isinstance(maintenance_row, (tuple, list))
                    else maintenance_row["maintenance_type"]
                )
                date_time = (
                    maintenance_row[3]
                    if isinstance(maintenance_row, (tuple, list))
                    else maintenance_row["date_time"]
                )

                cur.execute(
                    """
                    SELECT e.id
                    FROM maintenance_elements me
                    JOIN elements e ON e.id = me.element_id
                    WHERE me.maintenance_id=?
                    """,
                    (maintenance_id,),
                )
                element_ids = [
                    r[0] if isinstance(r, (tuple, list)) else r["id"]
                    for r in (cur.fetchall() or [])
                ]

                ensure_maintenance_folders(
                    conn,
                    maintenance_id=maintenance_id,
                    substation_id=substation_id,
                    maintenance_name=maintenance_name,
                    maintenance_type=maintenance_type,
                    date_time=date_time,
                    element_ids=element_ids,
                    attachment_paths=[],
                    persist_storage_rows=True,
                    db_path=db_path,
                )

                cur.execute(
                    """
                    SELECT reports_folder
                    FROM maintenance_storage_paths
                    WHERE maintenance_id=? AND gate_key=?
                    """,
                    (maintenance_id, gate_key),
                )
                rows = cur.fetchall() or []
        except Exception:
            rows = []

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
    targets: list[str] = []
    seen: set[str] = set()
    for row in rows:
        reports_root_raw = (
            row[0] if isinstance(row, (tuple, list)) else row["reports_folder"]
        )
        reports_root = _normalize_reports_root_path(
            _remap_legacy_shared_root(reports_root_raw, shared_root)
        )
        if not reports_root:
            continue
        if reports_root in seen:
            continue
        # NOTE: Folder creation moved to caller - only create when files are generated
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
    dga_root = os.path.join(gate_root, _DIR_DGA)

    queue_payload = {
        "kind": "ensure_dga_folder",
        "substation_id": substation_id,
        "gate": gate_rel,
        "shared_root": shared_root,
        "created_at": datetime.now().isoformat(),
    }

    _ensure_dir(gate_root, queue_payload=queue_payload)
    # NOTE: DGA root and measurement folders created on-demand when reports are generated

    try:
        dt = datetime.fromisoformat((measurement_date or "").replace("Z", "+00:00"))
        dt_part = dt.strftime("%Y%m%d")
    except Exception:
        dt_part = datetime.now().strftime("%Y%m%d")

    folder_name = f"{dt_part}_{_slug(element_name, fallback='transformer')}"
    folder_path = os.path.join(dga_root, folder_name)
    raw_data = os.path.join(folder_path, "raw_data")
    # Folder and raw_data will be created when files are actually written

    return {
        "gate_folder": gate_rel,
        "dga_root": dga_root,
        "folder_path": folder_path,
        "raw_data_path": raw_data,
    }


def delete_maintenance_folders(conn, maintenance_id: int) -> int:
    cur = conn.cursor()
    report_cleanup = invalidate_maintenance_reports(
        conn, maintenance_id, delete_files=True
    )
    dga_cleanup = prune_stale_dga_measurements(
        conn, maintenance_id=maintenance_id, valid_element_ids=[]
    )
    cur.execute(
        "SELECT instance_folder FROM maintenance_storage_paths WHERE maintenance_id=?",
        (maintenance_id,),
    )
    rows = cur.fetchall() or []

    deleted = int(report_cleanup.get("deleted_files", 0) or 0) + int(
        dga_cleanup.get("deleted_files", 0) or 0
    )
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

    cur.execute(
        "DELETE FROM maintenance_storage_paths WHERE maintenance_id=?",
        (maintenance_id,),
    )
    return deleted


def invalidate_maintenance_reports(
    conn, maintenance_id: int, *, delete_files: bool = True
) -> dict:
    """Remove tracked maintenance PDFs so sync regenerates current output."""
    cur = conn.cursor()

    cur.execute(
        "SELECT report_path FROM maintenance_report_paths WHERE maintenance_id=?",
        (maintenance_id,),
    )
    element_paths = [
        row[0] if isinstance(row, (tuple, list)) else row["report_path"]
        for row in (cur.fetchall() or [])
    ]
    cur.execute(
        "SELECT report_path FROM maintenance_overview_report_paths WHERE maintenance_id=?",
        (maintenance_id,),
    )
    overview_paths = [
        row[0] if isinstance(row, (tuple, list)) else row["report_path"]
        for row in (cur.fetchall() or [])
    ]

    deleted_files = 0
    if delete_files:
        seen_paths = set()
        for report_path in element_paths + overview_paths:
            if not report_path or report_path in seen_paths:
                continue
            seen_paths.add(report_path)
            try:
                if os.path.isfile(report_path):
                    os.remove(report_path)
                    deleted_files += 1
            except Exception:
                pass

    cur.execute(
        "DELETE FROM maintenance_report_paths WHERE maintenance_id=?", (maintenance_id,)
    )
    element_rows_deleted = cur.rowcount if cur.rowcount is not None else 0
    cur.execute(
        "DELETE FROM maintenance_overview_report_paths WHERE maintenance_id=?",
        (maintenance_id,),
    )
    overview_rows_deleted = cur.rowcount if cur.rowcount is not None else 0

    return {
        "maintenance_id": int(maintenance_id),
        "deleted_files": int(deleted_files),
        "element_rows_deleted": int(element_rows_deleted),
        "overview_rows_deleted": int(overview_rows_deleted),
    }


def prune_stale_dga_measurements(
    conn,
    *,
    maintenance_id: int,
    valid_element_ids: Iterable[int] | None,
) -> dict:
    """Delete DGA rows/files whose element is no longer part of the maintenance."""
    valid_ids = sorted({int(x) for x in (valid_element_ids or []) if x is not None})
    cur = conn.cursor()

    if valid_ids:
        placeholders = ",".join(["?"] * len(valid_ids))
        cur.execute(
            f"""
            SELECT id, report_path
            FROM dga_measurements
            WHERE maintenance_id=? AND element_id NOT IN ({placeholders})
            """,
            (maintenance_id, *valid_ids),
        )
    else:
        cur.execute(
            "SELECT id, report_path FROM dga_measurements WHERE maintenance_id=?",
            (maintenance_id,),
        )

    rows = cur.fetchall() or []
    deleted_files = 0
    deleted_rows = 0
    for row in rows:
        measurement_id = row[0] if isinstance(row, (tuple, list)) else row["id"]
        report_path = row[1] if isinstance(row, (tuple, list)) else row["report_path"]
        try:
            if report_path and os.path.isfile(report_path):
                os.remove(report_path)
                deleted_files += 1
        except Exception:
            pass
        cur.execute("DELETE FROM dga_measurements WHERE id=?", (measurement_id,))
        deleted_rows += 1

    return {
        "maintenance_id": int(maintenance_id),
        "deleted_rows": int(deleted_rows),
        "deleted_files": int(deleted_files),
    }


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
    cur.execute(
        """
        SELECT 1
        FROM maintenance_elements
        WHERE maintenance_id=? AND element_id=?
        """,
        (maintenance_id, element_id),
    )
    if not cur.fetchone():
        raise ValueError(
            f"Cannot track report for stale maintenance-element pair ({maintenance_id}, {element_id})"
        )
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


def delete_orphaned_maintenance_report_paths(conn) -> int:
    """Delete tracked element report rows that no longer map to maintenance_elements."""
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM maintenance_report_paths
        WHERE NOT EXISTS (
            SELECT 1
            FROM maintenance_elements me
            WHERE me.maintenance_id = maintenance_report_paths.maintenance_id
              AND me.element_id = maintenance_report_paths.element_id
        )
        """
    )
    return cur.rowcount if cur.rowcount is not None else 0


def upsert_maintenance_overview_report_path(
    conn,
    *,
    maintenance_id: int,
    gate_key: str,
    report_path: str,
    report_type: str = "pdf_overview",
) -> None:
    cur = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        """
        INSERT INTO maintenance_overview_report_paths
        (maintenance_id, gate_key, report_type, report_path, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(maintenance_id, gate_key, report_type) DO UPDATE SET
            report_path=excluded.report_path,
            updated_at=excluded.updated_at
        """,
        (maintenance_id, gate_key, report_type, report_path, now, now),
    )


def get_maintenance_overview_report_path(
    conn,
    *,
    maintenance_id: int,
    gate_key: str,
    report_type: str = "pdf_overview",
    verify_exists: bool = True,
) -> str | None:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT report_path
        FROM maintenance_overview_report_paths
        WHERE maintenance_id=? AND gate_key=? AND report_type=?
        """,
        (maintenance_id, gate_key, report_type),
    )
    row = cur.fetchone()
    if not row:
        return None
    path = row[0] if isinstance(row, (tuple, list)) else row["report_path"]
    if verify_exists and (not path or not os.path.exists(path)):
        return None
    return path


def get_maintenance_overview_targets(
    conn,
    *,
    maintenance_id: int,
    db_path: str | None = None,
) -> list[dict]:
    """Return unique report roots for each gate bucket of a maintenance."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT gate_key, reports_folder
        FROM maintenance_storage_paths
        WHERE maintenance_id=?
        ORDER BY gate_key
        """,
        (maintenance_id,),
    )
    rows = cur.fetchall() or []

    if not rows:
        try:
            cur.execute(
                """
                SELECT substation_id, name, maintenance_type, date_time
                FROM maintenance
                WHERE id=?
                """,
                (maintenance_id,),
            )
            maintenance_row = cur.fetchone()
            if maintenance_row:
                substation_id = (
                    maintenance_row[0]
                    if isinstance(maintenance_row, (tuple, list))
                    else maintenance_row["substation_id"]
                )
                maintenance_name = (
                    maintenance_row[1]
                    if isinstance(maintenance_row, (tuple, list))
                    else maintenance_row["name"]
                )
                maintenance_type = (
                    maintenance_row[2]
                    if isinstance(maintenance_row, (tuple, list))
                    else maintenance_row["maintenance_type"]
                )
                date_time = (
                    maintenance_row[3]
                    if isinstance(maintenance_row, (tuple, list))
                    else maintenance_row["date_time"]
                )

                cur.execute(
                    "SELECT element_id FROM maintenance_elements WHERE maintenance_id=?",
                    (maintenance_id,),
                )
                element_ids = [
                    r[0] if isinstance(r, (tuple, list)) else r["element_id"]
                    for r in (cur.fetchall() or [])
                ]

                ensure_maintenance_folders(
                    conn,
                    maintenance_id=maintenance_id,
                    substation_id=substation_id,
                    maintenance_name=maintenance_name,
                    maintenance_type=maintenance_type,
                    date_time=date_time,
                    element_ids=element_ids,
                    attachment_paths=[],
                    persist_storage_rows=True,
                    db_path=db_path,
                )
                cur.execute(
                    """
                    SELECT gate_key, reports_folder
                    FROM maintenance_storage_paths
                    WHERE maintenance_id=?
                    ORDER BY gate_key
                    """,
                    (maintenance_id,),
                )
                rows = cur.fetchall() or []
        except Exception:
            rows = []

    shared_root = resolve_shared_root(db_path)
    targets = []
    seen = set()
    for row in rows:
        gate_key = row[0] if isinstance(row, (tuple, list)) else row["gate_key"]
        reports_root_raw = (
            row[1] if isinstance(row, (tuple, list)) else row["reports_folder"]
        )
        reports_root = _normalize_reports_root_path(
            _remap_legacy_shared_root(reports_root_raw, shared_root)
        )
        if not gate_key or not reports_root or (gate_key, reports_root) in seen:
            continue
        seen.add((gate_key, reports_root))
        targets.append({"gate_key": gate_key, "reports_root": reports_root})

    return targets


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


def relink_existing_maintenance_assets(
    conn, *, db_path: str | None = None, progress_callback=None
) -> dict:
    """Relink existing folder/media/report paths into DB if missing.

    This does not create new files. It discovers existing paths under maintained
    folder structures and stores missing DB links.

    Args:
        conn: Database connection
        db_path: Path to database file
        progress_callback: Optional callable(operation, substation, current, total) for progress
    """
    cur = conn.cursor()

    # Resolve shared root for this DB so we can reconcile legacy duplicate roots
    shared_root = resolve_shared_root(db_path)

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

    # Preload report rows so total_work is available for media-phase progress.
    cur.execute(
        """
        SELECT m.id, me.element_id, e.name, e.element_type, e.gate, e.breaker_category, s.name
        FROM maintenance m
        JOIN maintenance_elements me ON me.maintenance_id = m.id
        JOIN elements e ON e.id = me.element_id
        JOIN substations s ON s.id = m.substation_id
        ORDER BY m.id DESC
        """
    )
    rows = cur.fetchall() or []

    # total_work covers media phase plus one progress tick for every report row.
    total_work = len(media_rows) + len(rows)

    media_linked = 0
    seen_media = set()
    current_work = 0
    _reconcile_duplicate_shared_root(shared_root)

    for row in media_rows:
        maintenance_id = row[0] if isinstance(row, (tuple, list)) else row["id"]
        existing_link = (
            row[1]
            if isinstance(row, (tuple, list))
            else row["onedrive_media_folder_link"]
        )
        media_folder = row[2] if isinstance(row, (tuple, list)) else row["media_folder"]
        substation_name = row[3] if isinstance(row, (tuple, list)) else row["name"]

        current_work += 1
        if progress_callback:
            progress_callback(
                operation="Relinking media folders",
                substation=substation_name,
                current=current_work,
                total=total_work,
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
    report_linked = 0
    report_already = 0
    report_missing = 0

    for row in rows:
        maintenance_id = row[0] if isinstance(row, (tuple, list)) else row["id"]
        element_id = row[1] if isinstance(row, (tuple, list)) else row["element_id"]
        element_name = row[2] if isinstance(row, (tuple, list)) else row["name"]
        element_type = row[3] if isinstance(row, (tuple, list)) else row["element_type"]
        gate = row[4] if isinstance(row, (tuple, list)) else row["gate"]
        breaker_category = (
            row[5] if isinstance(row, (tuple, list)) else row["breaker_category"]
        )
        substation_name = row[6] if isinstance(row, (tuple, list)) else row["name"]

        current_work += 1
        if progress_callback:
            progress_callback(
                operation="Relinking report files",
                substation=substation_name,
                current=current_work,
                total=total_work,
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
        subfolder = os.path.join(
            reports_root,
            _report_subfolder_name_for_element(element_type, breaker_category),
        )
        legacy_subfolder = os.path.join(
            _legacy_reports_root(reports_root),
            _legacy_report_subfolder_name_for_element(element_type, breaker_category),
        )
        if not os.path.isdir(subfolder) and not os.path.isdir(legacy_subfolder):
            report_missing += 1
            continue

        canonical_name = _canonical_report_filename(
            substation_name or "",
            element_name or "",
            maintenance_id,
            parent_dir=subfolder,
        )
        canonical = os.path.join(subfolder, canonical_name)

        found_path = canonical if os.path.isfile(canonical) else None
        if not found_path:
            legacy_matches = []
            try:
                search_dirs = []
                if os.path.isdir(subfolder):
                    search_dirs.append(subfolder)
                if (
                    os.path.isdir(legacy_subfolder)
                    and legacy_subfolder not in search_dirs
                ):
                    search_dirs.append(legacy_subfolder)
                for search_dir in search_dirs:
                    for fname in os.listdir(search_dir):
                        if fname.lower().endswith(".pdf"):
                            # Look for old format: Maintenance_M{id}_E{id}_...
                            if fname.startswith(
                                f"Maintenance_M{maintenance_id}_E{element_id}_"
                            ):
                                legacy_matches.append(os.path.join(search_dir, fname))
                            # Look for old element name prefix format: Maintenance_{element}_...
                            elif fname.startswith(
                                f"Maintenance_{(element_name or '').replace('/', '-').replace('\\', '-').replace(':', '-')}_"
                            ):
                                legacy_matches.append(os.path.join(search_dir, fname))
            except Exception:
                legacy_matches = []

            # Also support legacy short-name outputs under "_AUTO_SHORT".
            auto_short_dir = os.path.join(subfolder, "_AUTO_SHORT")
            if os.path.isdir(auto_short_dir):
                auto_short_candidates = [
                    os.path.join(
                        auto_short_dir, f"M{maintenance_id}_E{element_id}.pdf"
                    ),
                    os.path.join(auto_short_dir, canonical_name),
                ]
                for candidate in auto_short_candidates:
                    if os.path.isfile(candidate):
                        legacy_matches.append(candidate)

            if legacy_matches:
                legacy_matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)
                found_path = legacy_matches[0]
                # If the legacy match is a long/broken filename and the
                # canonical short name would be accessible, move it to the
                # canonical name so users don't accidentally open the old
                # long path. Use pdf_reports.move_pdf_preserve_title for a
                # safe move that preserves PDF Title metadata.
                try:
                    from pdf_reports import move_pdf_preserve_title

                    cand = os.path.join(
                        subfolder,
                        _canonical_report_filename(
                            substation_name or "",
                            element_name or "",
                            maintenance_id,
                            parent_dir=subfolder,
                        ),
                    )
                    # Only attempt move when canonical path appears shorter than
                    # the system budget and does not already exist.
                    if len(cand) <= _REPORT_FULL_PATH_MAX and not os.path.exists(cand):
                        try:
                            ok = move_pdf_preserve_title(found_path, cand)
                            if ok:
                                found_path = cand
                        except Exception:
                            pass
                except Exception:
                    pass

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


def _replace_prefix_ci(
    path: str | None, old_prefix: str | None, new_prefix: str | None
) -> str | None:
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
        SELECT m.id, m.substation_id, m.date_time, s.name, m.maintenance_type
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
        substation_id = (
            row[1] if isinstance(row, (tuple, list)) else row["substation_id"]
        )
        date_time = row[2] if isinstance(row, (tuple, list)) else row["date_time"]
        substation_name = row[3] if isinstance(row, (tuple, list)) else row["name"]
        maintenance_type = (
            row[4] if isinstance(row, (tuple, list)) else row["maintenance_type"]
        )
        base = ensure_substation_structure(conn, substation_id, db_path=db_path)
        substation_root = base["substation_root"]

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
            old_instance_raw = (
                prow[1] if isinstance(prow, (tuple, list)) else prow["instance_folder"]
            )
            old_media_raw = (
                prow[2] if isinstance(prow, (tuple, list)) else prow["media_folder"]
            )
            old_reports_raw = (
                prow[3] if isinstance(prow, (tuple, list)) else prow["reports_folder"]
            )
            gate_root = os.path.join(
                substation_root, _gate_relative_path_from_gate_key(gate_key)
            )
            target_instance_name = _maintenance_instance_folder_name(
                date_time,
                substation_name=substation_name,
                elements=elements,
                maintenance_id=maintenance_id,
                maintenance_type=maintenance_type,
                gate_root=gate_root,
            )

            old_instance_mapped = _remap_legacy_shared_root(
                old_instance_raw, shared_root
            )
            old_media_mapped = _remap_legacy_shared_root(old_media_raw, shared_root)
            old_reports_mapped = _remap_legacy_shared_root(old_reports_raw, shared_root)

            instance_parent = os.path.join(
                substation_root,
                _gate_relative_path_from_gate_key(gate_key),
                _maintenance_root_relative_path(maintenance_type),
            )
            if not instance_parent:
                continue
            target_instance = os.path.join(instance_parent, target_instance_name)

            current_instance_path = old_instance_mapped or old_instance_raw or ""
            current_abs = (
                os.path.normcase(os.path.abspath(current_instance_path))
                if current_instance_path
                else ""
            )
            target_abs = os.path.normcase(os.path.abspath(target_instance))
            needs_move = current_abs != target_abs

            # Resolve collisions by adding maintenance id suffix.
            final_target = target_instance
            if needs_move and os.path.exists(final_target):
                same = os.path.normcase(
                    os.path.abspath(final_target)
                ) == os.path.normcase(
                    os.path.abspath(
                        old_instance_mapped or old_instance_raw or final_target
                    )
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
            if (
                needs_move
                and not source_path
                and instance_parent
                and os.path.isdir(instance_parent)
            ):
                try:
                    legacy_suffix = f"Email_instance_{maintenance_id}"
                    for name in os.listdir(instance_parent):
                        cand = os.path.join(instance_parent, name)
                        if os.path.isdir(cand) and name.endswith(legacy_suffix):
                            source_path = cand
                            break
                except Exception:
                    pass

            if (
                needs_move
                and source_path
                and os.path.normcase(os.path.abspath(source_path))
                != os.path.normcase(os.path.abspath(final_target))
            ):
                try:
                    old_parent = os.path.dirname(source_path)
                    if not dry_run:
                        os.makedirs(os.path.dirname(final_target), exist_ok=True)
                        shutil.move(source_path, final_target)
                        _prune_empty_dir(old_parent, stop_at=gate_root)
                    renamed_folders += 1
                except Exception as exc:
                    errors.append(
                        f"maintenance {maintenance_id} gate {gate_key}: {exc}"
                    )
                    # Retry with a compact fallback name to avoid long-path errors.
                    try:
                        fallback_name = _instance_slug_short_fallback(
                            date_time,
                            substation_name,
                            maintenance_id,
                        )
                        fallback_target = os.path.join(instance_parent, fallback_name)
                        if fallback_target != final_target and not os.path.exists(
                            fallback_target
                        ):
                            if not dry_run:
                                os.makedirs(
                                    os.path.dirname(fallback_target), exist_ok=True
                                )
                                shutil.move(source_path, fallback_target)
                            renamed_folders += 1
                            final_target = fallback_target
                    except Exception:
                        # Keep going so DB links can still be normalized away from
                        # legacy naming even when the old folder is missing.
                        pass

            # Compute updated DB paths by prefix replacement from old->new.
            new_instance = (
                final_target
                if needs_move
                else (old_instance_mapped or old_instance_raw)
            )
            new_media = _replace_prefix_ci(
                old_media_mapped or old_media_raw,
                old_instance_mapped or old_instance_raw,
                new_instance,
            )
            new_reports = _replace_prefix_ci(
                old_reports_mapped or old_reports_raw,
                old_instance_mapped or old_instance_raw,
                new_instance,
            )

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
                        (
                            new_instance,
                            new_media,
                            new_reports,
                            maintenance_id,
                            gate_key,
                        ),
                    )
                storage_rows_updated += 1

            # Update primary media link in maintenance table for this maintenance.
            cur.execute(
                "SELECT onedrive_media_folder_link FROM maintenance WHERE id=?",
                (maintenance_id,),
            )
            mrow = cur.fetchone()
            old_link = (
                mrow[0]
                if mrow and isinstance(mrow, (tuple, list))
                else (mrow["onedrive_media_folder_link"] if mrow else None)
            )
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
                old_report_path = (
                    rrow[1] if isinstance(rrow, (tuple, list)) else rrow["report_path"]
                )
                new_report_path = _replace_prefix_ci(
                    old_report_path, old_instance_raw, new_instance
                )
                new_report_path = _replace_prefix_ci(
                    new_report_path, old_instance_mapped, new_instance
                )
                if (new_report_path or "") != (old_report_path or ""):
                    if not dry_run:
                        cur.execute(
                            "UPDATE maintenance_report_paths SET report_path=?, updated_at=? WHERE id=?",
                            (
                                new_report_path,
                                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                rid,
                            ),
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


def retrofit_shared_root_paths(
    conn,
    *,
    db_path: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Rewrite stored paths to the current shared root and canonical labels."""
    shared_root = resolve_shared_root(db_path)
    cur = conn.cursor()

    def _canonicalize_path(
        path: str | None,
        *,
        element_type: str | None = None,
        breaker_category: str | None = None,
    ) -> str | None:
        remapped = _remap_legacy_shared_root(path, shared_root)
        return _map_folder_labels_in_path(
            remapped,
            element_type=element_type,
            breaker_category=breaker_category,
        )

    stats = {
        "storage_rows_updated": 0,
        "maintenance_links_updated": 0,
        "report_paths_updated": 0,
        "overview_report_paths_updated": 0,
        "dga_report_paths_updated": 0,
    }

    cur.execute(
        "SELECT maintenance_id, gate_key, instance_folder, media_folder, reports_folder FROM maintenance_storage_paths"
    )
    for row in cur.fetchall() or []:
        maintenance_id, gate_key, instance_folder, media_folder, reports_folder = row
        new_instance = _canonicalize_path(instance_folder)
        new_media = _canonicalize_path(media_folder)
        new_reports = _canonicalize_path(reports_folder)
        if (
            (new_instance or "") != (instance_folder or "")
            or (new_media or "") != (media_folder or "")
            or (new_reports or "") != (reports_folder or "")
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
            stats["storage_rows_updated"] += 1

    cur.execute("SELECT id, onedrive_media_folder_link FROM maintenance")
    for maintenance_id, old_link in cur.fetchall() or []:
        new_link = _canonicalize_path(old_link)
        if (new_link or "") != (old_link or ""):
            if not dry_run:
                cur.execute(
                    "UPDATE maintenance SET onedrive_media_folder_link=? WHERE id=?",
                    (new_link, maintenance_id),
                )
            stats["maintenance_links_updated"] += 1

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute(
        """
        SELECT mrp.id, mrp.report_path, e.element_type, e.breaker_category
        FROM maintenance_report_paths mrp
        JOIN elements e ON e.id = mrp.element_id
        """
    )
    for report_id, old_report_path, element_type, breaker_category in (
        cur.fetchall() or []
    ):
        new_report_path = _canonicalize_path(
            old_report_path,
            element_type=element_type,
            breaker_category=breaker_category,
        )
        if (new_report_path or "") != (old_report_path or ""):
            if not dry_run:
                cur.execute(
                    "UPDATE maintenance_report_paths SET report_path=?, updated_at=? WHERE id=?",
                    (new_report_path, timestamp, report_id),
                )
            stats["report_paths_updated"] += 1

    cur.execute("SELECT id, report_path FROM maintenance_overview_report_paths")
    for report_id, old_report_path in cur.fetchall() or []:
        new_report_path = _canonicalize_path(old_report_path)
        if (new_report_path or "") != (old_report_path or ""):
            if not dry_run:
                cur.execute(
                    "UPDATE maintenance_overview_report_paths SET report_path=?, updated_at=? WHERE id=?",
                    (new_report_path, timestamp, report_id),
                )
            stats["overview_report_paths_updated"] += 1

    cur.execute("SELECT id, report_path FROM dga_measurements")
    for measurement_id, old_report_path in cur.fetchall() or []:
        new_report_path = _canonicalize_path(old_report_path)
        if (new_report_path or "") != (old_report_path or ""):
            if not dry_run:
                cur.execute(
                    "UPDATE dga_measurements SET report_path=?, updated_at=? WHERE id=?",
                    (new_report_path, timestamp, measurement_id),
                )
            stats["dga_report_paths_updated"] += 1

    if not dry_run:
        conn.commit()

    return stats


def _map_folder_labels_in_path(
    path: str | None,
    *,
    element_type: str | None = None,
    breaker_category: str | None = None,
) -> str | None:
    """Map legacy English folder labels in a Windows path to canonical Greek labels."""
    if not path:
        return path
    try:
        drive, tail = os.path.splitdrive(path)
        parts = [p for p in re.split(r"[\\/]+", tail.strip("\\/")) if p]
        mapped: list[str] = []
        for i, part in enumerate(parts):
            low = part.lower()
            if low in {"interconnections", _DIR_INTERCONNECTIONS.lower()}:
                next_part = parts[i + 1] if i + 1 < len(parts) else ""
                gate_rel = _gate_relative_path(_bucket_for_gate(next_part))
                if gate_rel != _DIR_GATE_UNKNOWN:
                    mapped.append(gate_rel)
                continue
            prev_low = parts[i - 1].lower() if i > 0 else ""
            if prev_low in {"interconnections", _DIR_INTERCONNECTIONS.lower()}:
                if _gate_relative_path(_bucket_for_gate(part)) != _DIR_GATE_UNKNOWN:
                    continue
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
            elif low == "maintenance" or low == _DIR_MAINTENANCE.lower():
                continue
            elif low == "faults" or low == _DIR_FAULTS.lower():
                continue
            elif low == "inspections":
                mapped.append(_DIR_INSPECTIONS)
            elif low == "dga_measurements":
                mapped.append(_DIR_DGA)
            elif low == _DIR_DGA_PARTS[0].lower():
                next_low = parts[i + 1].lower() if i + 1 < len(parts) else ""
                if next_low == _DIR_DGA_PARTS[1].lower():
                    mapped.append(_DIR_DGA)
                else:
                    mapped.append(part)
            elif low == _DIR_DGA_PARTS[1].lower():
                prev_low = parts[i - 1].lower() if i > 0 else ""
                if prev_low == _DIR_DGA_PARTS[0].lower():
                    continue
                mapped.append(part)
            elif low == "photos_videos":
                mapped.append(_DIR_MEDIA)
            elif low == "reports" or low == _DIR_REPORTS.lower():
                continue
            elif low == "transformers":
                mapped.append(_report_prefixed_name(_DIR_REPORTS_TRANSFORMERS))
            elif low == "other":
                mapped.append(_report_prefixed_name(_DIR_REPORTS_OTHER))
            elif low == "breakers":
                if element_type:
                    mapped.append(
                        _report_subfolder_name_for_element(
                            element_type, breaker_category
                        )
                    )
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
        maintenance_id = (
            row[0] if isinstance(row, (tuple, list)) else row["maintenance_id"]
        )
        gate_key = row[1] if isinstance(row, (tuple, list)) else row["gate_key"]
        old_instance = (
            row[2] if isinstance(row, (tuple, list)) else row["instance_folder"]
        )
        old_media = row[3] if isinstance(row, (tuple, list)) else row["media_folder"]
        old_reports = (
            row[4] if isinstance(row, (tuple, list)) else row["reports_folder"]
        )

        new_instance = _map_folder_labels_in_path(old_instance)
        new_media = _map_folder_labels_in_path(old_media)
        new_reports = _map_folder_labels_in_path(old_reports)

        try:
            if (
                old_instance
                and new_instance
                and os.path.normcase(os.path.abspath(old_instance))
                != os.path.normcase(os.path.abspath(new_instance))
            ):
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
        old_link = (
            row[1]
            if isinstance(row, (tuple, list))
            else row["onedrive_media_folder_link"]
        )
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


def sync_all_substation_structures(
    conn, *, db_path: str | None = None, quiet: bool = True, progress_callback=None
) -> dict:
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
    try:
        _reconcile_duplicate_shared_root(resolve_shared_root(db_path))
    except Exception:
        pass

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
                total=total,
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


def regenerate_maintenance_reports(
    conn,
    *,
    db_path: str | None = None,
    quiet: bool = True,
    limit: int = None,
    progress_callback=None,
) -> dict:
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
        from pdf_reports import generate_maintenance_report, repair_pdf_access
        from report_sync import ensure_maintenance_overview_reports
    except ImportError:
        return {
            "total": 0,
            "generated": 0,
            "skipped": 0,
            "failed": 0,
            "error": "pdf_reports module not available",
        }

    cur = conn.cursor()
    shared_root = resolve_shared_root(db_path)
    delete_orphaned_maintenance_report_paths(conn)
    retrofit_shared_root_paths(conn, db_path=db_path, dry_run=False)
    query = """
        SELECT DISTINCT m.id as maintenance_id, me.element_id, e.name as element_name,
               e.gate, e.element_type, e.breaker_category, m.substation_id, m.name as maintenance_name,
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
    touched_maintenance_ids = set()
    all_maintenance_ids = set()
    maintenance_context: dict[int, dict] = {}

    for row in records:
        maintenance_id = (
            row[0] if isinstance(row, (tuple, list)) else row["maintenance_id"]
        )
        element_id = row[1] if isinstance(row, (tuple, list)) else row["element_id"]
        gate = row[3] if isinstance(row, (tuple, list)) else row["gate"]
        substation_id = (
            row[6] if isinstance(row, (tuple, list)) else row["substation_id"]
        )
        maintenance_name = (
            row[7] if isinstance(row, (tuple, list)) else row["maintenance_name"]
        )
        maintenance_type = (
            row[8] if isinstance(row, (tuple, list)) else row["maintenance_type"]
        )
        date_time = row[9] if isinstance(row, (tuple, list)) else row["date_time"]
        context = maintenance_context.setdefault(
            maintenance_id,
            {
                "substation_id": substation_id,
                "maintenance_name": maintenance_name,
                "maintenance_type": maintenance_type,
                "date_time": date_time,
                "element_ids": set(),
                "reports_roots": {},
                "folders_ready": None,
            },
        )
        context["element_ids"].add(element_id)
        bucket = _bucket_for_gate(gate)
        gate_key = f"{bucket[0]}:{bucket[1]}"
        context["reports_roots"].setdefault(gate_key, None)

    for idx, row in enumerate(records):
        maintenance_id = (
            row[0] if isinstance(row, (tuple, list)) else row["maintenance_id"]
        )
        element_id = row[1] if isinstance(row, (tuple, list)) else row["element_id"]
        element_name = row[2] if isinstance(row, (tuple, list)) else row["element_name"]
        gate = row[3] if isinstance(row, (tuple, list)) else row["gate"]
        element_type = row[4] if isinstance(row, (tuple, list)) else row["element_type"]
        breaker_category = (
            row[5] if isinstance(row, (tuple, list)) else row["breaker_category"]
        )
        substation_id = (
            row[6] if isinstance(row, (tuple, list)) else row["substation_id"]
        )
        maintenance_name = (
            row[7] if isinstance(row, (tuple, list)) else row["maintenance_name"]
        )
        maintenance_type = (
            row[8] if isinstance(row, (tuple, list)) else row["maintenance_type"]
        )
        date_time = row[9] if isinstance(row, (tuple, list)) else row["date_time"]
        substation_name = (
            row[10] if isinstance(row, (tuple, list)) else row["substation_name"]
        )
        all_maintenance_ids.add(maintenance_id)

        if progress_callback:
            progress_callback(
                operation="Generating maintenance reports",
                substation=substation_name,
                current=idx + 1,
                total=total,
            )

        try:
            context = maintenance_context.get(maintenance_id) or {}
            folders_ready = context.get("folders_ready")
            if folders_ready is None:
                folders_ready = True
                try:
                    ensure_maintenance_folders(
                        conn,
                        maintenance_id=maintenance_id,
                        substation_id=context.get("substation_id", substation_id),
                        maintenance_name=context.get(
                            "maintenance_name", maintenance_name
                        ),
                        maintenance_type=context.get(
                            "maintenance_type", maintenance_type
                        ),
                        date_time=context.get("date_time", date_time),
                        element_ids=sorted(context.get("element_ids") or [element_id]),
                        attachment_paths=[],
                        persist_storage_rows=True,
                        db_path=db_path,
                    )
                except Exception:
                    # Do not fail regeneration when canonical folder creation is
                    # not possible (e.g. deep OneDrive paths). We can still emit
                    # valid PDFs to short fallback destinations below.
                    folders_ready = False
                context["folders_ready"] = folders_ready

            reports_root = None
            subfolder = None
            if folders_ready:
                try:
                    bucket = _bucket_for_gate(gate)
                    gate_key = f"{bucket[0]}:{bucket[1]}"
                    reports_root = (context.get("reports_roots") or {}).get(gate_key)
                    if reports_root is None:
                        report_targets = get_transformer_report_targets(
                            conn,
                            maintenance_id=maintenance_id,
                            gate_value=gate,
                            db_path=db_path,
                        )
                        reports_root = report_targets[0] if report_targets else ""
                        context.setdefault("reports_roots", {})[gate_key] = reports_root
                    if reports_root:
                        subfolder = os.path.join(
                            reports_root,
                            _report_subfolder_name_for_element(
                                element_type, breaker_category
                            ),
                        )
                        os.makedirs(_win_path(subfolder), exist_ok=True)
                except Exception:
                    reports_root = None
                    subfolder = None

            if not reports_root or not subfolder:
                failed += 1
                continue

            canonical_name = _canonical_report_filename(
                substation_name,
                element_name,
                maintenance_id,
                parent_dir=subfolder,
            )
            output_path = os.path.join(subfolder, canonical_name)

            if repair_pdf_access(output_path):
                upsert_maintenance_report_path(
                    conn,
                    maintenance_id=maintenance_id,
                    element_id=element_id,
                    report_type="pdf",
                    report_path=output_path,
                )
                touched_maintenance_ids.add(maintenance_id)
                skipped += 1
                continue

            # Try canonical path first. If still too long, use a tighter
            # canonical filename in the same canonical folder.
            generated_path = None
            tight_name = f"M{maintenance_id}_E{element_id}_{hashlib.sha1((substation_name + '|' + element_name).encode('utf-8')).hexdigest()[:8]}.pdf"
            candidates = [
                output_path,
                os.path.join(subfolder, tight_name),
            ]
            last_exc = None
            for cand in candidates:
                candidate_dir = os.path.dirname(cand)
                try:
                    os.makedirs(_win_path(candidate_dir), exist_ok=True)
                    generate_maintenance_report(conn, maintenance_id, element_id, cand)
                    generated_path = cand
                    break
                except Exception as gen_exc:
                    last_exc = gen_exc
                    if candidate_dir:
                        _prune_empty_dir(candidate_dir, stop_at=shared_root)

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
            touched_maintenance_ids.add(maintenance_id)
            generated += 1
        except Exception as exc:
            failed += 1
            if not quiet:
                raise RuntimeError(
                    f"Failed to generate report for maintenance {maintenance_id}, element {element_id} ({element_name}): {exc}"
                ) from exc

    overview_failed = 0
    for maintenance_id in sorted(all_maintenance_ids):
        try:
            ensure_maintenance_overview_reports(
                conn,
                maintenance_id=maintenance_id,
                db_path=db_path,
                overwrite=False,
            )
        except Exception:
            overview_failed += 1

    return {
        "total": total,
        "generated": generated,
        "skipped": skipped,
        "failed": failed,
        "overview_failed": overview_failed,
    }
