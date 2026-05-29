# Weekly Rotation Specification

## Purpose

Balance AM/PM assignments across weeks so no employee accumulates one shift type unfairly. Rotation respects jefe-de-pista and alternancia-de-mujeres configuration.

## Requirements

### Requirement: AM/PM Inter-Week Balance

The solver MUST track per-employee AM/PM counts across the schedule window and SHOULD minimize imbalance. The balance objective weight SHALL be lower than coverage but higher than consistency and preference penalties.

#### Scenario: Fair alternation after a morning-heavy week

- GIVEN employee "Carlos" worked 5 mañanas and 0 tardes in week 1
- WHEN the solver runs for week 2
- THEN Carlos SHOULD be assigned tarde for at least 3 days
- AND the |AM − PM| delta across both weeks MUST NOT exceed 2

#### Scenario: Jefe de pista overrides rotation balance

- GIVEN "Ana" is configured as jefa de pista requiring fixed mañana every day
- WHEN the solver runs
- THEN the AM/PM balance objective MUST defer to her jefe-de-pista config
- AND Ana MAY show an unbalanced split without penalty

#### Scenario: Balance tracking across weeks

- GIVEN coverage forced an employee into an unbalanced AM/PM split in the current week
- WHEN the solver completes
- THEN the imbalance delta MUST be persisted into rotation history
- AND the next week's solver MUST use that delta to correct the imbalance
