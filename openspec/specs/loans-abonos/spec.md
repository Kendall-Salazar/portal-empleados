# Spec: loans-abonos

## Purpose

Gestión completa de abonos a préstamos: crear con toggle planilla/fecha manual, editar notas, borrar (solo extraordinario), e historial expandible con acciones inline.

## Requirements

### R1: Crear abono con toggle planilla/fecha

El sistema MUST permitir registrar un abono eligiendo entre dos modos:
- **Planilla**: seleccionar mes + semana → fecha de pago se calcula automáticamente como el viernes siguiente al cierre de esa semana.
- **Directo**: seleccionar fecha manualmente con date picker.

El modelo `PrestamoAbono` en `backend/main.py` SHALL aceptar `fecha` opcional (`Optional[str] = None`). `planillas/database.py::add_abono()` ya recibe `fecha`; la API actual POST `/api/planillas/prestamos/{prestamo_id}/abono` se modifica para pasar `req.fecha` en lugar del fallback `datetime.now()`.

#### Scenario: Abono por planilla

- GIVEN un préstamo activo con saldo > 0
- WHEN se selecciona "Rebajado en planilla", se elige mes y semana, y se confirma con monto > 0
- THEN el abono se guarda con `tipo='planilla'`, `semana_planilla` = semana seleccionada, `fecha` = viernes siguiente al cierre
- AND el saldo del préstamo se recalcula

#### Scenario: Abono directo con fecha manual

- GIVEN un préstamo activo
- WHEN se selecciona "Abono directo", se elige fecha con date picker y se confirma con monto > 0
- THEN el abono se guarda con `tipo='extraordinario'`, `fecha` = fecha seleccionada, `semana_planilla` = null
- AND el saldo se recalcula

#### Scenario: Abono existente sin fecha de pago

- GIVEN un abono guardado sin campo `fecha` explícito (datos legacy)
- WHEN se muestra en el historial
- THEN se usa `fecha_registro` como fallback para display

### R2: Editar notas de abono

El sistema MUST proveer un endpoint PATCH `/api/planillas/abonos/{abono_id}` que acepte `{ notas: string }` y persista en `prestamo_abonos`. Solo el campo `notas` es editable; monto, tipo, y fecha son inmutables. La DB SHALL exponer `update_abono_nota(abono_id, notas)` que ejecuta `UPDATE prestamo_abonos SET notas = ? WHERE id = ?`.

#### Scenario: Editar nota de un abono

- GIVEN un abono existente con id=42
- WHEN se envía `PATCH /api/planillas/abonos/42` con `{ "notas": "Transferencia SINPE #1234" }`
- THEN la DB actualiza solo el campo `notas`
- AND el endpoint retorna `{ "status": "success" }`

#### Scenario: Nota vacía

- GIVEN un abono con nota existente
- WHEN se envía `PATCH` con `{ "notas": "" }`
- THEN la nota se borra (se guarda string vacío o null)

### R3: Borrar abono extraordinario

El sistema MUST permitir eliminar abonos de tipo `extraordinario` mediante `DELETE /api/planillas/abonos/{abono_id}`. Abonos de tipo `planilla` SHALL ser rechazados (sync los recrearía desde el Excel). La DB SHALL exponer `delete_abono(abono_id)` que ejecuta `DELETE FROM prestamo_abonos WHERE id = ?` y luego recalcula el saldo del préstamo asociado usando `_recalcular_prestamo_conn`.

#### Scenario: Borrar abono extraordinario exitoso

- GIVEN un abono con `tipo='extraordinario'`
- WHEN se envía `DELETE /api/planillas/abonos/42`
- THEN el abono se elimina de la DB
- AND el saldo del préstamo se recalcula automáticamente
- AND el endpoint retorna `{ "status": "success", "nuevo_saldo": ..., "estado": ... }`

#### Scenario: Borrar abono de planilla es rechazado

- GIVEN un abono con `tipo='planilla'`
- WHEN se envía `DELETE /api/planillas/abonos/42`
- THEN el endpoint retorna HTTP 403 con `{ "detail": "No se puede eliminar un abono de planilla" }`

### R4: Historial expandible con acciones

El sistema MUST transformar la tabla de abonos (`verAbonosPrestamo` en `frontend/planillas_ui.js`) en un historial interactivo: cada fila es clickeable y expande un panel que muestra fecha, monto, tipo, planilla/semana, y la nota completa (sin truncar). El panel expandido SHALL incluir botones: "Editar nota" (textarea inline + guardar) y "Borrar" (visible solo si `tipo='extraordinario'`, con confirmación antes de ejecutar).

#### Scenario: Expandir fila de abono

- GIVEN la vista de historial de abonos está cargada con 3 abonos
- WHEN el usuario hace click en la segunda fila
- THEN la fila se expande mostrando todos los detalles (fecha, monto, tipo, planilla, nota completa)
- AND las demás filas permanecen colapsadas

#### Scenario: Editar nota desde panel expandido

- GIVEN una fila expandida con nota actual "Pago parcial"
- WHEN el usuario edita el textarea a "Pago parcial — efectivo", hace click en "Guardar"
- THEN se llama `PATCH /api/planillas/abonos/{id}` con la nueva nota
- AND la UI se actualiza mostrando la nota editada

#### Scenario: Borrar desde panel expandido

- GIVEN una fila expandida de tipo `extraordinario`
- WHEN el usuario hace click en "Borrar", confirma el diálogo
- THEN se llama `DELETE /api/planillas/abonos/{id}`
- AND la tabla se refresca mostrando los abonos restantes con saldo actualizado
