import os
import traceback
from typing import Callable

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    from strings_proxy import STRINGS as S
except Exception:
    S = {"MESSAGES": {}}

# Canonical breaker element names
ELEM_BREAKER_YT = S["MESSAGES"].get("ELEMENT_BREAKER_YT", "Διακόπτης ΥΤ")
ELEM_BREAKER_MT = S["MESSAGES"].get("ELEMENT_BREAKER_MT", "Διακόπτης ΜΤ")
ELEMENT_BREAKER_SUBSTR = S.get("MESSAGES", {}).get(
    "ELEMENT_BREAKER_SUBSTR", "Διακόπτης"
)

# Template version for validation
TEMPLATE_VERSION = "v2.0"

# Required columns for element import
REQUIRED_COLUMNS = [
    "Substation Name",
    "Element Type",
    "Name",
    "Gate",
    "Operating Status",
]

# Valid values for specific columns (prefer centralized lists in strings.py)
VALID_OPERATING_STATUS = list(
    S.get("MESSAGES", {}).get("OPERATING_STATUS", ["Ενεργή", "Ανενεργή"])
) + ["Active", "Inactive"]
VALID_BREAKER_ROLES = list(
    S.get("MESSAGES", {}).get(
        "BREAKER_TYPES", ["Κεντρικός", "Γραμμής", "Διασυνδετικός", "Διακόπτης Πυκνωτών"]
    )
) + [""]

# Precompute canonical breaker element types from strings to avoid duplicating literals
BREAKER_ELEMENT_TYPES = [
    t
    for t in S.get("MESSAGES", {}).get("ELEMENT_TYPES", [])
    if ELEMENT_BREAKER_SUBSTR in t
]


def _clean_value(value):
    if pd is None:
        return value
    return str(value).strip() if pd.notna(value) else ""


# Column synonyms to tolerate English/Greek/header variants
COLUMN_SYNONYMS = {
    "Substation Name": [
        "Substation Name",
        "Substation",
        "Υποσταθμός",
        "Υποσταθμιο",
        "Υποσταθμός Όνομα",
        "Όνομα Υποσταθμού",
    ],
    "Element Type": ["Element Type", "Type", "Τύπος Στοιχείου", "Τύπος"],
    "Name": ["Name", "Όνομα", "Name (Στοιχείο)"],
    "Gate": ["Gate", "Πύλη", "Gate (Πύλη)"],
    "Operating Status": [
        "Operating Status",
        "Status",
        "Κατάσταση",
        "Κατάσταση Λειτουργίας",
    ],
    "Serial Number": ["Serial Number", "S/N", "Serial", "Αριθμός Σειράς"],
    "Maintenance Date": ["Maintenance Date", "Τελευταία Συντήρηση", "Last Maintenance"],
    "Model Name": ["Model Name", "Model", "Μοντέλο"],
    "Model Manufacturer": [
        "Model Manufacturer",
        "Manufacturer",
        "Κατασκευαστής Μοντέλου",
        "Μοντέλο Κατασκευαστής",
    ],
    "Model Installation Space": [
        "Model Installation Space",
        "Installation Space",
        "Χώρος Εγκατάστασης",
        "Installation",
    ],
    "Breaker Role": ["Breaker Role", "Role", "Ρόλος Διακόπτη"],
    "Τύπος Διακόπτη": [
        "Τύπος Διακόπτη",
        "Breaker Type",
        "BreakerType",
        "Breaker",
        "Τυπος Διακοπτη",
        "Breaker Type (τύπος)",
    ],
    "Rated Power": [
        "Rated Power",
        "Power",
        "Power MVA",
        "Power (MVA)",
        "Ισχύς",
        "Ονομαστική Ισχύς",
        "ΙΣΧΥΣ",
    ],
}


