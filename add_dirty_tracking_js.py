#!/usr/bin/env python3
"""
Add dirty tracking JavaScript to investment.html and inventory.html.
These templates keep their current per-row save pattern but add:
- Row highlighting on change
- Navigation warning when unsaved changes exist
"""
import os

def add_investment_js():
    """Add dirty tracking JS to investment.html before endblock."""
    f = 'tcm_app/templates/tcm_app/investment.html'
    if not os.path.exists(f):
        print(f"ERROR: {f} not found")
        return False
    
    c = open(f, 'r', encoding='utf-8').read()
    
    # Check if already has the JS
    if 'dirtyRows' in c:
        print(f"{f}: Already has dirty tracking JS, skipping")
        return True
    
    # Add navigation warning JS before endblock
    js_code = '''
<script>
document.addEventListener('DOMContentLoaded', function() {
    const dirtyRows = new Set();
    
    // Track changes on all form inputs
    document.querySelectorAll('.dirty-track').forEach(el => {
        const originalValue = el.value;
        el.dataset.originalValue = originalValue;
        
        el.addEventListener('change', function() {
            const row = this.closest('tr');
            if (!row) return;
            
            // Check if any field in this row differs from original
            let isDirty = false;
            row.querySelectorAll('.dirty-track').forEach(input => {
                if (input.value !== input.dataset.originalValue) {
                    isDirty = true;
                }
            });
            
            if (isDirty) {
                row.classList.add('table-warning');
                dirtyRows.add(row);
            } else {
                row.classList.remove('table-warning');
                dirtyRows.delete(row);
            }
        });
    });
    
    // Navigation warning when dirty
    window.addEventListener('beforeunload', function(e) {
        if (dirtyRows.size > 0) {
            e.preventDefault();
            e.returnValue = '';
            return '';
        }
    });
    
    // Clear dirty state when form submits (per-row save)
    document.querySelectorAll('form').forEach(form => {
        form.addEventListener('submit', function() {
            const row = this.closest('tr');
            if (row) {
                dirtyRows.delete(row);
            }
        });
    });
});
</script>
{% endblock %}'''
    
    c = c.replace('{% endblock %}', js_code)
    open(f, 'w', encoding='utf-8').write(c)
    print(f"Fixed {f}: Added dirty tracking JS")
    return True


def add_inventory_js():
    """Add dirty tracking JS to inventory.html."""
    f = 'tcm_app/templates/tcm_app/inventory.html'
    if not os.path.exists(f):
        print(f"ERROR: {f} not found")
        return False
    
    c = open(f, 'r', encoding='utf-8').read()
    
    # Check if already has the JS (look for our specific pattern)
    if 'dirtyRows' in c and 'beforeunload' in c:
        print(f"{f}: Already has dirty tracking JS, skipping")
        return True
    
    # The inventory template already has some JS - need to add to it or replace
    # Add navigation warning JS before endblock
    js_code = '''
<script>
document.addEventListener('DOMContentLoaded', function() {
    const dirtyRows = new Set();
    
    // Track changes on audience dropdowns
    document.querySelectorAll('.dirty-track').forEach(el => {
        const originalValue = el.value;
        el.dataset.originalValue = originalValue;
        
        // Remove auto-submit behavior, track instead
        el.removeAttribute('onchange');
        
        el.addEventListener('change', function() {
            const row = this.closest('tr');
            if (!row) return;
            
            if (this.value !== this.dataset.originalValue) {
                row.classList.add('table-warning');
                dirtyRows.add(row);
            } else {
                row.classList.remove('table-warning');
                dirtyRows.delete(row);
            }
        });
    });
    
    // Navigation warning when dirty
    window.addEventListener('beforeunload', function(e) {
        if (dirtyRows.size > 0) {
            e.preventDefault();
            e.returnValue = '';
            return '';
        }
    });
});
</script>
{% endblock %}'''
    
    c = c.replace('{% endblock %}', js_code)
    open(f, 'w', encoding='utf-8').write(c)
    print(f"Fixed {f}: Added dirty tracking JS")
    return True


if __name__ == '__main__':
    print("=" * 60)
    print("Adding Dirty Tracking JavaScript")
    print("=" * 60)
    
    results = []
    results.append(("Investment JS", add_investment_js()))
    results.append(("Inventory JS", add_inventory_js()))
    
    print("\n" + "=" * 60)
    print("Results:")
    for name, success in results:
        status = "✓" if success else "✗"
        print(f"  {status} {name}")
    
    if all(r[1] for r in results):
        print("\nDone! Run: pytest tests/test_template_compilation.py -q")
