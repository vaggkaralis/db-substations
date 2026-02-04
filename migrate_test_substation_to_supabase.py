import argparse
import os
import sqlite3
from typing import Iterable

try:
    import psycopg2
    from psycopg2.extras import DictCursor
except Exception as exc:  # pragma: no cover
    psycopg2 = None
    DictCursor = None
    raise RuntimeError("psycopg2 is required to run this migration") from exc


def connect_sqlite(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def connect_postgres(database_url: str):
    connect_kwargs = {}
    if "sslmode=" not in database_url:
        connect_kwargs["sslmode"] = "require"
    return psycopg2.connect(database_url, cursor_factory=DictCursor, **connect_kwargs)


def sqlite_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return bool(cur.fetchone())


def pg_apply_schema(conn):
    c = conn.cursor()
    schema = [
        """
        CREATE TABLE IF NOT EXISTS element_models (
            id SERIAL PRIMARY KEY,
            element_category TEXT NOT NULL,
            model_name TEXT NOT NULL,
            manufacturer TEXT,
            maintenance_cycle INTEGER DEFAULT 0,
            installation_space TEXT,
            breaker_category TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(element_category, model_name, manufacturer)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS substations (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            location TEXT,
            adoption_date TEXT,
            division TEXT DEFAULT 'ΤΜΘ',
            last_maintenance TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS elements (
            id SERIAL PRIMARY KEY,
            substation_id INTEGER NOT NULL,
            element_type TEXT,
            name TEXT NOT NULL,
            serial_number TEXT,
            maintenance_date TEXT,
            voltage_level TEXT,
            manufacturer TEXT,
            type TEXT,
            model TEXT,
            model_version TEXT,
            element_model_id INTEGER,
            operating_status TEXT DEFAULT 'Ενεργή',
            installation_space TEXT,
            maintenance_cycle INTEGER DEFAULT 0,
            gate TEXT,
            breaker_category TEXT,
            manufacture_year TEXT,
            is_main_switch BOOLEAN DEFAULT FALSE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (substation_id) REFERENCES substations(id),
            UNIQUE(substation_id, name)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS maintenance (
            id SERIAL PRIMARY KEY,
            substation_id INTEGER NOT NULL,
            name TEXT,
            date_time TEXT NOT NULL,
            overall_comments TEXT,
            maintenance_type TEXT,
            user_name TEXT,
            FOREIGN KEY (substation_id) REFERENCES substations(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS maintenance_elements (
            id SERIAL PRIMARY KEY,
            maintenance_id INTEGER NOT NULL,
            element_id INTEGER NOT NULL,
            element_comments TEXT,
            sf6_leak_methodology TEXT,
            FOREIGN KEY (maintenance_id) REFERENCES maintenance(id) ON DELETE CASCADE,
            FOREIGN KEY (element_id) REFERENCES elements(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS people (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            email TEXT,
            report_receiver INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS maintenance_people (
            id SERIAL PRIMARY KEY,
            maintenance_id INTEGER NOT NULL,
            person_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            FOREIGN KEY (maintenance_id) REFERENCES maintenance(id) ON DELETE CASCADE,
            FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS inspections (
            id SERIAL PRIMARY KEY,
            substation_id INTEGER,
            substation_name TEXT,
            inspection_date TEXT NOT NULL,
            month_key TEXT NOT NULL,
            data_json TEXT NOT NULL,
            source_file TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (substation_id) REFERENCES substations(id) ON DELETE SET NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS isolation_requests (
            id SERIAL PRIMARY KEY,
            substation_id INTEGER NOT NULL,
            start_datetime TEXT NOT NULL,
            end_datetime TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Requested',
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (substation_id) REFERENCES substations(id) ON DELETE CASCADE
        )
        """
    ]
    for stmt in schema:
        c.execute(stmt)


def _rows_to_dicts(rows: Iterable) -> list[dict]:
    return [dict(row) for row in rows]


def _set_sequences(cur, tables: list[str]):
    for table in tables:
        cur.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE((SELECT MAX(id) FROM {table}), 1), true)"
        )


