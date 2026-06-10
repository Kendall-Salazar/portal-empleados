# Proposal: tipo-quebrado-detalle

## Intent

Elegir QUÉ tipo de quebrado (Q1/Q2/Q3) usa un empleado con `forced_quebrado` activo, más corregir bug donde `forced_quebrado_partial` nunca se pasa al solver.

## Scope

### In Scope
- Nuevo campo `quebrado_preferido TEXT DEFAULT 'auto'` en DB + migración
- Selector Q1/Q2/Q3/Auto en detalle lateral del generador (visible cuando `forced_quebrado` activo)
- Rango horario legible ("5am-11am + 5pm-8pm") en el selector
- Restricción dura en engine filtrando Q shifts según preferencia
- Bugfix: agregar `forced_quebrado_partial` faltante en `horarios.py` (3 endpoints)

### Out of Scope
- UI de Gestión de Personal (modal empleado)
- Batch operations
- Validación `forced_quebrado=False` + `quebrado_preferido!=auto`

## Capabilities

### New Capabilities
- `quebrado-preference`: Asignar y aplicar tipo de quebrado específico (Q1/Q2/Q3/auto) por empleado en el generador

### Modified Capabilities
None — no existing specs in openspec/specs/

## Approach

1. **DB**: Columna + migración en `database.py`. Incluir en `resolve_prefs_for_solver`, `get_generator_employee_params`, `apply_generator_employee_params_batch`, `update_empleado`.
2. **Models**: `Employee.quebrado_preferido: str = "auto"`, `GeneratorParamFlags.quebrado_preferido: Optional[str] = None`.
3. **Routes**: Pasar campo en 3 builders de `employees_data` en `horarios.py` + agregar `forced_quebrado_partial`. Ídem `helpers.py` y `empleados.py`.
4. **Engine**: Filtrar Q shifts en constraint línea ~2445 según preferencia. Si `auto`, mantener 3 opciones.
5. **Frontend**: `rowFromApi` propaga campo. `_renderGenPanelDetail` muestra `<select>` Q1/Q2/Q3/Auto cuando `forced_quebrado=true`. Labels humanizados.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `planillas/database.py` | Modified | New col, migración, CRUD, generator endpoints |
| `backend/routes/shared_models.py` | Modified | Employee + GeneratorParamFlags |
| `backend/routes/horarios.py` | Modified | Bugfix + nuevo campo en 3 endpoints |
| `backend/routes/helpers.py` | Modified | load_db + save_db |
| `backend/routes/empleados.py` | Modified | Update flags |
| `backend/scheduler_engine.py` | Modified | Hard constraint filtrar Q |
| `frontend/generator_params_panel.js` | Modified | rowFromApi + detail selector |
| `frontend/index.html` | Modified | Template si markup necesario |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Infeasibility si Q restringido y poca cobertura | Med | Default "auto" = comportamiento actual intacto |
| Regresiones en endpoints sin `quebrado_preferido` | Bajo | Campo default en Pydantic + DB |

## Rollback Plan

1. Revert cambios en `scheduler_engine.py` (afecta resultados)
2. Revert cambios en `horarios.py` (bugfix reaplicable aparte)
3. Columna DB no destructiva — drop opcional con `ALTER TABLE`

## Dependencies

None

## Success Criteria

- [ ] Selector Q1/Q2/Q3/Auto aparece en detalle lateral cuando `forced_quebrado=true`
- [ ] Labels: "5am-11am + 5pm-8pm" en vez de "Q1_05-11+17-20"
- [ ] `forced_quebrado_partial` llega correctamente al engine
- [ ] Solver respeta preferencia (no asigna Q2 si se eligió Q1)
- [ ] Tests existentes pasan (pytest)
