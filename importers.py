from typing import Callable

try:
    import pandas as pd
except ImportError:
    pd = None

# Template version for validation
TEMPLATE_VERSION = "v2.0"

# Required columns for element import
REQUIRED_COLUMNS = [
    "Substation Name",
    "Element Type",
    "Name",
    "Serial Number",
    "Gate",
    "Operating Status",
]

# Valid values for specific columns
VALID_OPERATING_STATUS = ["Ενεργή", "Ανενεργή", "Active", "Inactive"]
VALID_BREAKER_ROLES = [
    "Κεντρικός",
    "Γραμμής",
    "Διασυνδετικός",
    "Διακόπτης Πυκνωτών",
    "",
]


def _clean_value(value):
    if pd is None:
        return value
    return str(value).strip() if pd.notna(value) else ""


def _validate_template_version(df) -> tuple[bool, str]:
    """Check if template has version header and matches current version."""
    # Check if first row contains version info
    if len(df) > 0:
        first_row_values = [str(v) for v in df.iloc[0].values if pd.notna(v)]
        version_marker = [
            v
            for v in first_row_values
            if v.startswith("Version:") or v.startswith("TEMPLATE_VERSION:")
        ]
        if version_marker:
            template_version = version_marker[0].split(":", 1)[1].strip()
            if template_version != TEMPLATE_VERSION:
                return (
                    False,
                    f"Το template είναι παλιά έκδοση ({template_version}). Παρακαλώ χρησιμοποιήστε το νέο template ({TEMPLATE_VERSION}).",
                )
    return True, ""


def _validate_required_fields(df, row_num: int, row) -> tuple[bool, list[str]]:
    """Validate that all required fields have values."""
    errors = []

    # Check required columns
    for col in REQUIRED_COLUMNS:
        value = row.get(col, "")
        if pd.isna(value) or str(value).strip() == "":
            errors.append(f'Γραμμή {row_num}: Το πεδίο "{col}" είναι κενό')

    # Validate operating status value
    operating_status = row.get("Operating Status", "")
    if pd.notna(operating_status):
        status_str = str(operating_status).strip()
        if status_str not in VALID_OPERATING_STATUS:
            errors.append(
                f'Γραμμή {row_num}: Άκυρη κατάσταση λειτουργίας "{status_str}". Επιτρεπόμενες: Ενεργή, Ανενεργή'
            )

    # Validate breaker role for circuit breakers
    element_type = str(row.get("Element Type", "")).strip()
    if element_type in ["Διακόπτης ΥΤ", "Διακόπτης ΜΤ"]:
        breaker_role = row.get("Breaker Role", "")
        if pd.notna(breaker_role):
            role_str = str(breaker_role).strip()
            if role_str and role_str not in VALID_BREAKER_ROLES:
                errors.append(
                    f'Γραμμή {row_num}: Άκυρος ρόλος διακόπτη "{role_str}". Επιτρεπόμενοι: Κεντρικός, Γραμμής, Διασυνδετικός, Διακόπτης Πυκνωτών'
                )
        # HV breakers MUST be Κεντρικός
        if element_type == "Διακόπτης ΥΤ":
            if pd.notna(breaker_role) and str(breaker_role).strip() not in [
                "",
                "Κεντρικός",
            ]:
                errors.append(
                    f"Γραμμή {row_num}: Οι διακόπτες ΥΤ μπορούν να είναι μόνο Κεντρικοί"
                )

    return len(errors) == 0, errors


