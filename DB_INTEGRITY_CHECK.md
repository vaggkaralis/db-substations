# Database Integrity Checker

## Overview

The database integrity checker (`db_integrity.py`) performs comprehensive validation of the SQLite database to detect corruption, schema issues, and data inconsistencies **before** they cause application crashes or silent data loss.

## When It Runs

The integrity check runs automatically during app startup, immediately after database compatibility check and before the login screen appears.

## What It Checks

### Quick Check Mode (Default on Startup)
Performs essential, fast checks only:

1. **SQLite Integrity** - Uses SQLite's built-in `PRAGMA integrity_check`
2. **Schema Validation** - Verifies all required tables and columns exist

### Full Check Mode (Optional, via CLI or API)
Includes all quick checks plus:

3. **Foreign Key Constraints** - Detects broken relationships between tables
4. **Required Fields** - Checks for NULL or empty values in critical fields
5. **Data Consistency** - Validates business rules:
   - Circuit breakers must have `breaker_category` (SF6, Ελαίου, etc.)
   - No future dates in maintenance records
   - Maintenance records must have at least one element
6. **Orphaned Records** - Finds records referencing non-existent parents:
   - Elements without substations
   - Maintenance elements without maintenance or elements

## Severity Levels

### ❌ ERRORS (Critical)
**Action**: App startup is blocked
- Corrupted SQLite file
- Missing required tables or columns
- Orphaned records (data referencing deleted records)
- Foreign key violations

**User sees**: Error dialog with details and suggestion to restore from backup

### ⚠️ WARNINGS
**Action**: User is warned but can choose to continue
- Circuit breakers missing breaker_category
- Future dates in maintenance records
- Maintenance records without elements
- NULL values in non-critical fields

**User sees**: Warning dialog with "Continue" and "Cancel" options

### ℹ️ INFO
**Action**: Logged silently (no user notification)
- Successful check results
- Statistics about checked tables

## Usage

### Automatic (App Startup)
```python
# In DBrun.py _finish_build() method
def _check_db_integrity(self):
    db_path = get_db_path() or DB_PATH
    result = check_database_integrity(db_path, quick_check=True)
    
    if result.errors:
        # Block app startup, show error
        return False
    
    if result.warnings:
        # Show warning, let user decide
        return user_confirmation()
    
    return True
```

### Manual Check (CLI)
```bash
# Quick check
python -c "from db_integrity import check_database_integrity; r = check_database_integrity('substations.db', quick_check=True); print(r.get_summary())"

# Full check
python -c "from db_integrity import check_database_integrity; r = check_database_integrity('substations.db'); print(r.get_summary())"
```

### Programmatic Use
```python
from db_integrity import check_database_integrity

# Run integrity check
result = check_database_integrity('path/to/database.db', quick_check=False)

# Check results
if result.passed:
    print("Database is healthy")
else:
    print(f"Found {len(result.errors)} errors and {len(result.warnings)} warnings")
    
# Get detailed summary
print(result.get_summary())

# Access specific issues
for error in result.errors:
    print(f"ERROR: {error}")

for warning in result.warnings:
    print(f"WARNING: {warning}")
```

## Performance

- **Quick Check**: ~50-100ms for typical database (100+ substations)
- **Full Check**: ~200-500ms for typical database
- **Startup Impact**: Minimal - runs in background before UI loads

## What to Do If Checks Fail

### Critical Errors
1. **Do NOT ignore** - Continuing may cause data loss
2. Restore from most recent backup (see `scripts/backup_db.py`)
3. Check disk for errors (`chkdsk` on Windows, `fsck` on Linux)
4. Contact support if backups are also corrupt

### Warnings
1. **Review the specific warnings** - Some may be acceptable
2. Fix data issues before they become errors:
   - Add missing breaker categories
   - Correct future dates
   - Associate maintenance with elements
3. Run full integrity check regularly to monitor issues

## Preventive Measures

### Regular Backups
```bash
# Create versioned backup (recommended before major changes)
python scripts/backup_db.py "Description of changes"

# Automatic backup (add to scheduled tasks)
python scripts/backup_db.py "Automated weekly backup"
```

### Periodic Full Checks
Add task to check database monthly:
```bash
python -c "from db_integrity import check_database_integrity; r = check_database_integrity('substations.db'); print(r.get_summary())" > integrity_report.txt
```

### Safe Database Operations
- Always use transactions for multi-step operations
- Enable foreign keys: `PRAGMA foreign_keys = ON`
- Use prepared statements to prevent SQL injection
- Close connections properly after use

## Technical Details

### Check Implementation

#### SQLite Integrity Check
```python
cursor.execute("PRAGMA integrity_check")
# Returns "ok" if database structure is valid
```

#### Orphaned Records Detection
```sql
-- Find elements without substations
SELECT COUNT(*) FROM elements e
WHERE NOT EXISTS (SELECT 1 FROM substations s WHERE s.id = e.substation_id)
```

#### Foreign Key Validation
```python
cursor.execute("PRAGMA foreign_keys = ON")
cursor.execute("PRAGMA foreign_key_check")
# Returns list of violations
```

### Performance Optimization

The integrity checker is optimized for startup performance:
- **Quick check mode** skips expensive data scans
- **Batch queries** reduce database round-trips
- **Early exit** on critical errors avoids wasted work
- **Indexed queries** for orphaned record detection

## Testing

Run integrity checker tests:
```bash
# Test all integrity check scenarios
pytest tests/test_db_integrity.py -v

# Test specific scenario
pytest tests/test_db_integrity.py::test_integrity_check_orphaned_elements -v
```

Test coverage: 83% (150 statements, 26 missed)

## Troubleshooting

### "CHECK constraint failed" during testing
This is expected! The database schema has CHECK constraints to prevent invalid data. The integrity checker can still detect legacy invalid data that bypassed these checks.

### File locked on Windows during tests
Windows locks database files differently than Unix. Tests include retry logic and cleanup handling.

### Slow startup after enabling integrity checks
- Verify `quick_check=True` is used on startup
- Check database size (>1000 substations may need optimization)
- Consider disabling on fast hardware if startup <2 seconds

## Future Enhancements

Potential improvements for future versions:
- [ ] Async integrity check (non-blocking UI)
- [ ] Scheduled background checks while app is running
- [ ] Auto-repair for common issues (with user confirmation)
- [ ] Detailed HTML report generation
- [ ] Email alerts for administrators on critical errors
- [ ] Integration with backup system (auto-backup before fixes)
