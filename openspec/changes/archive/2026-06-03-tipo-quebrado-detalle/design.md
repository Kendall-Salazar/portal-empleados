# Design: tipo-quebrado-detalle

## Technical Approach

Agregar columna `quebrado_preferido TEXT DEFAULT 'auto'` en `horario_empleados`, exponerla en modelos Pydantic, propagarla en los 3 builders de `employees_data` de `horarios.py` (corrigiendo además el bug de `forced_quebrado_partial` faltante), y filtrar dinámicamente los Q shifts en la constraint `forced_quebrado` del engine según la preferencia. Frontend: selector Q1/Q2/Q3/Auto en detalle lateral, visible solo cuando `forced_quebrado=true`.

## Architecture Decisions

| Decisión | Opción Elegida | Alternativa | Justificación |
|----------|---------------|-------------|---------------|
| Storage de preferencia | `TEXT DEFAULT 'auto'` en `horario_empleados` | Columna separada o JSON en `turnos_fijos` | Es un flag de empleado, no un turno fijo. Co-localizar con `forced_quebrado` es más simple. `_ensure_column` ya existe como patrón de migración. |
| Valores de `quebrado_preferido` | `"auto"`, `"Q1_05-11+17-20"`, `"Q2_07-11+17-20"`, `"Q3_05-11+17-22"` | Enums separados (Q1/Q2/Q3/auto) + mapeo aparte | Usar el key del `SHIFTS` dict como valor elimina la necesidad de un mapping extra en el engine. El label humanizado se resuelve en el frontend. |
| Restricción en engine | Filtrar lista `allowed_q` dinámicamente en la constraint existente (línea ~2449) | Crear constraint nueva separada | La constraint ya fuerza Q shifts exclusivos. Modificar la lista blanca es el cambio mínimo y preserva la semántica de "1 OFF/VAC/PERM exacto". |
| Penalización para Q preferido | Sin penalty (igual que `fq_total` actual) para el Q type preferido; penalty normal para los otros Q types | Penalización reducida (no cero) | Cuando `forced_quebrado=true`, el empleado DEBE trabajar quebrados. Penalizar el tipo preferido contradice la intención del usuario. Cero penalty es consistente con el comportamiento actual de `fq_total`. |
| `quebrado_preferido` en `GeneratorParamFlags` | Campo `Optional[str] = None` | `Optional[Literal[...]] = None` | Mantiene flexibilidad. La validación ocurre en el engine (si el valor no es reconocido, se trata como `auto`). |
| Scope del selector | Solo en detalle lateral del generador, visible cuando `forced_quebrado=true` | También en modal de Gestión de Personal | Out of scope según proposal. Se agrega solo donde el usuario lo pidió. |

## Data Flow

