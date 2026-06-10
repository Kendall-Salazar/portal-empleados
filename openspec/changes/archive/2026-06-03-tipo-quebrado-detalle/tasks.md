# Tasks: tipo-quebrado-detalle

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~100–130 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

## Phase 1: Foundation — DB + Models

- [x] **1.1** `planillas/database.py`: Agregar `_ensure_column("horario_empleados", "quebrado_preferido", "TEXT DEFAULT 'auto'")` cerca de L326 (junto a las otras migraciones de `horario_empleados`)
- [x] **1.2** `backend/routes/shared_models.py`: Agregar `quebrado_preferido: str = "auto"` a `Employee` (L22) y `quebrado_preferido: Optional[str] = None` a `GeneratorParamFlags` (L193)

## Phase 2: Core Backend — Propagación

- [x] **2.1** `planillas/database.py` `update_empleado`: Agregar kwarg `quebrado_preferido=None` (L579) + UPDATE block (después de L658, mismo patrón que `forced_quebrado_partial`)
- [x] **2.2** `planillas/database.py` `resolve_prefs_for_solver`: Agregar `"quebrado_preferido": str(emp_row.get("quebrado_preferido", "auto"))` en ambos return dicts (L870-892)
- [x] **2.3** `planillas/database.py` `get_generator_employee_params`: Agregar `"quebrado_preferido": str(rp.get("quebrado_preferido", "auto"))` en flags dict (L1013-1020)
- [x] **2.4** `planillas/database.py` `apply_generator_employee_params_batch`: Agregar mapeo `flags.get("quebrado_preferido")` → `kwargs["quebrado_preferido"]` (después de L1092)
- [x] **2.5** `backend/routes/helpers.py` `load_db`: Leer `r["quebrado_preferido"]` con fallback `"auto"` en el dict de employee (L420, mismo patrón que `forced_quebrado_partial` en L420)
- [x] **2.6** `backend/routes/helpers.py` `save_db`: Incluir `forced_quebrado_partial` (bugfix — falta en UPDATE e INSERT) + `quebrado_preferido` en ambas queries (L509-543)
- [x] **2.7** `backend/routes/empleados.py`: Pasar `quebrado_preferido=e.quebrado_preferido` a `update_empleado` en `update_employees` (L67-80) y `update_single_employee` (L118-131)
- [x] **2.8** `backend/routes/horarios.py`: Agregar `"forced_quebrado_partial"` (bugfix) + `"quebrado_preferido"` en los 3 builders de `employees_data` (L41-53, L593-605, L813-825)

## Phase 3: Engine — Constraints + Penalties

- [x] **3.1** `backend/scheduler_engine.py`: Reemplazar lista fija de Q shifts en L2449 por lógica dinámica: definir `ALL_Q_SHIFTS`, leer `quebrado_preferido`, si es específico permitir solo ese Q; si es `auto` permitir todos
- [x] **3.2** `backend/scheduler_engine.py`: Modificar bloque de penalizaciones (L3094-3108): cuando `fq_total=true` y `quebrado_preferido` es específico, penalizar solo los Q NO preferidos (penalty cero para el preferido)

## Phase 4: Frontend — UI Selector

- [x] **4.1** `frontend/generator_params_panel.js` `rowFromApi`: Verificar que `quebrado_preferido` se propaga desde `entry.flags` (ya spreads en L58 — confirmar que el API devuelve el campo)
- [x] **4.2** `frontend/generator_params_panel.js` `_renderGenPanelDetail`: Insertar `<select>` con opciones Q1/Q2/Q3/Auto antes de "Turnos fijos" (L219), visible solo si `row.flags.forced_quebrado`. Labels humanizados ("5am-11am + 5pm-8pm"). Event listener actualiza `row.flags.quebrado_preferido`
- [x] **4.3** `frontend/generator_params_panel.js` `genPanelBatchForcedQuebrado`: Resetear `quebrado_preferido = "auto"` al aplicar batch (L361)
- [x] **4.4** `frontend/generator_params_panel.js` `_genPanelSyncDomFromState`: Agregar `"quebrado_preferido"` a `FLAG_KEYS` L5 si se renderiza como toggle (no — solo en detalle, mantener sin cambio)

## Pre-apply checklist

- [ ] `shared_models.py` tiene `quebrado_preferido` en ambos `Employee` y `GeneratorParamFlags`
- [ ] `database.py` migración lista (columna + default)
- [ ] `helpers.py` bugfix `forced_quebrado_partial` en `save_db` cubierto
- [ ] Tests existentes pasan antes de tocar código
