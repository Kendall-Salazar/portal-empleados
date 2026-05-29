# Libres Visual Indicator Specification

## Purpose

Distinctive visual marker in the schedule grid identifying which employee is the "persona de libres" for the current week.

## Requirements

### Requirement: Persona-de-Libres Visual Badge

The schedule grid MUST render a visual indicator (badge, border, or icon) on the row or cell of the employee designated as persona de libres for the displayed week. The indicator MUST be perceivable without interaction.

#### Scenario: Indicator visible at a glance

- GIVEN "Steven" is the persona de libres for the current week
- WHEN the schedule grid renders
- THEN Steven's row or name cell MUST show a distinctive visual indicator
- AND the indicator MUST be visible without hovering or clicking

#### Scenario: No persona de libres assigned

- GIVEN no employee is designated as persona de libres this week
- WHEN the schedule grid renders
- THEN no libres indicator SHALL appear
- AND the grid MUST render normally without errors

#### Scenario: Multi-week view only shows indicator in applicable week

- GIVEN the frontend displays two consecutive weeks and Steven is persona de libres only in week 1
- WHEN both weeks render
- THEN the indicator MUST appear only in week 1's grid
- AND week 2 MUST NOT show the indicator for Steven
