"""Database integrity checker to validate structure and data consistency.

This module performs comprehensive checks when loading a database to detect:
- SQLite file corruption
- Missing or invalid schema
- Orphaned records (foreign key violations)
- Invalid data in critical fields
- Inconsistent state (e.g., null values in required fields)
"""

import re
import sqlite3
from typing import List


class IntegrityCheckResult:
    """Result of database integrity check."""

    def __init__(self):
        self.passed = True
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []

    def add_error(self, message: str):
        """Add a critical error (database cannot be used safely)."""
        self.errors.append(message)
        self.passed = False

    def add_warning(self, message: str):
        """Add a warning (database usable but has issues)."""
        self.warnings.append(message)

    def add_info(self, message: str):
        """Add informational message."""
        self.info.append(message)

    def get_summary(self) -> str:
        """Get human-readable summary of check results."""
        lines = []

        if self.errors:
            lines.append(f"❌ ERRORS ({len(self.errors)}):")
            for err in self.errors:
                lines.append(f"  • {err}")

        if self.warnings:
            lines.append(f"⚠️  WARNINGS ({len(self.warnings)}):")
            for warn in self.warnings:
                lines.append(f"  • {warn}")

        if self.info:
            lines.append(f"ℹ️  INFO ({len(self.info)}):")
            for info in self.info:
                lines.append(f"  • {info}")

        if self.passed and not self.warnings:
            lines.append("✓ Database integrity check passed")

        return "\n".join(lines)


def check_database_integrity(
    db_path: str, quick_check: bool = False
) -> IntegrityCheckResult:
    """Perform comprehensive database integrity checks.

    Args:
        db_path: Path to SQLite database file
        quick_check: If True, perform only essential fast checks

    Returns:
        IntegrityCheckResult with status and details
    """
    result = IntegrityCheckResult()

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 1. SQLite integrity check (built-in)
        _check_sqlite_integrity(conn, cursor, result)

        # 2. Schema validation (required tables exist)
        if not _check_schema(cursor, result):
            # If schema is broken, don't continue with data checks
            conn.close()
            return result

        if not quick_check:
            # 3. Foreign key constraint validation
            _check_foreign_keys(cursor, result)

            # 4. Required field validation
            _check_required_fields(cursor, result)

            # 5. Data consistency checks
            _check_data_consistency(cursor, result)

            # 6. Orphaned records check
            _check_orphaned_records(cursor, result)

        conn.close()

    except sqlite3.DatabaseError as e:
        result.add_error(f"Database file is corrupted or invalid: {e}")
    except Exception as e:
        result.add_error(f"Unexpected error during integrity check: {e}")

    return result


def _check_sqlite_integrity(
    conn: sqlite3.Connection, cursor: sqlite3.Cursor, result: IntegrityCheckResult
):
    """Check SQLite's built-in integrity check."""
    try:
        integrity_errors = _collect_integrity_errors(cursor)

        if not integrity_errors:
            result.add_info("SQLite integrity check passed")
            return

        repaired_indexes = _attempt_index_auto_repair(conn, cursor, integrity_errors)
        if repaired_indexes:
            result.add_warning(
                "SQLite index corruption was repaired automatically: "
                + ", ".join(repaired_indexes)
            )
            result.add_info("SQLite integrity check passed after automatic repair")
            return

        result.add_error(f"SQLite integrity check failed: {integrity_errors[0]}")
    except sqlite3.DatabaseError as e:
        repaired_objects = _attempt_malformed_db_repair(conn, cursor, e)
        if repaired_objects:
            result.add_warning(
                "SQLite malformed database condition was repaired automatically: "
                + ", ".join(repaired_objects)
            )
            result.add_info("SQLite integrity check passed after automatic repair")
            return
        result.add_error(f"Could not perform SQLite integrity check: {e}")
    except Exception as e:
        result.add_error(f"Could not perform SQLite integrity check: {e}")


def _collect_integrity_errors(cursor: sqlite3.Cursor) -> List[str]:
    cursor.execute("PRAGMA integrity_check")
    return [row[0] for row in cursor.fetchall() if row and row[0] and row[0] != "ok"]


def _attempt_index_auto_repair(
    conn: sqlite3.Connection, cursor: sqlite3.Cursor, integrity_errors: List[str]
) -> List[str]:
    index_names = _extract_repairable_index_names(integrity_errors)
    if not index_names:
        return []

    try:
        cursor.execute("REINDEX")
        conn.commit()
        if not _collect_integrity_errors(cursor):
            return index_names
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass

    recreated_indexes = []
    for index_name in index_names:
        create_sql = _get_index_create_sql(cursor, index_name)
        if not create_sql:
            continue
        try:
            cursor.execute(f"DROP INDEX IF EXISTS {_quote_identifier(index_name)}")
            cursor.execute(create_sql)
            recreated_indexes.append(index_name)
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            return []

    if not recreated_indexes:
        return []

    try:
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return []

    if not _collect_integrity_errors(cursor):
        return recreated_indexes

    return []


