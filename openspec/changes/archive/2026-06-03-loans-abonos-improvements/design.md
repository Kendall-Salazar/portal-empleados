# Design: loans-abonos-improvements

## Decisiones

| Decisión | Elegida | Justificación |
|----------|---------|---------------|
| Hard delete scope | Solo `extraordinario` | Abonos `planilla` son recreados por sync; borrarlos causaría inconsistencia. |
| Fecha fallback en display | `fecha_registro` | Abonos legacy no tienen `fecha` explícita; `fecha_registro` es el timestamp de creación. |
| Editar solo notas | Campo `notas` inmutable en monto/tipo/fecha | Minimiza superficie de riesgo; editar monto rompería trazabilidad contable. |
| Toggle planilla/fecha en modal existente | Extender `abonoExtraordinarioModal` | Reutiliza HTML/JS existente en vez de crear nuevo modal. |
| Expansión inline en tabla | Click-to-expand (no modal separado) | Mantiene contexto visual; evita navegación innecesaria. |
| Viernes siguiente al cierre | `fecha_cierre + timedelta(days=(4 - cierre.weekday()) % 7)` | Consistente con la lógica de pago de planillas del negocio. |

## Flujo de datos

```
┌─ FRONTEND ──────────────────────────────────────────────────┐
│                                                              │
│  verAbonosPrestamo()                                         │
│  ├── GET /api/planillas/prestamos/{id}/abonos                │
│  ├── Render tabla con filas clickeables                      │
│  ├── Click → expandir panel con detalles + botones           │
│  │   ├── [Editar nota] → PATCH /api/planillas/abonos/{id}   │
│  │   │   └── on success → refresh tabla                      │
│  │   └── [Borrar] (solo extraordinario)                      │
│  │       └── confirm → DELETE /api/planillas/abonos/{id}    │
│  │           └── on success → refresh tabla                  │
│  │                                                           │
│  openAbonoExtraordinarioModal() [REDISEÑADO]                 │
│  ├── Radio: "Rebajado en planilla" / "Abono directo"        │
│  ├── Si planilla: selector mes + semana → GET /api/meses    │
│  │   └── calculaFechaViernes(mes_id, semana_id)              │
│  ├── Si directo: <input type="date">                         │
│  ├── Monto + Notas                                           │
│  └── confirm → POST /api/planillas/prestamos/{id}/abono     │
│      └── body: { monto, tipo, fecha?, semana_planilla?, notas }│
│                                                              │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌─ BACKEND (FastAPI) ──────┼───────────────────────────────────┐
│                           ▼                                   │
│  POST /api/planillas/prestamos/{id}/abono                     │
│  └── plan_db.add_abono(id, monto, tipo, semana, notas, fecha)│
│      └── INSERT prestamo_abonos + _recalcular_prestamo_conn  │
│                                                              │
│  PATCH /api/planillas/abonos/{id}       [NUEVO]              │
│  └── plan_db.update_abono_nota(id, notas)                    │
│      └── UPDATE prestamo_abonos SET notas=? WHERE id=?       │
│                                                              │
│  DELETE /api/planillas/abonos/{id}      [NUEVO]              │
│  ├── Verificar tipo ≠ 'planilla' → 403 si planilla          │
│  └── plan_db.delete_abono(id)                                │
│      ├── SELECT prestamo_id, tipo FROM prestamo_abonos       │
│      ├── DELETE FROM prestamo_abonos WHERE id=?              │
│      └── _recalcular_prestamo_conn(prestamo_id)              │
│                                                              │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌─ DATABASE ───────────────┼───────────────────────────────────┐
│                           ▼                                   │
│  planillas/database.py                                       │
│  ├── add_abono()        (existe, ya recibe fecha)            │
│  ├── get_abonos()       (existe, sin cambios)                │
│  ├── _recalcular_prestamo_conn() (existe, sin cambios)       │
│  ├── update_abono_nota(abono_id, notas)  [NUEVA]             │
│  └── delete_abono(abono_id)             [NUEVA]              │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

## Cambios por capa

### Database (`planillas/database.py` L1717-1741)

```python
def update_abono_nota(abono_id, notas):
    """Actualiza solo el campo notas de un abono."""
    conn = get_conn()
    conn.execute("UPDATE prestamo_abonos SET notas=? WHERE id=?", (notas, abono_id))
    conn.commit()
    conn.close()

