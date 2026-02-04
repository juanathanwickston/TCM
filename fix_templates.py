#!/usr/bin/env python3
"""
Fix template files by adding data-version attributes.
Run this from the training_catalog_analyzer directory AFTER running:
    git restore tcm_app/templates/tcm_app/scrubbing.html tcm_app/templates/tcm_app/investment.html
"""
import re
import os

def fix_scrubbing():
    f = 'tcm_app/templates/tcm_app/scrubbing.html'
    if not os.path.exists(f):
        print(f"ERROR: {f} not found")
        return False
    
    c = open(f, 'r', encoding='utf-8').read()
    
    # Check if already fixed
    if 'data-version="{{ c.scrub_version' in c:
        print(f"{f}: Already has data-version, skipping")
        return True
    
    # Add data-version attribute
    old = '''data-original-notes="{{ c.scrub_notes|default:'' }}">'''
    new = '''data-original-notes="{{ c.scrub_notes|default:'' }}" data-version="{{ c.scrub_version|default:1 }}">'''
    
    if old not in c:
        print(f"ERROR: Could not find target string in {f}")
        return False
    
    c = c.replace(old, new)
    open(f, 'w', encoding='utf-8').write(c)
    print(f"Fixed {f}")
    return True

def fix_investment():
    f = 'tcm_app/templates/tcm_app/investment.html'
    if not os.path.exists(f):
        print(f"ERROR: {f} not found")
        return False
    
    c = open(f, 'r', encoding='utf-8').read()
    
    # Check if already fixed
    if 'data-container-key="{{ c.resource_key }}" data-version' in c:
        print(f"{f}: Already has data attributes, skipping")
        return True
    
    # Add data attributes to tr inside for loop
    pattern = r'(\{% for c in containers %\}\s*\n\s*)<tr>'
    replacement = r'\1<tr data-container-key="{{ c.resource_key }}" data-version="{{ c.invest_version|default:1 }}">'
    
    new_c, count = re.subn(pattern, replacement, c)
    if count == 0:
        print(f"ERROR: Could not find target pattern in {f}")
        return False
    
    open(f, 'w', encoding='utf-8').write(new_c)
    print(f"Fixed {f}")
    return True

if __name__ == '__main__':
    print("Fixing template files...")
    s1 = fix_scrubbing()
    s2 = fix_investment()
    
    if s1 and s2:
        print("\nAll fixes applied! Now run:")
        print("  pytest tests/test_template_compilation.py -q")
    else:
        print("\nSome fixes failed. Check errors above.")
