# UI Entrypoints — Django Migration

**Purpose**: Map exact backend functions each Streamlit page calls today.  
Django views will call these same functions — no alternatives, no rewrites.

---

## Dashboard (`views/dashboard.py`)

| Backend Module | Function | Purpose |
|----------------|----------|---------|
| `services.kpi_service` | `get_submission_summary()` | Total submissions, onboarding/upskilling breakdown |
| `services.kpi_service` | `get_scrub_status_breakdown()` | Include/Modify/Sunset/Unreviewed counts |
| `services.kpi_service` | `get_source_breakdown()` | Training sources by department |
| `services.kpi_service` | `get_training_type_breakdown()` | Training types distribution |
| `services.kpi_service` | `get_duplicate_count()` | Duplicate count (placeholder) |
| `db` | `get_active_containers()` | All active, non-archived containers |
| `db` | `get_sales_stage_breakdown()` | Sales-tagged content by stage |
| `services.container_service` | `compute_file_count(container)` | Content items inside folders |

---

## Inventory (`views/inventory.py`)

| Backend Module | Function | Purpose |
|----------------|----------|---------|
| `db` | `get_active_departments()` | Distinct departments for filter dropdown |
| `db` | `get_active_training_types(department)` | Training types (optionally filtered by dept) |
| `db` | `get_active_containers_filtered(...)` | Containers with dept/type/stage filters |
| `db` | `update_audience_bulk(keys, audience)` | **WRITE**: Batch update audience field |
| `services.container_service` | `compute_file_count(container)` | Content items calculation |
| `services.container_service` | `import_from_zip(path)` | Quick import (displayed if no data) |
| `services.container_service` | `TRAINING_TYPE_LABELS` | Display labels dict |
| `services.sales_stage` | `SALES_STAGES` | Stage options |
| `services.sales_stage` | `SALES_STAGE_LABELS` | Stage display labels |
| `services.scrub_rules` | `CANONICAL_AUDIENCES` | Audience options for editor |

---

## Scrubbing (`views/scrubbing.py`)

| Backend Module | Function | Purpose |
|----------------|----------|---------|
| `db` | `get_active_containers()` | All active containers for queue |
| `db` | `update_container_scrub(...)` | **WRITE**: Save scrub decision |
| `db` | `update_sales_stage(...)` | **WRITE**: Save sales stage |
| `services.scrub_rules` | `normalize_status(status)` | Map legacy/raw → canonical |
| `services.scrub_rules` | `CANONICAL_SCRUB_STATUSES` | ["Include", "Modify", "Sunset"] |
| `services.scrub_rules` | `CANONICAL_AUDIENCES` | Audience list |
| `services.scrub_rules` | `VALID_SCRUB_REASONS` | Reason options |
| `services.scrub_rules` | `REASON_LABELS` | Reason display labels |
| `services.sales_stage` | `SALES_STAGES` | Stage options |
| `services.sales_stage` | `SALES_STAGE_LABELS` | Stage display labels |
| `services.signal_service` | `compute_duplicate_map()` | Duplicate detection |
| `services.signal_service` | `compute_signals()` | Quality signals |
| `services.signal_service` | `get_flag_display_text(...)` | Signal display |

---

## Investment (`views/investment.py`)

| Backend Module | Function | Purpose |
|----------------|----------|---------|
| `db` | `get_containers_by_scrub_status([...])` | Containers with modify/gap status |
| `db` | `update_container_invest(...)` | **WRITE**: Save investment decision |
| `models.enums` | `ScrubStatus` | Enum for status labels |
| `models.enums` | `InvestDecision` | Enum for decision labels |

> **Note**: No `investment_service` module is used by this view. All logic is handled via `db` functions + enums.

---

## Tools (`views/tools.py`) — **JOHN ONLY**

| Backend Module | Function | Purpose |
|----------------|----------|---------|
| `db` | `get_all_containers()` | All containers (for export) |
| `db` | `get_active_containers()` | Active containers (for stats) |
| `db` | `get_resource_totals()` | Bucket totals |
| `db` | `clear_containers()` | **WRITE**: Clear all data |
| `db` | `run_audience_migration()` | **WRITE**: Backfill audience |
| `services.container_service` | `import_from_zip(path)` | **WRITE**: Import ZIP |
| `services.container_service` | `import_from_folder(path)` | **WRITE**: Import folder |
| `services.sharepoint_service` | `sync_from_sharepoint()` | **WRITE**: SharePoint sync |
| `services.sharepoint_service` | `is_sharepoint_enabled()` | Check env flag |

---

## Summary

| Category | Functions |
|----------|-----------|
| **Read-only** | 18 functions |
| **Write** | 7 functions |
| **Total** | 25 unique backend entrypoints |

Django views will import and call these functions exactly as Streamlit does today.
