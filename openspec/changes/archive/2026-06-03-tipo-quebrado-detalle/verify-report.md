## Verify Report: tipo-quebrado-detalle

### Resumen
- **Estado**: FAIL
- **Requisitos verificados**: 7/8 PASS, 1 FAIL
- **Escenarios probados**: 13/14 PASS, 1 FAIL
- **Issues**: 1 CRITICAL, 0 WARNING

---

### Verificación por Requisito

#### R1: Preferencia de tipo de quebrado por empleado
- [x] DB columna `quebrado_preferido TEXT DEFAULT 'auto'` existe  
  → `planillas/database.py:329`: `_ensure_column("horario_empleados", "quebrado_preferido", "TEXT DEFAULT 'auto'")`
- [x] `_ensure_column` en init_db  
  → `database.py:329` dentro de `init_db()`
- [x] `get_empleados` incluye columna  
  → `database.py:459`: `COALESCE(h.quebrado_preferido, 'auto') as quebrado_preferido`
- [x] `update_empleado` acepta y persiste  
  → `database.py:589` (kwarg) y `database.py:653-654` (UPDATE block)
- **STATUS**: PASS

#### R2: Propagación en endpoints del solver
- [x] `horarios.py solve_schedule` pasa `quebrado_preferido`  
  → `horarios.py:49`: `"quebrado_preferido": rp["quebrado_preferido"]`
- [x] `horarios.py solve_partial_schedule` lo pasa  
  → `horarios.py:825`: `"quebrado_preferido": rp["quebrado_preferido"]`
- [x] Segundo builder (horarios_generados) lo pasa  
  → `horarios.py:603`: `"quebrado_preferido": str(e.get("quebrado_preferido", "auto"))`
- [x] `load_db` lo lee  
  → `helpers.py:421`: `"quebrado_preferido": str(r["quebrado_preferido"]) if ... else "auto"`
- **STATUS**: PASS

#### R3: Restricción en engine
- [x] Si `quebrado_preferido='auto'`: todos Q permitidos  
  → `scheduler_engine.py:2450-2451`: `allowed_q = ALL_Q_SHIFTS`
- [x] Si `quebrado_preferido='Q1_05-11+17-20'`: solo Q1  
  → `scheduler_engine.py:2452-2453`: `allowed_q = [qpref]`
- [x] Si `quebrado_preferido='Q2_07-11+17-20'`: solo Q2  
  → idem
- [x] Si `quebrado_preferido='Q3_05-11+17-22'`: solo Q3  
  → idem
- **STATUS**: PASS

#### R4: Penalizaciones
- [x] `fq_total` + preferencia específica: penalización cero para preferido  
  → `scheduler_engine.py:3110-3111`: `if qpref != 'auto' and qs == qpref: pass`
- [ ] `fq_total` + `auto`: penalización cero para todos Q (status quo)  
  → **FAIL**. `scheduler_engine.py:3107-3114`: cuando `qpref == 'auto'`, el bucle entra al `else` y aplica penalización `q1_penalty` / `q2_penalty` a **todos** los Q shifts. El comportamiento anterior era `pass` (sin penalty) para todos los Q cuando `fq_total=true`.
- **STATUS**: FAIL

#### R5: API del generador
- [x] `GET /api/generator/employee-params` incluye `quebrado_preferido` en flags  
  → `database.py:1026`: `"quebrado_preferido": str(rp.get("quebrado_preferido", "auto"))`
- [x] `PUT /api/generator/employee-params` procesa `quebrado_preferido`  
  → `database.py:1103-1104`: mapea `flags["quebrado_preferido"]` → `kwargs`
- **STATUS**: PASS

#### R6: Modelos Pydantic
- [x] `Employee.quebrado_preferido: str = "auto"`  
  → `shared_models.py:17`
- [x] `GeneratorParamFlags.quebrado_preferido: Optional[str]`  
  → `shared_models.py:191`
- **STATUS**: PASS

#### R7: Bugfix forced_quebrado_partial
- [x] `helpers.py save_db` incluye `forced_quebrado_partial`  
  → `helpers.py:513` (UPDATE cols), `:522` (UPDATE values), `:535` (INSERT cols), `:544` (INSERT values)
- [x] `horarios.py solve_schedule` lo pasa  
  → `horarios.py:48`
- [x] `horarios.py solve_partial_schedule` lo pasa  
  → `horarios.py:824`
- [x] Segundo builder lo pasa  
  → `horarios.py:602`
- **STATUS**: PASS

#### R8: Frontend UI
- [x] Selector visible solo si `forced_quebrado` activo  
  → `generator_params_panel.js:222`: `if (row.flags.forced_quebrado) { ... }`
- [x] Opciones con labels humanizados  
  → `generator_params_panel.js:224-229`: labels correctos ("5am-11am + 5pm-8pm", etc.)
- [x] Al cambiar, actualiza `row.flags.quebrado_preferido`  
  → `generator_params_panel.js:299-307`: event listener actualiza `r.flags.quebrado_preferido = qSel.value`
- [x] `genPanelBatchForcedQuebrado` resetea a `"auto"`  
  → `generator_params_panel.js:392`: `genPanelRows[id].flags.quebrado_preferido = "auto"`
- **STATUS**: PASS

---

### Issues Encontrados

#### CRITICAL — Penalización de Q shifts cuando `quebrado_preferido='auto'`
- **Archivo**: `backend/scheduler_engine.py`, líneas ~3107–3114
- **Problema**: Cuando un empleado tiene `forced_quebrado=true` y `quebrado_preferido='auto'`, el engine aplica penalizaciones `q1_penalty` / `q2_penalty` a todos los Q shifts. La spec (escenario de R4) exige que el comportamiento sea idéntico al anterior: **sin penalización** para ningún Q shift cuando `fq_total` está activo y `quebrado_preferido='auto'`.
- **Evidencia del diff**: Antes del cambio el bloque era simplemente `pass` bajo `if fq_total:`. El nuevo código agrega:
  ```python
  for qs in ALL_Q_SHIFTS_PEN:
      if qpref != 'auto' and qs == qpref:
          pass
      else:
          p = q1_penalty if qs in ("Q1_05-11+17-20", "Q3_05-11+17-22") else q2_penalty
          penalties.append(p * x[(e, d, qs)])
  ```
  Cuando `qpref == 'auto'`, la condición `qpref != 'auto'` es falsa, por lo que **todos** los Q entran al `else` y reciben penalización.
- **Impacto**: Todos los empleados existentes migrados con valor `'auto'` (default) y `forced_quebrado=true` recibirán penalizaciones en sus turnos quebrados, potencialmente rompiendo la generación de horarios o cambiando drásticamente la asignación respecto al comportamiento previo.
- **Fix sugerido**:
  ```python
  if fq_total:
      if qpref != 'auto':
          for qs in ALL_Q_SHIFTS_PEN:
              if qs != qpref:
                  p = q1_penalty if qs in ("Q1_05-11+17-20", "Q3_05-11+17-22") else q2_penalty
                  penalties.append(p * x[(e, d, qs)])
  ```

---

### Veredicto Final
**FAIL — Must fix before archive**

El cambio está casi completo y correcto en DB, modelos, propagación, constraint dura, frontend y bugfix de `forced_quebrado_partial`. Sin embargo, la penalización en el engine cuando `quebrado_preferido='auto'` rompe el status quo para todos los empleados con `forced_quebrado=true` migrados. Este es un breaking change en el solver que debe corregirse antes de archivar el change.
