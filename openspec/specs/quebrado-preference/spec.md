# Spec: quebrado-preference

## Purpose

Permitir elegir el tipo de quebrado específico (Q1, Q2, Q3 o automático) por empleado cuando
`forced_quebrado` está activo, desde el panel de parámetros del generador.
Corregir bug donde `forced_quebrado_partial` nunca se propaga al solver en 3 endpoints.

---

## Requirements

### Requirement: Preferencia de tipo de quebrado por empleado

El sistema MUST permitir asignar un tipo de quebrado preferido (`Q1`, `Q2`, `Q3` o `auto`)
a cada empleado, visible y editable desde el detalle del panel de parámetros del generador
cuando `forced_quebrado` está activo.

#### Scenario: Empleado con forced_quebrado=true y quebrado_preferido='auto'

- GIVEN un empleado con `forced_quebrado=true` y `quebrado_preferido='auto'`
- WHEN el solver genera el horario
- THEN el empleado PUEDE recibir cualquiera de los tres tipos de quebrado (Q1, Q2, Q3)
- AND el comportamiento es idéntico al actual (sin restricción adicional)

#### Scenario: Empleado con forced_quebrado=true y quebrado_preferido='Q2'

- GIVEN un empleado con `forced_quebrado=true` y `quebrado_preferido='Q2_07-11+17-20'`
- WHEN el solver genera el horario
- THEN el empleado SOLO recibe turnos del tipo Q2
- AND Q1 y Q3 son forzados a 0 para este empleado en todos los días

#### Scenario: Empleado con forced_quebrado=false

- GIVEN un empleado con `forced_quebrado=false` y cualquier valor de `quebrado_preferido`
- WHEN el solver genera el horario
- THEN el campo `quebrado_preferido` es ignorado
- AND el empleado sigue las reglas normales de asignación

#### Scenario: Selector visible solo cuando forced_quebrado=true

- GIVEN el detalle del panel de parámetros del generador está abierto
- WHEN `forced_quebrado=false` para el empleado seleccionado
- THEN el selector de tipo de quebrado NO se muestra
- WHEN `forced_quebrado=true`
- THEN el selector se muestra con opciones: Automático, 5am-11am + 5pm-8pm, 7am-11am + 5pm-8pm, 5am-11am + 5pm-10pm

#### Scenario: Migración de empleados existentes

- GIVEN la columna `quebrado_preferido` no existe en `horario_empleados`
- WHEN se ejecuta `_ensure_column("horario_empleados", "quebrado_preferido", "TEXT DEFAULT 'auto'")`
- THEN la columna se crea con valor por defecto `'auto'`
- AND los empleados existentes con `forced_quebrado=true` mantienen el comportamiento actual (automático)

---

### Requirement: Propagación de quebrado_preferido en todos los endpoints del solver

El campo `quebrado_preferido` MUST estar presente en `employees_data` para los 3 builders
de `horarios.py` que alimentan el solver, y en `resolve_prefs_for_solver`.

#### Scenario: solve_schedule pasa quebrado_preferido

- GIVEN se llama a `GET /api/solve`
- WHEN se construye `employees_data` (línea ~41)
- THEN cada entrada incluye `"quebrado_preferido": rp["quebrado_preferido"]`

#### Scenario: segundo builder pasa quebrado_preferido

- GIVEN un endpoint que lee `horario_empleados` directo (línea ~593)
- WHEN se construye `employees_data`
- THEN cada entrada incluye `"quebrado_preferido": str(e.get("quebrado_preferido", "auto"))`

#### Scenario: solve_partial_schedule pasa quebrado_preferido

- GIVEN se llama a `POST /api/solve/partial`
- WHEN se construye `employees_data` (línea ~813)
- THEN cada entrada incluye `"quebrado_preferido": rp["quebrado_preferido"]`

---

### Requirement: Restricción dura de tipo de quebrado en el engine

