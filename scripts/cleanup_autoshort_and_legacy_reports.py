#!/usr/bin/env python3
"""
Cleanup fallback and legacy-named maintenance report files.

Safe behavior:
- Move mappable files to canonical report paths.
- If canonical already exists with same content: delete source duplicate.
- If canonical exists with different content: archive source (do not overwrite).
- If file cannot be mapped to a maintenance/element: archive it.
- Prune empty _AUTO_SHORT/_AUTO_SHORT_REPORTS directories.

Archives are stored under:
  <shared_root>/_AUTO_SHORT_ARCHIVE/<run_stamp>/...
"""

import filecmp
import os
import re
import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from onedrive_hybrid_storage import (  # noqa: E402
    _report_subfolder_name_for_element,
    ensure_maintenance_folders,
    get_transformer_report_targets,
    resolve_shared_root,
    upsert_maintenance_report_path,
)
from settings import DB_PATH  # noqa: E402

RE_OLD_FULL = re.compile(r"^Maintenance_M(\d+)_E(\d+)_.*\.pdf$", re.IGNORECASE)
RE_OLD_SHORT = re.compile(r"^M(\d+)_E(\d+)\.pdf$", re.IGNORECASE)
RE_CANONICAL = re.compile(r"^.*_Maintenance_M(\d+)\.pdf$", re.IGNORECASE)


def safe_name(text: str) -> str:
    return (text or "").replace("/", "-").replace("\\", "-").replace(":", "-")


def fs_path(path: str) -> str:
    abs_path = os.path.abspath(path)
    if os.name != "nt" or abs_path.startswith("\\\\?\\"):
        return abs_path
    if abs_path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + abs_path[2:]
    return "\\\\?\\" + abs_path


def parse_ids_from_filename(filename: str):
    m = RE_OLD_FULL.match(filename)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = RE_OLD_SHORT.match(filename)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = RE_CANONICAL.match(filename)
    if m:
        return int(m.group(1)), None
    return None, None


def canonical_filename(
    substation_name: str, element_name: str, maintenance_id: int
) -> str:
    return f"{safe_name(substation_name)}_{safe_name(element_name)}_Maintenance_M{maintenance_id}.pdf"


def ensure_dir(path: str) -> None:
    os.makedirs(fs_path(path), exist_ok=True)


def archive_move(src: str, archive_root: str, reason: str, shared_root: str) -> str:
    rel = os.path.relpath(src, shared_root)
    dst = os.path.join(archive_root, reason, rel)
    ensure_dir(os.path.dirname(dst))
    base, ext = os.path.splitext(dst)
    candidate = dst
    n = 1
    while os.path.exists(fs_path(candidate)):
        candidate = f"{base}__{n}{ext}"
        n += 1
    shutil.move(fs_path(src), fs_path(candidate))
    return candidate


