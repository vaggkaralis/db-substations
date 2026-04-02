"""Tests for database integrity checker."""

import os
import sqlite3
import tempfile
from unittest.mock import Mock

from db_integrity import (
    _attempt_index_auto_repair,
    _attempt_malformed_db_repair,
    _extract_repairable_index_names,
    _recreate_all_user_indexes,
    check_database_integrity,
)
from database import init_db


def test_integrity_check_valid_db():
    """Test that a valid database passes integrity check."""
    # Create a temporary valid database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Initialize a proper database
        conn = init_db(tmp_path)
        conn.close()

        # Run integrity check
        result = check_database_integrity(tmp_path, quick_check=True)

        assert result.passed, "Valid database should pass integrity check"
        assert len(result.errors) == 0, "Valid database should have no errors"

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def test_integrity_check_corrupted_db():
    """Test that a corrupted database is detected."""
    # Create a temporary file with invalid SQLite content
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp.write(b"This is not a valid SQLite database file")
        tmp_path = tmp.name

    try:
        # Run integrity check
        result = check_database_integrity(tmp_path, quick_check=True)

        assert not result.passed, "Corrupted database should fail integrity check"
        assert len(result.errors) > 0, "Corrupted database should have errors"

    finally:
        # Give Windows time to release the file
        import time

        time.sleep(0.1)
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except PermissionError:
            pass  # File still locked on Windows, ignore


