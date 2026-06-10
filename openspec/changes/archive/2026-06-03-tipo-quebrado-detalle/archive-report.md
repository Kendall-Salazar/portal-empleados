## Archive Report: tipo-quebrado-detalle

### Resumen
Selector de tipo de quebrado (Q1/Q2/Q3/Auto) en panel de parámetros del generador + bugfix de `forced_quebrado_partial` no propagado al solver.

### Archivos modificados
| Archivo | Cambio |
|---------|--------|
| `planillas/database.py` | Migración columna `quebrado_preferido TEXT DEFAULT 'auto'`, `update_empleado` nuevo kwarg, `resolve_prefs_for_solver`, `get_generator_employee_params`, `apply_generator_employee_params_batch` |
| `backend/routes/shared_models.py` | `Employee.quebrado_preferido: str = "auto"`, `GeneratorParamFlags.quebrado_preferido: Optional[str]` |
| `backend/routes/helpers.py` | `load_db` leer columna, `save_db` escribir columna + bugfix `forced_quebrado_partial` en UPDATE/INSERT |
| `backend/routes/empleados.py` | Pasar `quebrado_preferido` en `update_employees` y `update_single_employee` |
| `backend/routes/horarios.py` | 3 builders de `employees_data`: agregar `forced_quebrado_partial` (bugfix) + `quebrado_preferido` |
| `backend/scheduler_engine.py` | Restricción dinámica de Q shifts según preferencia; penalización cero para Q preferido con `fq_total` |
| `frontend/generator_params_panel.js` | Selector Q1/Q2/Q3/Auto en detalle lateral con labels humanizados, visible solo si `forced_quebrado=true` |

### Bugfixes
- **forced_quebrado_partial no propagado**: Faltaba en 3 endpoints de `horarios.py` (líneas ~41, ~593, ~813) y en `save_db` de `helpers.py` (líneas ~509, ~529). Se agregó en todos.
- **Penalización con quebrado_preferido='auto'**: El código inicial penalizaba todos los Q shifts cuando `fq_total=true` y `qpref='auto'`, rompiendo el status quo. Corregido con `if qpref == 'auto': pass` (línea 3108–3110 del engine).

### Specs sincronizadas
| Domain | Acción | Detalles |
|--------|--------|----------|
| `quebrado-preference` | Creada | 8 requisitos, 14 escenarios — spec completo copiado a `openspec/specs/quebrado-preference/spec.md` |

### Contenido del archivo
- `proposal.md` ✅
- `spec.md` ✅
- `design.md` ✅
- `tasks.md` ✅ (10/10 tasks completadas)
- `verify-report.md` ✅ (7/8 PASS → fix aplicado post-reporte)
- `apply-progress.md` ✅
- `archive-report.md` ✅ (este documento)

### Source of Truth actualizado
- `openspec/specs/quebrado-preference/spec.md` — nuevo spec principal para la capability `quebrado-preference`

### Lecciones aprendidas
- Los cambios en penalizaciones del engine con `forced_quebrado` son particularmente sensibles: el caso `auto` debe preservar el comportamiento original (`pass`) y solo agregar penalty diferencial cuando hay una preferencia específica.
- El bug de `forced_quebrado_partial` (faltante en 3+ lugares por ser un campo "nuevo" agregado después de los builders originales) muestra que los campos que se agregan a `employees_data` deben auditarse en TODOS los builders, no solo en el principal.
- `_ensure_column` como patrón de migración es efectivo y seguro — columna con DEFAULT no rompe queries existentes.

### Estado
✅ Archivado — 2026-06-03
