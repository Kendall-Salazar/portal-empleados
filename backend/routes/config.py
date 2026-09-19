"""API router for configuration endpoints."""
from fastapi import APIRouter, Request

from .helpers import load_db, save_db

router = APIRouter(prefix="/api", tags=["config"])


# Endpoints
@router.get("/config")
def get_config():
    """Get current configuration.

    SQLite (save_db/load_db) es la ÚNICA fuente de verdad. Incluye refuerzos y
    max_simultaneous (columnas refuerzos_json / max_simultaneous).
    """
    db = load_db()
    return db.get("config", {})


@router.post("/config")
async def update_config(request: Request):
    """Update configuration — acepta JSON directo sin validación Pydantic."""
    db = load_db()
    db["config"] = await request.json()
    # Guardar config NO debe reescribir la tabla de empleados: quitamos la lista
    # de employees del payload para que save_db solo toque la config. Antes, este
    # round-trip desactivaba en horario_empleados a cualquier empleado que no
    # estuviera ya en activo=1, desincronizándolo de empleados.activo.
    db.pop("employees", None)
    save_db(db)
    return {"status": "Updated"}
