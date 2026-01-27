"""
Flask API Server for DB Substations - shared backend for Windows and Android apps
Production-ready with cloud deployment support
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import json
import os
from datetime import datetime
import logging

app = Flask(__name__)
CORS(app)

# Configuration - supports both local and cloud environments
class Config:
    """Base configuration"""
    DEBUG = False
    TESTING = False
    LOG_LEVEL = 'INFO'
    
    # Database path - override in environment
    DATABASE = os.environ.get('DATABASE_PATH', 'database.db')
    
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
    DATABASE = os.environ.get('DATABASE_PATH', '/data/database.db')

# Select config based on environment
config_name = os.environ.get('FLASK_ENV', 'development')
if config_name == 'production':
    app.config.from_object(ProductionConfig)
else:
    app.config.from_object(DevelopmentConfig)

# Setup logging
logging.basicConfig(level=app.config['LOG_LEVEL'])
logger = logging.getLogger(__name__)

# Database path from config
DATABASE = app.config['DATABASE']

# Initialize database on module load (important for gunicorn)
def init_database():
    """Initialize database if it doesn't exist"""
    try:
        # Ensure database directory exists FIRST
        db_dir = os.path.dirname(DATABASE)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # Check if tables exist
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='substations'")
        if c.fetchone():
            logger.info("Database tables already exist")
            conn.close()
            return
        
        # Create substations table
        c.execute("""
            CREATE TABLE IF NOT EXISTS substations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                location TEXT,
                adoption_date TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create elements table
        c.execute("""
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
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (substation_id) REFERENCES substations(id),
                UNIQUE(substation_id, name, serial_number)
            )
        """)
        
        # Create maintenance tracking tables
        c.execute("""
            CREATE TABLE IF NOT EXISTS maintenance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                substation_id INTEGER NOT NULL,
                date_time TEXT NOT NULL,
                overall_comments TEXT,
                FOREIGN KEY (substation_id) REFERENCES substations(id) ON DELETE CASCADE
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS maintenance_elements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                maintenance_id INTEGER NOT NULL,
                element_id INTEGER NOT NULL,
                element_comments TEXT,
                FOREIGN KEY (maintenance_id) REFERENCES maintenance(id) ON DELETE CASCADE,
                FOREIGN KEY (element_id) REFERENCES elements(id) ON DELETE CASCADE
            )
        """)
        
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
        # Ensure database directory exists
        db_dir = os.path.dirname(DATABASE)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.OperationalError as e:
        logger.error(f"Database connection error: {str(e)}")
        raise

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
        
        if not name:
            return jsonify({'success': False, 'error': 'Name is required'}), 400
        
        conn = get_db()
        c = conn.cursor()
        
        # Check for duplicate
        c.execute("SELECT id FROM substations WHERE name=?", (name,))
        if c.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Substation already exists'}), 400
        
        c.execute(
            "INSERT INTO substations (name, location, adoption_date) VALUES (?, ?, ?)",
            (name, location, adoption_date)
        )
        conn.commit()
        substation_id = c.lastrowid
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
        
        conn = get_db()
        c = conn.cursor()
        c.execute(
            "UPDATE substations SET location=?, adoption_date=? WHERE id=?",
            (location, adoption_date, substation_id)
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

# ==================== ELEMENTS ENDPOINTS ====================

@app.route('/api/elements', methods=['GET'])
def get_elements():
    """Get all elements, optionally filtered by substation_id"""
    try:
        substation_id = request.args.get('substation_id', type=int)
        conn = get_db()
        c = conn.cursor()
        
        if substation_id:
            c.execute(
                "SELECT id, substation_id, element_type, name, serial_number, maintenance_date, voltage_level, manufacturer, type FROM elements WHERE substation_id=? ORDER BY element_type, name",
                (substation_id,)
            )
        else:
            c.execute("SELECT id, substation_id, element_type, name, serial_number, maintenance_date, voltage_level, manufacturer, type FROM elements ORDER BY element_type, name")
        
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
        elem_type = data.get('type', '').strip()
        
        if not substation_id or not name:
            return jsonify({'success': False, 'error': 'Substation ID and name are required'}), 400
        
        conn = get_db()
        c = conn.cursor()
        
        # Verify substation exists
        c.execute("SELECT id FROM substations WHERE id=?", (substation_id,))
        if not c.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Substation not found'}), 404
        
        c.execute(
            "INSERT INTO elements (substation_id, element_type, name, serial_number, maintenance_date, voltage_level, manufacturer, type) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (substation_id, element_type, name, serial_number, maintenance_date, voltage_level, manufacturer, elem_type)
        )
        conn.commit()
        element_id = c.lastrowid
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
        c.execute('''
            INSERT INTO maintenance (substation_id, date_time, overall_comments)
            VALUES (?, ?, ?)
        ''', (
            data['substation_id'],
            data['date_time'],
            data.get('overall_comments', '')
        ))
        
        maintenance_id = c.lastrowid
        
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
