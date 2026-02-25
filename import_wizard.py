"""Import wizard popups for validating and mapping imported data."""

from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    from strings_proxy import STRINGS as S
except Exception:
    S = {"BUTTONS": {"CANCEL": "Ακύρωση"}, "TITLES": {}, "MESSAGES": {}}
from import_validator import (COLUMN_MAPPINGS, analyze_import_data,
                              detect_column_mismatches)


class ColumnMappingPopup:
    """Popup for mapping mismatched columns to correct database columns."""

    def __init__(self, df_columns, df, conn, on_continue, on_cancel):
        """
        Args:
            df_columns: List of column names from imported file
            df: pandas DataFrame with imported data
            conn: Database connection
            on_continue: Callback(column_mapping_dict) when user clicks Continue
            on_cancel: Callback() when user clicks Cancel
        """
        self.df_columns = df_columns
        self.df = df
        self.conn = conn
        self.on_continue = on_continue
        self.on_cancel = on_cancel
        self.column_mapping = {}
        self.spinners = {}

        # Detect mismatches (pass DataFrame so validator can detect breaker rows)
        self.mismatch_info = detect_column_mismatches(df_columns, df)

        # Auto-assign matched columns
        self.column_mapping = self.mismatch_info["matched"].copy()

        # Detect substations in imported data
        self.substations_info = self._detect_substations()

        self.popup = None
        self.continue_btn = None

    def _detect_substations(self):
        """Detect substations in imported data and check if they exist."""
        substations = set()
        existing = set()
        new = set()

        # Find substation column
        sub_col = None
        for col in self.df_columns:
            if col in ["Substation Name", "Substation", "Υποσταθμός"]:
                sub_col = col
                break

        if sub_col and sub_col in self.df.columns:
            cursor = self.conn.cursor()
            for _, row in self.df.iterrows():
                sub_name = row.get(sub_col)
                if pd.notna(sub_name) and str(sub_name).strip():
                    sub_name_clean = str(sub_name).strip()
                    substations.add(sub_name_clean)

                    # Check if exists in DB
                    cursor.execute(
                        "SELECT id FROM substations WHERE name=?", (sub_name_clean,)
                    )
                    if cursor.fetchone():
                        existing.add(sub_name_clean)
                    else:
                        new.add(sub_name_clean)

        return {
            "all": sorted(list(substations)),
            "existing": sorted(list(existing)),
            "new": sorted(list(new)),
        }

    def show(self):
        """Display the column mapping popup."""
        self.popup = Popup(
            title="Αντιστοίχιση Στηλών - Βήμα 1/2",
            size_hint=(0.85, 0.9),
            auto_dismiss=False,
        )

        main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        # Show substations info at the top
        if self.substations_info["all"]:
            sub_info_layout = BoxLayout(
                orientation="vertical", size_hint_y=None, spacing=5, padding=10
            )
            sub_info_layout.bind(minimum_height=sub_info_layout.setter("height"))

            if self.substations_info["new"]:
                # New substations - need creation
                with sub_info_layout.canvas.before:
                    Color(1, 0.95, 0.8, 1)  # Light orange
                    sub_info_layout.bg_rect = Rectangle(
                        size=sub_info_layout.size, pos=sub_info_layout.pos
                    )
                sub_info_layout.bind(
                    size=lambda obj, _: setattr(obj.bg_rect, "size", obj.size)
                )
                sub_info_layout.bind(
                    pos=lambda obj, _: setattr(obj.bg_rect, "pos", obj.pos)
                )

                sub_text = "ΥΠΟΣΤΑΘΜΟΙ ΠΡΟΣ ΔΗΜΙΟΥΡΓΙΑ:\n" + ", ".join(
                    self.substations_info["new"]
                )
                if self.substations_info["existing"]:
                    sub_text += "\n\nΥΠΑΡΧΟΝΤΕΣ: " + ", ".join(
                        self.substations_info["existing"]
                    )

                sub_label = Label(
                    text=sub_text,
                    size_hint_y=None,
                    height=1,
                    text_size=(None, None),
                    color=(0.4, 0.2, 0, 1),
                    bold=True,
                )
            else:
                # All existing
                with sub_info_layout.canvas.before:
                    Color(0.8, 0.95, 0.8, 1)  # Light green
                    sub_info_layout.bg_rect = Rectangle(
                        size=sub_info_layout.size, pos=sub_info_layout.pos
                    )
                sub_info_layout.bind(
                    size=lambda obj, _: setattr(obj.bg_rect, "size", obj.size)
                )
                sub_info_layout.bind(
                    pos=lambda obj, _: setattr(obj.bg_rect, "pos", obj.pos)
                )

                sub_text = "ΥΠΟΣΤΑΘΜΟΙ: " + ", ".join(self.substations_info["existing"])

                sub_label = Label(
                    text=sub_text,
                    size_hint_y=None,
                    height=1,
                    text_size=(None, None),
                    color=(0, 0.3, 0, 1),
                    bold=True,
                )

            sub_label.bind(
                size=lambda obj, _: setattr(obj, "text_size", (obj.width - 20, None)),
                texture_size=lambda obj, _: setattr(
                    obj, "height", obj.texture_size[1] + 10
                ),
            )
            sub_info_layout.add_widget(sub_label)
            main_layout.add_widget(sub_info_layout)

        # Header info
        if (
            self.mismatch_info["unmatched_import"]
            or self.mismatch_info["unmatched_required"]
        ):
            info_layout = BoxLayout(
                orientation="vertical", size_hint_y=None, height=80, spacing=5
            )

            # Create colored background
            with info_layout.canvas.before:
                Color(1, 0.95, 0.7, 1)  # Light yellow background
                info_layout.bg_rect = Rectangle(
                    size=info_layout.size, pos=info_layout.pos
                )
            info_layout.bind(size=lambda obj, _: setattr(obj.bg_rect, "size", obj.size))
            info_layout.bind(pos=lambda obj, _: setattr(obj.bg_rect, "pos", obj.pos))

            info_label = Label(
                text="ΕΝΤΟΠΙΣΤΗΚΑΝ ΣΤΗΛΕΣ ΠΟΥ ΔΕΝ ΤΑΙΡΙΑΖΟΥΝ ΜΕ ΤΗ ΒΑΣΗ ΔΕΔΟΜΕΝΩΝ.\nΠαρακαλώ αντιστοιχίστε τις στήλες στο σωστό πεδίο.",
                size_hint_y=None,
                height=60,
                color=(0.3, 0.2, 0, 1),
            )
            info_layout.add_widget(info_label)
            main_layout.add_widget(info_layout)
        else:
            success_layout = BoxLayout(
                orientation="vertical", size_hint_y=None, height=60, spacing=5
            )

            with success_layout.canvas.before:
                Color(0.7, 1, 0.7, 1)  # Light green background
                success_layout.bg_rect = Rectangle(
                    size=success_layout.size, pos=success_layout.pos
                )
            success_layout.bind(
                size=lambda obj, _: setattr(obj.bg_rect, "size", obj.size)
            )
            success_layout.bind(pos=lambda obj, _: setattr(obj.bg_rect, "pos", obj.pos))

            success_label = Label(
                text="ΌΛΕΣ ΟΙ ΣΤΗΛΕΣ ΑΝΑΓΝΩΡΙΣΤΗΚΑΝ ΣΩΣΤΑ!",
                size_hint_y=None,
                height=40,
                color=(0, 0.3, 0, 1),
                bold=True,
            )
            success_layout.add_widget(success_label)
            main_layout.add_widget(success_layout)

        # Scrollable mapping area
        scroll = ScrollView(bar_width=10)
        mapping_layout = GridLayout(cols=3, size_hint_y=None, spacing=10, padding=10)
        mapping_layout.bind(minimum_height=mapping_layout.setter("height"))

        # Headers
        headers = [
            Label(text="Στήλη Αρχείου", bold=True, size_hint_y=None, height=40),
            Label(text="->", bold=True, size_hint_y=None, height=40),
            Label(text="Πεδίο Βάσης Δεδομένων", bold=True, size_hint_y=None, height=40),
        ]
        for header in headers:
            mapping_layout.add_widget(header)

        # Available canonical columns for dropdown (only unassigned ones)
        def get_available_options():
            """Get list of canonical columns not yet assigned."""
            assigned = set(self.column_mapping.values())
            available = ["-- Παράλειψη --"] + [
                col for col in COLUMN_MAPPINGS.keys() if col not in assigned
            ]
            return available

        # Add mappings
        for import_col in self.df_columns:
            import_col_clean = str(import_col).strip()

            # Import column name
            col_label = Label(
                text=import_col_clean,
                size_hint_y=None,
                height=40,
                bold=(import_col_clean in self.mismatch_info["unmatched_import"]),
            )
            mapping_layout.add_widget(col_label)

            # Arrow
            mapping_layout.add_widget(Label(text="->", size_hint_y=None, height=40))

            # Spinner for canonical column
            if import_col_clean in self.column_mapping:
                # Already matched
                current_value = self.column_mapping[import_col_clean]
                # For matched columns, include current value plus skip option
                available_opts = ["-- Παράλειψη --", current_value]
                spinner = Spinner(
                    text=current_value,
                    values=available_opts,
                    size_hint_y=None,
                    height=40,
                    background_color=(0.7, 1, 0.7, 1),  # Light green for matched
                )
            else:
                # Unmatched - suggest best match
                suggestions = self.mismatch_info["suggestions"].get(
                    import_col_clean, []
                )
                available_opts = get_available_options()

                if suggestions:
                    suggested_value = suggestions[0][0]  # Best match
                    if suggested_value in available_opts:
                        spinner = Spinner(
                            text=suggested_value,
                            values=available_opts,
                            size_hint_y=None,
                            height=40,
                            background_color=(
                                1,
                                1,
                                0.7,
                                1,
                            ),  # Light yellow for suggested
                        )
                        self.column_mapping[import_col_clean] = suggested_value
                    else:
                        spinner = Spinner(
                            text="-- Παράλειψη --",
                            values=available_opts,
                            size_hint_y=None,
                            height=40,
                            background_color=(
                                1,
                                0.9,
                                0.9,
                                1,
                            ),  # Light red for unmatched
                        )
                else:
                    spinner = Spinner(
                        text="-- Παράλειψη --",
                        values=available_opts,
                        size_hint_y=None,
                        height=40,
                        background_color=(1, 0.9, 0.9, 1),  # Light red for unmatched
                    )

            spinner.bind(text=self._create_spinner_callback(import_col_clean))
            self.spinners[import_col_clean] = spinner
            mapping_layout.add_widget(spinner)

        scroll.add_widget(mapping_layout)
        main_layout.add_widget(scroll)

        # Show unmatched required columns warning
        if self.mismatch_info["unmatched_required"]:
            warning_layout = BoxLayout(
                orientation="vertical", size_hint_y=None, height=100, spacing=5
            )

            with warning_layout.canvas.before:
                Color(1, 0.8, 0.8, 1)  # Light red background
                warning_layout.bg_rect = Rectangle(
                    size=warning_layout.size, pos=warning_layout.pos
                )
            warning_layout.bind(
                size=lambda obj, _: setattr(obj.bg_rect, "size", obj.size)
            )
            warning_layout.bind(pos=lambda obj, _: setattr(obj.bg_rect, "pos", obj.pos))

            missing_cols = ", ".join(self.mismatch_info["unmatched_required"][:5])
            if len(self.mismatch_info["unmatched_required"]) > 5:
                missing_cols += "..."

            warning_label = Label(
                text=f"ΛΕΙΠΟΥΝ ΑΠΑΙΤΟΥΜΕΝΕΣ ΣΤΗΛΕΣ:\n{missing_cols}",
                size_hint_y=None,
                height=80,
                color=(0.5, 0, 0, 1),
            )
            warning_layout.add_widget(warning_label)
            main_layout.add_widget(warning_layout)

        # Action buttons
        button_layout = BoxLayout(size_hint_y=None, height=50, spacing=10)

        self.continue_btn = Button(text=">> Συνέχεια", bold=True)
        self.continue_btn.bind(on_press=self._on_continue_press)

        cancel_btn = Button(text="X " + S["BUTTONS"]["CANCEL"])
        cancel_btn.bind(on_press=lambda x: self._on_cancel_press())

        button_layout.add_widget(cancel_btn)
        button_layout.add_widget(self.continue_btn)

        main_layout.add_widget(button_layout)

        self.popup.content = main_layout
        self.popup.open()

        # Update button state
        self._update_continue_button()

    def _create_spinner_callback(self, import_col):
        """Create a callback for spinner selection."""

        def callback(spinner, text):
            self.column_mapping.get(import_col)

            if text == "-- Παράλειψη --":
                if import_col in self.column_mapping:
                    del self.column_mapping[import_col]
            else:
                self.column_mapping[import_col] = text

            # Update all spinners to refresh available options
            self._refresh_spinner_options()
            self._update_continue_button()

        return callback

    def _refresh_spinner_options(self):
        """Refresh dropdown options for all spinners based on current assignments."""
        assigned = set(self.column_mapping.values())

        for import_col, spinner in self.spinners.items():
            current_text = spinner.text

            # Build available options
            available = ["-- Paralipsi --"]

            # If this column has an assignment, include it
            if import_col in self.column_mapping:
                available.append(self.column_mapping[import_col])

            # Add unassigned canonical columns
            for col in COLUMN_MAPPINGS.keys():
                if col not in assigned and col not in available:
                    available.append(col)

            # Update spinner values
            spinner.values = available

            # Make sure current text is still valid
            if current_text not in available:
                spinner.text = "-- Παράλειψη --"

    def _update_continue_button(self):
        """Enable/disable continue button based on required columns."""
        # Check if all required columns are mapped
        mapped_canonical = set(self.column_mapping.values())
        set(COLUMN_MAPPINGS.keys())

        # At minimum, we need these critical columns
        critical_columns = {
            "Substation Name",
            "Element Type",
            "Name",
            "Operating Status",
        }

        has_critical = critical_columns.issubset(mapped_canonical)

        if self.continue_btn:
            self.continue_btn.disabled = not has_critical
            if has_critical:
                self.continue_btn.background_color = (0.3, 0.7, 0.3, 1)  # Green
            else:
                self.continue_btn.background_color = (0.5, 0.5, 0.5, 1)  # Gray

    def _on_continue_press(self, instance):
        """Handle continue button press."""
        # Create reverse mapping (import_col -> canonical_col)
        final_mapping = {
            k: v for k, v in self.column_mapping.items() if v != "-- Παράλειψη --"
        }
        self.popup.dismiss()
        self.on_continue(final_mapping)

    def _on_cancel_press(self):
        """Handle cancel button press."""
        self.popup.dismiss()
        self.on_cancel()


