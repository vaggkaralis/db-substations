"""
Flask API Server for DB Substations - shared backend for Windows and Android apps
Production-ready with cloud deployment support
"""
from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_cors import CORS
import sqlite3
import json
import os
import logging
from datetime import datetime
try:
    import psycopg2
    from psycopg2.extras import DictCursor
except Exception:
    psycopg2 = None
    DictCursor = None

app = Flask(__name__)
CORS(app)

# Configuration - supports both local and cloud environments
class Config:
    """Base configuration"""
    DEBUG = False
    TESTING = False
    LOG_LEVEL = 'INFO'
    
    # Database path - override in environment
    DATABASE = os.environ.get('DATABASE_PATH', 'substations.db')
    
    # CORS settings
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*').split(',')

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    LOG_LEVEL = 'DEBUG'

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    LOG_LEVEL = 'INFO'
    # Make sure persistent database location
    DATABASE = os.environ.get('DATABASE_PATH', '/data/substations.db')

# Select config based on environment
config_name = os.environ.get('FLASK_ENV', 'development')
if config_name == 'production':
    app.config.from_object(ProductionConfig)
else:
    app.config.from_object(DevelopmentConfig)

# Setup logging
logging.basicConfig(level=app.config['LOG_LEVEL'])
logger = logging.getLogger(__name__)

# Database selection (SQLite vs PostgreSQL)
DATABASE_URL = os.environ.get('DATABASE_URL')
DB_BACKEND = 'postgres' if DATABASE_URL else 'sqlite'

# Database path from config (SQLite) or URL (PostgreSQL)
DATABASE = DATABASE_URL if DB_BACKEND == 'postgres' else app.config['DATABASE']


def _convert_qmark_sql(query: str) -> str:
    """Convert SQLite-style '?' placeholders to psycopg2 '%s' placeholders."""
    if DB_BACKEND != 'postgres':
        return query
    query = query.replace("datetime('now')", 'CURRENT_TIMESTAMP')
    out = []
    in_single = False
    in_double = False
    for ch in query:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        if ch == '?' and not in_single and not in_double:
            out.append('%s')
        else:
            out.append(ch)
    return ''.join(out)


class QmarkDictCursor(DictCursor):
    """Cursor that accepts SQLite-style '?' placeholders."""
    def execute(self, query, vars=None):
        return super().execute(_convert_qmark_sql(query), vars)

    def executemany(self, query, vars_list):
        return super().executemany(_convert_qmark_sql(query), vars_list)

# Initialize database on module load (important for gunicorn)
def _table_exists(conn, table_name):
    cur = conn.cursor()
    if DB_BACKEND == 'postgres':
        cur.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = ?
            """,
            (table_name,)
        )
    else:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    return bool(cur.fetchone())


def _apply_schema(conn):
    c = conn.cursor()

    if DB_BACKEND == 'postgres':
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
    else:
        schema = [
            """
            CREATE TABLE IF NOT EXISTS element_models (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                is_main_switch INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (substation_id) REFERENCES substations(id),
                UNIQUE(substation_id, name)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS maintenance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                email TEXT,
                report_receiver INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS maintenance_people (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                maintenance_id INTEGER NOT NULL,
                person_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                FOREIGN KEY (maintenance_id) REFERENCES maintenance(id) ON DELETE CASCADE,
                FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS inspections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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


def init_database():
    """Initialize database if it doesn't exist"""
    try:
        conn = get_db()
        if not _table_exists(conn, 'substations'):
            logger.info("Database tables not found, creating schema")
        else:
            logger.info("Database tables already exist")

        _apply_schema(conn)

        # Ensure TEST substation exists (cloud seed)
        c = conn.cursor()
        c.execute("SELECT id FROM substations WHERE name=?", ('TEST',))
        if not c.fetchone():
            c.execute(
                "INSERT INTO substations (name, location, adoption_date, division) VALUES (?, ?, ?, ?)",
                ('TEST', '', '', 'ΤΜΘ')
            )

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}", exc_info=True)
        raise

# Initialize database when module loads
init_database()

def get_db():
    """Get database connection with error handling"""
    try:
        if DB_BACKEND == 'postgres':
            if psycopg2 is None:
                raise RuntimeError('psycopg2 is required for PostgreSQL connections')
            connect_kwargs = {}
            if DATABASE and 'sslmode=' not in DATABASE:
                connect_kwargs['sslmode'] = 'require'
            conn = psycopg2.connect(DATABASE, cursor_factory=QmarkDictCursor, **connect_kwargs)
            return conn

        # SQLite path
        db_dir = os.path.dirname(DATABASE)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        logger.error(f"Database connection error: {str(e)}")
        raise

def _get_table_columns(conn, table_name):
    cur = conn.cursor()
    if DB_BACKEND == 'postgres':
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ?
            """,
            (table_name,)
        )
        rows = cur.fetchall()
        columns = set()
        for row in rows:
            if isinstance(row, dict):
                columns.add(row.get('column_name'))
            else:
                columns.add(row[0])
        return columns

    cur.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cur.fetchall()}


def _insert_and_get_id(cursor, sql, params):
    if DB_BACKEND == 'postgres':
        sql = sql.strip().rstrip(';')
        if 'RETURNING' not in sql.upper():
            sql = f"{sql} RETURNING id"
        cursor.execute(sql, params)
        row = cursor.fetchone()
        if isinstance(row, dict):
            return row.get('id')
        return row[0]
    cursor.execute(sql, params)
    return cursor.lastrowid

def _fetch_substations(conn):
    c = conn.cursor()
    c.execute("SELECT id, name FROM substations ORDER BY name")
    return [dict(row) for row in c.fetchall()]


# ==================== WEB UI ROUTES ====================

@app.route('/')
def web_index():
    """Simple web UI for substations list."""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id, name, location, adoption_date, division FROM substations ORDER BY name")
        substations = []

        for row in c.fetchall():
            substation = dict(row)
            c.execute("SELECT COUNT(*) as count FROM maintenance WHERE substation_id = ?", (row['id'],))
            maint_result = c.fetchone()
            substation['maintenance_count'] = maint_result['count'] if maint_result else 0
            c.execute("SELECT MAX(date_time) as last_maintenance FROM maintenance WHERE substation_id = ?", (row['id'],))
            last_result = c.fetchone()
            substation['last_maintenance'] = last_result['last_maintenance'] if last_result else None
            substations.append(substation)

        conn.close()
        return render_template('index.html', substations=substations)
    except Exception as e:
        logger.error(f"Web index error: {str(e)}", exc_info=True)
        return f"Web UI error: {str(e)}", 500


@app.route('/maintenance')
def web_maintenance():
    try:
        conn = get_db()
        maint_cols = _get_table_columns(conn, 'maintenance')

        base_fields = [
            'm.id',
            'm.substation_id',
            'm.date_time',
            'm.overall_comments',
            's.name as substation_name'
        ]
        if 'maintenance_type' in maint_cols:
            base_fields.append('m.maintenance_type')
        if 'user_name' in maint_cols:
            base_fields.append('m.user_name')

        query = f"""
            SELECT {', '.join(base_fields)}
            FROM maintenance m
            JOIN substations s ON m.substation_id = s.id
            ORDER BY m.date_time DESC
        """

        c = conn.cursor()
        c.execute(query)
        maintenance_rows = [dict(row) for row in c.fetchall()]
        conn.close()
        return render_template('maintenance.html', maintenance=maintenance_rows)
    except Exception as e:
        logger.error(f"Web maintenance error: {str(e)}", exc_info=True)
        return f"Web UI error: {str(e)}", 500


@app.route('/inspections')
def web_inspections():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT id, substation_name, inspection_date, month_key, source_file, created_at
            FROM inspections
            ORDER BY inspection_date DESC
        """)
        inspections = [dict(row) for row in c.fetchall()]
        conn.close()
        return render_template('inspections.html', inspections=inspections)
    except Exception as e:
        logger.error(f"Web inspections error: {str(e)}", exc_info=True)
        return f"Web UI error: {str(e)}", 500