def test_integrity_check_missing_table():
    """Test that missing required tables are detected."""
    # Create a database with missing tables
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        conn = sqlite3.connect(tmp_path)
        cursor = conn.cursor()

        # Create only substations table, missing others
        cursor.execute("CREATE TABLE substations (id INTEGER PRIMARY KEY, name TEXT)")
        conn.commit()
        conn.close()

        # Run integrity check (full check to test schema validation)
        result = check_database_integrity(tmp_path, quick_check=False)

        assert not result.passed, "Database with missing tables should fail"
        assert any("missing" in err.lower() for err in result.errors), (
            "Should report missing tables"
        )

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def test_integrity_check_orphaned_elements():
    """Test that orphaned elements are detected.

    Orphaned elements reference non-existent substations.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Initialize proper database
        conn = init_db(tmp_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = OFF")

        # Seed a legacy-corrupt orphan row that bypasses the runtime FK guard.
        cursor.execute(
            """
            INSERT INTO elements (substation_id, element_type, name)
            VALUES (99999, 'Test Type', 'Test Element')
            """
        )
        conn.commit()
        cursor.execute("PRAGMA foreign_keys = ON")
        conn.close()

        # Run full integrity check
        result = check_database_integrity(tmp_path, quick_check=False)

        assert not result.passed, "Database with orphaned elements should fail"
        assert any(
            "orphan" in err.lower() or "non-existent" in err.lower()
            for err in result.errors
        ), "Should report orphaned elements"

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def test_integrity_check_invalid_breaker_category():
    """Test that circuit breakers without category are flagged."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        # Initialize proper database
        conn = init_db(tmp_path)
        cursor = conn.cursor()

        # Add a substation
        cursor.execute("INSERT INTO substations (name) VALUES ('Test Sub')")
        sub_id = cursor.lastrowid

        # Disable CHECK constraints temporarily to insert invalid data
        # (we want to test if the integrity checker can detect this issue)
        cursor.execute("PRAGMA ignore_check_constraints = ON")

        # Add a circuit breaker without breaker_category
        # Note: This works because we disabled CHECK constraints
        try:
            cursor.execute(
                """
                INSERT INTO elements (
                    substation_id, element_type, name, breaker_category
                )
                VALUES (?, 'Διακόπτης ΥΤ', 'Test Breaker', '')
                """,
                (sub_id,),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            # If CHECK constraint is still enforced (SQLite version dependent),
            # skip this test as we can't create the invalid state
            conn.close()
            import pytest

            pytest.skip("Cannot disable CHECK constraints in this SQLite version")

        # Re-enable CHECK constraints
        cursor.execute("PRAGMA ignore_check_constraints = OFF")
        conn.close()

        # Run full integrity check
        result = check_database_integrity(tmp_path, quick_check=False)

        # This should generate a warning (not error, since database is usable)
        assert len(result.warnings) > 0, "Should warn about breakers without category"
        assert any("breaker" in warn.lower() for warn in result.warnings), (
            "Should mention breakers in warning"
        )

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def test_integrity_result_summary():
    """Test that IntegrityCheckResult generates proper summaries."""
    from db_integrity import IntegrityCheckResult

    result = IntegrityCheckResult()
    result.add_error("Test error")
    result.add_warning("Test warning")
    result.add_info("Test info")

    summary = result.get_summary()

    assert "ERROR" in summary
    assert "WARNING" in summary
    assert "INFO" in summary
    assert "Test error" in summary
    assert "Test warning" in summary
    assert "Test info" in summary


def test_extract_repairable_index_names():
    names = _extract_repairable_index_names(
        [
            "wrong # of entries in index idx_maintenance_overview_report_paths_maint_gate",
            "row 7 missing from index idx_maintenance_report_paths_maint_elem",
        ]
    )

    assert names == [
        "idx_maintenance_overview_report_paths_maint_gate",
        "idx_maintenance_report_paths_maint_elem",
    ]


def test_attempt_index_auto_repair_with_reindex_only():
    class FakeCursor:
        def __init__(self):
            self.last_sql = None

        def execute(self, sql, params=None):
            self.last_sql = sql
            return self

        def fetchall(self):
            if self.last_sql == "PRAGMA integrity_check":
                return [("ok",)]
            return []

        def fetchone(self):
            return None

    fake_conn = Mock()
    fake_cursor = FakeCursor()

    repaired = _attempt_index_auto_repair(
        fake_conn,
        fake_cursor,
        [
            "wrong # of entries in index idx_maintenance_overview_report_paths_maint_gate"
        ],
    )

    assert repaired == ["idx_maintenance_overview_report_paths_maint_gate"]
    fake_conn.commit.assert_called()


def test_attempt_malformed_db_repair_with_reindex_only():
    class FakeCursor:
        def __init__(self):
            self.last_sql = None
            self.integrity_calls = 1

        def execute(self, sql, params=None):
            self.last_sql = sql.strip()
            return self

        def fetchall(self):
            if self.last_sql == "PRAGMA integrity_check":
                self.integrity_calls += 1
                if self.integrity_calls == 1:
                    raise sqlite3.DatabaseError("database disk image is malformed")
                return [("ok",)]
            return []

        def fetchone(self):
            return None

    fake_conn = Mock()
    fake_cursor = FakeCursor()

    repaired = _attempt_malformed_db_repair(
        fake_conn,
        fake_cursor,
        sqlite3.DatabaseError("database disk image is malformed"),
    )

    assert repaired == ["REINDEX"]
    fake_conn.commit.assert_called()


def test_recreate_all_user_indexes_rebuilds_declared_indexes():
    class FakeCursor:
        def __init__(self):
            self.last_sql = None
            self.executed_sql = []

        def execute(self, sql, params=None):
            normalized_sql = sql.strip()
            self.last_sql = normalized_sql
            self.executed_sql.append(normalized_sql)
            return self

        def fetchall(self):
            if "FROM sqlite_master" in self.last_sql:
                return [
                    (
                        "idx_demo",
                        "CREATE INDEX idx_demo ON demo_table(example_column)",
                    )
                ]
            return []

        def fetchone(self):
            return None

    fake_conn = Mock()
    fake_cursor = FakeCursor()

    recreated = _recreate_all_user_indexes(fake_conn, fake_cursor)

    assert recreated == ["idx_demo"]
    assert 'DROP INDEX IF EXISTS "idx_demo"' in fake_cursor.executed_sql
    assert (
        "CREATE INDEX idx_demo ON demo_table(example_column)"
        in fake_cursor.executed_sql
    )
    fake_conn.commit.assert_called()
