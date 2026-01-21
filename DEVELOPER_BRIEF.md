# Training Catalogue Manager — Developer Brief

## What This System Is

A **workflow + metrics system** that overlays **human decisions** (scrub/invest) on top of a **deterministic training inventory** derived from a SharePoint-like folder structure.

**It is NOT:**
- A file browser
- An LMS
- A content management system

It reads content structure and stores **only metadata + decisions + sync history**. The app never mutates source content.

---

## Source of Truth

**The folder structure is the source of truth.**

Right now, SharePoint is not connected, so the local folder acts as SharePoint:
```
training_catalog_analyzer/Payroc Training Catalogue/
```

Sync is always an explicit user action from Tools. No auto-sync.

---

## Architecture Overview

```
training_catalog_analyzer/
├── Dashboard.py              # Main entry point, executive KPIs
├── db.py                     # SQLite data layer (all queries)
├── pages/
│   ├── 1_Inventory.py        # Browse all active resources
│   ├── 2_Scrubbing.py        # Review/classify resources
│   ├── 3_Investment.py       # Investment decision tracking
│   └── 4_Tools.py            # Import/export/sync utilities
├── services/
│   ├── container_service.py  # Sync logic, resource detection
│   └── tree_service.py       # Navigation tree builder
├── components/               # Reusable UI components
├── models/                   # Enums and data models
├── SYSTEM_CONTRACT.md        # ⚠️ READ THIS FIRST
├── DEVELOPER_BRIEF.md        # This file
└── README.md
```

---

## Canonical Folder Structure

Structure is fixed:

```
Payroc Training Catalogue/
└── Department/
    └── Sub-Department/
        └── Bucket/
            └── Training Type/
                ├── files
                ├── folders
                └── links.txt
```

- Everything above **Training Type** is categorization only (used for filters/reporting)
- **Training Type** folders are where "resources" live
- Display may clean labels (strip numeric prefixes, underscores, "(Drop Here)"), but **stored paths remain raw** for determinism

Example path parsing:
```
Payroc Training Catalogue/HR/_General/01_Onboarding/01_Instructor Led - In Person/Guide.pdf
                          │    │            │                    │
                   Department  Sub-Dept    Bucket           Training Type
```

---

## The Only Thing We Count: Training Resources

There is no "deliverable" concept. Only **Training Resources**.

A training resource is one of:

| Type | Definition | Count |
|------|------------|-------|
| **File** | Any file under a Training Type folder | 1 resource |
| **Folder** | Any directory under a Training Type folder (e.g., SCORM package) | 1 resource |
| **Link** | A URL parsed from `links.txt` | 1 resource per URL |

**Important**: `links.txt` is **parsed, not stored** as a resource row.

---

## Links Are First-Class Resources

When a `links.txt` exists:

1. Valid URLs are extracted (lines starting with `http://` or `https://`)
2. Each URL becomes its own row:
   - `container_type = "link"`
   - `resource_count = 1`
   - `web_url = <URL>`
   - `relative_path = parent/links.txt#<md5_hash>` (for stable hierarchy filtering)
3. Each link is independently scrubbed/invested

Empty `links.txt` creates **no countable resources**.

---

## Container Key (Unique Identifier)

Each resource has a deterministic `container_key`:

| Type | Format | Example |
|------|--------|---------|
| File | Full relative path | `HR/_General/01_Onboarding/.../Guide.pdf` |
| Folder | Path with trailing slash | `HR/_General/01_Onboarding/.../SCORM_Package/` |
| Link | Path + hash | `HR/_General/.../links.txt#a1b2c3d4e5f6` |

Re-adding a deleted resource with the same key **reactivates it** (same scrub/invest decisions preserved).

---

## Database Schema

### Main Table: `resource_containers`

