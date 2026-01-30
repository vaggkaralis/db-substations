import sqlite3

conn = sqlite3.connect('substations.db')
c = conn.cursor()

print("Motor Drive Elements in ΝΙΚΗΤΗ:")
c.execute('''SELECT e.id, e.name, e.element_type, e.model, e.model_version 
             FROM elements e 
             JOIN substations s ON e.substation_id = s.id 
             WHERE s.name = ? AND e.element_type = ?''', ('ΝΙΚΗΤΗ', 'Motor Drive'))
elements = c.fetchall()
for row in elements:
    print(f"  ID: {row[0]}, Name: {row[1]}, Type: {row[2]}, Model: '{row[3]}', Version: '{row[4]}'")

print("\nMotor Drive Models in element_models:")
c.execute('SELECT id, model_name, model_version FROM element_models WHERE element_category = ?', ('Motor Drive',))
models = c.fetchall()
for row in models:
    print(f"  ID: {row[0]}, Model Name: '{row[1]}', Version: '{row[2]}'")

conn.close()
