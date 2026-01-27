import esprima

print('=' * 60)
print('JAVASCRIPT SYNTAX VALIDATION PROOF')
print('=' * 60)

# Test 1: BROKEN syntax from scrubbing.html
print()
print('TEST 1: BROKEN SYNTAX (from scrubbing.html line 139)')
print('-' * 60)
broken_js = 'const isDirty = (currStatus ! == origStatus);'
print(f'Code: {broken_js}')
try:
    esprima.parseScript(broken_js)
    print('Result: VALID (unexpected)')
except esprima.Error as e:
    print(f'Result: SYNTAX ERROR')
    print(f'Error: {e}')

# Test 2: CORRECT syntax
print()
print('TEST 2: CORRECT SYNTAX (what it should be)')
print('-' * 60)
correct_js = 'const isDirty = (currStatus !== origStatus);'
print(f'Code: {correct_js}')
try:
    esprima.parseScript(correct_js)
    print('Result: VALID (expected)')
except esprima.Error as e:
    print(f'Result: SYNTAX ERROR - {e}')

# Test 3: Another broken operator from line 157
print()
print('TEST 3: BROKEN === OPERATOR (from scrubbing.html line 157)')
print('-' * 60)
broken_js2 = "if (el.tagName == = 'INPUT') { }"
print(f'Code: {broken_js2}')
try:
    esprima.parseScript(broken_js2)
    print('Result: VALID (unexpected)')
except esprima.Error as e:
    print(f'Result: SYNTAX ERROR')
    print(f'Error: {e}')

# Test 4: Correct === operator
print()
print('TEST 4: CORRECT === OPERATOR')
print('-' * 60)
correct_js2 = "if (el.tagName === 'INPUT') { }"
print(f'Code: {correct_js2}')
try:
    esprima.parseScript(correct_js2)
    print('Result: VALID (expected)')
except esprima.Error as e:
    print(f'Result: SYNTAX ERROR - {e}')

print()
print('=' * 60)
print('CONCLUSION')
print('=' * 60)
print('The broken operators (! == and == =) cause SYNTAX ERRORS.')
print('Browsers will fail to parse the script block entirely.')
print('This is why the Save button never enables.')