@app.route('/isolation')
def web_isolation():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT ir.id, ir.substation_id, s.name as substation_name,
                   ir.start_datetime, ir.end_datetime, ir.status, ir.notes,
                   ir.created_at, ir.updated_at
            FROM isolation_requests ir
            JOIN substations s ON ir.substation_id = s.id
            ORDER BY ir.created_at DESC
        """)
        requests_list = [dict(row) for row in c.fetchall()]
        conn.close()
        return render_template('isolation.html', requests=requests_list)
    except Exception as e:
        logger.error(f"Web isolation error: {str(e)}", exc_info=True)
        return f"Web UI error: {str(e)}", 500


@app.route('/models')
def web_models():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT id, element_category, model_name, manufacturer,
                   maintenance_cycle, installation_space, breaker_category
            FROM element_models
            ORDER BY element_category, model_name
        """)
        models = [dict(row) for row in c.fetchall()]
        conn.close()
        return render_template('models.html', models=models)
    except Exception as e:
        logger.error(f"Web models error: {str(e)}", exc_info=True)
        return f"Web UI error: {str(e)}", 500


@app.route('/people')
def web_people():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT id, name, role, email, report_receiver, active
            FROM people
            ORDER BY active DESC, name
        """)
        people = [dict(row) for row in c.fetchall()]
        conn.close()
        return render_template('people.html', people=people)
    except Exception as e:
        logger.error(f"Web people error: {str(e)}", exc_info=True)
        return f"Web UI error: {str(e)}", 500


@app.route('/import')
def web_import():
    return render_template('import.html')


@app.route('/inspections/<int:inspection_id>')
def web_inspection_detail(inspection_id):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT id, substation_id, substation_name, inspection_date,
                   month_key, data_json, source_file, created_at
            FROM inspections
            WHERE id = ?
        """, (inspection_id,))
        inspection = c.fetchone()
        if not inspection:
            conn.close()
            return "Inspection not found", 404

        try:
            data = json.loads(inspection['data_json'] or '{}')
        except Exception:
            data = {}

        fields = data.get('fields', []) if isinstance(data, dict) else []
        conn.close()
        return render_template('inspection_detail.html', inspection=dict(inspection), fields=fields)
    except Exception as e:
        logger.error(f"Web inspection detail error: {str(e)}", exc_info=True)
        return f"Web UI error: {str(e)}", 500


@app.route('/maintenance/<int:maintenance_id>')
def web_maintenance_detail(maintenance_id):
    try:
        conn = get_db()
        maint_cols = _get_table_columns(conn, 'maintenance')

        base_fields = [
            'm.id',
            'm.substation_id',
            'm.date_time',
            'm.overall_comments',
            's.name as substation_name',
            's.location as substation_location',
            's.division as substation_division'
        ]
        if 'maintenance_type' in maint_cols:
            base_fields.append('m.maintenance_type')
        if 'user_name' in maint_cols:
            base_fields.append('m.user_name')

        query = f"""
            SELECT {', '.join(base_fields)}
            FROM maintenance m
            JOIN substations s ON m.substation_id = s.id
            WHERE m.id = ?
        """

        c = conn.cursor()
        c.execute(query, (maintenance_id,))
        maintenance = c.fetchone()
        if not maintenance:
            conn.close()
            return "Maintenance not found", 404

        c.execute("""
            SELECT id, name, element_type
            FROM elements
            WHERE substation_id = ?
            ORDER BY element_type, name
        """, (maintenance['substation_id'],))
        elements_for_add = [dict(row) for row in c.fetchall()]

        c.execute("""
            SELECT me.*, e.element_type, e.name, e.serial_number, e.manufacturer, e.model,
                   e.breaker_category
            FROM maintenance_elements me
            JOIN elements e ON me.element_id = e.id
            WHERE me.maintenance_id = ?
            ORDER BY e.element_type, e.name
        """, (maintenance_id,))
        element_rows = [dict(row) for row in c.fetchall()]

        measurement_cols = {
            'insulation_closed_fa_ground', 'insulation_closed_fb_ground', 'insulation_closed_fc_ground',
            'insulation_open_fa_fa', 'insulation_open_fb_fb', 'insulation_open_fc_fc',
            'contact_resistance_fa_fa', 'contact_resistance_fb_fb', 'contact_resistance_fc_fc',
            'operations_count',
            'sf6_n2_fa', 'h2o_fa', 'so2_fa',
            'sf6_n2_fb', 'h2o_fb', 'so2_fb',
            'sf6_n2_fc', 'h2o_fc', 'so2_fc',
            'vidar_fa', 'vidar_fb', 'vidar_fc'
        }

        for elem in element_rows:
            elem['has_measurements'] = any(
                (col in elem) and (elem[col] not in (None, ''))
                for col in measurement_cols
            )

        conn.close()
        return render_template(
            'maintenance_detail.html',
            maintenance=dict(maintenance),
            elements=element_rows,
            elements_for_add=elements_for_add
        )
    except Exception as e:
        logger.error(f"Web maintenance detail error: {str(e)}", exc_info=True)
        return f"Web UI error: {str(e)}", 500


