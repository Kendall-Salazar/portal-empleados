# Proposal: Scheduler Consistency & Rotation

## Intent

The solver breaks `turno_principal` consistency (soft penalty 50k) when coverage demands it, producing unfair schedules. Rotation AM/PM between weeks is inequitable because coverage always wins over fairness. No per-employee history view exists to track shift patterns.

## Scope

### In Scope
- Near-hard constraint for `turno_principal` consistency (Steven exempted)
- AM/PM inter-week rotation (respecting jefe de pista and women's alternation config)
- Friday heuristic: post-night shift → prefer OFF or afternoon
- Individual employee history: last 6 weeks, dominant shift type per week
- Visual persona-de-libres indicator in schedule view

### Out of Scope
- `fixed_night_person` logic (works correctly)
- Steven's libre role behavior (correct by design)
- Full history export / CSV download
- Multi-shift-type resolution per week beyond dominant type
- Night rotation logic changes

## Capabilities

### New Capabilities
- `scheduler-consistency`: Near-hard `turno_principal` with Steven exemption
- `rotation-fairness`: AM/PM inter-week balance with alternancia de mujeres
- `friday-heuristic`: Post-night Friday preference for OFF/afternoon
- `employee-history`: Individual 6-week history by dominant shift type
- `schedule-visual`: Persona-de-libres visual indicator

### Modified Capabilities
None — first change, no base specs exist yet.

## Approach

1. **Consistency**: Raise `CONSISTENCY_PENALTY` from 50k to 1M, add pre-solve validation that flags breakage. Add explicit Steven exemption.
2. **Rotation**: Track AM/PM history per employee. Add balance objective (not hard constraint) with weight lower than coverage but higher than consistency penalty. Respect jefe de pista and mujer alternancia config.
3. **Friday heuristic**: Add post-processing rule: if employee worked night Thu, block AM shift Fri (unless Steven). If same person repeats night Fri, allow OFF rebalance.
4. **Employee history**: New `GET /api/employee/{id}/history?weeks=6` endpoint. Determine dominant type by counting days per shift type per ISO week. Frontend renders per-employee card.
5. **Visual indicator**: New badge/border style in schedule grid for persona-de-libres that week.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `backend/scheduler_engine.py` | Modified | Penalty weights, rotation logic, Friday heuristic |
| `backend/routes/horarios.py` | Modified | New history endpoint |
| `backend/database.json` | Modified | Rotation history schema |
| `frontend/app.js` | Modified | History view, visual indicator |
| `frontend/index.html` | Modified | History UI component |
| `frontend/style.css` | Modified | Persona-de-libres badge styles |
| `tests/unit/test_scheduler.py` | Modified | New consistency/rotation tests |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Over-constraining solver (no solution) | Medium | Keep consistency as near-hard with fallback: if infeasible, revert to soft + log warning |
| History API perf on large datasets | Low | 6-week window is bounded, JSON history is small |

## Rollback Plan

Restore `CONSISTENCY_PENALTY` to 50k, revert rotation/ Friday changes in `scheduler_engine.py`, remove new endpoint and frontend components. Validated via `pytest -v --tb=short`.

## Dependencies

- None — no new external libs required

## Success Criteria

- [ ] `pytest` passes with new consistency/rotation/heuristic tests
- [ ] Employee history endpoint returns correct dominant types per week
- [ ] Solver never breaks `turno_principal` unless truly infeasible
- [ ] Friday heuristic blocks AM shifts after Thursday night
