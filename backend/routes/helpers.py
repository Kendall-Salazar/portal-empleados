"""Funciones helper compartidas para los routers de Cronos."""
import json
import datetime
import os
import unicodedata
import re
from typing import Optional, List, Dict, Any
from scheduler_engine import DAYS, SPECIAL_DAY_MODES, ShiftScheduler
import database as plan_db


def _get_conn():
    """Get connection to the shared cronos.db"""
    return plan_db.get_conn()


def _history_sqlite_row_to_log_entry(r: dict):
    """Convierte una fila horarios_generados al dict del historial; None si es inválida."""
    row_id = r.get("id")
    try:
        raw_h = r.get("horario")
        schedule = json.loads(raw_h) if raw_h else {}
        if not isinstance(schedule, dict):
            schedule = {}
    except (json.JSONDecodeError, TypeError):
        print(f"[load_db] horario JSON inválido id={row_id}, entrada omitida del historial")
        return None
    try:
        raw_t = r.get("tareas")
        daily_tasks = json.loads(raw_t) if raw_t else {}
        if not isinstance(daily_tasks, dict):
            daily_tasks = {}
    except (json.JSONDecodeError, TypeError):
        daily_tasks = {}
    try:
        raw_m = r.get("metadata")
        meta = json.loads(raw_m) if raw_m else {}
        if not isinstance(meta, dict):
            meta = {}
    except (json.JSONDecodeError, TypeError):
        meta = {}
    entry = {
        "db_id": row_id,
        "name": r.get("nombre"),
        "schedule": schedule,
        "daily_tasks": daily_tasks,
        "timestamp": r.get("timestamp"),
    }
    entry.update(meta)
    return entry


_WEEK_NAME_RE = re.compile(r"semana\s*(\d+)", re.IGNORECASE)
SCHEDULE_DAYS = ("Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue")


def _normalize_special_days(raw_special_days):
    normalized = {}
    if not isinstance(raw_special_days, dict):
        return normalized

    for raw_day, raw_mode in raw_special_days.items():
        if raw_day not in SCHEDULE_DAYS:
            continue
        mode = raw_mode if raw_mode in SPECIAL_DAY_MODES else "normal"
        if raw_day == "Dom" and mode in ("sunday_like", "sunday"):
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


def _prepare_history_for_solver(history_list, target_week_start=None, use_history=True, max_entries=8):
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
            "selection_fallback": False,
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

    # Entradas sin week_dates ni "Semana N" en el nombre no tienen sort_date: el filtro por
    # semana objetivo las deja fuera y el solver queda sin contexto o peor. Usar últimas
    # guardadas como respaldo — no bloquea generar ni "pierde" el historial en la BD.
    selection_fallback = False
    if not eligible and ordered:
        eligible = ordered
        selection_fallback = True
        selection_reason = "fallback_no_week_anchor_match"

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
            "selection_fallback": False,
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

    if selection_fallback:
        label += " · Respaldo: sin fecha de semana anterior clara; se usan las últimas guardadas"

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
        "selection_fallback": selection_fallback,
        "selection_reason": selection_reason,
    }


