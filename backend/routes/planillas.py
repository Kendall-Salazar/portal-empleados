"""API router for planillas and export endpoints."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import json
import sys
import os

# Import from main module's context
try:
    from main import (
        plan_db,
        load_db,
        _build_validation_rules_impl,
        _normalize_special_days,
    )
except ImportError:
    # Fallback
    _backend_dir = os.path.dirname(os.path.abspath(__file__))
    _root_dir = os.path.abspath(os.path.join(_backend_dir, ".."))
    _planillas_dir = os.path.join(_root_dir, "planillas")
    if os.path.exists(_planillas_dir) and _planillas_dir not in sys.path:
        sys.path.insert(0, _planillas_dir)
    import database as plan_db
    
    def _normalize_special_days(special_days):
        return special_days if isinstance(special_days, dict) else {}
    
    def load_db():
        return {"employees": [], "config": {}, "history_log": [], "last_result": {}}
    
    def _build_validation_rules_impl(special_days=None):
        return {"shift_options": [], "bounds": {}}

router = APIRouter(prefix="/api", tags=["planillas"])


# Models
class ValidationRulesRequest(BaseModel):
    special_days: Dict[str, str] = Field(default_factory=dict)


# Endpoints
@router.get("/validation_rules")
def get_validation_rules():
    """Get validation rules for the scheduler."""
    return _build_validation_rules_impl({})


@router.post("/validation_rules")
def post_validation_rules(request: ValidationRulesRequest):
    """Get validation rules with custom special days."""
    return _build_validation_rules_impl(request.special_days)


# Planilla endpoints - these would need the full planilla module
# For now, we'll create placeholder endpoints that can be expanded

@router.get("/planillas")
def get_planillas():
    """Get list of planillas."""
    # Placeholder - would integrate with planillas module
    return {"status": "Not implemented", "message": "Use planillas app directly"}


@router.get("/planillas/{id}")
def get_planilla(id: int):
    """Get a specific planilla."""
    # Placeholder
    raise HTTPException(status_code=404, detail="Not implemented")