def delete_abono(abono_id):
    """Elimina un abono y recalcula el saldo del préstamo asociado."""
    conn = get_conn()
    row = conn.execute(
        "SELECT prestamo_id, tipo FROM prestamo_abonos WHERE id=?", (abono_id,)
    ).fetchone()
    if not row:
        conn.close()
        raise ValueError("Abono no encontrado")
    if row["tipo"] == "planilla":
        conn.close()
        raise PermissionError("No se puede eliminar un abono de planilla")

    prestamo_id = row["prestamo_id"]
    conn.execute("DELETE FROM prestamo_abonos WHERE id=?", (abono_id,))
    _recalcular_prestamo_conn(conn, prestamo_id)
    conn.commit()
    conn.close()
    return prestamo_id
```

### Backend API (`backend/main.py` L1668-1797)

**Modelo `PrestamoAbono`** — agregar `fecha` opcional:

```python
class PrestamoAbono(BaseModel):
    monto: float
    tipo: str = "planilla"
    semana_planilla: Optional[str] = None
    notas: Optional[str] = None
    fecha: Optional[str] = None  # ← NUEVO
```

**Endpoint POST existente** (L1790) — pasar `req.fecha`:

```python
@app.post("/api/planillas/prestamos/{prestamo_id}/abono")
def add_abono_prestamo(prestamo_id: int, req: PrestamoAbono):
    abono_id = plan_db.add_abono(
        prestamo_id, req.monto, tipo=req.tipo,
        semana_planilla=req.semana_planilla, notas=req.notas,
        fecha=req.fecha  # ← NUEVO: ya no es siempre datetime.now()
    )
    prestamo = plan_db.get_prestamo(prestamo_id)
    return {"status": "success", "id": abono_id, "nuevo_saldo": prestamo["saldo"], "estado": prestamo["estado"]}
```

**Nuevos endpoints:**

```python
@app.patch("/api/planillas/abonos/{abono_id}")
def update_abono_nota(abono_id: int, body: dict):
    plan_db.update_abono_nota(abono_id, body.get("notas", ""))
    return {"status": "success"}

@app.delete("/api/planillas/abonos/{abono_id}")
def delete_abono(abono_id: int):
    try:
        prestamo_id = plan_db.delete_abono(abono_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Abono no encontrado")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    prestamo = plan_db.get_prestamo(prestamo_id)
    return {"status": "success", "nuevo_saldo": prestamo["saldo"], "estado": prestamo["estado"]}
```

### Frontend (`frontend/planillas_ui.js` + `index.html`)

**Modal rediseñado** (`openAbonoExtraordinarioModal` L2795):
- Agregar radio toggle: planilla vs directo
- Si planilla: cargar meses vía `/api/planillas/meses` → selector de mes → cargar semanas → selector de semana
- Calcular fecha viernes en frontend: `calcularViernesSiguiente(fechaCierre)`
- Si directo: `<input type="date">` nativo
- Cambiar `confirmAbonoExtraordinario` para enviar `tipo`, `fecha`, `semana_planilla` según toggle

**Historial expandible** (`verAbonosPrestamo` L2887):
- Reemplazar `<table>` estática por lista de filas clickeables
- Panel expandido: render condicional con `display: none/block`
- Botón "Editar nota": `textarea` + botón "Guardar" que llama `PATCH`
- Botón "Borrar": visible solo si `a.tipo === 'extraordinario'`, llama `DELETE` con `confirm()`

**HTML** (`index.html` L1949):
- Agregar radio buttons, selector de mes/semana, input date al modal existente

## APIs

| Método | Ruta | Body | Response | DB function |
|--------|------|------|----------|-------------|
| POST | `/api/planillas/prestamos/{id}/abono` | `{ monto, tipo, fecha?, semana_planilla?, notas }` | `{ status, id, nuevo_saldo, estado }` | `add_abono()` (modificado) |
| PATCH | `/api/planillas/abonos/{id}` | `{ notas }` | `{ status }` | `update_abono_nota()` (nueva) |
| DELETE | `/api/planillas/abonos/{id}` | — | `{ status, nuevo_saldo, estado }` | `delete_abono()` (nueva) |
| GET | `/api/planillas/prestamos/{id}/abonos` | — | `{ abonos, prestamo }` | `get_abonos()` (sin cambio) |