def import_substations_from_excel(
    conn,
    file_path: str,
    on_success: Callable[[str], None],
    on_error: Callable[[str], None],
) -> None:
    if pd is None:
        on_error("pandas δεν είναι εγκατεστημένο!")
        return

    try:
        cursor = conn.cursor()
        df_sub = pd.read_excel(file_path, sheet_name="Substations")
        count = 0
        duplicates = []

        for _, row in df_sub.iterrows():
            name = _clean_value(row.get("Name", ""))
            location = (
                row.get("Location", "") if pd.notna(row.get("Location", "")) else ""
            )
            adoption_date = (
                row.get("Adoption Date", "")
                if pd.notna(row.get("Adoption Date", ""))
                else ""
            )

            if name:
                cursor.execute("SELECT id FROM substations WHERE name=?", (name,))
                if cursor.fetchone():
                    duplicates.append(name)
                else:
                    cursor.execute(
                        "INSERT INTO substations (name, location, adoption_date) VALUES (?, ?, ?)",
                        (name, location, adoption_date),
                    )
                    count += 1

        conn.commit()

        if duplicates:
            dup_list = ", ".join(duplicates)
            msg = f"{count} νέοι υποσταθμοί εισήχθησαν.\nΥπάρχοντες (δεν εισήχθησαν): {dup_list}"
        else:
            msg = f"{count} υποσταθμοί εισήχθησαν με επιτυχία!"

        on_success(msg)
    except Exception as exc:
        on_error(f"Σφάλμα: {exc}")


def import_substations_from_csv(
    conn,
    file_path: str,
    on_success: Callable[[str], None],
    on_error: Callable[[str], None],
) -> None:
    if pd is None:
        on_error("pandas δεν είναι εγκατεστημένο!")
        return

    try:
        cursor = conn.cursor()
        df_sub = pd.read_csv(file_path)
        count = 0
        duplicates = []

        for _, row in df_sub.iterrows():
            name = _clean_value(row.get("Name", ""))
            location = (
                row.get("Location", "") if pd.notna(row.get("Location", "")) else ""
            )
            adoption_date = (
                row.get("Adoption Date", "")
                if pd.notna(row.get("Adoption Date", ""))
                else ""
            )

            if name:
                cursor.execute("SELECT id FROM substations WHERE name=?", (name,))
                if cursor.fetchone():
                    duplicates.append(name)
                else:
                    cursor.execute(
                        "INSERT INTO substations (name, location, adoption_date) VALUES (?, ?, ?)",
                        (name, location, adoption_date),
                    )
                    count += 1

        conn.commit()

        if duplicates:
            dup_list = ", ".join(duplicates)
            msg = f"{count} νέοι υποσταθμοί εισήχθησαν.\nΥπάρχοντες (δεν εισήχθησαν): {dup_list}"
        else:
            msg = f"{count} υποσταθμοί εισήχθησαν με επιτυχία!"

        on_success(msg)
    except Exception as exc:
        on_error(f"Σφάλμα: {exc}")


