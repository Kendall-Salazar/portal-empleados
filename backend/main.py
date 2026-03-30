from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import json
import os
import datetime
from scheduler_engine import ShiftScheduler
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment
from fastapi.responses import FileResponse
import tempfile
import subprocess
import shutil
import re
import unicodedata

app = FastAPI()

# DATABASE — SQLite backend (shared with planilla system)
import sys
import sqlite3

_backend_dir = os.path.dirname(os.path.abspath(__file__))


def _get_resource_root():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.abspath(sys._MEIPASS)
    return os.path.abspath(os.path.join(_backend_dir, ".."))


def _get_runtime_root():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.abspath(os.path.join(_backend_dir, ".."))


def _prefer_runtime_path(*parts):
    runtime_path = os.path.join(_runtime_root, *parts)
    resource_path = os.path.join(_resource_root, *parts)
    if os.path.exists(runtime_path):
        return runtime_path
    return resource_path


_resource_root = _get_resource_root()
_runtime_root = _get_runtime_root()
_resource_planillas_dir = os.path.join(_resource_root, "planillas")
_runtime_planillas_dir = os.path.join(_runtime_root, "planillas")
_planillas_dir = (
    _runtime_planillas_dir
    if os.path.exists(_runtime_planillas_dir) or not os.path.exists(_resource_planillas_dir)
    else _resource_planillas_dir
)
_frontend_dir = _prefer_runtime_path("frontend")
_template_path = _prefer_runtime_path("backend", "formato_template.xlsm")

os.makedirs(_planillas_dir, exist_ok=True)

# Add source planillas dir to path for local runs; frozen builds rely on bundled imports.
if os.path.exists(_resource_planillas_dir):
    sys.path.insert(0, os.path.abspath(_resource_planillas_dir))

import database as plan_db  # Initializes planilla.db with all tables
import planilla as pl_module
import generador_boletas as gb_module
import horario_db
import prestamo_sync

# Import routers
from routes import empleados_router, horarios_router, planillas_router, config_router

DB_FILE_LEGACY = "database.json"  # JSON original, kept for migration reference
EXPORT_DIR = os.path.join(_runtime_root, "export_horarios")
os.makedirs(EXPORT_DIR, exist_ok=True)

def _sanitize_export_stem(value: str, fallback: str = "horario") -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[<>:\"/\\\\|?*\x00-\x1F]+", " ", normalized)
    normalized = re.sub(r"\s+", "_", normalized.strip())
    normalized = re.sub(r"_+", "_", normalized).strip("._-")
    return normalized or fallback

def _build_export_filename_parts(filename: str, default_ext: str = ".png", fallback: str = "horario"):
    safe_name = os.path.basename(str(filename or "")).strip()
    stem, ext = os.path.splitext(safe_name)
    ext = (ext or default_ext).lower()
    if not re.fullmatch(r"\.[a-z0-9]+", ext):
        ext = default_ext
    return _sanitize_export_stem(stem or safe_name, fallback), ext

def _get_export_base_name(entry: Optional[dict], fallback: str = "horario") -> str:
    if not isinstance(entry, dict):
        return fallback
    return _sanitize_export_stem(entry.get("name"), fallback)

def _get_conn():
    """Get connection to the shared planilla.db"""
    return plan_db.get_conn()

def load_db():
    """Lee datos de SQLite y devuelve dict compatible con la estructura JSON original."""
    conn = _get_conn()

    # Empleados
    rows = conn.execute("SELECT * FROM horario_empleados WHERE activo=1").fetchall()
    employees = []
    for r in rows:
        emp = {
            "name": r["nombre"],
            "gender": r["genero"],
            "can_do_night": bool(r["puede_nocturno"]),
            "allow_no_rest": bool(r["allow_no_rest"]),
            "forced_libres": bool(r["forced_libres"]),
            "forced_quebrado": bool(r["forced_quebrado"]),
            "is_jefe_pista": bool(r["es_jefe_pista"]),
            "is_practicante": bool(r["es_practicante"]) if "es_practicante" in r.keys() else False,
            "strict_preferences": bool(r["strict_preferences"]) if "strict_preferences" in r.keys() else False,
            "fixed_shifts": json.loads(r["turnos_fijos"]) if r["turnos_fijos"] else {},
        }
        employees.append(emp)

    # Config
    cfg_row = conn.execute("SELECT * FROM horario_config WHERE id=1").fetchone()
    config = {}
    if cfg_row:
        config = {
            "night_mode": cfg_row["night_mode"],
            "fixed_night_person": cfg_row["fixed_night_person"],
            "allow_long_shifts": bool(cfg_row["allow_long_shifts"]),
            "use_refuerzo": bool(cfg_row["use_refuerzo"]),
            "refuerzo_type": cfg_row["refuerzo_type"],
            "refuerzo_start": cfg_row["refuerzo_start"] if "refuerzo_start" in cfg_row.keys() and cfg_row["refuerzo_start"] else "07:00",
            "refuerzo_end": cfg_row["refuerzo_end"] if "refuerzo_end" in cfg_row.keys() and cfg_row["refuerzo_end"] else "12:00",
            "allow_collision_quebrado": bool(cfg_row["allow_collision_quebrado"]),
            "collision_peak_priority": cfg_row["collision_peak_priority"],
            "sunday_cycle_index": cfg_row["sunday_cycle_index"] or 0,
            "sunday_rotation_queue": json.loads(cfg_row["sunday_rotation_queue"]) if cfg_row["sunday_rotation_queue"] else None,
            "use_history": bool(cfg_row["use_history"]) if "use_history" in cfg_row.keys() else True,
        }

    # History log
    hist_rows = conn.execute("SELECT * FROM horarios_generados ORDER BY id").fetchall()
    history_log = []
    for r in hist_rows:
        entry = {
            "name": r["nombre"],
            "schedule": json.loads(r["horario"]),
            "daily_tasks": json.loads(r["tareas"]) if r["tareas"] else {},
            "timestamp": r["timestamp"],
        }
        meta = json.loads(r["metadata"]) if r["metadata"] else {}
        entry.update(meta)
        history_log.append(entry)

    # Last result: use the most recent history entry or empty
    last_result = {}
    if history_log:
        last_entry = history_log[-1]
        last_result = {
            "status": "Success",
            "schedule": last_entry.get("schedule", {}),
            "daily_tasks": last_entry.get("daily_tasks", {}),
            "metadata": {k: v for k, v in last_entry.items() if k not in ("name", "schedule", "daily_tasks", "timestamp")},
        }

    conn.close()
    return {
        "employees": employees,
        "config": config,
        "history_log": history_log,
        "last_result": last_result,
    }


