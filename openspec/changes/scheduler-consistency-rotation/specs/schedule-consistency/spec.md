# Schedule Consistency Specification

## Purpose

Enforce near-hard `turno_principal` consistency per employee so the CP-SAT solver never breaks an employee's default shift unless coverage is provably infeasible. Steven is explicitly exempted.

## Requirements

### Requirement: Turno Principal Near-Hard Enforcement

The solver MUST assign each employee their configured `turno_principal` on every scheduled day. The consistency penalty MUST dominate all soft constraints (1M weight) except coverage infeasibility. Steven MUST be exempt from this penalty entirely.

#### Scenario: Consistent assignment across full week

- GIVEN employee "María" has `turno_principal` = "mañana"
- WHEN the solver runs for a full week with feasible coverage
- THEN every scheduled day for María MUST be "mañana"
- AND no other shift type SHALL appear on her row

#### Scenario: Steven exemption

- GIVEN Steven has `turno_principal` = "noche" but his libre-person role requires variable shifts
- WHEN the solver runs
- THEN the consistency penalty MUST NOT be applied to Steven

#### Scenario: Infeasibility fallback

- GIVEN coverage constraints prevent `turno_principal` assignment for at least one employee-day
- WHEN the solver detects infeasibility during pre-solve validation
- THEN the penalty MUST fall back to soft weight (50k)
- AND the solver MUST log which employee and day forced the break
