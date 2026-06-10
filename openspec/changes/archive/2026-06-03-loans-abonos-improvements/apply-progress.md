# Apply Progress: loans-abonos-improvements

## Status: ALL TASKS COMPLETE (13/13)

## Phase 1: DB Layer ✅

### 1.1 update_abono_nota(abono_id, notas)
- **File**: `planillas/database.py` (after get_abonos, before delete_prestamo)
- **Implementation**: `UPDATE prestamo_abonos SET notas=? WHERE id=?`, returns True/False based on rowcount
- **Status**: ✅ Complete

### 1.2 delete_abono(abono_id)
- **File**: `planillas/database.py`
- **Implementation**: 
  - SELECT prestamo_id, tipo FROM prestamo_abonos WHERE id=?
  - If not found → raise ValueError
  - If tipo == 'planilla' → raise PermissionError
  - DELETE FROM prestamo_abonos WHERE id=?
  - Call _recalcular_prestamo_conn(conn, prestamo_id)
  - Return prestamo_id
- **Status**: ✅ Complete

## Phase 2: API Layer ✅

### 2.1 PrestamoAbono model — add fecha field
- **File**: `backend/main.py` (L1668)
- **Change**: Added `fecha: Optional[str] = None` to PrestamoAbono BaseModel
- **Status**: ✅ Complete

### 2.2 add_abono_prestamo — pass fecha
- **File**: `backend/main.py` (L1791)
- **Change**: Added `fecha=req.fecha` parameter to plan_db.add_abono() call
- **Status**: ✅ Complete

### 2.3 PATCH /api/planillas/abonos/{abono_id}
- **File**: `backend/main.py` (after add_abono_prestamo)
- **Implementation**: Receives `{ notas }`, calls plan_db.update_abono_nota(), returns `{ status: "success" }`
- **Status**: ✅ Complete

### 2.4 DELETE /api/planillas/abonos/{abono_id}
- **File**: `backend/main.py` (after PATCH endpoint)
- **Implementation**: 
  - Calls plan_db.delete_abono(abono_id)
  - Catches ValueError → 404
  - Catches PermissionError → 403
  - Returns `{ status, nuevo_saldo, estado }`
- **Status**: ✅ Complete

## Phase 3: Frontend — Modal ✅

### 3.1 Redesign HTML modal
- **File**: `frontend/index.html` (L1949)
- **Changes**:
  - Radio toggle: "Rebajado en planilla" / "Abono directo"
  - Planilla selectors: dropdown mes + dropdown semana (hidden by default)
  - Date picker for directo mode (default today)
  - Calculated fecha display for planilla mode
  - Existing monto + notas fields preserved
- **Status**: ✅ Complete

### 3.2 openAbonoExtraordinarioModal
- **File**: `frontend/planillas_ui.js`
- **Changes**:
  - Loads active months from GET /api/planillas/meses
  - Sets default date to today
  - Resets to directo mode on open
  - onAbonoExtMesChange: loads weeks into semana dropdown
  - onAbonoExtSemanaChange: calculates payment date (viernes + 7 days)
- **Status**: ✅ Complete

### 3.3 confirmAbonoExtraordinario
- **File**: `frontend/planillas_ui.js`
- **Changes**:
  - Reads tipo from radio buttons (planilla vs extraordinario)
  - For planilla: sends semana_planilla + calculated fecha
  - For directo: sends fecha from date picker
  - Body: { monto, tipo, fecha, semana_planilla, notas }
- **Status**: ✅ Complete

## Phase 4: Frontend — Historial ✅

### 4.1 verAbonosPrestamo — expandable rows
- **File**: `frontend/planillas_ui.js`
- **Changes**:
  - Replaced static table with clickable card rows
  - Each row has chevron icon that rotates on expand
  - Expanded panel shows: fecha, tipo, planilla/semana, monto, nota completa
  - Buttons: "Editar nota" + "Borrar" (only for extraordinario)
- **Status**: ✅ Complete

### 4.2 Editar nota inline
- **File**: `frontend/planillas_ui.js`
- **Functions**: editarNotaAbono(), guardarNotaAbono(), cancelarNotaAbono()
- **Flow**: Click "Editar nota" → textarea + save/cancel buttons → PATCH → restore display
- **Status**: ✅ Complete

### 4.3 Eliminar abono
- **File**: `frontend/planillas_ui.js`
- **Function**: eliminarAbonoIndividual(abonoId, prestamoId, empName)
- **Flow**: confirm() → DELETE → re-render list with updated saldo
- **Status**: ✅ Complete

### 4.4 calcularViernesSiguiente helper
- **File**: `frontend/planillas_ui.js`
- **Implementation**: Takes ISO date, finds next Friday + 7 days, returns ISO date
- **Status**: ✅ Complete

## Files Changed Summary

| File | Action | Lines Changed |
|------|--------|---------------|
| `planillas/database.py` | Modified | +38 (2 new functions) |
| `backend/main.py` | Modified | +28 (model field + 2 endpoints + modify existing) |
| `frontend/index.html` | Modified | +50 (modal redesign) |
| `frontend/planillas_ui.js` | Modified | +180 (modal logic + historial + helpers) |

## Deviations from Design
- None — implementation matches design.md strictly.

## Issues Found
- None.

## Workload / PR Boundary
- Mode: single PR
- Estimated lines: ~300 (within budget)
- All tasks complete, ready for verify phase.
