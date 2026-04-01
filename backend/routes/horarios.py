"""API router for scheduling and history endpoints."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import json
import datetime
import sys
import os

# Import directly
import sys
import os
_backend_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.abspath(os.path.join(_backend_dir, ".."))
_planillas_dir = os.path.join(_root_dir, "planillas")
if os.path.exists(_planillas_dir) and _planillas_dir not in sys.path:
    sys.path.insert(0, _planillas_dir)

from scheduler_engine import ShiftScheduler
import database as plan_db


# Import helper functions from main - will be set after import
def _get_helper_functions():
    """Get helper functions from main module after it's fully loaded."""
    import main as main_module
    return (
        main_module.plan_db,
        main_module.load_db,
        main_module.save_db,
        main_module._normalize_special_days,
        main_module._prepare_history_for_solver,
    )


# Try to get helpers, otherwise use fallbacks
try:
    import main as main_module
    _plan_db = main_module.plan_db
    _load_db = main_module.load_db
    _save_db = main_module.save_db
    _normalize_special_days = main_module._normalize_special_days
    _prepare_history_for_solver = main_module._prepare_history_for_solver
except (ImportError, AttributeError):
    # Fallbacks
    _plan_db = plan_db
    
    def _load_db():
        return {"employees": [], "config": {}, "history_log": [], "last_result": {}}
    
    def _save_db(data):
        pass
    
    def _normalize_special_days(special_days):
        return special_days if isinstance(special_days, dict) else {}
    
    def _prepare_history_for_solver(history_list, target_week_start=None, use_history=True, max_entries=3):
        return [], {"enabled": False, "label": "Mock"}

router = APIRouter(prefix="/api", tags=["horarios"])


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
    sunday_cycle_index: int = 0
    sunday_rotation_queue: Optional[List[str]] = None


class SolverRequest(BaseModel):
    employees: List[Employee]
    config: Config
    target_week_start: Optional[str] = None
    special_days: Dict[str, str] = Field(default_factory=dict)


class HistoryEntry(BaseModel):
    name: str
    schedule: Dict[str, Dict[str, str]]
    daily_tasks: Dict[str, Dict[str, Optional[str]]] = Field(default_factory=dict)
    next_sunday_cycle_index: Optional[int] = None
    next_sunday_rotation_queue: Optional[List[str]] = None
    week_dates: Optional[Dict[str, str]] = None
    special_days: Dict[str, str] = Field(default_factory=dict)
    timestamp: str = ""


# Endpoints
@router.post("/solve")
def solve_schedule(request: SolverRequest):
    """Generate a new schedule."""
    db = _load_db()
    
    # Get History
    history_list = db.get("history_log", [])
    if not isinstance(history_list, list):
        history_list = []
        
    # Always read employees from SQLite
    try:
        unified_emps = _plan_db.get_empleados(solo_activos=True)
    except Exception:
        unified_emps = []
    employees_data = []
    for e in unified_emps:
        try:
            fixed_shifts = json.loads(e.get("turnos_fijos", "{}")) if e.get("turnos_fijos") else {}
        except (json.JSONDecodeError, TypeError):
            fixed_shifts = {}
        employees_data.append({
            "name": e.get("nombre", ""),
            "gender": e.get("genero", "M"),
            "can_do_night": bool(e.get("puede_nocturno", 1)),
            "allow_no_rest": bool(e.get("allow_no_rest", 0)),
            "forced_libres": bool(e.get("forced_libres", 0)),
            "forced_quebrado": bool(e.get("forced_quebrado", 0)),
            "is_jefe_pista": bool(e.get("es_jefe_pista", 0)),
            "is_practicante": bool(e.get("es_practicante", 0)),
            "strict_preferences": bool(e.get("strict_preferences", 0)),
            "fixed_shifts": fixed_shifts
        })

    config_data = request.config.dict()
    special_days = _normalize_special_days(request.special_days)
    config_data["special_days"] = special_days
    history_for_solver, history_context = _prepare_history_for_solver(
        history_list,
        target_week_start=request.target_week_start,
        use_history=config_data.get("use_history", True),
    )
    
    # Instantiate Scheduler
    scheduler = ShiftScheduler(employees_data, config_data, history_data=history_for_solver)
    result = scheduler.solve()

    if isinstance(result, dict):
        metadata = result.setdefault("metadata", {})
        metadata["history_enabled"] = history_context["enabled"]
        metadata["history_entries_used"] = history_context["entries_used"]
        metadata["history_context_label"] = history_context["label"]
        metadata["special_days"] = special_days

    # Save last result
    if result.get("schedule"):
        db["last_result"] = result
        try:
            _save_db(db)
        except Exception as e:
            print(f"Warning: Could not save to DB (may be locked): {e}")
            # Continue anyway - the result is still returned to frontend
    
    return result


