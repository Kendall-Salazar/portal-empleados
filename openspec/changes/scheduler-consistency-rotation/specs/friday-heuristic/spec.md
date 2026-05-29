# Friday Heuristic Specification

## Purpose

Apply a post-processing rule: after a Thursday night shift, block mañana on Friday and prefer OFF or tarde instead. Steven is exempt.

## Requirements

### Requirement: Post-Thursday-Night Friday Preference

If an employee worked noche on Thursday, the solver MUST NOT assign mañana on Friday for that employee. The solver SHOULD prefer OFF, then tarde, then noche as fallback.

#### Scenario: Night Thursday → blocked Friday morning

- GIVEN employee "Pedro" worked noche on Thursday
- WHEN the solver assigns Pedro's Friday shift
- THEN mañana MUST NOT be assigned
- AND OFF SHOULD be preferred; tarde SHOULD be second choice
- AND noche MAY be assigned only if OFF and tarde are both infeasible

#### Scenario: Steven exemption

- GIVEN Steven worked noche on Thursday
- WHEN Friday assignment runs
- THEN the post-night heuristic MUST NOT apply to Steven

#### Scenario: No Thursday night → no restriction

- GIVEN employee "Laura" did NOT work noche on Thursday
- WHEN Friday assignment runs
- THEN no post-night restriction applies
- AND Laura MAY receive any shift type normally
