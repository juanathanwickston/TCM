# System Contract

## Canonical Rule

> **All operational pages (Inventory, Dashboard, Scrubbing, Investment, and navigation trees) must query only active, non-placeholder resources using `WHERE is_archived = 0 AND is_placeholder = 0` via `get_active_containers()`. Inventory additionally applies `resource_count > 0` as a display-only filter.**

---

## Definitions

| Term | Meaning |
|------|---------|
| **Training Resource** | A single actionable unit: file, folder, or URL from `links.txt` |
| **Active Resource** | `is_archived = 0` — exists in source folder at last sync |
| **Archived Resource** | `is_archived = 1` — removed from source, retained for history |
| **Placeholder** | `is_placeholder = 1` — structural node with no consumable content |

---

## Query Rules

### Operational Views (Inventory, Dashboard, Scrubbing, Investment)

```sql
WHERE is_archived = 0 AND is_placeholder = 0
```

**Use:** `get_active_containers()` or `get_resource_totals()`

### Historical/Export Views (Tools → Export)

```sql
-- No filter (all rows)
```

**Use:** `get_all_containers()` — explicitly labeled, never for KPIs

---

## Page Contracts

| Page | Data Source | Additional Filter |
|------|-------------|-------------------|
| **Inventory** | `get_active_containers()` | `resource_count > 0` (display) |
| **Dashboard** | `get_resource_totals()` | None — global rollup |
| **Scrubbing** | `get_active_containers()` | `scrub_status = 'not_reviewed'` |
| **Investment** | `get_active_containers()` | `scrub_status IN ('gap','modify','invest')` |
| **Tools Export** | `get_all_containers()` | None — historical audit |

---

## Discipline Rules

1. **No alternative query paths.** New pages/features use `get_active_containers()` or they're wrong.

2. **Historical views must be labeled.** Only allowed for export/audit, never operational KPIs.

3. **Reconciliation is mandatory.** If Inventory shows N, Dashboard shows N. No exceptions.

4. **Archive on sync.** Resources not found in source → `is_archived = 1`. Immediate effect on all views.

---

## Validation Proof

All tests passed 2026-01-15:

| Test | Result |
|------|--------|
| Zero-resource branch (empty `links.txt`) | Correctly excluded |
| Archive reconciliation (add 2, delete 2) | Counts match: 3 → 1 |
| Scrubbing subset (2/5 reviewed) | Dashboard = 40% |
