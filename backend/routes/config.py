"""API router for configuration endpoints."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

# Import from main module's context
try:
    from main import load_db, save_db
except ImportError:
    load_db = None
    save_db = None

router = APIRouter(prefix="/api", tags=["config"])


# Models
class Config(BaseModel):
    night_mode: str = "rotation"
    fixed_night_person: Optional[str] = None
    allow_long_shifts: bool = False
    use_refuerzo: bool = False
    refuerzo_type: str = "personalizado"
    refuerzo_start: str = "07:00"
    refuerzo_end: str = "12:00"
    allow_collision_quebrado: bool = False
    collision_peak_priority: str = "pm"
    use_history: bool = True
    strict_weekly_alternation: bool = False  # Alternancia semanal estricta para pares
    custom_shifts: list = []  # Turnos personalizados con prioridades [{name, start, end, priority}]
    holidays: list = []  # Días festivos [{date: "YYYY-MM-DD", name: "..."}]


# Endpoints
@router.get("/config")
def get_config():
    """Get current configuration."""
    if load_db is None:
        return {"error": "Database not initialized"}
    db = load_db()
    return db.get("config", {})


@router.post("/config")
def update_config(config: Config):
    """Update configuration."""
    if load_db is None or save_db is None:
        return {"error": "Database not initialized"}
    db = load_db()
    db["config"] = config.dict()
    save_db(db)
    return {"status": "Updated"}
