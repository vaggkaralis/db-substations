import sqlite3


def init_db(db_path: str = 'substations.db') -> sqlite3.Connection:
    """Initialize SQLite connection, ensure tables exist, and apply lightweight migrations."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        'CREATE TABLE IF NOT EXISTS substations (id INTEGER PRIMARY KEY, name TEXT, location TEXT, adoption_date TEXT)'
    )
    # Element models master table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS element_models (
            id INTEGER PRIMARY KEY,
            element_category TEXT NOT NULL,
            model_name TEXT NOT NULL,
            manufacturer TEXT,
            maintenance_cycle INTEGER DEFAULT 0,
            installation_space TEXT,
            breaker_category TEXT,
            UNIQUE(element_category, model_name, manufacturer)
        )
    ''')
    
    cursor.execute(
        'CREATE TABLE IF NOT EXISTS elements (id INTEGER PRIMARY KEY, substation_id INTEGER, element_type TEXT, name TEXT, serial_number TEXT, maintenance_date TEXT, voltage_level TEXT, manufacturer TEXT, type TEXT, FOREIGN KEY(substation_id) REFERENCES substations(id))'
    )
    
    # Maintenance tracking tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS maintenance (
            id INTEGER PRIMARY KEY,
            substation_id INTEGER NOT NULL,
            date_time TEXT NOT NULL,
            overall_comments TEXT,
            FOREIGN KEY(substation_id) REFERENCES substations(id) ON DELETE CASCADE
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS maintenance_elements (
            id INTEGER PRIMARY KEY,
            maintenance_id INTEGER NOT NULL,
            element_id INTEGER NOT NULL,
            element_comments TEXT,
            FOREIGN KEY(maintenance_id) REFERENCES maintenance(id) ON DELETE CASCADE,
            FOREIGN KEY(element_id) REFERENCES elements(id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('PRAGMA table_info(substations)')
    sub_columns = [column[1] for column in cursor.fetchall()]
    if 'location' not in sub_columns:
        try:
            cursor.execute('ALTER TABLE substations ADD COLUMN location TEXT DEFAULT ""')
        except Exception:
            pass
    if 'adoption_date' not in sub_columns:
        try:
            cursor.execute('ALTER TABLE substations ADD COLUMN adoption_date TEXT DEFAULT ""')
        except Exception:
            pass
    if 'division' not in sub_columns:
        try:
            cursor.execute('ALTER TABLE substations ADD COLUMN division TEXT DEFAULT "ΤΜΘ"')
        except Exception:
            pass
    if 'last_maintenance' not in sub_columns:
        try:
            cursor.execute('ALTER TABLE substations ADD COLUMN last_maintenance TEXT DEFAULT ""')
        except Exception:
            pass
    
    # Add breaker_category column to elements table
    cursor.execute('PRAGMA table_info(elements)')
    elem_columns = [column[1] for column in cursor.fetchall()]
    if 'breaker_category' not in elem_columns:
        try:
            cursor.execute('ALTER TABLE elements ADD COLUMN breaker_category TEXT DEFAULT ""')
        except Exception:
            pass
    
    # Rename type to model and add new columns
    if 'model' not in elem_columns:
        try:
            # SQLite doesn't support column rename, so we check if old column exists
            if 'type' in elem_columns:
                cursor.execute('ALTER TABLE elements ADD COLUMN model TEXT DEFAULT ""')
                # Copy data from type to model
                cursor.execute('UPDATE elements SET model = type')
            else:
                cursor.execute('ALTER TABLE elements ADD COLUMN model TEXT DEFAULT ""')
        except Exception:
            pass
    
    if 'installation_space' not in elem_columns:
        try:
            cursor.execute('ALTER TABLE elements ADD COLUMN installation_space TEXT DEFAULT ""')
        except Exception:
            pass
    
    if 'operating_status' not in elem_columns:
        try:
            cursor.execute('ALTER TABLE elements ADD COLUMN operating_status TEXT DEFAULT "Ενεργή"')
        except Exception:
            pass
    
    if 'maintenance_cycle' not in elem_columns:
        try:
            cursor.execute('ALTER TABLE elements ADD COLUMN maintenance_cycle INTEGER DEFAULT 0')
        except Exception:
            pass
    
    if 'element_model_id' not in elem_columns:
        try:
            cursor.execute('ALTER TABLE elements ADD COLUMN element_model_id INTEGER REFERENCES element_models(id)')
        except Exception:
            pass
    
    if 'manufacture_year' not in elem_columns:
        try:
            cursor.execute('ALTER TABLE elements ADD COLUMN manufacture_year TEXT DEFAULT ""')
        except Exception:
            pass
    
    if 'model_version' not in elem_columns:
        try:
            cursor.execute('ALTER TABLE elements ADD COLUMN model_version TEXT DEFAULT ""')
        except Exception:
            pass
    
    # Add bar column to elements table for organizing by transformer/bar
    if 'bar' not in elem_columns:
        try:
            cursor.execute('ALTER TABLE elements ADD COLUMN bar TEXT DEFAULT ""')
        except Exception:
            pass
    
    # Add is_main_switch flag to identify main circuit breakers (HV and MV main)
    if 'is_main_switch' not in elem_columns:
        try:
            cursor.execute('ALTER TABLE elements ADD COLUMN is_main_switch INTEGER DEFAULT 0')
        except Exception:
            pass
    
    # Add maintenance_type column to maintenance table
    cursor.execute('PRAGMA table_info(maintenance)')
    maint_columns = [column[1] for column in cursor.fetchall()]
    if 'maintenance_type' not in maint_columns:
        try:
            cursor.execute('ALTER TABLE maintenance ADD COLUMN maintenance_type TEXT DEFAULT "Επαναληπτική συντήρηση"')
        except Exception:
            pass
    
    # Add measurement fields to maintenance_elements table for circuit breakers
    cursor.execute('PRAGMA table_info(maintenance_elements)')
    maint_elem_columns = [column[1] for column in cursor.fetchall()]
    
    # Insulation resistance measurements - Switch closed (to ground)
    if 'insulation_closed_fa_ground' not in maint_elem_columns:
        try:
            cursor.execute('ALTER TABLE maintenance_elements ADD COLUMN insulation_closed_fa_ground REAL')
        except Exception:
            pass
    if 'insulation_closed_fb_ground' not in maint_elem_columns:
        try:
            cursor.execute('ALTER TABLE maintenance_elements ADD COLUMN insulation_closed_fb_ground REAL')
        except Exception:
            pass
    if 'insulation_closed_fc_ground' not in maint_elem_columns:
        try:
            cursor.execute('ALTER TABLE maintenance_elements ADD COLUMN insulation_closed_fc_ground REAL')
        except Exception:
            pass
    
    # Insulation resistance measurements - Switch open (phase to phase)
    if 'insulation_open_fa_fa' not in maint_elem_columns:
        try:
            cursor.execute('ALTER TABLE maintenance_elements ADD COLUMN insulation_open_fa_fa REAL')
        except Exception:
            pass
    if 'insulation_open_fb_fb' not in maint_elem_columns:
        try:
            cursor.execute('ALTER TABLE maintenance_elements ADD COLUMN insulation_open_fb_fb REAL')
        except Exception:
            pass
    if 'insulation_open_fc_fc' not in maint_elem_columns:
        try:
            cursor.execute('ALTER TABLE maintenance_elements ADD COLUMN insulation_open_fc_fc REAL')
        except Exception:
            pass
    
    # Contact resistance measurements - Switch closed (phase to phase)
    if 'contact_resistance_fa_fa' not in maint_elem_columns:
        try:
            cursor.execute('ALTER TABLE maintenance_elements ADD COLUMN contact_resistance_fa_fa REAL')
        except Exception:
            pass
    if 'contact_resistance_fb_fb' not in maint_elem_columns:
        try:
            cursor.execute('ALTER TABLE maintenance_elements ADD COLUMN contact_resistance_fb_fb REAL')
        except Exception:
            pass
    if 'contact_resistance_fc_fc' not in maint_elem_columns:
        try:
            cursor.execute('ALTER TABLE maintenance_elements ADD COLUMN contact_resistance_fc_fc REAL')
        except Exception:
            pass
    
    # Units for each insulation measurement
    if 'insulation_closed_fa_unit' not in maint_elem_columns:
        try:
            cursor.execute('ALTER TABLE maintenance_elements ADD COLUMN insulation_closed_fa_unit TEXT DEFAULT "GΩ"')
        except Exception:
            pass
    if 'insulation_closed_fb_unit' not in maint_elem_columns:
        try:
            cursor.execute('ALTER TABLE maintenance_elements ADD COLUMN insulation_closed_fb_unit TEXT DEFAULT "GΩ"')
        except Exception:
            pass
    if 'insulation_closed_fc_unit' not in maint_elem_columns:
        try:
            cursor.execute('ALTER TABLE maintenance_elements ADD COLUMN insulation_closed_fc_unit TEXT DEFAULT "GΩ"')
        except Exception:
            pass
    if 'insulation_open_fa_unit' not in maint_elem_columns:
        try:
            cursor.execute('ALTER TABLE maintenance_elements ADD COLUMN insulation_open_fa_unit TEXT DEFAULT "GΩ"')
        except Exception:
            pass
    if 'insulation_open_fb_unit' not in maint_elem_columns:
        try:
            cursor.execute('ALTER TABLE maintenance_elements ADD COLUMN insulation_open_fb_unit TEXT DEFAULT "GΩ"')
        except Exception:
            pass
    if 'insulation_open_fc_unit' not in maint_elem_columns:
        try:
            cursor.execute('ALTER TABLE maintenance_elements ADD COLUMN insulation_open_fc_unit TEXT DEFAULT "GΩ"')
        except Exception:
            pass
    
    # Add model_version column to element_models table
    cursor.execute('PRAGMA table_info(element_models)')
    model_columns = [column[1] for column in cursor.fetchall()]
    if 'model_version' not in model_columns:
        try:
            cursor.execute('ALTER TABLE element_models ADD COLUMN model_version TEXT DEFAULT ""')
        except Exception:
            pass

    cursor.execute('PRAGMA table_info(elements)')
    elem_columns = [column[1] for column in cursor.fetchall()]
    if elem_columns and 'serial_number' not in elem_columns:
        try:
            cursor.execute('ALTER TABLE elements ADD COLUMN serial_number TEXT DEFAULT ""')
        except Exception:
            pass
    if elem_columns and 'maintenance_date' not in elem_columns:
        try:
            cursor.execute('ALTER TABLE elements ADD COLUMN maintenance_date TEXT DEFAULT ""')
        except Exception:
            pass
    if elem_columns and 'voltage_level' not in elem_columns:
        try:
            cursor.execute('ALTER TABLE elements ADD COLUMN voltage_level TEXT DEFAULT ""')
        except Exception:
            pass
    if elem_columns and 'manufacturer' not in elem_columns:
        try:
            cursor.execute('ALTER TABLE elements ADD COLUMN manufacturer TEXT DEFAULT ""')
        except Exception:
            pass
    if elem_columns and 'type' not in elem_columns:
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

    conn.commit()
    return conn
