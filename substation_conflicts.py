"""Substation element conflict detection and persistent exceptions."""

import hashlib
import json
import os
import re


def ensure_substation_conflict_exception_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS substation_conflict_exceptions (
            id INTEGER PRIMARY KEY,
            substation_id INTEGER NOT NULL,
            issue_key TEXT NOT NULL,
            issue_type TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(substation_id, issue_key)
        )
        """
    )
    conn.commit()


def ensure_substation_no_transformer_exception_table(conn):
    """Create table for substations with no transformers (MV-only)."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS substation_no_transformer_exceptions (
            id INTEGER PRIMARY KEY,
            substation_id INTEGER NOT NULL UNIQUE,
            reason TEXT DEFAULT 'Manual exception - MV-only substation',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(substation_id) REFERENCES substations(id)
        )
        """
    )
    conn.commit()


def mark_substation_as_no_transformer(conn, substation_id, reason=None):
    """Mark a substation as having no transformers (MV-only exception)."""
    ensure_substation_no_transformer_exception_table(conn)
    conn.execute(
        """
        INSERT INTO substation_no_transformer_exceptions
            (substation_id, reason)
        VALUES (?, ?)
        ON CONFLICT(substation_id)
        DO UPDATE SET
            reason=excluded.reason,
            updated_at=datetime('now')
        """,
        (int(substation_id), reason or "MV-only substation"),
    )
    conn.commit()


def unmark_substation_no_transformer(conn, substation_id):
    """Remove no-transformer exception from a substation."""
    ensure_substation_no_transformer_exception_table(conn)
    conn.execute(
        "DELETE FROM substation_no_transformer_exceptions WHERE substation_id=?",
        (int(substation_id),),
    )
    conn.commit()


def is_substation_no_transformer_exception(conn, substation_id):
    """Check if a substation is marked as no-transformer (MV-only)."""
    ensure_substation_no_transformer_exception_table(conn)
    row = conn.execute(
        "SELECT 1 FROM substation_no_transformer_exceptions WHERE substation_id=?",
        (int(substation_id),),
    ).fetchone()
    return row is not None


def get_substation_exception_details(conn, substation_id):
    """Get detailed information about a substation's no-transformer exception."""
    ensure_substation_no_transformer_exception_table(conn)
    row = conn.execute(
        "SELECT reason, created_at FROM substation_no_transformer_exceptions WHERE substation_id=?",
        (int(substation_id),),
    ).fetchone()
    if row:
        return {
            "reason": row[0],
            "created_at": row[1],
        }
    return None


def auto_detect_no_transformer_substation(conn, substation_id):
    """Auto-detect if substation has no transformers based on elements."""
    c = conn.cursor()
    c.execute(
        """
        SELECT COUNT(*) FROM elements
        WHERE substation_id=?
            AND (element_type LIKE '%150/20%' OR element_type LIKE '%Μετασχη%')
            AND operating_status NOT IN ('Ανενεργή', 'Αποχαιρέτηση')
        """,
        (int(substation_id),),
    )
    transformer_count = c.fetchone()[0]
    return transformer_count == 0


