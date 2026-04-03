"""API router for employees endpoints."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict
import json
import sys
import os

# Import plan_db directly
import sys
import os
_backend_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.abspath(os.path.join(_backend_dir, ".."))
_planillas_dir = os.path.join(_root_dir, "planillas")
if os.path.exists(_planillas_dir) and _planillas_dir not in sys.path:
    sys.path.insert(0, _planillas_dir)
import database as plan_db

router = APIRouter(prefix="/api", tags=["empleados"])


# Models
class Employee(BaseModel):
    name: str
    gender: str = "M"
    can_do_night: bool = True
    allow_no_rest: bool = False
    forced_libres: bool = False
    forced_quebrado: bool = False
    is_jefe_pista: bool = False
    is_practicante: bool = False
    strict_preferences: bool = False
    activo: bool = True
    fixed_shifts: Dict[str, str] = Field(default_factory=dict)


# Endpoints
@router.get("/employees")
def get_employees(include_inactive: bool = False):
    """Get all employees."""
    unified_emps = plan_db.get_empleados(solo_activos=not include_inactive)
    legacy_emps = []
    
    for e in unified_emps:
        try:
            fixed_shifts = json.loads(e.get("turnos_fijos", "{}")) if e.get("turnos_fijos") else {}
        except (json.JSONDecodeError, TypeError):
            print(f"/api/employees: turnos_fijos inválido para {e.get('nombre', '<sin_nombre>')}")
            fixed_shifts = {}
            
        legacy_emps.append({
            "id": e.get("id"),
            "name": e.get("nombre", ""),
            "gender": e.get("genero", "M"),
            "can_do_night": bool(e.get("puede_nocturno", 1)),
            "allow_no_rest": bool(e.get("allow_no_rest", 0)),
            "forced_libres": bool(e.get("forced_libres", 0)),
            "forced_quebrado": bool(e.get("forced_quebrado", 0)),
            "is_jefe_pista": bool(e.get("es_jefe_pista", 0)),
            "is_practicante": bool(e.get("es_practicante", 0)),
            "strict_preferences": bool(e.get("strict_preferences", 0)),
            "activo": bool(e.get("activo", 1)),
            "fixed_shifts": fixed_shifts,
        })
        
    return legacy_emps


@router.post("/employees")
def update_employees(employees: List[Employee]):
    """Update or create employees."""
    for e in employees:
        exist = plan_db.get_conn().execute("SELECT id, activo FROM empleados WHERE nombre=?", (e.name,)).fetchone()
        if exist:
            if e.activo and exist["activo"] == 0:
                plan_db.reactivar_empleado(exist["id"])
            elif not e.activo and exist["activo"] == 1:
                plan_db.remove_empleado(exist["id"])
            
            # Update basic settings
            plan_db.update_empleado(
                exist["id"], 
                genero=e.gender,
                puede_nocturno=1 if e.can_do_night else 0,
                forced_libres=1 if e.forced_libres else 0,
                forced_quebrado=1 if e.forced_quebrado else 0,
                allow_no_rest=1 if e.allow_no_rest else 0,
                es_jefe_pista=1 if e.is_jefe_pista else 0,
                strict_preferences=1 if e.strict_preferences else 0,
                turnos_fijos=json.dumps(e.fixed_shifts),
            )
        else:
            plan_db.add_empleado(
                nombre=e.name,
                tipo_pago="efectivo",
                genero=e.gender,
                puede_nocturno=1 if e.can_do_night else 0,
                forced_libres=1 if e.forced_libres else 0,
                forced_quebrado=1 if e.forced_quebrado else 0,
                allow_no_rest=1 if e.allow_no_rest else 0,
                es_jefe_pista=1 if e.is_jefe_pista else 0,
                strict_preferences=1 if e.strict_preferences else 0,
                turnos_fijos=json.dumps(e.fixed_shifts),
            )
            # Fetch new ID in case it was created without activo
            if not e.activo:
                added = plan_db.get_conn().execute("SELECT id FROM empleados WHERE nombre=?", (e.name,)).fetchone()
                if added:
                    plan_db.remove_empleado(added["id"])
    return {"status": "Updated"}


@router.put("/employees/{name}")
def update_single_employee(name: str, emp: Employee):
    """Update a single employee by name — avoids bulk array stale-data risk."""
    from fastapi import HTTPException
    exist = plan_db.get_conn().execute("SELECT id, activo FROM empleados WHERE nombre=?", (name,)).fetchone()
    if not exist:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")

    if emp.activo and exist["activo"] == 0:
        plan_db.reactivar_empleado(exist["id"])
    elif not emp.activo and exist["activo"] == 1:
        plan_db.remove_empleado(exist["id"])

    plan_db.update_empleado(
        exist["id"],
        genero=emp.gender,
        puede_nocturno=1 if emp.can_do_night else 0,
        forced_libres=1 if emp.forced_libres else 0,
        forced_quebrado=1 if emp.forced_quebrado else 0,
        allow_no_rest=1 if emp.allow_no_rest else 0,
        es_jefe_pista=1 if emp.is_jefe_pista else 0,
        strict_preferences=1 if emp.strict_preferences else 0,
        turnos_fijos=json.dumps(emp.fixed_shifts),
    )
    return {"status": "Updated"}
