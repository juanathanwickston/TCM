# UI Behavior Contract — Django Migration

**Purpose**: Define inputs, outputs, and side effects for each page.  
Django must replicate this behavior exactly.

---

## Dashboard

### Inputs
- None (no user inputs)

### Outputs (read-only)
| Element | Source | Format |
|---------|--------|--------|
| Total Submissions | `get_submission_summary()['total']` | Integer, comma-formatted |
| Total Content Items | `sum(compute_file_count(c))` for active containers | Integer |
| Items Remaining | `get_scrub_status_breakdown()['unreviewed']` | Integer |
| Duplicates | `get_duplicate_count()` | Integer (placeholder) |
| Onboarding/Upskilling/Other | `get_submission_summary()` | Count + percentage |
| Include/Modify/Sunset | `get_scrub_status_breakdown()` | Counts |
| Training Sources | `get_source_breakdown()` | Table: Source, Count, % |
| Training Types | `get_training_type_breakdown()` | Table: Type, Count, % |
| Sales Stage | `get_sales_stage_breakdown()` | Table: Stage, Resources |

### Side Effects
- None

---

## Inventory

### Inputs
| Input | Type | Default |
|-------|------|---------|
| Department filter | Dropdown | "All Departments" |
| Training Type filter | Dropdown | "All Types" |
| Sales Stage filter | Dropdown | "All" |
| Audience filter | Dropdown | "All" |
| Audience cell edit | Inline select | Current value |

### Outputs
| Element | Source |
|---------|--------|
| Total resources count | `sum(c['resource_count'])` for filtered containers |
| Items inside folders | `sum(compute_file_count(c))` |
| Container table | Filtered `get_active_containers_filtered()` |

### Side Effects
| Trigger | Backend Call |
|---------|--------------|
| Audience cell changed | `update_audience_bulk([key], new_value)` |

### Validation Rules
- Audience cannot be cleared (error shown, change rejected)
- Filter cascades: Training Type options filtered by Department

---

## Scrubbing

### Inputs
| Input | Type | Default |
|-------|------|---------|
| Queue filter | Dropdown | "Unreviewed" |
| Queue selection | Radio list | First item |
| Status | Dropdown | Current value or empty |
| Sales Stage | Dropdown | Current value or empty |
| Notes | Text area | Current value |

### Outputs
| Element | Source |
|---------|--------|
| Review progress | `{reviewed}/{total}` from queue counts |
| Queue list | Filtered containers, sorted by resource_count desc |
| Asset info | Selected container details |

### Side Effects
| Trigger | Backend Call |
|---------|--------------|
| Save / Save and Next | `update_container_scrub(key, decision, '', notes, None)` |
| (same) | `update_sales_stage(key, stage)` |

### Validation Rules
- Status is required (error if empty on save)
- Notes required if Status is "Modify" or "Sunset"
- "Save and Next" advances queue index

---

## Investment

### Inputs
| Input | Type | Default |
|-------|------|---------|
| Scrub Status filter | Dropdown | "All" |
| Decision filter | Dropdown | "All" |
| Decision | Dropdown per item | Current value |
| Owner | Text input | Current value |
| Effort/Cost | Text input | Current value |
| Notes | Text area | Current value |

### Outputs
| Element | Source |
|---------|--------|
| Queue summary | Counts: Total, Modify, Gap, Decided |
| Container list | `get_containers_by_scrub_status(['modify', 'gap'])` |

### Side Effects
| Trigger | Backend Call |
|---------|--------------|
| Save button | `update_container_invest(key, decision, owner, effort, notes)` |

### Validation Rules
- Decision required
- Owner required
- Effort/Cost required if decision is build/buy/assign_sme
- Notes required if decision is defer

---

## Tools (John Only)

### Inputs
| Input | Type |
|-------|------|
| ZIP file upload | File uploader |
| Process ZIP button | Button |
| Import Payroc ZIP | Button |
| Sync Local Folder | Button |
| Sync from SharePoint | Button (if enabled) |
| Run Audience Migration | Button |
| Clear All Data | Button (requires checkbox confirm) |

### Outputs
| Element | Source |
|---------|--------|
| Export CSV/Excel | `get_all_containers()` → DataFrame |
| Resource Statistics | `get_resource_totals()` |
| Department Breakdown | From totals dict |

### Side Effects
| Trigger | Backend Call |
|---------|--------------|
| Process ZIP | `import_from_zip(temp_path)` |
| Import Payroc ZIP | `import_from_zip(payroc_path)` |
| Sync Local Folder | `import_from_folder(folder_path)` |
| Sync from SharePoint | `sync_from_sharepoint()` |
| Run Audience Migration | `run_audience_migration()` |
| Clear All Data | `clear_containers()` |

### Access Control
- **Only accessible by superuser (John)**
- Non-superuser receives 403 Forbidden

---

## Reconciliation Contract

| Metric | Dashboard Source | Inventory Source | Must Match |
|--------|------------------|------------------|------------|
| Total Submissions | `get_submission_summary()['total']` | `sum(c['resource_count'])` for filtered containers | ✅ Yes |
| Total Content Items | `sum(compute_file_count())` | Header "Items inside folders" | ✅ Yes |

**Note**: Dashboard and Inventory use *different calls* that must reconcile:
- Dashboard: `get_submission_summary()['total']` (aggregated in SQL)
- Inventory: `sum(c['resource_count'])` over `get_active_containers_filtered()` results

These are not the same call — do not shortcut by sharing one function for both.
