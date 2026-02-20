import os
import sys
import subprocess
import importlib

from pdf_reports import generate_maintenance_report, generate_sf6_leak_report
from popups import show_message_popup


def show_sf6_management_popup(app, instance=None):
    """Show SF6 leakage management report popup (delegated from DBrun)."""
    # Import Kivy widgets lazily to avoid top-level Kivy dependency in tests
    Popup = importlib.import_module("kivy.uix.popup").Popup
    BoxLayout = importlib.import_module("kivy.uix.boxlayout").BoxLayout
    Button = importlib.import_module("kivy.uix.button").Button
    Label = importlib.import_module("kivy.uix.label").Label
    Spinner = importlib.import_module("kivy.uix.spinner").Spinner
    GridLayout = importlib.import_module("kivy.uix.gridlayout").GridLayout
    ScrollView = importlib.import_module("kivy.uix.scrollview").ScrollView

    c = app.conn.cursor()
    c.execute(
        "SELECT DISTINCT substr(date_time, 1, 4) FROM maintenance WHERE date_time IS NOT NULL AND date_time != '' ORDER BY 1 DESC"
    )
    years = [row[0] for row in c.fetchall() if row[0] and row[0].isdigit()]
    if not years:
        years = [str(__import__("datetime").datetime.now().year)]

    popup = Popup(title="Διαχείριση SF6", size_hint=(0.95, 0.9))
    main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    control_row = BoxLayout(size_hint_y=None, height=40, spacing=10)
    control_row.add_widget(Label(text="Έτος:", size_hint_x=0.15))
    year_spinner = Spinner(
        text=years[0], values=years, size_hint_x=0.25, size_hint_y=None, height=35
    )
    control_row.add_widget(year_spinner)

    refresh_btn = Button(text="Ανανέωση", size_hint_x=0.2)
    control_row.add_widget(refresh_btn)
    print_btn = Button(text="Εκτύπωση", size_hint_x=0.2)
    control_row.add_widget(print_btn)
    excel_btn = Button(text="Excel", size_hint_x=0.2)
    control_row.add_widget(excel_btn)
    main_layout.add_widget(control_row)

    summary_label = Label(text="", size_hint_y=None, height=60)
    summary_label.bind(
        width=lambda inst, val: setattr(inst, "text_size", (val, None)),
        texture_size=lambda inst, val: setattr(inst, "height", val[1] + 10),
    )
    main_layout.add_widget(summary_label)

    scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
    table_layout = GridLayout(cols=1, spacing=5, size_hint_y=None, padding=5)
    table_layout.bind(minimum_height=table_layout.setter("height"))
    scroll.add_widget(table_layout)
    main_layout.add_widget(scroll)

    def render_report(year_value: str):
        table_layout.clear_widgets()
        data = app._get_sf6_report_data(year_value)
        total_leakage = data["total_leakage"]
        installed_sf6 = data["installed_sf6"]
        percentage = data["percentage"]
        active_elements = data["active_elements"]
        active_substations = data["active_substations"]

        summary_text = (
            f"Εγκατεστημένο SF6 (ενεργά): {installed_sf6:.2f} kg | "
            f"Ενεργά στοιχεία SF6: {active_elements} | Υποσταθμοί με SF6: {active_substations}\n"
            f"Έτος: {year_value} | Διαρροές: {total_leakage:.2f} kg | Ποσοστό: {percentage:.2f}%"
        )
        summary_label.text = summary_text

        header = GridLayout(cols=4, size_hint_y=None, height=30)
        header.add_widget(Label(text="Ημερομηνία", bold=True))
        header.add_widget(Label(text="Υποσταθμός", bold=True))
        header.add_widget(Label(text="Στοιχείο", bold=True))
        header.add_widget(Label(text="Διαρροή (kg)", bold=True))
        table_layout.add_widget(header)

        if not data["rows"]:
            table_layout.add_widget(
                Label(
                    text="Δεν υπάρχουν καταχωρήσεις διαρροών για το έτος.",
                    size_hint_y=None,
                    height=30,
                )
            )
            return

        for row in data["rows"]:
            rlayout = GridLayout(cols=4, size_hint_y=None, height=30)
            rlayout.add_widget(Label(text=row.get("date_time") or "-"))
            rlayout.add_widget(Label(text=row.get("substation") or "-"))
            rlayout.add_widget(Label(text=row.get("element") or "-"))
            leakage = row.get("leakage")
            leakage_text = ("-" if leakage is None else f"{leakage:.2f}")
            rlayout.add_widget(Label(text=leakage_text))
            table_layout.add_widget(rlayout)

    def handle_print(*_args):
        try:
            pdf_path = generate_sf6_leak_report(app.conn, year_spinner.text)

            def _open_pdf():
                try:
                    if sys.platform == "win32":
                        os.startfile(pdf_path)
                    elif sys.platform == "darwin":
                        subprocess.call(["open", pdf_path])
                    else:
                        subprocess.call(["xdg-open", pdf_path])
                except Exception:
                    # ignore open-errors; show_message_popup already reports success
                    pass

            show_message_popup("PDF Δημιουργήθηκε", f"Το PDF δημιουργήθηκε:\n{pdf_path}", callback=_open_pdf)
        except Exception as exc:
            show_message_popup("Σφάλμα", f"Αποτυχία δημιουργίας PDF:\n{str(exc)}")

    def handle_excel(*_args):
        try:
            excel_path = app._export_sf6_excel(year_spinner.text)

            def _open_excel():
                try:
                    if sys.platform == "win32":
                        os.startfile(excel_path)
                    elif sys.platform == "darwin":
                        subprocess.call(["open", excel_path])
                    else:
                        subprocess.call(["xdg-open", excel_path])
                except Exception:
                    pass

            show_message_popup("Excel Δημιουργήθηκε", f"Το Excel δημιουργήθηκε:\n{excel_path}", callback=_open_excel)
        except Exception as exc:
            show_message_popup("Σφάλμα", f"Αποτυχία δημιουργίας Excel:\n{str(exc)}")

    refresh_btn.bind(on_press=lambda _x: render_report(year_spinner.text))
    year_spinner.bind(text=lambda _s, _t: render_report(year_spinner.text))
    print_btn.bind(on_press=handle_print)
    excel_btn.bind(on_press=handle_excel)

    render_report(year_spinner.text)

    close_btn = Button(text="Κλείσιμο", size_hint_y=None, height=40)
    close_btn.bind(on_press=popup.dismiss)
    main_layout.add_widget(close_btn)

    popup.content = main_layout
    popup.open()


