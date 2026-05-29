# Individual History Specification

## Purpose

Per-employee view of the last 6 weeks showing the dominant shift type per ISO week (matutino/vespertino/nocturno/libre).

## Requirements

### Requirement: Employee History API

The system MUST expose `GET /api/employee/{id}/history?weeks=6` returning the dominant shift type per ISO week, with per-type counts, for the last N weeks (default 6).

#### Scenario: Clear dominant type per week

- GIVEN employee "María" worked 4 mañanas, 1 tarde, 0 noches, 0 libres in ISO week 22
- WHEN `GET /api/employee/maria/history?weeks=6` is called
- THEN week 22 MUST return `dominant_type: "matutino"`
- AND the response MUST include `counts: {matutino: 4, vespertino: 1, nocturno: 0, libre: 0}`

#### Scenario: Empty week

- GIVEN employee "Pedro" had 0 scheduled days in ISO week 21
- WHEN the history endpoint is called for Pedro
- THEN week 21 MUST return `dominant_type: "libre"` with all counts at 0

#### Scenario: Tie-breaking

- GIVEN employee worked 2 mañanas and 2 tardes in ISO week 23 (tie)
- WHEN dominant type is calculated
- THEN the tie MUST resolve to the first scheduled day's shift type within that week