@router.get("/history")
def get_history():
    """Get schedule history."""
    db = _load_db()
    return db.get("history_log", [])


@router.post("/history")
def save_history(entry: HistoryEntry):
    """Save a new history entry."""
    db = _load_db()
    history_list = db.get("history_log", [])
    if not isinstance(history_list, list):
        history_list = []
    
    new_record = entry.dict()
    if not new_record.get("timestamp"):
        new_record["timestamp"] = datetime.datetime.now().isoformat()
    normalized_special_days = _normalize_special_days(entry.special_days)
    if normalized_special_days:
        new_record["special_days"] = normalized_special_days
    else:
        new_record.pop("special_days", None)
    if entry.week_dates:
        new_record["week_dates"] = entry.week_dates
        
    history_list.append(new_record)
    
    if len(history_list) > 50:
        history_list = history_list[-50:]
        
    db["history_log"] = history_list
    
    if "config" not in db:
        db["config"] = {}
    if entry.next_sunday_rotation_queue is not None:
        db["config"]["sunday_rotation_queue"] = entry.next_sunday_rotation_queue
    elif entry.next_sunday_cycle_index is not None:
        db["config"]["sunday_cycle_index"] = entry.next_sunday_cycle_index
        
    _save_db(db)
    return {"status": "Saved", "history_len": len(history_list)}


@router.delete("/history/{index}")
def delete_history_item(index: int):
    """Delete a history entry."""
    db = _load_db()
    history_list = db.get("history_log", [])
    
    if 0 <= index < len(history_list):
        history_list.pop(index)
        db["history_log"] = history_list
        save_db(db)
        return {"status": "Deleted"}
    raise HTTPException(status_code=404, detail="Index out of bounds")


@router.patch("/history/{index}")
def update_history_item(index: int, entry: HistoryEntry):
    """Update a history entry."""
    db = load_db()
    history_list = db.get("history_log", [])
    
    if 0 <= index < len(history_list):
        history_list[index]["schedule"] = entry.schedule
        history_list[index]["daily_tasks"] = entry.daily_tasks
        if entry.week_dates is not None:
            history_list[index]["week_dates"] = entry.week_dates
        normalized_special_days = _normalize_special_days(entry.special_days)
        if normalized_special_days:
            history_list[index]["special_days"] = normalized_special_days
        else:
            history_list[index].pop("special_days", None)
        db["history_log"] = history_list
        save_db(db)
        return {"status": "Updated"}
    raise HTTPException(status_code=404, detail="Index out of bounds")


@router.put("/history")
def rename_history_entry(rename_data: dict):
    """Rename a history entry."""
    db = _load_db()
    history_list = db.get("history_log", [])
    
    index = rename_data.get("index")
    new_name = rename_data.get("name", "").strip()
    
    if index is None or not new_name:
        raise HTTPException(status_code=400, detail="Index and name are required")
    
    if 0 <= index < len(history_list):
        history_list[index]["name"] = new_name
        db["history_log"] = history_list
        _save_db(db)
        return {"status": "Renamed", "name": new_name}
    raise HTTPException(status_code=404, detail="Index out of bounds")