def _map_columns(df):
    """Rename dataframe columns in-place (returns df) mapping common synonyms
    to canonical column names used across import routines.
    Matching is case-insensitive and trims whitespace.
    """
    if df is None:
        return df
    cols = list(df.columns)
    mapped = {}
    lower_map = {c.lower().strip(): c for c in cols}
    for canonical, variants in COLUMN_SYNONYMS.items():
        found = None
        for v in variants:
            key = v.lower().strip()
            if key in lower_map:
                found = lower_map[key]
                break
        # also try direct exact canonical if present
        if not found and canonical in cols:
            found = canonical
        if found:
            mapped[found] = canonical
    if mapped:
        try:
            df = df.rename(columns=mapped)
        except Exception:
            pass
    return df


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
    if element_type in BREAKER_ELEMENT_TYPES:
        breaker_role = row.get("Breaker Role", "")
        if pd.notna(breaker_role):
            role_str = str(breaker_role).strip()
            if role_str and role_str not in VALID_BREAKER_ROLES:
                errors.append(
                    f'Γραμμή {row_num}: Άκυρος ρόλος διακόπτη "{role_str}". Επιτρεπόμενοι: Κεντρικός, Γραμμής, Διασυνδετικός, Διακόπτης Πυκνωτών'
                )
        # HV breakers MUST be Κεντρικός
        if element_type == ELEM_BREAKER_YT:
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

    # sanitize incoming file path to guard against stray surrounding quotes
    try:
        if isinstance(file_path, str):
            _qchars = "\"'\u2018\u2019\u201c\u201d\u2032\u2033"
            fp = file_path.strip()
            # strip matching quote characters from both ends
            while fp and fp[0] in _qchars:
                fp = fp[1:]
            while fp and fp[-1] in _qchars:
                fp = fp[:-1]
            file_path = fp
    except Exception:
        pass

    try:
        cursor = conn.cursor()
        # Try primary sheet name first, fall back to searching sheets for required columns
        df_sub = None
        try:
            df_sub = pd.read_excel(file_path, sheet_name="Substations")
        except ValueError:
            try:
                all_sheets = pd.read_excel(file_path, sheet_name=None)
                chosen = None
                for name, df in all_sheets.items():
                    cols = [str(c) for c in df.columns]
                    if all(col in cols for col in ["Name"]):
                        df_sub = df
                        chosen = name
                        break
                if chosen is None:
                    on_error(
                        f"Worksheet named 'Substations' not found and no suitable sheet detected. Available sheets: {list(all_sheets.keys())}"
                    )
                    return
            except Exception as exc2:
                tb = traceback.format_exc()

                # Provide more specific error messages based on the exception type
                error_msg = str(exc2).lower()
                if "file not found" in error_msg or "no such file" in error_msg:
                    user_msg = f"Το αρχείο δεν βρέθηκε: {file_path}"
                elif "permission denied" in error_msg:
                    user_msg = f"Δεν έχετε δικαίωμα ανάγνωσης του αρχείου: {file_path}"
                elif (
                    "unsupported format" in error_msg
                    or "not a zip file" in error_msg
                    or "expected" in error_msg
                ):
                    user_msg = (
                        "Το αρχείο δεν είναι έγκυρο Excel. "
                        "Βεβαιωθείτε ότι το αρχείο δεν είναι κατεστραμμένο ή μερικώς κατεβασμένο. "
                        f"Λάθος: {exc2}"
                    )
                elif "truncated" in error_msg:
                    user_msg = (
                        "Το αρχείο φαίνεται να είναι κατεστραμμένο ή μερικώς κατεβασμένο. "
                        "Δοκιμάστε να κατεβάσετε ξανά το αρχείο."
                    )
                else:
                    user_msg = f"Σφάλμα κατά την ανάγνωση του αρχείου: {exc2}"

                details = (
                    f"{user_msg}\n\n"
                    f"Λεπτομέρειες:\n"
                    f"Path: {repr(file_path)}\n"
                    f"Exists: {os.path.exists(file_path)}\n"
                    f"Readable: {os.access(file_path, os.R_OK) if os.path.exists(file_path) else 'N/A'}\n"
                    f"Size: {os.path.getsize(file_path) if os.path.exists(file_path) else 'N/A'} bytes\n"
                    f"Traceback:\n{tb}"
                )
                on_error(details)
                return
        except Exception as exc:
            tb = traceback.format_exc()

            # Provide more specific error messages based on the exception type
            error_msg = str(exc).lower()
            if "file not found" in error_msg or "no such file" in error_msg:
                user_msg = f"Το αρχείο δεν βρέθηκε: {file_path}"
            elif "permission denied" in error_msg:
                user_msg = f"Δεν έχετε δικαίωμα ανάγνωσης του αρχείου: {file_path}"
            elif (
                "unsupported format" in error_msg
                or "not a zip file" in error_msg
                or "expected" in error_msg
            ):
                user_msg = (
                    "Το αρχείο δεν είναι έγκυρο Excel. "
                    "Βεβαιωθείτε ότι το αρχείο δεν είναι κατεστραμμένο ή μερικώς κατεβασμένο. "
                    f"Λάθος: {exc}"
                )
            elif "truncated" in error_msg:
                user_msg = (
                    "Το αρχείο φαίνεται να είναι κατεστραμμένο ή μερικώς κατεβασμένο. "
                    "Δοκιμάστε να κατεβάσετε ξανά το αρχείο."
                )
            else:
                user_msg = f"Σφάλμα κατά την ανάγνωση του αρχείου: {exc}"

            details = (
                f"{user_msg}\n\n"
                f"Λεπτομέρειες:\n"
                f"Path: {repr(file_path)}\n"
                f"Exists: {os.path.exists(file_path)}\n"
                f"Readable: {os.access(file_path, os.R_OK) if os.path.exists(file_path) else 'N/A'}\n"
                f"Size: {os.path.getsize(file_path) if os.path.exists(file_path) else 'N/A'} bytes\n"
                f"Traceback:\n{tb}"
            )
            on_error(details)
            return
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

    # sanitize incoming file path to guard against stray surrounding quotes
    try:
        if isinstance(file_path, str):
            _qchars = "\"'\u2018\u2019\u201c\u201d\u2032\u2033"
            fp = file_path.strip()
            while fp and fp[0] in _qchars:
                fp = fp[1:]
            while fp and fp[-1] in _qchars:
                fp = fp[:-1]
            file_path = fp
    except Exception:
        pass

    try:
        cursor = conn.cursor()
        try:
            df_sub = pd.read_csv(file_path)
        except Exception as exc:
            tb = traceback.format_exc()

            # Provide more specific error messages based on the exception type
            error_msg = str(exc).lower()
            if "file not found" in error_msg or "no such file" in error_msg:
                user_msg = f"Το αρχείο δεν βρέθηκε: {file_path}"
            elif "permission denied" in error_msg:
                user_msg = f"Δεν έχετε δικαίωμα ανάγνωσης του αρχείου: {file_path}"
            elif (
                "unsupported format" in error_msg
                or "not a zip file" in error_msg
                or "expected" in error_msg
            ):
                user_msg = (
                    "Το αρχείο δεν είναι έγκυρο CSV. "
                    "Βεβαιωθείτε ότι το αρχείο δεν είναι κατεστραμμένο ή μερικώς κατεβασμένο. "
                    f"Λάθος: {exc}"
                )
            elif "truncated" in error_msg or "decoding" in error_msg:
                user_msg = (
                    "Το αρχείο φαίνεται να είναι κατεστραμμένο, μερικώς κατεβασμένο ή έχει κακή κωδικοποίηση. "
                    "Δοκιμάστε να κατεβάσετε ξανά το αρχείο ή να το ανοίξετε με Excel και να το σώσετε ως CSV."
                )
            else:
                user_msg = f"Σφάλμα κατά την ανάγνωση του αρχείου: {exc}"

            details = (
                f"{user_msg}\n\n"
                f"Λεπτομέρειες:\n"
                f"Path: {repr(file_path)}\n"
                f"Exists: {os.path.exists(file_path)}\n"
                f"Readable: {os.access(file_path, os.R_OK) if os.path.exists(file_path) else 'N/A'}\n"
                f"Size: {os.path.getsize(file_path) if os.path.exists(file_path) else 'N/A'} bytes\n"
                f"Traceback:\n{tb}"
            )
            on_error(details)
            return
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

    # sanitize incoming file path to guard against stray surrounding quotes
    try:
        if isinstance(file_path, str):
            _qchars = "\"'\u2018\u2019\u201c\u201d\u2032\u2033"
            fp = file_path.strip()
            while fp and fp[0] in _qchars:
                fp = fp[1:]
            while fp and fp[-1] in _qchars:
                fp = fp[:-1]
            file_path = fp
    except Exception:
        pass

    try:
        cursor = conn.cursor()
        # Try the 'Elements' sheet; if missing, search for a sheet that contains the required columns
        df_elem = None
        try:
            df_elem = pd.read_excel(file_path, sheet_name="Elements")
        except ValueError:
            try:
                all_sheets = pd.read_excel(file_path, sheet_name=None)
                chosen = None
                for name, df in all_sheets.items():
                    cols = [str(c) for c in df.columns]
                    if all(col in cols for col in REQUIRED_COLUMNS):
                        df_elem = df
                        chosen = name
                        break
                if chosen is None:
                    on_error(
                        f"Worksheet named 'Elements' not found and no sheet contains required columns. Available sheets: {list(all_sheets.keys())}"
                    )
                    return
            except Exception as exc2:
                tb = traceback.format_exc()
                details = (
                    f"Σφάλμα κατά τον έλεγχο αρχείου: {exc2}\n"
                    f"Path: {repr(file_path)}\n"
                    f"Exists: {os.path.exists(file_path)}\n"
                    f"Readable: {os.access(file_path, os.R_OK) if os.path.exists(file_path) else 'N/A'}\n"
                    f"Size: {os.path.getsize(file_path) if os.path.exists(file_path) else 'N/A'}\n"
                    f"Traceback:\n{tb}"
                )
                on_error(details)
                return
        except Exception as exc:
            tb = traceback.format_exc()

            # Provide more specific error messages based on the exception type
            error_msg = str(exc).lower()
            if "file not found" in error_msg or "no such file" in error_msg:
                user_msg = f"Το αρχείο δεν βρέθηκε: {file_path}"
            elif "permission denied" in error_msg:
                user_msg = f"Δεν έχετε δικαίωμα ανάγνωσης του αρχείου: {file_path}"
            elif (
                "unsupported format" in error_msg
                or "not a zip file" in error_msg
                or "expected" in error_msg
            ):
                user_msg = (
                    "Το αρχείο δεν είναι έγκυρο Excel ή CSV. "
                    "Βεβαιωθείτε ότι το αρχείο δεν είναι κατεστραμμένο ή μερικώς κατεβασμένο. "
                    f"Λάθος: {exc}"
                )
            elif "truncated" in error_msg:
                user_msg = (
                    "Το αρχείο φαίνεται να είναι κατεστραμμένο ή μερικώς κατεβασμένο. "
                    "Δοκιμάστε να κατεβάσετε ξανά το αρχείο."
                )
            else:
                user_msg = f"Σφάλμα κατά την ανάγνωση του αρχείου: {exc}"

            details = (
                f"{user_msg}\n\n"
                f"Λεπτομέρειες:\n"
                f"Path: {repr(file_path)}\n"
                f"Exists: {os.path.exists(file_path)}\n"
                f"Readable: {os.access(file_path, os.R_OK) if os.path.exists(file_path) else 'N/A'}\n"
                f"Size: {os.path.getsize(file_path) if os.path.exists(file_path) else 'N/A'} bytes\n"
                f"Traceback:\n{tb}"
            )
            on_error(details)
            return

        # debug logging removed

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

        # Map common header variants to canonical column names used below
        try:
            df_elem = _map_columns(df_elem)
        except Exception:
            pass

        # Validate all required columns exist (after mapping synonyms)
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
            # debug logging removed
            row_num = (
                idx + 3
            )  # +3 because Excel is 1-indexed, has version row and header row

            # debug logging removed

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

            # The element's `manufacturer` should be derived from the element model when possible.
            # Keep the import template focused on `Model Name` and `Model Manufacturer`.
            breaker_type = (
                str(row.get("Τύπος Διακόπτη", "")).strip()
                if pd.notna(row.get("Τύπος Διακόπτη", ""))
                else ""
            )
            # Ensure maintenance cycle variable exists before any possible use
            maintenance_cycle_int = None
            # Normalize breaker category for CSV
            normalized_breaker_category = None
            try:
                from import_validator import validate_breaker_category

                if breaker_type:
                    match = validate_breaker_category(breaker_type)
                    normalized_breaker_category = (
                        match[0]
                        if match and match[0]
                        else (breaker_type.strip() or None)
                    )
                else:
                    normalized_breaker_category = None
            except Exception:
                normalized_breaker_category = (
                    breaker_type.strip() if breaker_type else None
                )
            # Normalize breaker category for CSV path
            normalized_breaker_category = None
            try:
                from import_validator import validate_breaker_category

                if breaker_type:
                    match = validate_breaker_category(breaker_type)
                    normalized_breaker_category = (
                        match[0]
                        if match and match[0]
                        else (breaker_type.strip() or None)
                    )
                else:
                    normalized_breaker_category = None
            except Exception:
                normalized_breaker_category = (
                    breaker_type.strip() if breaker_type else None
                )
            # Normalize breaker category for CSV path (same logic as Excel import)
            normalized_breaker_category = None
            try:
                from import_validator import validate_breaker_category

                if breaker_type:
                    match = validate_breaker_category(breaker_type)
                    normalized_breaker_category = (
                        match[0]
                        if match and match[0]
                        else (breaker_type.strip() or None)
                    )
                else:
                    normalized_breaker_category = None
            except Exception:
                normalized_breaker_category = (
                    breaker_type.strip() if breaker_type else None
                )
            # Normalize breaker category to canonical values for storage and grouping
            normalized_breaker_category = None
            try:
                from import_validator import validate_breaker_category

                if breaker_type:
                    match = validate_breaker_category(breaker_type)
                    normalized_breaker_category = (
                        match[0]
                        if match and match[0]
                        else (breaker_type.strip() or None)
                    )
                else:
                    normalized_breaker_category = None
            except Exception:
                normalized_breaker_category = (
                    breaker_type.strip() if breaker_type else None
                )
            breaker_role = (
                str(row.get("Breaker Role", "")).strip()
                if pd.notna(row.get("Breaker Role", ""))
                else ""
            )
            # Normalize breaker category for CSV
            normalized_breaker_category = None
            try:
                from import_validator import validate_breaker_category

                if breaker_type:
                    match = validate_breaker_category(breaker_type)
                    normalized_breaker_category = (
                        match[0]
                        if match and match[0]
                        else (breaker_type.strip() or None)
                    )
                else:
                    normalized_breaker_category = None
            except Exception:
                normalized_breaker_category = (
                    breaker_type.strip() if breaker_type else None
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
            model_installation_space = (
                str(row.get("Model Installation Space", "")).strip()
                if pd.notna(row.get("Model Installation Space", ""))
                else ""
            )
            model_installation_space = (
                str(row.get("Model Installation Space", "")).strip()
                if pd.notna(row.get("Model Installation Space", ""))
                else ""
            )
            model_installation_space = (
                str(row.get("Model Installation Space", "")).strip()
                if pd.notna(row.get("Model Installation Space", ""))
                else ""
            )
            model_installation_space = (
                str(row.get("Model Installation Space", "")).strip()
                if pd.notna(row.get("Model Installation Space", ""))
                else ""
            )
            model_installation_space = (
                str(row.get("Model Installation Space", "")).strip()
                if pd.notna(row.get("Model Installation Space", ""))
                else ""
            )
            model_installation_space = (
                str(row.get("Model Installation Space", "")).strip()
                if pd.notna(row.get("Model Installation Space", ""))
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
                    # debug log removed

                    # Fetch substation flag for Thessaloniki (migration-safe)
                    is_thessaloniki = False
                    try:
                        cursor.execute(
                            "SELECT is_thessaloniki FROM substations WHERE id=?",
                            (sub_id,),
                        )
                        thr = cursor.fetchone()
                        is_thessaloniki = bool(thr[0]) if thr and thr[0] else False
                    except Exception:
                        is_thessaloniki = False

                    # Compute maintenance cycle according to rules:
                    # - Transformers and HV breakers: default 6 years, 3 if Thessaloniki
                    # - MV breakers: 'Πτωχού Ελαίου' or 'SF6' => 1 year; 'Κενού' or 'Ελαίου' => 3 years; default 3
                    maintenance_cycle_int = 0
                    elem_type_for_calc = (
                        str(element_type) if pd.notna(element_type) else ""
                    )
                    if (
                        "ΥΤ" in elem_type_for_calc
                        or "150/20" in elem_type_for_calc
                        or "Transformer" in elem_type_for_calc
                    ):
                        maintenance_cycle_int = 3 if is_thessaloniki else 6
                    elif "ΜΤ" in elem_type_for_calc or "20/0.4" in elem_type_for_calc:
                        bt = (breaker_type or "").strip().lower()
                        inst_space = (model_installation_space or "").strip().lower()
                        # MV breakers: SF6 inside -> 1 year, SF6 outside -> 3 years
                        if bt in ["πτωχού ελαίου", "sf6", "sf-6"] or "sf6" in bt:
                            if inst_space and (
                                "εξωτερ" in inst_space or "outside" in inst_space
                            ):
                                maintenance_cycle_int = 3
                            else:
                                maintenance_cycle_int = 1
                        elif bt in ["κενού", "ελαίου"]:
                            maintenance_cycle_int = 3
                        else:
                            maintenance_cycle_int = 3
                    else:
                        # All other element types default to 6 years
                        maintenance_cycle_int = 6
                    name_str = str(name)
                    serial_str = (
                        str(serial_number) if pd.notna(serial_number) else ""
                    ).strip()

                    # Look up element_model_id if model info provided. Use multiple
                    # fallbacks to be robust to existing DB rows.
                    element_model_id = None
                    if model_name:
                        elem_category = (
                            str(element_type) if pd.notna(element_type) else ""
                        )
                        # 1) Try exact match on category+model+manufacturer
                        cursor.execute(
                            "SELECT id FROM element_models WHERE TRIM(element_category)=TRIM(?) AND TRIM(model_name)=TRIM(?) AND TRIM(manufacturer)=TRIM(?)",
                            (elem_category, model_name, model_manufacturer),
                        )
                        model_result = cursor.fetchone()
                        # 2) Try match on category+model only
                        if not model_result:
                            cursor.execute(
                                "SELECT id FROM element_models WHERE TRIM(element_category)=TRIM(?) AND TRIM(model_name)=TRIM(?)",
                                (elem_category, model_name),
                            )
                            model_result = cursor.fetchone()
                        # 3) Try match on model+manufacturer
                        if not model_result and model_manufacturer:
                            cursor.execute(
                                "SELECT id FROM element_models WHERE TRIM(model_name)=TRIM(?) AND TRIM(manufacturer)=TRIM(?)",
                                (model_name, model_manufacturer),
                            )
                            model_result = cursor.fetchone()
                        # 4) Try match on model name only
                        if not model_result:
                            cursor.execute(
                                "SELECT id FROM element_models WHERE TRIM(model_name)=TRIM(?)",
                                (model_name,),
                            )
                            model_result = cursor.fetchone()

                        if model_result:
                            element_model_id = model_result[0]
                        elif model_name:
                            # create model using provided model_manufacturer (may be empty)
                            try:
                                # Detect available columns in element_models and insert accordingly
                                try:
                                    cursor.execute("PRAGMA table_info(element_models)")
                                    em_cols = [r[1] for r in cursor.fetchall()]
                                except Exception:
                                    em_cols = []

                                insert_cols = [
                                    "element_category",
                                    "model_name",
                                    "manufacturer",
                                ]
                                insert_vals = [
                                    elem_category,
                                    model_name,
                                    model_manufacturer or "",
                                ]
                                if "maintenance_cycle" in em_cols:
                                    insert_cols.append("maintenance_cycle")
                                    # Transformer models always use a 6-year model cycle; elements may use 3 when Thessaloniki
                                    try:
                                        is_transformer_model = False
                                        cat = elem_category or ""
                                        if isinstance(cat, str):
                                            is_transformer_model = (
                                                "ΥΤ" in cat
                                                or "150/20" in cat
                                                or "Transformer" in cat
                                                or "Μετασχηματιστής" in cat
                                                or cat.startswith("Μ/Σ")
                                            )
                                    except Exception:
                                        is_transformer_model = False

                                    if is_transformer_model:
                                        insert_vals.append(6)
                                    else:
                                        insert_vals.append(
                                            maintenance_cycle_int
                                            if maintenance_cycle_int
                                            else None
                                        )
                                if "installation_space" in em_cols:
                                    insert_cols.append("installation_space")
                                    insert_vals.append(model_installation_space or "")
                                if "breaker_category" in em_cols:
                                    insert_cols.append("breaker_category")
                                    insert_vals.append(
                                        normalized_breaker_category
                                        if normalized_breaker_category
                                        else None
                                    )
                                # If the element_models table supports a rated-power column,
                                # capture the power value from the imported row and persist it
                                # on the model rather than (or in addition to) the element.
                                power_val = None
                                try:
                                    pv = (
                                        row.get("Rated Power", "")
                                        or row.get("Power", "")
                                        or row.get("Power MVA", "")
                                        or row.get("Ισχύς", "")
                                        or row.get("Ονομαστική Ισχύς", "")
                                    )
                                    if (
                                        pd is not None
                                        and pd.notna(pv)
                                        and str(pv).strip() != ""
                                    ):
                                        power_val = float(
                                            str(pv).strip().replace(",", ".")
                                        )
                                except Exception:
                                    power_val = None
                                if "power_mva" in em_cols:
                                    insert_cols.append("power_mva")
                                    insert_vals.append(power_val)

                                # (debug prints removed)

                                placeholders = ",".join(["?"] * len(insert_cols))
                                sql = f"INSERT INTO element_models ({','.join(insert_cols)}) VALUES ({placeholders})"
                                cursor.execute(sql, tuple(insert_vals))
                                element_model_id = cursor.lastrowid
                            except Exception:
                                element_model_id = None
                        # Debug: show model lookup outcome when running tests
                        # model lookup completed

                    # Look up manufacturer from model if we have an element_model_id
                    manufacturer_value = None
                    if element_model_id:
                        cursor.execute(
                            "SELECT manufacturer FROM element_models WHERE id=?",
                            (element_model_id,),
                        )
                        mrow = cursor.fetchone()
                        if mrow and mrow[0] is not None:
                            manufacturer_value = str(mrow[0]).strip()
                    # If no model manufacturer found, fall back to the provided Model Manufacturer column
                    if not manufacturer_value and model_manufacturer:
                        manufacturer_value = model_manufacturer

                    # Check for duplicate (by substation, name, serial)
                    # debug log removed
                    cursor.execute(
                        "SELECT id FROM elements WHERE substation_id=? AND name=? AND serial_number=?",
                        (sub_id, name_str, serial_str),
                    )
                    existing = cursor.fetchone()

                    # If there's a duplicate but one of the two is inactive, import both
                    # by renaming the inactive one to include the suffix " (Ανενεργός)".
                    decision_replace = False
                    if existing:
                        try:
                            existing_id = existing[0]
                            cursor.execute(
                                "SELECT operating_status, name FROM elements WHERE id=?",
                                (existing_id,),
                            )
                            er = cursor.fetchone()
                            existing_status = er[0] if er and er[0] is not None else ""
                            existing_name_db = (
                                er[1] if er and er[1] is not None else name_str
                            )
                        except Exception:
                            existing_status = ""
                            existing_name_db = name_str

                        # Normalize statuses to Greek form for comparison
                        if existing_status == "Inactive":
                            existing_status = "Ανενεργή"
                        if operating_status == "Inactive":
                            operating_status = "Ανενεργή"

                        # If exactly one of the two is inactive, ensure the inactive one gets the suffix
                        if (existing_status == "Ανενεργή") != (
                            operating_status == "Ανενεργή"
                        ):
                            suffix = " (Ανενεργός)"
                            # If the existing DB row is inactive, rename it and allow insertion
                            if existing_status == "Ανενεργή":
                                new_name = existing_name_db + suffix
                                # avoid collision: increment suffix if needed
                                candidate = new_name
                                i = 1
                                while True:
                                    cursor.execute(
                                        "SELECT id FROM elements WHERE substation_id=? AND name=?",
                                        (sub_id, candidate),
                                    )
                                    if cursor.fetchone():
                                        i += 1
                                        candidate = f"{new_name} {i}"
                                    else:
                                        break
                                cursor.execute(
                                    "UPDATE elements SET name=? WHERE id=?",
                                    (candidate, existing_id),
                                )
                                # treat as no existing so the incoming row will be inserted
                                existing = None
                            else:
                                # existing is active and incoming is inactive: rename incoming
                                base = name_str
                                candidate = base + suffix
                                i = 1
                                while True:
                                    cursor.execute(
                                        "SELECT id FROM elements WHERE substation_id=? AND name=?",
                                        (sub_id, candidate),
                                    )
                                    if cursor.fetchone():
                                        i += 1
                                        candidate = f"{base} {suffix} {i}"
                                    else:
                                        break
                                name_str = candidate
                                # proceed to insert as a distinct element
                                existing = None
                        else:
                            # regular duplicate handling via callback/skip
                            if on_duplicate:
                                decision_replace = bool(
                                    on_duplicate(str(sub_name), name_str, serial_str)
                                )
                            else:
                                decision_replace = False

                    # Normalize element type and determine if element is a main switch
                    elem_type_str = str(element_type) if pd.notna(element_type) else ""
                    is_main_switch = 0
                    # Convert old element types to canonical constants
                    if elem_type_str == "Κεντρικός Διακόπτης ΥΤ":
                        elem_type_str = ELEM_BREAKER_YT
                        is_main_switch = 1
                    elif elem_type_str == "Κεντρικός Διακόπτης ΜΤ":
                        elem_type_str = ELEM_BREAKER_MT
                        is_main_switch = 1
                    elif elem_type_str == "Διακόπτης Φορτίου Γραμμής ΜΤ":
                        elem_type_str = ELEM_BREAKER_MT
                        is_main_switch = 0

                    # Map breaker role to is_main_switch for MV breakers; HV breakers are always main
                    if elem_type_str in [ELEM_BREAKER_YT, ELEM_BREAKER_MT]:
                        # HV breakers are ALWAYS main
                        if elem_type_str == ELEM_BREAKER_YT:
                            is_main_switch = 1
                        else:
                            # MV breakers: map from Breaker Role column
                            if breaker_role == S.get("MESSAGES", {}).get(
                                "BREAKER_ROLE_MAIN", "Κεντρικός"
                            ):
                                is_main_switch = 1
                            elif breaker_role == S.get("MESSAGES", {}).get(
                                "BREAKER_ROLE_INTERCONNECT", "Διασυνδετικός"
                            ):
                                is_main_switch = 2
                            elif breaker_role == S.get("MESSAGES", {}).get(
                                "BREAKER_LABEL_CAPACITOR", "Διακόπτης Πυκνωτών"
                            ):
                                is_main_switch = 3
                            elif breaker_role == S.get("MESSAGES", {}).get(
                                "BREAKER_ROLE_LINE", "Γραμμής"
                            ):
                                is_main_switch = 0
                            else:
                                # Empty or unknown defaults to line breaker
                                is_main_switch = 0

                    # Determine whether the elements table has a maintenance_cycle column
                    try:
                        cursor.execute("PRAGMA table_info(elements)")
                        elem_cols = [r[1] for r in cursor.fetchall()]
                    except Exception:
                        elem_cols = []
                    has_maintenance = "maintenance_cycle" in elem_cols

                    if existing and decision_replace:
                        if has_maintenance:
                            cursor.execute(
                                "UPDATE elements SET element_type=?, maintenance_date=?, voltage_level=?, manufacturer=?, gate=?, is_main_switch=?, breaker_category=?, maintenance_cycle=?, element_model_id=?, operating_status=? WHERE id=?",
                                (
                                    elem_type_str,
                                    (
                                        str(maintenance_date)
                                        if pd.notna(maintenance_date)
                                        else ""
                                    ),
                                    (
                                        str(voltage_level)
                                        if pd.notna(voltage_level)
                                        else ""
                                    ),
                                    (
                                        manufacturer_value
                                        if manufacturer_value is not None
                                        else ""
                                    ),
                                    str(gate) if gate else "",
                                    is_main_switch,
                                    (
                                        normalized_breaker_category
                                        if normalized_breaker_category
                                        else None
                                    ),
                                    maintenance_cycle_int,
                                    element_model_id,
                                    operating_status,
                                    existing[0],
                                ),
                            )
                        else:
                            cursor.execute(
                                "UPDATE elements SET element_type=?, maintenance_date=?, voltage_level=?, manufacturer=?, gate=?, is_main_switch=?, breaker_category=?, element_model_id=?, operating_status=? WHERE id=?",
                                (
                                    elem_type_str,
                                    (
                                        str(maintenance_date)
                                        if pd.notna(maintenance_date)
                                        else ""
                                    ),
                                    (
                                        str(voltage_level)
                                        if pd.notna(voltage_level)
                                        else ""
                                    ),
                                    (
                                        manufacturer_value
                                        if manufacturer_value is not None
                                        else ""
                                    ),
                                    str(gate) if gate else "",
                                    is_main_switch,
                                    (
                                        normalized_breaker_category
                                        if normalized_breaker_category
                                        else None
                                    ),
                                    element_model_id,
                                    operating_status,
                                    existing[0],
                                ),
                            )
                        # update executed
                        updated += 1
                    elif existing and not decision_replace:
                        skipped += 1
                    else:
                        if has_maintenance:
                            # debug log removed
                            cursor.execute(
                                "INSERT INTO elements (substation_id, element_type, name, serial_number, maintenance_date, voltage_level, manufacturer, gate, is_main_switch, breaker_category, maintenance_cycle, element_model_id, operating_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                                    (
                                        str(voltage_level)
                                        if pd.notna(voltage_level)
                                        else ""
                                    ),
                                    (
                                        manufacturer_value
                                        if manufacturer_value is not None
                                        else ""
                                    ),
                                    str(gate) if gate else "",
                                    is_main_switch,
                                    (
                                        normalized_breaker_category
                                        if normalized_breaker_category
                                        else None
                                    ),
                                    maintenance_cycle_int,
                                    element_model_id,
                                    operating_status,
                                ),
                            )
                        else:
                            # debug log removed
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
                                    (
                                        str(voltage_level)
                                        if pd.notna(voltage_level)
                                        else ""
                                    ),
                                    (
                                        manufacturer_value
                                        if manufacturer_value is not None
                                        else ""
                                    ),
                                    str(gate) if gate else "",
                                    is_main_switch,
                                    (
                                        normalized_breaker_category
                                        if normalized_breaker_category
                                        else None
                                    ),
                                    element_model_id,
                                    operating_status,
                                ),
                            )
                        # insert executed
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

    # sanitize incoming file path to guard against stray surrounding quotes
    try:
        if isinstance(file_path, str):
            _qchars = "\"'\u2018\u2019\u201c\u201d\u2032\u2033"
            fp = file_path.strip()
            while fp and fp[0] in _qchars:
                fp = fp[1:]
            while fp and fp[-1] in _qchars:
                fp = fp[:-1]
            file_path = fp
    except Exception:
        pass

    try:
        cursor = conn.cursor()
        # debug log removed
        try:
            df_elem = pd.read_csv(file_path)
        except Exception as exc:
            tb = traceback.format_exc()

            # Provide more specific error messages based on the exception type
            error_msg = str(exc).lower()
            if "file not found" in error_msg or "no such file" in error_msg:
                user_msg = f"Το αρχείο δεν βρέθηκε: {file_path}"
            elif "permission denied" in error_msg:
                user_msg = f"Δεν έχετε δικαίωμα ανάγνωσης του αρχείου: {file_path}"
            elif (
                "unsupported format" in error_msg
                or "not a zip file" in error_msg
                or "expected" in error_msg
            ):
                user_msg = (
                    "Το αρχείο δεν είναι έγκυρο CSV. "
                    "Βεβαιωθείτε ότι το αρχείο δεν είναι κατεστραμμένο ή μερικώς κατεβασμένο. "
                    f"Λάθος: {exc}"
                )
            elif "truncated" in error_msg or "decoding" in error_msg:
                user_msg = (
                    "Το αρχείο φαίνεται να είναι κατεστραμμένο, μερικώς κατεβασμένο ή έχει κακή κωδικοποίηση. "
                    "Δοκιμάστε να κατεβάσετε ξανά το αρχείο ή να το ανοίξετε με Excel και να το σώσετε ως CSV."
                )
            else:
                user_msg = f"Σφάλμα κατά την ανάγνωση του αρχείου: {exc}"

            details = (
                f"{user_msg}\n\n"
                f"Λεπτομέρειες:\n"
                f"Path: {repr(file_path)}\n"
                f"Exists: {os.path.exists(file_path)}\n"
                f"Readable: {os.access(file_path, os.R_OK) if os.path.exists(file_path) else 'N/A'}\n"
                f"Size: {os.path.getsize(file_path) if os.path.exists(file_path) else 'N/A'} bytes\n"
                f"Traceback:\n{tb}"
            )
            on_error(details)
            return

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

            # Do not read per-row `Manufacturer` column; prefer model-derived manufacturer.
            breaker_type = (
                str(row.get("Τύπος Διακόπτη", "")).strip()
                if pd.notna(row.get("Τύπος Διακόπτη", ""))
                else ""
            )
            # Normalize breaker category (CSV) - ensure variable exists for later use
            normalized_breaker_category = None
            try:
                from import_validator import validate_breaker_category

                if breaker_type:
                    match = validate_breaker_category(breaker_type)
                    normalized_breaker_category = (
                        match[0]
                        if match and match[0]
                        else (breaker_type.strip() or None)
                    )
                else:
                    normalized_breaker_category = None
            except Exception:
                normalized_breaker_category = (
                    breaker_type.strip() if breaker_type else None
                )
            breaker_role = (
                str(row.get("Breaker Role", "")).strip()
                if pd.notna(row.get("Breaker Role", ""))
                else ""
            )
            # Ensure maintenance cycle variable exists before any possible use
            maintenance_cycle_int = None
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
                    serial_str = (
                        str(serial_number) if pd.notna(serial_number) else ""
                    ).strip()

                    # Look up element_model_id if model info provided
                    element_model_id = None
                    if model_name:
                        # Simplified lookup: prefer any model matching model_name (tests/databases
                        # may have minimal schema); fall back to creating if missing.
                        try:
                            cursor.execute(
                                "SELECT id FROM element_models WHERE TRIM(model_name)=TRIM(?)",
                                (model_name,),
                            )
                            model_result = cursor.fetchone()
                            # debug log removed
                        except Exception:
                            model_result = None
                        if model_result:
                            element_model_id = model_result[0]
                            # debug log removed
                        else:
                            # create model using provided model_manufacturer (may be empty)
                            try:
                                elem_type_for_model = (
                                    str(element_type) if pd.notna(element_type) else ""
                                )
                                # Detect available columns in element_models and insert accordingly
                                try:
                                    cursor.execute("PRAGMA table_info(element_models)")
                                    em_cols = [r[1] for r in cursor.fetchall()]
                                except Exception:
                                    em_cols = []

                                insert_cols = [
                                    "element_category",
                                    "model_name",
                                    "manufacturer",
                                ]
                                insert_vals = [
                                    elem_type_for_model,
                                    model_name,
                                    model_manufacturer or "",
                                ]
                                if "maintenance_cycle" in em_cols:
                                    insert_cols.append("maintenance_cycle")
                                    # Transformer models always use a 6-year model cycle; elements may use 3 when Thessaloniki
                                    try:
                                        is_transformer_model = False
                                        cat = elem_type_for_model or ""
                                        if isinstance(cat, str):
                                            is_transformer_model = (
                                                "ΥΤ" in cat
                                                or "150/20" in cat
                                                or "Transformer" in cat
                                                or "Μετασχηματιστής" in cat
                                                or cat.startswith("Μ/Σ")
                                            )
                                    except Exception:
                                        is_transformer_model = False

                                    if is_transformer_model:
                                        insert_vals.append(6)
                                    else:
                                        insert_vals.append(
                                            maintenance_cycle_int
                                            if maintenance_cycle_int
                                            else None
                                        )
                                if "installation_space" in em_cols:
                                    insert_cols.append("installation_space")
                                    try:
                                        insert_vals.append(
                                            model_installation_space or ""
                                        )
                                    except NameError:
                                        insert_vals.append(
                                            (
                                                row.get("Model Installation Space", "")
                                                or ""
                                            )
                                        )
                                if "breaker_category" in em_cols:
                                    insert_cols.append("breaker_category")
                                    insert_vals.append(
                                        normalized_breaker_category
                                        if normalized_breaker_category
                                        else None
                                    )

                                # Capture rated power from the CSV/Excel row and store on model if available
                                power_val = None
                                try:
                                    pv = (
                                        row.get("Rated Power", "")
                                        or row.get("Power", "")
                                        or row.get("Power MVA", "")
                                        or row.get("Ισχύς", "")
                                        or row.get("Ονομαστική Ισχύς", "")
                                    )
                                    if (
                                        pd is not None
                                        and pd.notna(pv)
                                        and str(pv).strip() != ""
                                    ):
                                        power_val = float(
                                            str(pv).strip().replace(",", ".")
                                        )
                                except Exception:
                                    power_val = None
                                if "power_mva" in em_cols:
                                    insert_cols.append("power_mva")
                                    insert_vals.append(power_val)

                                # (debug prints removed)

                                placeholders = ",".join(["?"] * len(insert_cols))
                                sql = f"INSERT INTO element_models ({','.join(insert_cols)}) VALUES ({placeholders})"
                                cursor.execute(sql, tuple(insert_vals))
                                element_model_id = cursor.lastrowid
                                # debug log removed
                            except Exception:
                                element_model_id = None

                    # Determine manufacturer for the element: prefer model-derived manufacturer
                    manufacturer_value = None
                    if element_model_id:
                        cursor.execute(
                            "SELECT manufacturer FROM element_models WHERE id=?",
                            (element_model_id,),
                        )
                        mrow = cursor.fetchone()
                        if mrow and mrow[0] is not None:
                            manufacturer_value = str(mrow[0]).strip()
                    # If model didn't provide a manufacturer, fall back to the provided Model Manufacturer
                    if not manufacturer_value and model_manufacturer:
                        manufacturer_value = model_manufacturer

                    # Fetch substation flag for Thessaloniki (migration-safe)
                    is_thessaloniki = False
                    try:
                        cursor.execute(
                            "SELECT is_thessaloniki FROM substations WHERE id=?",
                            (sub_id,),
                        )
                        thr = cursor.fetchone()
                        is_thessaloniki = bool(thr[0]) if thr and thr[0] else False
                    except Exception:
                        is_thessaloniki = False

                    # Compute maintenance cycle according to rules (see importer docs):
                    maintenance_cycle_int = 0
                    elem_type_calc = str(element_type) if pd.notna(element_type) else ""
                    if (
                        "ΥΤ" in elem_type_calc
                        or "150/20" in elem_type_calc
                        or "Transformer" in elem_type_calc
                    ):
                        maintenance_cycle_int = 3 if is_thessaloniki else 6
                    elif "ΜΤ" in elem_type_calc or "20/0.4" in elem_type_calc:
                        bt = (breaker_type or "").strip().lower()
                        try:
                            inst_space = (
                                (model_installation_space or "").strip().lower()
                            )
                        except NameError:
                            inst_space = (
                                (row.get("Model Installation Space", "") or "")
                                .strip()
                                .lower()
                            )
                        # MV breakers: SF6 inside -> 1 year, SF6 outside -> 3 years
                        if bt in ["πτωχού ελαίου", "sf6", "sf-6"] or "sf6" in bt:
                            if inst_space and (
                                "εξωτερ" in inst_space or "outside" in inst_space
                            ):
                                maintenance_cycle_int = 3
                            else:
                                maintenance_cycle_int = 1
                        elif bt in ["κενού", "ελαίου"]:
                            maintenance_cycle_int = 3
                        else:
                            maintenance_cycle_int = 3
                    else:
                        # All other element types default to 6 years
                        maintenance_cycle_int = 6

                    # Check for duplicate (by substation, name, serial)
                    cursor.execute(
                        "SELECT id FROM elements WHERE substation_id=? AND name=? AND serial_number=?",
                        (sub_id, name_str, serial_str),
                    )
                    existing = cursor.fetchone()

                    # If there's a duplicate but one of the two is inactive, import both
                    # by renaming the inactive one to include the suffix " (Ανενεργός)".
                    decision_replace = False
                    if existing:
                        try:
                            existing_id = existing[0]
                            cursor.execute(
                                "SELECT operating_status, name FROM elements WHERE id=?",
                                (existing_id,),
                            )
                            er = cursor.fetchone()
                            existing_status = er[0] if er and er[0] is not None else ""
                            existing_name_db = (
                                er[1] if er and er[1] is not None else name_str
                            )
                        except Exception:
                            existing_status = ""
                            existing_name_db = name_str

                        # Normalize statuses to Greek form for comparison
                        if existing_status == "Inactive":
                            existing_status = "Ανενεργή"
                        if operating_status == "Inactive":
                            operating_status = "Ανενεργή"

                        # If exactly one of the two is inactive, ensure the inactive one gets the suffix
                        if (existing_status == "Ανενεργή") != (
                            operating_status == "Ανενεργή"
                        ):
                            suffix = " (Ανενεργός)"
                            # If the existing DB row is inactive, rename it and allow insertion
                            if existing_status == "Ανενεργή":
                                new_name = existing_name_db + suffix
                                # avoid collision: increment suffix if needed
                                candidate = new_name
                                i = 1
                                while True:
                                    cursor.execute(
                                        "SELECT id FROM elements WHERE substation_id=? AND name=?",
                                        (sub_id, candidate),
                                    )
                                    if cursor.fetchone():
                                        i += 1
                                        candidate = f"{new_name} {i}"
                                    else:
                                        break
                                cursor.execute(
                                    "UPDATE elements SET name=? WHERE id=?",
                                    (candidate, existing_id),
                                )
                                # treat as no existing so the incoming row will be inserted
                                existing = None
                            else:
                                # existing is active and incoming is inactive: rename incoming
                                base = name_str
                                candidate = base + suffix
                                i = 1
                                while True:
                                    cursor.execute(
                                        "SELECT id FROM elements WHERE substation_id=? AND name=?",
                                        (sub_id, candidate),
                                    )
                                    if cursor.fetchone():
                                        i += 1
                                        candidate = f"{base} {suffix} {i}"
                                    else:
                                        break
                                name_str = candidate
                                # proceed to insert as a distinct element
                                existing = None
                                # regular duplicate handling via callback/skip
                                if on_duplicate:
                                    decision_replace = bool(
                                        on_duplicate(
                                            str(sub_name), name_str, serial_str
                                        )
                                    )
                                else:
                                    decision_replace = False

                    # Normalize element type and determine if element is a main switch
                    elem_type_str = str(element_type) if pd.notna(element_type) else ""
                    is_main_switch = 0
                    # Convert old element types to canonical constants
                    if elem_type_str == "Κεντρικός Διακόπτης ΥΤ":
                        elem_type_str = ELEM_BREAKER_YT
                        is_main_switch = 1
                    elif elem_type_str == "Κεντρικός Διακόπτης ΜΤ":
                        elem_type_str = ELEM_BREAKER_MT
                        is_main_switch = 1
                    elif elem_type_str == "Διακόπτης Φορτίου Γραμμής ΜΤ":
                        elem_type_str = ELEM_BREAKER_MT
                        is_main_switch = 0

                    # Map breaker role to is_main_switch for MV breakers; HV breakers are always main
                    if elem_type_str in [ELEM_BREAKER_YT, ELEM_BREAKER_MT]:
                        # HV breakers are ALWAYS main
                        if elem_type_str == ELEM_BREAKER_YT:
                            is_main_switch = 1
                        else:
                            # MV breakers: map from Breaker Role column
                            if breaker_role == S.get("MESSAGES", {}).get(
                                "BREAKER_ROLE_MAIN", "Κεντρικός"
                            ):
                                is_main_switch = 1
                            elif breaker_role == S.get("MESSAGES", {}).get(
                                "BREAKER_ROLE_INTERCONNECT", "Διασυνδετικός"
                            ):
                                is_main_switch = 2
                            elif breaker_role == S.get("MESSAGES", {}).get(
                                "BREAKER_LABEL_CAPACITOR", "Διακόπτης Πυκνωτών"
                            ):
                                is_main_switch = 3
                            elif breaker_role == S.get("MESSAGES", {}).get(
                                "BREAKER_ROLE_LINE", "Γραμμής"
                            ):
                                is_main_switch = 0
                            else:
                                # Empty or unknown defaults to line breaker
                                is_main_switch = 0

                    # Determine whether the elements table has a maintenance_cycle column
                    try:
                        cursor.execute("PRAGMA table_info(elements)")
                        elem_cols = [r[1] for r in cursor.fetchall()]
                    except Exception:
                        elem_cols = []
                    has_maintenance = "maintenance_cycle" in elem_cols

                    if existing and decision_replace:
                        # Determine whether the elements table has a maintenance_cycle column
                        try:
                            cursor.execute("PRAGMA table_info(elements)")
                            elem_cols = [r[1] for r in cursor.fetchall()]
                        except Exception:
                            elem_cols = []
                        has_maintenance = "maintenance_cycle" in elem_cols

                        if has_maintenance:
                            cursor.execute(
                                "UPDATE elements SET element_type=?, maintenance_date=?, voltage_level=?, manufacturer=?, gate=?, is_main_switch=?, breaker_category=?, maintenance_cycle=?, element_model_id=?, operating_status=? WHERE id=?",
                                (
                                    elem_type_str,
                                    (
                                        str(maintenance_date)
                                        if pd.notna(maintenance_date)
                                        else ""
                                    ),
                                    (
                                        str(voltage_level)
                                        if pd.notna(voltage_level)
                                        else ""
                                    ),
                                    (
                                        manufacturer_value
                                        if manufacturer_value is not None
                                        else ""
                                    ),
                                    str(gate) if gate else "",
                                    is_main_switch,
                                    breaker_type if breaker_type else None,
                                    maintenance_cycle_int,
                                    element_model_id,
                                    operating_status,
                                    existing[0],
                                ),
                            )
                        else:
                            cursor.execute(
                                "UPDATE elements SET element_type=?, maintenance_date=?, voltage_level=?, manufacturer=?, gate=?, is_main_switch=?, breaker_category=?, element_model_id=?, operating_status=? WHERE id=?",
                                (
                                    elem_type_str,
                                    (
                                        str(maintenance_date)
                                        if pd.notna(maintenance_date)
                                        else ""
                                    ),
                                    (
                                        str(voltage_level)
                                        if pd.notna(voltage_level)
                                        else ""
                                    ),
                                    (
                                        manufacturer_value
                                        if manufacturer_value is not None
                                        else ""
                                    ),
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
                        try:
                            cursor.execute("PRAGMA table_info(elements)")
                            elem_cols = [r[1] for r in cursor.fetchall()]
                        except Exception:
                            elem_cols = []
                        has_maintenance = "maintenance_cycle" in elem_cols
                        if has_maintenance:
                            params = (
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
                                (
                                    manufacturer_value
                                    if manufacturer_value is not None
                                    else ""
                                ),
                                str(gate) if gate else "",
                                is_main_switch,
                                breaker_type if breaker_type else None,
                                maintenance_cycle_int,
                                element_model_id,
                                operating_status,
                            )
                            # debug log removed
                            cursor.execute(
                                "INSERT INTO elements (substation_id, element_type, name, serial_number, maintenance_date, voltage_level, manufacturer, gate, is_main_switch, breaker_category, maintenance_cycle, element_model_id, operating_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                params,
                            )
                        else:
                            params = (
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
                                (
                                    manufacturer_value
                                    if manufacturer_value is not None
                                    else ""
                                ),
                                str(gate) if gate else "",
                                is_main_switch,
                                breaker_type if breaker_type else None,
                                element_model_id,
                                operating_status,
                            )
                            # debug log removed
                            cursor.execute(
                                "INSERT INTO elements (substation_id, element_type, name, serial_number, maintenance_date, voltage_level, manufacturer, gate, is_main_switch, breaker_category, element_model_id, operating_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                                params,
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
