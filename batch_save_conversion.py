#!/usr/bin/env python3
"""
Batch Save Conversion Script
============================
Converts Investment and Inventory pages from per-row save to batch "Save All Changes" pattern.

Following PRE-FLIGHT-CHANGES discipline:
- Phase 1: Research complete (read all templates)
- Phase 2: Plan approved
- Phase 3: This script implements changes
- Phase 4: Template tests verify

Changes:
1. Investment: Remove per-row forms, add batch form + Save All button + JS
2. Inventory: Remove per-row forms + auto-submit, add batch form + Save All button + JS
"""
import os
import re

BASE_DIR = 'tcm_app/templates/tcm_app'

# ============================================================================
# INVESTMENT PAGE
# ============================================================================

INVESTMENT_TEMPLATE = '''{% extends "tcm_app/base.html" %}
{% load static %}

{% block title %}Investment | TCM{% endblock %}

{% block content %}
<div class="container-fluid py-4">
  <div class="d-flex align-items-center justify-content-between mb-3">
    <div>
      <h1 class="h3 mb-1">Investment Planning</h1>
      <div class="text-muted">Build/Buy/Assign decisions for Modify items</div>
    </div>
  </div>

  <!-- Summary KPIs -->
  <div class="row g-3 mb-4">
    <div class="col-md-4">
      <div class="card text-center">
        <div class="card-body">
          <div class="h4 mb-1">{{ total_count }}</div>
          <div class="text-muted small">Total Queue</div>
        </div>
      </div>
    </div>
    <div class="col-md-4">
      <div class="card text-center">
        <div class="card-body">
          <div class="h4 mb-1">{{ decided_count }}</div>
          <div class="text-muted small">Decided</div>
        </div>
      </div>
    </div>
    <div class="col-md-4">
      <div class="card text-center">
        <div class="card-body">
          <div class="h4 mb-1">{{ pending_count }}</div>
          <div class="text-muted small">Pending</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Filters and Save Button -->
  <div class="d-flex align-items-center justify-content-between mb-4">
    <form method="get" class="d-flex align-items-center gap-2">
      <label class="form-label mb-0 text-muted">Decision:</label>
      <select name="decision_filter" class="form-select form-select-sm" style="width:auto;">
        {% for value, label in decision_options %}
        <option value="{{ value }}" {% if filter_decision == value %}selected{% endif %}>{{ label }}</option>
        {% endfor %}
      </select>
    </form>
    <div class="d-flex align-items-center gap-3">
      <span class="text-muted small">Showing {{ containers|length }} items</span>
      <button type="button" id="global-save" class="btn btn-primary" disabled>Save All Changes</button>
    </div>
  </div>

  <form id="invest-form" method="post" action="{% url 'save_investment_batch' %}">
    {% csrf_token %}
    <input type="hidden" name="decision_filter" value="{{ filter_decision }}">
    <input type="hidden" name="current_page" value="{{ page_obj.number|default:1 }}">

    {% include 'tcm_app/partials/pagination.html' %}

    <!-- Container Table -->
    <div class="card">
      <div class="table-responsive">
        <table class="table table-hover mb-0 align-middle investment-table tcm-fixed-table">
          <colgroup>
            <col style="width: 30%"> <!-- Name -->
            <col style="width: 14%"> <!-- Decision -->
            <col style="width: 14%"> <!-- Owner -->
            <col style="width: 12%"> <!-- Effort/Cost -->
            <col style="width: 30%"> <!-- Notes -->
          </colgroup>
          <thead>
            <tr>
              <th>Name</th>
              <th>Decision</th>
              <th>Owner</th>
              <th>Effort/Cost</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody>
            {% for c in containers %}
            <tr data-container-key="{{ c.resource_key }}"
                data-original-decision="{{ c.invest_decision|default:'' }}"
                data-original-owner="{{ c.invest_owner|default:'' }}"
                data-original-effort="{{ c.invest_effort|default:'' }}"
                data-original-notes="{{ c.invest_notes|default:'' }}">
              <td title="{{ c.display_name }}">
                <div class="fw-semibold">{{ c.display_name }}</div>
                <div class="text-muted small" title="{{ c.relative_path }}">{{ c.relative_path }}</div>
              </td>
              <td>
                <select name="decision_{{ c.resource_key }}" class="form-select form-select-sm dirty-track" style="width:auto;">
                  <option value="" {% if not c.invest_decision %}selected{% endif %}>-</option>
                  {% for key, label in invest_choices %}
                  <option value="{{ key }}" {% if c.invest_decision == key %}selected{% endif %}>{{ label }}</option>
                  {% endfor %}
                </select>
              </td>
              <td>
                <input type="text" name="owner_{{ c.resource_key }}" class="form-control form-control-sm dirty-track"
                  value="{{ c.invest_owner|default_if_none:'' }}" placeholder="Owner">
              </td>
              <td>
                <input type="text" name="effort_{{ c.resource_key }}" class="form-control form-control-sm dirty-track"
                  value="{{ c.invest_effort|default_if_none:'' }}" placeholder="e.g., 2 weeks">
              </td>
              <td>
                <input type="text" name="notes_{{ c.resource_key }}" class="form-control form-control-sm dirty-track"
                  value="{{ c.invest_notes|default_if_none:'' }}" placeholder="Notes">
              </td>
            </tr>
            {% empty %}
            <tr>
              <td colspan="5" class="text-center text-muted py-4">No items in this queue. Complete Scrubbing to add Modify items.</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
    </div>
  </form>
</div>

<script>
(function() {
  /**
   * INVESTMENT BATCH SAVE - Matching Scrubbing Pattern
   */
  const form = document.getElementById('invest-form');
  const saveBtn = document.getElementById('global-save');
  const saveBtnOriginalText = 'Save All Changes';
  const dirtyRows = new Set();
  let isSaving = false;

  // Track changes to editable fields
  document.querySelectorAll('.dirty-track').forEach(function(el) {
    el.addEventListener('change', function() {
      const row = this.closest('tr');
      if (!row) return;
      const key = row.dataset.containerKey;

      // Get original values
      const origDecision = row.dataset.originalDecision;
      const origOwner = row.dataset.originalOwner;
      const origEffort = row.dataset.originalEffort;
      const origNotes = row.dataset.originalNotes;

      // Get current values
      const currDecision = row.querySelector('[name^="decision_"]').value;
      const currOwner = row.querySelector('[name^="owner_"]').value;
      const currEffort = row.querySelector('[name^="effort_"]').value;
      const currNotes = row.querySelector('[name^="notes_"]').value;

      // Logical dirty check
      const isDirty = (currDecision !== origDecision) ||
        (currOwner !== origOwner) ||
        (currEffort !== origEffort) ||
        (currNotes !== origNotes);

      if (isDirty) {
        dirtyRows.add(key);
        row.classList.add('table-warning');
      } else {
        dirtyRows.delete(key);
        row.classList.remove('table-warning');
      }
      updateSaveButton();
    });

    // Real-time tracking for text inputs
    if (el.tagName === 'INPUT') {
      el.addEventListener('input', function() {
        this.dispatchEvent(new Event('change'));
      });
    }
  });

  function updateSaveButton() {
    if (isSaving) {
      saveBtn.disabled = true;
      saveBtn.textContent = 'Saving...';
    } else {
      saveBtn.disabled = dirtyRows.size === 0;
      saveBtn.textContent = saveBtnOriginalText;
    }
  }

  // Save button click handler
  saveBtn.addEventListener('click', function() {
    if (dirtyRows.size === 0 || isSaving) return;
    isSaving = true;
    updateSaveButton();

    // Add dirty_keys hidden input
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'dirty_keys';
    input.value = Array.from(dirtyRows).join(',');
    form.appendChild(input);

    form.submit();
  });

  // Navigation warning
  window.addEventListener('beforeunload', function(e) {
    if (dirtyRows.size > 0 && !isSaving) {
      e.preventDefault();
      e.returnValue = '';
      return '';
    }
  });

  // Pagination warning
  document.addEventListener('click', function(e) {
    const link = e.target.closest('.pagination-link');
    if (link && dirtyRows.size > 0) {
      e.preventDefault();
      const confirmed = confirm('There are unsaved changes. Save before going to next page?');
      if (confirmed) {
        saveBtn.click();
      }
    }
  });

  // Filter dropdown warning
  const filterSelect = document.querySelector('select[name="decision_filter"]');
  if (filterSelect) {
    filterSelect.addEventListener('change', function(e) {
      if (dirtyRows.size > 0) {
        const confirmed = confirm('There are unsaved changes. They will be lost if you change the filter. Continue?');
        if (!confirmed) {
          e.preventDefault();
          e.stopPropagation();
          this.value = '{{ filter_decision|escapejs }}';
          return false;
        }
      }
      this.form.submit();
    });
  }
})();
</script>
{% endblock %}
'''

