# AUDIT_REPORT.md — Codebase Cleanliness Audit (REVISED)

**Date**: 2026-01-20  
**Auditor**: Automated Agent  
**Status**: AUDIT COMPLETE — REVISED per hardened spec

---

## 1. Repo Fingerprint

| Property | Value |
|----------|-------|
| Git | Not available (Git not on PATH) |
| Snapshot Method | SHA256 manifest (see `baseline_manifest.txt`) |
| Python Version | 3.12.10 |
| OS | Windows |
| Install Method | pip (requirements.txt) |
| Static Analyzer | ruff 0.x |

### Baseline Control

**Method**: File hash manifest created before any edits.

**Manifest Location**: `docs/audit/baseline_manifest.txt`

**Format**: `SHA256  relative_path`

---

## 2. Inventory of Violations (With Evidence)

### A. Emoji Violations (Runtime Code)

| File | Line | Match | Evidence |
|------|------|-------|----------|
| `views/scrubbing.py` | 307 | `📁` | `rg -n "📁" views/` → `views\scrubbing.py:307:st.caption(f"📁 Contains {rc} resources")` |
| `components/sidebar_router.py` | 110 | `💬` | `rg -n "💬" components/` → `components\sidebar_router.py:110:st.markdown("### 💬 Assistant")` |

**Command used**: ripgrep via `grep_search` tool with exact emoji patterns

**Tests exempt**: `tests/test_metrics_mock.py` contains ✓ checkmarks in test output (allowed per spec)

### B. Prompt Leakage

| File | Line | Match | Evidence |
|------|------|-------|----------|
| `components/sidebar_router.py` | 89 | `ChatGPT-style` | `rg -ni "chatgpt" .` → `components\sidebar_router.py:89:ChatGPT-style: chat fills entire sidebar...` |

**Additional check for `conversation`**:
- `sidebar_router.py:113` — `# Conversation container` — This is borderline but will be reworded to `# Chat history container`

**Command used**: `rg -ni "chatgpt|openai|master prompt|per prompt|user asked|as requested|conversation|llm|agent" . --glob "*.py"`

### C. Debug Statements (Runtime)

**Result**: NONE in runtime code.

**Evidence**: 
```
rg -n "print\(" views/ services/ components/ db.py app.py
→ No matches
```

All `print()` calls are in `tests/` and `scripts/` (allowed per spec).

### D. Unused Imports / Dead Code

**Tool**: `ruff check . --select F401,F841`

**Result**: 23 errors found (20 auto-fixable)

| File | Line | Issue |
|------|------|-------|
| `views/scrubbing.py` | 14 | `typing.Optional` imported but unused |
| `views/scrubbing.py` | 22 | `services.signal_service.get_flag_display_text` imported but unused |
| `views/tools.py` | 16 | `components.layout.error_message` imported but unused |
| `services/container_service.py` | 15 | `json` imported but unused |
| (+ 19 more) | | |

**Full output available**: Run `ruff check . --select F401,F841`

**Disposition**: Fix with `ruff check . --select F401,F841 --fix`

### E. TODO/FIXME/HACK

**Result**: None found.

**Command**: `rg -n "TODO|FIXME|HACK|XXX" . --glob "*.py"`
**Output**: No matches

---

## 3. CONTRACT VIOLATION: Investment Page (MUST FIX)

### The Defect

**Location**: `db.py:353-364`

**Function**: `get_containers_by_scrub_status()`

**Issue**: Does NOT include canonical predicate `is_archived = 0 AND is_placeholder = 0`

**Current code**:
```python
cursor.execute(
    f"SELECT * FROM resource_containers WHERE scrub_status IN ({placeholders})",
    statuses
)
```

**Impact**: Investment page can show archived/placeholder containers, violating the system contract.

### The Fix (Minimal Diff)

```diff
 def get_containers_by_scrub_status(statuses: List[str]) -> List[Dict[str, Any]]:
-    """Get containers filtered by scrub status."""
+    """Get ACTIVE containers filtered by scrub status.
+    
+    Uses canonical predicate: is_archived = 0 AND is_placeholder = 0
+    """
     conn = get_connection()
     cursor = conn.cursor()
     placeholders = ",".join("?" * len(statuses))
     cursor.execute(
-        f"SELECT * FROM resource_containers WHERE scrub_status IN ({placeholders})",
+        f"SELECT * FROM resource_containers WHERE is_archived = 0 AND is_placeholder = 0 AND scrub_status IN ({placeholders})",
         statuses
     )
     rows = cursor.fetchall()
     conn.close()
     return [dict(row) for row in rows]
```

**Risk**: LOW — this enforces existing contract, does not change expected behavior

---

## 4. Metrics Reconciliation

### Baseline Values (2026-01-20)

| Metric | Value | Query |
|--------|-------|-------|
| Dashboard Total | 13 | `kpi_service.get_submission_summary()['total']` |
| Inventory Total | 13 | `SUM(resource_count) WHERE is_archived=0 AND is_placeholder=0` |
| Scrubbing Queue | 10 | `not_reviewed` status count |
| Investment Queue | 2 | `Modify` status count |

### Reconciliation

| Check | Result | Status |
|-------|--------|--------|
| Dashboard total == Inventory total | 13 == 13 | ✅ PASS |
| Scrubbing count ≤ Total | 10 ≤ 13 | ✅ PASS |
| Investment count ≤ Total | 2 ≤ 13 | ✅ PASS |

### Canonical Locations

| Function | File | Line | Predicate |
|----------|------|------|-----------|
| `get_active_containers()` | `db.py` | 742 | `is_archived = 0 AND is_placeholder = 0` |
| `get_submission_summary()` | `services/kpi_service.py` | 506-513 | Same predicate in SQL |
| `get_containers_by_scrub_status()` | `db.py` | 353 | **MISSING** → FIX |

---

## 5. Gate Script Specification

### File: `scripts/audit_gate.py`

**Purpose**: Deterministic cleanliness check, runnable offline.

**Checks**:

1. **Emoji check**: Scan `views/`, `services/`, `components/`, `db.py`, `app.py` for emoji chars
2. **Prompt leakage**: Scan for `ChatGPT|OpenAI|master prompt|per prompt|user asked|LLM|agent`
3. **Debug statements**: Scan for `print(` in runtime code
4. **Canonical predicate enforcement**: Verify `get_containers_by_scrub_status` includes canonical predicate
5. **Metrics reconciliation**: Query DB directly:
   - `inventory_total = SUM(resource_count) FROM resource_containers WHERE is_archived=0 AND is_placeholder=0`
   - `dashboard_total = kpi_service.get_submission_summary()['total']`
   - Assert `inventory_total == dashboard_total`

**Exit codes**:
- 0 = All checks pass
- 1 = One or more checks fail (with specific error message)

---

## 6. Summary

| Category | Count | Action |
|----------|-------|--------|
| Emojis (runtime) | 2 | Remove |
| Prompt leakage | 1 | Reword |
| Unused imports | 23 | Fix via ruff |
| Contract violations | 1 | Fix Investment predicate |
| print() in runtime | 0 | Clean |
| Dead code | Not proven | (vulture not available) |

**Verdict**: 

- 4 cosmetic fixes (emojis + prompt text)
- 23 unused import fixes (auto-fixable)
- 1 contract violation fix (Investment predicate)
- 1 gate script to add

---

## 7. Approval Checklist

- [ ] Baseline manifest verified
- [ ] All evidence commands verifiable
- [ ] Investment defect fix approved
- [ ] Unused import auto-fix approved
- [ ] Gate script spec approved
