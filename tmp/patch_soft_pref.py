"""
Patch script: replace the flat soft-preference penalty block
with a three-level family-aware hierarchy.

Run once from the project root:
    python tmp/patch_soft_pref.py
"""

import re

TARGET_FILE = "backend/scheduler_engine.py"

OLD_BLOCK = (
    "        # Apply SOFT constraints (flexible employees)\n"
    "        # Penalty per day of deviation.  In standard mode (\u226510 employees), 2M is\n"
    "        # high enough to respect preferences while still allowing coverage-driven\n"
    "        # deviations.  In short-staff mode (<10 employees), Q shifts MUST win\n"
    "        # consistently: Q reward (-800k) - 2M penalty = +1.2M net cost, which is\n"
    "        # only 800k better than the PM coverage gap (2M) \u2014 too close for the solver\n"
    "        # to commit reliably.  At 600k: Q net = -200k (reward), gap vs no-Q = 2.2M.\n"
    "        PREF_DEVIATION_PENALTY = 2000000 if standard_mode else 600000\n"
    "        for (e, d), s_code in soft_preferences.items():\n"
    "            pref_violated = model.NewBoolVar(f\"pref_violated_{e}_{d}\")\n"
    "            model.Add(x[(e, d, s_code)] == 0).OnlyEnforceIf(pref_violated)\n"
    "            model.Add(x[(e, d, s_code)] == 1).OnlyEnforceIf(pref_violated.Not())\n"
    "            penalties.append(PREF_DEVIATION_PENALTY * pref_violated)\n"
    "                \n"
)

NEW_BLOCK = (
    "        # Apply SOFT constraints (flexible employees) \u2014 Family-Aware Three-Level Hierarchy\n"
    "        # \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
    "        # When a soft preference is configured (e.g. Maikel: T1_05-13 on Lunes):\n"
    "        #\n"
    "        #   Level 1 \u2014 exact shift used         \u2192 cost 0          (ideal)\n"
    "        #   Level 2 \u2014 same AM/PM family used   \u2192 cost PREF_DEVIATION_PENALTY   (acceptable)\n"
    "        #   Level 3 \u2014 opposite family used     \u2192 cost PREF_DEVIATION_PENALTY\n"
    "        #                                          + PREF_FAMILY_PENALTY       (last resort)\n"
    "        #\n"
    "        # This ensures that when the solver can't assign T1_05-13, it tries other AM\n"
    "        # shifts (T2_06-14, T3_07-15 ...) before falling back to a PM shift.\n"
    "        # Consistency across the week is automatically handled by turno_principal (50K/day).\n"
    "        #\n"
    "        # Standard mode: 2M deviation keeps the preference strong vs. coverage needs.\n"
    "        # Short-staff:   600K so Q-shifts can still win against the soft preference.\n"
    "        PREF_DEVIATION_PENALTY = 2_000_000 if standard_mode else 600_000\n"
    "        PREF_FAMILY_PENALTY    = 400_000   # extra cost for crossing AM<->PM boundary\n"
    "\n"
    "        for (e, d), s_code in soft_preferences.items():\n"
    "            pref_family = _am_pm_token(s_code)  # \"AM\", \"PM\", or None\n"
    "\n"
    "            # Level 1: penalize when the exact preferred shift is NOT used\n"
    "            pref_violated = model.NewBoolVar(f\"pref_violated_{e}_{d}\")\n"
    "            model.Add(x[(e, d, s_code)] == 0).OnlyEnforceIf(pref_violated)\n"
    "            model.Add(x[(e, d, s_code)] == 1).OnlyEnforceIf(pref_violated.Not())\n"
    "            penalties.append(PREF_DEVIATION_PENALTY * pref_violated)\n"
    "\n"
    "            # Level 2: when deviated AND landed on the wrong AM/PM family, add extra cost\n"
    "            if pref_family:\n"
    "                for s in SHIFT_NAMES:\n"
    "                    if s == s_code or s in IGNORED_ROTATION_SHIFTS:\n"
    "                        continue\n"
    "                    s_family = _am_pm_token(s)\n"
    "                    if not s_family or s_family == pref_family:\n"
    "                        continue  # same family -- no extra cost\n"
    "                    # Wrong family: pref_violated AND x[e,d,s] == 1\n"
    "                    wrong_family_used = model.NewBoolVar(f\"wrong_fam_{e}_{d}_{s}\")\n"
    "                    model.AddBoolAnd([pref_violated, x[(e, d, s)]]).OnlyEnforceIf(wrong_family_used)\n"
    "                    model.AddBoolOr([pref_violated.Not(), x[(e, d, s)].Not()]).OnlyEnforceIf(wrong_family_used.Not())\n"
    "                    penalties.append(PREF_FAMILY_PENALTY * wrong_family_used)\n"
    "        \n"
)

# Read file
with open(TARGET_FILE, encoding="utf-8") as f:
    content = f.read()

# Try to find and replace
if OLD_BLOCK not in content:
    # Try with different line endings
    print("ERROR: Block not found. Checking alternatives...")
    # Print the actual lines 1456-1469 for inspection
    lines = content.splitlines()
    for i, line in enumerate(lines[1455:1470], start=1456):
        print(f"{i}: {repr(line)}")
    raise SystemExit(1)

new_content = content.replace(OLD_BLOCK, NEW_BLOCK, 1)

if new_content == content:
    print("ERROR: Replace had no effect")
    raise SystemExit(1)

with open(TARGET_FILE, "w", encoding="utf-8") as f:
    f.write(new_content)

print("PATCH APPLIED SUCCESSFULLY")

# Verify the new content is there
with open(TARGET_FILE, encoding="utf-8") as f:
    content_check = f.read()

assert "PREF_FAMILY_PENALTY" in content_check, "Patch verification failed"
assert "wrong_fam_" in content_check, "Patch verification failed: wrong_fam_ not found"
print("Verification: OK")