def save_db(data):
    """Guarda dict de vuelta a SQLite, manteniendo compatibilidad."""
    conn = _get_conn()

    # Guardar empleados
    if "employees" in data:
        # Desactivar todos primero
        conn.execute("UPDATE horario_empleados SET activo=0")
        for emp in data["employees"]:
            existing = conn.execute(
                "SELECT id FROM horario_empleados WHERE nombre=?", (emp["name"],)
            ).fetchone()
            if existing:
                conn.execute("""
                    UPDATE horario_empleados SET
                        genero=?, puede_nocturno=?, allow_no_rest=?, forced_libres=?,
                        forced_quebrado=?, es_jefe_pista=?, es_practicante=?, strict_preferences=?, turnos_fijos=?, activo=1
                    WHERE nombre=?
                """, (
                    emp.get("gender", "M"),
                    1 if emp.get("can_do_night", True) else 0,
                    1 if emp.get("allow_no_rest", False) else 0,
                    1 if emp.get("forced_libres", False) else 0,
                    1 if emp.get("forced_quebrado", False) else 0,
                    1 if emp.get("is_jefe_pista", False) else 0,
                    1 if emp.get("is_practicante", False) else 0,
                    1 if emp.get("strict_preferences", False) else 0,
                    json.dumps(emp.get("fixed_shifts", {}), ensure_ascii=False),
                    emp["name"],
                ))
            else:
                conn.execute("""
                    INSERT INTO horario_empleados
                    (nombre, genero, puede_nocturno, allow_no_rest, forced_libres,
                     forced_quebrado, es_jefe_pista, es_practicante, strict_preferences, turnos_fijos, activo)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    emp["name"], emp.get("gender", "M"),
                    1 if emp.get("can_do_night", True) else 0,
                    1 if emp.get("allow_no_rest", False) else 0,
                    1 if emp.get("forced_libres", False) else 0,
                    1 if emp.get("forced_quebrado", False) else 0,
                    1 if emp.get("is_jefe_pista", False) else 0,
                    1 if emp.get("is_practicante", False) else 0,
                    1 if emp.get("strict_preferences", False) else 0,
                    json.dumps(emp.get("fixed_shifts", {}), ensure_ascii=False),
                ))

    # Guardar config
    if "config" in data:
        cfg = data["config"]
        conn.execute("DELETE FROM horario_config")
        conn.execute("""
            INSERT INTO horario_config
            (id, night_mode, fixed_night_person, allow_long_shifts, use_refuerzo,
             refuerzo_type, refuerzo_start, refuerzo_end, allow_collision_quebrado,
             collision_peak_priority, sunday_cycle_index, sunday_rotation_queue, use_history)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cfg.get("night_mode", "rotation"),
            cfg.get("fixed_night_person"),
            1 if cfg.get("allow_long_shifts", False) else 0,
            1 if cfg.get("use_refuerzo", False) else 0,
            cfg.get("refuerzo_type", "personalizado"),
            cfg.get("refuerzo_start", "07:00"),
            cfg.get("refuerzo_end", "12:00"),
            1 if cfg.get("allow_collision_quebrado", False) else 0,
            cfg.get("collision_peak_priority", "pm"),
            cfg.get("sunday_cycle_index", 0),
            json.dumps(cfg.get("sunday_rotation_queue")) if cfg.get("sunday_rotation_queue") else None,
            1 if cfg.get("use_history", True) else 0,
        ))

    # Guardar history_log (reescribir completo)
    if "history_log" in data:
        conn.execute("DELETE FROM horarios_generados")
        for entry in data["history_log"]:
            meta = {k: v for k, v in entry.items()
                    if k not in ("name", "schedule", "daily_tasks", "timestamp")}
            conn.execute("""
                INSERT INTO horarios_generados (nombre, horario, tareas, metadata, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (
                entry.get("name", "SIN NOMBRE"),
                json.dumps(entry.get("schedule", {}), ensure_ascii=False),
                json.dumps(entry.get("daily_tasks", {}), ensure_ascii=False),
                json.dumps(meta, ensure_ascii=False),
                entry.get("timestamp", datetime.datetime.now().isoformat()),
            ))

    conn.commit()
    conn.close()


_WEEK_NAME_RE = re.compile(r"semana\s*(\d+)", re.IGNORECASE)
SCHEDULE_DAYS = ("Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue")
SPECIAL_DAY_MODES = {"normal", "sunday_like", "holy_thursday", "closed"}


def _normalize_special_days(raw_special_days):
    normalized = {}
    if not isinstance(raw_special_days, dict):
        return normalized

    for raw_day, raw_mode in raw_special_days.items():
        if raw_day not in SCHEDULE_DAYS:
            continue
        mode = raw_mode if raw_mode in SPECIAL_DAY_MODES else "normal"
        if raw_day == "Dom" and mode == "sunday_like":
            continue
        if raw_day != "Jue" and mode == "holy_thursday":
            continue
        if mode != "normal":
            normalized[raw_day] = mode
    return normalized


def _parse_date_like(value):
    if not value:
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if not isinstance(value, str):
        return None

    raw = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _parse_timestamp(value):
    if not value:
        return None
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime.combine(value, datetime.time.min)
    if not isinstance(value, str):
        return None
    raw = value.strip()
    try:
        return datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        parsed_date = _parse_date_like(raw)
        if parsed_date:
            return datetime.datetime.combine(parsed_date, datetime.time.min)
        return None


def _infer_week_start_from_name(name, fallback_year, reference_date=None):
    if not name or fallback_year is None:
        return None
    match = _WEEK_NAME_RE.search(name)
    if not match:
        return None
    week_number = int(match.group(1))
    if week_number < 1:
        return None

    candidates = []
    try:
        # Current UI naming uses the ISO week of the Monday inside the Fri-Thu range.
        monday = datetime.date.fromisocalendar(fallback_year, week_number, 1)
        candidates.append(monday - datetime.timedelta(days=3))
    except ValueError:
        pass
    try:
        # Legacy fallback for older names saved with the Friday ISO week number.
        candidates.append(datetime.date.fromisocalendar(fallback_year, week_number, 5))
    except ValueError:
        pass

    if not candidates:
        return None
    if reference_date:
        candidates.sort(key=lambda candidate: (
            abs((candidate - reference_date).days),
            0 if candidate <= reference_date else 1,
        ))
    return candidates[0]


def _extract_history_anchor(entry):
    week_dates = entry.get("week_dates")
    if isinstance(week_dates, dict):
        friday = week_dates.get("Vie")
        parsed = _parse_date_like(friday)
        if parsed:
            return parsed

    timestamp = _parse_timestamp(entry.get("timestamp"))
    inferred = _infer_week_start_from_name(
        entry.get("name", ""),
        timestamp.year if timestamp else None,
        timestamp.date() if timestamp else None,
    )
    return inferred


def _history_entry_display_name(info):
    if not isinstance(info, dict):
        return "semana previa"
    entry = info.get("entry") if isinstance(info.get("entry"), dict) else info
    name = entry.get("name")
    if name:
        return name
    sort_date = info.get("sort_date")
    if sort_date:
        return f"Semana del {sort_date.isoformat()}"
    return "semana previa"


def _prepare_history_for_solver(history_list, target_week_start=None, use_history=True, max_entries=3):
    if not use_history:
        return [], {
            "enabled": False,
            "label": "Historial desactivado",
            "entries_used": 0,
            "reference_name": None,
            "reference_week_start": None,
            "range_start_name": None,
            "range_start_week_start": None,
            "range_end_name": None,
            "range_end_week_start": None,
            "women_reference_name": None,
        }

    normalized = []
    for index, entry in enumerate(history_list or []):
        if not isinstance(entry, dict):
            continue
        timestamp = _parse_timestamp(entry.get("timestamp"))
        anchor = _extract_history_anchor(entry)
        sort_date = anchor or (timestamp.date() if timestamp else None)
        normalized.append({
            "entry": entry,
            "anchor": anchor,
            "sort_date": sort_date,
            "timestamp": timestamp,
            "index": index,
        })

    deduped = {}
    passthrough = []
    for info in normalized:
        if info["anchor"] is None:
            passthrough.append(info)
            continue
        previous = deduped.get(info["anchor"])
        current_rank = (info["timestamp"] or datetime.datetime.min, info["index"])
        previous_rank = (previous["timestamp"] or datetime.datetime.min, previous["index"]) if previous else None
        if previous is None or current_rank >= previous_rank:
            deduped[info["anchor"]] = info

    ordered = list(deduped.values()) + passthrough
    ordered.sort(key=lambda info: (
        info["sort_date"] or datetime.date.min,
        info["timestamp"] or datetime.datetime.min,
        info["index"],
    ))

    target_date = _parse_date_like(target_week_start)
    selection_reason = "latest"
    if target_date:
        previous_week = target_date - datetime.timedelta(days=7)
        eligible = [info for info in ordered if info["sort_date"] and info["sort_date"] < target_date]
        exact_previous = [info for info in eligible if info["sort_date"] == previous_week]
        if exact_previous:
            eligible = [info for info in eligible if info["sort_date"] <= previous_week]
            selection_reason = "exact_previous_week"
        else:
            selection_reason = "nearest_previous_week"
    else:
        eligible = ordered

    if not eligible:
        return [], {
            "enabled": True,
            "label": "Historial activo: sin semana previa elegible",
            "entries_used": 0,
            "reference_name": None,
            "reference_week_start": None,
            "range_start_name": None,
            "range_start_week_start": None,
            "range_end_name": None,
            "range_end_week_start": None,
            "women_reference_name": None,
        }

    selected = eligible[-max_entries:]
    first_reference = selected[0]
    reference = selected[-1]
    range_start_name = _history_entry_display_name(first_reference)
    range_end_name = _history_entry_display_name(reference)
    range_start_week_start = first_reference["sort_date"].isoformat() if first_reference["sort_date"] else None
    reference_week_start = reference["sort_date"].isoformat() if reference["sort_date"] else None

    if len(selected) == 1:
        label = f"Historial usado: {range_end_name}"
    else:
        label = f"Historial usado: Hombres {range_start_name} -> {range_end_name} | Mujeres {range_end_name}"

    return [info["entry"] for info in selected], {
        "enabled": True,
        "label": label,
        "entries_used": len(selected),
        "reference_name": reference["entry"].get("name"),
        "reference_week_start": reference_week_start,
        "range_start_name": range_start_name,
        "range_start_week_start": range_start_week_start,
        "range_end_name": range_end_name,
        "range_end_week_start": reference_week_start,
        "women_reference_name": range_end_name,
    }


def _normalize_inventory_header(value):
    if value is None:
        return ""
    text = str(value).strip().lower()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return text


def _matches_inventory_alias(normalized_value: str, alias: str) -> bool:
    if not normalized_value:
        return False
    return (
        normalized_value == alias
        or normalized_value.startswith(f"{alias} ")
        or f" {alias} " in f" {normalized_value} "
    )


def _detect_inventory_header_row(ws, target_fields, max_scan_rows=30, max_scan_cols=30):
    normalized_aliases = {
        field: [_normalize_inventory_header(alias) for alias in aliases]
        for field, aliases in target_fields.items()
    }

    best_row = None
    best_header_map = {}
    best_score = 0

    for row_idx in range(1, min(ws.max_row, max_scan_rows) + 1):
        row_header_map = {}
        matched_fields = set()

        for col_idx in range(1, min(ws.max_column, max_scan_cols) + 1):
            normalized_value = _normalize_inventory_header(ws.cell(row=row_idx, column=col_idx).value)
            if not normalized_value:
                continue

            for field, aliases in normalized_aliases.items():
                if field in matched_fields:
                    continue
                if any(_matches_inventory_alias(normalized_value, alias) for alias in aliases):
                    row_header_map[col_idx] = field
                    matched_fields.add(field)
                    break

        row_score = len(matched_fields)
        if row_score > best_score:
            best_score = row_score
            best_row = row_idx
            best_header_map = row_header_map

    return best_row, best_header_map

# INITIALIZATION (Seed if empty)
db = load_db()
if not db.get("employees"):
    default_employees = [
        {"name": "Jeison", "gender": "M", "can_do_night": False, "is_jefe_pista": True, "fixed_shifts": {"Vie": "J_06-16", "Lun": "J_06-16", "Mar": "J_06-16", "Mié": "J_06-16", "Jue": "J_06-16", "Sáb": "T1_05-13", "Dom": "OFF"}},
        {"name": "Eligio", "gender": "M", "can_do_night": True},
        {"name": "Maikel", "gender": "M", "can_do_night": True},
        {"name": "Jensy", "gender": "F", "can_do_night": False},
        {"name": "Ileana", "gender": "F", "can_do_night": False},
        {"name": "Steven", "gender": "M", "can_do_night": True},
        {"name": "Randall", "gender": "M", "can_do_night": True},
        {"name": "Angel", "gender": "M", "can_do_night": True},
        {"name": "Keilor", "gender": "M", "can_do_night": True}
    ]
    db["employees"] = default_employees
    db["config"] = {
        "night_mode": "rotation", 
        "fixed_night_person": "Eligio",
        "refuerzo_type": "personalizado",
        "refuerzo_start": "07:00",
        "refuerzo_end": "12:00",
        "use_history": True,
    }
    save_db(db)

# MODELS
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
    sunday_cycle_index: int = 0  # Legacy, kept for backwards compat
    sunday_rotation_queue: Optional[List[str]] = None

class SolverRequest(BaseModel):
    employees: List[Employee]
    config: Config
    target_week_start: Optional[str] = None
    special_days: Dict[str, str] = Field(default_factory=dict)

class PlanillaPermiso(BaseModel):
    empleado_id: int
    fecha: str
    motivo: Optional[str] = None
    notas: Optional[str] = None

class DescontarPermisosRequest(BaseModel):
    empleado_id: int
    cantidad: int
    anio: int

class SyncVacPermRequest(BaseModel):
    fecha_inicio: str
    fecha_fin: str

class HistoryEntry(BaseModel):
    name: str
    schedule: Dict[str, Dict[str, str]]
    daily_tasks: Dict[str, Dict[str, Optional[str]]] = Field(default_factory=dict)
    next_sunday_cycle_index: Optional[int] = None  # Legacy
    next_sunday_rotation_queue: Optional[List[str]] = None
    week_dates: Optional[Dict[str, str]] = None
    special_days: Dict[str, str] = Field(default_factory=dict)
    timestamp: str = "" 


class ValidationRulesRequest(BaseModel):
    special_days: Dict[str, str] = Field(default_factory=dict)

class ImageExportRequest(BaseModel):
    image_data: str  # Base64 string
    filename: str = "horario.png"

# ENDPOINTS
@app.get("/api/employees")
def get_employees(include_inactive: bool = False):
    # Map from the unified Planilla Database format to the legacy generator format
    unified_emps = plan_db.get_empleados(solo_activos=not include_inactive)
    legacy_emps = []
    
    for e in unified_emps:
        try:
            fixed_shifts = json.loads(e.get("turnos_fijos", "{}")) if e.get("turnos_fijos") else {}
        except (json.JSONDecodeError, TypeError):
            print(f"/api/employees: turnos_fijos inválido para {e.get('nombre', '<sin_nombre>')}")
            fixed_shifts = {}
            
        legacy_emps.append({
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
            "fixed_shifts": fixed_shifts
        })
        
    return legacy_emps

@app.post("/api/employees")
def update_employees(employees: List[Employee]):
    # This endpoint gets triggered by the legacy layout on app.js when saving config.
    # Instead of wiping the DB, we just update or reactivate properties.
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
                turnos_fijos=json.dumps(e.fixed_shifts)
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
                turnos_fijos=json.dumps(e.fixed_shifts)
            )
            # Fetch new ID in case it was created without activo
            if not e.activo:
                added = plan_db.get_conn().execute("SELECT id FROM empleados WHERE nombre=?", (e.name,)).fetchone()
                if added:
                    plan_db.remove_empleado(added["id"])
    return {"status": "Updated"}

@app.get("/api/config")
def get_config():
    db = load_db()
    return db.get("config", {})

@app.post("/api/config")
def update_config(config: Config):
    db = load_db()
    db["config"] = config.dict()
    save_db(db)
    return {"status": "Updated"}

@app.post("/api/solve")
def solve_schedule(request: SolverRequest):
    db = load_db()
    
    # Get History (List of past schedules)
    history_list = db.get("history_log", [])
    if not isinstance(history_list, list):
        history_list = []
        
    # SIEMPRE leer empleados desde SQLite, ignorando lo que manda el frontend.
    # La variable 'employees' en app.js es un 'let' que nunca vive en window,
    # así que planillas_ui.js no puede actualizarla. La fuente de verdad es la DB.
    unified_emps = plan_db.get_empleados(solo_activos=True)
    employees_data = []
    for e in unified_emps:
        try:
            fixed_shifts = json.loads(e.get("turnos_fijos", "{}")) if e.get("turnos_fijos") else {}
        except (json.JSONDecodeError, TypeError):
            print(f"/api/solve: turnos_fijos inválido para {e.get('nombre', '<sin_nombre>')}")
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
        metadata["history_reference_name"] = history_context["reference_name"]
        metadata["history_reference_week_start"] = history_context["reference_week_start"]
        metadata["history_range_start_name"] = history_context["range_start_name"]
        metadata["history_range_start_week_start"] = history_context["range_start_week_start"]
        metadata["history_range_end_name"] = history_context["range_end_name"]
        metadata["history_range_end_week_start"] = history_context["range_end_week_start"]
        metadata["history_women_reference_name"] = history_context["women_reference_name"]
        metadata["history_context_label"] = history_context["label"]
        metadata["history_target_week_start"] = request.target_week_start
        metadata["special_days"] = special_days

    # Save last result for Export (if feasible or even partial)
    # We save it to DB so export_excel can read it
    if result.get("schedule"):
        db["last_result"] = result
        save_db(db)
    
    return result

@app.get("/api/history")
def get_history():
    db = load_db()
    return db.get("history_log", [])

@app.get("/api/rotacion-domingos")
def get_sunday_rotation():
    """Devuelve la cola de rotación para los domingos basándose en el historial."""
    db = load_db()
    history_list = db.get("history_log", [])
    
    unified_emps = plan_db.get_empleados(solo_activos=True)
    eligible = []
    for e in unified_emps:
        name = e.get("nombre", "")
        # Filter out Jefe de Pista as they don't rotate on Sundays normally
        if not e.get("es_jefe_pista", False):
            eligible.append(name)
        
    last_sunday_off = {}
    for idx, entry in enumerate(history_list):
        sched = entry.get('schedule', {})
        if isinstance(sched, str):
            try: sched = json.loads(sched)
            except json.JSONDecodeError:
                print(f"/api/rotacion-domingos: schedule JSON inválido en historial idx={idx}")
                sched = {}
            
        for emp_name, days in sched.items():
            if isinstance(days, dict) and days.get('Dom') in ['OFF', 'VAC', 'PERM'] and emp_name in eligible:
                last_sunday_off[emp_name] = idx

    # Sort: workers who had Sunday OFF least recently go first. (-1 means never had it off)
    # The first person in the queue is the one who *most deserves* to have Sunday OFF this week.
    # The last people are the ones who *must work* this Sunday.
    rotation_queue = sorted(eligible, key=lambda e: last_sunday_off.get(e, -1))
    
    result = []
    for emp_name in rotation_queue:
        weeks_since_off = "Sin registrar"
        if emp_name in last_sunday_off:
            weeks_ago = len(history_list) - 1 - last_sunday_off[emp_name]
            weeks_since_off = f"Hace {weeks_ago} sem" if weeks_ago > 0 else "La sem pasada"
            
        result.append({
            "name": emp_name,
            "last_off": weeks_since_off,
            "priority": "Alta (Libre Próximo)" if result == [] else "En cola" # simple tag
        })
        
    # Let's fix priority tagging
    for i, res in enumerate(result):
        if i == 0: res["priority"] = "Próximo a descansar"
        elif i < 3: res["priority"] = "En Espera Corta"
        else: res["priority"] = "Le toca trabajar"
        
    return result

@app.post("/api/history")
def save_history(entry: HistoryEntry):
    db = load_db()
    history_list = db.get("history_log", [])
    if not isinstance(history_list, list): history_list = []
    
    # Add new entry
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
    
    # Limit history size if needed, user requested manual deletion so maybe high limit
    if len(history_list) > 50:
        history_list = history_list[-50:]
        
    db["history_log"] = history_list
    
    # Update Sunday Rotation Queue if present (persist logic state)
    if "config" not in db: db["config"] = {}
    if entry.next_sunday_rotation_queue is not None:
        db["config"]["sunday_rotation_queue"] = entry.next_sunday_rotation_queue
    elif entry.next_sunday_cycle_index is not None:
        # Legacy fallback
        db["config"]["sunday_cycle_index"] = entry.next_sunday_cycle_index
        
    save_db(db)
    return {"status": "Saved", "history_len": len(history_list)}

@app.delete("/api/history/{index}")
def delete_history_item(index: int):
    db = load_db()
    history_list = db.get("history_log", [])
    
    if 0 <= index < len(history_list):
        history_list.pop(index)
        db["history_log"] = history_list
        save_db(db)
        return {"status": "Deleted"}
    raise HTTPException(status_code=404, detail="Index out of bounds")

@app.patch("/api/history/{index}")
def update_history_item(index: int, entry: HistoryEntry):
    db = load_db()
    history_list = db.get("history_log", [])
    
    if 0 <= index < len(history_list):
        # Update specific fields
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


@app.post("/api/history/{index}/reassign_tasks")
def reassign_history_tasks(index: int):
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

def format_shift_code(code: str) -> str:
    """
    Converts internal shift code (e.g., 'T12_14-22') to readable 12h format 
    (e.g., '02:00 PM - 10:00 PM').
    """
    normalized = horario_db.normalize_manual_shift_code(code) or code

    if not normalized or normalized == "OFF": return "LIBRE"
    if normalized == "VAC": return "VACACIONES"
    if normalized == "PERM": return "PERMISO"
    
    # Check for split shift first (e.g. Q1_05-11+17-20)
    if "+" in normalized:
        parts = normalized.split("_")
        if len(parts) > 1:
            times = parts[1].split("+") # ['05-11', '17-20']
            readable_times = []
            for t in times:
                readable_times.append(_format_time_range(t))
            return " / ".join(readable_times)
    
    # Standard Shift (Code_Start-End)
    parts = normalized.split("_")
    if len(parts) > 1:
        return _format_time_range(parts[1])
        
    return normalized

def _format_time_range(time_range: str) -> str:
    # time_range ex: "14-22" or "06-16"
    try:
        start_s, end_s = time_range.split("-")
        start_h = int(start_s)
        end_h = int(end_s)
        
        # Handle > 24 (next day)
        start_dt = datetime.time(start_h % 24, 0)
        end_dt = datetime.time(end_h % 24, 0)
        
        start_str = start_dt.strftime("%I:%M %p")
        end_str = end_dt.strftime("%I:%M %p")
        
        return f"{start_str} - {end_str}"
    except (ValueError, TypeError, AttributeError):
        return time_range


EXCEL_EMPLOYEE_PALETTE = [
    "4D93D9",
    "FF0000",
    "61CBF3",
    "663300",
    "D86DCD",
    "153D64",
    "8ED973",
    "D9EAD3",
    "BFBFBF",
    "F1A983",
    "F9E79F",
    "D6E4F0",
]
EXCEL_EMPLOYEE_COLOR_MAP = {
    "Angel": "4D93D9",
    "Eligio": "FF0000",
    "Ileana": "61CBF3",
    "Jeison": "663300",
    "Jensy": "D86DCD",
    "Keilor": "153D64",
    "Maikel": "8ED973",
    "Alejandro": "D9EAD3",
    "Randall": "BFBFBF",
    "Steven": "F1A983",
    "Tomas": "F9E79F",
    "Refuerzo": "D6E4F0",
}
EXCEL_EMPLOYEE_FONT_COLOR_MAP = {
    "Eligio": "FFFFFF",
}
EXCEL_LIBRE_FILL = "FFFF00"


def _excel_font_color_for_fill(hex_color: str) -> str:
    color = (hex_color or "").strip().lstrip("#")
    if len(color) == 8:
        color = color[2:]
    if len(color) != 6:
        return "000000"

    try:
        red = int(color[0:2], 16)
        green = int(color[2:4], 16)
        blue = int(color[4:6], 16)
    except ValueError:
        return "000000"

    brightness = (red * 299 + green * 587 + blue * 114) / 1000
    return "FFFFFF" if brightness < 145 else "000000"


def _normalize_excel_task_text(task_text: str) -> str:
    if task_text is None:
        return ""

    text = str(task_text).strip()
    replacements = {
        "â†‘AM": "↑",
        "â†“PM": "↓",
        "↑AM": "↑",
        "↓PM": "↓",
        "↑ AM": "↑",
        "↓ PM": "↓",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return " ".join(text.split())


def _build_excel_task_text(task_text: str, shift_code: str) -> str:
    text = _normalize_excel_task_text(task_text)
    if not text:
        return ""

    if "↑" not in text and "↓" not in text:
        hours = sorted(horario_db.get_shift_hours_set(shift_code))
        if hours:
            text = f"{text} {'↑' if hours[0] < 12 else '↓'}"

    return text


def _task_style_key(task_text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(task_text or ""))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()
    if "banos" in normalized:
        return "banos"
    if "tanques" in normalized:
        return "tanques"
    if "oficina" in normalized:
        return "oficina"
    return ""


def _build_validation_rules_impl(special_days=None):
    db = load_db()
    employees = db.get("employees", [])
    normalized_special_days = _normalize_special_days(special_days)

    from scheduler_engine import DAYS

    active_count = 0
    for e in employees:
        if e.get('is_refuerzo', False) or e.get('name') == 'Refuerzo':
            continue
        fixed = e.get('fixed_shifts', {})
        all_absent = all(fixed.get(d) in ['VAC', 'PERM'] for d in DAYS)
        if not all_absent:
            active_count += 1

    standard_mode = active_count >= 10

    from scheduler_engine import (
        SHIFTS,
        HOURS,
        coverage_bounds,
        effective_coverage_bounds,
        get_allowed_shifts_for_day,
        get_effective_day_mode,
        get_overstaff_policy_for_days,
        ensure_manual_shift_code,
        sync_refuerzo_custom_shift,
    )
    sync_refuerzo_custom_shift(db.get("config", {}))
    ensure_manual_shift_code(7, 12)

    bounds = {}
    max_bounds = {}
    soft_bounds = {}
    day_allowed_shifts = {}
    day_modes = {}
    overstaff_policy = get_overstaff_policy_for_days(normalized_special_days)
    for d in DAYS:
        bounds[d] = {}
        max_bounds[d] = {}
        soft_bounds[d] = {}
        day_mode = get_effective_day_mode(d, normalized_special_days)
        day_modes[d] = day_mode
        day_allowed_shifts[d] = get_allowed_shifts_for_day(d, standard_mode, normalized_special_days)
        for h in HOURS:
            mn, _ = coverage_bounds(h, d, standard_mode, special_day_mode=day_mode)
            _, effective_mx = effective_coverage_bounds(h, d, standard_mode, special_day_mode=day_mode)
            bounds[d][h] = mn
            max_bounds[d][h] = effective_mx

            if day_mode == "closed":
                soft_bounds[d][h] = 0
            elif day_mode in {"sunday_like", "holy_thursday"}:
                soft_bounds[d][h] = mn
            else:
                if 7 <= h <= 10 or 17 <= h <= 19:
                    soft_bounds[d][h] = 4
                elif h == 6:
                    soft_bounds[d][h] = 3
                else:
                    soft_bounds[d][h] = mn

    shift_sets = {s: list(hours) for s, hours in SHIFTS.items()}
    shift_options = [
        {"code": "AUTO", "label": "Auto"},
        {"code": "VAC", "label": "VACACIONES"},
        {"code": "PERM", "label": "PERMISO"},
        {"code": "OFF", "label": "LIBRE"},
    ]
    shift_hours = {"OFF": 0, "VAC": 0, "PERM": 0}

    for s, hours in SHIFTS.items():
        if s in ["OFF", "VAC", "PERM", "AUTO"]:
            continue
        shift_hours[s] = len(hours)
        if s == "N_22-05":
            label = "Noche"
        else:
            parts = s.split("_")
            label = parts[1] if len(parts) > 1 else s
            if "+" in label:
                label = parts[0]
        shift_options.append({"code": s, "label": label})

    return {
        "shift_sets": shift_sets,
        "shift_options": shift_options,
        "shift_hours": shift_hours,
        "bounds": bounds,
        "max_bounds": max_bounds,
        "soft_bounds": soft_bounds,
        "day_allowed_shifts": day_allowed_shifts,
        "sunday_allowed_shifts": day_allowed_shifts.get("Dom", []),
        "special_days": normalized_special_days,
        "day_modes": day_modes,
        "overstaff_policy": overstaff_policy,
        "standard_mode": standard_mode,
        "active_employees": active_count
    }

@app.get("/api/validation_rules")
def get_validation_rules():
    return _build_validation_rules_impl({})

    db = load_db()
    employees = db.get("employees", [])
    
    # Calculate standard_mode identical to scheduler_engine
    from scheduler_engine import DAYS
    active_count = 0
    for e in employees:
        if e.get('is_refuerzo', False) or e.get('name') == 'Refuerzo':
            continue
        fixed = e.get('fixed_shifts', {})
        all_absent = all(fixed.get(d) in ['VAC', 'PERM'] for d in DAYS)
        if not all_absent:
            active_count += 1
            
    standard_mode = active_count >= 10
    
    from scheduler_engine import (
        SHIFTS,
        HOURS,
        coverage_bounds,
        effective_coverage_bounds,
        get_overstaff_policy,
        ensure_manual_shift_code,
        sync_refuerzo_custom_shift,
    )
    sync_refuerzo_custom_shift(db.get("config", {}))
    ensure_manual_shift_code(7, 12)
    
    # Precompute coverage matrix bounds: { "Dom": { "5": 2, "6": 2... } }
    bounds = {}
    max_bounds = {}
    soft_bounds = {}  # Desired optimal coverage (for yellow warnings)
    overstaff_policy = get_overstaff_policy()
    for d in DAYS:
        bounds[d] = {}
        max_bounds[d] = {}
        soft_bounds[d] = {}
        for h in HOURS:
            mn, _ = coverage_bounds(h, d, standard_mode)
            _, effective_mx = effective_coverage_bounds(h, d, standard_mode)
            bounds[d][h] = mn
            max_bounds[d][h] = effective_mx
            
            # Soft targets (desired, not strictly enforced)
            if d == "Dom" and standard_mode:
                # Exact puzzle — no slack, soft = hard
                soft_bounds[d][h] = mn
            elif d == "Dom":
                soft_bounds[d][h] = mn  # No specific soft targets on short-staffed Sunday
            else:
                # Weekdays: peak hours have soft target of 4
                if 7 <= h <= 10 or 17 <= h <= 19:
                    soft_bounds[d][h] = 4
                elif h == 6:
                    soft_bounds[d][h] = 3
                else:
                    soft_bounds[d][h] = mn  # Same as hard
            
    # Shift sets list conversion
    shift_sets = {s: list(hours) for s, hours in SHIFTS.items()}
    
    shift_options = [
        {"code": "AUTO", "label": "Auto"},
        {"code": "VAC", "label": "VACACIONES"},
        {"code": "PERM", "label": "PERMISO"},
        {"code": "OFF", "label": "LIBRE"},
    ]
    shift_hours = {
        "OFF": 0, "VAC": 0, "PERM": 0
    }
    if standard_mode:
        sunday_allowed_shifts = [
            "OFF",
            "VAC",
            "PERM",
            "T1_05-13",
            "T3_07-15",
            "T8_13-20",
            "D4_13-22",
            "T10_15-22",
            "N_22-05",
        ]
    else:
        sunday_allowed_shifts = [
            s for s in SHIFTS.keys()
            if s not in ["AUTO"]
        ]
    
    for s, hours in SHIFTS.items():
        if s in ["OFF", "VAC", "PERM", "AUTO"]: continue
        shift_hours[s] = len(hours)
        if s == "N_22-05":
            label = "Noche"
        else:
            parts = s.split("_")
            label = parts[1] if len(parts) > 1 else s
            if "+" in label: # For Q1_05-11+17-20 -> Q1
                label = parts[0]
        shift_options.append({"code": s, "label": label})
    
    return {
        "shift_sets": shift_sets,
        "shift_options": shift_options,
        "shift_hours": shift_hours,
        "bounds": bounds,
        "max_bounds": max_bounds,
        "soft_bounds": soft_bounds,
        "sunday_allowed_shifts": sunday_allowed_shifts,
        "overstaff_policy": overstaff_policy,
        "standard_mode": standard_mode,
        "active_employees": active_count
    }


@app.post("/api/validation_rules")
def post_validation_rules(request: ValidationRulesRequest):
    return _build_validation_rules_impl(request.special_days)

@app.get("/api/export_excel")
def export_excel(history_index: Optional[int] = None):
    db = load_db()
    
    target_schedule = {}
    target_tasks = {}
    selected_entry = None
    
    if history_index is not None:
        history_list = db.get("history_log", [])
        if 0 <= history_index < len(history_list):
            selected_entry = history_list[history_index]
            target_schedule = selected_entry.get("schedule", {})
            target_tasks = selected_entry.get("daily_tasks", {})
    else:
        last_result = db.get("last_result", {})
        target_schedule = last_result.get("schedule", {})
        target_tasks = last_result.get("daily_tasks", {})
        history_list = db.get("history_log", [])
        if history_list:
            selected_entry = history_list[-1]
    
    if not target_schedule:
        raise HTTPException(status_code=404, detail="No hay horario generado para exportar")

    from openpyxl.styles import Border, Side
    from scheduler_engine import DAYS

    template_path = _template_path
    use_vba = os.path.exists(template_path)
    
    if use_vba:
        wb = openpyxl.load_workbook(template_path, keep_vba=True)
        ws = wb.active
        if ws.title != "Horario":
            ws.title = "Horario"
    else:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Horario"
    
    palette = EXCEL_EMPLOYEE_PALETTE
    thin_border = Border(
        left=Side(style='thin', color='CCCCCC'),
        right=Side(style='thin', color='CCCCCC'),
        top=Side(style='thin', color='CCCCCC'),
        bottom=Side(style='thin', color='CCCCCC')
    )
    
    week_dates = None
    if selected_entry:
        week_dates = selected_entry.get("week_dates")
        if not week_dates:
            meta = selected_entry.get("metadata", {})
            if isinstance(meta, str):
                import json as _json
                try:
                    meta = _json.loads(meta)
                except _json.JSONDecodeError:
                    if history_index is not None:
                        print(f"export_excel: metadata JSON invalido en history_index={history_index}")
                    meta = {}
            week_dates = meta.get("week_dates")
    current_row = 1
    if week_dates:
        date_font = Font(bold=True, color="2F5496", size=10)
        for day_idx, day in enumerate(DAYS, start=2):
            cell = ws.cell(row=current_row, column=day_idx, value=week_dates.get(day, ""))
            cell.number_format = "d/m/yyyy"
            cell.font = date_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
        current_row += 1
    
    header_row = current_row
    headers = ["Colaborador"] + DAYS + ["Horas"]
    for col_idx, header in enumerate(headers, start=1):
        ws.cell(row=header_row, column=col_idx, value=header)
    header_fill = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    
    for cell in ws[header_row]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    emp_names = list(target_schedule.keys())
    emp_colors = {}
    fallback_index = 0
    for name in emp_names:
        if name in EXCEL_EMPLOYEE_COLOR_MAP:
            emp_colors[name] = EXCEL_EMPLOYEE_COLOR_MAP[name]
        else:
            emp_colors[name] = palette[fallback_index % len(palette)]
            fallback_index += 1
    first_emp_row = header_row + 1
    
    for idx, name in enumerate(emp_names):
        shifts = target_schedule[name]
        row_data = [name]
        total_hours = 0
        
        for d in DAYS:
            s_code = shifts.get(d, "OFF")
            readable_shift = format_shift_code(s_code)
            row_data.append(readable_shift)
            
            # Calculate hours
            hours = len(horario_db.get_shift_hours_set(s_code))
            total_hours += hours
            
        row_data.append(total_hours)
        current_data_row = first_emp_row + idx
        for col_idx, value in enumerate(row_data, start=1):
            ws.cell(row=current_data_row, column=col_idx, value=value)

        color = emp_colors[name]
        row_fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
        row_font_color = EXCEL_EMPLOYEE_FONT_COLOR_MAP.get(name, _excel_font_color_for_fill(color))
        
        for col_idx in range(1, len(row_data) + 1):
            cell = ws.cell(row=current_data_row, column=col_idx)
            cell.border = thin_border
            cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
            
            if col_idx == 1:
                cell.fill = row_fill
                cell.font = Font(bold=True, size=11, color=row_font_color)
                cell.alignment = Alignment(vertical="center", horizontal="left")
            else:
                cell.fill = row_fill
                cell.font = Font(
                    bold=(col_idx == len(row_data)),
                    size=11 if col_idx == len(row_data) else 10,
                    color=row_font_color,
                )
                
                s_code = shifts.get(DAYS[col_idx - 2], "OFF") if col_idx <= 8 else None
                if s_code == "OFF":
                    cell.fill = PatternFill(start_color=EXCEL_LIBRE_FILL, end_color=EXCEL_LIBRE_FILL, fill_type="solid")
                    cell.font = Font(color="999999", italic=True, size=11 if col_idx == len(row_data) else 10)
                elif s_code == "VAC":
                    cell.fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
                    cell.font = Font(color="006100", bold=True)
                elif s_code == "PERM":
                    cell.fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
                    cell.font = Font(color="9A3412", bold=True)
        
    ws.column_dimensions["A"].width = 18
    for col_idx in range(2, 9):
        col_letter = openpyxl.utils.get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = 20
    ws.column_dimensions[openpyxl.utils.get_column_letter(9)].width = 8
    
    formato_col = 11  # Column K
    
    fmt_header = ws.cell(row=header_row, column=formato_col, value="FORMATO")
    fmt_header.fill = PatternFill(start_color="2F5496", end_color="2F5496", fill_type="solid")
    fmt_header.font = Font(bold=True, color="FFFFFF", size=11)
    fmt_header.alignment = Alignment(horizontal="center", vertical="center")
    fmt_header.border = thin_border
    
    for idx, name in enumerate(emp_names):
        fmt_row = first_emp_row + idx
        color = emp_colors[name]
        fmt_cell = ws.cell(row=fmt_row, column=formato_col, value=name)
        fmt_cell.fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
        fmt_cell.font = Font(bold=True, size=11, color=_excel_font_color_for_fill(color))
        fmt_cell.alignment = Alignment(vertical="center", horizontal="left")
        fmt_cell.border = thin_border
    
    libre_row = first_emp_row + len(emp_names)
    libre_cell = ws.cell(row=libre_row, column=formato_col, value="LIBRE")
    libre_cell.fill = PatternFill(start_color=EXCEL_LIBRE_FILL, end_color=EXCEL_LIBRE_FILL, fill_type="solid")
    libre_cell.font = Font(color="999999", italic=True, size=11)
    libre_cell.alignment = Alignment(vertical="center", horizontal="left")
    libre_cell.border = thin_border
    
    ws.column_dimensions[openpyxl.utils.get_column_letter(formato_col)].width = 18

    separator_row = ws.max_row + 2
    
    ws.cell(row=separator_row, column=1, value="OBLIGACIONES / LIMPIEZA")
    title_cell = ws.cell(row=separator_row, column=1)
    title_cell.font = Font(bold=True, size=13, color="2F5496")
    title_cell.alignment = Alignment(horizontal="left", vertical="center")
    ws.merge_cells(start_row=separator_row, start_column=1, end_row=separator_row, end_column=9)
    
    task_header_row = separator_row + 1
    task_headers = ["Colaborador"] + DAYS
    for col_idx, header in enumerate(task_headers, 1):
        cell = ws.cell(row=task_header_row, column=col_idx, value=header)
        cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        cell.font = Font(bold=True, color="FFFFFF", size=10)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border
    
    for idx, name in enumerate(emp_names):
        emp_tasks = target_tasks.get(name, {})
        task_row_num = task_header_row + 1 + idx
        color = emp_colors[name]
        name_fill = PatternFill(start_color=color, end_color=color, fill_type="solid")
        
        name_cell = ws.cell(row=task_row_num, column=1, value=name)
        name_cell.fill = name_fill
        name_cell.font = Font(bold=True, size=10, color=_excel_font_color_for_fill(color))
        name_cell.alignment = Alignment(vertical="center", horizontal="left")
        name_cell.border = thin_border
        
        for d_idx, d in enumerate(DAYS):
            task = emp_tasks.get(d)
            shift_code = target_schedule.get(name, {}).get(d, "OFF")
            col = d_idx + 2
            
            if task:
                task_text = _build_excel_task_text(task, shift_code)
                cell = ws.cell(row=task_row_num, column=col, value=task_text)
                style_key = _task_style_key(task_text)
                
                if style_key == "banos":
                    cell.fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
                    cell.font = Font(color="B45309", bold=True, size=10)
                elif style_key == "tanques":
                    cell.fill = PatternFill(start_color="D6E4F0", end_color="D6E4F0", fill_type="solid")
                    cell.font = Font(color="1D4ED8", bold=True, size=10)
                elif style_key == "oficina":
                    cell.fill = PatternFill(start_color="FADBD8", end_color="FADBD8", fill_type="solid")
                    cell.font = Font(color="BE185D", bold=True, size=10)
                else:
                    cell.font = Font(size=10)
            else:
                cell = ws.cell(row=task_row_num, column=col, value="—")
                cell.font = Font(color="CCCCCC", size=10)
            
            cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
            cell.border = thin_border

    # Save to temp
    suffix = ".xlsm" if use_vba else ".xlsx"
    export_base_name = "horario"
    if history_index is not None:
        export_base_name = _get_export_base_name(selected_entry, f"historial_{history_index + 1}")
    filename = f"{export_base_name}{suffix}"
    
    # Save a local backup to EXPORT_DIR
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    local_filename = f"{export_base_name}_{timestamp}{suffix}"
    local_path = os.path.join(EXPORT_DIR, local_filename)
    wb.save(local_path)
    
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    wb.save(tmp.name)
    tmp.close()
    wb.close()
    
    return FileResponse(tmp.name, filename=filename)

@app.post("/api/export_image")
def export_image(req: ImageExportRequest):
    import base64
    try:
        # data:image/png;base64,...
        header, encoded = req.image_data.split(",", 1)
        data = base64.b64decode(encoded)
        
        stem, ext = _build_export_filename_parts(req.filename, default_ext=".png", fallback="horario")
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{stem}_{timestamp}{ext}"
        file_path = os.path.join(EXPORT_DIR, filename)
        
        with open(file_path, "wb") as f:
            f.write(data)
            
        return {"status": "success", "file": filename, "path": file_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==============================================================================
# PLANILLAS API ENDPOINTS (Shared with new unified Web UI)
# ==============================================================================

class PlanillaEmpleado(BaseModel):
    nombre: str
    tipo_pago: str
    salario_fijo: Optional[float] = None
    cedula: Optional[str] = None
    correo: Optional[str] = None
    telefono: Optional[str] = None
    fecha_inicio: Optional[str] = None
    aplica_seguro: Optional[int] = 1
    genero: Optional[str] = 'M'
    puede_nocturno: Optional[int] = 1
    forced_libres: Optional[int] = 0
    forced_quebrado: Optional[int] = 0
    allow_no_rest: Optional[int] = 0
    es_jefe_pista: Optional[int] = 0
    es_practicante: Optional[int] = 0
    strict_preferences: Optional[int] = 0
    activo: Optional[int] = 1
    turnos_fijos: Optional[str] = "{}"

class PlanillaVacacion(BaseModel):
    empleado_id: int
    fecha_inicio: str
    fecha_fin: str
    dias: float
    fecha_reingreso: Optional[str] = None
    notas: Optional[str] = None

class PlanillaTarifas(BaseModel):
    tarifa_diurna: float
    tarifa_nocturna: float
    tarifa_mixta: float
    seguro: float

class PlanillaMes(BaseModel):
    anio: int
    mes: int

class PlanillaSemana(BaseModel):
    mes_id: int
    viernes: str

class PlanillaBoletasRequest(BaseModel):
    semana_nombre: str

class PlanillaImportarHorario(BaseModel):
    horario_id: int
    semana_nombre: str
    sync_empleados: bool = True

@app.get("/api/planillas/empleados")
def get_planillas_empleados(solo_activos: bool = True):
    return plan_db.get_empleados(solo_activos)

@app.post("/api/planillas/empleados")
def add_planilla_empleado(emp: PlanillaEmpleado):
    ok, msg = plan_db.add_empleado(
        emp.nombre, emp.tipo_pago, emp.salario_fijo, 
        cedula=emp.cedula, correo=emp.correo, 
        telefono=emp.telefono, fecha_inicio=emp.fecha_inicio,
        aplica_seguro=emp.aplica_seguro, genero=emp.genero,
        puede_nocturno=emp.puede_nocturno,
        forced_libres=emp.forced_libres, forced_quebrado=emp.forced_quebrado,
        allow_no_rest=emp.allow_no_rest, es_jefe_pista=emp.es_jefe_pista,
        es_practicante=emp.es_practicante,
        strict_preferences=emp.strict_preferences, turnos_fijos=emp.turnos_fijos
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "success", "message": msg}

@app.put("/api/planillas/empleados/{emp_id}")
def update_planilla_empleado(emp_id: int, emp: PlanillaEmpleado):
    plan_db.update_empleado(
        emp_id, nombre=emp.nombre, tipo_pago=emp.tipo_pago, salario_fijo=emp.salario_fijo,
        cedula=emp.cedula, correo=emp.correo, 
        telefono=emp.telefono, fecha_inicio=emp.fecha_inicio,
        aplica_seguro=emp.aplica_seguro, genero=emp.genero,
        puede_nocturno=emp.puede_nocturno,
        forced_libres=emp.forced_libres, forced_quebrado=emp.forced_quebrado,
        allow_no_rest=emp.allow_no_rest, es_jefe_pista=emp.es_jefe_pista,
        es_practicante=emp.es_practicante,
        strict_preferences=emp.strict_preferences, turnos_fijos=emp.turnos_fijos
    )

    # Check if the active status changed
    exist = plan_db.get_conn().execute("SELECT activo FROM empleados WHERE id=?", (emp_id,)).fetchone()
    if exist:
        current_state = exist["activo"]
        new_state = 1 if emp.activo else 0
        if current_state == 1 and new_state == 0:
            plan_db.remove_empleado(emp_id)
        elif current_state == 0 and new_state == 1:
            plan_db.reactivar_empleado(emp_id)

    return {"status": "success"}

@app.delete("/api/planillas/empleados/{emp_id}")
def delete_planilla_empleado(emp_id: int):
    plan_db.delete_empleado(emp_id)
    return {"status": "success"}

@app.get("/api/planillas/vacaciones/{emp_id}")
def get_planillas_vacaciones(emp_id: int):
    vacs = plan_db.get_vacaciones(emp_id)
    emp_data = next((e for e in plan_db.get_empleados(solo_activos=False) if e["id"] == emp_id), None)
    if emp_data:
        fi = emp_data.get("fecha_inicio")
        acumulados = plan_db.calcular_dias_vacaciones(fi) if fi else 0
        tomados = plan_db.total_dias_vacaciones_tomados(emp_id)
        return {
            "registros": vacs,
            "acumulados": acumulados,
            "tomados": tomados,
            "disponibles": max(0, acumulados - tomados)
        }
    return {"registros": vacs}

@app.post("/api/planillas/vacaciones")
def add_planilla_vacacion(vac: PlanillaVacacion):
    plan_db.add_vacacion(
        vac.empleado_id, vac.fecha_inicio, vac.fecha_fin, vac.dias,
        fecha_reingreso=vac.fecha_reingreso, notas=vac.notas
    )
    return {"status": "success"}

@app.delete("/api/planillas/vacaciones/{vac_id}")
def delete_planilla_vacacion(vac_id: int):
    plan_db.delete_vacacion(vac_id)
    return {"status": "success"}

@app.put("/api/planillas/vacaciones/{vac_id}")
def update_planilla_vacacion(vac_id: int, vac: PlanillaVacacion):
    plan_db.update_vacacion(
        vac_id, vac.fecha_inicio, vac.fecha_fin, vac.dias,
        fecha_reingreso=vac.fecha_reingreso, notas=vac.notas
    )
    return {"status": "success"}

# ------------------------------------------------------------------------------
# PERMISOS API
# ------------------------------------------------------------------------------
@app.get("/api/planillas/permisos/{emp_id}")
def get_planillas_permisos(emp_id: int, anio: Optional[int] = None):
    permisos = plan_db.get_permisos_empleado(emp_id, anio=anio)
    if anio:
        conteo = plan_db.get_conteo_permisos_anio(emp_id, anio)
    else:
        conteo = plan_db.get_conteo_permisos_anio(emp_id, datetime.datetime.now().year)
    return {"permisos": permisos, "conteo": conteo}

@app.post("/api/planillas/permisos")
def add_planilla_permiso(perm: PlanillaPermiso):
    permiso_id = plan_db.add_permiso(
        perm.empleado_id, perm.fecha, motivo=perm.motivo, notas=perm.notas
    )
    return {"status": "success", "id": permiso_id}

@app.delete("/api/planillas/permisos/{permiso_id}")
def delete_planilla_permiso(permiso_id: int, restaurar: bool = True):
    plan_db.delete_permiso(permiso_id, restaurar_vacaciones=restaurar)
    return {"status": "success"}

@app.post("/api/planillas/permisos/descontar-vacaciones")
def descontar_permisos_vacaciones(req: DescontarPermisosRequest):
    ok, msg = plan_db.descontar_permisos_de_vacaciones(
        req.empleado_id, req.cantidad, req.anio
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "success", "message": msg}

# ------------------------------------------------------------------------------
# SYNC VACACIONES/PERMISOS → HORARIO (Fixed Shifts)
# ------------------------------------------------------------------------------
@app.post("/api/sync_vac_fixed_shifts")
def sync_vac_fixed_shifts(req: SyncVacPermRequest):
    """Sincroniza vacaciones y permisos activos con los turnos fijos de todos los empleados."""
    emps = plan_db.get_empleados(solo_activos=True)
    updated = []
    for emp in emps:
        shifts = plan_db.sync_vac_perm_to_fixed_shifts(
            emp["nombre"], req.fecha_inicio, req.fecha_fin
        )
        updated.append({"nombre": emp["nombre"], "turnos_fijos": shifts})
    return {"status": "success", "updated": updated}

# ------------------------------------------------------------------------------
# PRÉSTAMOS API
# ------------------------------------------------------------------------------
class PlanillaPrestamo(BaseModel):
    empleado_id: int
    monto_total: float
    pago_semanal: float
    notas: Optional[str] = None

class PrestamoAbono(BaseModel):
    monto: float
    tipo: str = "planilla"
    semana_planilla: Optional[str] = None
    notas: Optional[str] = None


def _find_mes_for_sync(mes_id: Optional[int] = None):
    if mes_id is None:
        return plan_db.get_mes_activo()

    meses = plan_db.get_todos_meses()
    return next((m for m in meses if m["id"] == mes_id), None)


def _sync_prestamo_rebajos_mes(mes_id: Optional[int] = None, mes_data: Optional[dict] = None):
    mes = mes_data or _find_mes_for_sync(mes_id)
    if not mes:
        return {
            "status": "noop",
            "message": "No hay un mes para sincronizar.",
            "created": 0,
            "updated": 0,
            "deleted": 0,
            "skipped": 0,
            "affected_prestamos": 0,
        }

    archivo_path = os.path.join(_planillas_dir, mes["archivo"])
    if not os.path.exists(archivo_path):
        return {
            "status": "noop",
            "message": f"No se encontro el Excel del mes {mes['id']}.",
            "created": 0,
            "updated": 0,
            "deleted": 0,
            "skipped": 0,
            "affected_prestamos": 0,
        }

    semanas = plan_db.get_semanas_del_mes(mes["id"])
    summary = prestamo_sync.sync_rebajos_mes(mes, archivo_path, semanas)
    summary["status"] = "success"
    summary["mes_id"] = mes["id"]
    return summary


def _sync_prestamo_rebajos_todos():
    meses = plan_db.get_todos_meses()
    if not meses:
        return {
            "status": "noop",
            "message": "No hay meses registrados para sincronizar.",
            "created": 0,
            "updated": 0,
            "deleted": 0,
            "skipped": 0,
            "affected_prestamos": 0,
            "meses_sincronizados": 0,
        }

    total = {
        "status": "success",
        "created": 0,
        "updated": 0,
        "deleted": 0,
        "skipped": 0,
        "affected_prestamos": 0,
        "meses_sincronizados": 0,
    }
    for mes in meses:
        summary = _sync_prestamo_rebajos_mes(mes_data=mes)
        if summary["status"] != "success":
            continue
        total["created"] += summary["created"]
        total["updated"] += summary["updated"]
        total["deleted"] += summary["deleted"]
        total["skipped"] += summary["skipped"]
        total["affected_prestamos"] += summary["affected_prestamos"]
        total["meses_sincronizados"] += 1

    if total["meses_sincronizados"] == 0:
        total["status"] = "noop"
        total["message"] = "No se encontro ningun Excel de planilla para sincronizar."
    return total


@app.post("/api/planillas/prestamos/sync-planilla-rebajos")
def sync_planilla_rebajos_prestamo(mes_id: Optional[int] = None):
    if mes_id is None:
        return _sync_prestamo_rebajos_todos()
    return _sync_prestamo_rebajos_mes(mes_id=mes_id)


@app.get("/api/planillas/prestamos")
def get_all_prestamos_activos():
    prestamos = plan_db.get_todos_prestamos_activos()
    return prestamos

@app.get("/api/planillas/prestamos/{emp_id}")
def get_prestamos_emp(emp_id: int, solo_activos: bool = False):
    prestamos = plan_db.get_prestamos_empleado(emp_id, solo_activos=solo_activos)
    return prestamos

@app.post("/api/planillas/prestamos")
def add_prestamo(req: PlanillaPrestamo):
    pid = plan_db.add_prestamo(
        req.empleado_id, req.monto_total, req.pago_semanal, notas=req.notas
    )
    return {"status": "success", "id": pid}

@app.delete("/api/planillas/prestamos/{prestamo_id}")
def delete_prestamo(prestamo_id: int):
    plan_db.delete_prestamo(prestamo_id)
    return {"status": "success"}

@app.get("/api/planillas/prestamos/{prestamo_id}/abonos")
def get_abonos_prestamo(prestamo_id: int):
    abonos = plan_db.get_abonos(prestamo_id)
    prestamo = plan_db.get_prestamo(prestamo_id)
    return {"abonos": abonos, "prestamo": prestamo}

@app.post("/api/planillas/prestamos/{prestamo_id}/abono")
def add_abono_prestamo(prestamo_id: int, req: PrestamoAbono):
    abono_id = plan_db.add_abono(
        prestamo_id, req.monto, tipo=req.tipo,
        semana_planilla=req.semana_planilla, notas=req.notas
    )
    prestamo = plan_db.get_prestamo(prestamo_id)
    return {"status": "success", "id": abono_id, "nuevo_saldo": prestamo["saldo"], "estado": prestamo["estado"]}

# ------------------------------------------------------------------------------
# LIQUIDACIÓN — Cálculo automático según Ley Costarricense
# ------------------------------------------------------------------------------
@app.get("/api/planillas/liquidacion/{emp_id}")
def calcular_liquidacion(emp_id: int):
    """Calcula todos los rubros de liquidación para un empleado.
    
    - Vacaciones: días disponibles × tarifa_diurna × 8hrs
    - Aguinaldo proporcional: salarios brutos del período ÷ 12
    - Cesantía (Art. 29 CT CR): según tabla de antigüedad
    - Preaviso: 1 mes de salario promedio si >1 año
    """
    from datetime import date, timedelta
    import math

    emp_data = next((e for e in plan_db.get_empleados(solo_activos=False) if e["id"] == emp_id), None)
    if not emp_data:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")

    nombre = emp_data.get("nombre", "")
    fi = emp_data.get("fecha_inicio")
    tarifas = plan_db.get_tarifas()
    tarifa_diurna = tarifas.get("tarifa_diurna", 0)

    # ── 1. VACACIONES ──
    acumulados = plan_db.calcular_dias_vacaciones(fi) if fi else 0
    tomados = plan_db.total_dias_vacaciones_tomados(emp_id)
    vac_dias = max(0, acumulados - tomados)
    vac_monto = vac_dias * tarifa_diurna * 8  # jornada ordinaria diurna

    # ── 2. ANTIGÜEDAD ──
    antiguedad_dias = 0
    antiguedad_anios = 0
    if fi:
        try:
            inicio = datetime.datetime.strptime(fi, "%Y-%m-%d").date()
            antiguedad_dias = (date.today() - inicio).days
            antiguedad_anios = antiguedad_dias / 365.25
        except (ValueError, TypeError):
            print(f"liquidacion_preview: fecha_inicio inválida para empleado_id={emp_id}: {fi}")

    # ── 3. SALARIO PROMEDIO MENSUAL (de planillas reales) ──
    anio_actual = date.today().year
    salario_total_anual = 0.0
    semanas_con_datos = 0

    for anio in [anio_actual - 1, anio_actual]:
        meses = plan_db.get_meses_del_anio(anio)
        mes_activo = plan_db.get_mes_activo()
        if mes_activo and mes_activo['anio'] == anio:
            meses.append(mes_activo)

        for mes_data in meses:
            archivo = mes_data['archivo']
            archivo_path = os.path.join(_planillas_dir, archivo)
            if not os.path.exists(archivo_path):
                continue
            try:
                wb = openpyxl.load_workbook(archivo_path, data_only=True)
                for sheet_name in wb.sheetnames:
                    if sheet_name.startswith("Semana "):
                        ws = wb[sheet_name]
                        for row in range(5, ws.max_row + 1):
                            name_cell = ws.cell(row=row, column=1).value
                            if name_cell and isinstance(name_cell, str) and name_cell.strip() == nombre:
                                # Find salario bruto column
                                for col in range(2, min(ws.max_column + 1, 20)):
                                    header = ws.cell(row=4, column=col).value
                                    if header and isinstance(header, str) and "bruto" in header.lower():
                                        val = ws.cell(row=row, column=col).value
                                        if val and isinstance(val, (int, float)):
                                            salario_total_anual += val
                                            semanas_con_datos += 1
                                        break
                wb.close()
            except (OSError, ValueError, KeyError):
                print(f"liquidacion_preview: no se pudo leer archivo de planilla {archivo}")

    # Promedio mensual = total / meses con datos (aprox 4 semanas = 1 mes)
    meses_con_datos = max(1, semanas_con_datos / 4.33)
    salario_promedio_mensual = salario_total_anual / meses_con_datos if meses_con_datos > 0 else 0

    # ── 4. AGUINALDO PROPORCIONAL ──
    # En CR: aguinaldo = salarios de dic anterior a nov actual ÷ 12
    aguinaldo_monto = salario_total_anual / 12.0 if salario_total_anual > 0 else 0

    # ── 5. CESANTÍA (Art. 29 Código de Trabajo CR) ──
    # Solo aplica a despido sin justa causa
    cesantia_dias = 0
    if antiguedad_dias >= 90:  # Mínimo 3 meses
        if antiguedad_dias < 180:       # 3-6 meses
            cesantia_dias = 7
        elif antiguedad_dias < 365:     # 6-12 meses
            cesantia_dias = 14
        else:
            # Más de 1 año: tabla progresiva
            anios_completos = int(antiguedad_anios)
            if anios_completos == 1:
                cesantia_dias = 19.5
            elif anios_completos == 2:
                cesantia_dias = 19.5 + 19.5
            elif anios_completos == 3:
                cesantia_dias = 19.5 + 19.5 + 20
            elif anios_completos == 4:
                cesantia_dias = 19.5 + 19.5 + 20 + 20
            elif anios_completos == 5:
                cesantia_dias = 19.5 + 19.5 + 20 + 20 + 20.5
            elif anios_completos == 6:
                cesantia_dias = 19.5 + 19.5 + 20 + 20 + 20.5 + 21
            elif anios_completos >= 7:
                cesantia_dias = 19.5 + 19.5 + 20 + 20 + 20.5 + 21 + 21.24
            if anios_completos >= 8:
                cesantia_dias = 19.5 + 19.5 + 20 + 20 + 20.5 + 21 + 21.24 + 21.5
            # Máximo legal: ~22 días por año, tope 8 años

    salario_diario = salario_promedio_mensual / 30 if salario_promedio_mensual > 0 else 0
    cesantia_monto = cesantia_dias * salario_diario

    # ── 6. PREAVISO ──
    # >1 año: 1 mes; 3-6 meses: 1 semana; 6-12 meses: 15 días
    preaviso_monto = 0
    if antiguedad_dias >= 365:
        preaviso_monto = salario_promedio_mensual  # 1 mes
    elif antiguedad_dias >= 180:
        preaviso_monto = salario_promedio_mensual / 2  # 15 días
    elif antiguedad_dias >= 90:
        preaviso_monto = salario_promedio_mensual / 4.33  # 1 semana

    return {
        "emp_id": emp_id,
        "nombre": nombre,
        "fecha_inicio": fi,
        "antiguedad_anios": round(antiguedad_anios, 1),
        "tarifa_diurna": tarifa_diurna,
        "vacaciones_dias": vac_dias,
        "vacaciones_monto": round(vac_monto, 2),
        "aguinaldo_monto": round(aguinaldo_monto, 2),
        "cesantia_dias": round(cesantia_dias, 1),
        "cesantia_monto": round(cesantia_monto, 2),
        "preaviso_monto": round(preaviso_monto, 2),
        "salario_promedio_mensual": round(salario_promedio_mensual, 2),
        "total_despido": round(vac_monto + aguinaldo_monto + cesantia_monto + preaviso_monto, 2),
        "total_renuncia": round(vac_monto + aguinaldo_monto, 2),
    }


def calcular_aguinaldo(anio: int):
    """Calcula aguinaldo basado en la tabla salarios_mensuales de la BD."""
    MES_NOMBRES = {1:'Enero',2:'Febrero',3:'Marzo',4:'Abril',5:'Mayo',6:'Junio',
                   7:'Julio',8:'Agosto',9:'Septiembre',10:'Octubre',11:'Noviembre',12:'Diciembre'}

    desglose_rows = plan_db.get_salarios_anio_desglose(anio)
    if not desglose_rows:
        return {"status": "error", "message": f"No hay salarios registrados para {anio}", "data": []}

    # Group by employee
    emp_data = {}
    for row in desglose_rows:
        eid = row['empleado_id']
        if eid not in emp_data:
            emp_data[eid] = {
                'nombre': row['empleado_nombre'],
                'total_bruto': 0.0,
                'desglose': []
            }
        mes_label = MES_NOMBRES.get(row['mes'], f'Mes {row["mes"]}')
        emp_data[eid]['total_bruto'] += row['total_bruto']
        emp_data[eid]['desglose'].append({
            'mes': mes_label,
            'bruto': round(row['total_bruto'], 2)
        })

    # Get employee info from DB
    emps = plan_db.get_empleados(solo_activos=False)
    emp_lookup = {e['id']: e for e in emps}

    results = []
    total_aguinaldo = 0.0
    meses_set = set()

    for eid, data in emp_data.items():
        emp = emp_lookup.get(eid, {})
        sal_total = data['total_bruto']
        aguinaldo = sal_total / 12.0 if sal_total > 0 else 0.0
        total_aguinaldo += aguinaldo
        for d in data['desglose']:
            meses_set.add(d['mes'])
        results.append({
            "id": eid,
            "nombre": data['nombre'],
            "cedula": emp.get("cedula") or "—",
            "salario_anual": round(sal_total, 2),
            "aguinaldo": round(aguinaldo, 2),
            "desglose_mensual": data['desglose']
        })

    # Also include employees with no salary data
    for emp in emps:
        if emp['id'] not in emp_data:
            results.append({
                "id": emp['id'],
                "nombre": emp['nombre'],
                "cedula": emp.get("cedula") or "—",
                "salario_anual": 0,
                "aguinaldo": 0,
                "desglose_mensual": []
            })

    return {
        "status": "success",
        "data": results,
        "total_aguinaldo": round(total_aguinaldo, 2),
        "meses_evaluados": len(meses_set)
    }


@app.get("/api/planillas/aguinaldo/{anio}")
def get_aguinaldo(anio: int):
    return calcular_aguinaldo(anio)


# ------------------------------------------------------------------------------
# PLANILLAS - GUARDAR SALARIOS
# ------------------------------------------------------------------------------
class SalarioSemanal(BaseModel):
    empleado_id: int
    empleado_nombre: str
    anio: int
    mes: int
    semana: int
    salario_bruto: float

class SalariosLote(BaseModel):
    salarios: list[SalarioSemanal]

@app.post("/api/planillas/salarios")
def guardar_salarios(req: SalariosLote):
    for s in req.salarios:
        plan_db.guardar_salario_semanal(
            s.empleado_id, s.empleado_nombre,
            s.anio, s.mes, s.semana, s.salario_bruto
        )
    return {"status": "success", "count": len(req.salarios)}

@app.post("/api/planillas/sincronizar-aguinaldo/{anio}")
def sincronizar_aguinaldo_anio(anio: int):
    """
    Escanea los Excel (cerrados y activo) para el año dado, lee todas las hojas 
    de semanas y guarda los salarios brutos en la DB para reconstruir el historial.
    """
    meses_a_sincronizar = plan_db.get_meses_del_anio(anio)
    mes_activo = plan_db.get_mes_activo()
    if mes_activo and mes_activo["anio"] == anio:
        if not any(m["archivo"] == mes_activo["archivo"] for m in meses_a_sincronizar):
            meses_a_sincronizar.append(mes_activo)

    # Deduplicar por archivo — evita procesar el mismo Excel dos veces si
    # quedaron registros duplicados de meses en la base de datos.
    seen_archivos = set()
    meses_unicos = []
    for m in meses_a_sincronizar:
        if m["archivo"] not in seen_archivos:
            seen_archivos.add(m["archivo"])
            meses_unicos.append(m)
    meses_a_sincronizar = meses_unicos

    if not meses_a_sincronizar:
        return {"status": "error", "message": f"No se encontraron meses para el año {anio} para sincronizar."}
    
    count = 0
    skipped = []
    errores = []
    tarifas = plan_db.get_tarifas()
    emps = plan_db.get_empleados(solo_activos=False)
    emp_map = {e["nombre"]: e["id"] for e in emps}

    for mes in meses_a_sincronizar:
        archivo_path = os.path.join(_planillas_dir, mes["archivo"])
        if not os.path.exists(archivo_path):
            # Archivo no existe: ignorar silenciosamente (puede ser un mes
            # registrado por error en la DB sin Excel real).
            skipped.append(mes["archivo"])
            continue
            
        try:
            wb = openpyxl.load_workbook(archivo_path, data_only=True)
            for sheet_name in wb.sheetnames:
                if sheet_name.startswith("Semana "):
                    try:
                        sem_num = int(sheet_name.split(" ")[-1])
                    except (ValueError, IndexError):
                        print(f"sync_salarios_historicos: nombre de hoja no estándar '{sheet_name}' en {mes['archivo']}")
                        continue
                    
                    ws = wb[sheet_name]
                    bruto_col = 12 # Default based on rellenar_horas_en_excel logic and template
                    
                    for r in range(5, ws.max_row + 1):
                        name_cell = ws.cell(row=r, column=1).value
                        if name_cell and isinstance(name_cell, str) and name_cell.strip() in emp_map:
                            nombre = name_cell.strip()
                            bruto_val = ws.cell(row=r, column=bruto_col).value
                            if bruto_val and isinstance(bruto_val, (int, float)):
                                plan_db.guardar_salario_semanal(
                                    emp_map[nombre], nombre, anio, mes["mes"], sem_num, bruto_val
                                )
                                count += 1
            wb.close()
        except Exception as e:
            errores.append(f"Error procesando {mes['archivo']}: {str(e)}")

    msg = f"Sincronizados {count} registros de salarios."
    if skipped:
        print(f"Sincronización: {len(skipped)} archivos omitidos (no existen): {skipped}")
    if errores:
        msg += f" ({len(errores)} errores, revisa la consola para detalles)"
        print("Errores de sincronización:", errores)
        
    return {"status": "success", "message": msg, "count": count}


# ------------------------------------------------------------------------------
# PLANILLAS - TARIFAS
# ------------------------------------------------------------------------------
@app.get("/api/planillas/tarifas")
def get_planillas_tarifas():
    return plan_db.get_tarifas()

@app.post("/api/planillas/tarifas")
def update_planillas_tarifas(t: PlanillaTarifas):
    plan_db.set_tarifas(t.tarifa_diurna, t.tarifa_nocturna, t.tarifa_mixta, t.seguro)
    return {"status": "success"}

# ------------------------------------------------------------------------------
# PLANILLAS - MESES & SEMANAS
# ------------------------------------------------------------------------------
@app.get("/api/planillas/meses")
def get_todos_meses():
    meses = plan_db.get_todos_meses()
    for m in meses:
        m["semanas"] = plan_db.get_semanas_del_mes(m["id"])
    return meses

@app.get("/api/planillas/meses/activo")
def get_mes_activo():
    mes = plan_db.get_mes_activo()
    if not mes:
        return {"mes": None, "semanas": []}
    semanas = plan_db.get_semanas_del_mes(mes["id"])
    return {"mes": mes, "semanas": semanas}

@app.post("/api/planillas/meses")
def create_mes(m: PlanillaMes):
    emps = plan_db.get_empleados()
    if not emps:
        raise HTTPException(status_code=400, detail="Agregue empleados antes de crear la planilla.")
    
    # Crear Excel del Mes
    meses_nombres = {
        1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
        5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
        9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
    }
    mes_name = meses_nombres.get(m.mes, str(m.mes))
    
    # Create nested folder structure: Planillas {Anio} / {Mes}
    folder_year = f"Planillas {m.anio}"
    folder_month = mes_name
    rel_folder_path = os.path.join(folder_year, folder_month)
    abs_folder_path = os.path.join(_planillas_dir, rel_folder_path)
    os.makedirs(abs_folder_path, exist_ok=True)
    
    archivo_name = f"Planilla_{mes_name}_{m.anio}.xlsx"
    archivo_rel_path = os.path.join(rel_folder_path, archivo_name).replace("\\", "/")
    archivo_path = os.path.join(abs_folder_path, archivo_name)
    
    # Init Excel
    tarifas = plan_db.get_tarifas()
    pl_module.TARIFA_DIURNA = tarifas["tarifa_diurna"]
    pl_module.TARIFA_NOCTURNA = tarifas["tarifa_nocturna"]
    pl_module.TARIFA_MIXTA = tarifas["tarifa_mixta"]
    
    wb = openpyxl.Workbook()
    pl_module.SAMPLE_EMPS = []
    pl_module.crear_catalogo(wb)
    
    ws_cat = wb["Catalogo"]
    tipo_map = {"tarjeta": "Tarjeta", "efectivo": "Efectivo", "fijo": "Salario Fijo"}
    for i, emp in enumerate(emps):
        r = 5 + i
        pl_module.sc(ws_cat, r, 1, emp["nombre"], pl_module.f_data, pl_module.ROW_1 if i % 2 == 0 else pl_module.ROW_2, pl_module.al_l, pl_module.borde)
        pl_module.sc(ws_cat, r, 2, tipo_map.get(emp["tipo_pago"], emp["tipo_pago"]),
                     pl_module.f_data, pl_module.ROW_1 if i % 2 == 0 else pl_module.ROW_2, pl_module.al_c, pl_module.borde)
        if emp["salario_fijo"]:
            pl_module.sc(ws_cat, r, 3, emp["salario_fijo"],
                         pl_module.f_data, pl_module.ROW_1 if i % 2 == 0 else pl_module.ROW_2, pl_module.al_c, pl_module.borde, pl_module.MONEY)
                         
    pl_module.crear_resumen_mensual(wb)
    if "Sheet" in wb.sheetnames:
        wb.remove(wb["Sheet"])
    wb.save(archivo_path)
    
    # Registrar en DB
    mes_db = plan_db.crear_mes(m.anio, m.mes, archivo_rel_path)
    return {"status": "success", "mes": mes_db}

@app.post("/api/planillas/meses/{mes_id}/cerrar")
def cerrar_mes(mes_id: int):
    plan_db.cerrar_mes(mes_id)
    return {"status": "success"}

@app.post("/api/planillas/semanas")
def agregar_semana(s: PlanillaSemana):
    mes_activo = plan_db.get_mes_activo()
    if not mes_activo or mes_activo["id"] != s.mes_id:
        raise HTTPException(status_code=400, detail="Mes inválido o cerrado.")
        
    archivo_path = os.path.join(_planillas_dir, mes_activo["archivo"])
    if not os.path.exists(archivo_path):
        raise HTTPException(status_code=400, detail=f"No se encontró el Excel: {mes_activo['archivo']}")
        
    viernes_date = datetime.datetime.strptime(s.viernes, "%Y-%m-%d").date()
    
    tarifas = plan_db.get_tarifas()
    pl_module.TARIFA_DIURNA = tarifas["tarifa_diurna"]
    pl_module.TARIFA_NOCTURNA = tarifas["tarifa_nocturna"]
    pl_module.TARIFA_MIXTA = tarifas["tarifa_mixta"]
    
    wb = openpyxl.load_workbook(archivo_path)
    empleados = pl_module.leer_catalogo(wb)
    total_emp = sum(len(v) for v in empleados.values())
    if total_emp == 0:
        raise HTTPException(status_code=400, detail="No hay empleados en el Excel.")
        
    num = pl_module.contar_semanas(wb) + 1
    sem_num = pl_module.num_semana_anual(viernes_date)
    
    nombre_hoja, gran_row, section_totals = pl_module.crear_hoja_semanal(
        wb, num, viernes_date, empleados, seguro=tarifas["seguro"])
    pl_module.crear_resumen_semanal(wb, nombre_hoja, sem_num, viernes_date)
    pl_module.crear_resumen_mensual(wb)
    pl_module.crear_dashboard(wb)
    
    wb.save(archivo_path)
    
    # Save to DB
    plan_db.add_semana(s.mes_id, sem_num, s.viernes)
    semanas = plan_db.get_semanas_del_mes(s.mes_id)
    return {"status": "success", "semanas": semanas}

@app.delete("/api/planillas/semanas/{semana_id}")
def delete_semana(semana_id: int):
    """Elimina una semana de cualquier mes (activo o cerrado).
    
    Busca el mes al que pertenece la semana entre TODOS los meses registrados,
    no solo el activo. Esto permite editar el historial de planillas anteriores.
    """
    # Buscar la semana y su mes en todos los meses registrados
    all_months = plan_db.get_todos_meses()
    target_sem = None
    target_mes = None

    for mes in all_months:
        semanas = plan_db.get_semanas_del_mes(mes["id"])
        found = next((s for s in semanas if s["id"] == semana_id), None)
        if found:
            target_sem = found
            target_mes = mes
            break

    if not target_sem or not target_mes:
        raise HTTPException(status_code=404, detail="Semana no encontrada")

    num_semana = target_sem["num_semana"]
    plan_db.delete_semana(semana_id)

    # Eliminar hojas del Excel si el archivo existe
    archivo_path = os.path.join(_planillas_dir, target_mes["archivo"])
    if os.path.exists(archivo_path):
        try:
            wb = openpyxl.load_workbook(archivo_path)
            sheet_sem = f"Semana {num_semana}"
            sheet_res = f"Res. Sem. {num_semana}"
            if sheet_sem in wb.sheetnames: wb.remove(wb[sheet_sem])
            if sheet_res in wb.sheetnames: wb.remove(wb[sheet_res])
            pl_module.crear_resumen_mensual(wb)
            pl_module.crear_dashboard(wb)
            wb.save(archivo_path)
        except Exception as e:
            print(f"Advertencia al modificar Excel: {e}")

    _sync_prestamo_rebajos_mes(mes_data=target_mes)

    return {"status": "success", "semanas": plan_db.get_semanas_del_mes(target_mes["id"])}


@app.delete("/api/planillas/meses/{mes_id}")
def delete_mes_historial(mes_id: int):
    """Elimina un mes cerrado y todos sus registros. Rechaza meses activos."""
    meses = plan_db.get_todos_meses()
    mes_target = next((m for m in meses if m["id"] == mes_id), None)
    if not mes_target:
        raise HTTPException(status_code=404, detail="Mes no encontrado")
    if not mes_target.get("cerrado"):
        raise HTTPException(status_code=400, detail="Solo se pueden eliminar meses cerrados")

    prestamo_sync.clear_auto_rebajos_mes(mes_id)

    # Intentar borrar el Excel físico (no fatal si falla)
    archivo_path = os.path.join(_planillas_dir, mes_target["archivo"])
    if os.path.exists(archivo_path):
        try:
            os.remove(archivo_path)
        except Exception as e:
            print(f"Advertencia: no se pudo eliminar el archivo Excel: {e}")

    plan_db.delete_mes(mes_id)
    return {"status": "success", "message": f"Mes {mes_id} eliminado"}


@app.post("/api/planillas/meses/{mes_id}/semanas")
def agregar_semana_a_mes_historico(mes_id: int, s: PlanillaSemana):
    """Agrega una semana a cualquier mes (activo o cerrado), para edición del historial.
    
    A diferencia del endpoint /api/planillas/semanas, este no exige que el mes
    sea el activo, permitiendo gestionar semanas en planillas anteriores.
    """
    meses = plan_db.get_todos_meses()
    mes_target = next((m for m in meses if m["id"] == mes_id), None)
    if not mes_target:
        raise HTTPException(status_code=404, detail="Mes no encontrado")

    archivo_path = os.path.join(_planillas_dir, mes_target["archivo"])
    if not os.path.exists(archivo_path):
        raise HTTPException(status_code=400, detail=f"No se encontró el Excel: {mes_target['archivo']}")

    viernes_date = datetime.datetime.strptime(s.viernes, "%Y-%m-%d").date()

    tarifas = plan_db.get_tarifas()
    pl_module.TARIFA_DIURNA = tarifas["tarifa_diurna"]
    pl_module.TARIFA_NOCTURNA = tarifas["tarifa_nocturna"]
    pl_module.TARIFA_MIXTA = tarifas["tarifa_mixta"]

    wb = openpyxl.load_workbook(archivo_path)
    empleados = pl_module.leer_catalogo(wb)
    total_emp = sum(len(v) for v in empleados.values())
    if total_emp == 0:
        raise HTTPException(status_code=400, detail="No hay empleados en el Excel.")

    num = pl_module.contar_semanas(wb) + 1
    sem_num = pl_module.num_semana_anual(viernes_date)

    nombre_hoja, gran_row, section_totals = pl_module.crear_hoja_semanal(
        wb, num, viernes_date, empleados, seguro=tarifas["seguro"])
    pl_module.crear_resumen_semanal(wb, nombre_hoja, sem_num, viernes_date)
    pl_module.crear_resumen_mensual(wb)
    pl_module.crear_dashboard(wb)

    wb.save(archivo_path)

    plan_db.add_semana(mes_id, sem_num, s.viernes)
    semanas = plan_db.get_semanas_del_mes(mes_id)
    return {"status": "success", "semanas": semanas}

@app.get("/api/planillas/horarios-disponibles")
def get_horarios_disponibles():
    horarios = horario_db.get_horarios_generados()
    return {"status": "success", "horarios": horarios}

@app.post("/api/planillas/semanas/importar")
def importar_horario_semana(req: PlanillaImportarHorario):
    mes_activo = plan_db.get_mes_activo()
    if not mes_activo:
        raise HTTPException(status_code=400, detail="No hay un mes activo")
        
    horario = horario_db.get_horario_por_id(req.horario_id)
    if not horario:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
        
    if req.sync_empleados:
        horario_db.sincronizar_empleados_a_planilla()
        
    archivo_path = os.path.join(_planillas_dir, mes_activo["archivo"])
    ok, msg, hours_data = horario_db.rellenar_horas_en_excel(
        archivo_path, req.semana_nombre, horario["horario"]
    )
    
    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    # Store salaries in DB
    try:
        tarifas = plan_db.get_tarifas()
        emps = plan_db.get_empleados(solo_activos=False)
        emp_map = {e["nombre"]: e["id"] for e in emps}
        
        # Get week number from semantic name "Semana X"
        try:
            sem_num = int(req.semana_nombre.split(" ")[-1])
        except (ValueError, IndexError):
            print(f"importar_horario_semana: semana_nombre no parseable '{req.semana_nombre}', usando 0")
            sem_num = 0

        for emp_nombre, h in hours_data.items():
            if emp_nombre in emp_map:
                bruto = h.get("salario_bruto")
                if bruto is None:
                    bruto = (h["diurnas"] * tarifas["tarifa_diurna"]) + \
                            (h["mixtas"] * tarifas["tarifa_mixta"]) + \
                            (h["nocturnas"] * tarifas["tarifa_nocturna"]) + \
                            (h["extra"] * (tarifas["tarifa_diurna"] * 1.5)) # Extra typically 1.5x
                
                plan_db.guardar_salario_semanal(
                    emp_map[emp_nombre], emp_nombre,
                    mes_activo["anio"], mes_activo["mes"], sem_num, bruto
                )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error guardando salarios semanales: {e}")

    return {"status": "success", "message": msg}

@app.post("/api/planillas/meses/{mes_id}/semanas/{semana_nombre}/importar")
def importar_horario_semana_historico(mes_id: int, semana_nombre: str, req: PlanillaImportarHorario):
    """Importa un horario guardado a la hoja de una semana específica de CUALQUIER mes.
    
    A diferencia del endpoint /api/planillas/semanas/importar, este no exige que el mes
    sea el activo, permitiendo rellenar horas en planillas históricas o cerradas.
    """
    meses = plan_db.get_todos_meses()
    mes_target = next((m for m in meses if m["id"] == mes_id), None)
    if not mes_target:
        raise HTTPException(status_code=404, detail="Mes no encontrado")

    horario = horario_db.get_horario_por_id(req.horario_id)
    if not horario:
        raise HTTPException(status_code=404, detail="Horario no encontrado")

    if req.sync_empleados:
        horario_db.sincronizar_empleados_a_planilla()

    archivo_path = os.path.join(_planillas_dir, mes_target["archivo"])
    if not os.path.exists(archivo_path):
        raise HTTPException(status_code=404, detail=f"No se encontró el Excel: {mes_target['archivo']}")

    ok, msg, hours_data = horario_db.rellenar_horas_en_excel(
        archivo_path, semana_nombre, horario["horario"]
    )

    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    # Guardar salarios en DB
    try:
        tarifas = plan_db.get_tarifas()
        emps = plan_db.get_empleados(solo_activos=False)
        emp_map = {e["nombre"]: e["id"] for e in emps}

        try:
            sem_num = int(semana_nombre.split(" ")[-1])
        except (ValueError, IndexError):
            print(f"importar_horario_semana_historico: semana_nombre no parseable '{semana_nombre}', usando 0")
            sem_num = 0

        for emp_nombre, h in hours_data.items():
            if emp_nombre in emp_map:
                bruto = h.get("salario_bruto")
                if bruto is None:
                    bruto = (h["diurnas"] * tarifas["tarifa_diurna"]) + \
                            (h["mixtas"] * tarifas["tarifa_mixta"]) + \
                            (h["nocturnas"] * tarifas["tarifa_nocturna"]) + \
                            (h["extra"] * (tarifas["tarifa_diurna"] * 1.5))

                plan_db.guardar_salario_semanal(
                    emp_map[emp_nombre], emp_nombre,
                    mes_target["anio"], mes_target["mes"], sem_num, bruto
                )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al guardar salarios semanales: {e}")

    return {"status": "success", "message": msg}


@app.post("/api/planillas/boletas/generar")
def generar_boletas(req: PlanillaBoletasRequest):
    mes_activo = plan_db.get_mes_activo()
    if not mes_activo:
        raise HTTPException(status_code=400, detail="No active month to generate boletas.")

    _sync_prestamo_rebajos_mes(mes_data=mes_activo)

    archivo_path = os.path.join(_planillas_dir, mes_activo["archivo"])
    logo_path = os.path.join(_planillas_dir, "logo.png")
    
    ok, msg, out_dir = gb_module.generar_boletas_semana(archivo_path, req.semana_nombre, logo_path)
    
    if ok:
        # Open folder dynamically on Windows
        if os.name == 'nt':
            os.startfile(out_dir)
        return {"status": "success", "message": msg, "out_dir": out_dir}
    else:
        raise HTTPException(status_code=400, detail=msg)

@app.get("/api/planillas/excel/abrir")
def abrir_excel_activo():
    mes_activo = plan_db.get_mes_activo()
    if not mes_activo:
        raise HTTPException(status_code=400, detail="No hay mes activo.")
    
    archivo_path = os.path.join(_planillas_dir, mes_activo["archivo"])
    if not os.path.exists(archivo_path):
        raise HTTPException(status_code=404, detail="No se encontró el archivo Excel.")
        
    if os.name == 'nt':
        os.startfile(archivo_path)
    return {"status": "success"}

@app.get("/api/planillas/excel/abrir/{mes_id}")
def abrir_excel_por_id(mes_id: int):
    meses = plan_db.get_todos_meses()
    mes_target = next((m for m in meses if m["id"] == mes_id), None)
    
    if not mes_target:
        raise HTTPException(status_code=404, detail="Mes no encontrado")
        
    archivo_path = os.path.join(_planillas_dir, mes_target["archivo"])
    if not os.path.exists(archivo_path):
        raise HTTPException(status_code=404, detail="Archivo Excel no encontrado")
        
    if os.name == 'nt':
        os.startfile(archivo_path)
    return {"status": "success"}

# ==============================================================================
# UTILIDADES — GENERADOR DE DOCUMENTOS WORD
# ==============================================================================
import docx_generator

class DocPrestamo(BaseModel):
    emp_id: int
    monto_total: float
    pago_semanal: float

class AmoDatoItem(BaseModel):
    fecha: Optional[str] = None
    monto: Optional[float] = None
    minutos: Optional[int] = None

class DocAmonestacion(BaseModel):
    emp_id: int
    tipo: str  # "faltantes", "tardanzas", "conductas"
    datos: List[AmoDatoItem] = Field(default_factory=list)

class DocVacacionesReq(BaseModel):
    emp_id: int
    tipo: str  # 'total' or 'parcial'
    fecha_inicio: str
    fecha_reingreso: str

class DocLiquidacion(BaseModel):
    emp_id: int
    vacaciones_dias: float
    vacaciones_monto: float
    aguinaldo_monto: float
    cesantia_monto: float = 0
    preaviso_monto: float = 0
    total_pagar: float
    modo_pago: str  # "Abonos" o "Total"

def _get_emp_info(emp_id: int):
    emps = plan_db.get_empleados(solo_activos=False)
    emp = next((e for e in emps if e["id"] == emp_id), None)
    if not emp:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    return emp.get("nombre", ""), emp.get("cedula", "")

@app.post("/api/utilidades/prestamo")
def generar_doc_prestamo(req: DocPrestamo):
    nombre, cedula = _get_emp_info(req.emp_id)
    logo = os.path.join(_planillas_dir, "logo.png")
    base = _runtime_root
    path = docx_generator.generar_prestamo(nombre, cedula, req.monto_total, req.pago_semanal, logo, base)
    return {"status": "success", "path": path}

@app.post("/api/utilidades/amonestacion")
def generar_doc_amonestacion(req: DocAmonestacion):
    nombre, cedula = _get_emp_info(req.emp_id)
    logo = os.path.join(_planillas_dir, "logo.png")
    base = _runtime_root
    datos_dict = [d.dict(exclude_none=True) for d in req.datos]
    path = docx_generator.generar_amonestacion(nombre, cedula, req.tipo, datos_dict, logo, base)
    return {"status": "success", "path": path}

@app.post("/api/utilidades/vacaciones")
def generar_doc_vacaciones(req: DocVacacionesReq):
    nombre, cedula = _get_emp_info(req.emp_id)
    logo = os.path.join(_planillas_dir, "logo.png")
    base = _runtime_root
    path = docx_generator.generar_vacaciones(nombre, cedula, req.tipo, req.fecha_inicio, req.fecha_reingreso, logo, base)
    return {"status": "success", "path": path}

@app.post("/api/utilidades/despido")
def generar_doc_despido(req: DocLiquidacion):
    nombre, cedula = _get_emp_info(req.emp_id)
    logo = os.path.join(_planillas_dir, "logo.png")
    base = _runtime_root
    path = docx_generator.generar_liquidacion("Despido", nombre, cedula, req.vacaciones_dias, req.vacaciones_monto, req.aguinaldo_monto, req.cesantia_monto, req.preaviso_monto, req.total_pagar, req.modo_pago, logo, base)
    return {"status": "success", "path": path}

@app.post("/api/utilidades/renuncia")
def generar_doc_renuncia(req: DocLiquidacion):
    nombre, cedula = _get_emp_info(req.emp_id)
    logo = os.path.join(_planillas_dir, "logo.png")
    base = _runtime_root
    path = docx_generator.generar_liquidacion("Renuncia", nombre, cedula, req.vacaciones_dias, req.vacaciones_monto, req.aguinaldo_monto, 0, 0, req.total_pagar, req.modo_pago, logo, base)
    return {"status": "success", "path": path}

class DocRecomendacion(BaseModel):
    emp_id: int
    puesto: str
    texto_adicional: str = ""

@app.post("/api/utilidades/recomendacion")
def generar_doc_recomendacion(req: DocRecomendacion):
    nombre, cedula = _get_emp_info(req.emp_id)
    emps = plan_db.get_empleados(solo_activos=False)
    emp = next((e for e in emps if e['id'] == req.emp_id), None)
    fecha_inicio = emp.get("fecha_inicio", "") if emp else ""
    logo = os.path.join(_planillas_dir, "logo.png")
    base = _runtime_root
    path = docx_generator.generar_recomendacion(nombre, cedula, req.puesto, fecha_inicio, req.texto_adicional, logo, base)
    return {"status": "success", "path": path}

# ==============================================================================
# INVENTARIO API ENDPOINTS
# ==============================================================================
from fastapi import UploadFile, File

INVENTARIO_BASE_DEFAULT_PATH = r"c:\Users\kenda\Downloads\Control de Inventario Pista.xlsx"


def _normalize_inventory_key(value):
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text)
    return text


def _to_float(value, default=0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_inventario_base_from_excel(path: str):
    wb = openpyxl.load_workbook(path, data_only=True)
    articulos = []
    try:
        for sheet_name in ("S", "S2"):
            if sheet_name not in wb.sheetnames:
                continue
            ws = wb[sheet_name]
            for row_idx in range(3, ws.max_row + 1):
                nombre = ws.cell(row=row_idx, column=1).value
                if nombre is None or str(nombre).strip() == "":
                    continue
                articulos.append({
                    "codigo": str(ws.cell(row=row_idx, column=2).value or "").strip(),
                    "nombre": str(nombre).strip(),
                    "precio": _to_float(ws.cell(row=row_idx, column=3).value, 0),
                    "existencias_base": _to_float(ws.cell(row=row_idx, column=4).value, 0),
                    "hoja_origen": sheet_name,
                    "orden": len(articulos) + 1,
                })
    finally:
        wb.close()
    return articulos


def _ensure_inventario_base_seeded():
    current = plan_db.get_inventario_base()
    if current["articulos"]:
        return current
    if os.path.exists(INVENTARIO_BASE_DEFAULT_PATH):
        articulos = _load_inventario_base_from_excel(INVENTARIO_BASE_DEFAULT_PATH)
        if articulos:
            plan_db.replace_inventario_base(articulos, source_path=INVENTARIO_BASE_DEFAULT_PATH)
            return plan_db.get_inventario_base()
    return current


def _compare_inventory_against_base(upload_items, base_items):
    # Build lookup by (codigo, nombre) — both must match exactly
    base_by_key = {}
    for base in base_items:
        code = _normalize_inventory_key(base.get("codigo"))
        name = _normalize_inventory_key(base.get("nombre"))
        if code and name:
            base_by_key[(code, name)] = base

    rows = []
    matched_base_ids = set()
    resumen = {
        "total_base": len(base_items),
        "total_cargados": len(upload_items),
        "coinciden": 0,
        "con_diferencia": 0,
        "faltantes_en_carga": 0,
    }

    for item in upload_items:
        item_code = _normalize_inventory_key(item.get("codigo"))
        item_name = _normalize_inventory_key(item.get("nombre"))
        match = base_by_key.get((item_code, item_name)) if item_code and item_name else None

        if match:
            matched_base_ids.add(match["id"])
            delta = _to_float(item.get("existencias"), 0) - _to_float(match.get("existencias_base"), 0)
            resumen["coinciden" if delta == 0 else "con_diferencia"] += 1
            rows.append({
                "status": "match" if delta == 0 else "difference",
                "base_id": match["id"],
                "hoja_origen": match.get("hoja_origen"),
                "codigo": item.get("codigo") or match.get("codigo", ""),
                "nombre": item.get("nombre") or match.get("nombre", ""),
                "precio": item.get("precio", 0) or match.get("precio", 0),
                "existencias_base": _to_float(match.get("existencias_base"), 0),
                "existencias_actual": _to_float(item.get("existencias"), 0),
                "delta": delta,
            })
        # Items not in base are simply ignored — no "new" rows

    for base in base_items:
        if base["id"] in matched_base_ids:
            continue
        resumen["faltantes_en_carga"] += 1
        rows.append({
            "status": "missing",
            "base_id": base["id"],
            "hoja_origen": base.get("hoja_origen"),
            "codigo": base.get("codigo", ""),
            "nombre": base.get("nombre", ""),
            "precio": base.get("precio", 0),
            "existencias_base": _to_float(base.get("existencias_base"), 0),
            "existencias_actual": None,
            "delta": None,
        })

    order = {"difference": 0, "missing": 1, "match": 2}
    rows.sort(key=lambda r: (order.get(r["status"], 9), r.get("hoja_origen") or "Z", r.get("nombre") or ""))
    return rows, resumen


class InventarioBaseArticuloIn(BaseModel):
    id: Optional[int] = None
    codigo: str = ""
    nombre: str
    precio: float = 0
    existencias_base: float = 0
    hoja_origen: Optional[str] = None
    orden: Optional[int] = None


@app.get("/api/inventario/base")
def get_inventario_base():
    return _ensure_inventario_base_seeded()


@app.post("/api/inventario/base/import-default")
def import_inventario_base_default():
    if not os.path.exists(INVENTARIO_BASE_DEFAULT_PATH):
        raise HTTPException(status_code=404, detail=f"No se encontro el archivo base en {INVENTARIO_BASE_DEFAULT_PATH}")
    articulos = _load_inventario_base_from_excel(INVENTARIO_BASE_DEFAULT_PATH)
    if not articulos:
        raise HTTPException(status_code=400, detail="No se encontraron articulos en las hojas S y S2.")
    plan_db.replace_inventario_base(articulos, source_path=INVENTARIO_BASE_DEFAULT_PATH)
    return {"status": "success", "total_articulos": len(articulos), "source_path": INVENTARIO_BASE_DEFAULT_PATH}


@app.post("/api/inventario/base/articulo")
def save_inventario_base_articulo(payload: InventarioBaseArticuloIn):
    if not payload.nombre.strip():
        raise HTTPException(status_code=400, detail="El nombre del producto es obligatorio.")
    articulo_id = plan_db.upsert_inventario_base_articulo(payload.model_dump())
    return {"status": "success", "id": articulo_id}


@app.delete("/api/inventario/base/articulo/{articulo_id}")
def delete_inventario_base_articulo(articulo_id: int):
    plan_db.delete_inventario_base_articulo(articulo_id)
    return {"status": "success"}

@app.post("/api/inventario/upload")
async def upload_inventario(file: UploadFile = File(...)):
    """Sube un Excel de inventario, parsea artículos y guarda en DB."""
    if not file.filename.endswith(('.xlsx', '.xls', '.xlsm')):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos Excel (.xlsx, .xls, .xlsm)")

    # Save to temp file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    content = await file.read()
    tmp.write(content)
    tmp.close()

    try:
        wb = openpyxl.load_workbook(tmp.name, data_only=True)
        ws = wb.active

        target_fields = {
            'nombre': ['nombre', 'articulo', 'producto', 'descripcion', 'item', 'descripción'],
            'precio': ['precio', 'costo', 'price', 'valor'],
            'codigo': ['codigo', 'código', 'code', 'cod', 'sku', 'ref', 'referencia'],
            'existencias': ['existencias', 'existencia', 'stock', 'cantidad', 'cant', 'inventario', 'qty'],
        }

        # Find a coherent header row inside the initial report area.
        # This avoids confusing report filters like "Inventario: Todos" with
        # the real table headers when the Excel includes a preamble.
        header_row, header_map = _detect_inventory_header_row(ws, target_fields)

        if not header_row or 'nombre' not in header_map.values():
            wb.close()
            raise HTTPException(status_code=400, detail="No se encontró encabezado con columna de nombre de artículo. Asegúrese de que el Excel tenga encabezados: Nombre, Precio, Código, Existencias.")

        # Parse articles
        articulos = []
        for row_idx in range(header_row + 1, ws.max_row + 1):
            art = {'codigo': '', 'nombre': '', 'precio': 0, 'existencias': 0}
            has_name = False
            for col_idx, field in header_map.items():
                val = ws.cell(row=row_idx, column=col_idx).value
                if val is None:
                    continue
                if field == 'nombre':
                    if isinstance(val, str) and val.strip():
                        art['nombre'] = val.strip()
                        has_name = True
                elif field == 'codigo':
                    art['codigo'] = str(val).strip()
                elif field in ('precio', 'existencias'):
                    try:
                        art[field] = float(val)
                    except (ValueError, TypeError):
                        art[field] = 0
            if has_name:
                articulos.append(art)

        wb.close()

        if not articulos:
            raise HTTPException(status_code=400, detail="No se encontraron artículos en el Excel.")

        # Save to DB
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        carga_id = plan_db.guardar_carga_inventario(today, file.filename, articulos)

        return {
            "status": "success",
            "carga_id": carga_id,
            "total_articulos": len(articulos),
            "message": f"Se cargaron {len(articulos)} artículos exitosamente."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al procesar el Excel: {str(e)}")
    finally:
        os.unlink(tmp.name)

@app.get("/api/inventario/latest")
def get_inventario_latest():
    """Devuelve la carga más reciente con sus artículos."""
    data = plan_db.get_ultima_carga()
    if not data:
        return {"carga": None, "articulos": []}
    return data

@app.get("/api/inventario/diff")
def get_inventario_diff():
    """Calcula diferencias entre la ultima carga y la base maestra editable."""
    ultima = plan_db.get_ultima_carga()
    base = _ensure_inventario_base_seeded()
    if not ultima:
        return {"carga_actual": None, "base": base, "articulos": [], "resumen": {}}

    arts_out, resumen = _compare_inventory_against_base(ultima["articulos"], base["articulos"])

    return {
        "carga_actual": ultima["carga"],
        "base": base,
        "articulos": arts_out,
        "resumen": resumen
    }

@app.get("/api/inventario/history")
def get_inventario_history():
    """Historial de cargas de inventario."""
    return plan_db.get_historial_cargas(limit=30)

@app.delete("/api/inventario/{carga_id}")
def delete_inventario_carga(carga_id: int):
    """Elimina una carga de inventario."""
    plan_db.delete_carga_inventario(carga_id)
    return {"status": "success"}

# ==============================================================================
# Include Routers (for organized endpoint structure)
# ==============================================================================
app.include_router(empleados_router)
app.include_router(horarios_router)
app.include_router(planillas_router)
app.include_router(config_router)

# ==============================================================================
# Serve Frontend
# ==============================================================================
frontend_path = _frontend_dir
if os.path.exists(frontend_path):
    # Mount frontend directory for static files (React/Vue/JS/CSS)
    # Using 'html=True' lets it serve index.html for the root automatically.
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
else:
    print(f"Warning: Frontend path {frontend_path} not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
