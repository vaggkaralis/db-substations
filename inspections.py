import os
import re
import json
from datetime import datetime
from strings import STRINGS as S

def _get_inspection_fallback_fields():
    base = [
        "Υποσταθμός",
        "Αρ. Δελτίου",
        "Μήνας",
        "Ονομ. Επιθεωρητή",
        "Περιοχή",
        "Ημέρα",
        "Έτος",
        "Ημερομηνία",
    ]

    inspection_rows = S["MESSAGES"].get("INSPECTION_ROWS", [])

    # Return a combined list: basic metadata fields followed by the inspection rows.
    return base + inspection_rows


def _format_inspection_value(value):
    if value is None:
        return ""
    try:
        import math

        if isinstance(value, float) and math.isnan(value):
            return ""
    except Exception:
        pass

    if hasattr(value, "to_pydatetime"):
        try:
            value = value.to_pydatetime()
        except Exception:
            pass

    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")

    if isinstance(value, float) and value.is_integer():
        value = int(value)

    return str(value).strip()


def _parse_inspection_date(value):
    if value is None:
        return ""
    if hasattr(value, "to_pydatetime"):
        try:
            value = value.to_pydatetime()
        except Exception:
            pass
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")

    text = str(value).strip()
    if not text:
        return ""

    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass

    return text


def _derive_month_key(date_str):
    if not date_str:
        return datetime.now().strftime("%Y-%m")

    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m")
        except Exception:
            pass

    if len(date_str) >= 7 and date_str[4] == "-":
        return date_str[:7]

    return datetime.now().strftime("%Y-%m")


def _detect_inspection_column(columns, keywords):
    for col in columns:
        col_text = str(col).strip().lower()
        for key in keywords:
            if key in col_text:
                return col
    return None


