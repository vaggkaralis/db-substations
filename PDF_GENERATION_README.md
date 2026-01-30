# PDF Maintenance Report Generation

## Overview

The application can now automatically generate professional PDF maintenance reports for circuit breakers. These reports match the official templates and include all measurements and maintenance data.

## Features

### Supported Breaker Types
- **SF6 (Gas) Circuit Breakers** (Διακόπτης Αερίου)
- **Oil Circuit Breakers** (Διακόπτης Λαδιού)  
- **Vacuum Circuit Breakers** (Διακόπτης Κενού)

### Report Contents
Each PDF report includes:
- **Equipment Information**: Name, S/N, manufacturer, model, voltage level, bar assignment, manufacturing year
- **Maintenance Details**: Date, maintenance type (Επαναληπτική συντήρηση, Βλάβη, Οπτικός έλεγχος), division
- **Insulation Measurements**: 
  - Closed position (to ground) - 3 phases with units (GΩ, MΩ, kΩ)
  - Open position (between contacts) - 3 phases with units
- **Contact Resistance Measurements**: 3 phases in μΩ
- **Comments**: Element-specific and overall maintenance comments
- **Professional Formatting**: Color-coded tables, Greek text support, timestamp

## How to Use

### From Desktop App

1. **Record Maintenance**:
   - Navigate to substation details
   - Click "Συντήρηση" button
   - Select circuit breakers to maintain
   - Enter all measurements (insulation, contact resistance)
   - Add comments
   - Save

2. **Generate PDF Report**:
   - Go to "Ιστορικό Συντήρησης" (maintenance history)
   - Find the maintenance record
   - Click "📄 PDF" button next to any circuit breaker
   - PDF will be generated in the `reports/` folder
   - Click "Άνοιγμα PDF" to view immediately

### File Location

Generated PDFs are saved in:
```
DB Substations/reports/Maintenance_[ElementName]_[Timestamp].pdf
```

Example: `reports/Maintenance_Δ-215_20260130_143022.pdf`

## Technical Details

### Implementation

- **Module**: `pdf_reports.py`
- **Generator Class**: `MaintenanceReportGenerator`
- **Library**: ReportLab (Python PDF generation)
- **Page Size**: A4
- **Encoding**: Unicode (full Greek character support)

### Database Requirements

Reports pull data from:
- `maintenance` table: Date, type, comments, substation
- `maintenance_elements` table: Measurements (insulation, contact resistance)
- `elements` table: Equipment details, breaker category
- `element_models` table: Model information (if linked)
- `substations` table: Substation name, division

### Report Generation Function

```python
from pdf_reports import generate_maintenance_report

# Generate PDF for a specific maintenance record and element
pdf_path = generate_maintenance_report(
    conn=database_connection,
    maintenance_id=1,
    element_id=5,
    output_path=None  # Optional: specify custom path
)
```

### Error Handling

The system validates:
- Maintenance record exists
- Element exists and is a circuit breaker
- Breaker category is SF6, Oil, or Vacuum
- Maintenance measurements are available

Error messages are displayed in Greek via popup dialogs.

## Template Matching

The generated PDFs closely match the official templates found in `documents/`:
- ΔΕΛΤΙΟ ΣΥΝΤΗΡΗΣΗΣ ΑΕΡΙΟΥ ver.2.pdf
- ΔΕΛΤΙΟ ΣΥΝΤΗΡΗΣΗΣ ΛΑΔΙΟΥ ver.2.pdf
- ΔΕΛΤΙΟ ΣΥΝΤΗΡΗΣΗΣ ΚΕΝΟΥ ver.2.pdf

### Visual Elements
- Blue header with substation name
- Color-coded measurement tables (green for insulation, yellow for contact resistance)
- Proper spacing and alignment
- Professional footer with generation timestamp

## Testing

To test PDF generation:

1. Create a maintenance record with circuit breaker measurements
2. Run the test script:
   ```bash
   python test_pdf_generation.py
   ```
3. Check the `reports/` folder for generated PDF

## Dependencies

Required Python package:
```
reportlab>=4.0.0
```

Install with:
```bash
pip install reportlab
```

## Future Enhancements

Potential improvements:
- [ ] Custom report templates per organization
- [ ] Batch PDF generation for all elements in a maintenance session
- [ ] Email PDF reports directly from app
- [ ] Digital signatures on reports
- [ ] Logo/header image customization
- [ ] Additional measurement types for other equipment
- [ ] PDF report history tracking
- [ ] Export to other formats (Excel, Word)

## Troubleshooting

### "No maintenance data found"
- Ensure you've saved the maintenance record
- Verify measurements were entered for the circuit breaker
- Check that the element is linked to the maintenance record

### "Unknown breaker category"
- Verify breaker_category field is set to 'SF6', 'Oil', or 'Vacuum'
- Check element type contains 'Διακόπτης'

### PDF Won't Open
- Ensure PDF viewer is installed (Adobe Reader, browser, etc.)
- Check file permissions on reports folder
- Verify reportlab package is installed correctly

### Greek Characters Not Displaying
- ReportLab's default fonts support Greek characters
- If issues persist, check system font installation

## Integration Points

### Desktop App (DBrun.py)
- Import: `from pdf_reports import generate_maintenance_report`
- Method: `generate_pdf_report(maintenance_id, element_id, element_name)`
- UI: PDF buttons in maintenance history views
- Success popup with "Open PDF" option

### Android App
Not yet implemented - requires different approach:
- Could generate PDFs on backend API
- Or use Android PDF generation library
- Future roadmap item

### Cloud API
Could add endpoint for PDF generation:
```
POST /api/maintenance/{maintenance_id}/element/{element_id}/report
Response: PDF file stream
```

## Support

For issues or questions about PDF report generation, contact the development team.