def generate_pdf_report(app, maintenance_id, element_id, element_name):
    """Generate PDF maintenance report (UI wrapper)."""
    # Lazy imports for UI elements
    Popup = importlib.import_module("kivy.uix.popup").Popup
    BoxLayout = importlib.import_module("kivy.uix.boxlayout").BoxLayout
    Button = importlib.import_module("kivy.uix.button").Button
    Label = importlib.import_module("kivy.uix.label").Label

    try:
        pdf_path = generate_maintenance_report(app.conn, maintenance_id, element_id)

        def _open_pdf():
            try:
                if sys.platform == "win32":
                    os.startfile(pdf_path)
                elif sys.platform == "darwin":
                    subprocess.call(["open", pdf_path])
                else:
                    subprocess.call(["xdg-open", pdf_path])
            except Exception:
                pass

        show_message_popup(
            "PDF Δημιουργήθηκε",
            f'Το αρχείο PDF για το στοιχείο "{element_name}"\nδημιουργήθηκε επιτυχώς!\n\nΑποθηκεύτηκε στο:\n{pdf_path}',
            callback=_open_pdf,
        )

    except Exception as e:
        show_message_popup("Σφάλμα", f"Αποτυχία δημιουργίας PDF:\n{str(e)}")


def export_full_db_ui(app, parent_popup=None):
    """Invoke `excel_io.export_full_db` using `app.conn`.

    This keeps the UI wiring for the "Export DB" button in `reports.py`.
    """
    try:
        from excel_io import export_full_db
    except Exception:
        return False

    try:
        if parent_popup:
            parent_popup.dismiss()
    except Exception:
        pass

    return export_full_db(app.conn)