@app.route('/substations/<int:substation_id>')
def web_substation_detail(substation_id):
    """Web UI for substation details."""
    try:
        conn = get_db()
        c = conn.cursor()

        c.execute("SELECT id, name, location, adoption_date, division FROM substations WHERE id = ?", (substation_id,))
        substation = c.fetchone()
        if not substation:
            conn.close()
            return "Substation not found", 404

        c.execute("""
            SELECT id, element_type, name, serial_number, maintenance_date, manufacturer, model,
                   breaker_category, installation_space, operating_status, maintenance_cycle, manufacture_year
            FROM elements
            WHERE substation_id = ?
            ORDER BY element_type, name
        """, (substation_id,))
        elements = [dict(row) for row in c.fetchall()]

        c.execute("""
            SELECT id, date_time, overall_comments
            FROM maintenance
            WHERE substation_id = ?
            ORDER BY date_time DESC
        """, (substation_id,))
        maintenance = [dict(row) for row in c.fetchall()]

        conn.close()
        return render_template('substation.html', substation=dict(substation), elements=elements, maintenance=maintenance)
    except Exception as e:
        logger.error(f"Web substation error: {str(e)}", exc_info=True)
        return f"Web UI error: {str(e)}", 500

# ==================== WEB UI CRUD ====================

@app.route('/substations/add', methods=['GET', 'POST'])
def web_substation_add():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        location = request.form.get('location', '').strip()
        adoption_date = request.form.get('adoption_date', '').strip()
        division = request.form.get('division', 'ΤΜΘ').strip()
        if not name:
            return "Name required", 400
        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT INTO substations (name, location, adoption_date, division) VALUES (?, ?, ?, ?)",
                  (name, location, adoption_date, division))
        conn.commit()
        conn.close()
        return redirect(url_for('web_index'))
    return render_template('substation_form.html', substation=None)


