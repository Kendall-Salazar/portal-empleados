# Apply Progress: tipo-quebrado-detalle

**Change**: tipo-quebrado-detalle
**Mode**: Standard (sin strict TDD)
**Date**: 2026-06-03

## Completed Tasks

### Phase 1: Foundation
- [x] **1.1** `planillas/database.py`: Agregada migración `_ensure_column("horario_empleados", "quebrado_preferido", "TEXT DEFAULT 'auto'")` después de `forced_quebrado_partial`. También agregado `quebrado_preferido` en query `get_empleados` con `COALESCE(h.quebrado_preferido, 'auto')`.
- [x] **1.2** `backend/routes/shared_models.py`: Agregado `quebrado_preferido: str = "auto"` a `Employee` (después de `forced_quebrado_partial`). Agregado `quebrado_preferido: Optional[str] = None` a `GeneratorParamFlags`.

### Phase 2: Core Backend — Propagación
- [x] **2.1** `planillas/database.py` `update_empleado`: Agregado kwarg `quebrado_preferido=None` en firma + UPDATE block después de `forced_quebrado_partial`.
- [x] **2.2** `planillas/database.py` `resolve_prefs_for_solver`: Agregado `"quebrado_preferido": str(emp_row.get("quebrado_preferido", "auto"))` en ambos return dicts (rama plantilla + rama inline).
- [x] **2.3** `planillas/database.py` `get_generator_employee_params`: Agregado `"quebrado_preferido": str(rp.get("quebrado_preferido", "auto"))` en flags dict.
- [x] **2.4** `planillas/database.py` `apply_generator_employee_params_batch`: Agregado mapeo `flags.get("quebrado_preferido")` → `kwargs["quebrado_preferido"] = str(flags["quebrado_preferido"])`.
- [x] **2.5** `backend/routes/helpers.py` `load_db`: Agregado `"quebrado_preferido": str(r["quebrado_preferido"]) if "quebrado_preferido" in r.keys() else "auto"`.
- [x] **2.6** `backend/routes/helpers.py` `save_db`: **BUGFIX** — agregado `forced_quebrado_partial` que faltaba en UPDATE e INSERT. Agregado `quebrado_preferido` en ambas queries.
- [x] **2.7** `backend/routes/empleados.py`: Pasado `quebrado_preferido=e.quebrado_preferido` en `update_employees` (update path) y `update_single_employee`.
- [x] **2.8** `backend/routes/horarios.py`: Agregados `"forced_quebrado_partial"` (bugfix) + `"quebrado_preferido"` en los 3 builders de `employees_data` (solve_schedule, horarios_generados, solve_partial_schedule).

### Phase 3: Engine — Constraints + Penalties
- [x] **3.1** `backend/scheduler_engine.py`: Reemplazada lista fija por lógica dinámica con `ALL_Q_SHIFTS`. Si `quebrado_preferido` es específico, solo ese Q es permitido; si es `auto` o inválido, todos los Q.
- [x] **3.2** `backend/scheduler_engine.py`: Modificadas penalizaciones — cuando `fq_total=true` y `quebrado_preferido` es específico, penalty cero para ese Q; los otros Q reciben penalty normal.

### Phase 4: Frontend — UI Selector
- [x] **4.1** `frontend/generator_params_panel.js` `rowFromApi`: Verificado — ya funciona via spread `{ ...entry.flags }`.
- [x] **4.2** `frontend/generator_params_panel.js` `_renderGenPanelDetail`: Insertado `<select>` con opciones Q1/Q2/Q3/Auto antes de "Turnos fijos", visible solo si `forced_quebrado=true`. Labels humanizados. Event listener actualiza `row.flags.quebrado_preferido`.
- [x] **4.3** `frontend/generator_params_panel.js` `genPanelBatchForcedQuebrado`: Resetear `quebrado_preferido = "auto"` al aplicar batch con `value=true`.
- [x] **4.4** `frontend/generator_params_panel.js` `_genPanelSyncDomFromState`: Sin cambios — `quebrado_preferido` solo en detalle, no en toggle de matriz.

## Files Changed

| File | Action | What Was Done |
|------|--------|---------------|
| `planillas/database.py` | Modified | Migration `_ensure_column` para `quebrado_preferido`. `get_empleados` lee columna. `update_empleado` acepta kwarg. `resolve_prefs_for_solver` incluye en ambos returns. `get_generator_employee_params` incluye en flags. `apply_generator_employee_params_batch` mapea flags → kwarg. |
| `backend/routes/shared_models.py` | Modified | `Employee.quebrado_preferido: str = "auto"`. `GeneratorParamFlags.quebrado_preferido: Optional[str] = None`. |
| `backend/routes/helpers.py` | Modified | `load_db`: lee `quebrado_preferido` con fallback. `save_db`: bugfix `forced_quebrado_partial` + nuevo `quebrado_preferido` en UPDATE e INSERT. |
| `backend/routes/empleados.py` | Modified | `update_employees` y `update_single_employee`: pasan `quebrado_preferido`. |
| `backend/routes/horarios.py` | Modified | 3 builders: agregados `forced_quebrado_partial` (bugfix) + `quebrado_preferido`. |
| `backend/scheduler_engine.py` | Modified | Constraint forced_quebrado: filtro dinámico de Q shifts. Penalizaciones: sin penalty para Q preferido. |
| `frontend/generator_params_panel.js` | Modified | `_renderGenPanelDetail`: selector de tipo quebrado. `genPanelBatchForcedQuebrado`: reset a "auto". Event listener para selector. |

## Deviations from Design
None — implementation matches design.

## Issues Found
None.

## Bugfixes Applied
- `forced_quebrado_partial` was missing from `save_db()` in `helpers.py` (both UPDATE and INSERT queries). This is now fixed.
- `forced_quebrado_partial` was missing from all 3 `employees_data` builders in `horarios.py`. This is now fixed.

## Status
14/14 tasks complete. Ready for verify.