def _attempt_malformed_db_repair(
    conn: sqlite3.Connection, cursor: sqlite3.Cursor, error: Exception
) -> List[str]:
    error_text = str(error).lower()
    if "malformed" not in error_text and "disk image is malformed" not in error_text:
        return []

    try:
        cursor.execute("REINDEX")
        conn.commit()
        if not _collect_integrity_errors(cursor):
            return ["REINDEX"]
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass

    recreated_indexes = _recreate_all_user_indexes(conn, cursor)
    if not recreated_indexes:
        return []

    try:
        if not _collect_integrity_errors(cursor):
            return recreated_indexes
    except Exception:
        return []

    return []


def _recreate_all_user_indexes(
    conn: sqlite3.Connection, cursor: sqlite3.Cursor
) -> List[str]:
    index_definitions = _get_recreatable_indexes(cursor)
    if not index_definitions:
        return []

    recreated_indexes = []
    for index_name, create_sql in index_definitions:
        try:
            cursor.execute(f"DROP INDEX IF EXISTS {_quote_identifier(index_name)}")
            cursor.execute(create_sql)
            recreated_indexes.append(index_name)
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            return []

    try:
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return []

    return recreated_indexes


def _get_recreatable_indexes(cursor: sqlite3.Cursor) -> List[tuple[str, str]]:
    cursor.execute(
        """
        SELECT name, sql
        FROM sqlite_master
        WHERE type='index'
          AND sql IS NOT NULL
        ORDER BY name
        """
    )
    return [
        (row[0], row[1])
        for row in cursor.fetchall()
        if row and len(row) >= 2 and row[0] and row[1]
    ]


def _extract_repairable_index_names(integrity_errors: List[str]) -> List[str]:
    index_names = []
    patterns = (
        r"wrong # of entries in index (?P<name>\S+)",
        r"row \d+ missing from index (?P<name>\S+)",
        r"UNIQUE constraint error in (?P<name>\S+)",
    )

    for error in integrity_errors:
        matched_name = None
        for pattern in patterns:
            match = re.search(pattern, error)
            if match:
                matched_name = match.group("name")
                break
        if not matched_name:
            return []
        if matched_name not in index_names:
            index_names.append(matched_name)

    return index_names


def _get_index_create_sql(cursor: sqlite3.Cursor, index_name: str) -> str:
    cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (index_name,)
    )
    row = cursor.fetchone()
    if not row:
        return ""
    return row[0] or ""


def _quote_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _check_schema(cursor: sqlite3.Cursor, result: IntegrityCheckResult) -> bool:
    """Verify that all required tables exist with expected columns.

    Returns:
        True if schema is valid, False otherwise
    """
    required_tables = {
        "substations": ["id", "name"],
        "elements": ["id", "substation_id", "element_type", "name"],
        "maintenance": ["id", "substation_id", "date_time"],
        "maintenance_elements": ["id", "maintenance_id", "element_id"],
        "people": ["id", "name", "role"],
        "maintenance_people": ["id", "maintenance_id", "person_id", "role"],
        "inspections": ["id", "substation_id", "inspection_date"],
        "element_models": ["id", "element_category", "model_name"],
    }

    schema_valid = True

    # Check if tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = {row[0] for row in cursor.fetchall()}

    for table_name, required_columns in required_tables.items():
        if table_name not in existing_tables:
            result.add_error(f"Required table '{table_name}' is missing")
            schema_valid = False
            continue

        # Check if required columns exist
        cursor.execute(f"PRAGMA table_info({table_name})")
        existing_columns = {row[1] for row in cursor.fetchall()}

        for col in required_columns:
            if col not in existing_columns:
                result.add_error(
                    f"Required column '{col}' is missing from table '{table_name}'"
                )
                schema_valid = False

    if schema_valid:
        result.add_info(f"Schema validation passed ({len(required_tables)} tables)")

    return schema_valid


def _check_foreign_keys(cursor: sqlite3.Cursor, result: IntegrityCheckResult):
    """Check for foreign key constraint violations."""
    # Enable foreign key checks temporarily
    cursor.execute("PRAGMA foreign_keys = ON")

    # Check for violations
    cursor.execute("PRAGMA foreign_key_check")
    violations = cursor.fetchall()

    if violations:
        for violation in violations[:10]:  # Limit to first 10
            table, rowid, parent, fkid = violation
            result.add_error(
                f"Foreign key violation in table '{table}', row {rowid}: "
                f"references non-existent row in '{parent}'"
            )

        if len(violations) > 10:
            result.add_error(
                f"... and {len(violations) - 10} more foreign key violations"
            )
    else:
        result.add_info("Foreign key constraints are valid")


