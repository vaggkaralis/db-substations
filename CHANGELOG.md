# Changelog

## [0.0.1] - 2026-01-29

### Added
- Four circuit breaker types: Κεντρικός, Γραμμής, Διασυνδετικός, Διακόπτης Πυκνωτών
- Model management system with element_models table
- Model categorization by breaker type (SF6, Κενού, Πτωχού Ελαίου)
- Active/inactive element status tracking
- Inactive elements view with count display
- Interconnection bar logic (ΖΥΓΟΣ 1-2 format)
- Collapsible maintenance form
- Visible scrollbars throughout UI
- Import validation system with template versioning
- Required field validation (Operating Status, Breaker Role, etc.)
- Automatic model linking during import
- Breaker role validation (HV breakers must be Κεντρικός)
- Jump-to-substation navigation buttons

### Changed
- Import template updated to v2.0 with new columns
- Operating Status now required during import
- Element display now shows model data from element_models table
- Maintenance date shows in red when missing or overdue
- Simplified import workflow (auto-create substations)
- Model validation during import (new/conflicting prompts)

### Fixed
- Model assignment during import (element_model_id linking)
- Operating status normalization (Active → Ενεργή)
- HV breaker enforcement (always set as Κεντρικός)
- Breaker type display in inactive elements view
- Element display query using deprecated columns
- Navigation popup dismissal chain
- Maintenance date red color logic

### Technical
- Database schema with element_model_id foreign key
- Template version validation
- Strict data validation before import
- All-or-nothing import (transaction rollback on errors)
- Greek/English operating status normalization
- 6,216 total lines of Python code across 13 files