def import_elements_from_excel(
    conn,
    file_path: str,
    on_success: Callable[[str], None],
    on_error: Callable[[str], None],
    on_duplicate: Callable[[str, str, str], bool] = None,
) -> None:
    """Import elements from Excel.

    on_duplicate(sub_name, name, serial_number) -> bool
    - True: replace existing element
    - False: skip existing element
    """

    if pd is None:
        on_error("pandas δεν είναι εγκατεστημένο!")
        return

    try:
        cursor = conn.cursor()
        df_elem = pd.read_excel(file_path, sheet_name="Elements")

        # Validate template version
        is_valid, version_error = _validate_template_version(df_elem)
        if not is_valid:
            on_error(version_error)
            return

        # Skip version row if present
        if len(df_elem) > 0:
            first_row_values = [str(v) for v in df_elem.iloc[0].values if pd.notna(v)]
            if any(
                v.startswith("Version:") or v.startswith("TEMPLATE_VERSION:")
                for v in first_row_values
            ):
                df_elem = df_elem.iloc[1:].reset_index(drop=True)

        # Validate all required columns exist
        missing_cols = [col for col in REQUIRED_COLUMNS if col not in df_elem.columns]
        if missing_cols:
            on_error(
                f"Λείπουν απαιτούμενες στήλες: {', '.join(missing_cols)}\n\nΠαρακαλώ χρησιμοποιήστε το ενημερωμένο template."
            )
            return

        # Collect all validation errors first
        validation_errors = []
        count = 0
        updated = 0
        skipped = 0
        not_found = []

        for idx, row in df_elem.iterrows():
            row_num = (
                idx + 3
            )  # +3 because Excel is 1-indexed, has version row and header row

            # Validate required fields for this row
            is_valid, field_errors = _validate_required_fields(df_elem, row_num, row)
            if not is_valid:
                validation_errors.extend(field_errors)
                continue  # Skip this row but continue checking others

            sub_name = row.get("Substation Name", "")
            element_type = row.get("Element Type", "")
            name = row.get("Name", "")
            serial_number = row.get("Serial Number", "")
            maintenance_date = row.get("Maintenance Date", "")

            # Set voltage_level automatically based on element_type
            element_type_str = str(element_type)
            if "ΥΤ" in element_type_str or "150/20" in element_type_str:
                voltage_level = "150KV"
            elif "ΜΤ" in element_type_str or "20/0.4" in element_type_str:
                voltage_level = "20KV"
            else:
                voltage_level = ""

            manufacturer = row.get("Manufacturer", "")
            breaker_type = (
                str(row.get("Τύπος Διακόπτη", "")).strip()
                if pd.notna(row.get("Τύπος Διακόπτη", ""))
                else ""
            )
            (
                str(row.get("Breaker Role", "")).strip()
                if pd.notna(row.get("Breaker Role", ""))
                else ""
            )
            gate = row.get("Gate", "") if pd.notna(row.get("Gate", "")) else ""
            model_name = (
                str(row.get("Model Name", "")).strip()
                if pd.notna(row.get("Model Name", ""))
                else ""
            )
            model_manufacturer = (
                str(row.get("Model Manufacturer", "")).strip()
                if pd.notna(row.get("Model Manufacturer", ""))
                else ""
            )

            # Read operating_status and normalize to Greek
            operating_status = (
                row.get("Operating Status", "")
                if pd.notna(row.get("Operating Status", ""))
                else ""
            )
            if operating_status:
                operating_status = str(operating_status).strip()
                # Normalize English to Greek
                if operating_status == "Active":
                    operating_status = "Ενεργή"
                elif operating_status == "Inactive":
                    operating_status = "Ανενεργή"
            # Default to Active if not provided
            if not operating_status:
                operating_status = "Ενεργή"

            if sub_name and name:
                cursor.execute(
                    "SELECT id FROM substations WHERE name=?", (str(sub_name),)
                )
                result = cursor.fetchone()
                if result:
                    sub_id = result[0]
                    name_str = str(name)
                    serial_str = str(serial_number) if pd.notna(serial_number) else ""

                    # Look up element_model_id if model info provided
                    element_model_id = None
                    if model_name:
                        elem_type_for_model = (
                            str(element_type) if pd.notna(element_type) else ""
                        )
                        cursor.execute(
                            "SELECT id FROM element_models WHERE element_category=? AND model_name=? AND manufacturer=?",
                            (elem_type_for_model, model_name, model_manufacturer),
                        )
                        model_result = cursor.fetchone()
                        if model_result:
                            element_model_id = model_result[0]

                    # Check for duplicate
                    cursor.execute(
                        "SELECT id FROM elements WHERE substation_id=? AND name=? AND serial_number=?",
                        (sub_id, name_str, serial_str),
                    )
                    existing = cursor.fetchone()

                    decision_replace = False
                    if existing:
                        if on_duplicate:
                            decision_replace = bool(
                                on_duplicate(str(sub_name), name_str, serial_str)
                            )
                        else:
                            decision_replace = False

                    # Normalize element type and determine if element is a main switch
                    elem_type_str = str(element_type) if pd.notna(element_type) else ""
                    is_main_switch = 0
                    # Convert old element types to new format
                    if elem_type_str == "Κεντρικός Διακόπτης ΥΤ":
                        elem_type_str = "Διακόπτης ΥΤ"
                        is_main_switch = 1
                    elif elem_type_str == "Κεντρικός Διακόπτης ΜΤ":
                        elem_type_str = "Διακόπτης ΜΤ"
                        is_main_switch = 1
                    elif elem_type_str == "Διακόπτης Φορτίου Γραμμής ΜΤ":
                        elem_type_str = "Διακόπτης ΜΤ"
                        is_main_switch = 0

                    if existing and decision_replace:
                        cursor.execute(
                            "UPDATE elements SET element_type=?, maintenance_date=?, voltage_level=?, manufacturer=?, gate=?, is_main_switch=?, breaker_category=?, element_model_id=?, operating_status=? WHERE id=?",
                            (
                                elem_type_str,
                                (
                                    str(maintenance_date)
                                    if pd.notna(maintenance_date)
                                    else ""
                                ),
                                str(voltage_level) if pd.notna(voltage_level) else "",
                                str(manufacturer) if pd.notna(manufacturer) else "",
                                str(gate) if gate else "",
                                is_main_switch,
                                breaker_type if breaker_type else None,
                                element_model_id,
                                operating_status,
                                existing[0],
                            ),
                        )
                        updated += 1
                    elif existing and not decision_replace:
                        skipped += 1
                    else:
                        cursor.execute(
                            "INSERT INTO elements (substation_id, element_type, name, serial_number, maintenance_date, voltage_level, manufacturer, gate, is_main_switch, breaker_category, element_model_id, operating_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                sub_id,
                                elem_type_str,
                                name_str,
                                serial_str,
                                (
                                    str(maintenance_date)
                                    if pd.notna(maintenance_date)
                                    else ""
                                ),
                                str(voltage_level) if pd.notna(voltage_level) else "",
                                str(manufacturer) if pd.notna(manufacturer) else "",
                                str(gate) if gate else "",
                                is_main_switch,
                                breaker_type if breaker_type else None,
                                element_model_id,
                                operating_status,
                            ),
                        )
                        count += 1
                else:
                    not_found.append(sub_name)

        # If there are validation errors, don't commit and show all errors
        if validation_errors:
            error_msg = "Σφάλματα επικύρωσης δεδομένων:\n\n" + "\n".join(
                validation_errors[:10]
            )
            if len(validation_errors) > 10:
                error_msg += (
                    f"\n\n... και {len(validation_errors) - 10} ακόμα σφάλματα."
                )
            error_msg += "\n\nΗ εισαγωγή ακυρώθηκε. Παρακαλώ διορθώστε τα σφάλματα και προσπαθήστε ξανά."
            on_error(error_msg)
            return

        conn.commit()

        msg_parts = []
        if count > 0:
            msg_parts.append(f"{count} νέα στοιχεία εισήχθησαν")
        if updated > 0:
            msg_parts.append(f"{updated} στοιχεία ενημερώθηκαν")
        if skipped > 0:
            msg_parts.append(f"{skipped} διπλότυπα παραλείφθηκαν")
        if not_found:
            msg_parts.append(f"Υποσταθμοί δεν βρέθησαν: {set(not_found)}")

        msg = ". ".join(msg_parts) + "!" if msg_parts else "Δεν εισήχθησαν στοιχεία!"
        on_success(msg)
    except Exception as exc:
        on_error(f"Σφάλμα: {exc}")


