"""Test substation matching in background thread with PST-like setup"""
import sqlite3
import threading
from database import init_db
from settings import DB_PATH
from maintenance_email_importer import (
    _parse_subject_for_substation_and_date,
    _match_substation_by_name,
    _match_substation_in_text,
)

def test_in_thread():
    """Mimic PST import: create connection in background thread and test matching"""
    print(f"Thread DB_PATH: {DB_PATH}")
    
    # Create connection like PST import does
    conn = init_db(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Check substations exist
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM substations")
    count = c.fetchone()[0]
    print(f"Substations found: {count}")
    
    # Test subjects from failed imports
    test_subjects = [
        "Re: Συντήρηση ΔΙ Υ/Σ Νικήτης 06.02.2026",
        "Αναφορά συνεργείου ΥΣ Παύλου Μελά",
        "Re: Ενημέρωση πύλης 3 Σκύδρα",
        "Re: Κλειστή είσοδος ΥΣ Παύλου Μελά",
        "Συντήρηση ΔΙ Υ/Σ Νικήτης 03.02.2026",
    ]
    
    print("\nTesting substation matching:")
    for subj in test_subjects:
        print(f"\nSubject: {subj}")
        
        # Parse
        parsed, date = _parse_subject_for_substation_and_date(subj)
        print(f"  Parsed name: {parsed}")
        
        # Try match by name
        match1 = _match_substation_by_name(conn, parsed) if parsed else None
        if match1:
            print(f"  ✓ Match by name: {match1['name']}")
        else:
            print(f"  ✗ Match by name: None")
        
        # Try match in text (subject)
        match2 = _match_substation_in_text(conn, subj)
        if match2:
            print(f"  ✓ Match in subject: {match2['name']}")
        else:
            print(f"  ✗ Match in subject: None")
    
    conn.close()
    print("\nDone!")

if __name__ == "__main__":
    print("Testing in main thread:")
    test_in_thread()
    
    print("\n" + "="*60)
    print("Testing in background thread:")
    thread = threading.Thread(target=test_in_thread)
    thread.start()
    thread.join()
