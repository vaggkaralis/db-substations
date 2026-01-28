# Maintenance Tracking Feature

## Overview
The maintenance tracking system allows you to record on-site maintenance activities for substations and their elements. This feature is available in both desktop (DBrun.py) and will be integrated into the Android app.

## Key Features

### ✅ Maintenance Requirements
- **One substation per maintenance** - Cannot span multiple substations
- **At least one element required** - Must service at least one piece of equipment
- **Automatic date/time** - Auto-filled with current timestamp, manually editable
- **Comments support** - Both overall maintenance comments and per-element notes

### 📊 Database Schema

**maintenance table:**
- `id` - Primary key
- `substation_id` - Foreign key to substations (required)
- `date_time` - Timestamp of maintenance (required)
- `overall_comments` - General notes about the maintenance session

**maintenance_elements table:**
- `id` - Primary key  
- `maintenance_id` - Foreign key to maintenance (cascades on delete)
- `element_id` - Foreign key to elements (cascades on delete)
- `element_comments` - Specific notes for this element's maintenance

## Desktop App Usage (DBrun.py)

### Recording a Maintenance

1. **Launch app** and click "Καταχώρηση Συντήρησης" (Record Maintenance)

2. **Select Substation** from dropdown
   - Elements list updates automatically

3. **Edit Date/Time** if needed
   - Default: Current date and time (YYYY-MM-DD HH:MM)
   - Format: `2026-01-27 14:30`

4. **Enter Overall Comments** (optional)
   - General observations about the maintenance session
   - Work performed, conditions, etc.

5. **Select Elements**
   - Check at least one element checkbox
   - Elements automatically filtered for selected substation

6. **Add Per-Element Comments** (optional)
   - Individual notes for each serviced element
   - Specific repairs, measurements, observations

7. **Click "Αποθήκευση"** (Save)
   - Validates at least one element selected
   - Validates date/time present
   - Saves to database

### Viewing Maintenance History

1. Click "Προβολή Ιστορικού Συντήρησης" (View Maintenance History)

2. **View Details:**
   - Substation name
   - Date and time of maintenance
   - Overall comments
   - List of serviced elements with comments

3. **Delete Maintenance:**
   - Click "Διαγραφή Συντήρησης" (Delete Maintenance)
   - Cascade deletes associated element records

## API Endpoints

### GET /api/maintenance
Get all maintenance records or filter by substation.

**Query Parameters:**
- `substation_id` (optional) - Filter by substation

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "substation_id": 5,
      "substation_name": "ΥΣ Αθηνών",
      "date_time": "2026-01-27 14:30",
      "overall_comments": "Routine maintenance",
      "elements": [
        {
          "id": 1,
          "element_id": 12,
          "element_type": "Διακόπτης Ισχύος",
          "name": "CB-01",
          "serial_number": "12345",
          "element_comments": "Checked SF6 pressure"
        }
      ]
    }
  ]
}
```

### POST /api/maintenance
Create a new maintenance record.

**Request Body:**
```json
{
  "substation_id": 5,
  "date_time": "2026-01-27 14:30",
  "overall_comments": "Routine maintenance",
  "elements": [
    {
      "element_id": 12,
      "element_comments": "Checked SF6 pressure"
    },
    {
      "element_id": 13,
      "element_comments": "Oil sample taken"
    }
  ]
}
```

**Validation:**
- `substation_id` - Required
- `date_time` - Required
- `elements` - Required, must have at least one element

**Response:**
```json
{
  "success": true,
  "data": {
    "id": 1
  }
}
```

### DELETE /api/maintenance/<id>
Delete a maintenance record (cascades to maintenance_elements).

**Response:**
```json
{
  "success": true,
  "data": {
    "deleted_id": 1
  }
}
```

## Android App Integration (Coming Soon)

The Android app will have a "Record Maintenance" button optimized for field use:
- Quick substation selection
- Large checkboxes for gloved hands
- Voice-to-text for comments (if available)
- Offline support with sync when connection restored
- GPS coordinates for location verification

## Data Migration

Existing databases will automatically create the new tables on next connection:
- `maintenance` table
- `maintenance_elements` table

No data loss or manual migration required.

## Best Practices

1. **Regular Recording** - Record maintenance immediately on-site
2. **Detailed Comments** - Include measurements, observations, actions taken
3. **Element Selection** - Only check elements actually serviced
4. **Date Accuracy** - Verify auto-filled timestamp is correct
5. **Backup** - Maintenance history is valuable - back up database regularly

## Future Enhancements

Planned improvements:
- [ ] Maintenance scheduling and reminders
- [ ] Photo attachments for maintenance evidence
- [ ] Maintenance templates for common tasks
- [ ] Maintenance reports and statistics
- [ ] Required maintenance intervals by element type
- [ ] Technician assignment tracking
- [ ] Parts used inventory tracking
