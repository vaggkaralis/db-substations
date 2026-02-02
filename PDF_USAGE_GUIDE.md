# Quick Guide: Generating PDF Maintenance Reports

## Step-by-Step Instructions

### 1. Record Maintenance (First Time)

If you haven't recorded any maintenance yet:

1. **Open the Desktop App** (`DBrun.py`)
2. **Select a Substation** from the list
3. **Click "Συντήρηση"** (Maintenance) button
4. **Fill in maintenance details**:
   - Select maintenance type
   - Confirm date/time
   - Add overall comments (optional)

5. **Select Circuit Breakers** to maintain:
   - Check the boxes for breakers (ΥΤ or ΜΤ)
   - For each breaker, fill in measurements:
     - **Μονώσεις Κλειστό** (Insulation Closed): Values + units for all 3 phases
     - **Μονώσεις Ανοιχτό** (Insulation Open): Values + units for all 3 phases
     - **Αντίσταση Επαφών** (Contact Resistance): Values in μΩ for all 3 phases
   - Add element-specific comments (optional)

6. **Click "Αποθήκευση"** (Save)

### 2. Generate PDF Report

Once maintenance is recorded:

1. **From Main Menu**:
   - Click "Ιστορικό Συντήρησης" (Maintenance History)
   - OR from substation details, click maintenance button

2. **Find Your Maintenance Record**:
   - Records are listed by date (newest first)
   - Each card shows:
     - Substation name and date
     - Overall comments
     - List of maintained elements

3. **Generate PDF**:
   - Look for the **"📄 PDF"** button next to each circuit breaker
   - Click the button
   - Wait for generation (usually <1 second)

4. **View PDF**:
   - Success popup appears
   - Shows file path
   - Click **"Άνοιγμα PDF"** to view immediately
   - Or click **"Κλείσιμο"** and find it later in `reports/` folder

### 3. Find Generated PDFs

PDFs are saved to:
```
DB Substations/reports/Maintenance_[ElementName]_[Timestamp].pdf
```

Example filenames:
- `Maintenance_Δ-215_20260130_143530.pdf`
- `Maintenance_Δ-15_20260130_144200.pdf`

## What Each Report Contains

### Header Section
- Report title with breaker type (ΑΕΡΙΟΥ / ΛΑΔΙΟΥ / ΚΕΝΟΥ)
- Substation name

### Equipment Information (Blue Table)
| Field | Example |
|-------|---------|
| Όνομα | Δ-215 |
| Αριθμός Σειράς (S/N) | ML 020273 |
| Κατασκευαστής | ABB |
| Μοντέλο | SACE HA3/ZC |
| Τάση (kV) | 20 KV |
| Πύλη | ΠΥΛΗ 1 |
| Έτος Κατασκευής | 2015 |

### Maintenance Information (Blue Table)
| Field | Example |
|-------|---------|
| Ημερομηνία | 2026-01-30 14:35 |
| Τύπος Συντήρησης | Επαναληπτική συντήρηση |
| Τομέας | ΤΜΘ |

### Measurements (Green Table)
**ΜΕΤΡΗΣΕΙΣ ΜΟΝΩΣΕΩΝ**

| Θέση | Φάση Α | Φάση Β | Φάση Γ |
|------|--------|--------|--------|
| Κλειστή Θέση (προς γη) | 1000 GΩ | 1000 GΩ | 1000 GΩ |
| Ανοιχτή Θέση (μεταξύ επαφών) | 1000 GΩ | 1000 GΩ | 1000 GΩ |

### Contact Resistance (Yellow Table)
**ΜΕΤΡΗΣΕΙΣ ΑΝΤΙΣΤΑΣΗΣ ΕΠΑΦΩΝ (μΩ)**

| | Φάση Α | Φάση Β | Φάση Γ |
|-|--------|--------|--------|
| Αντίσταση Επαφών | 50 μΩ | 50 μΩ | 50 μΩ |

### Comments Section
- Element-specific comments
- Overall maintenance comments

### Footer
- Generation timestamp

## Tips & Best Practices

### Before Recording Maintenance
✓ Have all measurement values ready
✓ Know which breaker type (SF6, Oil, Vacuum)
✓ Prepare comments beforehand
✓ Check units match your measurements

### During Measurement Entry
✓ Enter all 3 phases for consistency
✓ Use appropriate units (GΩ for high values, MΩ/kΩ for lower)
✓ Contact resistance always in μΩ
✓ Add meaningful comments

### After PDF Generation
✓ Review PDF for accuracy
✓ File PDFs systematically (by substation, date, etc.)
✓ Print if needed for physical records
✓ Back up reports folder regularly

## Troubleshooting

### "No PDF button appears"
- **Reason**: Element is not a circuit breaker, or breaker_category not set
- **Solution**: Check element type includes "Διακόπτης" and breaker_category is SF6/Oil/Vacuum

### "PDF generation failed"
- **Reason**: Missing measurements or database connection issue
- **Solution**: Re-enter measurements, save maintenance record again

### "Can't open PDF"
- **Reason**: No PDF viewer installed
- **Solution**: Install Adobe Reader or use browser to open PDFs

### "Greek characters look wrong"
- **Reason**: PDF viewer encoding issue (rare)
- **Solution**: Use different PDF viewer (Adobe Reader recommended)

## Example Workflow

**Scenario**: Quarterly maintenance on TEST substation

1. **Open Desktop App**
2. **Click "TEST" substation**
3. **Click "Συντήρηση"** button
4. **Select maintenance type**: "Επαναληπτική συντήρηση"
5. **Check all breakers**: Δ-215 (SF6), Δ-OIL-TEST (Oil), Δ-VAC-TEST (Vacuum)
6. **Enter measurements** for each:
   - Insulation closed: 1000 GΩ all phases
   - Insulation open: 1000 GΩ all phases  
   - Contact resistance: 50 μΩ all phases
7. **Add comments**: "Routine quarterly maintenance - all values normal"
8. **Click "Αποθήκευση"**
9. **Go to maintenance history**
10. **Click 📄 PDF for each breaker** (generates 3 PDFs)
11. **Review all PDFs**
12. **File in records**

## Support

For questions or issues:
- Check PDF_GENERATION_README.md for technical details
- Review measurement data in database before generating
- Ensure reportlab package is installed (`pip install reportlab`)
