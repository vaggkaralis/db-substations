# Android ↔ Desktop Architecture Alignment Plan

## Current Status

### ✅ Completed
- [x] Basic CRUD operations (Create, Read, Update, Delete)
- [x] API connectivity to Render.com
- [x] Element types updated (15 types matching desktop)
- [x] UI spacing fixes

### ❌ Missing Features in Android App

#### **Priority 1: Critical Differences**

**1. Element Models System** 🔧
- **Desktop:** `element_models` table with model library
- **Android:** No model management
- **Impact:** Cannot reuse predefined equipment configurations
- **Fields missing:**
  - `element_model_id` (foreign key to models)
  - `model_name`, `manufacturer` (from model)
  - `maintenance_cycle` (auto-filled from model)
  - `installation_space` (auto-filled from model)
  - `breaker_category` (for breakers: SF6, Oil, Vacuum)

**2. Element Fields** 📋
Desktop has many fields Android lacks:
- `manufacture_year` - Year manufactured (YYYY)
- `model_version` - Model variant/version
- `operating_status` - 'Ενεργή' or 'Ανενεργή'
- `installation_space` - 'Εσωτερικός' or 'Εξωτερικός'
- `maintenance_cycle` - Months between maintenance
- `bar` - Bar assignment (ΖΥΓΟΣ 1, ΖΥΓΟΣ 2, etc.)
- `is_main_switch` - Breaker type (0=Line, 1=Main, 2=Interconnection, 3=Capacitor)

**3. Voltage Levels** ⚡
- **Desktop:** User-defined per element (free text)
- **Android:** Fixed spinner ['20 KV', '150 KV', '20/150 KV']
- **Fix needed:** Make it flexible like desktop

#### **Priority 2: Important Features**

**4. Maintenance Tracking** 📅
- **Desktop:** Full maintenance system with:
  - `maintenance` table (date, substation, comments, type)
  - `maintenance_elements` table (element-specific comments)
  - Measurement tracking (insulation, contact resistance)
  - Maintenance history view
  - Automatic date updates
- **Android:** Only stores `maintenance_date` field (no tracking system)

**5. Breaker-Specific Features** 🔌
- **Desktop:**
  - Breaker categories (SF6, Oil, Vacuum)
  - Breaker types (Main, Line, Interconnection, Capacitor)
  - Bar assignments
  - `is_main_switch` field to distinguish types
- **Android:** Treats all breakers the same

**6. Bar Management** 🏗️
- **Desktop:** Automatic bar detection from transformers
- **Android:** No bar concept

**7. Division Field** 🏢
- **Desktop:** Substation has `division` field (e.g., 'ΤΜΘ')
- **Android:** Only `name`, `location`, `adoption_date`

#### **Priority 3: Advanced Features**

**8. Import/Export** 📥📤
- **Desktop:** CSV/Excel import for bulk operations
- **Android:** Manual entry only

**9. Model Management UI** 🎛️
- **Desktop:** Full model library management interface
- **Android:** No model management

**10. Inactive Elements View** 👻
- **Desktop:** Filter by `operating_status` to show inactive elements
- **Android:** Shows all elements (no status filtering)

---

## Implementation Strategy

### **Phase 1: Database Schema Alignment** (High Priority)

Update API server to support all desktop fields:

```python
# api_server.py needs to handle:
- element_model_id
- manufacture_year
- model_version
- operating_status
- installation_space
- maintenance_cycle
- bar
- is_main_switch
```

Update API endpoints:
- `POST /elements` - Accept new fields
- `PUT /elements/<id>` - Update with new fields
- `GET /elements` - Return all fields

### **Phase 2: Android UI Updates** (Step-by-step)

#### **Step 2.1: Extend Element Fields**
- Add missing input fields to add/edit element popups
- Add spinners for dropdowns (operating_status, installation_space)
- Add text inputs for free-form fields
- **Estimated:** 2-3 hours

#### **Step 2.2: Model System (Basic)**
- Create model selection dropdown
- Fetch models from API (`GET /models`)
- Auto-fill fields when model selected
- **Estimated:** 3-4 hours

#### **Step 2.3: Model Management**
- Add "Models" menu item
- Create model list view
- Add model creation popup
- **Estimated:** 4-5 hours

#### **Step 2.4: Breaker Features**
- Add breaker type selector (Main/Line/Interconnection/Capacitor)
- Add bar assignment field
- Add breaker category (SF6/Oil/Vacuum)
- **Estimated:** 2-3 hours

#### **Step 2.5: Maintenance Tracking**
- Add maintenance recording screen
- Show maintenance history
- Record element-specific comments
- **Estimated:** 6-8 hours

### **Phase 3: API Enhancement**

Add new endpoints:
```
GET  /models                    - List all models
POST /models                    - Create model
GET  /models/<id>               - Get model details
DELETE /models/<id>             - Delete model

GET  /maintenance/<substation>  - Maintenance history
POST /maintenance               - Record maintenance
DELETE /maintenance/<id>        - Delete maintenance record

GET  /bars/<substation>         - Get available bars
```

---

## Field Mapping Reference

### **Elements Table - Full Schema**

| Field | Type | Desktop | Android | Priority |
|-------|------|---------|---------|----------|
| `id` | INTEGER | ✅ | ✅ | - |
| `substation_id` | INTEGER | ✅ | ✅ | - |
| `element_type` | TEXT | ✅ | ✅ | - |
| `name` | TEXT | ✅ | ✅ | - |
| `serial_number` | TEXT | ✅ | ✅ | - |
| `maintenance_date` | TEXT | ✅ | ✅ | - |
| `manufacturer` | TEXT | ✅ | ✅ | - |
| `type` | TEXT | ✅ | ✅ | - |
| `voltage_level` | TEXT | ✅ | ✅ (fixed) | Med |
| `element_model_id` | INTEGER | ✅ | ❌ | **HIGH** |
| `manufacture_year` | TEXT | ✅ | ❌ | Med |
| `model` | TEXT | ✅ | ❌ | Med |
| `model_version` | TEXT | ✅ | ❌ | Low |
| `operating_status` | TEXT | ✅ | ❌ | Med |
| `installation_space` | TEXT | ✅ | ❌ | Med |
| `maintenance_cycle` | INTEGER | ✅ | ❌ | Med |
| `bar` | TEXT | ✅ | ❌ | Med |
| `is_main_switch` | INTEGER | ✅ | ❌ | Med |

### **Substations Table**

| Field | Desktop | Android | Priority |
|-------|---------|---------|----------|
| `id` | ✅ | ✅ | - |
| `name` | ✅ | ✅ | - |
| `location` | ✅ | ✅ | - |
| `adoption_date` | ✅ | ✅ | - |
| `division` | ✅ | ❌ | Low |
| `last_maintenance` | ✅ | ❌ (via API) | Med |

---

## Next Steps (Recommended Order)

1. ✅ **Fix spacing issues** - DONE
2. ✅ **Update element types** - DONE
3. 🔄 **Test current Android APK** - Verify spacing and types work
4. 📝 **Update API server** - Add support for new element fields
5. 📱 **Android: Add element fields UI** - Step 2.1
6. 🔧 **Android: Basic model system** - Step 2.2
7. 📊 **Test data migration** - Move laptop data to cloud
8. 🔄 **Iterate on remaining features** - Based on usage feedback

---

**Last Updated:** January 30, 2026
**Status:** Architecture gap documented, spacing fixed, element types aligned
