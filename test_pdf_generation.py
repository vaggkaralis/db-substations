"""
Test script for PDF report generation
"""
import sqlite3
from pdf_reports import generate_maintenance_report

# Connect to database
conn = sqlite3.connect('substations.db')
c = conn.cursor()

# Find a maintenance record with a circuit breaker
c.execute("""
    SELECT m.id, e.id, e.name, e.breaker_category
    FROM maintenance m
    JOIN maintenance_elements me ON m.id = me.maintenance_id
    JOIN elements e ON me.element_id = e.id
    WHERE e.breaker_category IN ('SF6', 'Oil', 'Vacuum')
    LIMIT 1
""")

result = c.fetchone()

if result:
    maintenance_id, element_id, element_name, breaker_category = result
    print(f"Found maintenance record:")
    print(f"  Maintenance ID: {maintenance_id}")
    print(f"  Element ID: {element_id}")
    print(f"  Element Name: {element_name}")
    print(f"  Breaker Category: {breaker_category}")
    print()
    
    try:
        pdf_path = generate_maintenance_report(conn, maintenance_id, element_id)
        print(f"✓ PDF generated successfully!")
        print(f"  Path: {pdf_path}")
    except Exception as e:
        print(f"✗ Error generating PDF: {e}")
        import traceback
        traceback.print_exc()
else:
    print("No maintenance records found for circuit breakers")
    print("Please add a maintenance record first using the app")

conn.close()