def migrate(sqlite_path: str, database_url: str):
    sqlite_conn = connect_sqlite(sqlite_path)
    pg_conn = connect_postgres(database_url)

    pg_apply_schema(pg_conn)

    s_cur = sqlite_conn.cursor()
    s_cur.execute("SELECT * FROM substations WHERE name=?", ("TEST",))
    substation = s_cur.fetchone()
    if not substation:
        raise RuntimeError("TEST substation not found in SQLite database")

    substation_id = substation["id"]

    s_cur.execute("SELECT * FROM elements WHERE substation_id=?", (substation_id,))
    elements = _rows_to_dicts(s_cur.fetchall())

    s_cur.execute("SELECT * FROM maintenance WHERE substation_id=?", (substation_id,))
    maintenance = _rows_to_dicts(s_cur.fetchall())
    maintenance_ids = [m["id"] for m in maintenance]

    maintenance_elements = []
    if maintenance_ids and sqlite_table_exists(sqlite_conn, "maintenance_elements"):
        placeholders = ",".join(["?"] * len(maintenance_ids))
        s_cur.execute(
            f"SELECT * FROM maintenance_elements WHERE maintenance_id IN ({placeholders})",
            maintenance_ids,
        )
        maintenance_elements = _rows_to_dicts(s_cur.fetchall())

    inspections = []
    if sqlite_table_exists(sqlite_conn, "inspections"):
        s_cur.execute(
            "SELECT * FROM inspections WHERE substation_id=? OR substation_name=?",
            (substation_id, "TEST"),
        )
        inspections = _rows_to_dicts(s_cur.fetchall())

    isolation_requests = []
    if sqlite_table_exists(sqlite_conn, "isolation_requests"):
        s_cur.execute(
            "SELECT * FROM isolation_requests WHERE substation_id=?",
            (substation_id,),
        )
        isolation_requests = _rows_to_dicts(s_cur.fetchall())

    element_models = []
    if sqlite_table_exists(sqlite_conn, "element_models"):
        model_ids = sorted({e.get("element_model_id") for e in elements if e.get("element_model_id")})
        if model_ids:
            placeholders = ",".join(["?"] * len(model_ids))
            s_cur.execute(
                f"SELECT * FROM element_models WHERE id IN ({placeholders})",
                model_ids,
            )
            element_models = _rows_to_dicts(s_cur.fetchall())

    maintenance_people = []
    people = []
    if maintenance_ids and sqlite_table_exists(sqlite_conn, "maintenance_people"):
        placeholders = ",".join(["?"] * len(maintenance_ids))
        s_cur.execute(
            f"SELECT * FROM maintenance_people WHERE maintenance_id IN ({placeholders})",
            maintenance_ids,
        )
        maintenance_people = _rows_to_dicts(s_cur.fetchall())
        person_ids = sorted({mp.get("person_id") for mp in maintenance_people if mp.get("person_id")})
        if person_ids and sqlite_table_exists(sqlite_conn, "people"):
            placeholders = ",".join(["?"] * len(person_ids))
            s_cur.execute(
                f"SELECT * FROM people WHERE id IN ({placeholders})",
                person_ids,
            )
            people = _rows_to_dicts(s_cur.fetchall())

    sqlite_conn.close()

    p_cur = pg_conn.cursor()

    # Clear existing TEST data
    p_cur.execute("SELECT id FROM substations WHERE name=%s", ("TEST",))
    existing = p_cur.fetchone()
    if existing:
        existing_id = existing["id"]
        p_cur.execute(
            "DELETE FROM maintenance_elements WHERE maintenance_id IN (SELECT id FROM maintenance WHERE substation_id=%s)",
            (existing_id,),
        )
        p_cur.execute(
            "DELETE FROM maintenance_people WHERE maintenance_id IN (SELECT id FROM maintenance WHERE substation_id=%s)",
            (existing_id,),
        )
        p_cur.execute("DELETE FROM maintenance WHERE substation_id=%s", (existing_id,))
        p_cur.execute("DELETE FROM inspections WHERE substation_id=%s", (existing_id,))
        p_cur.execute("DELETE FROM isolation_requests WHERE substation_id=%s", (existing_id,))
        p_cur.execute("DELETE FROM elements WHERE substation_id=%s", (existing_id,))
        p_cur.execute("DELETE FROM substations WHERE id=%s", (existing_id,))

    # Insert element models first
    for model in element_models:
        p_cur.execute(
            """
            INSERT INTO element_models (id, element_category, model_name, manufacturer, maintenance_cycle, installation_space, breaker_category, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                element_category = EXCLUDED.element_category,
                model_name = EXCLUDED.model_name,
                manufacturer = EXCLUDED.manufacturer,
                maintenance_cycle = EXCLUDED.maintenance_cycle,
                installation_space = EXCLUDED.installation_space,
                breaker_category = EXCLUDED.breaker_category,
                created_at = EXCLUDED.created_at
            """,
            (
                model.get("id"),
                model.get("element_category"),
                model.get("model_name"),
                model.get("manufacturer"),
                model.get("maintenance_cycle"),
                model.get("installation_space"),
                model.get("breaker_category"),
                model.get("created_at"),
            ),
        )

    # Insert substation
    p_cur.execute(
        """
        INSERT INTO substations (id, name, location, adoption_date, division, last_maintenance, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            substation.get("id"),
            substation.get("name"),
            substation.get("location"),
            substation.get("adoption_date"),
            substation.get("division"),
            substation.get("last_maintenance"),
            substation.get("created_at"),
        ),
    )

    for elem in elements:
        p_cur.execute(
            """
            INSERT INTO elements (
                id, substation_id, element_type, name, serial_number, maintenance_date, voltage_level,
                manufacturer, type, model, model_version, element_model_id, operating_status,
                installation_space, maintenance_cycle, gate, breaker_category, manufacture_year,
                is_main_switch, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                elem.get("id"),
                elem.get("substation_id"),
                elem.get("element_type"),
                elem.get("name"),
                elem.get("serial_number"),
                elem.get("maintenance_date"),
                elem.get("voltage_level"),
                elem.get("manufacturer"),
                elem.get("type"),
                elem.get("model"),
                elem.get("model_version"),
                elem.get("element_model_id"),
                elem.get("operating_status"),
                elem.get("installation_space"),
                elem.get("maintenance_cycle"),
                elem.get("gate"),
                elem.get("breaker_category"),
                elem.get("manufacture_year"),
                bool(elem.get("is_main_switch")) if elem.get("is_main_switch") is not None else None,
                elem.get("created_at"),
            ),
        )

    for m in maintenance:
        p_cur.execute(
            """
            INSERT INTO maintenance (id, substation_id, name, date_time, overall_comments, maintenance_type, user_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                m.get("id"),
                m.get("substation_id"),
                m.get("name"),
                m.get("date_time"),
                m.get("overall_comments"),
                m.get("maintenance_type"),
                m.get("user_name"),
            ),
        )

    for me in maintenance_elements:
        p_cur.execute(
            """
            INSERT INTO maintenance_elements (id, maintenance_id, element_id, element_comments, sf6_leak_methodology)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                me.get("id"),
                me.get("maintenance_id"),
                me.get("element_id"),
                me.get("element_comments"),
                me.get("sf6_leak_methodology"),
            ),
        )

    for person in people:
        p_cur.execute(
            """
            INSERT INTO people (id, name, role, email, report_receiver, active)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                person.get("id"),
                person.get("name"),
                person.get("role"),
                person.get("email"),
                person.get("report_receiver"),
                person.get("active"),
            ),
        )

    for mp in maintenance_people:
        p_cur.execute(
            """
            INSERT INTO maintenance_people (id, maintenance_id, person_id, role)
            VALUES (%s, %s, %s, %s)
            """,
            (
                mp.get("id"),
                mp.get("maintenance_id"),
                mp.get("person_id"),
                mp.get("role"),
            ),
        )

    for insp in inspections:
        p_cur.execute(
            """
            INSERT INTO inspections (id, substation_id, substation_name, inspection_date, month_key, data_json, source_file, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                insp.get("id"),
                insp.get("substation_id"),
                insp.get("substation_name"),
                insp.get("inspection_date"),
                insp.get("month_key"),
                insp.get("data_json"),
                insp.get("source_file"),
                insp.get("created_at"),
            ),
        )

    for ir in isolation_requests:
        p_cur.execute(
            """
            INSERT INTO isolation_requests (id, substation_id, start_datetime, end_datetime, status, notes, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                ir.get("id"),
                ir.get("substation_id"),
                ir.get("start_datetime"),
                ir.get("end_datetime"),
                ir.get("status"),
                ir.get("notes"),
                ir.get("created_at"),
                ir.get("updated_at"),
            ),
        )

    _set_sequences(
        p_cur,
        [
            "element_models",
            "substations",
            "elements",
            "maintenance",
            "maintenance_elements",
            "people",
            "maintenance_people",
            "inspections",
            "isolation_requests",
        ],
    )

    pg_conn.commit()
    pg_conn.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate ONLY the TEST substation to Supabase/Postgres")
    parser.add_argument(
        "--sqlite-path",
        default="substations.db",
        help="Path to local SQLite database (default: substations.db)",
    )
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is required")

    migrate(args.sqlite_path, database_url)
    print("Migration completed successfully.")


if __name__ == "__main__":
    main()