def _issue_key(issue_type, substation_id, scope):
    payload = json.dumps(
        {
            "substation_id": int(substation_id),
            "issue_type": str(issue_type),
            "scope": scope,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def set_substation_conflict_exception(
    conn, substation_id, issue_type, issue_key, message
):
    ensure_substation_conflict_exception_table(conn)
    conn.execute(
        """
        INSERT INTO substation_conflict_exceptions
            (substation_id, issue_key, issue_type, message)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(substation_id, issue_key)
        DO UPDATE SET
            issue_type=excluded.issue_type,
            message=excluded.message
        """,
        (int(substation_id), str(issue_key), str(issue_type), str(message)),
    )
    conn.commit()


def get_substation_conflict_exceptions(conn, substation_id):
    ensure_substation_conflict_exception_table(conn)
    rows = conn.execute(
        """
        SELECT issue_key
        FROM substation_conflict_exceptions
        WHERE substation_id=?
        """,
        (int(substation_id),),
    ).fetchall()
    return {str(row[0]) for row in rows}


def detect_substation_conflicts(conn, substation_id):
    """Return unresolved configuration issues for one substation."""
    ensure_substation_conflict_exception_table(conn)
    rows = conn.execute(
        """
        SELECT id, name, serial_number, element_type, gate, hemizygos,
               is_main_switch, operating_status, COALESCE(split_mv_gates, 0)
        FROM elements
        WHERE substation_id=?
        """,
        (int(substation_id),),
    ).fetchall()

    hv_type = "Διακόπτης ΥΤ"
    mv_type = "Διακόπτης ΜΤ"
    issues = []

    def add_issue(issue_type, title, scope, message, severity="problem"):
        normalized_severity = (
            "warning"
            if str(severity or "").strip().casefold() == "warning"
            else "problem"
        )
        key = _issue_key(issue_type, substation_id, scope)
        issues.append(
            {
                "key": key,
                "type": issue_type,
                "severity": normalized_severity,
                "title": title,
                "message": message,
            }
        )

    names = {}
    serials = {}
    for row in rows:
        (
            elem_id,
            name,
            serial_number,
            elem_type,
            gate,
            hemizygos,
            _main,
            _status,
            _split_mv_gates,
        ) = row
        name_value = str(name or "").strip()
        serial_value = str(serial_number or "").strip()
        if name_value:
            names.setdefault(name_value.casefold(), []).append(
                (int(elem_id), name_value)
            )
        if serial_value:
            serials.setdefault(serial_value.casefold(), []).append(
                (int(elem_id), serial_value)
            )

    for normalized, entries in sorted(names.items()):
        if len(entries) > 1:
            ids = ", ".join(str(entry[0]) for entry in entries)
            add_issue(
                "duplicate_name",
                "Διπλότυπο όνομα στοιχείου",
                normalized,
                f"Το όνομα «{entries[0][1]}» χρησιμοποιείται από τα στοιχεία με ID: {ids}.",
            )

    for normalized, entries in sorted(serials.items()):
        if len(entries) > 1:
            ids = ", ".join(str(entry[0]) for entry in entries)
            add_issue(
                "duplicate_serial",
                "Διπλότυπος σειριακός αριθμός",
                normalized,
                f"Ο σειριακός αριθμός «{entries[0][1]}» χρησιμοποιείται από τα στοιχεία με ID: {ids}.",
            )

    for elem_id, name, _serial, _etype, gate, _hemi, _main, _status, _split in rows:
        if not str(gate or "").strip():
            add_issue(
                "missing_gate",
                "Στοιχείο χωρίς πύλη",
                int(elem_id),
                f"Το στοιχείο «{str(name or '').strip() or '#' + str(elem_id)}» (ID {elem_id}) δεν έχει πύλη.",
            )

    hemizygos_available = any(str(row[5] or "").strip() for row in rows)
    if hemizygos_available:
        for (
            elem_id,
            name,
            _serial,
            elem_type,
            gate,
            hemizygos,
            _main,
            _status,
            _split,
        ) in rows:
            if (
                str(elem_type or "").strip() == mv_type
                and not str(hemizygos or "").strip()
            ):
                add_issue(
                    "missing_hemizygos",
                    "Διακόπτης ΜΤ χωρίς Ημιζυγό",
                    int(elem_id),
                    f"Ο διακόπτης ΜΤ «{str(name or '').strip() or '#' + str(elem_id)}» (ID {elem_id}) δεν έχει Ημιζυγό.",
                )

    gates = {}
    gate_prefix = "ΠΥΛΗ"
    split_parent_pattern = re.compile(
        rf"^{re.escape(gate_prefix)}\s*(\d+)$",
        flags=re.IGNORECASE,
    )
    split_child_pattern = re.compile(
        rf"^{re.escape(gate_prefix)}\s*(\d+)\.(\d+)$",
        flags=re.IGNORECASE,
    )

    split_mv_parent_gates = set()
    for row in rows:
        (
            _elem_id,
            _name,
            _serial,
            elem_type,
            gate,
            _hemizygos,
            _is_main,
            status,
            split_mv_gates,
        ) = row
        gate_text = str(gate or "").strip()
        if not gate_text:
            continue
        if str(status or "").strip() not in {"", "Ενεργή"}:
            continue
        if int(split_mv_gates or 0) != 1:
            continue
        match = split_parent_pattern.match(gate_text)
        if not match:
            continue
        split_mv_parent_gates.add(f"{gate_prefix} {int(match.group(1))}".casefold())

    for row in rows:
        elem_id, name, _serial, elem_type, gate, hemizygos, is_main, status, _split = (
            row
        )
        gate_name = str(gate or "").strip()
        if not gate_name:
            continue
        gates.setdefault(gate_name, []).append(
            {
                "id": int(elem_id),
                "name": str(name or "").strip(),
                "type": str(elem_type or "").strip(),
                "hemizygos": str(hemizygos or "").strip(),
                "is_main": is_main,
                "status": str(status or "").strip(),
            }
        )

    for gate_name in sorted(gates, key=str.casefold):
        gate_rows = gates[gate_name]
        normalized_gate = str(gate_name).strip().casefold()
        is_split_parent_gate = normalized_gate in split_mv_parent_gates
        split_child_match = split_child_pattern.match(str(gate_name).strip())
        split_child_parent_gate = None
        if split_child_match:
            split_child_parent_gate = (
                f"{gate_prefix} {int(split_child_match.group(1))}".casefold()
            )
        is_split_child_gate = (
            split_child_parent_gate is not None
            and split_child_parent_gate in split_mv_parent_gates
        )
        gate_suffix = normalized_gate
        for gate_prefix_token in ("πύλη ", "pyli ", "gate "):
            if gate_suffix.startswith(gate_prefix_token):
                gate_suffix = gate_suffix[len(gate_prefix_token) :]
                break
        interconnection_gate = "-" in gate_suffix
        active_gate_rows = [
            row for row in gate_rows if not row["status"] or row["status"] == "Ενεργή"
        ]
        transformers = [
            row
            for row in active_gate_rows
            if "μετασχηματιστ" in str(row["type"]).casefold()
        ]
        hv_breakers = [row for row in active_gate_rows if row["type"] == hv_type]

        # Check if this substation is marked as no-transformer exception
        is_no_transformer_exception = is_substation_no_transformer_exception(
            conn, substation_id
        )

        if (
            not interconnection_gate
            and not is_split_child_gate
            and len(transformers) != 1
        ):
            # Skip transformer check if this is a no-transformer exception
            if not is_no_transformer_exception:
                add_issue(
                    "gate_transformer_count",
                    "Μη έγκυρος αριθμός μετασχηματιστών στην πύλη",
                    gate_name.casefold(),
                    f"Η {gate_name} έχει {len(transformers)} μετασχηματιστές· απαιτείται ακριβώς 1.",
                )

        if (
            not interconnection_gate
            and not is_split_child_gate
            and len(hv_breakers) != 1
        ):
            # Skip HV breaker check if this is a no-transformer exception
            if not is_no_transformer_exception:
                add_issue(
                    "gate_hv_breaker_count",
                    "Μη έγκυρος αριθμός διακοπτών ΥΤ στην πύλη",
                    gate_name.casefold(),
                    f"Η {gate_name} έχει {len(hv_breakers)} διακόπτες ΥΤ· απαιτείται ακριβώς 1.",
                )

        mv_mains = [
            row
            for row in active_gate_rows
            if row["type"] == mv_type and str(row["is_main"]).strip() == "1"
        ]
        if interconnection_gate:
            pass
        elif is_split_parent_gate:
            pass
        elif hemizygos_available:
            hemi_names = sorted(
                {
                    str(row["hemizygos"]).strip()
                    for row in active_gate_rows
                    if str(row["hemizygos"]).strip()
                },
                key=str.casefold,
            )
            for hemi_name in hemi_names:
                count = sum(
                    1 for row in mv_mains if str(row["hemizygos"]).strip() == hemi_name
                )
                if count != 1:
                    add_issue(
                        "gate_main_mv_breaker_per_hemizygos",
                        "Μη έγκυρος αριθμός κεντρικών ΜΤ ανά Ημιζυγό",
                        f"{gate_name.casefold()}|{hemi_name.casefold()}",
                        f"Η {gate_name}, {hemi_name}, έχει {count} κεντρικούς διακόπτες ΜΤ· απαιτείται ακριβώς 1.",
                    )
        else:
            if len(mv_mains) != 1:
                add_issue(
                    "gate_main_mv_breaker",
                    "Μη έγκυρος αριθμός κεντρικών ΜΤ στην πύλη",
                    gate_name.casefold(),
                    f"Η {gate_name} έχει {len(mv_mains)} κεντρικούς διακόπτες ΜΤ· απαιτείται ακριβώς 1.",
                )

    maint_rows = conn.execute(
        """
        SELECT m.id, m.name, m.date_time, e.id, e.name, e.substation_id
        FROM maintenance m
        JOIN maintenance_elements me ON me.maintenance_id=m.id
        JOIN elements e ON e.id=me.element_id
        WHERE m.substation_id=?
          AND e.substation_id IS NOT NULL
          AND e.substation_id!=?
        ORDER BY m.id, e.id
        """,
        (int(substation_id), int(substation_id)),
    ).fetchall()
    cross_by_maintenance = {}
    for maint_id, maint_name, maint_date, elem_id, elem_name, elem_sub_id in maint_rows:
        cross_by_maintenance.setdefault(
            int(maint_id),
            {
                "name": maint_name,
                "date": maint_date,
                "elements": [],
            },
        )["elements"].append((int(elem_id), str(elem_name or ""), int(elem_sub_id)))

    for maint_id, data in sorted(cross_by_maintenance.items()):
        elems = ", ".join(
            f"{name or '#' + str(elem_id)} (ID {elem_id}, Υ/Σ ID {elem_sub_id})"
            for elem_id, name, elem_sub_id in data["elements"]
        )
        add_issue(
            "cross_substation_maintenance",
            "Σύνδεση στοιχείων άλλου Υποσταθμού στη συντήρηση",
            int(maint_id),
            f"Η συντήρηση #{maint_id} «{data['name'] or '-'}» ({data['date'] or '-'}) περιλαμβάνει στοιχεία άλλων Υποσταθμών: {elems}.",
        )

    def _is_web_url(value):
        text = str(value or "").strip().casefold()
        return text.startswith("http://") or text.startswith("https://")

    manual_rows = conn.execute(
        """
        SELECT e.id, e.name, e.element_model_id, e.operating_status,
               em.model_name, em.manual_pdf, em.onedrive_manual_link
        FROM elements e
        LEFT JOIN element_models em ON em.id = e.element_model_id
        WHERE e.substation_id=?
          AND COALESCE(e.parent_element_id, 0)=0
          AND (COALESCE(TRIM(e.operating_status), '') = '' OR TRIM(e.operating_status) = 'Ενεργή')
        """,
        (int(substation_id),),
    ).fetchall()
    for (
        elem_id,
        elem_name,
        model_id,
        _status,
        model_name,
        manual_pdf,
        onedrive_manual_link,
    ) in manual_rows:
        manual_pdf_text = str(manual_pdf or "").strip()
        onedrive_link_text = str(onedrive_manual_link or "").strip()
        has_local_manual = bool(manual_pdf_text) and (
            _is_web_url(manual_pdf_text) or os.path.exists(manual_pdf_text)
        )
        has_onedrive_manual = _is_web_url(onedrive_link_text)
        if has_local_manual or has_onedrive_manual:
            continue

        element_display_name = str(elem_name or "").strip() or f"#{elem_id}"
        if model_id is None:
            message = (
                f"Το στοιχείο «{element_display_name}» (ID {elem_id}) δεν έχει "
                "συσχετισμένο μοντέλο, άρα δεν υπάρχει καταχωρημένο εγχειρίδιο."
            )
        else:
            model_display_name = str(model_name or "").strip() or "-"
            message = (
                f"Το στοιχείο «{element_display_name}» (ID {elem_id}) με μοντέλο "
                f"«{model_display_name}» (Model ID {model_id}) δεν έχει καταχωρημένο "
                "εγχειρίδιο (manual_pdf / onedrive_manual_link)."
            )
        add_issue(
            "missing_manual",
            "Απουσία εγχειριδίου μοντέλου",
            int(elem_id),
            message,
            severity="warning",
        )

    exceptions = get_substation_conflict_exceptions(conn, substation_id)
    unresolved = [issue for issue in issues if issue["key"] not in exceptions]

    # Auto-detect no-transformer substations and suggest exception if appropriate
    if auto_detect_no_transformer_substation(conn, substation_id):
        if not is_substation_no_transformer_exception(conn, substation_id):
            # Check if there are transformer-related issues that would be resolved by marking exception
            has_transformer_issues = any(
                issue["type"] in ("gate_transformer_count", "gate_hv_breaker_count")
                for issue in unresolved
            )
            if has_transformer_issues:
                # Add a suggestion issue to mark this substation as no-transformer
                suggestion_key = _issue_key(
                    "no_transformer_suggestion", substation_id, "substation"
                )
                unresolved.append(
                    {
                        "key": suggestion_key,
                        "type": "no_transformer_suggestion",
                        "severity": "warning",
                        "title": "Πρόταση: Χωρίς Μετασχηματιστή",
                        "message": "Αυτός ο Υποσταθμός δεν έχει ενεργούς μετασχηματιστές. Μπορείτε να κάνετε κλικ 'Επικύρωση' για να αφαιρέσετε τις προειδοποιήσεις σχετικά με τους μετασχηματιστές.",
                        "is_suggestion": True,
                        "action": "mark_no_transformer_exception",
                    }
                )

    return unresolved
