"""Import validation and mapping utilities for handling mismatched columns and values."""

from typing import Dict, List, Tuple, Optional
from difflib import SequenceMatcher

try:
    import pandas as pd
except ImportError:
    pd = None


# Expected column mappings (internal name -> display names)
COLUMN_MAPPINGS = {
    "Substation Name": [
        "Substation Name",
        "Substation",
        "Υποσταθμός",
        "Όνομα Υποσταθμού",
        "Station",
    ],
    "Element Type": ["Element Type", "Type", "Τύπος", "Τύπος Στοιχείου", "Element"],
    "Name": ["Name", "Όνομα", "Element Name", "Όνομα Στοιχείου"],
    "Serial Number": ["Serial Number", "Serial", "SN", "Σειριακός Αριθμός", "S/N"],
    "Gate": ["Gate", "Πύλη"],
    "Operating Status": [
        "Operating Status",
        "Status",
        "Κατάσταση",
        "Κατάσταση Λειτουργίας",
    ],
    "Maintenance Date": [
        "Maintenance Date",
        "Date",
        "Ημερομηνία",
        "Ημερομηνία Συντήρησης",
        "Maint Date",
    ],
    "Model Name": ["Model Name", "Model", "Μοντέλο", "Όνομα Μοντέλου"],
    "Model Manufacturer": [
        "Model Manufacturer",
        "Model Mfg",
        "Κατασκευαστής Μοντέλου",
        "Manufacturer",
    ],
    "Model Installation Space": [
        "Model Installation Space",
        "Installation Space",
        "Χώρος Εγκατάστασης",
        "Space",
    ],
    "Model Maintenance Cycle": [
        "Model Maintenance Cycle",
        "Model Cycle",
        "Κύκλος Μοντέλου",
    ],
    "Breaker Role": ["Breaker Role", "Role", "Ρόλος", "Ρόλος Διακόπτη"],
    "Τύπος Διακόπτη": [
        "Τύπος Διακόπτη",
        "Breaker Type",
        "Category",
        "Κατηγορία",
        "Breaker Category",
    ],
}

# Expected values for element types
ELEMENT_TYPE_MAPPINGS = {
    "Μετασχηματιστής 150/20KV": [
        "Μετασχηματιστής 150/20KV",
        "Μετασχηματιστής",
        "Transformer 150/20",
        "Transformer",
    ],
    "Μετασχηματιστής 20/0.4KV": [
        "Μετασχηματιστής 20/0.4KV",
        "Μετασχηματιστής 20/0.4",
        "Transformer 20/0.4",
    ],
    "Διακόπτης ΥΤ": [
        "Διακόπτης ΥΤ",
        "Κεντρικός Διακόπτης ΥΤ",
        "HV Breaker",
        "HV Circuit Breaker",
    ],
    "Διακόπτης ΜΤ": [
        "Διακόπτης ΜΤ",
        "Κεντρικός Διακόπτης ΜΤ",
        "Διακόπτης Φορτίου Γραμμής ΜΤ",
        "MV Breaker",
        "MV Circuit Breaker",
    ],
    "Αποζεύκτης ΥΤ": ["Αποζεύκτης ΥΤ", "HV Disconnector", "Disconnector HV"],
    "Αποζεύκτης ΜΤ": ["Αποζεύκτης ΜΤ", "MV Disconnector", "Disconnector MV"],
    "Αλεξικέραυνο ΥΤ": ["Αλεξικέραυνο ΥΤ", "Surge Arrester HV", "HV Arrester"],
    "Αλεξικέραυνο ΜΤ": ["Αλεξικέραυνο ΜΤ", "Surge Arrester MV", "MV Arrester"],
}

# Expected values for operating status
OPERATING_STATUS_MAPPINGS = {
    "Ενεργή": ["Ενεργή", "Active", "Ενεργός", "Ενεργό", "Λειτουργία", "Operational"],
    "Ανενεργή": [
        "Ανενεργή",
        "Inactive",
        "Ανενεργός",
        "Ανενεργό",
        "Εκτός Λειτουργίας",
        "Out of Service",
    ],
}