def open_file(path, *, not_found_message="Το αρχείο δεν βρέθηκε!", error_title="Σφάλμα", error_prefix="Αποτυχία ανοίγματος αρχείου:\n"):
    """Open a file with the platform default application and handle errors with popups.

    Returns True on success, False on failure.
    """
    from popups import show_message_popup
    import subprocess
    import sys

    if not path or not os.path.exists(path):
        show_message_popup(error_title, not_found_message)
        return False
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.call(["open", path])
        else:
            subprocess.call(["xdg-open", path])
        return True
    except Exception as exc:
        show_message_popup(error_title, f"{error_prefix}{str(exc)}")
        return False


def show_confirm(title: str, message: str, yes_callback=None, yes_text="ΝΑΙ", no_text="ΟΧΙ", yes_color=None, size_hint=(0.6, 0.3)):
    """Show a standardized confirmation popup and call `yes_callback` when confirmed.

    The callback is called after the popup is dismissed.
    """
    Popup = __import__("kivy.uix.popup", fromlist=["Popup"]).Popup
    BoxLayout = __import__("kivy.uix.boxlayout", fromlist=["BoxLayout"]).BoxLayout
    Label = __import__("kivy.uix.label", fromlist=["Label"]).Label
    Button = __import__("kivy.uix.button", fromlist=["Button"]).Button

    popup = Popup(title=title, size_hint=size_hint)
    layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
    warning_label = Label(text=message, size_hint_y=0.6)
    layout.add_widget(warning_label)

    buttons_layout = BoxLayout(size_hint_y=0.3, spacing=10)

    def _on_yes(_instance=None):
        try:
            popup.dismiss()
        except Exception:
            pass
        try:
            if yes_callback:
                yes_callback()
        except Exception:
            pass

    yes_btn = Button(text=yes_text)
    if yes_color:
        try:
            yes_btn.color = yes_color
        except Exception:
            pass
    yes_btn.bind(on_press=lambda x: _on_yes(x))
    buttons_layout.add_widget(yes_btn)

    no_btn = Button(text=no_text)
    no_btn.bind(on_press=popup.dismiss)
    buttons_layout.add_widget(no_btn)

    layout.add_widget(buttons_layout)
    popup.content = layout
    popup.open()
    return popup