# ============================================================================
# INVENTORY PAGE
# ============================================================================

INVENTORY_TEMPLATE = '''{% extends 'tcm_app/base.html' %}
{% load tcm_tags %}

{% block title %}Inventory | TCM{% endblock %}

{% block content %}
<!-- INVENTORY TEMPLATE FINGERPRINT: 2026-02-02-BATCH-SAVE -->
<style>
    /* Inventory Table - Enterprise-grade polish */
    .inventory-table th,
    .inventory-table td {
        vertical-align: middle;
        padding: 0.6rem 0.75rem;
    }
    .inventory-table td.col-name { text-align: left; }
    .inventory-table td.col-type { text-align: center; }
    .inventory-table td.col-audience { vertical-align: middle; }
    .inventory-table td.col-contents { text-align: center; white-space: nowrap; }
    .inventory-table td.col-path { text-align: left; }
    .inventory-table .badge { min-width: 50px; font-size: 0.7rem; }
    .inventory-table .form-select-sm { padding-top: 0.2rem; padding-bottom: 0.2rem; }
</style>

<div class="container-fluid">
    <div class="d-flex justify-content-between align-items-center mb-4">
        <div>
            <h1 class="h3 mb-0">Inventory</h1>
            <p class="text-muted mb-0">Browse and filter training content</p>
        </div>
    </div>

    <!-- Filter Bar -->
    <div class="card mb-4">
        <div class="card-body">
            <form method="get" class="row g-3">
                <div class="col-md-3">
                    <label for="department" class="form-label">Department</label>
                    <select class="form-select" id="department" name="department">
                        <option value="">All Departments</option>
                        {% for dept in departments %}
                        <option value="{{ dept }}" {% if current_department == dept %}selected{% endif %}>{{ dept }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="col-md-3">
                    <label for="training_type" class="form-label">Training Type</label>
                    <select class="form-select" id="training_type" name="training_type">
                        <option value="">All Types</option>
                        {% for tt in training_types %}
                        <option value="{{ tt }}" {% if current_training_type == tt %}selected{% endif %}>{{ training_type_labels|get_item:tt|default:tt }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="col-md-3">
                    <label for="sales_stage" class="form-label">Sales Stage</label>
                    <select class="form-select" id="sales_stage" name="sales_stage">
                        <option value="">All</option>
                        <option value="untagged" {% if current_sales_stage == 'untagged' %}selected{% endif %}>Untagged</option>
                        {% for stage_key, stage_label in sales_stages %}
                        <option value="{{ stage_key }}" {% if current_sales_stage == stage_key %}selected{% endif %}>{{ stage_label }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="col-md-2">
                    <label for="audience_filter" class="form-label">Audience</label>
                    <select class="form-select" id="audience_filter" name="audience">
                        <option value="">All</option>
                        <option value="unassigned" {% if current_audience == 'unassigned' %}selected{% endif %}>Unassigned</option>
                        {% for aud in audiences %}
                        <option value="{{ aud }}" {% if current_audience == aud %}selected{% endif %}>{{ aud }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="col-md-1 d-flex align-items-end">
                    <button type="submit" class="btn btn-outline-secondary">Filter</button>
                </div>
            </form>
        </div>
    </div>

    <!-- Summary Header with Save Button -->
    <div class="d-flex align-items-center justify-content-between mb-3">
        <div class="d-flex align-items-center gap-3">
            <h4 class="mb-0">Total resources ({{ total_resources|intcomma }})</h4>
            <span class="badge bg-secondary">
                {% if current_department %}{{ current_department }}{% endif %}
                {% if current_training_type %} / {{ training_type_labels|get_item:current_training_type|default:current_training_type }}{% endif %}
                {% if not current_department and not current_training_type %}All Resources{% endif %}
            </span>
        </div>
        <button type="button" id="global-save" class="btn btn-primary" disabled>Save All Changes</button>
    </div>

    {% include 'tcm_app/partials/pagination.html' %}

    <!-- Container Table -->
    {% if containers %}
    <form id="audience-form" method="post" action="{% url 'save_audience_batch' %}">
        {% csrf_token %}
        <input type="hidden" name="department" value="{{ current_department }}">
        <input type="hidden" name="training_type" value="{{ current_training_type }}">
        <input type="hidden" name="sales_stage" value="{{ current_sales_stage }}">
        <input type="hidden" name="audience_filter" value="{{ current_audience }}">
        <input type="hidden" name="current_page" value="{{ page_obj.number|default:1 }}">

        <div class="card">
            <div class="card-body p-0">
                <div class="table-responsive">
                    <table class="table table-hover mb-0 inventory-table">
                        <thead class="table-light">
                            <tr>
                                <th style="min-width: 280px;">Name</th>
                                <th style="width: 70px; text-align: center;">Type</th>
                                <th style="width: 140px;">Audience</th>
                                <th style="width: 90px; text-align: center;">Contents</th>
                                <th>Path</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for c in containers %}
                            <tr data-container-key="{{ c.resource_key }}" data-original-audience="{{ c.audience|default:'' }}">
                                <td class="col-name">{{ c.display_name }}</td>
                                <td class="col-type">
                                    {% if c.resource_type == 'folder' %}
                                    <span class="badge bg-primary">FOLDER</span>
                                    {% elif c.resource_type == 'link' %}
                                    <span class="badge bg-info">LINK</span>
                                    {% else %}
                                    <span class="badge bg-secondary">FILE</span>
                                    {% endif %}
                                </td>
                                <td class="col-audience">
                                    <select name="audience_{{ c.resource_key }}" class="form-select form-select-sm dirty-track" style="width: 120px;">
                                        <option value="">-</option>
                                        {% for aud in audiences %}
                                        <option value="{{ aud }}" {% if c.audience == aud %}selected{% endif %}>{{ aud }}</option>
                                        {% endfor %}
                                    </select>
                                </td>
                                <td class="col-contents">
                                    {% if c.resource_type == 'folder' %}
                                    {{ c.contents_count|default:0 }}
                                    {% else %}
                                    Single File
                                    {% endif %}
                                </td>
                                <td class="col-path"><small class="text-muted">{{ c.relative_path|split_hash }}</small></td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </form>
    {% else %}
    <div class="alert alert-info">
        <h5 class="alert-heading">No resources match the current filters</h5>
        <p class="mb-0">Adjust filters or sync content from the Tools page.</p>
    </div>
    {% endif %}
</div>

<script>
(function() {
  /**
   * INVENTORY BATCH SAVE - Matching Scrubbing Pattern
   */
  const form = document.getElementById('audience-form');
  const saveBtn = document.getElementById('global-save');
  if (!form || !saveBtn) return; // Guard against empty state

  const saveBtnOriginalText = 'Save All Changes';
  const dirtyRows = new Set();
  let isSaving = false;

  // Track changes to audience dropdowns
  document.querySelectorAll('.dirty-track').forEach(function(el) {
    el.addEventListener('change', function() {
      const row = this.closest('tr');
      if (!row) return;
      const key = row.dataset.containerKey;
      const origAudience = row.dataset.originalAudience;
      const currAudience = this.value;

      if (currAudience !== origAudience) {
        dirtyRows.add(key);
        row.classList.add('table-warning');
      } else {
        dirtyRows.delete(key);
        row.classList.remove('table-warning');
      }
      updateSaveButton();
    });
  });

  function updateSaveButton() {
    if (isSaving) {
      saveBtn.disabled = true;
      saveBtn.textContent = 'Saving...';
    } else {
      saveBtn.disabled = dirtyRows.size === 0;
      saveBtn.textContent = saveBtnOriginalText;
    }
  }

  // Save button click handler
  saveBtn.addEventListener('click', function() {
    if (dirtyRows.size === 0 || isSaving) return;
    isSaving = true;
    updateSaveButton();

    // Add dirty_keys hidden input
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'dirty_keys';
    input.value = Array.from(dirtyRows).join(',');
    form.appendChild(input);

    form.submit();
  });

  // Navigation warning
  window.addEventListener('beforeunload', function(e) {
    if (dirtyRows.size > 0 && !isSaving) {
      e.preventDefault();
      e.returnValue = '';
      return '';
    }
  });

  // Pagination warning
  document.addEventListener('click', function(e) {
    const link = e.target.closest('.pagination-link');
    if (link && dirtyRows.size > 0) {
      e.preventDefault();
      const confirmed = confirm('There are unsaved changes. Save before going to next page?');
      if (confirmed) {
        saveBtn.click();
      }
    }
  });

  // Filter dropdowns warning
  document.querySelectorAll('#department, #training_type, #sales_stage, #audience_filter').forEach(function(select) {
    select.addEventListener('change', function(e) {
      if (dirtyRows.size > 0) {
        const confirmed = confirm('There are unsaved changes. They will be lost if you change the filter. Continue?');
        if (!confirmed) {
          e.preventDefault();
          e.stopPropagation();
          location.reload();
          return false;
        }
      }
      this.form.submit();
    });
  });
})();
</script>
{% endblock %}
'''


