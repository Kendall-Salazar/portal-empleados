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
        return [], {"enabled": False, "label": "Mock", "selection_fallback": False}

router = APIRouter(prefix="/api", tags=["horarios"])

# Mismo orden que el listado del cliente (más reciente primero).
_HISTORY_LIST_ORDER = "timestamp DESC, id DESC"
_TRASH_LIST_ORDER = "deleted_at DESC, id DESC"


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
    prioritize_jefe_coverage: bool = True


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
    use_tpl = _plan_db.get_use_pref_plantilla()
    employees_data = []
    for e in unified_emps:
        rp = _plan_db.resolve_prefs_for_solver(e, use_pref_plantilla=use_tpl)
        employees_data.append({
            "name": e.get("nombre", ""),
            "gender": e.get("genero", "M"),
            "can_do_night": bool(e.get("puede_nocturno", 1)),
            "allow_no_rest": rp["allow_no_rest"],
            "forced_libres": rp["forced_libres"],
            "forced_quebrado": rp["forced_quebrado"],
            "is_jefe_pista": bool(e.get("es_jefe_pista", 0)),
            "is_practicante": bool(e.get("es_practicante", 0)),
            "strict_preferences": rp["strict_preferences"],
            "fixed_shifts": rp["fixed_shifts"],
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

    # NO guardar en DB — el horario generado es solo visual hasta que el usuario decida guardarlo
    return result


@router.get("/history")
def get_history():
    """Get schedule history."""
    db = _load_db()
    return db.get("history_log", [])


@router.post("/history")
def save_history(entry: HistoryEntry):
    """Misma semántica que main: siempre INSERT (varios con el mismo nombre), sin purga de activos."""
    horario_json = json.dumps(entry.schedule, ensure_ascii=False)
    tareas_json = json.dumps(entry.daily_tasks or {}, ensure_ascii=False)
    metadata_json = json.dumps({
        "rotation_queue": entry.dict().get("next_sunday_rotation_queue"),
        "rotation_target": entry.dict().get("next_sunday_cycle_index"),
        "special_days": entry.special_days or {},
        "week_dates": entry.week_dates,
    }, ensure_ascii=False)
    ts = entry.timestamp or datetime.datetime.now().isoformat()

    conn = plan_db.get_conn()
    conn.execute("""
        INSERT INTO horarios_generados (nombre, horario, tareas, metadata, timestamp, deleted, deleted_at)
        VALUES (?, ?, ?, ?, ?, 0, NULL)
    """, (entry.name, horario_json, tareas_json, metadata_json, ts))

    conn.execute("""
        DELETE FROM horarios_generados
        WHERE deleted = 1 AND deleted_at IS NOT NULL
        AND datetime(deleted_at) < datetime('now', '-7 days')
    """)

    if entry.next_sunday_rotation_queue is not None:
        conn.execute(
            "UPDATE horario_config SET sunday_rotation_queue = ? WHERE id = 1",
            (json.dumps(entry.next_sunday_rotation_queue),),
        )
    elif entry.next_sunday_cycle_index is not None:
        conn.execute(
            "UPDATE horario_config SET sunday_cycle_index = ? WHERE id = 1",
            (entry.next_sunday_cycle_index,),
        )

    conn.commit()
    conn.close()

    total_conn = plan_db.get_conn()
    total = total_conn.execute("SELECT COUNT(*) FROM horarios_generados WHERE IFNULL(deleted, 0) = 0").fetchone()[0]
    total_conn.close()
    return {"status": "Saved", "history_len": total}


@router.delete("/history/{index}")
def delete_history_item(index: int):
    """Soft delete a history entry — moves to trash instead of permanent deletion."""
    import database as db_module
    
    conn = db_module.get_conn()
    
    # Get the entry by id (not index — we need to map index to actual row)
    active_rows = conn.execute(
        f"SELECT id FROM horarios_generados WHERE deleted = 0 ORDER BY {_HISTORY_LIST_ORDER}"
    ).fetchall()
    
    if 0 <= index < len(active_rows):
        row_id = active_rows[index]["id"]
        now = datetime.datetime.now().isoformat()
        conn.execute(
            "UPDATE horarios_generados SET deleted = 1, deleted_at = ? WHERE id = ? AND deleted = 0",
            (now, row_id)
        )
        conn.commit()
        conn.close()
        return {"status": "Trashed", "message": "Movido a la papelera"}
    
    conn.close()
    raise HTTPException(status_code=404, detail="Index out of bounds")


@router.get("/history/trash")
def get_trash():
    """List soft-deleted history entries (papelera de reciclaje)."""
    import database as db_module
    
    conn = db_module.get_conn()
    rows = conn.execute(
        "SELECT id, nombre, timestamp, deleted_at FROM horarios_generados "
        "WHERE deleted = 1 ORDER BY deleted_at DESC"
    ).fetchall()
    conn.close()
    
    return [
        {
            "db_id": r["id"],
            "name": r["nombre"],
            "timestamp": r["timestamp"],
            "deleted_at": r["deleted_at"],
        }
        for r in rows
    ]


@router.post("/history/{index}/restore")
def restore_history_item(index: int):
    """Restore a soft-deleted history entry from trash."""
    import database as db_module
    
    conn = db_module.get_conn()
    
    # Get trash entries
    trash_rows = conn.execute(
        f"SELECT id FROM horarios_generados WHERE deleted = 1 ORDER BY {_TRASH_LIST_ORDER}"
    ).fetchall()
    
    if 0 <= index < len(trash_rows):
        row_id = trash_rows[index]["id"]
        conn.execute(
            "UPDATE horarios_generados SET deleted = 0, deleted_at = NULL WHERE id = ?",
            (row_id,)
        )
        conn.commit()
        conn.close()
        return {"status": "Restored", "message": "Semana restaurada del historial"}
    
    conn.close()
    raise HTTPException(status_code=404, detail="Index out of bounds")


@router.post("/history/trash/restore/{row_id}")
def restore_history_item_by_row_id(row_id: int):
    """Restaurar desde la papelera por id de fila (alineado con db_id del listado)."""
    import database as db_module
    
    conn = db_module.get_conn()
    row = conn.execute(
        "SELECT id FROM horarios_generados WHERE id = ? AND deleted = 1", (row_id,)
    ).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Entrada no encontrada en la papelera")
    conn.execute(
        "UPDATE horarios_generados SET deleted = 0, deleted_at = NULL WHERE id = ?",
        (row_id,),
    )
    conn.commit()
    conn.close()
    return {"status": "Restored", "message": "Semana restaurada del historial"}


@router.delete("/history/trash/{index}")
def permanent_delete_history_item(index: int):
    """Permanently delete a soft-deleted entry from trash."""
    import database as db_module
    
    conn = db_module.get_conn()
    
    trash_rows = conn.execute(
        f"SELECT id FROM horarios_generados WHERE deleted = 1 ORDER BY {_TRASH_LIST_ORDER}"
    ).fetchall()
    
    if 0 <= index < len(trash_rows):
        row_id = trash_rows[index]["id"]
        conn.execute("DELETE FROM horarios_generados WHERE id = ?", (row_id,))
        conn.commit()
        conn.close()
        return {"status": "Permanently deleted"}
    
    conn.close()
    raise HTTPException(status_code=404, detail="Index out of bounds")


@router.delete("/history/trash/entry/{row_id}")
def permanent_delete_history_item_by_row_id(row_id: int):
    """Eliminar permanentemente por id de fila."""
    import database as db_module
    
    conn = db_module.get_conn()
    cur = conn.execute(
        "DELETE FROM horarios_generados WHERE id = ? AND deleted = 1", (row_id,)
    )
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Entrada no encontrada en la papelera")
    conn.commit()
    conn.close()
    return {"status": "Permanently deleted"}


@router.post("/history/trash/purge")
def purge_old_trash():
    """Permanently delete entries that have been in trash for more than 7 days."""
    import database as db_module
    
    conn = db_module.get_conn()
    
    # Delete entries where deleted_at is older than 7 days
    conn.execute("""
        DELETE FROM horarios_generados 
        WHERE deleted = 1 AND deleted_at IS NOT NULL 
        AND datetime(deleted_at) < datetime('now', '-7 days')
    """)
    affected = conn.total_changes
    conn.commit()
    conn.close()
    
    return {"status": "Purged", "deleted_count": affected}


@router.patch("/history/{index}")
def update_history_item(index: int, entry: HistoryEntry):
    """Update a history entry directly in SQLite — no save_db() involved."""
    conn = plan_db.get_conn()

    active_rows = conn.execute(
        f"SELECT id, nombre, horario, tareas, metadata FROM horarios_generados WHERE deleted = 0 ORDER BY {_HISTORY_LIST_ORDER}"
    ).fetchall()

    if 0 <= index < len(active_rows):
        row = active_rows[index]
        row_id = row["id"]

        horario_json = json.dumps(entry.schedule, ensure_ascii=False)
        tareas_json = json.dumps(entry.daily_tasks or {}, ensure_ascii=False)

        existing_meta = json.loads(row["metadata"]) if row["metadata"] else {}
        normalized_special_days = _normalize_special_days(entry.special_days)
        if normalized_special_days:
            existing_meta["special_days"] = normalized_special_days
        else:
            existing_meta.pop("special_days", None)
        if entry.week_dates is not None:
            existing_meta["week_dates"] = entry.week_dates

        metadata_json = json.dumps(existing_meta, ensure_ascii=False)

        conn.execute("""
            UPDATE horarios_generados SET horario = ?, tareas = ?, metadata = ? WHERE id = ?
        """, (horario_json, tareas_json, metadata_json, row_id))
        conn.commit()
        conn.close()
        return {"status": "Updated"}

    conn.close()
    raise HTTPException(status_code=404, detail="Index out of bounds")


@router.put("/history")
def rename_history_entry(rename_data: dict):
    """Rename a history entry directly in SQLite — no save_db() involved."""
    conn = plan_db.get_conn()

    new_name = rename_data.get("name", "").strip()
    db_id = rename_data.get("db_id")

    if not new_name:
        conn.close()
        raise HTTPException(status_code=400, detail="Index and name are required")

    if db_id is not None:
        cur = conn.execute(
            "UPDATE horarios_generados SET nombre = ? WHERE id = ? AND deleted = 0",
            (new_name, int(db_id)),
        )
        if cur.rowcount:
            conn.commit()
            conn.close()
            return {"status": "Renamed", "name": new_name}
        conn.close()
        raise HTTPException(status_code=404, detail="Index out of bounds")

    index = rename_data.get("index")
    if index is None:
        conn.close()
        raise HTTPException(status_code=400, detail="Index and name are required")

    active_rows = conn.execute(
        f"SELECT id FROM horarios_generados WHERE deleted = 0 ORDER BY {_HISTORY_LIST_ORDER}"
    ).fetchall()

    if 0 <= index < len(active_rows):
        row_id = active_rows[index]["id"]
        conn.execute("UPDATE horarios_generados SET nombre = ? WHERE id = ?", (new_name, row_id))
        conn.commit()
        conn.close()
        return {"status": "Renamed", "name": new_name}

    conn.close()
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
    
    # ── Construir resultado: semanas = entradas desde el último domingo libre ──
    result = []
    total = len(history_list)
    
    for i, emp_name in enumerate(rotation_queue):
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
            weeks_ago = total - 1 - last_idx
            if weeks_ago == 0:
                weeks_since_off = "Esta semana"
            elif weeks_ago == 1:
                weeks_since_off = "Hace 1 sem"
            else:
                weeks_since_off = f"Hace {weeks_ago} sem"
        else:
            weeks_since_off = "Sin registrar"
        
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
    """Reassign tasks for a history entry — reads/writes directly to SQLite."""
    conn = plan_db.get_conn()

    active_rows = conn.execute(
        f"SELECT id, nombre, horario, tareas, metadata FROM horarios_generados WHERE IFNULL(deleted, 0) = 0 ORDER BY {_HISTORY_LIST_ORDER}"
    ).fetchall()

    if not (0 <= index < len(active_rows)):
        conn.close()
        raise HTTPException(status_code=404, detail="Index out of bounds")

    row = active_rows[index]
    row_id = row["id"]
    schedule = json.loads(row["horario"]) if row["horario"] else {}

    if not isinstance(schedule, dict) or not schedule:
        conn.close()
        raise HTTPException(status_code=400, detail="El historial no tiene un horario válido")

    # Read employees and config from DB
    employees_rows = conn.execute("SELECT * FROM horario_empleados WHERE activo=1").fetchall()
    employees_data = [dict(e) for e in employees_rows]
    employee_names = {emp.get("nombre", "") for emp in employees_data}
    for missing_name in sorted(name for name in schedule.keys() if name not in employee_names):
        employees_data.append({"nombre": missing_name, "genero": "M", "puede_nocturno": 1})

    config_row = conn.execute("SELECT * FROM horario_config WHERE id=1").fetchone()
    config_data = dict(config_row) if config_row else {}
    config_data["use_refuerzo"] = "Refuerzo" in schedule
    existing_meta = json.loads(row["metadata"]) if row["metadata"] else {}
    special_days = _normalize_special_days(existing_meta.get("special_days", {}))
    config_data["special_days"] = special_days

    scheduler = ShiftScheduler(employees_data, config_data, history_data=[])
    daily_tasks = scheduler.assign_tasks(schedule)

    # Update tasks in metadata
    existing_meta["daily_tasks"] = daily_tasks
    if special_days:
        existing_meta["special_days"] = special_days
    else:
        existing_meta.pop("special_days", None)

    conn.execute(
        "UPDATE horarios_generados SET tareas = ?, metadata = ? WHERE id = ?",
        (json.dumps(daily_tasks, ensure_ascii=False), json.dumps(existing_meta, ensure_ascii=False), row_id)
    )
    conn.commit()
    conn.close()

    return {
        "status": "Updated",
        "daily_tasks": daily_tasks,
        "special_days": special_days,
    }