def _get_sf6_report_data(app, year: str):
    """Return SF6 report data dictionary for `year` using `app.conn`."""
    c = app.conn.cursor()
    year_prefix = f"{year}%"

    c.execute(
        """
             SELECT m.date_time, s.name, e.name, e.element_type, me.sf6_leakage_kg,
                 me.sf6_leak_methodology, p.name
        FROM maintenance_elements me
        JOIN maintenance m ON me.maintenance_id = m.id
        JOIN elements e ON me.element_id = e.id
        JOIN substations s ON m.substation_id = s.id
        LEFT JOIN people p ON m.responsible_id = p.id
        WHERE e.breaker_category = 'SF6'
          AND m.date_time LIKE ?
          AND me.sf6_leakage_kg IS NOT NULL
          AND me.sf6_leakage_kg > 0
        ORDER BY m.date_time ASC
        """,
        (year_prefix,),
    )
    leak_rows = c.fetchall()

    total_leakage = 0.0
    rows = []
    for (
        date_time,
        sub_name,
        elem_name,
        elem_type,
        leakage,
        methodology,
        responsible_name,
    ) in leak_rows:
        total_leakage += leakage
        rows.append(
            {
                "date_time": date_time or "-",
                "substation": sub_name or "-",
                "element": elem_name or "-",
                "leakage": leakage,
                "methodology": methodology or "",
                "responsible": responsible_name or "-",
            }
        )

    substation_rows = {}
    for row in rows:
        substation_rows.setdefault(row["substation"], []).append(row)

    c.execute("""
        SELECT
            COUNT(*),
            SUM(COALESCE(em.sf6_capacity_kg, 0))
        FROM elements e
        LEFT JOIN element_models em ON e.element_model_id = em.id
        WHERE e.operating_status = 'Ενεργή'
          AND e.breaker_category = 'SF6'
          AND e.element_type IN ('Διακόπτης ΥΤ', 'Διακόπτης ΜΤ')
        """)
    counts = c.fetchone()
    total_elements = counts[0] or 0
    installed_sf6 = counts[1] or 0.0

    c.execute("""
        SELECT COUNT(*), COUNT(DISTINCT s.id)
        FROM elements e
        JOIN substations s ON e.substation_id = s.id
        WHERE e.operating_status = 'Ενεργή'
          AND e.breaker_category = 'SF6'
          AND e.element_type IN ('Διακόπτης ΥΤ', 'Διακόπτης ΜΤ')
        """)
    active_counts = c.fetchone()
    active_elements = active_counts[0] or 0
    active_substations = active_counts[1] or 0

    c.execute("""
        SELECT s.name, SUM(COALESCE(em.sf6_capacity_kg, 0))
        FROM elements e
        JOIN substations s ON e.substation_id = s.id
        LEFT JOIN element_models em ON e.element_model_id = em.id
        WHERE e.operating_status = 'Ενεργή'
          AND e.breaker_category = 'SF6'
          AND e.element_type IN ('Διακόπτης ΥΤ', 'Διακόπτης ΜΤ')
        GROUP BY s.name
        """)
    substation_installed = {row[0]: (row[1] or 0.0) for row in c.fetchall()}

    percentage = (total_leakage / installed_sf6 * 100) if installed_sf6 else 0.0

    return {
        "total_leakage": total_leakage,
        "installed_sf6": installed_sf6,
        "percentage": percentage,
        "total_elements": total_elements,
        "active_elements": active_elements,
        "active_substations": active_substations,
        "rows": rows,
        "substation_rows": substation_rows,
        "substation_installed": substation_installed,
    }