```
[Frontend genPanelDetail]                        [API]                              [DB]                         [Engine]
         │                                         │                                  │                              │
         │ PUT /api/generator/employee-params      │                                  │                              │
         │ { updates: [{ employee_id,              │                                  │                              │
         │     flags: { forced_quebrado: true,      │                                  │                              │
         │              quebrado_preferido:         │                                  │                              │
         │                "Q2_07-11+17-20" } }] }   │                                  │                              │
         │────────────────────────────────────────►│                                  │                              │
         │                                         │ apply_generator_employee_params  │                              │
         │                                         │ ──► kwargs["quebrado_preferido"] │                              │
         │                                         │     = "Q2_07-11+17-20"            │                              │
         │                                         │─────────────────────────────────►│                              │
         │                                         │     update_empleado(eid,         │                              │
         │                                         │       quebrado_preferido="Q2...") │                              │
         │                                         │     ──► UPDATE horario_empleados  │                              │
         │                                         │         SET quebrado_preferido=   │                              │
         │                                         │         'Q2_07-11+17-20'          │                              │
         │                                         │                                  │                              │
         │                                         │                                  │  GET /api/solve              │
         │                                         │                                  │  resolve_prefs_for_solver()  │
         │                                         │                                  │─────────────────────────────►│
         │                                         │                                  │  employees_data incluye:     │
         │                                         │                                  │  "quebrado_preferido":       │
         │                                         │                                  │    "Q2_07-11+17-20"          │
         │                                         │                                  │                              │
         │                                         │                                  │  Constraint forced_quebrado  │
         │                                         │                                  │  allowed = ["OFF","VAC",     │
         │                                         │                                  │    "PERM",                   │
         │                                         │                                  │    "Q2_07-11+17-20"]         │
         │                                         │                                  │  Solo Q2 permitido           │
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `planillas/database.py` | Modify | Schema: `_ensure_column("horario_empleados", "quebrado_preferido", "TEXT DEFAULT 'auto'")`. `update_empleado`: nuevo kwarg `quebrado_preferido=None`. `resolve_prefs_for_solver`: incluir `quebrado_preferido` en ambos returns. `get_generator_employee_params`: incluir en `flags`. `apply_generator_employee_params_batch`: mapear `flags.quebrado_preferido` → kwarg. |
| `backend/routes/shared_models.py` | Modify | `Employee`: nuevo campo `quebrado_preferido: str = "auto"`. `GeneratorParamFlags`: nuevo campo `quebrado_preferido: Optional[str] = None`. |
| `backend/routes/helpers.py` | Modify | `load_db`: leer `r["quebrado_preferido"]` con fallback `"auto"`. `save_db`: incluir `forced_quebrado_partial` y `quebrado_preferido` en UPDATE e INSERT (bugfix + feature). |
| `backend/routes/horarios.py` | Modify | 3 builders de `employees_data`: agregar `"forced_quebrado_partial": rp["forced_quebrado_partial"]` (bugfix) + `"quebrado_preferido": rp["quebrado_preferido"]` en los 3 bloques (líneas ~41-53, ~593-605, ~813-825). |
| `backend/routes/empleados.py` | Modify | `update_employees` y `update_single_employee`: pasar `quebrado_preferido=e.quebrado_preferido` a `plan_db.update_empleado(...)`. |
| `backend/scheduler_engine.py` | Modify | Hard constraint (líneas ~2445-2451): calcular `allowed_q` dinámicamente según `quebrado_preferido`. Penalizaciones (líneas ~3098-3108): sin penalty para Q type preferido cuando `fq_total=true`. |
| `frontend/generator_params_panel.js` | Modify | `rowFromApi`: propagar `quebrado_preferido` desde `entry.flags`. `_renderGenPanelDetail`: agregar `<select>` de tipo quebrado debajo de los toggles, visible solo si `forced_quebrado=true`. `saveGeneratorParamsPanel`: incluir `quebrado_preferido` en `flags`. Batch operations: preservar/resetear `quebrado_preferido`. |

## DB Migration Code

En `planillas/database.py`, dentro de `init_db()` o al inicio del módulo:

```python
_ensure_column("horario_empleados", "quebrado_preferido", "TEXT DEFAULT 'auto'")
```

## UI Component Diagram

```
┌──────────────────────────────────────────────────────────────┐
│ Panel Parámetros Matriz (genPanelTbody)                      │
│ ┌────────────┬───────┬───────┬───────┬───────┬───────┐      │
│ │ Empleado   │ F.Lib │ F.Qbr │F.Q.Par│No Desc│Strict │ ...  │
│ │ Ana ✅     │  ☐   │  ☑   │  ☐   │  ☐   │  ☐   │      │
│ │ Juan       │  ☐   │  ☐   │  ☐   │  ☐   │  ☐   │      │
│ └────────────┴───────┴───────┴───────┴───────┴───────┘      │
│                                                              │
│ ┌──────────────────────┐  ┌─────────────────────────────┐    │
│ │ [Guardar todo]       │  │ Detalle Lateral (Ana)       │    │
│ │ [Sincronizar RRHH]   │  │                             │    │
│ │ [Q Total a todos]    │  │ Turnos fijos (semana tipo)  │    │
│ │ [Q Parcial a todos]  │  │ Vie: [AUTO ▾]               │    │
│ └──────────────────────┘  │ Sáb: [T1_05-13 ▾]           │    │
│                            │ ...                         │    │
│                            │                             │    │
│                            │ Tipo de Quebrado (Ana):     │    │
│                            │ ┌───────────────────────┐   │    │
│                            │ │ Automático       ▾   │   │    │
│                            │ │ 5am-11am + 5pm-8pm │   │    │
│                            │ │ 7am-11am + 5pm-8pm │   │    │
│                            │ │ 5am-11am + 5pm-10pm│   │    │
│                            │ └───────────────────────┘   │    │
│                            │ (visible solo si F.Qbr ✓)   │    │
│                            └─────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

