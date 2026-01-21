# CLEANUP_PLAN.md — Codebase Cleanliness Audit (REVISED)

**Date**: 2026-01-20  
**Status**: PENDING APPROVAL — Revised per hardened spec

---

## Version Control

**Method**: SHA256 file manifest

**Baseline**: `docs/audit/baseline_manifest.txt` (to be created before edits)

**Post-change verification**: Diff manifest after changes complete

---

## Pre-Execution Checklist

- [ ] Baseline manifest created
- [ ] User approval received
- [ ] All changes follow scope lock

---

## Planned Changes (Commit Order per Spec)

### Commit 1: Add Audit Tooling (No Behavior Changes)

| # | Action | File | Risk |
|---|--------|------|------|
| 1.1 | Create gate script | `scripts/audit_gate.py` | None |

---

### Commit 2: Remove Dead Code / Unused Imports (No Behavior Changes)

| # | Action | File | Line | Evidence |
|---|--------|------|------|----------|
| 2.1 | Remove unused import | `views/scrubbing.py` | 14 | ruff F401 |
| 2.2 | Remove unused import | `views/scrubbing.py` | 22 | ruff F401 |
| 2.3 | Remove unused import | `views/tools.py` | 16 | ruff F401 |
| 2.4 | Remove unused import | `services/container_service.py` | 15 | ruff F401 |
| ... | (20 total auto-fixable) | various | | ruff --fix |

**Command**: `ruff check . --select F401,F841 --fix`

---

### Commit 3: Style-Only Fixes (No Behavior Changes)

| # | Action | File | Line | Current | Proposed | Risk |
|---|--------|------|------|---------|----------|------|
| 3.1 | Remove emoji | `views/scrubbing.py` | 307 | `📁 Contains` | `Contains` | None |
| 3.2 | Remove emoji | `components/sidebar_router.py` | 110 | `### 💬 Assistant` | `### Assistant` | None |
| 3.3 | Reword comment | `components/sidebar_router.py` | 89 | `ChatGPT-style:` | `Chat UI style:` | None |
| 3.4 | Reword comment | `components/sidebar_router.py` | 113 | `# Conversation container` | `# Chat history container` | None |

---

### Commit 4: Contract Violation Fix (Behavioral — Enforces Existing Contract)

| # | Action | File | Line | Evidence |
|---|--------|------|------|----------|
| 4.1 | Add canonical predicate | `db.py` | 359 | Investment page contract violation |

**Current**:
```python
f"SELECT * FROM resource_containers WHERE scrub_status IN ({placeholders})"
```

**Fixed**:
```python
f"SELECT * FROM resource_containers WHERE is_archived = 0 AND is_placeholder = 0 AND scrub_status IN ({placeholders})"
```

**Before/After Proof**: 
- Before: Investment could show archived containers (0 currently, but contract violated)
- After: Investment only shows active containers (matches Inventory/Dashboard behavior)

**Reconciliation**:
- Investment count will be ≤ Inventory total ✅
- Uses same predicate as all other operational pages ✅

---

## Files Modified (Complete List)

| File | Scope | Commit |
|------|-------|--------|
| `scripts/audit_gate.py` | NEW | 1 |
| `views/scrubbing.py` | 2 lines (import + emoji) | 2, 3 |
| `views/tools.py` | 1 line (import) | 2 |
| `services/container_service.py` | 1 line (import) | 2 |
| `components/sidebar_router.py` | 3 lines (emoji + comments) | 3 |
| `db.py` | 1 line (predicate fix) | 4 |
| (other files with unused imports) | various | 2 |

---

## Files NOT Modified (Scope Lock)

- All views except specified imports/emoji
- All services except specified imports
- All models
- All SQL queries (except Investment predicate fix)
- `Payroc Training Catalogue/`

---

## Verification Protocol

### After Each Commit

1. Run `streamlit run app.py` — verify app launches
2. Navigate to all 5 pages — verify no crashes
3. Check Dashboard total == Inventory total
4. Run `python scripts/audit_gate.py` — verify all gates pass

### After Commit 4 (Contract Fix)

1. Query Investment count directly
2. Verify count ≤ Inventory total
3. Verify Investment only shows active containers

---

## Rollback Plan

| Commit | Rollback |
|--------|----------|
| 1 | Delete `scripts/audit_gate.py` |
| 2 | `ruff` changes are import removals — safe to revert |
| 3 | Restore emoji/comments from baseline |
| 4 | Remove `is_archived = 0 AND is_placeholder = 0` from query |

---

## Approval Required

Before proceeding:

1. ✅ Baseline manifest will be created
2. ✅ Evidence is command-based and verifiable  
3. ✅ Dead code audited via ruff (23 issues found)
4. ✅ Investment defect is IN SCOPE (contract enforcement)
5. ✅ Gate script enforces contract + reconciliation

Reply **APPROVED** to proceed with execution.
