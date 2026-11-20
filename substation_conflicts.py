"""Substation element conflict detection and persistent exceptions."""

import hashlib
import json


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
               is_main_switch, operating_status
        FROM elements
        WHERE substation_id=?
        """,
        (int(substation_id),),
    ).fetchall()

    hv_type = "Διακόπτης ΥΤ"
    mv_type = "Διακόπτης ΜΤ"
    issues = []

    def add_issue(issue_type, title, scope, message):
        key = _issue_key(issue_type, substation_id, scope)
        issues.append(
            {
                "key": key,
                "type": issue_type,
                "title": title,
                "message": message,
            }
        )

    names = {}
    serials = {}
    for row in rows:
        elem_id, name, serial_number, elem_type, gate, hemizygos, _main, _status = row
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

    for elem_id, name, _serial, _etype, gate, _hemi, _main, _status in rows:
        if not str(gate or "").strip():
            add_issue(
                "missing_gate",
                "Στοιχείο χωρίς πύλη",
                int(elem_id),
                f"Το στοιχείο «{str(name or '').strip() or '#' + str(elem_id)}» (ID {elem_id}) δεν έχει πύλη.",
            )

    hemizygos_available = any(str(row[5] or "").strip() for row in rows)
    if hemizygos_available:
        for elem_id, name, _serial, elem_type, gate, hemizygos, _main, _status in rows:
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
    for row in rows:
        elem_id, name, _serial, elem_type, gate, hemizygos, is_main, status = row
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
        gate_suffix = normalized_gate
        for gate_prefix in ("πύλη ", "pyli ", "gate "):
            if gate_suffix.startswith(gate_prefix):
                gate_suffix = gate_suffix[len(gate_prefix) :]
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
        if not interconnection_gate and len(transformers) != 1:
            add_issue(
                "gate_transformer_count",
                "Μη έγκυρος αριθμός μετασχηματιστών στην πύλη",
                gate_name.casefold(),
                f"Η {gate_name} έχει {len(transformers)} μετασχηματιστές· απαιτείται ακριβώς 1.",
            )
        if not interconnection_gate and len(hv_breakers) != 1:
            add_issue(
                "gate_hv_breaker_count",
                "Μη έγκυρος αριθμός διακοπτών ΥΤ στην πύλη",
                gate_name.casefold(),
                f"Η {gate_name} έχει {len(hv_breakers)} διακόπτες ΥΤ· απαιτείται ακριβώς 1.",
            )

        mv_mains = [
            row
            for row in gate_rows
            if row["type"] == mv_type and str(row["is_main"]).strip() == "1"
        ]
        if interconnection_gate:
            pass
        elif hemizygos_available:
            hemi_names = sorted(
                {
                    str(row["hemizygos"]).strip()
                    for row in gate_rows
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

    exceptions = get_substation_conflict_exceptions(conn, substation_id)
    unresolved = [issue for issue in issues if issue["key"] not in exceptions]
    return unresolved
