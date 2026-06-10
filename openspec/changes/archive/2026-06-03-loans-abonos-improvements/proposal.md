# Proposal: loans-abonos-improvements

## Intent

Mejorar la gestión de abonos a préstamos: permitir editar notas, borrar abonos individuales, registrar abonos con referencia a planilla o fecha manual, y explorar el historial con detalle expandido.

## Scope

### In Scope
- Editar notas de abono existente (PATCH endpoint + UI inline)
- Hard delete de abono individual (solo tipo `extraordinario`)
- Nuevo abono con toggle "rebajado en planilla" (seleccionar mes/semana → auto-fecha viernes) o fecha manual + monto + notas
- Historial de abonos clickable: expande fila con fecha, monto, planilla, nota completa
- Recalcular saldo automático tras delete/edit

### Out of Scope
- Editar monto o tipo de abono (solo notas)
- Soft delete / papelera de reciclaje
- Borrar abonos de planilla (sync los recrearía)
- Batch import/export de abonos

## Capabilities

### New Capabilities
- `loans-abonos`: CRUD de abonos (crear con toggle planilla/fecha, editar notas, hard delete), historial expandible

### Modified Capabilities
- None (sync behavior unchanged; solo extraordinario es borrable)

## Approach

**Quirúrgico** — cambios mínimos en DB/API:

1. **DB** (`planillas/database.py`): agregar `delete_abono(id)` y `update_abono_nota(id, notas)`. Reaprovechar `_recalcular_prestamo_conn`.
2. **API** (`backend/main.py`): `PATCH /api/planillas/abonos/{id}` (notas), `DELETE /api/planillas/abonos/{id}`. Modelo `PrestamoAbono` acepta `fecha` opcional.
3. **UI** (`frontend/planillas_ui.js`): `verAbonosPrestamo` → filas expandibles. Modal de nuevo abono rediseñado con toggle planilla/fecha + selector de mes/semana.
4. **HTML** (`frontend/index.html`): modal de abono ampliado con toggle, selector de planilla, campo de fecha.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `planillas/database.py` (L1717-1741) | Modified | +`delete_abono()`, +`update_abono_nota()` |
| `backend/main.py` (L1668-1797) | Modified | +PATCH/DELETE endpoints, modelo con `fecha` opcional |
| `frontend/planillas_ui.js` (L2795-3014) | Modified | Modal rediseñado, filas expandibles, edit nota inline |
| `frontend/index.html` (L1949-1991) | Modified | Modal con toggle planilla/fecha + selector semana |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Abonos existentes sin fecha de pago | High | Usar `fecha_registro` como fallback en display |
| Hard delete rompe integridad si sync lo esperaba | Low | Hard delete solo para tipo `extraordinario` |

## Rollback Plan

1. Revertir cambios en `backend/main.py` (endpoints nuevos)
2. Revertir cambios en `planillas/database.py`
3. Revertir HTML/JS a versión anterior (git checkout)
4. Abonos borrados no son recuperables (hard delete)

## Dependencies

- Ninguna externa. Dependencia interna: `_recalcular_prestamo_conn` ya existe.

## Success Criteria

- [ ] PATCH notas persiste y recalcula correctamente
- [ ] DELETE abono extraordinario lo elimina sin dejar rastro
- [ ] DELETE abono planilla es rechazado (solo extraordinario)
- [ ] Nuevo abono con planilla auto-calculó viernes siguiente al cierre
- [ ] Nuevo abono con fecha manual guarda fecha exacta
- [ ] Click en abono expande fila con todos los detalles
- [ ] Saldo se recalcula tras cada operación
