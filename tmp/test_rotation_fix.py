import sys
sys.path.insert(0, 'backend')
from scheduler_engine import _count_streak, _fixed_dominant_token, ROTATION_HISTORY_WINDOW

# 1. Verify constant
assert ROTATION_HISTORY_WINDOW == 6, f'Expected 6, got {ROTATION_HISTORY_WINDOW}'
print(f'ROTATION_HISTORY_WINDOW = {ROTATION_HISTORY_WINDOW}: OK')

# 2. Test _fixed_dominant_token
emp_no_fixed = {'fixed_shifts': {}}
assert _fixed_dominant_token(emp_no_fixed) is None

emp_pm = {'fixed_shifts': {'Lun': 'T11_12-20', 'Mar': 'T8_13-20', 'Mie': 'T3_07-15'}}
# 2 PM, 1 AM -> PM dominant
assert _fixed_dominant_token(emp_pm) == 'PM', f"Expected PM got {_fixed_dominant_token(emp_pm)}"

emp_am = {'fixed_shifts': {'Lun': 'T3_07-15', 'Mar': 'T2_06-14'}}
# 2 AM -> AM dominant
assert _fixed_dominant_token(emp_am) == 'AM', f"Expected AM got {_fixed_dominant_token(emp_am)}"

emp_tie = {'fixed_shifts': {'Lun': 'T3_07-15', 'Mar': 'T11_12-20'}}
# 1 AM, 1 PM -> None (empate)
assert _fixed_dominant_token(emp_tie) is None

emp_off = {'fixed_shifts': {'Lun': 'OFF', 'Mar': 'VAC'}}
# All non-working -> None
assert _fixed_dominant_token(emp_off) is None

print('_fixed_dominant_token: OK')

# 3. Test that _count_streak still works
assert _count_streak(['PM', 'PM', 'PM', 'PM', 'PM', 'PM']) == 6
assert _count_streak(['AM', 'PM', 'PM', 'PM']) == 3
print('_count_streak with 6-week scenarios: OK')

print('ALL TESTS PASSED')