def import_inspections_from_file(app, file_path):
    import pandas as pd

    try:
        if file_path.endswith(".xlsx"):
            df = pd.read_excel(file_path)
        elif file_path.endswith(".csv"):
            df = pd.read_csv(file_path)
        else:
            from popups import show_message_popup

            show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["UNSUPPORTED_FILE_FORMAT"])
            return
    except Exception as e:
        from popups import show_message_popup

        show_message_popup(S["TITLES"]["ERROR"], f"{S['MESSAGES']['IMPORT_FAILED']}\n{str(e)}")
        return

    if df.empty:
        from popups import show_message_popup

        show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["FILE_HAS_NO_DATA"])
        return

    columns = list(df.columns)
    date_col = _detect_inspection_column(columns, ["ημερομην", "ημ/ν", "date"])
    substation_col = _detect_inspection_column(columns, ["υποσταθ", "substation"])

    inserted = 0
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    c = app.conn.cursor()

    for _, row in df.iterrows():
        if hasattr(row, "isna") and row.isna().all():
            continue

        date_value = row.get(date_col) if date_col else None
        inspection_date = _parse_inspection_date(date_value) or datetime.now().strftime("%Y-%m-%d")
        month_key = _derive_month_key(inspection_date)

        substation_name = ""
        if substation_col:
            substation_name = _format_inspection_value(row.get(substation_col))

        substation_id = None
        if substation_name:
            c.execute("SELECT id FROM substations WHERE name=?", (substation_name,))
            sub_row = c.fetchone()
            substation_id = sub_row[0] if sub_row else None

        fields = []
        for col in columns:
            value = row.get(col)
            try:
                import pandas as pd

                if pd.isna(value):
                    value = ""
            except Exception:
                pass
            fields.append({"label": str(col), "value": _format_inspection_value(value)})

        data_json = json.dumps({"fields": fields}, ensure_ascii=False)

        c.execute(
            """
            INSERT INTO inspections (
                substation_id, substation_name, inspection_date,
                month_key, data_json, source_file, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                substation_id,
                substation_name,
                inspection_date,
                month_key,
                data_json,
                os.path.basename(file_path),
                created_at,
            ),
        )
        inserted += 1

    app.conn.commit()
    from popups import show_message_popup

    show_message_popup(
        "Εισαγωγή Επιθεωρήσεων",
        f"Ολοκληρώθηκε η εισαγωγή ({inserted} εγγραφές).",
        callback=lambda: app.show_inspection_history(None),
    )


def show_inspection_menu_popup_delegate(app, instance=None):
    """Delegate to the app's `show_inspection_menu_popup` method.

    This avoids referencing module-level functions that remain in `DBrun.py`.
    """
    return getattr(app, "show_inspection_menu_popup")(instance)


def handle_inspection_menu(app, instance=None):
    """Default implementation for the inspection menu.

    This is a non-delegating handler that DBrun can call directly to
    avoid an infinite recursion when the delegate points back to the
    app method. By default it opens the inspection history view.
    """
    if hasattr(app, "show_inspection_history"):
        return getattr(app, "show_inspection_history")(instance)
    # Fallback: no-op
    return None


def show_import_inspections_dialog_delegate(app, instance):
    """Delegate to the app's import dialog creator for inspections."""
    # Some apps expose a helper `_create_file_import_dialog`; fall back to
    # calling the app method `show_import_inspections_dialog` if present.
    if hasattr(app, "_create_file_import_dialog"):
        return app._create_file_import_dialog("Εισαγωγή επιθεωρήσεων από αρχείο", lambda fp: import_inspections_from_file(app, fp))
    return getattr(app, "show_import_inspections_dialog")(instance)


def show_inspection_history_delegate(app, instance=None):
    return getattr(app, "show_inspection_history")(instance)


def handle_inspection_history(app, instance=None):
    """Default non-recursive inspection history handler.

    Shows a simple summary using the app's DB connection or calls a
    private app implementation if available. This prevents delegates
    from calling back into `app.show_inspection_history` and creating
    a recursion loop.
    """
    # If the app provides a private implementation, prefer that.
    if hasattr(app, "_show_inspection_history"):
        return getattr(app, "_show_inspection_history")(instance)

    # Otherwise, attempt a minimal summary popup (safe fallback).
    try:
        c = app.conn.cursor()
        c.execute("SELECT COUNT(*) FROM inspections")
        row = c.fetchone()
        count = row[0] if row else 0
        from popups import show_message_popup

        # If there are no inspections yet, offer to create one directly
        # instead of only showing a count message. This makes the UI
        # discoverable for users who expect to add the first inspection.
        if count == 0:
            show_message_popup(
                "Ιστορικό Επιθεώρησης",
                "Δεν υπάρχουν καταχωρημένες επιθεώρήσεις. Θέλετε να δημιουργήσετε μία;",
                callback=lambda: getattr(app, "show_inspection_entry_popup")(None),
            )
        else:
            show_message_popup("Ιστορικό Επιθεώρησης", f"{count} εγγραφές επιθεώρησης")
    except Exception:
        # Give up silently to avoid crashing the app in this fallback.
        return None

    return None


def handle_substation_inspection_history(app, substation_id, substation_name, parent_display_popup=None):
    """Non-recursive handler for showing a substation's inspection history.

    Safe fallback: shows a simple count or delegates to a private app
    implementation `_show_substation_inspection_history` if present.
    """
    if hasattr(app, "_show_substation_inspection_history"):
        return getattr(app, "_show_substation_inspection_history")(substation_id, substation_name, parent_display_popup)

    try:
        c = app.conn.cursor()
        c.execute("SELECT COUNT(*) FROM inspections WHERE substation_id=?", (substation_id,))
        row = c.fetchone()
        count = row[0] if row else 0
        from popups import show_message_popup

        show_message_popup(
            f"Ιστορικό Επιθεωρήσεων - {substation_name}",
            f"{count} εγγραφές επιθεώρησης για τον υποσταθμό {substation_name}",
        )
    except Exception:
        return None

    return None


def handle_inspection_details(app, inspection_id):
    """Non-recursive handler to show inspection details.

    Falls back to a message popup summarizing the inspection if a
    private implementation is not available.
    """
    if hasattr(app, "_show_inspection_details"):
        return getattr(app, "_show_inspection_details")(inspection_id)

    try:
        c = app.conn.cursor()
        c.execute("SELECT substation_name, inspection_date, data_json FROM inspections WHERE id=?", (inspection_id,))
        row = c.fetchone()
        if not row:
            from popups import show_message_popup

            show_message_popup(S["TITLES"]["INFO"], S["MESSAGES"]["RECORD_NOT_FOUND"])
            return None

        sub_name, insp_date, data_json = row
        try:
            data = json.loads(data_json)
            fields = data.get("fields", [])
            preview = []
            for f in fields[:10]:
                preview.append(f"{f.get('label')}: {f.get('value')}")
            body = "\n".join(preview)
        except Exception:
            body = f"Υποσταθμός: {sub_name}\nΗμερομηνία: {insp_date}"

        from popups import show_message_popup

        show_message_popup("Λεπτομέρειες Επιθεώρησης", body)
    except Exception:
        return None

    return None


def show_substation_inspection_history_delegate(app, substation_id, substation_name, parent_display_popup=None):
    return getattr(app, "show_substation_inspection_history")(substation_id, substation_name, parent_display_popup)


def show_inspection_details_delegate(app, inspection_id):
    return getattr(app, "show_inspection_details")(inspection_id)
