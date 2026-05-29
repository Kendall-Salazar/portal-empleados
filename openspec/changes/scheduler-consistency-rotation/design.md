# Design: Scheduler Consistency & Rotation

## Technical Approach

Five independent changes, all within CP-SAT penalty model at `scheduler_engine.py:1514` (consistency), `:3374` (anti-3peat), `:3432` (AM/PM streak), `:2150` (night→morning block). New endpoint at `routes/horarios.py`, frontend changes in `app.js` + `style.css`.

Sequence for solve flow:
```
POST /api/solve → ShiftScheduler.solve() → CP-SAT model
  ├─ CONSISTENCY_PENALTY (now near-hard) ──→ turno_principal selection
  ├─ AM/PM streak/balance penalties ──→ turno_principal rotation
  ├─ Anti-3peat AM/PM hard constraint ──→ blocks 3rd consecutive same token
  ├─ Friday heuristic reward ──→ nudges OFF/PM after night Thu
  └─ metadata.libres_person ──→ consumed by frontend badge
```

## Architecture Decisions

| Decision | Choice | Alternative | Rationale |
|----------|--------|-------------|-----------|
| CONSISTENCY_PENALTY magnitude | 1M (20x from 50k) | 300-500k (10x) | At 50k coverage always wins. 1M competes with peak penalties (~100-500k/employee-day). Feasibility fallback: if INFEASIBLE, retry with 50k + log warning. |
| Steven exemption | Skip `turno_principal` creation when `forced_libres=True` | Keep limited turno_principal (no N_22-05) | Steven's role is to cover anyone OFF — assigning a principal shift contradicts that. Existing code already gives him reduced principal; skipping entirely is simpler and correct. |
| Anti-3peat for AM/PM | Hard constraint: `turno_principal` ≠ last 2 weeks' token when streak ≥ 3 | Higher soft penalty (cap 10M) | Soft penalties allow coverage to win. Hard constraint guarantees rotation with explicit exemptions (fixed shifts, jefe de pista, women alternation). |
| Friday heuristic | Add soft reward (-300k) for OFF/PM after ANY night Thu (not just N_22-05) | Extend hard block to all night shifts | Hard blocking all night shifts would over-constrain for non-N_22-05 night workers. Soft reward preserves feasibility. |
| Employee history endpoint | In-memory aggregation from `GET /api/history` — no new SQL | New SQLite query joining `horarios_generados` | Reuses existing cache (`historyEntriesCache` in frontend). 6-week window is bounded (~42 rows per entry). |
| Libres indicator | CSS class `.libres-row` on the schedule table `<tr>` — no new data | New API field or metadata restructure | `libres_person` already in `result.metadata` at line 3847. Frontend reads it from `currentGeneratedSchedule.metadata`. |

## Data Flow — Employee History

```
GET /api/history/individual/{name}?weeks=6
  → routes/horarios.py (NEW handler)
    → plan_db.get_conn()
      → SELECT horario FROM horarios_generados WHERE deleted=0 ORDER BY timestamp DESC LIMIT 6
        → For each row: JSON parse, extract employee's days
          → Count shift occurrences, determine dominant AM/PM/OFF/N per ISO week
            → Return [{week_label, dominant_type, days: {day: shift}},...]
  → frontend: renderHistoryIndividual(employee) modal with color-coded cells
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `backend/scheduler_engine.py` | Modify | CONSISTENCY_PENALTY 50k→1M (L1514), skip turno_principal for forced_libres (L1475-1495), anti-3peat AM/PM hard constraint (NEW after L3405), Friday soft reward (after L2168) |
| `backend/routes/horarios.py` | Modify | Add `GET /api/history/individual/{name}` — aggregates last 6 weeks per employee |
| `frontend/app.js` | Modify | `renderHistoryIndividual()` — per-employee week×type table; libres badge logic in `renderSchedule` |
| `frontend/style.css` | Modify | `.libres-row` highlight, `.hist-individual-modal` styles, `.cell-dominant-am/pm/off/n` colors |
| `tests/unit/test_scheduler.py` | Modify | Verify 1M penalty rejects deviations, anti-3peat AM/PM blocks 3rd same token, Friday reward nudges OFF/PM |
| `tests/unit/test_routes_horarios.py` | Create | Test individual history aggregation: dominant type computation, edge cases (empty history, single week) |

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | CONSISTENCY_PENALTY=1M rejects deviations | Parametrized CP-SAT: 2 employees, 6 days, verify turno_principal assigned consistently |
| Unit | Anti-3peat AM/PM blocks 3rd same token | Mock 2-week history with same token, assert solver assigns opposite |
| Unit | Friday soft reward: OFF/PM chosen over AM after night Thu | Mock history with Tue-Thu night, verify solver prefers OFF/PM on Fri |
| Unit | Individual history: dominant type = AM when 4 days AM out of 6 | Pure function test on mock horario JSON rows |
| Integration | New endpoint returns valid JSON structure | FastAPI TestClient → `GET /api/history/individual/Steven?weeks=6` |

## Migration / Rollout

No migration required. Rollback: revert `CONSISTENCY_PENALTY` to 50k, remove anti-3peat hard constraint, remove Friday reward, delete new endpoint, remove frontend modal + CSS. All changes are additive within the existing penalty model.

## Open Questions

- [ ] Should anti-3peat AM/PM exempt jefes de pista? (Proposal says yes for alternancia config — need confirmation)
- [ ] Is Steven always `forced_libres=True`, or should exemption be name-based (`"Steven"` string match)?