# Expected values for breaker roles
BREAKER_ROLE_MAPPINGS = {
    "Κεντρικός": ["Κεντρικός", "Central", "Main", "Κεντρικός Διακόπτης"],
    "Γραμμής": ["Γραμμής", "Line", "Feeder", "Line Breaker"],
    "Διασυνδετικός": ["Διασυνδετικός", "Tie", "Bus Coupler", "Interconnection"],
    "Διακόπτης Πυκνωτών": [
        "Διακόπτης Πυκνωτών",
        "Capacitor",
        "Capacitor Breaker",
        "Cap Bank",
    ],
}

# Expected values for breaker categories
BREAKER_CATEGORY_MAPPINGS = {
    "SF6": ["SF6", "SF 6", "Hexafluoride"],
    "Κενού": ["Κενού", "Vacuum", "VAC"],
    "Πτωχού Ελαίου": ["Πτωχού Ελαίου", "Minimum Oil", "Low Oil"],
    "Ελαίου": ["Ελαίου", "Oil"],
}


def similarity_ratio(str1: str, str2: str) -> float:
    """Calculate similarity between two strings (0.0 to 1.0)."""
    return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()


def find_best_match(
    value: str, mapping_dict: Dict[str, List[str]], threshold: float = 0.6
) -> Optional[Tuple[str, float, List[str]]]:
    """
    Find best match for a value in a mapping dictionary.

    Returns:
        Tuple of (canonical_value, confidence, alternative_suggestions) or None if no good match
    """
    if not value or pd.isna(value):
        return None

    value_clean = str(value).strip()
    best_match = None
    best_score = 0.0
    alternatives = []

    for canonical, variants in mapping_dict.items():
        for variant in variants:
            score = similarity_ratio(value_clean, variant)
            if score > best_score:
                best_score = score
                best_match = canonical

        # Collect good alternatives
        if best_score >= threshold and best_score < 0.95:
            alternatives.append((canonical, best_score))

    if best_score >= threshold:
        # Sort alternatives by score
        alternatives.sort(key=lambda x: x[1], reverse=True)
        alt_names = [alt[0] for alt in alternatives[:3]]  # Top 3
        return (best_match, best_score, alt_names)

    return None


def detect_column_mismatches(df_columns: List[str]) -> Dict[str, any]:
    """
    Detect mismatched columns in imported data.

    Returns:
        {
            'matched': {imported_col: canonical_col},
            'unmatched_import': [col1, col2, ...],  # Columns in import that don't match
            'unmatched_required': [col1, col2, ...],  # Required columns not found
            'suggestions': {unmatched_col: [(canonical, score), ...]}
        }
    """
    matched = {}
    unmatched_import = []
    unmatched_required = list(COLUMN_MAPPINGS.keys())
    suggestions = {}

    for import_col in df_columns:
        found = False
        import_col_clean = str(import_col).strip()

        # Try exact match first
        for canonical, variants in COLUMN_MAPPINGS.items():
            if import_col_clean in variants:
                matched[import_col_clean] = canonical
                if canonical in unmatched_required:
                    unmatched_required.remove(canonical)
                found = True
                break

        if not found:
            # Try fuzzy match
            best_matches = []
            for canonical in COLUMN_MAPPINGS.keys():
                score = similarity_ratio(import_col_clean, canonical)
                if score >= 0.5:  # Lower threshold for suggestions
                    best_matches.append((canonical, score))

            if best_matches:
                best_matches.sort(key=lambda x: x[1], reverse=True)
                suggestions[import_col_clean] = best_matches[:3]
                unmatched_import.append(import_col_clean)
            else:
                unmatched_import.append(import_col_clean)

    return {
        "matched": matched,
        "unmatched_import": unmatched_import,
        "unmatched_required": unmatched_required,
        "suggestions": suggestions,
    }


def validate_element_type(value: str) -> Tuple[Optional[str], float, List[str]]:
    """Validate and suggest corrections for element type."""
    result = find_best_match(value, ELEMENT_TYPE_MAPPINGS)
    if result:
        return result
    return (None, 0.0, [])


def validate_operating_status(value: str) -> Tuple[Optional[str], float, List[str]]:
    """Validate and suggest corrections for operating status."""
    result = find_best_match(value, OPERATING_STATUS_MAPPINGS)
    if result:
        return result
    return (None, 0.0, [])


