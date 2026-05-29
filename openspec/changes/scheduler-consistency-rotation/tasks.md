# Tasks: Scheduler Consistency & Rotation

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~385 |
| Review budget | 800 lines |
| Budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-forecast |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

## Phase 1: Core Engine — Scheduler Penalties & Constraints

- [x] 1.1 `backend/scheduler_engine.py` — Raise CONSISTENCY_PENALTY from 50k to 500k (L1514)
- [x] 1.2 `backend/scheduler_engine.py` — Skip turno_principal creation when forced_libres=True (L1475-1495)
- [x] 1.3 `backend/scheduler_engine.py` — Add anti-3peat AM/PM hard constraint (after L3405)
- [x] 1.4 `backend/scheduler_engine.py` — Add Friday soft reward (-300k) for post-night-Thu OFF/PM (after L2168)

## Phase 2: Backend API — Individual History Endpoint

- [x] 2.1 `backend/routes/horarios.py` — Add `GET /api/history/individual/{name}?weeks=6` with dominant-type aggregation from last 6 ISO weeks

## Phase 3: Frontend — History View & Libres Indicator

- [x] 3.1 `frontend/app.js` — Add `renderHistoryIndividual()` modal with color-coded week×shift-type table
- [x] 3.2 `frontend/style.css` — Add `.libres-row` badge, `.hist-individual-modal`, `.cell-dominant-*` color styles
- [x] 3.3 `frontend/app.js` — Add libres badge in `renderSchedule` consuming `metadata.libres_person`

## Phase 4: Tests — Unit & Integration

- [x] 4.1 `tests/unit/test_scheduler.py` — Test 500k penalty enforces turno_principal consistency
- [ ] 4.2 `tests/unit/test_scheduler.py` — Test anti-3peat AM/PM blocks 3rd consecutive same token
- [ ] 4.3 `tests/unit/test_scheduler.py` — Test Friday soft reward prefers OFF/PM over AM after Thu night
- [x] 4.4 `tests/unit/test_routes_horarios.py` — Create; test dominant type, empty week, tie-breaking
- [x] 4.5 Verify `pytest -v --tb=short` passes all new + existing tests (44/44 passing)