def _export_sf6_excel(app, year: str):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import PatternFill, Border, Side, Alignment, Font
    except Exception as exc:
        raise RuntimeError(
            "Δεν βρέθηκε το πακέτο openpyxl. Εγκαταστήστε το για εξαγωγή Excel."
        ) from exc

    data = _get_sf6_report_data(app, year)

    wb = Workbook()
    ws = wb.active
    ws.title = "Σύνοψη"

    grey_fill = PatternFill(fill_type="solid", fgColor="D9D9D9")
    blue_fill = PatternFill(fill_type="solid", fgColor="1F4E79")
    white_font = Font(color="FFFFFF", bold=True)
    bold_font = Font(bold=True)
    thin = Side(style="thin")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    summary_titles = [
        "ΣΥΝΟΛΙΚΗ ΕΓΚΑΤΕΣΤΗΜΕΝΗ ΠΟΣΟΤΗΤΑ (kg)",
        f"ΔΙΑΡΡΟΕΣ {year} (kg)",
        f"ΠΟΣΟΣΤΟ ΔΙΑΡΡΟΩΝ {year}",
    ]
    summary_values = [
        f"{data['installed_sf6']:.2f}",
        f"{data['total_leakage']:.2f}",
        f"{data['percentage']:.2f}%",
    ]

    for col_idx, title in enumerate(summary_titles, start=1):
        cell = ws.cell(row=1, column=col_idx, value=title)
        cell.fill = grey_fill
        cell.font = bold_font
        cell.alignment = center
        cell.border = border

        val_cell = ws.cell(row=2, column=col_idx, value=summary_values[col_idx - 1])
        val_cell.alignment = center
        val_cell.border = border

    ws.row_dimensions[1].height = 30
    ws.row_dimensions[2].height = 24

    for col in range(1, 4):
        ws.column_dimensions[chr(64 + col)].width = 35

    substation_sums = []
    for substation, rows in data["substation_rows"].items():
        total = sum([r.get("leakage") or 0 for r in rows])
        if total > 0:
            substation_sums.append((substation, total))

    start_row = 4
    if substation_sums:
        ws.cell(row=start_row, column=1, value="Υποσταθμός").font = bold_font
        ws.cell(row=start_row, column=2, value="Σύνολο Διαρροών (kg)").font = (
            bold_font
        )
        for col_idx in (1, 2):
            cell = ws.cell(row=start_row, column=col_idx)
            cell.alignment = center
            cell.border = border

        row_ptr = start_row + 1
        for substation, total in sorted(substation_sums, key=lambda x: x[0] or ""):
            ws.cell(row=row_ptr, column=1, value=substation or "-").border = border
            ws.cell(row=row_ptr, column=2, value=f"{total:.2f}").border = border
            ws.cell(row=row_ptr, column=1).alignment = center
            ws.cell(row=row_ptr, column=2).alignment = center
            row_ptr += 1

    for substation, rows in data["substation_rows"].items():
        sheet_title = substation[:31] if substation else "Υποσταθμός"
        if sheet_title in wb.sheetnames:
            suffix = 1
            base = sheet_title[:28]
            while f"{base}_{suffix}" in wb.sheetnames:
                suffix += 1
            sheet_title = f"{base}_{suffix}"

        ws_sub = wb.create_sheet(title=sheet_title)
        ws_sub.merge_cells("A1:J1")
        title_cell = ws_sub["A1"]
        title_cell.value = "ΠΙΝΑΚΑΣ 4: ΠΗΓΗ ΕΚΠΟΜΠΩΝ ΑΠΌ ΕΞΟΠΛΙΣΜΟ ΧΡΗΣΗΣ SF6"
        title_cell.alignment = center

        for col_idx in range(1, 11):
            cell = ws_sub.cell(row=1, column=col_idx)
            cell.fill = blue_fill
            cell.font = white_font
            cell.alignment = center
            cell.border = border

        headers = [
            "Α/Α",
            "ΒΟΚ ή ΠΕΡΙΟΧΗ",
            "ΕΓΚΑΤΑΣΤΑΣΗ (Πχ. Όνομα Υ/Σ)",
            "ΜΟΝΑΔΑ ΜΕΤΡΗΣΗΣ",
            "ΠΛΗΡΩΣΗ Ή ΑΝΤΙΚΑΤΑΣΤΑΣΗ (ΜΕΘΟΔΟΛΟΓΙΑ)",
            "ΣΥΝΟΛΙΚΗ ΕΓΚΑΤΕΣΤΗΜΕΝΗ ΠΟΣΟΤΗΤΑ (kg)",
            "ΠΟΣΟΤΗΤΑ ΔΙΑΡΡΟΩΝ (kg)",
            "ΗΜ/ΝΙΑ",
            "ΥΠΕΥΘΥΝΟΣ ΣΥΝΕΡΓΕΙΟΥ",
            "ΥΠΟΓΡΑΦΗ",
        ]

        for col_idx, header in enumerate(headers, start=1):
            cell = ws_sub.cell(row=2, column=col_idx, value=header)
            cell.font = bold_font
            cell.alignment = center
            cell.border = border

        installed_sub = data["substation_installed"].get(substation, 0.0)
        start_row = 3
        for idx, row in enumerate(rows, start=1):
            values = [
                idx,
                "ΔΕΕΔ",
                substation,
                "kg",
                row.get("methodology", "") or "",
                f"{installed_sub:.2f}",
                f"{row['leakage']:.2f}",
                row["date_time"],
                row.get("responsible", "-") or "-",
                "",
            ]
            for col_idx, value in enumerate(values, start=1):
                cell = ws_sub.cell(row=start_row, column=col_idx, value=value)
                cell.alignment = Alignment(
                    horizontal="center", vertical="center", wrap_text=True
                )
                cell.border = border
            start_row += 1

        ws_sub.row_dimensions[1].height = 30
        ws_sub.row_dimensions[2].height = 28
        for col_idx in range(1, 11):
            ws_sub.column_dimensions[chr(64 + col_idx)].width = 22

    reports_dir = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(reports_dir, exist_ok=True)
    timestamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(reports_dir, f"SF6_Leakages_{year}_{timestamp}.xlsx")
    wb.save(output_path)
    return output_path