def fetch_rows(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
        SELECT m.id AS maintenance_id,
               e.id AS element_id,
               e.name AS element_name,
               e.element_type AS element_type,
               e.gate AS gate,
               s.name AS substation_name
        FROM maintenance m
        JOIN maintenance_elements me ON me.maintenance_id = m.id
        JOIN elements e ON e.id = me.element_id
        JOIN substations s ON s.id = m.substation_id
        """)
    rows = cur.fetchall() or []
    by_mid = defaultdict(list)
    by_pair = {}
    for row in rows:
        maintenance_id = int(row[0])
        element_id = int(row[1])
        data = {
            "maintenance_id": maintenance_id,
            "element_id": element_id,
            "element_name": row[2],
            "element_type": row[3],
            "gate": row[4],
            "substation_name": row[5],
        }
        by_mid[maintenance_id].append(data)
        by_pair[(maintenance_id, element_id)] = data
    return by_mid, by_pair


def fetch_maintenance_context(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("""
        SELECT m.id AS maintenance_id,
               m.substation_id,
               m.name AS maintenance_name,
               m.maintenance_type,
               m.date_time
        FROM maintenance m
        """)
    ctx = {}
    for row in cur.fetchall() or []:
        maintenance_id = int(row[0])
        ctx[maintenance_id] = {
            "substation_id": row[1],
            "maintenance_name": row[2],
            "maintenance_type": row[3],
            "date_time": row[4],
        }
    return ctx


def find_element_for_canonical_name(candidates, filename_lower: str):
    for row in candidates:
        expected = canonical_filename(
            row["substation_name"], row["element_name"], row["maintenance_id"]
        ).lower()
        if expected == filename_lower:
            return row
    token_hits = []
    for row in candidates:
        token = safe_name(row["element_name"]).lower()
        if token and token in filename_lower:
            token_hits.append(row)
    if len(token_hits) == 1:
        return token_hits[0]
    if len(candidates) == 1:
        return candidates[0]
    return None


def canonical_target_path(conn, db_path: str, row: dict, maintenance_ctx: dict) -> str:
    targets = get_transformer_report_targets(
        conn,
        maintenance_id=row["maintenance_id"],
        gate_value=row["gate"],
        db_path=db_path,
    )
    if not targets:
        ctx = maintenance_ctx.get(row["maintenance_id"])
        if not ctx:
            raise RuntimeError("No maintenance context")
        ensure_maintenance_folders(
            conn,
            maintenance_id=row["maintenance_id"],
            substation_id=ctx["substation_id"],
            maintenance_name=ctx["maintenance_name"],
            maintenance_type=ctx["maintenance_type"],
            date_time=ctx["date_time"],
            element_ids=[row["element_id"]],
            attachment_paths=[],
            db_path=db_path,
        )
        targets = get_transformer_report_targets(
            conn,
            maintenance_id=row["maintenance_id"],
            gate_value=row["gate"],
            db_path=db_path,
        )
    if not targets:
        raise RuntimeError("No report target")
    reports_root = targets[0]
    subfolder = os.path.join(
        reports_root, _report_subfolder_name_for_element(row["element_type"])
    )
    ensure_dir(subfolder)
    return os.path.join(
        subfolder,
        canonical_filename(
            row["substation_name"], row["element_name"], row["maintenance_id"]
        ),
    )


def gather_candidates(shared_root: str):
    files = []
    legacy_roots = []
    fallback_markers = {"_AUTO_SHORT", "_AUTO_SHORT_REPORTS"}
    for dp, dns, fns in os.walk(shared_root):
        base = os.path.basename(dp)
        parts_lower = {part.lower() for part in dp.split(os.sep) if part}
        under_fallback = any(
            marker.lower() in parts_lower for marker in fallback_markers
        )

        if base in fallback_markers:
            legacy_roots.append(dp)
        for fn in fns:
            if not fn.lower().endswith(".pdf"):
                continue
            full = os.path.join(dp, fn)
            if under_fallback:
                files.append(full)
                continue
            if RE_OLD_FULL.match(fn) or RE_OLD_SHORT.match(fn):
                files.append(full)
    dedup = sorted(set(files))
    return dedup, sorted(set(legacy_roots))


def prune_empty_dirs(paths):
    removed = 0
    for root in paths:
        if not os.path.isdir(root):
            continue
        for dp, dns, fns in os.walk(root, topdown=False):
            try:
                if not os.listdir(dp):
                    os.rmdir(dp)
                    removed += 1
            except OSError:
                pass
    return removed


def main() -> int:
    shared_root = resolve_shared_root(DB_PATH)
    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_root = os.path.join(shared_root, "_AUTO_SHORT_ARCHIVE", run_stamp)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    by_mid, by_pair = fetch_rows(conn)
    maintenance_ctx = fetch_maintenance_context(conn)
    candidates, legacy_roots = gather_candidates(shared_root)

    stats = {
        "candidates": len(candidates),
        "moved_to_canonical": 0,
        "deleted_duplicates": 0,
        "archived_conflicts": 0,
        "archived_unmapped": 0,
        "db_upserts": 0,
        "errors": 0,
        "ensured_storage": 0,
        "pruned_dirs": 0,
    }
    reasons_left = defaultdict(int)
    error_samples = []

    for src in candidates:
        try:
            fn = os.path.basename(src)
            mid, eid = parse_ids_from_filename(fn)

            row = None
            if mid is not None and eid is not None:
                row = by_pair.get((mid, eid))
            elif mid is not None:
                row = find_element_for_canonical_name(by_mid.get(mid, []), fn.lower())

            if row is None:
                archive_move(src, archive_root, "unmapped", shared_root)
                stats["archived_unmapped"] += 1
                reasons_left["unmapped"] += 1
                continue

            target = canonical_target_path(conn, DB_PATH, row, maintenance_ctx)
            src_abs = os.path.abspath(src)
            target_abs = os.path.abspath(target)

            src_fs = fs_path(src_abs)
            target_fs = fs_path(target_abs)

            if os.path.normcase(src_abs) == os.path.normcase(target_abs):
                # already canonical path, just ensure DB link
                upsert_maintenance_report_path(
                    conn,
                    maintenance_id=row["maintenance_id"],
                    element_id=row["element_id"],
                    report_type="pdf",
                    report_path=target_abs,
                )
                stats["db_upserts"] += 1
                continue

            if os.path.exists(target_fs):
                if filecmp.cmp(src_fs, target_fs, shallow=False):
                    os.remove(src_fs)
                    stats["deleted_duplicates"] += 1
                else:
                    archive_move(src_abs, archive_root, "conflict", shared_root)
                    stats["archived_conflicts"] += 1
                    reasons_left["conflict"] += 1
            else:
                ensure_dir(os.path.dirname(target_abs))
                shutil.move(src_fs, target_fs)
                stats["moved_to_canonical"] += 1

            upsert_maintenance_report_path(
                conn,
                maintenance_id=row["maintenance_id"],
                element_id=row["element_id"],
                report_type="pdf",
                report_path=target_abs,
            )
            stats["db_upserts"] += 1

        except Exception as exc:
            stats["errors"] += 1
            if len(error_samples) < 15:
                error_samples.append((src, str(exc)))

    conn.commit()
    conn.close()

    # Re-scan and prune empty fallback trees.
    _, roots_after = gather_candidates(shared_root)
    # include discovered explicit legacy dirs too so empty _AUTO_SHORT_REPORTS root can be removed
    prune_targets = sorted(set(legacy_roots + roots_after))
    stats["pruned_dirs"] = prune_empty_dirs(prune_targets)

    print("CLEANUP_RUN", run_stamp)
    print("SHARED_ROOT", shared_root)
    for k, v in stats.items():
        print(k.upper(), v)

    # Post-state summary
    auto_dirs = []
    old_named = []
    for dp, dns, fns in os.walk(shared_root):
        b = os.path.basename(dp)
        if b in ("_AUTO_SHORT", "_AUTO_SHORT_REPORTS"):
            auto_dirs.append(dp)
        for fn in fns:
            if fn.lower().endswith(".pdf") and (
                RE_OLD_FULL.match(fn) or RE_OLD_SHORT.match(fn)
            ):
                old_named.append(os.path.join(dp, fn))

    print("REMAINING_AUTO_DIRS", len(auto_dirs))
    print("REMAINING_OLD_NAMED", len(old_named))
    for reason, count in sorted(reasons_left.items()):
        print("REASON", reason, count)
    for src, err in error_samples:
        print("ERROR_SAMPLE", src)
        print("ERROR_MSG", err)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
