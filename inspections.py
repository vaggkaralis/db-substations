import os
import re
import json
from datetime import datetime

def _get_inspection_fallback_fields():
    return [
        "Υποσταθμός",
        "Αρ. Δελτίου",
        "Μήνας",
        "Ονομ. Επιθεωρητή",
        "Περιοχή",
        "Ημέρα",
        "Έτος",
        "Ημερομηνία",
        {"type": "section", "title": "1. Έλεγχος Χώρων ΥΣ"},
        "Παρατηρήσεις (1. Έλεγχος Χώρων ΥΣ)",
        "Έλεγχος εξωτερικών & εσωτερικών Θυρών ΥΣ",
        "Έλεγχος εσωτερικού Χώρου κτηρίου (Φωτισμός, κλιματισμός κλπ)",
        "Έλεγχος περιβάλλοντος χώρου (βλάστηση, δένδρα, φωτισμός κλπ)",
        "Έλεγχος μέσων πυρόσβεσης γενικά",
        {"type": "section", "title": "2. Μ/Σ 150/20kV & Διακόπτες 150kV & 20kV"},
        "Παρατηρήσεις (2. Μ/Σ 150/20kV & Διακόπτες 150kV & 20kV)",
        "Οπτικός έλεγχος, διαρροής/στάθμης/θερμοκρασίας λαδιού, silica gel στον Μ/Σ",
        "Οπτικός έλεγχος διαρροής λαδιού ή πίεσης SF6 ή πίεσης αέρα στους Διακόπτες Ισχύος 150kV & 20kV",
        "Έλεγχος λειτουργίας ανεμιστήρων Μ/Σ",
        "Οπτικός έλεγχος Μ/Σ εγχύσεως, ΜΣΕ, ΜΣΤ, Μ/Σ εσωτ. Υπηρ., αντίστασης κόμβου (θερμοκρασία)",
        "Οπτικός έλεγχος Μονωτήρων (ρύπανση, εκδορές κ.α.)",
        "Οπτικός έλεγχος τηκτών πυκνωτών",
        "Έλεγχος σημάνσεων στους Πίνακες Μ/Σ , Α/Δ 150kV & 20kV",
        "Λήψη φωτογραφίας όταν απαιτείται",
        {"type": "section", "title": "3α. Υπαίθριες πύλες 20 kV"},
        "Παρατηρήσεις (3α. Υπαίθριες πύλες 20 kV)",
        "Οπτικός έλεγχος των πυλών, A/Z και γενικά του ικριώματος για τυχόν φωλιές από πτηνά, σπασίματα, μονωτήρες, κλαδιά, σύρματα κλπ",
        {"type": "section", "title": "3β. Πίνακες 20 kV"},
        "Παρατηρήσεις (3β. Πίνακες 20 kV)",
        "Οπτικός έλεγχος στους πίνακες Διακοπτών 20kV (αναγγελίες, ενδείξεις οργάνων, πόρτες) και έλεγχος θορύβων, ιονισμών",
        "Έλεγχοι υγρασίας (υπόγειο, κανάλια καλωδίων), αφυγραντήρων, θερμαντικών, φορητών πυροσβεστήρων",
        {"type": "section", "title": "4. Κτίριο χειρισμών & Τ.Α.Σ."},
        "Παρατηρήσεις (4. Κτίριο χειρισμών & Τ.Α.Σ.)",
        "Έλεγχος φορτιστή 110 V οπτικά με έλεγχο της τάσης, έντασης και καταγραφή",
        "Έλεγχος για alarm έλλειψης DC στον γενικό πίνακα DC",
        "Οπτικός έλεγχος διαρροών στοιχείων συσσωρευτών",
        {"type": "section", "title": "5. Αποζεύκτες Γραμμών"},
        "Παρατηρήσεις (5. Αποζεύκτες Γραμμών)",
        'Οπτικός έλεγχος των ΑΠ/Ζ και των "γεφυρών" αυτών στον 1ο Στύλο κάθε Γραμμής (σπασμένοι ΑΠ/Ζ, μονωτήρες, εκτονωμένα Α/Ξ κλπ)',
        {"type": "section", "title": "6. PC ΧΕΙΡΙΣΜΩΝ"},
        "Παρατηρήσεις (6. PC ΧΕΙΡΙΣΜΩΝ)",
        "Έλεγχος λειτουργίας ψηφιακού συστήματος (χειρισμοί, ενδείξεις, σημάνσεις)",
        "Τροφοδοσία υπολογιστή",
        {"type": "section", "title": "7. Απόψεις"},
        "Παρατηρήσεις και τυχόν προτάσεις  για την καλύτερη λειτουργία τόσο του εξοπλισμού, όσο και του κτηρίου γενικά του Υ/Σ.",
    ]


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

            show_message_popup("Σφάλμα", "Μη υποστηριζόμενη μορφή αρχείου")
            return
    except Exception as e:
        from popups import show_message_popup

        show_message_popup("Σφάλμα", f"Σφάλμα κατά την ανάγνωση αρχείου: {e}")
        return

    if df.empty:
        from popups import show_message_popup

        show_message_popup("Σφάλμα", "Το αρχείο δεν περιέχει δεδομένα.")
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
    return show_inspection_menu_popup(app, instance)


def show_import_inspections_dialog_delegate(app, instance):
    return app._create_file_import_dialog("Εισαγωγή επιθεωρήσεων από αρχείο", lambda fp: import_inspections_from_file(app, fp))


def show_inspection_history_delegate(app, instance=None):
    return show_inspection_history(app, instance)


def show_substation_inspection_history_delegate(app, substation_id, substation_name, parent_display_popup=None):
    return show_substation_inspection_history(app, substation_id, substation_name, parent_display_popup)


def show_inspection_details_delegate(app, inspection_id):
    return show_inspection_details(app, inspection_id)