def _check_required_fields(cursor: sqlite3.Cursor, result: IntegrityCheckResult):
    """Check that required fields have valid values (not NULL or empty)."""
    checks = [
        ("substations", "name", "Substation name"),
        ("elements", "substation_id", "Element substation ID"),
        ("elements", "element_type", "Element type"),
        ("elements", "name", "Element name"),
        ("maintenance", "substation_id", "Maintenance substation ID"),
        ("maintenance", "date_time", "Maintenance date/time"),
        ("people", "name", "Person name"),
        ("people", "role", "Person role"),
    ]

    for table, column, field_name in checks:
        try:
            # Check for NULL values
            cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} IS NULL")
            null_count = cursor.fetchone()[0]

            if null_count > 0:
                result.add_warning(
                    f"{null_count} records in '{table}' have NULL {field_name}"
                )

            # Check for empty strings (for text fields)
            if column != "substation_id" and "id" not in column:
                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} = ''")
                empty_count = cursor.fetchone()[0]

                if empty_count > 0:
                    result.add_warning(
                        f"{empty_count} records in '{table}' have empty {field_name}"
                    )

        except Exception as e:
            result.add_warning(
                f"Could not check required field '{column}' in '{table}': {e}"
            )


def _check_data_consistency(cursor: sqlite3.Cursor, result: IntegrityCheckResult):
    """Check for data consistency issues."""

    # Check for circuit breakers without breaker_category
    try:
        cursor.execute("""
            SELECT COUNT(*) FROM elements 
            WHERE element_type IN ('Διακόπτης ΥΤ', 'Διακόπτης ΜΤ')
            AND (breaker_category IS NULL OR TRIM(breaker_category) = '')
        """)
        invalid_breakers = cursor.fetchone()[0]

        if invalid_breakers > 0:
            result.add_warning(
                f"{invalid_breakers} circuit breakers are missing breaker_category "
                "(should be SF6, Ελαίου, Πτωχού Ελαίου, or Κενού)"
            )
    except Exception:
        pass

    # Check for future dates in maintenance records
    try:
        cursor.execute("""
            SELECT COUNT(*) FROM maintenance 
            WHERE date_time > datetime('now', '+1 day')
        """)
        future_dates = cursor.fetchone()[0]

        if future_dates > 0:
            result.add_warning(f"{future_dates} maintenance records have future dates")
    except Exception:
        pass

    # Check for maintenance without elements
    try:
        cursor.execute("""
            SELECT COUNT(*) FROM maintenance m
            WHERE NOT EXISTS (
                SELECT 1 FROM maintenance_elements me 
                WHERE me.maintenance_id = m.id
            )
        """)
        maint_no_elements = cursor.fetchone()[0]

        if maint_no_elements > 0:
            result.add_warning(
                f"{maint_no_elements} maintenance records have no associated elements"
            )
    except Exception:
        pass


def _check_orphaned_records(cursor: sqlite3.Cursor, result: IntegrityCheckResult):
    """Check for orphaned records (referencing non-existent parents)."""

    # Check for elements referencing non-existent substations
    try:
        cursor.execute("""
            SELECT COUNT(*) FROM elements e
            WHERE NOT EXISTS (SELECT 1 FROM substations s WHERE s.id = e.substation_id)
        """)
        orphaned_elements = cursor.fetchone()[0]

        if orphaned_elements > 0:
            result.add_error(
                f"{orphaned_elements} elements reference non-existent substations"
            )
    except Exception:
        pass

    # Check for maintenance_elements referencing non-existent maintenance
    try:
        cursor.execute("""
            SELECT COUNT(*) FROM maintenance_elements me
            WHERE NOT EXISTS (SELECT 1 FROM maintenance m WHERE m.id = me.maintenance_id)
        """)
        orphaned_maint_elem = cursor.fetchone()[0]

        if orphaned_maint_elem > 0:
            result.add_error(
                f"{orphaned_maint_elem} maintenance_elements reference non-existent maintenance"
            )
    except Exception:
        pass

    # Check for maintenance_elements referencing non-existent elements
    try:
        cursor.execute("""
            SELECT COUNT(*) FROM maintenance_elements me
            WHERE NOT EXISTS (SELECT 1 FROM elements e WHERE e.id = me.element_id)
        """)
        orphaned_maint_elem2 = cursor.fetchone()[0]

        if orphaned_maint_elem2 > 0:
            result.add_error(
                f"{orphaned_maint_elem2} maintenance_elements reference non-existent elements"
            )
    except Exception:
        pass