| Column | Type | Description |
|--------|------|-------------|
| `container_key` | TEXT PK | Unique path-based identifier |
| `drive_item_id` | TEXT | SharePoint item ID (future use) |
| `relative_path` | TEXT | Full path from root |
| `bucket` | TEXT | `onboarding`, `upskilling`, or `not_sure` |
| `primary_department` | TEXT | Top-level department |
| `sub_department` | TEXT | Second-level folder |
| `training_type` | TEXT | Delivery format folder |
| `container_type` | TEXT | `file`, `folder`, or `link` |
| `display_name` | TEXT | Human-readable name |
| `web_url` | TEXT | URL (for links) |
| `resource_count` | INT | Number of resources (usually 1) |
| `valid_link_count` | INT | Count of valid URLs (for links.txt) |
| `is_placeholder` | INT | 1 = structural node, no content |
| `is_archived` | INT | 1 = deleted from source |
| `scrub_status` | TEXT | `not_reviewed`, `keep`, `modify`, `sunset`, `gap` |
| `scrub_owner` | TEXT | Who reviewed it |
| `scrub_notes` | TEXT | Review notes |
| `invest_decision` | TEXT | Investment decision |
| `invest_owner` | TEXT | Investment owner |
| `invest_effort` | TEXT | Effort estimate |
| `invest_notes` | TEXT | Investment notes |
| `first_seen` | TEXT | ISO timestamp of first sync |
| `last_seen` | TEXT | ISO timestamp of last sync |
| `source` | TEXT | `folder` or `zip` |

### Metrics Table: `sync_runs`

| Column | Type | Description |
|--------|------|-------------|
| `run_id` | INT PK | Auto-increment |
| `started_at` | TEXT | Sync start timestamp |
| `finished_at` | TEXT | Sync end timestamp |
| `source` | TEXT | Source type |
| `active_total_before` | INT | Active count before sync |
| `added_count` | INT | New resources added |
| `archived_count` | INT | Resources archived |
| `active_total_after` | INT | Active count after sync |

---

## The System Contract ⚠️

**Read `SYSTEM_CONTRACT.md` before making any changes.**

### Canonical Operational Predicate

```sql
WHERE is_archived = 0 AND is_placeholder = 0
```

### Canonical Function

All operational pages must use: **`get_active_containers()`**

### Reconciliation Rule

If Inventory shows **N**, then:
- Dashboard Total = **N**
- Scrubbing ≤ **N**
- Investment ≤ **N**

**No exceptions. No phantom data. No alternate query paths.**

---

## Sync Model (Reconciliation + Archiving)

Sync is explicit: **Tools → Sync Local Folder**

### Algorithm

1. **Record sync start**: `sync_started_at = datetime.utcnow()`
2. **Capture baseline**: `active_before = COUNT(*) WHERE is_archived = 0`
3. **Scan folder**: For each file/folder/link found:
   - Call `upsert_container()` with `last_seen_override=sync_started_at`
   - This sets `is_archived = 0` and `last_seen = sync_started_at`
4. **Archive stale**: After scan completes:
   ```sql
   UPDATE resource_containers 
   SET is_archived = 1 
   WHERE is_archived = 0 AND last_seen < sync_started_at
   ```
5. **Record metrics**: Save to `sync_runs` table

### Key Behaviors

| Action | Result |
|--------|--------|
| File deleted from source | `is_archived = 1` → disappears from all views |
| File added to source | `is_archived = 0` → appears immediately |
| File re-added (same path) | Reactivated with preserved decisions |
| Archived resources | Stay in DB for history, never shown operationally |

**No hard deletes.** Archived resources remain for CFO-level trend reporting.

---

## Page Responsibilities

| Page | Purpose | Data Source | Additional Filter |
|------|---------|-------------|-------------------|
| **Inventory** | Canonical active dataset | `get_active_containers()` | `resource_count > 0` (display) |
| **Dashboard** | Pure aggregation | `get_resource_totals()` | None — global rollup |
| **Scrubbing** | Review workflow | `get_active_containers()` | `scrub_status = 'not_reviewed'` |
| **Investment** | Investment tracking | `get_active_containers()` | `scrub_status IN ('gap','modify','invest')` |
| **Tools Export** | Historical audit | `get_all_containers()` | Explicitly labeled, never for KPIs |