@router.get("/rotacion-domingos")
def get_sunday_rotation():
    """Get Sunday rotation queue — usa cola guardada o reconstruye desde historial."""
    db = load_db()
    history_list = db.get("history_log", [])
    config = db.get("config", {})
    
    unified_emps = plan_db.get_empleados(solo_activos=True)
    eligible = [e["nombre"] for e in unified_emps if not e.get("es_jefe_pista", False)]
    
    # ── Intentar usar cola guardada en config ──
    saved_queue = config.get("sunday_rotation_queue")
    saved_index = config.get("sunday_cycle_index", 0)
    
    if saved_queue and isinstance(saved_queue, list):
        # Filtrar solo empleados que aún son elegibles
        rotation_queue = [name for name in saved_queue if name in eligible]
        # Agregar nuevos empleados que no estaban en la cola
        for name in eligible:
            if name not in rotation_queue:
                rotation_queue.append(name)
        # Usar índice guardado para determinar quién sigue
        if rotation_queue and saved_index is not None:
            next_idx = saved_index % len(rotation_queue)
            rotation_queue = rotation_queue[next_idx:] + rotation_queue[:next_idx]
    else:
        # ── Reconstruir desde historial ──
        last_sunday_off = {}
        for idx, entry in enumerate(history_list):
            sched = entry.get('schedule', {})
            if isinstance(sched, str):
                try:
                    sched = json.loads(sched)
                except json.JSONDecodeError:
                    sched = {}
            
            for emp_name, days in sched.items():
                if isinstance(days, dict) and days.get('Dom') in ['OFF', 'VAC', 'PERM'] and emp_name in eligible:
                    last_sunday_off[emp_name] = idx
        
        # Ordenar: primero los que NO han descansado (índice -1), luego los más antiguos
        rotation_queue = sorted(eligible, key=lambda e: last_sunday_off.get(e, -1))
    
    # ── Construir resultado con semanas reales ──
    result = []
    total_entries = len(history_list)
    
    for i, emp_name in enumerate(rotation_queue):
        # Buscar el último índice donde tuvo domingo libre
        last_idx = None
        for idx, entry in enumerate(history_list):
            sched = entry.get('schedule', {})
            if isinstance(sched, str):
                try:
                    sched = json.loads(sched)
                except json.JSONDecodeError:
                    sched = {}
            
            days = sched.get(emp_name, {})
            if isinstance(days, dict) and days.get('Dom') in ['OFF', 'VAC', 'PERM']:
                last_idx = idx
        
        if last_idx is not None:
            weeks_ago = total_entries - 1 - last_idx
            if weeks_ago == 0:
                weeks_since_off = "La sem pasada"
            elif weeks_ago == 1:
                weeks_since_off = "Hace 1 sem"
            else:
                weeks_since_off = f"Hace {weeks_ago} sem"
        else:
            weeks_since_off = "Sin registrar"
        
        # Prioridad basada en posición en la cola
        if i == 0:
            priority = "★ Le toca descansar"
        elif i <= 2:
            priority = "Próximo a descansar"
        elif i <= len(rotation_queue) // 2:
            priority = "En cola media"
        else:
            priority = "Recién descansó"
            
        result.append({
            "name": emp_name,
            "last_off": weeks_since_off,
            "priority": priority
        })
        
    return result


@router.post("/history/{index}/reassign_tasks")
def reassign_history_tasks(index: int):
    """Reassign tasks for a history entry."""
    db = load_db()
    history_list = db.get("history_log", [])

    if not (0 <= index < len(history_list)):
        raise HTTPException(status_code=404, detail="Index out of bounds")

    entry = history_list[index]
    schedule = entry.get("schedule", {})
    if not isinstance(schedule, dict) or not schedule:
        raise HTTPException(status_code=400, detail="El historial no tiene un horario válido")

    employees_data = [
        dict(employee)
        for employee in (db.get("employees", []) or [])
        if isinstance(employee, dict)
    ]
    employee_names = {emp.get("name") for emp in employees_data if isinstance(emp, dict)}
    for missing_name in sorted(name for name in schedule.keys() if name not in employee_names):
        employees_data.append({
            "name": missing_name,
            "gender": "M",
            "can_do_night": True,
            "allow_no_rest": False,
            "forced_libres": False,
            "forced_quebrado": False,
            "is_jefe_pista": False,
            "is_practicante": False,
            "strict_preferences": False,
            "fixed_shifts": {},
        })

    config_data = dict(db.get("config", {}) or {})
    config_data["use_refuerzo"] = "Refuerzo" in schedule
    special_days = _normalize_special_days(entry.get("special_days", {}))
    config_data["special_days"] = special_days

    scheduler = ShiftScheduler(employees_data, config_data, history_data=[])
    daily_tasks = scheduler.assign_tasks(schedule)

    history_list[index]["daily_tasks"] = daily_tasks
    if special_days:
        history_list[index]["special_days"] = special_days
    else:
        history_list[index].pop("special_days", None)
    db["history_log"] = history_list
    save_db(db)

    return {
        "status": "Updated",
        "daily_tasks": daily_tasks,
        "special_days": special_days,
    }