## Save Sequence

```
1. Usuario activa forced_quebrado en matriz → _genPanelSyncDomFromState()
2. Detalle muestra selector <select id="genPanelQPref_...">
3. Usuario elige "7am-11am + 5pm-8pm" (Q2_07-11+17-20)
4. Usuario hace click en "Guardar todo" → saveGeneratorParamsPanel()
5. Payload:
   PUT /api/generator/employee-params
   {
     updates: [{
       employee_id: 42,
       flags: {
         forced_quebrado: true,
         forced_quebrado_partial: false,
         quebrado_preferido: "Q2_07-11+17-20",
         ...
       },
       shift_preferences: { ... }
     }]
   }
6. apply_generator_employee_params_batch:
   flags.quebrado_preferido → kwargs["quebrado_preferido"] = "Q2_07-11+17-20"
7. update_empleado(eid, quebrado_preferido="Q2_07-11+17-20", ...)
   → UPDATE horario_empleados SET quebrado_preferido='Q2_07-11+17-20' WHERE nombre=?
8. En próximo GET /api/solve → resolve_prefs_for_solver() → employees_data
   incluye "quebrado_preferido": "Q2_07-11+17-20"
9. Engine constraint dinámica: solo Q2_07-11+17-20 permitido
```

## Engine Constraint Specification

Reemplazar la lista fija en línea ~2449 por lógica dinámica:

```python
# ── CONSTRAINT: Forced Quebrado (Hard) ──
ALL_Q_SHIFTS = ["Q1_05-11+17-20", "Q2_07-11+17-20", "Q3_05-11+17-22"]
for e in self.employees:
    if self.emp_data[e].get('forced_quebrado', False):
        qpref = self.emp_data[e].get('quebrado_preferido', 'auto')
        if qpref == 'auto' or qpref not in ALL_Q_SHIFTS:
            allowed_q = ALL_Q_SHIFTS  # comportamiento actual
        else:
            allowed_q = [qpref]       # solo el Q preferido
        # allowed_shifts = fixed non-Q + dynamic Q list
        for d in DAYS:
            for s in SHIFT_NAMES:
                if s not in ["OFF", "VAC", "PERM"] + allowed_q:
                    model.Add(x[(e, d, s)] == 0)
        model.Add(sum(x[(e, d, "OFF")] + x[(e, d, "VAC")] + x[(e, d, "PERM")] for d in DAYS) == 1)
```

## Engine Penalty Specification

Modificar el bloque ~3098 para diferenciar Q preferido de otros Q:

