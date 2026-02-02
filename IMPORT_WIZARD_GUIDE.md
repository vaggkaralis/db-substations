# Import Wizard - User Guide

## Overview

The Import Wizard provides a two-step validation process to ensure data quality when importing elements from Excel or CSV files. It intelligently detects column mismatches, validates values against expected formats, and provides suggestions for corrections.

## Features

### 🔍 Step 1: Column Mapping
Automatically detects and maps imported columns to database fields:
- **Auto-detection**: Recognizes common column name variations (e.g., "Element" → "Element Type")
- **Fuzzy matching**: Suggests best matches for unrecognized columns
- **Multi-language support**: Handles both Greek and English column names
- **Interactive mapping**: Manual override with dropdowns for custom mappings

**Supported Column Variations:**
- `Substation Name`: Substation, Υποσταθμός, Station
- `Element Type`: Type, Τύπος, Element
- `Operating Status`: Status, Κατάσταση
- `Serial Number`: Serial, SN, S/N
- And many more...

### ✅ Step 2: Data Validation
Validates and corrects data values before import:
- **Value normalization**: Converts English to Greek (e.g., "Active" → "Ενεργή")
- **Fuzzy value matching**: Suggests corrections for partial matches
- **New entity detection**: Highlights new substations and models
- **Data preview**: Shows what will be imported

**Validated Fields:**
1. **Element Types**: 
   - Μετασχηματιστής → Μετασχηματιστής 150/20KV
   - Breaker MV → Διακόπτης ΜΤ
   
2. **Operating Status**:
   - Active/Inactive → Ενεργή/Ανενεργή
   
3. **Breaker Roles**:
   - Central → Κεντρικός
   - Line/Feeder → Γραμμής
   - Tie → Διασυνδετικός
   
4. **Breaker Categories**:
   - Vacuum → Κενού
   - Oil → Πτωχού Ελαίου

## Usage

### Importing Elements

1. **Click Import Button** → Select "Import Elements"

2. **Select File** → Choose Excel (.xlsx) or CSV file

3. **Step 1 - Column Mapping**:
   - Review automatically matched columns (green highlight)
   - Fix any mismatched columns (yellow/red highlight)
   - Use dropdowns to assign unmatched columns
   - Click "Συνέχεια" (Continue) when ready

4. **Step 2 - Data Validation**:
   - Review validation summary
   - Check new substations and models (blue info box)
   - Review issues and suggested corrections
   - Accept/reject suggestions for each issue
   - Click "Εισαγωγή" (Import) to proceed

5. **Traditional Flow**:
   - Confirm new substations (if any)
   - Review new models (if any)
   - Handle duplicates (replace/skip)
   - Complete import

## Validation Rules

### Column Mapping Rules
- **Critical columns**: Substation Name, Element Type, Name, Operating Status
- **Optional columns**: Manufacturer, Model Name, Breaker Role, etc.
- **Minimum requirement**: All critical columns must be mapped

### Value Validation Rules
1. **Element Type** (confidence threshold: 60%)
   - Must match one of the predefined element types
   - Fuzzy matching for close matches
   - Suggestions provided for invalid values

2. **Operating Status** (required)
   - Must be either Ενεργή or Ανενεργή
   - Auto-converts English values

3. **Breaker Role** (for circuit breakers only)
   - Must be one of: Κεντρικός, Γραμμής, Διασυνδετικός, Διακόπτης Πυκνωτών
   - HV breakers must be Κεντρικός

4. **Breaker Category** (for circuit breakers only)
   - Must be one of: SF6, Κενού, Πτωχού Ελαίου

## Error Handling

### Issue Types

1. **🔍 Fuzzy Match** (Yellow)
   - Value is close but not exact
   - Suggested correction with confidence %
   - Accept/reject available

2. **❌ Invalid Value** (Red)
   - Value doesn't match any expected format
   - Alternatives provided
   - Must be corrected to proceed

3. **⚠️ Missing Required** (Red)
   - Required field is empty
   - Must be filled to proceed

### Common Issues & Solutions

**Issue**: Column "Element" not recognized
**Solution**: Map to "Element Type" in column mapping step

**Issue**: Value "Μετασχηματιστής" flagged
**Solution**: Accept suggestion "Μετασχηματιστής 150/20KV"

**Issue**: English values in import file
**Solution**: Wizard auto-converts (Active → Ενεργή)

**Issue**: New substation appears
**Solution**: Confirm creation in next step

## Tips & Best Practices

### Preparing Import Files

1. **Use the Template**: Export template from application
2. **Consistent Naming**: Use Greek or English consistently
3. **Complete Data**: Fill all required fields
4. **Check Types**: Ensure element types match exactly

### During Import

1. **Review Carefully**: Check column mappings before continuing
2. **Accept Good Matches**: Fuzzy matches with >80% confidence are usually correct
3. **Verify New Entities**: Check new substations and models are intentional
4. **Test First**: Try importing a small sample file first

### Performance

- Import files with 1000+ rows may take a few seconds to validate
- Validation runs once at the beginning, not per row during import
- Large files: Consider splitting into smaller batches

## Technical Details

### Supported File Formats
- Excel (.xlsx) - Recommended
- CSV (.csv) - Basic support

### Column Detection Algorithm
1. Exact match against known variants
2. Fuzzy string matching (SequenceMatcher)
3. Confidence threshold: 50% for suggestions

### Value Matching Algorithm
1. Exact match against canonical values
2. Fuzzy match against all variants
3. Confidence threshold: 60% for validation
4. Multiple alternatives provided

### Data Flow
```
File Selection
    ↓
Column Mapping Wizard (Step 1)
    ↓
Data Validation Wizard (Step 2)
    ↓
Corrected DataFrame
    ↓
Traditional Import Flow
    ↓
Database Import
```

## Troubleshooting

**Wizard doesn't appear**
- Check pandas is installed: `pip install pandas openpyxl`
- Verify file format is .xlsx or .csv

**Column suggestions wrong**
- Manually select correct column from dropdown
- Report issue if pattern consistently wrong

**Value validation too strict**
- Some manual corrections may be needed
- Fuzzy matching helps but not perfect

**Import fails after wizard**
- Check error message for specific issue
- Verify all required fields have values
- Check database constraints (duplicates, etc.)

## Future Enhancements

Planned improvements:
- [ ] Custom validation rules per organization
- [ ] Learn from user corrections
- [ ] Bulk accept/reject suggestions
- [ ] Import history and rollback
- [ ] Template library with presets

## Support

For issues or questions:
1. Check this guide first
2. Review QUICK_REFERENCE.md
3. Test with sample file: `test_import_with_issues.xlsx`
4. Check validation logic: `python test_import_wizard.py`