def import_elements_from_csv(
    conn,
    file_path: str,
    on_success: Callable[[str], None],
    on_error: Callable[[str], None],
    on_duplicate: Callable[[str, str, str], bool] = None,
) -> None:
    """Import elements from CSV.

    on_duplicate(sub_name, name, serial_number) -> bool
    - True: replace existing element
    - False: skip existing element
    """

    if pd is None:
        on_error("pandas δεν είναι εγκατεστημένο!")
        return

    try:
        cursor = conn.cursor()
        df_elem = pd.read_csv(file_path)

        # Validate template version
        is_valid, version_error = _validate_template_version(df_elem)
        if not is_valid:
            on_error(version_error)
            return

        # Skip version row if present
        if len(df_elem) > 0:
            first_row_values = [str(v) for v in df_elem.iloc[0].values if pd.notna(v)]
            if any(
                v.startswith("Version:") or v.startswith("TEMPLATE_VERSION:")
                for v in first_row_values
            ):
                df_elem = df_elem.iloc[1:].reset_index(drop=True)

        # Validate all required columns exist
        missing_cols = [col for col in REQUIRED_COLUMNS if col not in df_elem.columns]
        if missing_cols:
            on_error(
                f"Λείπουν απαιτούμενες στήλες: {', '.join(missing_cols)}\n\nΠαρακαλώ χρησιμοποιήστε το ενημερωμένο template."
            )
            return

        # Collect all validation errors first
        validation_errors = []
        count = 0
        updated = 0
        skipped = 0
        not_found = []

        for idx, row in df_elem.iterrows():
            row_num = (
                idx + 3
            )  # +3 because CSV is 1-indexed, has version row and header row

            # Validate required fields for this row
            is_valid, field_errors = _validate_required_fields(df_elem, row_num, row)
            if not is_valid:
                validation_errors.extend(field_errors)
                continue  # Skip this row but continue checking others

            sub_name = row.get("Substation Name", "")
            element_type = row.get("Element Type", "")
            name = row.get("Name", "")
            serial_number = row.get("Serial Number", "")
            maintenance_date = row.get("Maintenance Date", "")

            # Set voltage_level automatically based on element_type
            element_type_str = str(element_type)
            if "ΥΤ" in element_type_str or "150/20" in element_type_str:
                voltage_level = "150KV"
            elif "ΜΤ" in element_type_str or "20/0.4" in element_type_str:
                voltage_level = "20KV"
            else:
                voltage_level = ""

            manufacturer = row.get("Manufacturer", "")
            breaker_type = (
                str(row.get("Τύπος Διακόπτη", "")).strip()
                if pd.notna(row.get("Τύπος Διακόπτη", ""))
                else ""
            )
            breaker_role = (
                str(row.get("Breaker Role", "")).strip()
                if pd.notna(row.get("Breaker Role", ""))
                else ""
            )
            gate = row.get("Gate", "") if pd.notna(row.get("Gate", "")) else ""
            model_name = (
                str(row.get("Model Name", "")).strip()
                if pd.notna(row.get("Model Name", ""))
                else ""
            )
            model_manufacturer = (
                str(row.get("Model Manufacturer", "")).strip()
                if pd.notna(row.get("Model Manufacturer", ""))
                else ""
            )

            # Read operating_status and normalize to Greek
            operating_status = (
                row.get("Operating Status", "")
                if pd.notna(row.get("Operating Status", ""))
                else ""
            )
            if operating_status:
                operating_status = str(operating_status).strip()
                # Normalize English to Greek
                if operating_status == "Active":
                    operating_status = "Ενεργή"
                elif operating_status == "Inactive":
                    operating_status = "Ανενεργή"
            # Default to Active if not provided
            if not operating_status:
                operating_status = "Ενεργή"

            if sub_name and name:
                cursor.execute(
                    "SELECT id FROM substations WHERE name=?", (str(sub_name),)
                )
                result = cursor.fetchone()
                if result:
                    sub_id = result[0]
                    name_str = str(name)
                    serial_str = str(serial_number) if pd.notna(serial_number) else ""

                    # Look up element_model_id if model info provided
                    element_model_id = None
                    if model_name:
                        elem_type_for_model = (
                            str(element_type) if pd.notna(element_type) else ""
                        )
                        cursor.execute(
                            "SELECT id FROM element_models WHERE element_category=? AND model_name=? AND manufacturer=?",
                            (elem_type_for_model, model_name, model_manufacturer),
                        )
                        model_result = cursor.fetchone()
                        if model_result:
                            element_model_id = model_result[0]

                    # Check for duplicate
                    cursor.execute(
                        "SELECT id FROM elements WHERE substation_id=? AND name=? AND serial_number=?",
                        (sub_id, name_str, serial_str),
                    )
                    existing = cursor.fetchone()

                    decision_replace = False
                    if existing:
                        if on_duplicate:
                            decision_replace = bool(
                                on_duplicate(str(sub_name), name_str, serial_str)
                            )
                        else:
                            decision_replace = False

                            # Normalize element type and determine breaker role
                    elem_type_str = str(element_type) if pd.notna(element_type) else ""

                    # Map breaker role to is_main_switch
                    # 0=Γραμμής, 1=Κεντρικός, 2=Διασυνδετικός, 3=Διακόπτης Πυκνωτών
                    is_main_switch = 0  # Default to line breaker

                    if elem_type_str in ["Διακόπτης ΥΤ", "Διακόπτης ΜΤ"]:
                        # HV breakers are ALWAYS main breakers
                        if elem_type_str == "Διακόπτης ΥΤ":
                            is_main_switch = 1
                        # MV breakers: map from Breaker Role column
                        elif breaker_role == "Κεντρικός":
                            is_main_switch = 1
                        elif breaker_role == "Διασυνδετικός":
                            is_main_switch = 2
                        elif breaker_role == "Διακόπτης Πυκνωτών":
                            is_main_switch = 3
                        elif breaker_role == "Γραμμής":
                            is_main_switch = 0
                        else:
                            # Empty breaker role defaults to line breaker for MV
                            is_main_switch = 0

                    # Convert old element type formats (backward compatibility)
                    if elem_type_str == "Κεντρικός Διακόπτης ΥΤ":
                        elem_type_str = "Διακόπτης ΥΤ"
                        is_main_switch = 1
                    elif elem_type_str == "Κεντρικός Διακόπτης ΜΤ":
                        elem_type_str = "Διακόπτης ΜΤ"
                        is_main_switch = 1
                    elif elem_type_str == "Διακόπτης Φορτίου Γραμμής ΜΤ":
                        elem_type_str = "Διακόπτης ΜΤ"
                        is_main_switch = 0

                    if existing and decision_replace:
                        cursor.execute(
                            "UPDATE elements SET element_type=?, maintenance_date=?, voltage_level=?, manufacturer=?, gate=?, is_main_switch=?, breaker_category=?, element_model_id=?, operating_status=? WHERE id=?",
                            (
                                elem_type_str,
                                (
                                    str(maintenance_date)
                                    if pd.notna(maintenance_date)
                                    else ""
                                ),
                                str(voltage_level) if pd.notna(voltage_level) else "",
                                str(manufacturer) if pd.notna(manufacturer) else "",
                                str(gate) if gate else "",
                                is_main_switch,
                                breaker_type if breaker_type else None,
                                element_model_id,
                                operating_status,
                                existing[0],
                            ),
                        )
                        updated += 1
                    elif existing and not decision_replace:
                        skipped += 1
                    else:
                        cursor.execute(
                            "INSERT INTO elements (substation_id, element_type, name, serial_number, maintenance_date, voltage_level, manufacturer, gate, is_main_switch, breaker_category, element_model_id, operating_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                sub_id,
                                elem_type_str,
                                name_str,
                                serial_str,
                                (
                                    str(maintenance_date)
                                    if pd.notna(maintenance_date)
                                    else ""
                                ),
                                str(voltage_level) if pd.notna(voltage_level) else "",
                                str(manufacturer) if pd.notna(manufacturer) else "",
                                str(gate) if gate else "",
                                is_main_switch,
                                breaker_type if breaker_type else None,
                                element_model_id,
                                operating_status,
                            ),
                        )
                        count += 1
                else:
                    not_found.append(sub_name)

        # If there are validation errors, don't commit and show all errors
        if validation_errors:
            error_msg = "Σφάλματα επικύρωσης δεδομένων:\n\n" + "\n".join(
                validation_errors[:10]
            )
            if len(validation_errors) > 10:
                error_msg += (
                    f"\n\n... και {len(validation_errors) - 10} ακόμα σφάλματα."
                )
            error_msg += "\n\nΗ εισαγωγή ακυρώθηκε. Παρακαλώ διορθώστε τα σφάλματα και προσπαθήστε ξανά."
            on_error(error_msg)
            return

        conn.commit()

        msg_parts = []
        if count > 0:
            msg_parts.append(f"{count} νέα στοιχεία εισήχθησαν")
        if updated > 0:
            msg_parts.append(f"{updated} στοιχεία ενημερώθηκαν")
        if skipped > 0:
            msg_parts.append(f"{skipped} διπλότυπα παραλείφθηκαν")
        if not_found:
            msg_parts.append(f"Υποσταθμοί δεν βρέθησαν: {set(not_found)}")

        msg = ". ".join(msg_parts) + "!" if msg_parts else "Δεν εισήχθησαν στοιχεία!"
        on_success(msg)
    except Exception as exc:
        on_error(f"Σφάλμα: {exc}")