@app.route('/substations/<int:substation_id>/edit', methods=['GET', 'POST'])
def web_substation_edit(substation_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM substations WHERE id = ?", (substation_id,))
    substation = c.fetchone()
    if not substation:
        conn.close()
        return "Substation not found", 404
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        location = request.form.get('location', '').strip()
        adoption_date = request.form.get('adoption_date', '').strip()
        division = request.form.get('division', 'ΤΜΘ').strip()
        if not name:
            conn.close()
            return "Name required", 400
        c.execute("UPDATE substations SET name=?, location=?, adoption_date=?, division=? WHERE id=?",
                  (name, location, adoption_date, division, substation_id))
        conn.commit()
        conn.close()
        return redirect(url_for('web_substation_detail', substation_id=substation_id))
    conn.close()
    return render_template('substation_form.html', substation=dict(substation))


@app.route('/substations/<int:substation_id>/delete', methods=['POST'])
def web_substation_delete(substation_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM substations WHERE id = ?", (substation_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('web_index'))


@app.route('/elements/add', methods=['GET', 'POST'])
def web_element_add():
    conn = get_db()
    substations = _fetch_substations(conn)
    if request.method == 'POST':
        substation_id = request.form.get('substation_id')
        element_type = request.form.get('element_type', '').strip()
        name = request.form.get('name', '').strip()
        serial_number = request.form.get('serial_number', '').strip()
        manufacturer = request.form.get('manufacturer', '').strip()
        model = request.form.get('model', '').strip()
        breaker_category = request.form.get('breaker_category', '').strip()
        operating_status = request.form.get('operating_status', 'Ενεργή').strip()
        maintenance_cycle = request.form.get('maintenance_cycle', '').strip()
        manufacture_year = request.form.get('manufacture_year', '').strip()
        voltage_level = request.form.get('voltage_level', '').strip()
        gate = request.form.get('gate', '').strip()
        if not substation_id or not name:
            conn.close()
            return "Substation and name required", 400
        c = conn.cursor()
        c.execute("""
            INSERT INTO elements (
                substation_id, element_type, name, serial_number, manufacturer, model,
                breaker_category, operating_status, maintenance_cycle, manufacture_year,
                voltage_level, gate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            substation_id, element_type, name, serial_number, manufacturer, model,
            breaker_category, operating_status, maintenance_cycle or None, manufacture_year,
            voltage_level, gate
        ))
        conn.commit()
        conn.close()
        return redirect(url_for('web_substation_detail', substation_id=substation_id))
    conn.close()
    return render_template('element_form.html', element=None, substations=substations, selected_substation=request.args.get('substation_id'))


@app.route('/elements/<int:element_id>/edit', methods=['GET', 'POST'])
def web_element_edit(element_id):
    conn = get_db()
    substations = _fetch_substations(conn)
    c = conn.cursor()
    c.execute("SELECT * FROM elements WHERE id = ?", (element_id,))
    element = c.fetchone()
    if not element:
        conn.close()
        return "Element not found", 404
    if request.method == 'POST':
        substation_id = request.form.get('substation_id')
        element_type = request.form.get('element_type', '').strip()
        name = request.form.get('name', '').strip()
        serial_number = request.form.get('serial_number', '').strip()
        manufacturer = request.form.get('manufacturer', '').strip()
        model = request.form.get('model', '').strip()
        breaker_category = request.form.get('breaker_category', '').strip()
        operating_status = request.form.get('operating_status', 'Ενεργή').strip()
        maintenance_cycle = request.form.get('maintenance_cycle', '').strip()
        manufacture_year = request.form.get('manufacture_year', '').strip()
        voltage_level = request.form.get('voltage_level', '').strip()
        gate = request.form.get('gate', '').strip()
        if not substation_id or not name:
            conn.close()
            return "Substation and name required", 400
        c.execute("""
            UPDATE elements SET substation_id=?, element_type=?, name=?, serial_number=?,
                manufacturer=?, model=?, breaker_category=?, operating_status=?,
                maintenance_cycle=?, manufacture_year=?, voltage_level=?, gate=?
            WHERE id=?
        """, (
            substation_id, element_type, name, serial_number, manufacturer, model,
            breaker_category, operating_status, maintenance_cycle or None, manufacture_year,
            voltage_level, gate, element_id
        ))
        conn.commit()
        conn.close()
        return redirect(url_for('web_substation_detail', substation_id=substation_id))
    conn.close()
    return render_template('element_form.html', element=dict(element), substations=substations, selected_substation=str(element['substation_id']))


@app.route('/elements/<int:element_id>/delete', methods=['POST'])
def web_element_delete(element_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT substation_id FROM elements WHERE id = ?", (element_id,))
    row = c.fetchone()
    substation_id = row['substation_id'] if row else None
    c.execute("DELETE FROM elements WHERE id = ?", (element_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('web_substation_detail', substation_id=substation_id))


@app.route('/maintenance/add', methods=['GET', 'POST'])
def web_maintenance_add():
    conn = get_db()
    substations = _fetch_substations(conn)
    if request.method == 'POST':
        substation_id = request.form.get('substation_id')
        date_time = request.form.get('date_time', '').strip()
        overall_comments = request.form.get('overall_comments', '').strip()
        maintenance_type = request.form.get('maintenance_type', '').strip()
        user_name = request.form.get('user_name', '').strip()
        name = request.form.get('name', '').strip()
        if not substation_id or not date_time:
            conn.close()
            return "Substation and date required", 400
        c = conn.cursor()
        maintenance_id = _insert_and_get_id(
            c,
            """
            INSERT INTO maintenance (substation_id, date_time, overall_comments, maintenance_type, user_name, name)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (substation_id, date_time, overall_comments, maintenance_type, user_name, name)
        )
        conn.commit()
        conn.close()
        return redirect(url_for('web_maintenance_detail', maintenance_id=maintenance_id))
    conn.close()
    return render_template('maintenance_form.html', substations=substations)


@app.route('/maintenance/<int:maintenance_id>/add-element', methods=['POST'])
def web_maintenance_add_element(maintenance_id):
    conn = get_db()
    c = conn.cursor()
    element_id = request.form.get('element_id')
    element_comments = request.form.get('element_comments', '').strip()
    if not element_id:
        conn.close()
        return "Element required", 400
    c.execute("INSERT INTO maintenance_elements (maintenance_id, element_id, element_comments) VALUES (?, ?, ?)",
              (maintenance_id, element_id, element_comments))
    conn.commit()
    conn.close()
    return redirect(url_for('web_maintenance_detail', maintenance_id=maintenance_id))


@app.route('/maintenance/<int:maintenance_id>/delete', methods=['POST'])
def web_maintenance_delete(maintenance_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM maintenance WHERE id = ?", (maintenance_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('web_maintenance'))


@app.route('/inspections/add', methods=['GET', 'POST'])
def web_inspections_add():
    if request.method == 'POST':
        substation_name = request.form.get('substation_name', '').strip()
        inspection_date = request.form.get('inspection_date', '').strip()
        month_key = request.form.get('month_key', '').strip()
        notes = request.form.get('notes', '').strip()
        data_json = json.dumps({'fields': [{'label': 'Σχόλια', 'value': notes}]}, ensure_ascii=False)
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO inspections (substation_name, inspection_date, month_key, data_json, source_file, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (substation_name, inspection_date, month_key, data_json, 'web-entry'))
        conn.commit()
        conn.close()
        return redirect(url_for('web_inspections'))
    return render_template('inspection_form.html')


@app.route('/inspections/<int:inspection_id>/delete', methods=['POST'])
def web_inspections_delete(inspection_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM inspections WHERE id = ?", (inspection_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('web_inspections'))


@app.route('/isolation/add', methods=['GET', 'POST'])
def web_isolation_add():
    conn = get_db()
    substations = _fetch_substations(conn)
    if request.method == 'POST':
        substation_id = request.form.get('substation_id')
        start_datetime = request.form.get('start_datetime', '').strip()
        end_datetime = request.form.get('end_datetime', '').strip()
        status = request.form.get('status', 'Requested').strip()
        notes = request.form.get('notes', '').strip()
        if not substation_id or not start_datetime or not end_datetime:
            conn.close()
            return "Fields required", 400
        c = conn.cursor()
        c.execute("""
            INSERT INTO isolation_requests (substation_id, start_datetime, end_datetime, status, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """, (substation_id, start_datetime, end_datetime, status, notes))
        conn.commit()
        conn.close()
        return redirect(url_for('web_isolation'))
    conn.close()
    return render_template('isolation_form.html', substations=substations)


@app.route('/isolation/<int:request_id>/delete', methods=['POST'])
def web_isolation_delete(request_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM isolation_requests WHERE id = ?", (request_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('web_isolation'))


@app.route('/people/add', methods=['GET', 'POST'])
def web_people_add():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        role = request.form.get('role', '').strip()
        email = request.form.get('email', '').strip()
        report_receiver = 1 if request.form.get('report_receiver') == 'on' else 0
        active = 1 if request.form.get('active') == 'on' else 0
        if not name or not role:
            return "Name and role required", 400
        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT INTO people (name, role, email, report_receiver, active) VALUES (?, ?, ?, ?, ?)",
                  (name, role, email, report_receiver, active))
        conn.commit()
        conn.close()
        return redirect(url_for('web_people'))
    return render_template('people_form.html', person=None)


@app.route('/people/<int:person_id>/edit', methods=['GET', 'POST'])
def web_people_edit(person_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM people WHERE id = ?", (person_id,))
    person = c.fetchone()
    if not person:
        conn.close()
        return "Person not found", 404
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        role = request.form.get('role', '').strip()
        email = request.form.get('email', '').strip()
        report_receiver = 1 if request.form.get('report_receiver') == 'on' else 0
        active = 1 if request.form.get('active') == 'on' else 0
        if not name or not role:
            conn.close()
            return "Name and role required", 400
        c.execute("UPDATE people SET name=?, role=?, email=?, report_receiver=?, active=? WHERE id=?",
                  (name, role, email, report_receiver, active, person_id))
        conn.commit()
        conn.close()
        return redirect(url_for('web_people'))
    conn.close()
    return render_template('people_form.html', person=dict(person))


@app.route('/people/<int:person_id>/delete', methods=['POST'])
def web_people_delete(person_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM people WHERE id = ?", (person_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('web_people'))


@app.route('/models/add', methods=['GET', 'POST'])
def web_models_add():
    if request.method == 'POST':
        element_category = request.form.get('element_category', '').strip()
        model_name = request.form.get('model_name', '').strip()
        manufacturer = request.form.get('manufacturer', '').strip()
        maintenance_cycle = request.form.get('maintenance_cycle', '').strip()
        installation_space = request.form.get('installation_space', '').strip()
        breaker_category = request.form.get('breaker_category', '').strip()
        if not element_category or not model_name:
            return "Category and model required", 400
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO element_models (element_category, model_name, manufacturer, maintenance_cycle, installation_space, breaker_category)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (element_category, model_name, manufacturer, maintenance_cycle or None, installation_space, breaker_category))
        conn.commit()
        conn.close()
        return redirect(url_for('web_models'))
    return render_template('model_form.html', model=None)


@app.route('/models/<int:model_id>/edit', methods=['GET', 'POST'])
def web_models_edit(model_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM element_models WHERE id = ?", (model_id,))
    model = c.fetchone()
    if not model:
        conn.close()
        return "Model not found", 404
    if request.method == 'POST':
        element_category = request.form.get('element_category', '').strip()
        model_name = request.form.get('model_name', '').strip()
        manufacturer = request.form.get('manufacturer', '').strip()
        maintenance_cycle = request.form.get('maintenance_cycle', '').strip()
        installation_space = request.form.get('installation_space', '').strip()
        breaker_category = request.form.get('breaker_category', '').strip()
        if not element_category or not model_name:
            conn.close()
            return "Category and model required", 400
        c.execute("""
            UPDATE element_models SET element_category=?, model_name=?, manufacturer=?,
                maintenance_cycle=?, installation_space=?, breaker_category=?
            WHERE id=?
        """, (element_category, model_name, manufacturer, maintenance_cycle or None, installation_space, breaker_category, model_id))
        conn.commit()
        conn.close()
        return redirect(url_for('web_models'))
    conn.close()
    return render_template('model_form.html', model=dict(model))


@app.route('/models/<int:model_id>/delete', methods=['POST'])
def web_models_delete(model_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM element_models WHERE id = ?", (model_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('web_models'))

# ==================== SUBSTATIONS ENDPOINTS ====================

@app.route('/api/substations', methods=['GET'])
def get_substations():
    """Get all substations with maintenance statistics"""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id, name, location, adoption_date FROM substations ORDER BY name")
        substations = []
        
        for row in c.fetchall():
            substation = dict(row)
            
            # Add maintenance count
            c.execute("SELECT COUNT(*) as count FROM maintenance WHERE substation_id = ?", (row['id'],))
            maint_result = c.fetchone()
            substation['maintenance_count'] = maint_result['count'] if maint_result else 0
            
            # Add last maintenance date
            c.execute("SELECT MAX(date_time) as last_maintenance FROM maintenance WHERE substation_id = ?", (row['id'],))
            last_result = c.fetchone()
            substation['last_maintenance'] = last_result['last_maintenance'] if last_result else None
            
            substations.append(substation)
        
        conn.close()
        return jsonify({'success': True, 'data': substations})
    except Exception as e:
        logger.error(f"Error fetching substations: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/substations', methods=['POST'])
def add_substation():
    """Add a new substation"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        location = data.get('location', '').strip()
        adoption_date = data.get('adoption_date', '').strip()
        division = data.get('division', 'ΤΜΘ').strip()
        
        if not name:
            return jsonify({'success': False, 'error': 'Name is required'}), 400
        
        conn = get_db()
        c = conn.cursor()
        
        # Check for duplicate
        c.execute("SELECT id FROM substations WHERE name=?", (name,))
        if c.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Substation already exists'}), 400
        
        substation_id = _insert_and_get_id(
            c,
            "INSERT INTO substations (name, location, adoption_date, division) VALUES (?, ?, ?, ?)",
            (name, location, adoption_date, division)
        )
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'Substation "{name}" added successfully',
            'id': substation_id
        }), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/substations/<int:substation_id>', methods=['PUT'])
def update_substation(substation_id):
    """Update a substation"""
    try:
        data = request.get_json()
        location = data.get('location', '').strip()
        adoption_date = data.get('adoption_date', '').strip()
        division = data.get('division', 'ΤΜΘ').strip()
        
        conn = get_db()
        c = conn.cursor()
        c.execute(
            "UPDATE substations SET location=?, adoption_date=?, division=? WHERE id=?",
            (location, adoption_date, division, substation_id)
        )
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Substation updated'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/substations/<int:substation_id>', methods=['DELETE'])
def delete_substation(substation_id):
    """Delete a substation and all its elements"""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM elements WHERE substation_id=?", (substation_id,))
        c.execute("DELETE FROM substations WHERE id=?", (substation_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Substation deleted'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== ELEMENT MODELS ENDPOINTS ====================

@app.route('/api/element_models', methods=['GET'])
def get_element_models():
    """Get all element models, optionally filtered by element_category"""
    try:
        element_category = request.args.get('element_category')
        conn = get_db()
        c = conn.cursor()
        
        if element_category:
            c.execute("SELECT id, element_category, model_name, manufacturer, maintenance_cycle, installation_space, breaker_category FROM element_models WHERE element_category=? ORDER BY model_name", (element_category,))
        else:
            c.execute("SELECT id, element_category, model_name, manufacturer, maintenance_cycle, installation_space, breaker_category FROM element_models ORDER BY element_category, model_name")
        
        models = c.fetchall()
        conn.close()
        
        return jsonify({
            'success': True,
            'models': [
                {
                    'id': m[0],
                    'element_category': m[1],
                    'model_name': m[2],
                    'manufacturer': m[3],
                    'maintenance_cycle': m[4],
                    'installation_space': m[5],
                    'breaker_category': m[6]
                }
                for m in models
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/element_models', methods=['POST'])
def create_element_model():
    """Create a new element model"""
    try:
        data = request.json
        required_fields = ['element_category', 'model_name', 'manufacturer']
        
        # Validate required fields
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400
        
        conn = get_db()
        c = conn.cursor()
        
        # Check for duplicate model (unique constraint)
        c.execute("SELECT id FROM element_models WHERE element_category=? AND model_name=? AND manufacturer=?",
                  (data['element_category'], data['model_name'], data['manufacturer']))
        if c.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Model already exists'}), 400
        
        # Insert new model
        model_id = _insert_and_get_id(
            c,
            """INSERT INTO element_models 
                     (element_category, model_name, manufacturer, maintenance_cycle, installation_space, breaker_category) 
                     VALUES (?, ?, ?, ?, ?, ?)""",
            (
                data['element_category'],
                data['model_name'],
                data['manufacturer'],
                data.get('maintenance_cycle', 0),
                data.get('installation_space', ''),
                data.get('breaker_category', '')
            )
        )
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'model_id': model_id, 'message': 'Model created'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/element_models/<int:model_id>', methods=['PUT'])
def update_element_model(model_id):
    """Update an element model"""
    try:
        data = request.json
        conn = get_db()
        c = conn.cursor()
        
        # Check if model exists
        c.execute("SELECT id FROM element_models WHERE id=?", (model_id,))
        if not c.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Model not found'}), 404
        
        # Update model (element_category cannot be changed to maintain data integrity)
        c.execute("""UPDATE element_models 
                     SET model_name=?, manufacturer=?, maintenance_cycle=?, 
                         installation_space=?, breaker_category=?
                     WHERE id=?""",
                  (
                      data.get('model_name', ''),
                      data.get('manufacturer', ''),
                      data.get('maintenance_cycle', 0),
                      data.get('installation_space', ''),
                      data.get('breaker_category', ''),
                      model_id
                  ))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Model updated'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/element_models/<int:model_id>', methods=['DELETE'])
def delete_element_model(model_id):
    """Delete an element model (only if not in use)"""
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Check if model is in use
        c.execute("SELECT COUNT(*) FROM elements WHERE element_model_id=?", (model_id,))
        count = c.fetchone()[0]
        
        if count > 0:
            conn.close()
            return jsonify({'success': False, 'error': f'Cannot delete model: it is used by {count} element(s)'}), 400
        
        # Delete model
        c.execute("DELETE FROM element_models WHERE id=?", (model_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Model deleted'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== ELEMENTS ENDPOINTS ====================

@app.route('/api/elements', methods=['GET'])
def get_elements():
    """Get all elements, optionally filtered by substation_id"""
    try:
        substation_id = request.args.get('substation_id', type=int)
        conn = get_db()
        c = conn.cursor()
        
        columns = _get_table_columns(conn, 'elements')

        desired = [
            'id', 'substation_id', 'element_type', 'name', 'serial_number', 'maintenance_date',
            'voltage_level', 'manufacturer', 'type', 'element_model_id', 'manufacture_year',
            'model', 'model_version', 'operating_status', 'installation_space', 'maintenance_cycle',
            'gate', 'is_main_switch', 'breaker_category'
        ]

        select_parts = []
        for col in desired:
            if col in columns:
                select_parts.append(col)
            elif col == 'gate' and 'bar' in columns:
                select_parts.append('bar AS gate')
            else:
                select_parts.append(f"NULL AS {col}")

        select_sql = ", ".join(select_parts)

        if substation_id:
            c.execute(
                f"SELECT {select_sql} FROM elements WHERE substation_id=? ORDER BY element_type, name",
                (substation_id,)
            )
        else:
            c.execute(f"SELECT {select_sql} FROM elements ORDER BY element_type, name")
        
        elements = [dict(row) for row in c.fetchall()]
        conn.close()
        return jsonify({'success': True, 'data': elements})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/elements', methods=['POST'])
def add_element():
    """Add a new element"""
    try:
        data = request.get_json()
        substation_id = data.get('substation_id')
        element_type = data.get('element_type', '').strip()
        name = data.get('name', '').strip()
        serial_number = data.get('serial_number', '').strip()
        maintenance_date = data.get('maintenance_date', '').strip()
        voltage_level = data.get('voltage_level', '').strip()
        manufacturer = data.get('manufacturer', '').strip()
        element_type_field = data.get('type', '').strip()  # Renamed to avoid conflict
        breaker_category = data.get('breaker_category', '').strip()
        element_model_id = data.get('element_model_id')
        manufacture_year = data.get('manufacture_year', '').strip()
        model = data.get('model', '').strip()
        model_version = data.get('model_version', '').strip()
        operating_status = data.get('operating_status', 'Ενεργή').strip()
        installation_space = data.get('installation_space', 'Εσωτερικός').strip()
        maintenance_cycle = data.get('maintenance_cycle', 0)
        gate = data.get('gate', '').strip()
        is_main_switch = data.get('is_main_switch', 0)
        
        if not substation_id or not name:
            return jsonify({'success': False, 'error': 'Substation ID and name are required'}), 400
        
        # Validate maintenance_cycle is integer
        try:
            maintenance_cycle = int(maintenance_cycle)
        except (ValueError, TypeError):
            maintenance_cycle = 0
        
        # Validate is_main_switch is integer
        try:
            is_main_switch = int(is_main_switch)
        except (ValueError, TypeError):
            is_main_switch = 0
        
        conn = get_db()
        c = conn.cursor()
        
        # Verify substation exists
        c.execute("SELECT id FROM substations WHERE id=?", (substation_id,))
        if not c.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Substation not found'}), 404
        
        # Check for duplicate name within substation
        c.execute("SELECT id FROM elements WHERE substation_id=? AND name=?", (substation_id, name))
        if c.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': f'Element with name "{name}" already exists in this substation'}), 400
        
        columns = _get_table_columns(conn, 'elements')

        col_values = {
            'substation_id': substation_id,
            'element_type': element_type,
            'name': name,
            'serial_number': serial_number,
            'maintenance_date': maintenance_date,
            'voltage_level': voltage_level,
            'manufacturer': manufacturer,
            'type': element_type_field,
            'breaker_category': breaker_category,
            'element_model_id': element_model_id,
            'manufacture_year': manufacture_year,
            'model': model,
            'model_version': model_version,
            'operating_status': operating_status,
            'installation_space': installation_space,
            'maintenance_cycle': maintenance_cycle,
            'gate': gate,
            'is_main_switch': is_main_switch,
        }

        if 'gate' not in columns and 'bar' in columns:
            col_values['bar'] = gate

        insert_cols = [col for col in col_values.keys() if col in columns]
        insert_vals = [col_values[col] for col in insert_cols]

        placeholders = ', '.join(['?'] * len(insert_cols))
        insert_sql = f"INSERT INTO elements ({', '.join(insert_cols)}) VALUES ({placeholders})"
        element_id = _insert_and_get_id(c, insert_sql, insert_vals)
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'Element "{name}" added successfully',
            'id': element_id
        }), 201
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/elements/<int:element_id>', methods=['DELETE'])
def delete_element(element_id):
    """Delete an element"""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM elements WHERE id=?", (element_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Element deleted'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== MAINTENANCE ENDPOINTS ====================

@app.route('/api/maintenance', methods=['GET'])
def get_maintenance():
    """Get all maintenance records or filter by substation"""
    try:
        conn = get_db()
        c = conn.cursor()
        
        substation_id = request.args.get('substation_id', type=int)
        
        if substation_id:
            c.execute('''
                SELECT m.id, m.substation_id, s.name as substation_name, 
                       m.date_time, m.overall_comments
                FROM maintenance m
                JOIN substations s ON m.substation_id = s.id
                WHERE m.substation_id = ?
                ORDER BY m.date_time DESC
            ''', (substation_id,))
        else:
            c.execute('''
                SELECT m.id, m.substation_id, s.name as substation_name,
                       m.date_time, m.overall_comments
                FROM maintenance m
                JOIN substations s ON m.substation_id = s.id
                ORDER BY m.date_time DESC
            ''')
        
        maintenance_records = []
        for row in c.fetchall():
            maint_dict = dict(row)
            
            # Get elements for this maintenance
            c.execute('''
                SELECT me.id, me.element_id, e.element_type, e.name, 
                       e.serial_number, me.element_comments
                FROM maintenance_elements me
                JOIN elements e ON me.element_id = e.id
                WHERE me.maintenance_id = ?
            ''', (row['id'],))
            
            maint_dict['elements'] = [dict(elem_row) for elem_row in c.fetchall()]
            maintenance_records.append(maint_dict)
        
        conn.close()
        return jsonify({'success': True, 'data': maintenance_records})
    
    except Exception as e:
        logger.error(f"Error fetching maintenance: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/maintenance', methods=['POST'])
def create_maintenance():
    """Create a new maintenance record"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('substation_id'):
            return jsonify({'success': False, 'error': 'substation_id is required'}), 400
        
        if not data.get('date_time'):
            return jsonify({'success': False, 'error': 'date_time is required'}), 400
        
        if not data.get('elements') or len(data['elements']) == 0:
            return jsonify({'success': False, 'error': 'At least one element is required'}), 400
        
        conn = get_db()
        c = conn.cursor()
        
        # Insert maintenance record
        maintenance_id = _insert_and_get_id(
            c,
            '''
            INSERT INTO maintenance (substation_id, date_time, overall_comments)
            VALUES (?, ?, ?)
            ''',
            (
                data['substation_id'],
                data['date_time'],
                data.get('overall_comments', '')
            )
        )
        
        # Insert maintenance elements
        for element in data['elements']:
            c.execute('''
                INSERT INTO maintenance_elements (maintenance_id, element_id, element_comments)
                VALUES (?, ?, ?)
            ''', (
                maintenance_id,
                element['element_id'],
                element.get('element_comments', '')
            ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Created maintenance record {maintenance_id} for substation {data['substation_id']}")
        return jsonify({
            'success': True,
            'data': {'id': maintenance_id}
        }), 201
    
    except sqlite3.IntegrityError as e:
        logger.error(f"Database integrity error: {str(e)}")
        return jsonify({'success': False, 'error': 'Database constraint violation'}), 400
    except Exception as e:
        logger.error(f"Error creating maintenance: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/maintenance/<int:maintenance_id>', methods=['DELETE'])
def delete_maintenance(maintenance_id):
    """Delete a maintenance record"""
    try:
        conn = get_db()
        c = conn.cursor()
        
        # Check if maintenance exists
        c.execute('SELECT id FROM maintenance WHERE id = ?', (maintenance_id,))
        if not c.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Maintenance not found'}), 404
        
        # Delete maintenance (elements will cascade)
        c.execute('DELETE FROM maintenance WHERE id = ?', (maintenance_id,))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Deleted maintenance {maintenance_id}")
        return jsonify({'success': True, 'data': {'deleted_id': maintenance_id}})
    
    except Exception as e:
        logger.error(f"Error deleting maintenance: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== INSPECTIONS ENDPOINTS ====================

def _derive_month_key(inspection_date: str) -> str:
    """Derive YYYY-MM month key from an ISO-like date string."""
    if not inspection_date:
        return datetime.now().strftime('%Y-%m')
    try:
        parsed = datetime.fromisoformat(inspection_date)
        return parsed.strftime('%Y-%m')
    except ValueError:
        try:
            parsed = datetime.strptime(inspection_date, '%Y-%m-%d')
            return parsed.strftime('%Y-%m')
        except ValueError:
            return datetime.now().strftime('%Y-%m')


@app.route('/api/inspections', methods=['GET'])
def get_inspections():
    """Get inspections, optionally filtered by substation_id"""
    try:
        substation_id = request.args.get('substation_id', type=int)
        conn = get_db()
        c = conn.cursor()
        if substation_id:
            c.execute(
                """SELECT id, substation_id, substation_name, inspection_date, month_key,
                          data_json, source_file, created_at
                   FROM inspections WHERE substation_id=? ORDER BY inspection_date DESC""",
                (substation_id,)
            )
        else:
            c.execute(
                """SELECT id, substation_id, substation_name, inspection_date, month_key,
                          data_json, source_file, created_at
                   FROM inspections ORDER BY inspection_date DESC"""
            )
        inspections = [dict(row) for row in c.fetchall()]
        conn.close()
        return jsonify({'success': True, 'data': inspections})
    except Exception as e:
        logger.error(f"Error fetching inspections: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/inspections', methods=['POST'])
def add_inspection():
    """Add a new inspection"""
    try:
        data = request.get_json() or {}
        substation_id = data.get('substation_id')
        substation_name = (data.get('substation_name') or '').strip()
        inspection_date = (data.get('inspection_date') or '').strip()
        month_key = (data.get('month_key') or '').strip()
        notes = (data.get('notes') or '').strip()
        data_json = data.get('data_json')

        if not inspection_date:
            inspection_date = datetime.now().strftime('%Y-%m-%d')

        if not month_key:
            month_key = _derive_month_key(inspection_date)

        conn = get_db()
        c = conn.cursor()

        if substation_id:
            c.execute("SELECT name FROM substations WHERE id=?", (substation_id,))
            row = c.fetchone()
            if not row:
                conn.close()
                return jsonify({'success': False, 'error': 'Substation not found'}), 404
            substation_name = row['name']

        if not substation_name:
            conn.close()
            return jsonify({'success': False, 'error': 'Substation name is required'}), 400

        if data_json is None:
            data_json = json.dumps({'fields': [{'label': 'Σχόλια', 'value': notes}]}, ensure_ascii=False)

        inspection_id = _insert_and_get_id(
            c,
            """INSERT INTO inspections (substation_id, substation_name, inspection_date, month_key,
                      data_json, source_file, created_at)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'))""",
            (substation_id, substation_name, inspection_date, month_key, data_json, 'api-entry')
        )
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'id': inspection_id}), 201
    except Exception as e:
        logger.error(f"Error adding inspection: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== HEALTH CHECK ====================

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    try:
        conn = get_db()
        conn.close()
        return jsonify({'success': True, 'status': 'Server is running'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/reset-database', methods=['POST'])
def reset_database():
    """ADMIN: Reset database with full schema - USE WITH CAUTION!"""
    try:
        if DB_BACKEND == 'postgres':
            return jsonify({'success': False, 'error': 'Reset not supported for PostgreSQL backend'}), 400

        # Require secret key for safety
        data = request.get_json() or {}
        secret = data.get('secret', '')
        
        if secret != os.environ.get('ADMIN_SECRET', 'reset-db-2026'):
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        # Delete old database
        if os.path.exists(DATABASE):
            os.remove(DATABASE)
            logger.info("Deleted old database")
        
        # Initialize new database with full schema
        from database import init_db
        conn = init_db(DATABASE)
        
        # Verify schema
        cursor = conn.cursor()
        columns = list(_get_table_columns(conn, 'elements'))
        conn.close()
        
        logger.info(f"Database reset complete. Elements table has {len(columns)} columns")
        
        return jsonify({
            'success': True,
            'message': 'Database reset successfully',
            'element_columns_count': len(columns)
        })
    except Exception as e:
        logger.error(f"Error resetting database: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    logger.warning(f"404 error: {request.path}")
    return jsonify({'success': False, 'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def server_error(error):
    logger.error(f"500 error: {str(error)}")
    return jsonify({'success': False, 'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Get host and port from environment variables
    # Railway provides PORT, fallback to FLASK_PORT or 5000
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', os.environ.get('FLASK_PORT', 5000)))
    debug = app.config['DEBUG']
    
    logger.info(f"Starting Flask server on {host}:{port}")
    logger.info(f"Environment: {config_name}")
    logger.info(f"Database: {DATABASE}")
    
    # Run server
    app.run(host=host, port=port, debug=debug)
