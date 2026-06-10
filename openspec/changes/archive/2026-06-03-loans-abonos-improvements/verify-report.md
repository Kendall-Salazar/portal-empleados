## Verify Report: loans-abonos-improvements

### Resumen
- Estado: PASS
- Requisitos verificados: 5/5
- Tareas completadas: 14/14

### Verificación por Requisito

#### R1: Editar notas de abono
- [x] `planillas/database.py` L1744: `update_abono_nota(abono_id, notas)` — ejecuta `UPDATE prestamo_abonos SET notas=? WHERE id=?` y devuelve `rowcount > 0`. Usa `try/finally` para cerrar conexión.
- [x] `backend/main.py` L1802: `PATCH /api/planillas/abonos/{abono_id}` — recibe `body: dict`, extrae `body.get("notas", "")`, llama `plan_db.update_abono_nota()`, retorna `{"status": "success"}`.
- [x] `frontend/planillas_ui.js` L3130-L3175: `editarNotaAbono()` reemplaza el div de nota por un `<textarea>` inline + botón Guardar. `guardarNotaAbono()` envía PATCH con `{ notas: nuevaNota || null }` y restaura el display con la nota actualizada (o "Sin nota" si está vacía).

#### R2: Borrar abono individual
- [x] `planillas/database.py` L1758: `delete_abono(abono_id)` — consulta `prestamo_id` y `tipo`; si `tipo == 'planilla'` lanza `PermissionError`; si no, ejecuta `DELETE` y recalcula saldo vía `_recalcular_prestamo_conn`. Incluye `rollback` en bloque `except`.
- [x] `backend/main.py` L1809: `DELETE /api/planillas/abonos/{abono_id}` — captura `ValueError` → HTTP 404, `PermissionError` → HTTP 403 con `detail=str(e)`. Retorna `{"status": "success", "nuevo_saldo": ..., "estado": ...}`.
- [x] `frontend/planillas_ui.js` L3190-L3208: `eliminarAbonoIndividual()` muestra `confirm()`, llama DELETE, recarga el historial con `verAbonosPrestamo()` y muestra toast con nuevo saldo.

#### R3: Nuevo abono con toggle planilla/fecha
- [x] `frontend/index.html` L1968-L1975: Radio toggle con `name="abonoExtTipo"` — "Rebajado en planilla" (`value="planilla"`) y "Abono directo" (`value="extraordinario"`).
- [x] Modo planilla: selectores `abonoExtMes` y `abonoExtSemana` (L1982-L1992). `onAbonoExtMesChange()` carga semanas vía `/api/planillas/meses`. `onAbonoExtSemanaChange()` calcula fecha de pago con `calcularViernesSiguiente(opt.dataset.viernes)`.
- [x] Modo directo: `<input type="date" id="abonoExtFecha">` (L2001).
- [x] `frontend/planillas_ui.js` L2940-L3003: `confirmAbonoExtraordinario()` lee el radio seleccionado, determina `tipo`, calcula `fecha` y `semana_planilla` según modo, y envía POST con `body: { monto, tipo, fecha, semana_planilla, notas }`.

#### R4: Historial expandible
- [x] `frontend/planillas_ui.js` L3014-L3127: `verAbonosPrestamo()` genera filas clickeables con `onclick="toggleAbonoDetalle(${a.id})"`. `toggleAbonoDetalle()` alterna `display` y rota el chevrón.
- [x] Panel expandido (L3077-L3102) renderiza: Fecha, Tipo (legible), Planilla/Semana, Monto, Nota completa.
- [x] Botón "Editar nota" presente en panel expandido (L3094), llama `editarNotaAbono()` → textarea inline → PATCH.
- [x] Botón "Borrar" condicional `${a.tipo !== 'planilla' ? ... : ''}` (L3097), visible solo para abonos extraordinarios.

#### R5: Modelo PrestamoAbono
- [x] `backend/main.py` L1668-L1673: `class PrestamoAbono` incluye `fecha: Optional[str] = None`.
- [x] `backend/main.py` L1791-L1797: `add_abono_prestamo()` pasa explícitamente `fecha=req.fecha` a `plan_db.add_abono()`.

### Escenarios de Spec Verificados

| Escenario | Estado | Evidencia |
|---|---|---|
| Abono por planilla (R1) | PASS | `confirmAbonoExtraordinario` envía `tipo='planilla'`, `semana_planilla` y `fecha` calculada. |
| Abono directo con fecha manual (R1) | PASS | `tipo='extraordinario'`, `fecha` del date picker, `semana_planilla=null`. |
| Abono legacy sin fecha (R1) | PASS | `verAbonosPrestamo` usa fallback `a.fecha || a.fecha_registro`. |
| Editar nota (R2) | PASS | PATCH endpoint + inline textarea + refresh display. |
| Nota vacía (R2) | PASS | Se envía `null` al backend; DB permite `NULL` en columna `notas`. |
| Borrar extraordinario exitoso (R3) | PASS | DELETE recalcula saldo y retorna `nuevo_saldo` / `estado`. |
| Borrar planilla rechazado (R3) | PASS | DB lanza `PermissionError`; endpoint responde HTTP 403. |
| Expandir fila (R4) | PASS | Click en fila ejecuta `toggleAbonoDetalle`. |
| Editar nota desde panel (R4) | PASS | Inline textarea + Guardar → PATCH → UI refresh. |
| Borrar desde panel (R4) | PASS | `eliminarAbonoIndividual` con `confirm()` → DELETE → refresh tabla. |

### Design Coherence

| Decisión (Design) | Implementación | Estado |
|---|---|---|
| Hard delete solo `extraordinario` | `delete_abono` valida `tipo != 'planilla'` | PASS |
| Fecha fallback `fecha_registro` | `a.fecha \|\| a.fecha_registro` en frontend | PASS |
| Editar solo notas | PATCH body solo lee `notas`; DB solo actualiza `notas` | PASS |
| Toggle en modal existente | `abonoExtraordinarioModal` rediseñado con radios | PASS |
| Expansión inline (no modal) | `toggleAbonoDetalle` en fila de lista | PASS |
| Viernes siguiente al cierre | `calcularViernesSiguiente(fechaIso)` en JS | PASS |

### Issues
Ninguno. Todos los requisitos están implementados, los endpoints responden con los códigos de estado correctos, y el frontend refleja el comportamiento descrito en las especificaciones.

### Veredicto
PASS