# Orden alineado con fetchHistoryEntries() en el frontend: más reciente primero (timestamp, luego id).
_HISTORY_LIST_ORDER = "timestamp DESC, id DESC"


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
            elif day_mode in {"sunday", "sunday_like", "holy_thursday"}:
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
            "forced_quebrado_partial": bool(r["forced_quebrado_partial"]) if "forced_quebrado_partial" in r.keys() else False,
            "quebrado_preferido": str(r["quebrado_preferido"]) if "quebrado_preferido" in r.keys() else "auto",
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
            "refuerzo_days_mode": cfg_row["refuerzo_days_mode"] if "refuerzo_days_mode" in cfg_row.keys() and cfg_row["refuerzo_days_mode"] else "auto",
            "refuerzo_manual_days": json.loads(cfg_row["refuerzo_manual_days"]) if "refuerzo_manual_days" in cfg_row.keys() and cfg_row["refuerzo_manual_days"] else [],
            "allow_collision_quebrado": bool(cfg_row["allow_collision_quebrado"]),
            "allow_quebrado_largo": bool(cfg_row["allow_quebrado_largo"]) if "allow_quebrado_largo" in cfg_row.keys() else False,
            "collision_peak_priority": cfg_row["collision_peak_priority"],
            "sunday_cycle_index": cfg_row["sunday_cycle_index"] or 0,
            "sunday_rotation_queue": json.loads(cfg_row["sunday_rotation_queue"]) if cfg_row["sunday_rotation_queue"] else None,
            "use_history": bool(cfg_row["use_history"]) if "use_history" in cfg_row.keys() else True,
            "holidays": json.loads(cfg_row["holidays"]) if "holidays" in cfg_row.keys() and cfg_row["holidays"] else [],
            "jefe_base_shift": (
                (cfg_row["jefe_base_shift"] or "J_06-16")
                if "jefe_base_shift" in cfg_row.keys()
                else "J_06-16"
            ),
            "use_pref_plantilla": bool(cfg_row["use_pref_plantilla"])
            if "use_pref_plantilla" in cfg_row.keys()
            else False,
            "cleaning_tasks": json.loads(cfg_row["cleaning_tasks"])
            if "cleaning_tasks" in cfg_row.keys() and cfg_row["cleaning_tasks"]
            else {},
            "jefe_config": json.loads(cfg_row["jefe_config"])
            if "jefe_config" in cfg_row.keys() and cfg_row["jefe_config"]
            else {},
        }

    # Historial: todas las filas activas, orden cronológico por id (no se borra al generar).
    # Filas con JSON corrupto se omiten para no tumbar el arranque ni /api/solve.
    hist_rows = conn.execute(
        "SELECT * FROM horarios_generados WHERE IFNULL(deleted, 0) = 0 ORDER BY id ASC"
    ).fetchall()
    history_log = []
    for r in hist_rows:
        entry = _history_sqlite_row_to_log_entry(dict(r))
        if entry:
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
                        forced_quebrado=?, forced_quebrado_partial=?, quebrado_preferido=?,
                        es_jefe_pista=?, es_practicante=?, strict_preferences=?, turnos_fijos=?, dia_libre_forzado=?, activo=1
                    WHERE nombre=?
                """, (
                    emp.get("gender", "M"),
                    1 if emp.get("can_do_night", True) else 0,
                    1 if emp.get("allow_no_rest", False) else 0,
                    1 if emp.get("forced_libres", False) else 0,
                    1 if emp.get("forced_quebrado", False) else 0,
                    1 if emp.get("forced_quebrado_partial", False) else 0,
                    emp.get("quebrado_preferido", "auto"),
                    1 if emp.get("is_jefe_pista", False) else 0,
                    1 if emp.get("is_practicante", False) else 0,
                    1 if emp.get("strict_preferences", False) else 0,
                    json.dumps(emp.get("fixed_shifts", {}), ensure_ascii=False),
                    "",
                    emp["name"],
                ))
            else:
                conn.execute("""
                    INSERT INTO horario_empleados
                    (nombre, genero, puede_nocturno, allow_no_rest, forced_libres,
                     forced_quebrado, forced_quebrado_partial, quebrado_preferido,
                     es_jefe_pista, es_practicante, strict_preferences, turnos_fijos, dia_libre_forzado, activo)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """, (
                    emp["name"], emp.get("gender", "M"),
                    1 if emp.get("can_do_night", True) else 0,
                    1 if emp.get("allow_no_rest", False) else 0,
                    1 if emp.get("forced_libres", False) else 0,
                    1 if emp.get("forced_quebrado", False) else 0,
                    1 if emp.get("forced_quebrado_partial", False) else 0,
                    emp.get("quebrado_preferido", "auto"),
                    1 if emp.get("is_jefe_pista", False) else 0,
                    1 if emp.get("is_practicante", False) else 0,
                    1 if emp.get("strict_preferences", False) else 0,
                    json.dumps(emp.get("fixed_shifts", {}), ensure_ascii=False),
                    "",
                ))

    # Guardar config
    if "config" in data:
        cfg = data["config"]
        conn.execute("DELETE FROM horario_config")
        conn.execute("""
            INSERT INTO horario_config
            (id, night_mode, fixed_night_person, allow_long_shifts, use_refuerzo,
             refuerzo_type, refuerzo_start, refuerzo_end, refuerzo_days_mode, refuerzo_manual_days,
             allow_collision_quebrado, allow_quebrado_largo, collision_peak_priority, sunday_cycle_index,
             sunday_rotation_queue, use_history, strict_weekly_alternation, holidays,
             jefe_base_shift, use_pref_plantilla, cleaning_tasks, jefe_config)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cfg.get("night_mode", "rotation"),
            cfg.get("fixed_night_person"),
            1 if cfg.get("allow_long_shifts", False) else 0,
            1 if cfg.get("use_refuerzo", False) else 0,
            cfg.get("refuerzo_type", "personalizado"),
            cfg.get("refuerzo_start", "07:00"),
            cfg.get("refuerzo_end", "12:00"),
            cfg.get("refuerzo_days_mode", "auto"),
            json.dumps(cfg.get("refuerzo_manual_days", [])),
            1 if cfg.get("allow_collision_quebrado", False) else 0,
            1 if cfg.get("allow_quebrado_largo", False) else 0,
            cfg.get("collision_peak_priority", "pm"),
            cfg.get("sunday_cycle_index", 0),
            json.dumps(cfg.get("sunday_rotation_queue")) if cfg.get("sunday_rotation_queue") else None,
            1 if cfg.get("use_history", True) else 0,
            1 if cfg.get("strict_weekly_alternation", False) else 0,
            json.dumps(cfg.get("holidays", [])),
            str(cfg.get("jefe_base_shift", "J_06-16") or "J_06-16"),
            1 if cfg.get("use_pref_plantilla", False) else 0,
            json.dumps(cfg.get("cleaning_tasks", {})),
            json.dumps(cfg.get("jefe_config", {})),
        ))

    # NOTA: history_log NO se guarda aquí. El historial se maneja exclusivamente
    # por los endpoints dedicados (/api/history y variantes) que escriben directo
    # a SQLite. Esto previene borrado silencioso: si save_db() se llama con un
    # history_log incompleto (ej. desde /api/config o /api/solve), NO se pierden
    # entradas de historial que ya existen en la DB.

    conn.commit()
    conn.close()