def write_template(filename, content):
    """Write template file with explicit encoding."""
    filepath = os.path.join(BASE_DIR, filename)
    with open(filepath, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)
    print(f"✓ Wrote {filepath}")
    return filepath


def verify_template(filepath):
    """Verify template was written correctly."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Check for key markers
    checks = [
        ('global-save', 'Save button'),
        ('dirty-track', 'Dirty tracking class'),
        ('dirtyRows', 'JS dirty tracking'),
        ('Save All Changes', 'Button text'),
    ]
    
    all_passed = True
    for marker, description in checks:
        if marker in content:
            print(f"  ✓ {description} present")
        else:
            print(f"  ✗ {description} MISSING")
            all_passed = False
    
    return all_passed


if __name__ == '__main__':
    print("=" * 60)
    print("BATCH SAVE CONVERSION")
    print("=" * 60)
    print()
    
    # Investment
    print("Investment Page:")
    invest_path = write_template('investment.html', INVESTMENT_TEMPLATE)
    verify_template(invest_path)
    print()
    
    # Inventory
    print("Inventory Page:")
    inv_path = write_template('inventory.html', INVENTORY_TEMPLATE)
    verify_template(inv_path)
    print()
    
    print("=" * 60)
    print("NEXT: Run template tests")
    print("  pytest tests/test_template_compilation.py -q")
    print("=" * 60)
