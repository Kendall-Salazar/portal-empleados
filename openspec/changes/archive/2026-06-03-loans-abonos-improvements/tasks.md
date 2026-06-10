# Tasks: loans-abonos-improvements

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~160-180 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | ask-on-risk |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Low

## Phase 1: DB Layer — Nuevas funciones

- [x] **1.1** `planillas/database.py`: Agregar `update_abono_nota(abono_id, notas)` — `UPDATE prestamo_abonos SET notas=? WHERE id=?`
- [x] **1.2** `planillas/database.py`: Agregar `delete_abono(abono_id)` — validar `tipo != 'planilla'`, `DELETE` + `_recalcular_prestamo_conn`

## Phase 2: API Layer — Endpoints + modelo

- [x] **2.1** `backend/main.py`: Agregar `fecha: Optional[str] = None` al modelo `PrestamoAbono` (L1668)
- [x] **2.2** `backend/main.py`: Modificar `add_abono_prestamo` (L1791) — pasar `fecha=req.fecha` a `plan_db.add_abono()`
- [x] **2.3** `backend/main.py`: Agregar `PATCH /api/planillas/abonos/{abono_id}` — recibe `{ notas }`, llama `update_abono_nota()`
- [x] **2.4** `backend/main.py`: Agregar `DELETE /api/planillas/abonos/{abono_id}` — llama `delete_abono()`, maneja 403/404

## Phase 3: Frontend — Modal rediseñado

- [x] **3.1** `frontend/index.html` (L1949): Rediseñar modal — radio toggle planilla/directo, selector mes+semana, `<input type="date">`
- [x] **3.2** `frontend/planillas_ui.js`: Rediseñar `openAbonoExtraordinarioModal` (L2795) — toggle show/hide selectores según modo
- [x] **3.3** `frontend/planillas_ui.js`: Modificar `confirmAbonoExtraordinario` (L2839) — enviar `tipo`, `fecha`, `semana_planilla` según toggle

## Phase 4: Frontend — Historial expandible

- [x] **4.1** `frontend/planillas_ui.js`: Rediseñar `verAbonosPrestamo` (L2887) — filas clickeables que expanden panel con detalles completos
- [x] **4.2** `frontend/planillas_ui.js`: En panel expandido: botón "Editar nota" → textarea inline → `PATCH /api/planillas/abonos/{id}`
- [x] **4.3** `frontend/planillas_ui.js`: En panel expandido: botón "Borrar" (solo si `tipo === 'extraordinario'`) → `confirm()` → `DELETE` → refresh
- [x] **4.4** `frontend/planillas_ui.js`: Función helper `calcularViernesSiguiente(fechaCierre)` — viernes post-cierre semanal