El `ShiftScheduler` MUST filtrar los shifts Q permitidos según `quebrado_preferido`
en la constraint de `forced_quebrado` (línea ~2445), reemplazando la lista fija actual
por una dinámica basada en la preferencia.

#### Scenario: quebrado_preferido='auto' → todos los Q permitidos

- GIVEN `emp_data[e].get('quebrado_preferido', 'auto') == 'auto'`
- WHEN se ejecuta la constraint de forced_quebrado
- THEN los shifts permitidos son: OFF, VAC, PERM, Q1, Q2, Q3

#### Scenario: quebrado_preferido='Q1' → solo Q1 permitido

- GIVEN `emp_data[e].get('quebrado_preferido') == 'Q1_05-11+17-20'`
- WHEN se ejecuta la constraint de forced_quebrado
- THEN los shifts permitidos son: OFF, VAC, PERM, Q1_05-11+17-20

#### Scenario: quebrado_preferido='Q3' → solo Q3 permitido

- GIVEN `emp_data[e].get('quebrado_preferido') == 'Q3_05-11+17-22'`
- WHEN se ejecuta la constraint de forced_quebrado
- THEN los shifts permitidos son: OFF, VAC, PERM, Q3_05-11+17-22

---

### Requirement: Penalizaciones respetan preferencia de quebrado

Cuando hay `forced_quebrado=true` con `quebrado_preferido` específico, el sistema MUST
aplicar el mismo tratamiento de "sin penalización" que actualmente recibe `fq_total`
(línea ~3098), extendido para cubrir solo el Q type preferido.

#### Scenario: Penalización cero para Q preferido con forced_quebrado total

- GIVEN `forced_quebrado=true` y `quebrado_preferido='Q2_07-11+17-20'`
- WHEN se calculan penalizaciones de quebrados
- THEN Q2 no recibe penalización (igual que el `fq_total` actual)
- AND Q1 y Q3 reciben la penalización normal de quebrados (sin forced)

#### Scenario: Penalización parcial sin cambio

- GIVEN `forced_quebrado_partial=true` (sin forced_quebrado total)
- WHEN se calculan penalizaciones
- THEN se aplica `FQ_PARTIAL_Q_PENALTY = 200_000` a Q1, Q2, Q3
- AND el comportamiento es idéntico al actual

---

### Requirement: API del generador expone y persiste quebrado_preferido

Los endpoints `GET` y `PUT /api/generator/employee-params` MUST incluir
`quebrado_preferido` en `flags` del `GeneratorParamFlags` y mapearlo correctamente
en `apply_generator_employee_params_batch`.

#### Scenario: GET devuelve quebrado_preferido en flags

- GIVEN `get_generator_employee_params()` es llamado
- WHEN se construye el objeto `flags` para cada empleado
- THEN incluye `"quebrado_preferido": str(rp.get("quebrado_preferido", "auto"))`

#### Scenario: PUT persiste quebrado_preferido via update_empleado

- GIVEN una llamada PUT con `updates[].flags.quebrado_preferido = "Q2_07-11+17-20"`
- WHEN `apply_generator_employee_params_batch` procesa el update
- THEN llama a `update_empleado(eid, quebrado_preferido="Q2_07-11+17-20")`

#### Scenario: PUT con quebrado_preferido='auto' persiste correctamente

- GIVEN una llamada PUT con `updates[].flags.quebrado_preferido = "auto"`
- WHEN se procesa el update
- THEN `update_empleado` recibe `quebrado_preferido="auto"`

---

### Requirement: Modelos Pydantic incluyen quebrado_preferido

`Employee` y `GeneratorParamFlags` en `shared_models.py` MUST incluir el campo
`quebrado_preferido` con default `"auto"`.

#### Scenario: Employee acepta quebrado_preferido

- GIVEN un JSON con `"quebrado_preferido": "Q1_05-11+17-20"`
- WHEN se deserializa a `Employee`
- THEN `emp.quebrado_preferido == "Q1_05-11+17-20"`

#### Scenario: Employee default es 'auto'