---

## UI Display Rules (Inventory Table)

| Column | Rule |
|--------|------|
| **Type** | File extension uppercase (PDF, PNG), or FOLDER, or LINK |
| **Name** | Filename without extension |
| **Path** | Directory only (no filename); link path shows `.../links.txt` (hash removed) |
| **Count** | Always shown (usually 1) |

**No duplicate totals** — header count is the single authoritative total on the page.

---

## Key Functions Reference

### `db.py`

| Function | Returns | Filter |
|----------|---------|--------|
| `get_active_containers()` | List[Dict] | `is_archived = 0` |
| `get_all_containers()` | List[Dict] | None (all rows) |
| `get_resource_totals()` | Dict | `is_archived = 0 AND is_placeholder = 0` |
| `upsert_container()` | bool | Sets `is_archived = 0` on insert/update |
| `archive_stale_resources()` | int | Archives old rows after sync |
| `update_container_scrub()` | None | Updates scrub fields |

### `services/container_service.py`

| Function | Purpose |
|----------|---------|
| `import_from_folder()` | Main sync — scans folder, upserts, archives stale |
| `import_from_zip()` | Extracts ZIP and calls `import_from_folder()` |
| `get_tree_structure()` | Builds virtual folder tree for navigation |

---

## Common Pitfalls

### 1. Using `get_all_containers()` for operational views
**Wrong**: Dashboard/Inventory/Scrubbing calls `get_all_containers()`  
**Right**: Always use `get_active_containers()` for operational views

### 2. Forgetting the placeholder filter
`get_resource_totals()` must filter `is_placeholder = 0` or Dashboard will count structural nodes.

### 3. Not invalidating after sync
After sync, the page must rerun (`st.rerun()`) to show new counts.

### 4. Counting rows instead of resources
Inventory count = `SUM(resource_count)`, not `COUNT(*)`.

### 5. Introducing alternate query paths
Any new feature that queries resources must use `get_active_containers()` or it's wrong.

---

## Safety Rails for Future Changes

If you touch anything that could affect reconciliation, you **must** re-run these validations:

| Test | Action | Expected |
|------|--------|----------|
| **Add resources** | Add files → Sync | Inventory & Dashboard match |
| **Delete resources** | Delete files → Sync | Inventory drops, Dashboard matches |
| **Scrub subset** | Mark some reviewed | Dashboard % matches |
| **Empty links.txt** | Add empty file → Sync | No resources, no metric change |

**Any feature that introduces a second query path is a regression.**

---

## Where to Start When Debugging

1. **Verify query function**: 
   - Operational views → `get_active_containers()`
   - Export/history → `get_all_containers()` (acceptable)

2. **Verify operational predicate**:
   ```sql
   is_archived = 0 AND is_placeholder = 0
   ```

3. **Verify sync timestamp flow**:
   - `last_seen` set consistently before archiving stale records

4. **Compare counts**:
   - If Inventory ≠ Dashboard, one of them has a wrong query

---

## Running the App

```bash
cd training_catalog_analyzer
pip install -r requirements.txt
streamlit run Dashboard.py
```

App runs at: `http://localhost:8501`

---

## Metrics Rules (CFO-Safe)

- Counts are based on **training resources**, not files
- Operational totals come from the active dataset only
- Sync history is recorded in `sync_runs` for trend analysis
- Archived resources never affect active counts

---

## Future Enhancements

1. **SharePoint API integration** — replace local folder sync
2. **Trend reporting** — track resource churn over time using `sync_runs`
3. **Coverage gaps** — identify missing training by type
4. **Multi-user scrubbing** — track who reviewed what

---

## Final Words

This is a **metrics-driven system**. Every number on screen must trace back to:

```sql
SELECT ... FROM resource_containers WHERE is_archived = 0 AND is_placeholder = 0
```

If you can't trace a number to that query, it's wrong.

Read `SYSTEM_CONTRACT.md`. Follow it. Don't create shortcuts.
