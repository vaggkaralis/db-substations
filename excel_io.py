import json

import pandas as pd

from popups import ask_save_file, show_message_popup
from strings_proxy import STRINGS as S


def _safe_sheet_name(name: str) -> str:
    # Excel sheet names max length 31 and cannot contain some chars
    if not name:
        return "sheet"
    bad = "[]:*?/\\"
    s = "".join(ch for ch in name if ch not in bad)
    return s[:31]


def export_full_db(conn, default_path=None):
    path = default_path
    if not path:
        path = ask_save_file(
            title="Εξαγωγή Βάσης (Excel)",
            default_name="db_export.xlsx",
            filetypes=[("Excel files", "*.xlsx")],
        )
    if not path:
        return False

    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        tables = [r[0] for r in cur.fetchall()]

        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            for t in tables:
                try:
                    # Special-case elements: include substation name for easier lookup
                    if str(t).lower() == "elements":
                        df = pd.read_sql_query(
                            "SELECT e.*, s.name AS substation_name FROM elements e LEFT JOIN substations s ON e.substation_id = s.id",
                            conn,
                        )
                    else:
                        df = pd.read_sql_query(f"SELECT * FROM {t}", conn)
                except Exception:
                    # fallback to manual select
                    rows = cur.execute(f"SELECT * FROM {t}").fetchall()
                    cols = [c[0] for c in cur.description] if cur.description else []
                    df = pd.DataFrame(rows, columns=cols)
                sheet = _safe_sheet_name(t)
                df.to_excel(writer, sheet_name=sheet, index=False)
        show_message_popup(
            S["TITLES"]["SUCCESS"], f"Εξαγωγή βάσης ολοκληρώθηκε: {path}"
        )
        return True
    except Exception as exc:
        show_message_popup("Σφάλμα", f"Απέτυχε η εξαγωγή βάσης:\n{str(exc)}")
        return False


def export_maintenances_per_substation(conn, default_path=None):
    path = default_path
    if not path:
        path = ask_save_file(
            title="Εξαγωγή Συντηρήσεων (Excel)",
            default_name="maintenances_export.xlsx",
            filetypes=[("Excel files", "*.xlsx")],
        )
    if not path:
        return False

    try:
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM substations ORDER BY name")
        subs = cur.fetchall()
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            for sid, sname in subs:
                # fetch maintenance rows for this substation
                cur.execute(
                    "SELECT id, date_time, name, overall_comments, maintenance_type, user_name, substation_division, substation_location FROM maintenance WHERE substation_id=? ORDER BY date_time",
                    (sid,),
                )
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description] if cur.description else []
                out_rows = []
                for r in rows:
                    m_id = r[0]
                    # fetch elements for this maintenance
                    cur.execute(
                        "SELECT me.element_id, e.name, me.element_comments FROM maintenance_elements me JOIN elements e ON me.element_id = e.id WHERE me.maintenance_id=?",
                        (m_id,),
                    )
                    elems = cur.fetchall()
                    elems_text = "; ".join(
                        f"{ename} (id:{eid}){(' - ' + c) if c else ''}"
                        for eid, ename, c in elems
                    )
                    row_dict = dict(zip(cols, r))
                    row_dict["elements"] = elems_text
                    # fetch maintenance people
                    cur.execute(
                        "SELECT p.name, mp.role FROM maintenance_people mp JOIN people p ON mp.person_id = p.id WHERE mp.maintenance_id=?",
                        (m_id,),
                    )
                    ppl = cur.fetchall()
                    ppl_text = "; ".join(f"{pname} ({role})" for pname, role in ppl)
                    row_dict["people"] = ppl_text
                    out_rows.append(row_dict)
                df = pd.DataFrame(out_rows, columns=(cols + ["elements", "people"]))
                sheet = _safe_sheet_name(sname)
                df.to_excel(writer, sheet_name=sheet, index=False)
        show_message_popup(
            S["TITLES"]["SUCCESS"], f"Εξαγωγή συντηρήσεων ολοκληρώθηκε: {path}"
        )
        return True
    except Exception as exc:
        show_message_popup("Σφάλμα", f"Απέτυχε η εξαγωγή συντηρήσεων:\n{str(exc)}")
        return False


