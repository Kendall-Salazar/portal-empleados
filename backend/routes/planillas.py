"""API router for planillas and export endpoints."""
from fastapi import APIRouter, HTTPException
from typing import List, Optional, Dict

from .shared_models import ValidationRulesRequest
from .helpers import _build_validation_rules_impl, load_db, save_db, _normalize_special_days
import json

router = APIRouter(prefix="/api", tags=["planillas"])


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