class DataValidationPopup:
    """Popup for previewing and validating import data before final import."""

    def __init__(self, df, column_mapping, conn, on_continue, on_cancel, on_back):
        """
        Args:
            df: pandas DataFrame with imported data
            column_mapping: Dict mapping import columns to canonical columns
            conn: Database connection
            on_continue: Callback(corrected_df) when user clicks Import
            on_cancel: Callback() when user clicks Cancel
            on_back: Callback() when user clicks Back
        """
        self.df = df
        self.column_mapping = column_mapping
        self.conn = conn
        self.on_continue = on_continue
        self.on_cancel = on_cancel
        self.on_back = on_back

        # Analyze data
        self.analysis = analyze_import_data(df, column_mapping, conn)

        # Track corrections
        self.corrections = {}  # {(row, column): corrected_value}

        self.popup = None

    def show(self):
        """Display the data validation popup."""
        self.popup = Popup(
            title="Επικύρωση Δεδομένων - Βήμα 2/2",
            size_hint=(0.9, 0.95),
            auto_dismiss=False,
        )

        main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        # Summary header
        summary_layout = BoxLayout(orientation="vertical", size_hint_y=None, spacing=5)
        summary_layout.bind(minimum_height=summary_layout.setter("height"))

        total_rows = self.analysis["total_rows"]
        valid_rows = self.analysis["valid_rows"]
        issue_count = len(self.analysis["issues"])
        new_sub_count = len(self.analysis["new_substations"])
        new_model_count = len(self.analysis["new_models"])

        if issue_count == 0:
            # All valid - green background
            with summary_layout.canvas.before:
                Color(0.7, 1, 0.7, 1)
                summary_layout.bg_rect = Rectangle(
                    size=summary_layout.size, pos=summary_layout.pos
                )
            summary_layout.bind(
                size=lambda obj, _: setattr(obj.bg_rect, "size", obj.size)
            )
            summary_layout.bind(pos=lambda obj, _: setattr(obj.bg_rect, "pos", obj.pos))

            summary_text = f"ΟΛΑ ΤΑ ΔΕΔΟΜΕΝΑ ΕΙΝΑΙ ΕΓΚΥΡΑ!\n\nΣύνολο γραμμών: {total_rows} | Έγκυρες: {valid_rows}"
            text_color = (0, 0.3, 0, 1)
        else:
            # Has issues - yellow background
            with summary_layout.canvas.before:
                Color(1, 0.95, 0.7, 1)
                summary_layout.bg_rect = Rectangle(
                    size=summary_layout.size, pos=summary_layout.pos
                )
            summary_layout.bind(
                size=lambda obj, _: setattr(obj.bg_rect, "size", obj.size)
            )
            summary_layout.bind(pos=lambda obj, _: setattr(obj.bg_rect, "pos", obj.pos))

            summary_text = f"ΒΡΕΘΗΚΑΝ {issue_count} ΠΙΘΑΝΑ ΠΡΟΒΛΗΜΑΤΑ\n\nΣύνολο γραμμών: {total_rows} | Έγκυρες: {valid_rows} | Προβλήματα: {issue_count}"
            text_color = (0.3, 0.2, 0, 1)

        summary_label = Label(
            text=summary_text, size_hint_y=None, height=80, color=text_color, bold=True
        )
        summary_layout.add_widget(summary_label)

        # Show new substations and models info
        if new_sub_count > 0 or new_model_count > 0:
            info_layout = BoxLayout(
                orientation="vertical", size_hint_y=None, spacing=3, padding=5
            )
            info_layout.bind(minimum_height=info_layout.setter("height"))

            with info_layout.canvas.before:
                Color(0.9, 0.95, 1, 1)  # Light blue background
                info_layout.bg_rect = Rectangle(
                    size=info_layout.size, pos=info_layout.pos
                )
            info_layout.bind(size=lambda obj, _: setattr(obj.bg_rect, "size", obj.size))
            info_layout.bind(pos=lambda obj, _: setattr(obj.bg_rect, "pos", obj.pos))

            if new_sub_count > 0:
                new_subs_text = f"ΝΕΟΙ ΥΠΟΣΤΑΘΜΟΙ ({new_sub_count}): " + ", ".join(
                    self.analysis["new_substations"][:5]
                )
                if new_sub_count > 5:
                    new_subs_text += f" ... και {new_sub_count - 5} ακόμα"
                new_subs_label = Label(
                    text=new_subs_text,
                    size_hint_y=None,
                    height=1,
                    text_size=(None, None),
                    color=(0.1, 0.2, 0.5, 1),
                )
                new_subs_label.bind(
                    size=lambda obj, _: setattr(
                        obj, "text_size", (obj.width - 10, None)
                    ),
                    texture_size=lambda obj, _: setattr(
                        obj, "height", obj.texture_size[1] + 5
                    ),
                )
                info_layout.add_widget(new_subs_label)

            if new_model_count > 0:
                models_text = f"ΝΕΑ ΜΟΝΤΕΛΑ ({new_model_count}): "
                models_list = [
                    f"{m['name']} ({m['category']})"
                    for m in self.analysis["new_models"][:3]
                ]
                models_text += ", ".join(models_list)
                if new_model_count > 3:
                    models_text += f" ... και {new_model_count - 3} ακόμα"
                new_models_label = Label(
                    text=models_text,
                    size_hint_y=None,
                    height=1,
                    text_size=(None, None),
                    color=(0.1, 0.2, 0.5, 1),
                )
                new_models_label.bind(
                    size=lambda obj, _: setattr(
                        obj, "text_size", (obj.width - 10, None)
                    ),
                    texture_size=lambda obj, _: setattr(
                        obj, "height", obj.texture_size[1] + 5
                    ),
                )
                info_layout.add_widget(new_models_label)

            summary_layout.add_widget(info_layout)

        main_layout.add_widget(summary_layout)

        # Issues section (if any)
        if self.analysis["issues"]:
            issues_label = Label(
                text="Ζητήματα που χρειάζονται προσοχή:",
                size_hint_y=None,
                height=30,
                bold=True,
            )
            main_layout.add_widget(issues_label)

            scroll = ScrollView(bar_width=10)
            issues_layout = GridLayout(cols=1, size_hint_y=None, spacing=5, padding=5)
            issues_layout.bind(minimum_height=issues_layout.setter("height"))

            # Group issues by row
            issues_by_row = {}
            for issue in self.analysis["issues"]:
                row = issue["row"]
                if row not in issues_by_row:
                    issues_by_row[row] = []
                issues_by_row[row].append(issue)

            # Display issues
            for row_num in sorted(issues_by_row.keys()):
                row_issues = issues_by_row[row_num]

                # Row header
                row_header = BoxLayout(
                    orientation="vertical", size_hint_y=None, spacing=5
                )
                row_header.bind(minimum_height=row_header.setter("height"))

                with row_header.canvas.before:
                    Color(0.95, 0.95, 0.95, 1)
                    row_header.bg_rect = Rectangle(
                        size=row_header.size, pos=row_header.pos
                    )
                row_header.bind(
                    size=lambda obj, _: setattr(obj.bg_rect, "size", obj.size)
                )
                row_header.bind(pos=lambda obj, _: setattr(obj.bg_rect, "pos", obj.pos))

                row_label = Label(
                    text=f"Γραμμή {row_num}:",
                    size_hint_y=None,
                    height=30,
                    bold=True,
                    color=(0, 0, 0, 1),
                )
                row_header.add_widget(row_label)

                # Each issue in this row
                for issue in row_issues:
                    issue_box = self._create_issue_widget(issue)
                    row_header.add_widget(issue_box)

                issues_layout.add_widget(row_header)

            scroll.add_widget(issues_layout)
            main_layout.add_widget(scroll)
        else:
            # No issues - show Excel-like table preview of all data
            preview_label = Label(
                text=f"Προεπισκόπηση δεδομένων ({total_rows} γραμμές):",
                size_hint_y=None,
                height=30,
                bold=True,
            )
            main_layout.add_widget(preview_label)

            # Create scrollable table with all rows - use horizontal scroll too
            scroll = ScrollView(bar_width=10, do_scroll_x=True, do_scroll_y=True)

            # Create reverse mapping for display
            reverse_mapping = {v: k for k, v in self.column_mapping.items()}
            columns = list(self.column_mapping.values())
            num_cols = len(columns) + 1  # +1 for row number

            # Calculate column width (minimum 150px per column)
            col_width = 150

            # Table layout with proper columns - set explicit width to enable horizontal scrolling
            table_layout = GridLayout(
                cols=num_cols,
                size_hint_y=None,
                size_hint_x=None,
                width=40 + (col_width * len(columns)),  # 40 for row# + width per column
                spacing=1,
                padding=2,
            )
            table_layout.bind(minimum_height=table_layout.setter("height"))

            # Header row with background
            # Row number header
            row_num_header = Label(
                text="#",
                size_hint=(None, None),
                width=40,
                height=30,
                bold=True,
                color=(1, 1, 1, 1),
            )
            with row_num_header.canvas.before:
                Color(0.2, 0.2, 0.5, 1)
                row_num_header.bg_rect = Rectangle(
                    size=row_num_header.size, pos=row_num_header.pos
                )
            row_num_header.bind(
                size=lambda obj, _: setattr(obj.bg_rect, "size", obj.size)
            )
            row_num_header.bind(pos=lambda obj, _: setattr(obj.bg_rect, "pos", obj.pos))
            table_layout.add_widget(row_num_header)

            # Column headers
            for col_name in columns:
                header = Label(
                    text=col_name,
                    size_hint=(None, None),
                    width=col_width,
                    height=30,
                    bold=True,
                    color=(1, 1, 1, 1),
                    text_size=(col_width - 10, None),
                    halign="center",
                    valign="middle",
                    shorten=True,
                    shorten_from="right",
                )
                with header.canvas.before:
                    Color(0.2, 0.2, 0.5, 1)
                    header.bg_rect = Rectangle(size=header.size, pos=header.pos)
                header.bind(size=lambda obj, _: setattr(obj.bg_rect, "size", obj.size))
                header.bind(pos=lambda obj, _: setattr(obj.bg_rect, "pos", obj.pos))
                table_layout.add_widget(header)

            # Data rows - show ALL rows
            for idx, row in self.df.iterrows():
                row_color = (0.95, 0.95, 0.95, 1) if idx % 2 == 0 else (1, 1, 1, 1)

                # Row number cell
                row_num_cell = Label(
                    text=str(idx + 1),
                    size_hint=(None, None),
                    width=40,
                    height=25,
                    color=(0, 0, 0, 1),
                )
                with row_num_cell.canvas.before:
                    Color(*row_color)
                    row_num_cell.bg_rect = Rectangle(
                        size=row_num_cell.size, pos=row_num_cell.pos
                    )
                row_num_cell.bind(
                    size=lambda obj, _: setattr(obj.bg_rect, "size", obj.size)
                )
                row_num_cell.bind(
                    pos=lambda obj, _: setattr(obj.bg_rect, "pos", obj.pos)
                )
                table_layout.add_widget(row_num_cell)

                # Data cells
                for canonical_col in columns:
                    import_col = reverse_mapping.get(canonical_col)
                    if import_col and import_col in self.df.columns:
                        val = row.get(import_col)
                        cell_text = str(val) if pd.notna(val) else ""
                    else:
                        cell_text = ""

                    cell = Label(
                        text=cell_text,
                        size_hint=(None, None),
                        width=col_width,
                        height=25,
                        color=(0, 0, 0, 1),
                        text_size=(col_width - 10, None),
                        halign="left",
                        valign="middle",
                        shorten=True,
                        shorten_from="right",
                    )
                    with cell.canvas.before:
                        Color(*row_color)
                        cell.bg_rect = Rectangle(size=cell.size, pos=cell.pos)
                    cell.bind(
                        size=lambda obj, _: setattr(obj.bg_rect, "size", obj.size)
                    )
                    cell.bind(pos=lambda obj, _: setattr(obj.bg_rect, "pos", obj.pos))
                    table_layout.add_widget(cell)

            scroll.add_widget(table_layout)
            main_layout.add_widget(scroll)

        # Action buttons
        button_layout = BoxLayout(size_hint_y=None, height=50, spacing=10)

        back_btn = Button(text="<< Πίσω")
        back_btn.bind(on_press=lambda x: self._on_back_press())

        cancel_btn = Button(text="X " + S["BUTTONS"]["CANCEL"])
        cancel_btn.bind(on_press=lambda x: self._on_cancel_press())

        import_btn = Button(
            text=">> Εισαγωγή", bold=True, background_color=(0.3, 0.7, 0.3, 1)
        )
        import_btn.bind(on_press=lambda x: self._on_import_press())

        button_layout.add_widget(back_btn)
        button_layout.add_widget(cancel_btn)
        button_layout.add_widget(import_btn)

        main_layout.add_widget(button_layout)

        self.popup.content = main_layout
        self.popup.open()

    def _create_issue_widget(self, issue):
        """Create a widget for displaying a single issue."""
        issue_layout = BoxLayout(
            orientation="vertical", size_hint_y=None, spacing=5, padding=(10, 5)
        )
        issue_layout.bind(minimum_height=issue_layout.setter("height"))

        # Issue description
        issue_type_map = {
            "invalid_value": "X Μη έγκυρη τιμή",
            "missing_required": "! Λείπει απαιτούμενο πεδίο",
            "fuzzy_match": "? Πιθανή διόρθωση",
        }

        issue_type_text = issue_type_map.get(issue["issue_type"], "! Πρόβλημα")

        desc_text = f"{issue_type_text} στη στήλη '{issue['column']}':\n"
        desc_text += f"   Τιμή: '{issue['value']}'"

        if issue["suggested_value"]:
            confidence_pct = int(issue["confidence"] * 100)
            desc_text += f"\n   Προτεινόμενη διόρθωση: '{issue['suggested_value']}' ({confidence_pct}% εμπιστοσύνη)"

        if issue["alternatives"]:
            alts = ", ".join([f"'{alt}'" for alt in issue["alternatives"][:3]])
            desc_text += f"\n   Άλλες επιλογές: {alts}"

        desc_label = Label(
            text=desc_text,
            size_hint_y=None,
            height=1,
            text_size=(None, None),
            color=(0, 0, 0, 1),
            halign="left",
        )
        desc_label.bind(
            size=lambda obj, _: setattr(obj, "text_size", (obj.width, None)),
            texture_size=lambda obj, _: setattr(
                obj, "height", obj.texture_size[1] + 10
            ),
        )

        issue_layout.add_widget(desc_label)

        # If there's a suggestion, add accept/reject buttons
        if issue["suggested_value"]:
            action_layout = BoxLayout(size_hint_y=None, height=40, spacing=5)

            accept_btn = Button(
                text=f"Apodoxi '{issue['suggested_value']}'",
                size_hint_x=0.6,
                background_color=(0.7, 1, 0.7, 1),
            )
            accept_btn.bind(on_press=lambda x, i=issue: self._accept_suggestion(i))

            reject_btn = Button(
                text="X Aporripsi", size_hint_x=0.4, background_color=(1, 0.9, 0.9, 1)
            )
            reject_btn.bind(on_press=lambda x, i=issue: self._reject_suggestion(i))

            action_layout.add_widget(accept_btn)
            action_layout.add_widget(reject_btn)
            issue_layout.add_widget(action_layout)

        issue_layout.bind(minimum_height=issue_layout.setter("height"))

        return issue_layout

    def _accept_suggestion(self, issue):
        """Accept a suggested correction."""
        key = (issue["row"], issue["column"])
        self.corrections[key] = issue["suggested_value"]
        # TODO: Update UI to show accepted

    def _reject_suggestion(self, issue):
        """Reject a suggested correction."""
        key = (issue["row"], issue["column"])
        if key in self.corrections:
            del self.corrections[key]
        # TODO: Update UI to show rejected

    def _on_import_press(self):
        """Handle import button press."""
        # Apply corrections to dataframe
        corrected_df = self.df.copy()

        # Apply accepted corrections
        reverse_mapping = {v: k for k, v in self.column_mapping.items()}
        for (row_num, canonical_col), corrected_value in self.corrections.items():
            import_col = reverse_mapping.get(canonical_col)
            if import_col:
                df_row_idx = row_num - 3  # Convert Excel row to DataFrame index
                if 0 <= df_row_idx < len(corrected_df):
                    corrected_df.at[df_row_idx, import_col] = corrected_value

        self.popup.dismiss()
        self.on_continue(corrected_df, self.column_mapping)

    def _on_back_press(self):
        """Handle back button press."""
        self.popup.dismiss()
        self.on_back()

    def _on_cancel_press(self):
        """Handle cancel button press."""
        self.popup.dismiss()
        self.on_cancel()
