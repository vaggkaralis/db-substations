import sqlite3

from settings import DB_PATH
from strings_proxy import STRINGS as S


def init_db(db_path: str = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = DB_PATH
    """Initialize SQLite connection, ensure tables exist, and apply lightweight migrations."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS substations (id INTEGER PRIMARY KEY, name TEXT, location TEXT, adoption_date TEXT)"
    )
    # Element models master table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS element_models (
            id INTEGER PRIMARY KEY,
            element_category TEXT NOT NULL,
            model_name TEXT NOT NULL,
            manufacturer TEXT,
            maintenance_cycle INTEGER DEFAULT 0,
            installation_space TEXT,
            breaker_category TEXT,
            sf6_capacity_kg REAL,
            manual_pdf TEXT,
            UNIQUE(element_category, model_name, manufacturer)
        )
    """)

    cursor.execute(
        "CREATE TABLE IF NOT EXISTS elements (id INTEGER PRIMARY KEY, substation_id INTEGER, element_type TEXT, name TEXT, serial_number TEXT, maintenance_date TEXT, voltage_level TEXT, manufacturer TEXT, type TEXT, gate TEXT, FOREIGN KEY(substation_id) REFERENCES substations(id))"
    )

    # Maintenance tracking tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS maintenance (
            id INTEGER PRIMARY KEY,
            substation_id INTEGER NOT NULL,
            name TEXT,
            date_time TEXT NOT NULL,
            overall_comments TEXT,
            responsible_id INTEGER,
            FOREIGN KEY(substation_id) REFERENCES substations(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS maintenance_elements (
            id INTEGER PRIMARY KEY,
            maintenance_id INTEGER NOT NULL,
            element_id INTEGER NOT NULL,
            element_comments TEXT,
            sf6_leak_methodology TEXT,
            FOREIGN KEY(maintenance_id) REFERENCES maintenance(id) ON DELETE CASCADE,
            FOREIGN KEY(element_id) REFERENCES elements(id) ON DELETE CASCADE
        )
    """)

    # Folder tracking per maintenance + gate/interconnection bucket
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS maintenance_storage_paths (
            id INTEGER PRIMARY KEY,
            maintenance_id INTEGER NOT NULL,
            gate_key TEXT NOT NULL,
            gate_folder TEXT,
            instance_folder TEXT,
            media_folder TEXT,
            reports_folder TEXT,
            created_at TEXT,
            FOREIGN KEY(maintenance_id) REFERENCES maintenance(id) ON DELETE CASCADE,
            UNIQUE(maintenance_id, gate_key)
        )
    """)

    # Report tracking per maintenance + element
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS maintenance_report_paths (
            id INTEGER PRIMARY KEY,
            maintenance_id INTEGER NOT NULL,
            element_id INTEGER NOT NULL,
            report_type TEXT NOT NULL DEFAULT 'pdf',
            report_path TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(maintenance_id) REFERENCES maintenance(id) ON DELETE CASCADE,
            FOREIGN KEY(element_id) REFERENCES elements(id) ON DELETE CASCADE,
            UNIQUE(maintenance_id, element_id, report_type)
        )
    """)

    # DGA measurements (transformer-only extra report)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dga_measurements (
            id INTEGER PRIMARY KEY,
            maintenance_id INTEGER NOT NULL,
            element_id INTEGER NOT NULL,
            substation_id INTEGER NOT NULL,
            measurement_date TEXT,
            sampling_date TEXT,
            sampling_responsible TEXT,
            measurement_responsible TEXT,
            sample_point TEXT,
            sampling_method TEXT,
            sample_temperature REAL,
            h2 REAL,
            c2h2 REAL,
            c2h4 REAL,
            c2h6 REAL,
            co REAL,
            co2 REAL,
            ch4 REAL,
            o2 REAL,
            c3h8 REAL,
            n2 REAL,
            h2o REAL,
            density REAL,
            humidity REAL,
            dielectric_strength REAL,
            loss_factor REAL,
            surface_tension REAL,
            notes TEXT,
            report_path TEXT,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(maintenance_id) REFERENCES maintenance(id) ON DELETE CASCADE,
            FOREIGN KEY(element_id) REFERENCES elements(id) ON DELETE CASCADE,
            FOREIGN KEY(substation_id) REFERENCES substations(id) ON DELETE CASCADE
        )
    """)

    # People management tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS people (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            email TEXT,
            report_receiver INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS maintenance_people (
            id INTEGER PRIMARY KEY,
            maintenance_id INTEGER NOT NULL,
            person_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            FOREIGN KEY(maintenance_id) REFERENCES maintenance(id) ON DELETE CASCADE,
            FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
        )
    """)

    # Inspections table (monthly inspection reports)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inspections (
            id INTEGER PRIMARY KEY,
            substation_id INTEGER,
            substation_name TEXT,
            inspection_date TEXT NOT NULL,
            month_key TEXT NOT NULL,
            data_json TEXT NOT NULL,
            source_file TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(substation_id) REFERENCES substations(id) ON DELETE SET NULL
        )
    """)

    # Isolation requests table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS isolation_requests (
            id INTEGER PRIMARY KEY,
            substation_id INTEGER NOT NULL,
            start_datetime TEXT NOT NULL,
            end_datetime TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Requested',
            notes TEXT,
            request_file_path TEXT,
            storage_folder_path TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(substation_id) REFERENCES substations(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS isolation_request_elements (
            id INTEGER PRIMARY KEY,
            request_id INTEGER NOT NULL,
            element_id INTEGER NOT NULL,
            FOREIGN KEY(request_id) REFERENCES isolation_requests(id) ON DELETE CASCADE,
            FOREIGN KEY(element_id) REFERENCES elements(id) ON DELETE CASCADE,
            UNIQUE(request_id, element_id)
        )
    """)

    cursor.execute("PRAGMA table_info(substations)")
    sub_columns = [column[1] for column in cursor.fetchall()]
    if "location" not in sub_columns:
        try:
            cursor.execute(
                'ALTER TABLE substations ADD COLUMN location TEXT DEFAULT ""'
            )
        except Exception:
            pass
    if "adoption_date" not in sub_columns:
        try:
            cursor.execute(
                'ALTER TABLE substations ADD COLUMN adoption_date TEXT DEFAULT ""'
            )
        except Exception:
            pass
    if "division" not in sub_columns:
        try:
            cursor.execute(
                'ALTER TABLE substations ADD COLUMN division TEXT DEFAULT "ΤΜΘ"'
            )
        except Exception:
            pass
    if "is_thessaloniki" not in sub_columns:
        try:
            cursor.execute(
                'ALTER TABLE substations ADD COLUMN is_thessaloniki INTEGER DEFAULT 0'
            )
        except Exception:
            pass
    if "last_maintenance" not in sub_columns:
        try:
            cursor.execute(
                'ALTER TABLE substations ADD COLUMN last_maintenance TEXT DEFAULT ""'
            )
        except Exception:
            pass
    if "monogram_pdf" not in sub_columns:
        try:
            cursor.execute(
                'ALTER TABLE substations ADD COLUMN monogram_pdf TEXT DEFAULT ""'
            )
        except Exception:
            pass

    # Add breaker_category column to elements table
    cursor.execute("PRAGMA table_info(elements)")
    elem_columns = [column[1] for column in cursor.fetchall()]

    # Performance indexes for maintenance history views/import joins
    try:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_maintenance_substation_date ON maintenance(substation_id, date_time DESC)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_maintenance_date ON maintenance(date_time DESC)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_maintenance_substation_type ON maintenance(substation_id, maintenance_type)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_maintenance_elements_maintenance ON maintenance_elements(maintenance_id)"
        )
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_maintenance_elements_maint_elem ON maintenance_elements(maintenance_id, element_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_maintenance_people_maintenance ON maintenance_people(maintenance_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_maintenance_storage_paths_maintenance ON maintenance_storage_paths(maintenance_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_maintenance_report_paths_maint_elem ON maintenance_report_paths(maintenance_id, element_id, report_type)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_dga_maintenance_element ON dga_measurements(maintenance_id, element_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_elements_substation ON elements(substation_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_elements_substation_gate ON elements(substation_id, gate)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_elements_substation_status ON elements(substation_id, operating_status)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_elements_substation_type_switch ON elements(substation_id, element_type, is_main_switch)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_inspections_substation ON inspections(substation_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_substations_name ON substations(name)"
        )
    except Exception:
        pass

    # Ensure database-level constraint: for circuit breakers (Διακόπτης ΥΤ/Διακόπτης ΜΤ)
    # breaker_category must be non-empty. We implement this by creating a new
    # `elements` table with a CHECK constraint and migrating existing data if the
    # current table does not already have the constraint.
    try:
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='elements'")
        tbl_sql_row = cursor.fetchone()
        tbl_sql = tbl_sql_row[0] if tbl_sql_row and tbl_sql_row[0] else ""
    except Exception:
        tbl_sql = ""

    # Detect whether a suitable CHECK already exists (simple substring check).
    need_migration = True
    if tbl_sql and "TRIM(breaker_category)" in tbl_sql and "CHECK" in tbl_sql:
        need_migration = False

    if need_migration:
        try:
            cursor.execute("PRAGMA table_info(elements)")
            existing_cols = [r[1] for r in cursor.fetchall()]

            # Create new table with the desired schema and CHECK constraint
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS elements_new (
                    id INTEGER PRIMARY KEY,
                    substation_id INTEGER,
                    element_type TEXT,
                    name TEXT,
                    serial_number TEXT,
                    maintenance_date TEXT,
                    voltage_level TEXT,
                    manufacturer TEXT,
                    model TEXT DEFAULT "",
                    gate TEXT DEFAULT "",
                    breaker_category TEXT DEFAULT "",
                    installation_space TEXT DEFAULT "",
                    operating_status TEXT DEFAULT 'Ενεργή',
                    maintenance_cycle INTEGER DEFAULT 0,
                    element_model_id INTEGER,
                    manufacture_year TEXT DEFAULT "",
                    model_version TEXT DEFAULT "",
                    power_mva REAL,
                    is_main_switch INTEGER DEFAULT 0,
                    operations_count INTEGER DEFAULT 0,
                    FOREIGN KEY(substation_id) REFERENCES substations(id),
                    CHECK((element_type NOT IN ('Διακόπτης ΥΤ', 'Διακόπτης ΜΤ')) OR (breaker_category IS NOT NULL AND TRIM(breaker_category) != ''))
                )
            ''')

            # Copy columns that exist in the old table into the new table
            cols_to_copy = [c for c in [
                'id','substation_id','element_type','name','serial_number','maintenance_date',
                'voltage_level','manufacturer','model','gate','breaker_category','installation_space',
                'operating_status','maintenance_cycle','element_model_id','manufacture_year',
                'model_version','power_mva','is_main_switch','operations_count'
            ] if c in existing_cols]

            if cols_to_copy:
                cols_list = ",".join(cols_to_copy)
                cursor.execute(f"INSERT INTO elements_new ({cols_list}) SELECT {cols_list} FROM elements")

            cursor.execute("DROP TABLE elements")
            cursor.execute("ALTER TABLE elements_new RENAME TO elements")
            conn.commit()
        except Exception:
            # If migration fails, ensure we don't crash init_db; leave existing table as-is
            try:
                conn.rollback()
            except Exception:
                pass
    if "breaker_category" not in elem_columns:
        try:
            cursor.execute(
                'ALTER TABLE elements ADD COLUMN breaker_category TEXT DEFAULT ""'
            )
        except Exception:
            pass

    # Rename type to model and add new columns
    if "model" not in elem_columns:
        try:
            # SQLite doesn't support column rename, so we check if old column exists
            if "type" in elem_columns:
                cursor.execute('ALTER TABLE elements ADD COLUMN model TEXT DEFAULT ""')
                # Copy data from type to model
                cursor.execute("UPDATE elements SET model = type")
            else:
                cursor.execute('ALTER TABLE elements ADD COLUMN model TEXT DEFAULT ""')
        except Exception:
            pass

    if "installation_space" not in elem_columns:
        try:
            cursor.execute(
                'ALTER TABLE elements ADD COLUMN installation_space TEXT DEFAULT ""'
            )
        except Exception:
            pass

    if "operating_status" not in elem_columns:
        try:
            cursor.execute(
                'ALTER TABLE elements ADD COLUMN operating_status TEXT DEFAULT "Ενεργή"'
            )
        except Exception:
            pass

    if "maintenance_cycle" not in elem_columns:
        try:
            cursor.execute(
                "ALTER TABLE elements ADD COLUMN maintenance_cycle INTEGER DEFAULT 0"
            )
        except Exception:
            pass

    if "element_model_id" not in elem_columns:
        try:
            cursor.execute(
                "ALTER TABLE elements ADD COLUMN element_model_id INTEGER REFERENCES element_models(id)"
            )
        except Exception:
            pass

    if "manufacture_year" not in elem_columns:
        try:
            cursor.execute(
                'ALTER TABLE elements ADD COLUMN manufacture_year TEXT DEFAULT ""'
            )
        except Exception:
            pass

    if "model_version" not in elem_columns:
        try:
            cursor.execute(
                'ALTER TABLE elements ADD COLUMN model_version TEXT DEFAULT ""'
            )
        except Exception:
            pass

    # Add power (ΙΣΧΥΣ) column to elements to store transformer power in MVA
    # This is a standard attribute for any element; allow NULL so it can be empty.
    if "power_mva" not in elem_columns:
        try:
            cursor.execute('ALTER TABLE elements ADD COLUMN power_mva REAL')
        except Exception:
            pass

    # Add gate column to elements table for organizing by transformer/gate
    if "gate" not in elem_columns:
        try:
            if "bar" in elem_columns:
                cursor.execute("ALTER TABLE elements RENAME COLUMN bar TO gate")
            else:
                cursor.execute('ALTER TABLE elements ADD COLUMN gate TEXT DEFAULT ""')
        except Exception:
            try:
                cursor.execute('ALTER TABLE elements ADD COLUMN gate TEXT DEFAULT ""')
            except Exception:
                pass

    cursor.execute("PRAGMA table_info(elements)")
    elem_columns = [column[1] for column in cursor.fetchall()]

    if "gate" in elem_columns and "bar" in elem_columns:
        try:
            cursor.execute(
                'UPDATE elements SET gate = bar WHERE (gate IS NULL OR gate = "") AND bar IS NOT NULL AND bar != ""'
            )
        except Exception:
            pass

    if "gate" in elem_columns:
        try:
            cursor.execute(
                'UPDATE elements SET gate = REPLACE(gate, "ΖΥΓΟΣ", "ΠΥΛΗ") WHERE gate LIKE "ΖΥΓΟΣ%"'
            )
        except Exception:
            pass

    # Add data_json column to maintenance_elements for storing arbitrary form data
    cursor.execute("PRAGMA table_info(maintenance_elements)")
    me_columns = [column[1] for column in cursor.fetchall()]
    if "data_json" not in me_columns:
        try:
            cursor.execute('ALTER TABLE maintenance_elements ADD COLUMN data_json TEXT')
        except Exception:
            pass

    # Add is_main_switch flag to identify main circuit breakers (HV and MV main)
    if "is_main_switch" not in elem_columns:
        try:
            cursor.execute(
                "ALTER TABLE elements ADD COLUMN is_main_switch INTEGER DEFAULT 0"
            )
        except Exception:
            pass

    # Add operations_count to track circuit breaker operations
    if "operations_count" not in elem_columns:
        try:
            cursor.execute(
                "ALTER TABLE elements ADD COLUMN operations_count INTEGER DEFAULT 0"
            )
        except Exception:
            pass

    # Add maintenance_type and user columns to maintenance table
    cursor.execute("PRAGMA table_info(maintenance)")
    maint_columns = [column[1] for column in cursor.fetchall()]
    if "name" not in maint_columns:
        try:
            cursor.execute("ALTER TABLE maintenance ADD COLUMN name TEXT")
        except Exception:
            pass
    if "maintenance_type" not in maint_columns:
        try:
            cursor.execute(
                'ALTER TABLE maintenance ADD COLUMN maintenance_type TEXT DEFAULT "' + S.get("MESSAGES", {}).get("MAINT_TYPE_DEFAULT", "Επαναληπτική συντήρηση") + '"'
            )
        except Exception:
            pass
    if "user_name" not in maint_columns:
        try:
            cursor.execute(
                'ALTER TABLE maintenance ADD COLUMN user_name TEXT DEFAULT ""'
            )
        except Exception:
            pass
    if "responsible_id" not in maint_columns:
        try:
            cursor.execute("ALTER TABLE maintenance ADD COLUMN responsible_id INTEGER")
        except Exception:
            pass
    if "isolation_request_id" not in maint_columns:
        try:
            cursor.execute("ALTER TABLE maintenance ADD COLUMN isolation_request_id INTEGER")
        except Exception:
            pass
    if "preparation_checklist_json" not in maint_columns:
        try:
            cursor.execute("ALTER TABLE maintenance ADD COLUMN preparation_checklist_json TEXT")
        except Exception:
            pass

    # People table migrations
    cursor.execute("PRAGMA table_info(people)")
    people_columns = [column[1] for column in cursor.fetchall()]
    if "email" not in people_columns:
        try:
            cursor.execute("ALTER TABLE people ADD COLUMN email TEXT")
        except Exception:
            pass
    if "report_receiver" not in people_columns:
        try:
            cursor.execute(
                "ALTER TABLE people ADD COLUMN report_receiver INTEGER DEFAULT 0"
            )
        except Exception:
            pass

    # Add measurement fields to maintenance_elements table for circuit breakers
    cursor.execute("PRAGMA table_info(maintenance_elements)")
    maint_elem_columns = [column[1] for column in cursor.fetchall()]

    # SF6 leakage measurement (kg)
    if "sf6_leakage_kg" not in maint_elem_columns:
        try:
            cursor.execute(
                "ALTER TABLE maintenance_elements ADD COLUMN sf6_leakage_kg REAL"
            )
        except Exception:
            pass

    if "sf6_leak_methodology" not in maint_elem_columns:
        try:
            cursor.execute(
                "ALTER TABLE maintenance_elements ADD COLUMN sf6_leak_methodology TEXT"
            )
        except Exception:
            pass

    # Insulation resistance measurements - Switch closed (to ground)
    if "insulation_closed_fa_ground" not in maint_elem_columns:
        try:
            cursor.execute(
                "ALTER TABLE maintenance_elements ADD COLUMN insulation_closed_fa_ground REAL"
            )
        except Exception:
            pass
    if "insulation_closed_fb_ground" not in maint_elem_columns:
        try:
            cursor.execute(
                "ALTER TABLE maintenance_elements ADD COLUMN insulation_closed_fb_ground REAL"
            )
        except Exception:
            pass
    if "insulation_closed_fc_ground" not in maint_elem_columns:
        try:
            cursor.execute(
                "ALTER TABLE maintenance_elements ADD COLUMN insulation_closed_fc_ground REAL"
            )
        except Exception:
            pass

    # Insulation resistance measurements - Switch open (phase to phase)
    if "insulation_open_fa_fa" not in maint_elem_columns:
        try:
            cursor.execute(
                "ALTER TABLE maintenance_elements ADD COLUMN insulation_open_fa_fa REAL"
            )
        except Exception:
            pass
    if "insulation_open_fb_fb" not in maint_elem_columns:
        try:
            cursor.execute(
                "ALTER TABLE maintenance_elements ADD COLUMN insulation_open_fb_fb REAL"
            )
        except Exception:
            pass
    if "insulation_open_fc_fc" not in maint_elem_columns:
        try:
            cursor.execute(
                "ALTER TABLE maintenance_elements ADD COLUMN insulation_open_fc_fc REAL"
            )
        except Exception:
            pass

    # Contact resistance measurements - Switch closed (phase to phase)
    if "contact_resistance_fa_fa" not in maint_elem_columns:
        try:
            cursor.execute(
                "ALTER TABLE maintenance_elements ADD COLUMN contact_resistance_fa_fa REAL"
            )
        except Exception:
            pass
    if "contact_resistance_fb_fb" not in maint_elem_columns:
        try:
            cursor.execute(
                "ALTER TABLE maintenance_elements ADD COLUMN contact_resistance_fb_fb REAL"
            )
        except Exception:
            pass
    if "contact_resistance_fc_fc" not in maint_elem_columns:
        try:
            cursor.execute(
                "ALTER TABLE maintenance_elements ADD COLUMN contact_resistance_fc_fc REAL"
            )
        except Exception:
            pass

    # Units for each insulation measurement
    if "insulation_closed_fa_unit" not in maint_elem_columns:
        try:
            cursor.execute(
                'ALTER TABLE maintenance_elements ADD COLUMN insulation_closed_fa_unit TEXT DEFAULT "GΩ"'
            )
        except Exception:
            pass
    if "insulation_closed_fb_unit" not in maint_elem_columns:
        try:
            cursor.execute(
                'ALTER TABLE maintenance_elements ADD COLUMN insulation_closed_fb_unit TEXT DEFAULT "GΩ"'
            )
        except Exception:
            pass
    if "insulation_closed_fc_unit" not in maint_elem_columns:
        try:
            cursor.execute(
                'ALTER TABLE maintenance_elements ADD COLUMN insulation_closed_fc_unit TEXT DEFAULT "GΩ"'
            )
        except Exception:
            pass
    if "insulation_open_fa_unit" not in maint_elem_columns:
        try:
            cursor.execute(
                'ALTER TABLE maintenance_elements ADD COLUMN insulation_open_fa_unit TEXT DEFAULT "GΩ"'
            )
        except Exception:
            pass
    if "insulation_open_fb_unit" not in maint_elem_columns:
        try:
            cursor.execute(
                'ALTER TABLE maintenance_elements ADD COLUMN insulation_open_fb_unit TEXT DEFAULT "GΩ"'
            )
        except Exception:
            pass
    if "insulation_open_fc_unit" not in maint_elem_columns:
        try:
            cursor.execute(
                'ALTER TABLE maintenance_elements ADD COLUMN insulation_open_fc_unit TEXT DEFAULT "GΩ"'
            )
        except Exception:
            pass

    # Operations count at maintenance time
    if "operations_count" not in maint_elem_columns:
        try:
            cursor.execute(
                "ALTER TABLE maintenance_elements ADD COLUMN operations_count INTEGER"
            )
        except Exception:
            pass

    # SF6 Gas Quality measurements (for SF6 breakers only)
    # Phase A
    if "sf6_n2_fa" not in maint_elem_columns:
        try:
            cursor.execute("ALTER TABLE maintenance_elements ADD COLUMN sf6_n2_fa REAL")
        except Exception:
            pass
    if "h2o_fa" not in maint_elem_columns:
        try:
            cursor.execute("ALTER TABLE maintenance_elements ADD COLUMN h2o_fa REAL")
        except Exception:
            pass
    if "so2_fa" not in maint_elem_columns:
        try:
            cursor.execute("ALTER TABLE maintenance_elements ADD COLUMN so2_fa REAL")
        except Exception:
            pass
    # Phase B
    if "sf6_n2_fb" not in maint_elem_columns:
        try:
            cursor.execute("ALTER TABLE maintenance_elements ADD COLUMN sf6_n2_fb REAL")
        except Exception:
            pass
    if "h2o_fb" not in maint_elem_columns:
        try:
            cursor.execute("ALTER TABLE maintenance_elements ADD COLUMN h2o_fb REAL")
        except Exception:
            pass
    if "so2_fb" not in maint_elem_columns:
        try:
            cursor.execute("ALTER TABLE maintenance_elements ADD COLUMN so2_fb REAL")
        except Exception:
            pass
    # Phase C
    if "sf6_n2_fc" not in maint_elem_columns:
        try:
            cursor.execute("ALTER TABLE maintenance_elements ADD COLUMN sf6_n2_fc REAL")
        except Exception:
            pass
    if "h2o_fc" not in maint_elem_columns:
        try:
            cursor.execute("ALTER TABLE maintenance_elements ADD COLUMN h2o_fc REAL")
        except Exception:
            pass
    if "so2_fc" not in maint_elem_columns:
        try:
            cursor.execute("ALTER TABLE maintenance_elements ADD COLUMN so2_fc REAL")
        except Exception:
            pass

    # Vacuum Check (VIDAR) measurements (for Vacuum breakers only)
    if "vidar_fa" not in maint_elem_columns:
        try:
            cursor.execute("ALTER TABLE maintenance_elements ADD COLUMN vidar_fa REAL")
        except Exception:
            pass
    if "vidar_fb" not in maint_elem_columns:
        try:
            cursor.execute("ALTER TABLE maintenance_elements ADD COLUMN vidar_fb REAL")
        except Exception:
            pass
    if "vidar_fc" not in maint_elem_columns:
        try:
            cursor.execute("ALTER TABLE maintenance_elements ADD COLUMN vidar_fc REAL")
        except Exception:
            pass

    # Add model_version column to element_models table
    cursor.execute("PRAGMA table_info(element_models)")
    model_columns = [column[1] for column in cursor.fetchall()]
    if "sf6_capacity_kg" not in model_columns:
        try:
            cursor.execute("ALTER TABLE element_models ADD COLUMN sf6_capacity_kg REAL")
        except Exception:
            pass
    # Add rated power (power_mva) to element_models so the model can carry the
    # transformer's rated power. Elements will read from the model when present.
    if "power_mva" not in model_columns:
        try:
            cursor.execute("ALTER TABLE element_models ADD COLUMN power_mva REAL")
        except Exception:
            pass
    if "model_version" not in model_columns:
        try:
            cursor.execute(
                'ALTER TABLE element_models ADD COLUMN model_version TEXT DEFAULT ""'
            )
        except Exception:
            pass
    if "manual_pdf" not in model_columns:
        try:
            cursor.execute("ALTER TABLE element_models ADD COLUMN manual_pdf TEXT")
        except Exception:
            pass

    cursor.execute("PRAGMA table_info(elements)")
    elem_columns = [column[1] for column in cursor.fetchall()]
    if elem_columns and "serial_number" not in elem_columns:
        try:
            cursor.execute(
                'ALTER TABLE elements ADD COLUMN serial_number TEXT DEFAULT ""'
            )
        except Exception:
            pass
    if elem_columns and "maintenance_date" not in elem_columns:
        try:
            cursor.execute(
                'ALTER TABLE elements ADD COLUMN maintenance_date TEXT DEFAULT ""'
            )
        except Exception:
            pass
    if elem_columns and "voltage_level" not in elem_columns:
        try:
            cursor.execute(
                'ALTER TABLE elements ADD COLUMN voltage_level TEXT DEFAULT ""'
            )
        except Exception:
            pass
    if elem_columns and "manufacturer" not in elem_columns:
        try:
            cursor.execute(
                'ALTER TABLE elements ADD COLUMN manufacturer TEXT DEFAULT ""'
            )
        except Exception:
            pass
    if elem_columns and "type" not in elem_columns:
        try:
            cursor.execute('ALTER TABLE elements ADD COLUMN type TEXT DEFAULT ""')
        except Exception:
            pass

    # Migration: Split circuit breaker types from 'Διακόπτης ΜΤ/ΥΤ' to separate MV and HV types
    # Rename existing 'Διακόπτης ΜΤ/ΥΤ' to 'Διακόπτης ΥΤ' (HV) throughout the database
    try:
        # Update element_models table
        cursor.execute("""
            UPDATE element_models 
            SET element_category = 'Διακόπτης ΥΤ' 
            WHERE element_category = 'Διακόπτης ΜΤ/ΥΤ'
        """)

        # Update elements table
        cursor.execute("""
            UPDATE elements 
            SET element_type = 'Διακόπτης ΥΤ' 
            WHERE element_type = 'Διακόπτης ΜΤ/ΥΤ'
        """)

        conn.commit()
    except Exception:
        pass

    # Add OneDrive links for model manuals and maintenance media
    cursor.execute("PRAGMA table_info(element_models)")
    em_columns = [column[1] for column in cursor.fetchall()]
    if "onedrive_manual_link" not in em_columns:
        try:
            cursor.execute(
                'ALTER TABLE element_models ADD COLUMN onedrive_manual_link TEXT'
            )
        except Exception:
            pass

    if "onedrive_media_folder_link" not in maint_columns:
        try:
            cursor.execute(
                'ALTER TABLE maintenance ADD COLUMN onedrive_media_folder_link TEXT'
            )
        except Exception:
            pass

    cursor.execute("PRAGMA table_info(isolation_requests)")
    isolation_columns = [column[1] for column in cursor.fetchall()]
    if "request_file_path" not in isolation_columns:
        try:
            cursor.execute('ALTER TABLE isolation_requests ADD COLUMN request_file_path TEXT')
        except Exception:
            pass
    if "storage_folder_path" not in isolation_columns:
        try:
            cursor.execute('ALTER TABLE isolation_requests ADD COLUMN storage_folder_path TEXT')
        except Exception:
            pass

    try:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_maintenance_isolation_request ON maintenance(isolation_request_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_isolation_request_elements_request ON isolation_request_elements(request_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_isolation_request_elements_element ON isolation_request_elements(element_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_isolation_requests_substation_dates ON isolation_requests(substation_id, start_datetime, end_datetime)"
        )
    except Exception:
        pass

    conn.commit()
    return conn