def create_substations_template(base_dir: str) -> tuple[bool, str]:
    """Create substations import template. Returns (success, message/path)."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
    except Exception:
        return False, "openpyxl δεν είναι εγκατεστημένο!"

    try:
        wb = Workbook()
        ws = wb.active
        ws.title = "Substations"

        headers = ["Name", "Location", "Adoption Date"]
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill(
                start_color="4472C4", end_color="4472C4", fill_type="solid"
            )

        ws.column_dimensions["A"].width = 30
        ws.column_dimensions["B"].width = 50
        ws.column_dimensions["C"].width = 15

        examples = [
            ("Υποσταθμός Α", "https://maps.google.com/?q=example1", "2025-01-15"),
            ("Υποσταθμός Β", "https://maps.google.com/?q=example2", "2025-01-20"),
        ]
        for idx, (name, location, date) in enumerate(examples, 2):
            ws.cell(row=idx, column=1, value=name)
            ws.cell(row=idx, column=2, value=location)
            ws.cell(row=idx, column=3, value=date)

        template_path = os.path.join(base_dir, "substations_import_template.xlsx")
        wb.save(template_path)
        return True, template_path
    except Exception as exc:  # pragma: no cover - UI surface
        return False, f"Σφάλμα: {exc}"


def create_elements_template(base_dir: str) -> tuple[bool, str]:
    """Create elements import template. Returns (success, message/path)."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
    except Exception:
        return False, "openpyxl δεν είναι εγκατεστημένο!"

    try:
        wb = Workbook()
        ws = wb.active
        ws.title = "Elements"

        # Add version info in first row
        ws.cell(row=1, column=1, value="TEMPLATE_VERSION: v2.0")
        ws.cell(row=1, column=1).font = Font(italic=True, color="999999")
        ws.row_dimensions[1].height = 15

        headers = [
            "Substation Name",
            "Element Type",
            "Name",
            "Serial Number",
            "Maintenance Date",
            "Τύπος Διακόπτη",
            "Breaker Role",
            "Operating Status",
            "Gate",
            "Model Name",
            "Model Manufacturer",
            "Model Installation Space",
        ]
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=2, column=col, value=header)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill(
                start_color="70AD47", end_color="70AD47", fill_type="solid"
            )

        ws.column_dimensions["A"].width = 25
        ws.column_dimensions["B"].width = 25
        ws.column_dimensions["C"].width = 20
        ws.column_dimensions["D"].width = 15
        ws.column_dimensions["E"].width = 15
        ws.column_dimensions["F"].width = 20
        ws.column_dimensions["G"].width = 15
        ws.column_dimensions["H"].width = 20
        ws.column_dimensions["I"].width = 15
        ws.column_dimensions["J"].width = 15
        ws.column_dimensions["K"].width = 20
        ws.column_dimensions["L"].width = 20

        examples = [
            (
                "Υποσταθμός Α",
                "Διακόπτης ΜΤ",
                "Main Breaker",
                "SN-001",
                "2025-01-20",
                "SF6",
                "Κεντρικός",
                "Ενεργή",
                "ΠΥΛΗ 1",
                "SF6-400",
                "ABB",
                "Εσωτερικού",
            ),
            (
                "Υποσταθμός Α",
                "Μετασχηματιστής 150/20KV",
                "Transformer 1",
                "SN-002",
                "2025-01-18",
                "",
                "",
                "Ενεργή",
                "ΠΥΛΗ 1",
                "GEAFOL",
                "Siemens",
                "Εξωτερικού",
            ),
        ]
        for idx, row_data in enumerate(examples, 3):
            for col, value in enumerate(row_data, 1):
                ws.cell(row=idx, column=col, value=value)

        template_path = os.path.join(base_dir, "elements_import_template.xlsx")
        wb.save(template_path)
        return True, template_path
    except Exception as exc:  # pragma: no cover - UI surface
        return False, f"Σφάλμα: {exc}"
