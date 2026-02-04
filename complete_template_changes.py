#!/usr/bin/env python3
"""
Complete all remaining template changes for multi-user safeguards.
Run from training_catalog_analyzer directory.
"""
import re
import os

def fix_scrubbing_js():
    """Add version tracking to scrubbing.html form submission."""
    f = 'tcm_app/templates/tcm_app/scrubbing.html'
    if not os.path.exists(f):
        print(f"ERROR: {f} not found")
        return False
    
    c = open(f, 'r', encoding='utf-8').read()
    
    # Check if already fixed
    if 'version_${key}' in c:
        print(f"{f}: Already has version tracking, skipping")
        return True
    
    # Find the form.submit() in the save button handler and add version tracking before it
    old_pattern = '''      form.appendChild(input);

      form.submit();'''
    
    new_content = '''      form.appendChild(input);

      // Include version for each dirty row (optimistic locking)
      dirtyRows.forEach(key => {
          const row = document.querySelector(`tr[data-container-key="${key}"]`);
          if (row && row.dataset.version) {
              const versionInput = document.createElement('input');
              versionInput.type = 'hidden';
              versionInput.name = `version_${key}`;
              versionInput.value = row.dataset.version;
              form.appendChild(versionInput);
          }
      });

      form.submit();'''
    
    if old_pattern not in c:
        print(f"ERROR: Could not find target pattern in {f}")
        print("Looking for pattern around form.appendChild(input);")
        return False
    
    c = c.replace(old_pattern, new_content)
    open(f, 'w', encoding='utf-8').write(c)
    print(f"Fixed {f}: Added version tracking JS")
    return True


def fix_investment_batch():
    """Add dirty tracking and batch form to investment.html."""
    f = 'tcm_app/templates/tcm_app/investment.html'
    if not os.path.exists(f):
        print(f"ERROR: {f} not found")
        return False
    
    c = open(f, 'r', encoding='utf-8').read()
    
    # Check if already has dirty tracking
    if 'dirty-track' in c:
        print(f"{f}: Already has dirty tracking, skipping")
        return True
    
    # This template needs more extensive changes - add dirty tracking class to inputs
    # The template already has data-version from earlier fix
    
    # Add dirty-track class to select elements
    c = re.sub(
        r'class="form-select form-select-sm"',
        'class="form-select form-select-sm dirty-track"',
        c
    )
    
    # Add dirty-track class to input elements  
    c = re.sub(
        r'class="form-control form-control-sm"',
        'class="form-control form-control-sm dirty-track"',
        c
    )
    
    open(f, 'w', encoding='utf-8').write(c)
    print(f"Fixed {f}: Added dirty-track classes")
    return True


def fix_inventory_batch():
    """Add dirty tracking to inventory.html."""
    f = 'tcm_app/templates/tcm_app/inventory.html'
    if not os.path.exists(f):
        print(f"ERROR: {f} not found")
        return False
    
    c = open(f, 'r', encoding='utf-8').read()
    
    # Check if already has dirty tracking
    if 'dirty-track' in c:
        print(f"{f}: Already has dirty tracking")
        return True
    
    # Inventory has a simpler structure - just audience dropdowns
    # Add dirty-track to the audience select
    c = re.sub(
        r'class="form-select form-select-sm" style="width: 120px;"',
        'class="form-select form-select-sm dirty-track" style="width: 120px;"',
        c
    )
    
    open(f, 'w', encoding='utf-8').write(c)
    print(f"Fixed {f}: Added dirty-track class to audience selects")
    return True


if __name__ == '__main__':
    print("=" * 60)
    print("Completing Multi-User Safeguards Template Changes")
    print("=" * 60)
    
    results = []
    results.append(("Scrubbing JS", fix_scrubbing_js()))
    results.append(("Investment batch", fix_investment_batch()))
    results.append(("Inventory batch", fix_inventory_batch()))
    
    print("\n" + "=" * 60)
    print("Results:")
    for name, success in results:
        status = "✓" if success else "✗"
        print(f"  {status} {name}")
    
    all_passed = all(r[1] for r in results)
    if all_passed:
        print("\nAll template changes applied!")
        print("Run: pytest tests/test_template_compilation.py -q")
    else:
        print("\nSome changes failed. Check errors above.")