def validate_breaker_role(value: str) -> Tuple[Optional[str], float, List[str]]:
    """Validate and suggest corrections for breaker role."""
    result = find_best_match(value, BREAKER_ROLE_MAPPINGS)
    if result:
        return result
    return (None, 0.0, [])


def validate_breaker_category(value: str) -> Tuple[Optional[str], float, List[str]]:
    """Validate and suggest corrections for breaker category."""
    result = find_best_match(value, BREAKER_CATEGORY_MAPPINGS)
    if result:
        return result
    return (None, 0.0, [])


def analyze_import_data(df, column_mapping: Dict, conn) -> Dict:
    """
    Analyze import data for validation issues.

    Args:
        df: pandas DataFrame with imported data
        column_mapping: Dict mapping import columns to canonical columns
        conn: Database connection for checking existing data

    Returns:
        {
            'total_rows': int,
            'valid_rows': int,
            'issues': [
                {
                    'row': int,
                    'column': str,
                    'value': str,
                    'issue_type': str,  # 'invalid_value', 'missing_required', 'fuzzy_match'
                    'suggested_value': str,
                    'confidence': float,
                    'alternatives': [str, ...]
                },
                ...
            ],
            'new_substations': [str, ...],
            'existing_substations': {sub_name: count, ...},
            'new_models': [{category, name, manufacturer}, ...],
            'existing_models': {(category, name, manufacturer): count, ...}
        }
    """
    issues = []
    new_substations = set()
    existing_substations = {}
    new_models_dict = {}
    existing_models = {}

    # Get database cursor
    cursor = conn.cursor()

    # Cache substations
    cursor.execute("SELECT name FROM substations")
    db_substations = {row[0] for row in cursor.fetchall()}

    # Cache models
    cursor.execute(
        "SELECT element_category, model_name, manufacturer FROM element_models"
    )
    db_models = {(row[0], row[1], row[2]) for row in cursor.fetchall()}

    # Create reverse mapping
    reverse_mapping = {v: k for k, v in column_mapping.items()}

    # Get canonical column names
    def get_value(row, canonical_col):
        import_col = reverse_mapping.get(canonical_col)
        if import_col and import_col in df.columns:
            val = row.get(import_col)
            return str(val).strip() if pd.notna(val) and str(val).strip() else None
        return None

    valid_rows = 0

    # Define required fields
    REQUIRED_FIELDS = [
        "Substation Name",
        "Element Type",
        "Name",
        "Serial Number",
        "Gate",
        "Operating Status",
    ]

    for idx, row in df.iterrows():
        row_num = idx + 3  # Excel row number
        row_valid = True

        # Check for missing required fields first
        for required_field in REQUIRED_FIELDS:
            value = get_value(row, required_field)
            if not value:
                issues.append(
                    {
                        "row": row_num,
                        "column": required_field,
                        "value": "",
                        "issue_type": "missing_required",
                        "suggested_value": None,
                        "confidence": 0.0,
                        "alternatives": [],
                    }
                )
                row_valid = False

        # Check substation
        sub_name = get_value(row, "Substation Name")
        if sub_name:
            if sub_name in db_substations:
                existing_substations[sub_name] = (
                    existing_substations.get(sub_name, 0) + 1
                )
            else:
                new_substations.add(sub_name)

        # Check element type
        elem_type = get_value(row, "Element Type")
        if elem_type:
            canonical, confidence, alternatives = validate_element_type(elem_type)
            if canonical and confidence < 0.95:
                issues.append(
                    {
                        "row": row_num,
                        "column": "Element Type",
                        "value": elem_type,
                        "issue_type": "fuzzy_match",
                        "suggested_value": canonical,
                        "confidence": confidence,
                        "alternatives": alternatives,
                    }
                )
                row_valid = False
            elif not canonical:
                issues.append(
                    {
                        "row": row_num,
                        "column": "Element Type",
                        "value": elem_type,
                        "issue_type": "invalid_value",
                        "suggested_value": None,
                        "confidence": 0.0,
                        "alternatives": list(ELEMENT_TYPE_MAPPINGS.keys())[:5],
                    }
                )
                row_valid = False

        # Check model
        model_name = get_value(row, "Model Name")
        model_manufacturer = get_value(row, "Model Manufacturer")
        if model_name and elem_type:
            model_key = (elem_type, model_name, model_manufacturer or "")
            if model_key in db_models:
                existing_models[model_key] = existing_models.get(model_key, 0) + 1
            else:
                new_models_dict[model_key] = {
                    "category": elem_type,
                    "name": model_name,
                    "manufacturer": model_manufacturer or "",
                }

        # Check operating status
        op_status = get_value(row, "Operating Status")
        if op_status:
            canonical, confidence, alternatives = validate_operating_status(op_status)
            if canonical and confidence < 0.95:
                issues.append(
                    {
                        "row": row_num,
                        "column": "Operating Status",
                        "value": op_status,
                        "issue_type": "fuzzy_match",
                        "suggested_value": canonical,
                        "confidence": confidence,
                        "alternatives": alternatives,
                    }
                )
            elif not canonical:
                issues.append(
                    {
                        "row": row_num,
                        "column": "Operating Status",
                        "value": op_status,
                        "issue_type": "invalid_value",
                        "suggested_value": None,
                        "confidence": 0.0,
                        "alternatives": list(OPERATING_STATUS_MAPPINGS.keys()),
                    }
                )
                row_valid = False

        # Check breaker role (if applicable)
        breaker_role = get_value(row, "Breaker Role")
        if breaker_role and elem_type and "Διακόπτης" in str(elem_type):
            canonical, confidence, alternatives = validate_breaker_role(breaker_role)
            if canonical and confidence < 0.95:
                issues.append(
                    {
                        "row": row_num,
                        "column": "Breaker Role",
                        "value": breaker_role,
                        "issue_type": "fuzzy_match",
                        "suggested_value": canonical,
                        "confidence": confidence,
                        "alternatives": alternatives,
                    }
                )
            elif not canonical:
                issues.append(
                    {
                        "row": row_num,
                        "column": "Breaker Role",
                        "value": breaker_role,
                        "issue_type": "invalid_value",
                        "suggested_value": None,
                        "confidence": 0.0,
                        "alternatives": list(BREAKER_ROLE_MAPPINGS.keys()),
                    }
                )
                row_valid = False

        # Check breaker category
        breaker_cat = get_value(row, "Τύπος Διακόπτη")
        if breaker_cat and elem_type and "Διακόπτης" in str(elem_type):
            canonical, confidence, alternatives = validate_breaker_category(breaker_cat)
            allowed_by_type = {
                "Διακόπτης ΥΤ": ["SF6", "Κενού", "Ελαίου"],
                "Διακόπτης ΜΤ": ["SF6", "Κενού", "Πτωχού Ελαίου", "Ελαίου"],
            }
            allowed_categories = allowed_by_type.get(
                str(elem_type), list(BREAKER_CATEGORY_MAPPINGS.keys())
            )

            if not canonical:
                issues.append(
                    {
                        "row": row_num,
                        "column": "Τύπος Διακόπτη",
                        "value": breaker_cat,
                        "issue_type": "invalid_value",
                        "suggested_value": None,
                        "confidence": 0.0,
                        "alternatives": allowed_categories,
                    }
                )
                row_valid = False
            else:
                if canonical not in allowed_categories:
                    suggested = (
                        "Ελαίου"
                        if (
                            canonical == "Πτωχού Ελαίου"
                            and str(elem_type) == "Διακόπτης ΥΤ"
                        )
                        else None
                    )
                    issues.append(
                        {
                            "row": row_num,
                            "column": "Τύπος Διακόπτη",
                            "value": breaker_cat,
                            "issue_type": "invalid_value",
                            "suggested_value": suggested,
                            "confidence": confidence,
                            "alternatives": allowed_categories,
                        }
                    )
                    row_valid = False
                elif confidence < 0.95:
                    issues.append(
                        {
                            "row": row_num,
                            "column": "Τύπος Διακόπτη",
                            "value": breaker_cat,
                            "issue_type": "fuzzy_match",
                            "suggested_value": canonical,
                            "confidence": confidence,
                            "alternatives": alternatives,
                        }
                    )

        if row_valid:
            valid_rows += 1

    return {
        "total_rows": len(df),
        "valid_rows": valid_rows,
        "issues": issues,
        "new_substations": sorted(list(new_substations)),
        "existing_substations": existing_substations,
        "new_models": list(new_models_dict.values()),
        "existing_models": existing_models,
    }
