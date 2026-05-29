"""API router for configuration endpoints."""
from fastapi import APIRouter

from .shared_models import Config
from .helpers import load_db, save_db

router = APIRouter(prefix="/api", tags=["config"])


# Endpoints
@router.get("/config")
def get_config():
    """Get current configuration."""
    db = load_db()
    return db.get("config", {})


@router.post("/config")
def update_config(config: Config):
    """Update configuration."""
    db = load_db()
    db["config"] = config.model_dump()
    save_db(db)
    return {"status": "Updated"}