- GIVEN un JSON sin `quebrado_preferido`
- WHEN se deserializa a `Employee`
- THEN `emp.quebrado_preferido == "auto"`

---

### Requirement: Bugfix — forced_quebrado_partial propagado al solver

El campo `forced_quebrado_partial` MUST estar presente en `employees_data` para los
3 endpoints de `horarios.py` que construyen datos para el solver.

#### Scenario: solve_schedule incluye forced_quebrado_partial

- GIVEN `rp["forced_quebrado_partial"] == True`
- WHEN se construye `employees_data` en `solve_schedule` (línea ~41)
- THEN la entrada incluye `"forced_quebrado_partial": True`

#### Scenario: builder de horarios_generados incluye forced_quebrado_partial

- GIVEN `e.get("forced_quebrado_partial", 0) == 1`
- WHEN se construye `employees_data` (línea ~593)
- THEN la entrada incluye `"forced_quebrado_partial": True`

#### Scenario: solve_partial_schedule incluye forced_quebrado_partial

- GIVEN `rp["forced_quebrado_partial"] == True`
- WHEN se construye `employees_data` en `solve_partial_schedule` (línea ~813)
- THEN la entrada incluye `"forced_quebrado_partial": True`

---

### Requirement: DB schema y migración

La tabla `horario_empleados` MUST tener la columna `quebrado_preferido TEXT DEFAULT 'auto'`
agregada mediante `_ensure_column`.

#### Scenario: Columna creada en BD existente

- GIVEN una BD donde `horario_empleados` no tiene la columna `quebrado_preferido`
- WHEN `_ensure_column("horario_empleados", "quebrado_preferido", "TEXT DEFAULT 'auto'")` se ejecuta
- THEN `ALTER TABLE horario_empleados ADD COLUMN quebrado_preferido TEXT DEFAULT 'auto'` se ejecuta
- AND todos los registros existentes tienen valor `'auto'`

#### Scenario: update_empleado acepta quebrado_preferido

- GIVEN una llamada a `update_empleado(eid, quebrado_preferido="Q3_05-11+17-22")`
- WHEN la función procesa el parámetro
- THEN ejecuta `UPDATE horario_empleados SET quebrado_preferido='Q3_05-11+17-22' WHERE nombre=?`

---

## Valores válidos de quebrado_preferido

| Valor | Label | Rangos |
|-------|-------|--------|
| `auto` | Automático | Cualquiera (Q1/Q2/Q3) |
| `Q1_05-11+17-20` | 5am-11am + 5pm-8pm | 05:00-11:00 + 17:00-20:00 |
| `Q2_07-11+17-20` | 7am-11am + 5pm-8pm | 07:00-11:00 + 17:00-20:00 |
| `Q3_05-11+17-22` | 5am-11am + 5pm-10pm | 05:00-11:00 + 17:00-22:00 |

## Archivos afectados

| Archivo | Cambio |
|---------|--------|
| `planillas/database.py` | `_ensure_column`, `update_empleado` (nuevo kwarg), `resolve_prefs_for_solver`, `get_generator_employee_params`, `apply_generator_employee_params_batch` |
| `backend/routes/shared_models.py` | `Employee.quebrado_preferido`, `GeneratorParamFlags.quebrado_preferido` |
| `backend/routes/horarios.py` | 3 builders `employees_data`: nuevo campo + bugfix `forced_quebrado_partial` |
| `backend/scheduler_engine.py` | Constraint forced_quebrado (línea ~2445): filtro dinámico. Penalizaciones (línea ~3098): sin penalty para Q preferido |
| `backend/routes/empleados.py` | `update_employees` (línea ~67) y `update_single_employee` (línea ~118): pasar `quebrado_preferido` |
| `backend/routes/helpers.py` | `load_db` (línea ~410): leer columna. `save_db` (línea ~509, ~529): escribir columna |
| `frontend/generator_params_panel.js` | `rowFromApi`, `_renderGenPanelDetail` (selector), `_genPanelSyncDomFromState`, `saveGeneratorParamsPanel` |