def export_inspections_per_substation(conn, default_path=None):
    path = default_path
    if not path:
        path = ask_save_file(
            title="Εξαγωγή Επιθεωρήσεων (Excel)",
            default_name="inspections_export.xlsx",
            filetypes=[("Excel files", "*.xlsx")],
        )
    if not path:
        return False

    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT substation_id, substation_name FROM inspections ORDER BY substation_name"
        )
        subs = cur.fetchall()
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            for sid, sname in subs:
                cur.execute(
                    "SELECT id, inspection_date, month_key, data_json, source_file, created_at FROM inspections WHERE substation_id=? ORDER BY inspection_date",
                    (sid,),
                )
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description] if cur.description else []
                out_rows = []
                for r in rows:
                    row_dict = dict(zip(cols, r))
                    # pretty-print JSON data if possible
                    try:
                        row_dict["data_json"] = json.dumps(
                            json.loads(row_dict.get("data_json") or "{}"),
                            ensure_ascii=False,
                        )
                    except Exception:
                        pass
                    out_rows.append(row_dict)
                df = pd.DataFrame(out_rows, columns=cols)
                sheet = _safe_sheet_name(sname)
                df.to_excel(writer, sheet_name=sheet, index=False)
        show_message_popup(
            S["TITLES"]["SUCCESS"], f"Εξαγωγή επιθεωρήσεων ολοκληρώθηκε: {path}"
        )
        return True
    except Exception as exc:
        show_message_popup("Σφάλμα", f"Απέτυχε η εξαγωγή επιθεωρήσεων:\n{str(exc)}")
        return False


# People import/export
PEOPLE_COLUMNS = [
    "given_name",
    "surname",
    "name",
    "role",
    "email",
    "report_receiver",
    "active",
]


def export_people(conn, default_path=None):
    path = default_path
    if not path:
        path = ask_save_file(
            title="Εξαγωγή Προσωπικού (Excel)",
            default_name="people_export.xlsx",
            filetypes=[("Excel files", "*.xlsx")],
        )
    if not path:
        return False
    try:
        df = pd.read_sql_query(
            "SELECT given_name, surname, name, role, email, report_receiver, active FROM people ORDER BY active DESC, COALESCE(surname, name)",
            conn,
        )
        df.to_excel(path, index=False)
        show_message_popup(
            S["TITLES"]["SUCCESS"], f"Εξαγωγή προσωπικού ολοκληρώθηκε: {path}"
        )
        return True
    except Exception as exc:
        show_message_popup("Σφάλμα", f"Απέτυχε η εξαγωγή προσωπικού:\n{str(exc)}")
        return False


def export_people_template(default_path=None):
    path = default_path
    if not path:
        path = ask_save_file(
            title="Δημιουργία Προτύπου Προσωπικού (Excel)",
            default_name="people_template.xlsx",
            filetypes=[("Excel files", "*.xlsx")],
        )
    if not path:
        return False
    try:
        df = pd.DataFrame(columns=PEOPLE_COLUMNS)
        df.to_excel(path, index=False)
        show_message_popup(
            S["TITLES"]["SUCCESS"], f"Πρότυπο προσωπικού δημιουργήθηκε: {path}"
        )
        return True
    except Exception as exc:
        show_message_popup("Σφάλμα", f"Απέτυχε η δημιουργία προτύπου:\n{str(exc)}")
        return False


def import_people(conn, file_path=None):
    try:
        if not file_path:
            # use open dialog
            from popups import ask_open_file

            file_path = ask_open_file(
                title="Εισαγωγή Προσωπικού (Excel)",
                filetypes=[("Excel files", "*.xlsx;*.xls")],
            )
        if not file_path:
            return False
        df = pd.read_excel(file_path, dtype=str)
        # normalize columns (coerce non-string headers safely)
        cols = [str(c).strip() for c in df.columns]
        df.columns = cols
        cur = conn.cursor()
        inserted = 0
        for _, row in df.iterrows():
            # Safely coerce possible NaN/float values to strings before stripping
            def _strval(v):
                try:
                    if pd.isna(v):
                        return ""
                    return str(v).strip()
                except Exception:
                    return ""

            given = _strval(row.get("given_name"))
            surname = _strval(row.get("surname"))
            name = _strval(row.get("name")) or f"{surname} {given}".strip()
            role = _strval(row.get("role"))
            email = _strval(row.get("email"))
            rr_raw = row.get("report_receiver")
            report_receiver = (
                1
                if (
                    not pd.isna(rr_raw)
                    and str(rr_raw).strip().lower() in {"1", "true", "yes", "ναι", "y"}
                )
                else 0
            )
            active_raw = row.get("active")
            active = (
                1
                if (
                    not pd.isna(active_raw)
                    and str(active_raw).strip().lower()
                    in {"1", "true", "yes", "ναι", "y"}
                )
                else 0
            )
            if not surname and not name:
                continue
            cur.execute(
                "INSERT INTO people (name, given_name, surname, role, email, report_receiver, active) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, given, surname, role, email, report_receiver, active),
            )
            inserted += 1
        conn.commit()
        show_message_popup(
            S["TITLES"]["SUCCESS"],
            f"Εισαγωγή προσωπικού ολοκληρώθηκε: {inserted} εγγραφές.",
        )
        return True
    except Exception as exc:
        show_message_popup("Σφάλμα", f"Απέτυχε η εισαγωγή προσωπικού:\n{str(exc)}")
        return False