```python
for e in self.employees:
    fq_total = self.emp_data[e].get('forced_quebrado', False)
    fq_partial = self.emp_data[e].get('forced_quebrado_partial', False)
    qpref = self.emp_data[e].get('quebrado_preferido', 'auto')
    for d in DAYS:
        if fq_total:
            # Sin penalty para Q preferido; penalty normal para los otros Q
            for qs in ALL_Q_SHIFTS:
                if qpref != 'auto' and qs == qpref:
                    pass  # sin penalty — es el tipo elegido
                else:
                    # Penalty igual al caso sin forced_quebrado
                    p = q1_penalty if qs in ("Q1_05-11+17-20", "Q3_05-11+17-22") else q2_penalty
                    penalties.append(p * x[(e, d, qs)])
        elif fq_partial:
            p = FQ_PARTIAL_Q_PENALTY if standard_mode else q1_penalty
            penalties.append(p * x[(e, d, "Q1_05-11+17-20")])
            penalties.append(p * x[(e, d, "Q2_07-11+17-20")])
            penalties.append(p * x[(e, d, "Q3_05-11+17-22")])
        else:
            penalties.append(q1_penalty * x[(e, d, "Q1_05-11+17-20")])
            penalties.append(q2_penalty * x[(e, d, "Q2_07-11+17-20")])
            penalties.append(q1_penalty * x[(e, d, "Q3_05-11+17-22")])
```

## Frontend Selector Spec

En `_renderGenPanelDetail()`, insertar debajo del bloque de toggles (antes de "Turnos fijos"):

```javascript
// ── Selector tipo de quebrado (visible solo si forced_quebrado=true) ──
if (row.flags.forced_quebrado) {
    const qpref_val = row.flags.quebrado_preferido || "auto";
    const q_opts = [
        { v: "auto",               l: "Automático" },
        { v: "Q1_05-11+17-20",    l: "5am-11am + 5pm-8pm" },
        { v: "Q2_07-11+17-20",    l: "7am-11am + 5pm-8pm" },
        { v: "Q3_05-11+17-22",    l: "5am-11am + 5pm-10pm" },
    ];
    parts.push(`<p style="...">Tipo de Quebrado</p>`);
    parts.push(`<select id="genPanelQPref_${row.employee_id}" ...>`);
    q_opts.forEach(o => {
        parts.push(`<option value="${o.v}"${qpref_val===o.v?' selected':''}>${o.l}</option>`);
    });
    parts.push(`</select>`);
    // event listener: row.flags.quebrado_preferido = this.value
}
```

En `rowFromApi()` agregar: `quebrado_preferido: entry.flags.quebrado_preferido || "auto"`.

En `saveGeneratorParamsPanel()`: `flags.quebrado_preferido = r.flags.quebrado_preferido` (ya incluido porque usa `{ ...r.flags }` — spread automático).

En `genPanelBatchForcedQuebrado()`: resetear `quebrado_preferido = "auto"` al aplicar batch.

## Performance Considerations

- **Sin impacto en solver**: el cambio reemplaza una lista fija de 3 strings por una lista dinámica de 1 o 3. El número de constraints no cambia — sigue siendo `|employees| × |DAYS| × (|SHIFT_NAMES| − |allowed|)`. La penalización agrega un `if` extra en tiempo de construcción del modelo (no en tiempo de solve).
- **DB**: `_ensure_column` es O(1), se ejecuta una vez en `init_db()`. Las queries existentes no se ven afectadas porque la columna tiene default.

## Implementation Order

1. **DB migration** — `_ensure_column("horario_empleados", "quebrado_preferido", "TEXT DEFAULT 'auto'")` en `database.py`
2. **Modelos Pydantic** — `Employee.quebrado_preferido: str = "auto"` + `GeneratorParamFlags.quebrado_preferido: Optional[str] = None`
3. **database.py** — `update_empleado` nuevo kwarg, `resolve_prefs_for_solver`, `get_generator_employee_params`, `apply_generator_employee_params_batch`
4. **helpers.py** — `load_db` + `save_db` (leer/escribir columna + bugfix `forced_quebrado_partial` en save_db)
5. **empleados.py** — `update_employees` y `update_single_employee`: pasar `quebrado_preferido`
6. **horarios.py** — 3 builders: agregar `forced_quebrado_partial` (bugfix) + `quebrado_preferido`
7. **scheduler_engine.py** — constraint dinámica + penalizaciones
8. **generator_params_panel.js** — `rowFromApi`, `_renderGenPanelDetail`, batch operations

## Open Questions

- None
