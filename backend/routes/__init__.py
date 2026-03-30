"""API routers for Chronos."""
from .empleados import router as empleados_router
from .horarios import router as horarios_router
from .planillas import router as planillas_router
from .config import router as config_router

__all__ = [
    "empleados_router",
    "horarios_router",
    "planillas_router",
    "config_router",
]
