# scheduler_engine.py
# EXACT PORT OF FUNCIONA.PY LOGIC

from collections import Counter
import copy
import json
from ortools.sat.python import cp_model
import json
from ortools.sat.python import cp_model
import logging
import re

class SolutionCounter(cp_model.CpSolverSolutionCallback):
    def __init__(self):
        cp_model.CpSolverSolutionCallback.__init__(self)
        self.solution_count = 0
    def on_solution_callback(self):
        self.solution_count += 1


def _refresh_solution_hints(model, solver, x):
    """Replace the model's hints with the solver's current solution so the
    next lexicographic pass starts from it. Skips silently when the installed
    OR-Tools version offers no way to clear hints (adding duplicate hints
    would invalidate the model)."""
    try:
        model.ClearHints()
    except AttributeError:
        try:
            model.Proto().solution_hint.Clear()
        except Exception:
            return
    for var in x.values():
        model.AddHint(var, solver.Value(var))


from datetime import datetime
import os
import time

logger = logging.getLogger(__name__)

# CONSTANTS
DAYS = ["Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue"]
HOURS = list(range(5, 29))
ROTATION_HISTORY_CORE_DAYS = ("Vie", "Lun", "Mar", "Mié", "Jue")
IGNORED_ROTATION_SHIFTS = frozenset({"OFF", "VAC", "PERM", "N_22-05"})

# Ventana de semanas que se usa para rachas AM/PM y rotación de domingos.
# Se usa en: build_rotation_history_context, recent_entries, Sunday rotation scan.
ROTATION_HISTORY_WINDOW = 8

HEAVY_EXTENDED_SHIFTS = frozenset({
    "J_07-17",
    "J_08-18",
    "J_09-19",
    "J_10-20",
    "E1_07-18",
    "E2_08-19",
    "T4_08-16",
})
WOMEN_ROTATION_TOKENS = ("AM", "PM")
MANUAL_SHIFT_PREFIX = "MANUAL_"
# Per-day refuerzo sentinel: the day is ACTIVE but the solver decides whether the
# refuerzo works and which shift (from its allowed pool) — vs a fixed MANUAL_ shift.
REFUERZO_AUTO_DAY = "AUTO"
SPECIAL_DAY_MODE_NORMAL = "normal"
# Domingo real (solo Dom): cobertura y turnos de domingo. No es una "excepción".
SPECIAL_DAY_MODE_SUNDAY = "sunday"
# Excepción semanal aplicable a otros días: "como domingo" (misma lógica de cobertura/turnos).
SPECIAL_DAY_MODE_SUNDAY_LIKE = "sunday_like"
SPECIAL_DAY_MODE_HOLY_THURSDAY = "holy_thursday"
SPECIAL_DAY_MODE_CLOSED = "closed"
SPECIAL_DAY_MODES = frozenset({
    SPECIAL_DAY_MODE_NORMAL,
    SPECIAL_DAY_MODE_SUNDAY,
    SPECIAL_DAY_MODE_SUNDAY_LIKE,
    SPECIAL_DAY_MODE_HOLY_THURSDAY,
    SPECIAL_DAY_MODE_CLOSED,
})
WEEKDAY_LIKE_SPECIAL_DAY_MODES = frozenset({
    SPECIAL_DAY_MODE_NORMAL,
    SPECIAL_DAY_MODE_HOLY_THURSDAY,
})
HISTORY_NEUTRAL_SPECIAL_DAY_MODES = frozenset({
    SPECIAL_DAY_MODE_SUNDAY,
    SPECIAL_DAY_MODE_SUNDAY_LIKE,
    SPECIAL_DAY_MODE_HOLY_THURSDAY,
    SPECIAL_DAY_MODE_CLOSED,
})

# Datafono policy: cap live staffing at 5 on every day.
# Outside Sunday we also hard-limit the amount of time spent exactly at that cap.
OVERSTAFF_POLICY_DAYS = tuple(DAYS)
OVERSTAFF_CAP_LIMIT_DAYS = tuple(d for d in DAYS if d != "Dom")
OVERSTAFF_CAP_VALUE = 5
OVERSTAFF_ALLOWED_HOURS_AT_CAP_PER_DAY = 1

# Rango permitido para el tope configurable de personas en pista al mismo tiempo.
OVERSTAFF_CAP_MIN = 3
OVERSTAFF_CAP_MAX = 12


def resolve_overstaff_cap(config):
    """Máximo de personas en pista al mismo tiempo (por hora).

    Lee 'max_simultaneous' de la config del usuario. Si no está definido o es
    inválido, cae al valor por defecto del sistema (OVERSTAFF_CAP_VALUE).
    Se acota al rango [OVERSTAFF_CAP_MIN, OVERSTAFF_CAP_MAX] para evitar valores
    absurdos que degeneren el modelo.
    """
    raw = (config or {}).get("max_simultaneous")
    if raw in (None, "", 0):
        return OVERSTAFF_CAP_VALUE
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return OVERSTAFF_CAP_VALUE
    return max(OVERSTAFF_CAP_MIN, min(OVERSTAFF_CAP_MAX, value))


def _am_pm_token(shift_name: str):
    """Classify any shift into 'AM' (starts before 12) or 'PM' (starts at 12+).
    Returns None for non-working or ignored shifts."""
    if shift_name in ("AM", "PM"):
        return shift_name  # already classified
    if shift_name not in SHIFTS or shift_name in IGNORED_ROTATION_SHIFTS:
        return None
    hours = SHIFTS.get(shift_name, set())
    if not hours:
        return None
    return "AM" if min(hours) < 12 else "PM"


def _get_alternating_pairs(config, employees, emp_data):
    """Return list of (emp1, emp2) pairs for the alternation (opposite AM/PM) constraint.

    Uses config['alternating_pairs'] when explicitly set; otherwise auto-detects
    pairs from employees with gender == 'F' (preserves the original default behaviour)."""
    pairs_config = (config or {}).get("alternating_pairs")
    if pairs_config is not None:
        result = []
        for p in pairs_config:
            members = p.get("employees", [])
            if len(members) == 2 and members[0] in employees and members[1] in employees:
                result.append((members[0], members[1]))
        return result
    # Default: form a single pair from all gender-F employees (original behaviour)
    women = [e for e in employees if emp_data.get(e, {}).get("gender") == "F"]
    return [(women[0], women[1])] if len(women) == 2 else []


def get_overstaff_policy():
    return get_overstaff_policy_for_days()


def normalize_special_day_modes(raw_modes):
    normalized = {}
    if not isinstance(raw_modes, dict):
        return normalized

    for raw_day, raw_mode in raw_modes.items():
        if raw_day not in DAYS:
            continue
        mode = raw_mode if raw_mode in SPECIAL_DAY_MODES else SPECIAL_DAY_MODE_NORMAL
        if raw_day == "Dom" and mode in (SPECIAL_DAY_MODE_SUNDAY_LIKE, SPECIAL_DAY_MODE_SUNDAY):
            continue
        if raw_day != "Jue" and mode == SPECIAL_DAY_MODE_HOLY_THURSDAY:
            continue
        if mode != SPECIAL_DAY_MODE_NORMAL:
            normalized[raw_day] = mode
    return normalized


def get_effective_day_mode(day: str, special_day_modes=None):
    """Domingo: siempre `sunday` salvo `closed` explícito. `sunday_like` solo aplica a otros días."""
    normalized = normalize_special_day_modes(special_day_modes)
    if day == "Dom":
        if normalized.get(day) == SPECIAL_DAY_MODE_CLOSED:
            return SPECIAL_DAY_MODE_CLOSED
        return SPECIAL_DAY_MODE_SUNDAY
    if day in normalized:
        return normalized[day]
    return SPECIAL_DAY_MODE_NORMAL


def is_sunday_style_mode(mode: str) -> bool:
    return mode in (SPECIAL_DAY_MODE_SUNDAY, SPECIAL_DAY_MODE_SUNDAY_LIKE)


def is_sunday_like_day(day: str, special_day_modes=None) -> bool:
    """True solo si un día que no es Dom tiene excepción 'como domingo'."""
    normalized = normalize_special_day_modes(special_day_modes or {})
    return day != "Dom" and normalized.get(day) == SPECIAL_DAY_MODE_SUNDAY_LIKE


def is_holy_thursday_day(day: str, special_day_modes=None) -> bool:
    return get_effective_day_mode(day, special_day_modes) == SPECIAL_DAY_MODE_HOLY_THURSDAY


def is_closed_day(day: str, special_day_modes=None) -> bool:
    return get_effective_day_mode(day, special_day_modes) == SPECIAL_DAY_MODE_CLOSED


def is_weekday_like_mode(mode: str) -> bool:
    return mode in WEEKDAY_LIKE_SPECIAL_DAY_MODES


def get_allowed_shifts_for_day(day: str, standard_mode: bool = False, special_day_modes=None):
    mode = get_effective_day_mode(day, special_day_modes)
    if mode == SPECIAL_DAY_MODE_CLOSED:
        return ["OFF", "VAC", "PERM"]

    if mode == SPECIAL_DAY_MODE_HOLY_THURSDAY:
        return [shift for shift in SHIFTS.keys() if shift != "D4_13-22"]

    if is_sunday_style_mode(mode) and standard_mode:
        return [
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

    if is_sunday_style_mode(mode):
        return [shift for shift in SHIFTS.keys() if shift != "AUTO"]

    return [shift for shift in SHIFTS.keys() if shift != "D4_13-22"]


def get_overstaff_policy_for_days(special_day_modes=None, cap_value=None):
    normalized = normalize_special_day_modes(special_day_modes)
    policy_days = [d for d in DAYS if not is_closed_day(d, normalized)]
    limited_days = [
        d for d in policy_days
        if is_weekday_like_mode(get_effective_day_mode(d, normalized))
        and get_effective_day_mode(d, normalized) != SPECIAL_DAY_MODE_HOLY_THURSDAY
    ]
    return {
        "cap_value": cap_value if cap_value else OVERSTAFF_CAP_VALUE,
        "allowed_hours_at_cap_per_day": OVERSTAFF_ALLOWED_HOURS_AT_CAP_PER_DAY,
        "days": policy_days,
        "limited_days": limited_days,
    }


# SHIFT DEFINITIONS
SHIFTS = {
    "OFF": set(),
    # VAC: Vacation. PERM: Permission/Permiso.
    # CRITICAL: These must NOT be assigned automatically. Only via fixed_shifts.
    # We treat them as valid shift keys, but constrain to 0 unless fixed.
    "VAC": set(),
    "PERM": set(),
    "N_22-05": set([22, 23, 24, 25, 26, 27, 28]),  # 22:00-05:00 (7h)
    "T1_05-13": set(range(5, 13)),     # 05:00-13:00 (8h)
    "T2_06-14": set(range(6, 14)),     # 06:00-14:00 (8h)
    "T3_07-15": set(range(7, 15)),     # 07:00-15:00 (8h)
    "T4_08-16": set(range(8, 16)),     # 08:00-16:00 (8h)
    "T8_13-20": set(range(13, 20)),    # 13:00-20:00 (7h)
    "T10_15-22": set(range(15, 22)),   # 15:00-22:00 (7h)
    "T11_12-20": set(range(12, 20)),   # 12:00-20:00 (8h)
    "T13_16-22": set(range(16, 22)),   # 16:00-22:00 (6h)
    "T16_05-14": set(range(5, 14)),    # 05:00-14:00 (9h) - NEW for short staffed mornings
    
    # NEW 10-HOUR SHIFTS (Added to solve 4,3,4 peak feasibility)
    "J_06-16": set(range(6, 16)),      # 06:00-16:00 (10h)
    "J_07-17": set(range(7, 17)),      # 07:00-17:00 (10h)
    "J_08-18": set(range(8, 18)),      # 08:00-18:00 (10h)
    "J_09-19": set(range(9, 19)),      # 09:00-19:00 (10h)
    "J_10-20": set(range(10, 20)),     # 10:00-20:00 (10h)

    # NEW 11-HOUR SHIFTS (Bridging Morning/Afternoon precisely)
    "E1_07-18": set(range(7, 18)),     # 07:00-18:00 (11h)
    "E2_08-19": set(range(8, 19)),     # 08:00-19:00 (11h)
    "T17_16-23": set(range(16, 23)),   # 16:00-23:00 (7h, Mixed)
    
    "X_07-19": set(range(7, 19)),      # 07:00-19:00 (12h) - EXTRA FOR FEASIBILITY
    "X_08-20": set(range(8, 20)),      # 08:00-20:00 (12h)
    
    "D1_05-13": set(range(5, 13)),     # 05:00-13:00 (8h)
    "D2_14-22": set(range(14, 22)),    # 14:00-22:00 (8h)
    "D3_15-23": set(range(15, 23)),    # 15:00-23:00 (8h)
    "D4_13-22": set(range(13, 22)),    # 13:00-22:00 (9h, Dominical PM)
    "T13_13-22": set(range(13, 22)),   # 13:00-22:00 (9h) - Manual-only, same hours as D4
    "R1_07-11": set(range(7, 11)),     # 07:00-11:00 (4h) - Refuerzo Medio Tiempo
    "R2_16-20": set(range(16, 20)),    # 16:00-20:00 (4h) - Refuerzo Medio Tiempo
    "Q1_05-11+17-20": set(range(5, 11)) | set(range(17, 20)),  # 5am-11am + 5pm-8pm
    "Q2_07-11+17-20": set(range(7, 11)) | set(range(17, 20)),  # 7-11am + 5-8pm (Optimal for peak)
    "Q3_05-11+17-22": set(range(5, 11)) | set(range(17, 22)),  # 5am-11am + 5pm-10pm (11h, covers night)
}
SHIFT_NAMES = list(SHIFTS.keys())

# Shifts that must NEVER be auto-assigned by the solver.
# Only assignable via fixed_shifts (manual assignment from params panel).
MANUAL_ONLY_SHIFTS = {"T13_13-22", "VAC", "PERM"}

# Fallback groups: when a manual-only shift is infeasible,
# the solver tries these alternatives with similar entry hours.
SIMILAR_ENTRY_SHIFTS = {
    "T13_13-22": ["T8_13-20", "D4_13-22", "T10_15-22"],
}

# ── TURNOS DOBLES (DBL_*) ────────────────────────────────────────────────────
# Prefijo para los códigos de turno doble generados dinámicamente por
# sync_double_shifts(). Igual que MANUAL_/CUST_, es estado de módulo que se
# limpia y regenera en cada solve() (ver sync_double_shifts).
DOUBLE_SHIFT_PREFIX = "DBL_"
DEFAULT_MAX_DOUBLE_SHIFT_HOURS = 12
# Franja de noche real (22:00-05:00 del día siguiente, horas 22..28 en el
# reloj extendido de este módulo). El componente s1 de un doble NO puede
# tocar esta franja: se permite ENTRAR a la noche (s2 puede ser N_22-05)
# pero no salir de la noche y seguir de día.
NIGHT_HOURS_RANGE = frozenset(range(22, 29))


def resolve_max_double_shift_hours(config):
    """Tope de horas para un turno doble (DBL_*). Default 12h.

    Lee 'max_double_shift_hours' de la config del usuario. Si no está
    definido o es inválido, cae al default (DEFAULT_MAX_DOUBLE_SHIFT_HOURS).
    """
    raw = (config or {}).get("max_double_shift_hours")
    if raw in (None, "", 0):
        return DEFAULT_MAX_DOUBLE_SHIFT_HOURS
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_MAX_DOUBLE_SHIFT_HOURS
    if value <= 0:
        return DEFAULT_MAX_DOUBLE_SHIFT_HOURS
    return value


def _is_double_shift_component_eligible(code):
    """Componentes válidos para armar un turno doble.

    Excluye OFF/VAC/PERM, los turnos multi-bloque existentes (tienen '+' en
    el nombre, ej. Q1_05-11+17-20), los códigos MANUAL_/CUST_ (dinámicos,
    ya son manual-only o de prioridad configurable) y los HEAVY_EXTENDED_SHIFTS
    (bloqueo duro total, no combinables).
    """
    if code in ("OFF", "VAC", "PERM"):
        return False
    if "+" in code:
        return False
    if code.startswith(MANUAL_SHIFT_PREFIX) or code.startswith("CUST_"):
        return False
    if code in HEAVY_EXTENDED_SHIFTS:
        return False
    return True

def _parse_manual_time_token(token):
    raw = str(token or "").strip().lower().replace(".", "")
    raw = re.sub(r"\s+", "", raw)
    if not raw:
        return None

    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?(am|pm)", raw)
    if match:
        hour = int(match.group(1))
        minutes = int(match.group(2) or 0)
        suffix = match.group(3)
        if minutes != 0 or hour < 1 or hour > 12:
            return None
        if suffix == "am":
            return 0 if hour == 12 else hour
        return hour if hour == 12 else hour + 12

    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?", raw)
    if not match:
        return None

    hour = int(match.group(1))
    minutes = int(match.group(2) or 0)
    if minutes != 0 or hour < 0 or hour > 29:
        return None
    return hour

def _split_manual_range_segment(segment):
    cleaned = str(segment or "").strip().replace("–", "-").replace("—", "-")
    if not cleaned:
        return None

    for pattern in (
        re.compile(r"\s*-\s*"),
        re.compile(r"\s+a\s+", re.IGNORECASE),
        re.compile(r"\s+to\s+", re.IGNORECASE),
    ):
        parts = pattern.split(cleaned, maxsplit=1)
        if len(parts) == 2:
            return parts[0], parts[1]

    return None

def normalize_manual_shift_code(shift_code):
    if not isinstance(shift_code, str):
        return None

    raw = shift_code.strip()
    if not raw:
        return None

    upper = raw.upper()
    if upper in SHIFTS:
        return upper
    if upper in ("OFF", "LIBRE", "DESCANSO"):
        return "OFF"
    if upper in ("VAC", "VACACIONES"):
        return "VAC"
    if upper in ("PERM", "PERMISO"):
        return "PERM"

    candidate = raw
    if upper.startswith(MANUAL_SHIFT_PREFIX):
        candidate = raw[len(MANUAL_SHIFT_PREFIX):]

    segments = [seg for seg in re.split(r"\s*(?:\+|/|,)\s*", candidate) if seg]
    if not segments:
        return None

    normalized_segments = []
    for segment in segments:
        split = _split_manual_range_segment(segment)
        if not split:
            return None

        start = _parse_manual_time_token(split[0])
        end = _parse_manual_time_token(split[1])
        if start is None or end is None:
            return None

        normalized_segments.append(f"{start:02d}-{end:02d}")

    return f"{MANUAL_SHIFT_PREFIX}{'+'.join(normalized_segments)}"

def get_shift_hours_set(shift_code):
    normalized = normalize_manual_shift_code(shift_code)
    if normalized in SHIFTS:
        return set(SHIFTS[normalized])

    if not normalized or not normalized.startswith(MANUAL_SHIFT_PREFIX):
        return set()

    horas = set()
    for segment in normalized[len(MANUAL_SHIFT_PREFIX):].split("+"):
        start_raw, end_raw = segment.split("-")
        start = int(start_raw)
        end = int(end_raw)
        if end <= start:
            end += 24
        horas.update(range(start, end))
    return horas
HOMOGENEITY_MONITORED_SHIFTS = tuple(
    shift_name for shift_name in SHIFT_NAMES
    if shift_name not in {"OFF", "VAC", "PERM", "N_22-05", "R1_07-11", "R2_16-20"}
    and not shift_name.startswith("Q")
    and not shift_name.startswith("J_")
    and not shift_name.startswith("X_")
)
SUNDAY_ABSENCE_REWARD = 20000
# FIX 2026-06-03: Recompensas muy bajas (18k→2k) eran irrelevantes frente a
# otras penalizaciones del modelo (900k consistencia, 6M mujeres, etc.).
# El solver elegía quién trabaja el domingo por otros criterios, ignorando
# la cola de rotación. Ahora las recompensas son órdenes de magnitud mayores
# para que la cola sea el factor determinante.
SUNDAY_QUEUE_REWARDS = (5_000_000, 3_000_000, 2_000_000, 1_000_000, 500_000, 200_000)
SUNDAY_CONGESTED_WEEKDAY_PENALTY = 8000
SAME_SHIFT_STACK_PENALTY_3 = 6000
SAME_SHIFT_STACK_PENALTY_4 = 25000
SAME_SHIFT_STACK_PENALTY_5 = 90000
INFEASIBLE_DIAGNOSTIC_MAX_TIME_SECONDS = 6
# La prueba de cobertura (subir el tope de personas en pista) necesita más tiempo:
# encontrar una solución factible en un modelo grande tarda más que descartar
# preferencias estrictas. Corre una sola vez, así que puede permitirse más segundos.
INFEASIBLE_DIAGNOSTIC_COVERAGE_MAX_TIME_SECONDS = 20

# Near-hard consistency penalty: raised from 50k to 500k so turno_principal
# dominates all soft constraints except coverage infeasibility.
CONSISTENCY_PENALTY = 500000


def build_rest_incompatible_pairs(min_rest_hours, shift_names, shift_is_working, shift_min_hour, shift_max_hour):
    """Pares (s1,s2) con descanso estrictamente menor a min_rest_hours entre fin(s1) e inicio(s2) al día siguiente."""
    bad = set()
    for s1 in shift_names:
        if not shift_is_working.get(s1):
            continue
        end1 = shift_max_hour[s1] + 1
        for s2 in shift_names:
            if not shift_is_working.get(s2):
                continue
            start2 = shift_min_hour[s2]
            rest = (start2 + 24) - end1
            if rest < min_rest_hours:
                bad.add((s1, s2))
    return bad


def rest_hours_between_shifts(s1, s2, shift_min_hour, shift_max_hour, shift_is_working):
    if not s1 or not s2 or not shift_is_working.get(s1) or not shift_is_working.get(s2):
        return None
    end1 = shift_max_hour[s1] + 1
    start2 = shift_min_hour[s2]
    return (start2 + 24) - end1


def _parse_refuerzo_hour(value, default_hour):
    if isinstance(value, int):
        hour = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            return default_hour
        if ":" in raw:
            raw = raw.split(":", 1)[0]
        try:
            hour = int(raw)
        except ValueError:
            return default_hour
    else:
        return default_hour

    if hour < 0 or hour > 23:
        return default_hour
    return hour


def _normalize_refuerzos(config: dict) -> list:
    """Returns active refuerzos from config.refuerzos list (new format only).
    Does NOT migrate legacy use_refuerzo — legacy path is handled separately.
    """
    refuerzos = config.get('refuerzos') or []
    # Safety: if a raw JSON string leaks in (e.g. direct SQLite read), parse it
    if isinstance(refuerzos, str):
        try:
            refuerzos = json.loads(refuerzos) if refuerzos else []
        except (json.JSONDecodeError, TypeError):
            refuerzos = []
    if not isinstance(refuerzos, list):
        refuerzos = []
    return [r for r in refuerzos if isinstance(r, dict) and r.get('activo', True) and r.get('nombre')]


def _compute_refuerzo_coverage(refuerzos_activos: list) -> dict:
    """Pre-computes per-day, per-hour coverage count from a list of active refuerzos.
    Returns {day: {hour: count}} for documentation/future use.
    """
    coverage = {d: {h: 0 for h in range(24)} for d in ["Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue"]}
    for ref in refuerzos_activos:
        schedule = ref.get('schedule', {}) or {}
        for day, times in schedule.items():
            if day not in coverage:
                continue
            if isinstance(times, dict) and times.get('start') and times.get('end'):
                start_h = _parse_refuerzo_hour(times.get('start'), 7)
                end_h = _parse_refuerzo_hour(times.get('end'), 12)
                for h in range(start_h, min(end_h, 24)):
                    coverage[day][h] += 1
    return coverage


def sync_refuerzo_custom_shift(config):
    """Creates per-day shift codes for refuerzo schedule.

    Returns dict {day: shift_code} for personalizado with schedules,
    a single shift code string for legacy format,
    or None if not personalizado / no schedule.

    Also registers MANUAL_ codes for additional personalizado refuerzos
    from config.refuerzos[] so their fixed_shifts constraints work.
    """
    global SHIFT_NAMES

    # 1) Cleanup ALL MANUAL_ codes — they'll be re-registered below
    dynamic_codes = [code for code in list(SHIFTS.keys()) if code.startswith(MANUAL_SHIFT_PREFIX)]
    for code in dynamic_codes:
        SHIFTS.pop(code, None)
    if dynamic_codes:
        SHIFT_NAMES = [shift for shift in SHIFT_NAMES if shift not in dynamic_codes]

    result = None

    # 2) Legacy personalizado refuerzo
    if (config or {}).get("refuerzo_type") == "personalizado":
        schedule = (config or {}).get("refuerzo_schedule", None)

        if schedule and isinstance(schedule, dict) and len(schedule) > 0:
            # New per-day schedule format
            day_shift_map = {}
            created = {}  # (start_hour, end_hour) -> code
            for day, times in schedule.items():
                if not isinstance(times, dict):
                    continue
                if times.get("auto"):
                    # Día AUTO: activo, pero el solver elige turno (o lo deja OFF).
                    day_shift_map[day] = REFUERZO_AUTO_DAY
                    continue
                start_hour = _parse_refuerzo_hour(times.get("start"), 7)
                end_hour = _parse_refuerzo_hour(times.get("end"), 12)
                if end_hour == start_hour:
                    end_hour = (start_hour + 5) % 24

                key = (start_hour, end_hour)
                if key not in created:
                    code = f"{MANUAL_SHIFT_PREFIX}{start_hour:02d}-{end_hour:02d}"
                    effective_end = end_hour + 24 if end_hour <= start_hour else end_hour
                    SHIFTS[code] = set(range(start_hour, effective_end))
                    if code not in SHIFT_NAMES:
                        SHIFT_NAMES.append(code)
                    created[key] = code

                day_shift_map[day] = created[key]
            result = day_shift_map
        else:
            # Legacy format: single start/end + manual_days
            start_hour = _parse_refuerzo_hour((config or {}).get("refuerzo_start"), 7)
            end_hour = _parse_refuerzo_hour((config or {}).get("refuerzo_end"), 12)
            if end_hour == start_hour:
                end_hour = (start_hour + 5) % 24

            code = f"{MANUAL_SHIFT_PREFIX}{start_hour:02d}-{end_hour:02d}"
            effective_end = end_hour + 24 if end_hour <= start_hour else end_hour
            SHIFTS[code] = set(range(start_hour, effective_end))
            SHIFT_NAMES = [shift for shift in SHIFT_NAMES if shift != code] + [code]
            result = code

    # 3) Register MANUAL_ codes for ADDITIONAL personalizado refuerzos
    #    from config.refuerzos[] array, so their fixed_shifts constraints
    #    don't get silently skipped in _build_shift_selection.
    _all_refs = _normalize_refuerzos(config)
    for _ref in _all_refs:
        # Only personalizado type uses MANUAL_ codes in fixed_shifts
        if str(_ref.get('tipo') or 'personalizado').lower() != 'personalizado':
            continue
        _schedule = _ref.get('schedule', {}) or {}
        for _day, _times in _schedule.items():
            if isinstance(_times, dict) and _times.get('start') and _times.get('end'):
                _sh = _parse_refuerzo_hour(_times.get('start'), 7)
                _eh = _parse_refuerzo_hour(_times.get('end'), 12)
                ensure_manual_shift_code(_sh, _eh)

    # 4) Dedup SHIFT_NAMES
    seen = set()
    SHIFT_NAMES = [s for s in SHIFT_NAMES if not (s in seen or seen.add(s))]

    return result


# Custom shifts priorities - will be used by the solver
CUSTOM_SHIFTS_PRIORITIES = {}  # {shift_code: priority_value}


def sync_custom_shifts(config):
    """Add custom shifts from config to the available shifts list.
    
    Custom shifts are added with their priority. Higher priority means
    the solver will prefer this shift over others when filling time slots.
    
    Priority affects the solver's preference:
    - 100 (Alta): Strongly preferred, may break other rules to use this shift
    - 50 (Media): Normal preference
    - 10 (Baja): Used only when necessary
    
    This is applied AFTER the solver tries to satisfy all hard constraints,
    and affects soft constraints / penalty minimization.
    """
    global SHIFT_NAMES, CUSTOM_SHIFTS_PRIORITIES
    
    # Clear previous custom shifts (those starting with CUSTOM_SHIFT_PREFIX)
    custom_codes = [code for code in list(SHIFTS.keys()) if code.startswith("CUST_")]
    for code in custom_codes:
        SHIFTS.pop(code, None)
    CUSTOM_SHIFTS_PRIORITIES = {}
    
    custom_shifts = (config or {}).get("custom_shifts", [])
    if not custom_shifts:
        return
    
    for shift in custom_shifts:
        name = shift.get("name", "")
        start = shift.get("start")
        end = shift.get("end")
        priority = shift.get("priority", 50)
        
        if not name or start is None or end is None:
            continue
        
        # Create shift code
        code = f"CUST_{name}"
        effective_end = end + 24 if end <= start else end
        
        # Add to SHIFTS dict
        SHIFTS[code] = set(range(start, effective_end))
        SHIFT_NAMES.append(code)
        
        # Store priority (higher = more preferred)
        CUSTOM_SHIFTS_PRIORITIES[code] = priority


def sync_double_shifts(config):
    """Genera turnos dobles (DBL_*) combinando pares de turnos base contiguos.

    Un doble = unión de dos turnos base s1+s2 donde:
      - max(SHIFTS[s1]) + 1 == min(SHIFTS[s2])  (contiguos, sin overlap/gap).
      - s1 NO toca la franja de noche (22..28) — se permite ENTRAR a la noche
        (s2 puede ser N_22-05) pero no salir de la noche y seguir de día.
        (Esto sale solo de la contigüidad, pero se deja explícito.)
      - La unión de horas no supera resolve_max_double_shift_hours(config)
        (default 12h).

    Los códigos generados son SIEMPRE manual-only: nunca se auto-asignan,
    solo vía la pill "DOBLE" en fixed_shifts (ver _solve_with_min_rest).

    Se nombran por reloj de pared, ej. DBL_05-20 (05:00-20:00),
    DBL_15-05 (15:00-05:00 del día siguiente).

    Estado de módulo reusado entre requests: limpia los DBL_ previos al
    inicio, igual que sync_custom_shifts hace con los CUST_.
    """
    global SHIFT_NAMES

    # NOTA: los códigos DBL_* NO se agregan a MANUAL_ONLY_SHIFTS: ese set usa
    # comparación exacta contra el valor de fixed_shifts (ver bloque
    # "TURNOS MANUAL-ONLY"), y el valor que ve el solver ahí es la pill
    # "DOBLE" (no el código concreto DBL_xx). El bloqueo "nunca auto-asignable"
    # de los dobles se aplica aparte, en el bloque "TURNOS DOBLES (DBL_*)".
    previous_codes = [code for code in list(SHIFTS.keys()) if code.startswith(DOUBLE_SHIFT_PREFIX)]
    for code in previous_codes:
        SHIFTS.pop(code, None)
    SHIFT_NAMES = [s for s in SHIFT_NAMES if not s.startswith(DOUBLE_SHIFT_PREFIX)]

    max_hours = resolve_max_double_shift_hours(config)

    components = [code for code in list(SHIFTS.keys()) if _is_double_shift_component_eligible(code)]

    generated = {}
    for s1 in components:
        h1 = SHIFTS[s1]
        if not h1 or (h1 & NIGHT_HOURS_RANGE):
            continue  # s1 vacío o toca la franja nocturna
        for s2 in components:
            if s2 == s1:
                continue
            h2 = SHIFTS[s2]
            if not h2:
                continue
            if max(h1) + 1 != min(h2):
                continue  # no contiguos
            union_hours = h1 | h2
            if len(union_hours) > max_hours:
                continue
            start_wall = min(union_hours) % 24
            end_wall = (max(union_hours) + 1) % 24
            code = f"{DOUBLE_SHIFT_PREFIX}{start_wall:02d}-{end_wall:02d}"
            if code in generated and generated[code] != union_hours:
                continue  # colisión de nombre con horas distintas: se ignora
            generated[code] = union_hours

    for code, hours in generated.items():
        SHIFTS[code] = set(hours)
        if code not in SHIFT_NAMES:
            SHIFT_NAMES.append(code)

    return list(generated.keys())


def ensure_manual_shift_code(start_hour, end_hour):
    global SHIFT_NAMES

    if end_hour == start_hour:
        end_hour = (start_hour + 5) % 24

    code = f"{MANUAL_SHIFT_PREFIX}{start_hour:02d}-{end_hour:02d}"
    effective_end = end_hour + 24 if end_hour <= start_hour else end_hour
    SHIFTS[code] = set(range(start_hour, effective_end))
    if code not in SHIFT_NAMES:
        SHIFT_NAMES.append(code)
    return code

def coverage_bounds(h: int, day: str = None, standard_mode: bool = False, num_emps: int = 9, special_day_mode: str = None):
    """Límites de cobertura según hora y día.
    
    REGLAS (Weekdays):
      h5: exactamente 2  |  h6: min 3  |  h7-h10: hard min 3, soft target 4
      h11: min 3  |  h12: min 3
      h13-h16: min 3  |  h17-h19: hard min 3, soft target 4
      h20-h22: exactamente 2  |  h23-h28: exactamente 1
    
    Hard min=3 at peak hours guarantees feasibility; existing soft constraints
    (500k penalty) strongly push toward 4 people during h7-h10 and h17-h19.
    
    DOMINGO (`sunday`) y días con excepción `sunday_like`: 5-6 y noche con reglas propias;
    7:00-19:00 exactamente 3 personas (min=max=3).
    """
    N = num_emps  # max employees (used as upper bound for 'min' constraints)
    
    mode = special_day_mode or (
        SPECIAL_DAY_MODE_SUNDAY if day == "Dom" else SPECIAL_DAY_MODE_NORMAL
    )

    if mode == SPECIAL_DAY_MODE_CLOSED:
        return (0, 0)

    if mode == SPECIAL_DAY_MODE_HOLY_THURSDAY:
        if h == 5: return (2, 2)
        if h == 6: return (2, 3)
        if h == 7: return (3, N)
        if 8 <= h <= 12: return (4, N)
        if 13 <= h <= 19: return (3, N)   # Afternoon drops to 3 from 1pm
        if 20 <= h <= 21: return (2, 2)
        if 22 <= h <= 28: return (1, 1)
        return (3, N)

    if is_sunday_style_mode(mode):
        if standard_mode:
            # Domingo / día tipo domingo: 7-19 con exactamente 3 (evita 4 en tardes por mx=N)
            if 5 <= h <= 6:
                return (2, 2)
            if 7 <= h <= 19:
                return (3, 3)
            if 20 <= h <= 21:
                return (2, 2)
            if 22 <= h <= 28:
                return (1, 1)
        else:
            # Short-staffed: misma meta 7-19 = exactamente 3
            if h == 5:
                return (2, 2)
            if h == 6:
                return (2, 5)
            if 7 <= h <= 19:
                return (3, 3)
            if 20 <= h <= 21:
                return (2, 2)
            if h == 22:
                return (1, 2)
            if 23 <= h <= 28:
                return (1, 1)
            return (3, 3)
    
    # Weekdays (Lun-Sáb)
    if h == 5:
        if standard_mode:
            return (2, 2)             # 10+ empleados: exactamente 2 a las 5am
        return (2, 3)                 # Short-staffed: permitir 3 para habilitar Q1 + T1×2
    if h == 6: return (2, N)          # Hard min 2 (soft target 3, J_07-17 compatibility)
    if 7 <= h <= 10: return (3, N)    # Hard min 3 (soft target 4 via 500k penalty)
    if h == 11: return (3, N)         # Mínimo 3
    if h == 12: return (3, N)         # Mínimo 3
    if 13 <= h <= 16: return (3, N)   # Mínimo 3
    if 17 <= h <= 19: return (3, N)   # Hard min 3 (soft target 4 via 500k penalty)
    if 20 <= h <= 22: return (2, 2)   # Exactamente 2
    if 23 <= h <= 28: return (1, 1)   # Exactamente 1
    return (3, N)


def effective_coverage_bounds(h: int, day: str = None, standard_mode: bool = False, num_emps: int = 9, special_day_mode: str = None, cap_value: int = None):
    mn, mx = coverage_bounds(h, day, standard_mode, num_emps, special_day_mode=special_day_mode)
    effective_cap = cap_value if cap_value else OVERSTAFF_CAP_VALUE
    if day in OVERSTAFF_POLICY_DAYS and mx > effective_cap:
        mx = effective_cap
    return mn, mx


def touches_night(shift_name: str) -> bool:
    """Verifica si un turno cubre la franja 20:00-23:00"""
    if not shift_name or shift_name not in SHIFTS:
        return False
    shift_hours = SHIFTS[shift_name]
    return any(h in shift_hours for h in [20, 21, 22])


def _normalize_history_schedule(schedule):
    if isinstance(schedule, dict):
        return schedule
    if isinstance(schedule, str):
        try:
            parsed = json.loads(schedule)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _rotation_token_for_shift(shift_name: str, employee_data: dict):
    if shift_name not in SHIFTS or shift_name in IGNORED_ROTATION_SHIFTS:
        return None
    if shift_name.startswith("Q") or shift_name.startswith("X_") or shift_name.startswith("J_"):
        return None
    if shift_name in HEAVY_EXTENDED_SHIFTS:
        return None

    shift_hours = SHIFTS.get(shift_name, set())
    if not shift_hours:
        return None

    if employee_data.get("gender") == "F":
        return "AM" if min(shift_hours) < 12 else "PM"

    return shift_name


def _history_entry_special_days(entry):
    if not isinstance(entry, dict):
        return {}
    return normalize_special_day_modes(entry.get("special_days", {}))


def _history_day_is_neutral(entry, day):
    return _history_entry_special_days(entry).get(day) in HISTORY_NEUTRAL_SPECIAL_DAY_MODES


def _extract_rotation_token_from_week(employee_data: dict, weekly_schedule: dict, ignored_days=None):
    tokens = []
    ignored_days = set(ignored_days or [])
    for day in ROTATION_HISTORY_CORE_DAYS:
        if day in ignored_days:
            continue
        token = _rotation_token_for_shift(weekly_schedule.get(day), employee_data)
        if token:
            tokens.append(token)

    if not tokens:
        return None

    counts = Counter(tokens)
    top_count = max(counts.values())
    for token in reversed(tokens):
        if counts[token] == top_count:
            return token
    return tokens[-1]


def _fallback_rotation_pool(employee_data: dict, allow_long: bool):
    if employee_data.get("gender") == "F":
        return list(WOMEN_ROTATION_TOKENS)

    pool = []
    for shift_name in SHIFT_NAMES:
        if shift_name in IGNORED_ROTATION_SHIFTS:
            continue
        if shift_name.startswith("Q"):
            continue
        if shift_name in HEAVY_EXTENDED_SHIFTS:
            continue
        if not allow_long and (shift_name.startswith("J_") or shift_name.startswith("X_")):
            continue
        if not employee_data.get("can_do_night", True) and touches_night(shift_name):
            continue

        token = _rotation_token_for_shift(shift_name, employee_data)
        if token and token not in pool:
            pool.append(token)
    return pool

def _count_streak(tokens: list) -> int:
    """Counts how many consecutive identical tokens appear at the end of the list.

    Examples:
        ["AM", "PM", "PM", "PM"] -> 3
        ["PM", "AM"]              -> 1
        []                        -> 0
    """
    if not tokens:
        return 0
    last = tokens[-1]
    streak = 0
    for t in reversed(tokens):
        if t == last:
            streak += 1
        else:
            break
    return streak

def build_rotation_history_context(employee_names, employee_map, history_entries, allow_long: bool, night_person_name=None, alternating_pair_members=None, rotation_enabled=True):
    normalized_history = []
    for entry in history_entries or []:
        if not isinstance(entry, dict):
            continue
        normalized_history.append({
            "name": entry.get("name"),
            "schedule": _normalize_history_schedule(entry.get("schedule", {})),
            "special_days": _history_entry_special_days(entry),
        })

    context = {}
    for employee_name in employee_names:
        employee_data = employee_map.get(employee_name, {})
        fixed_days_count = len(employee_data.get("fixed_shifts", {}) or {})

        if (
            employee_name == night_person_name
            or employee_data.get("is_refuerzo")
            or employee_data.get("forced_quebrado", False)
            or fixed_days_count > 5
        ):
            continue

        recent_tokens = []
        distinct_history_tokens = []
        for entry in normalized_history:
            weekly_schedule = entry.get("schedule", {}).get(employee_name, {})
            ignored_days = {
                day for day, mode in (entry.get("special_days", {}) or {}).items()
                if mode in HISTORY_NEUTRAL_SPECIAL_DAY_MODES
            }
            token = _extract_rotation_token_from_week(
                employee_data,
                weekly_schedule,
                ignored_days=ignored_days,
            )
            if not token:
                continue
            recent_tokens.append(token)
            if token not in distinct_history_tokens:
                distinct_history_tokens.append(token)

        is_alternating = employee_name in (alternating_pair_members or set())
        if is_alternating:
            # Alternating pair member: always use AM/PM token cycle
            pool = list(WOMEN_ROTATION_TOKENS)
        elif rotation_enabled and recent_tokens:
            # Global rotation enabled: classify history into AM/PM and rotate
            pool = list(WOMEN_ROTATION_TOKENS)
            # Re-classify recent_tokens to AM/PM so penalties compare correctly
            recent_tokens = [_am_pm_token(t) or t for t in recent_tokens]
        elif len(distinct_history_tokens) >= 2:
            pool = list(distinct_history_tokens)
        else:
            # No history and rotation disabled; preserve current shift via
            # turno_principal consistency (900k/day reward).
            continue

        if len(pool) <= 1:
            continue

        # Count AM/PM balance and consecutive streak at the end of history
        am_pm_tokens = [t for t in recent_tokens if t in ("AM", "PM")]
        am_count = am_pm_tokens.count("AM")
        pm_count = am_pm_tokens.count("PM")
        streak = _count_streak(am_pm_tokens)

        context[employee_name] = {
            "recent_tokens": recent_tokens,
            "pool": pool,
            "cycle_weeks": len(pool),
            "am_count": am_count,
            "pm_count": pm_count,
            "streak": streak,
        }

    return context


def _fixed_shift_token_for_day(employee_data: dict, day: str):
    fixed_shift = (employee_data.get("fixed_shifts") or {}).get(day)
    if fixed_shift not in SHIFTS or fixed_shift in IGNORED_ROTATION_SHIFTS:
        return None

    shift_hours = SHIFTS.get(fixed_shift, set())
    if not shift_hours:
        return None

    return "AM" if min(shift_hours) < 12 else "PM"


def _fixed_dominant_token(employee_data: dict):
    """Retorna el token AM/PM dominante entre los turnos fijos (manuales) del empleado.

    Si la mayoría de los turnos fijos son AM → retorna 'AM'.
    Si la mayoría son PM                    → retorna 'PM'.
    Si no hay turnos fijos, o hay empate    → retorna None.

    Se usa para ignorar las streak/balance penalties cuando una asignación manual
    ya dictamina el turno de la semana (el usuario eligió eso a propósito).
    """
    fixed_map = employee_data.get("fixed_shifts") or {}
    am = 0
    pm = 0
    for day, shift in fixed_map.items():
        if shift not in SHIFTS or shift in IGNORED_ROTATION_SHIFTS:
            continue
        hours = SHIFTS.get(shift, set())
        if not hours:
            continue
        if min(hours) < 12:
            am += 1
        else:
            pm += 1
    if am == 0 and pm == 0:
        return None
    if am > pm:
        return "AM"
    if pm > am:
        return "PM"
    return None  # empate → no hay dominante claro


def _has_working_fixed_shift(employee_data: dict, day: str = None) -> bool:
    fixed_map = employee_data.get("fixed_shifts") or {}
    days_to_check = [day] if day is not None else list(fixed_map.keys())

    for target_day in days_to_check:
        fixed_shift = fixed_map.get(target_day)
        if fixed_shift in SHIFTS and fixed_shift not in IGNORED_ROTATION_SHIFTS:
            return True

    return False


def _working_fixed_shift_days(employee_data: dict):
    fixed_map = employee_data.get("fixed_shifts") or {}
    return [
        day for day in DAYS
        if fixed_map.get(day) in SHIFTS and fixed_map.get(day) not in IGNORED_ROTATION_SHIFTS
    ]


def _sanitize_fixed_shifts(fixed_map):
    cleaned = {}
    for day, shift_code in (fixed_map or {}).items():
        if shift_code == "D4_13-22" and day != "Dom":
            continue
        cleaned[day] = shift_code
    return cleaned

class ShiftScheduler:
    def __init__(self, employees_config, global_config, history_data=None):
        normalized_employees = []
        for employee_data in employees_config:
            normalized = dict(employee_data)
            normalized["fixed_shifts"] = _sanitize_fixed_shifts(employee_data.get("fixed_shifts") or {})
            normalized_employees.append(normalized)

        self.employees = [e['name'] for e in normalized_employees]
        self.emp_data = {e['name']: e for e in normalized_employees}
        self.special_day_modes = normalize_special_day_modes((global_config or {}).get("special_days", {}))
        self.day_modes = {
            day: get_effective_day_mode(day, self.special_day_modes)
            for day in DAYS
        }
        self.config = dict(global_config or {})
        self.config["special_days"] = dict(self.special_day_modes)
        # [] es falsy: no convertir a {} o normalize_history_entries no recibe lista vacía bien
        # para todos los code paths; None → sin historial.
        if history_data is None:
            self.history = []
        elif isinstance(history_data, list):
            self.history = history_data
        elif isinstance(history_data, dict):
            self.history = history_data
        else:
            self.history = []
        
        # INJECT REFUERZO si está activado
        self.refuerzo_name = str(self.config.get('refuerzo_nombre') or 'Refuerzo')
        if self.config.get('use_refuerzo', False):
            ref_partial = self.config.get('refuerzo_partial_mode', False)
            self.employees.append(self.refuerzo_name)

            # Build fixed_shifts from per-day schedule for partial mode
            ref_fixed = {}
            if ref_partial:
                schedule = self.config.get('refuerzo_schedule', {}) or {}
                manual_only_allowed = list(MANUAL_ONLY_SHIFTS)
                for day, times in schedule.items():
                    if isinstance(times, dict) and times.get("start") and times.get("end"):
                        start_h = _parse_refuerzo_hour(times.get("start"), 7)
                        end_h = _parse_refuerzo_hour(times.get("end"), 12)
                        if end_h == start_h:
                            end_h = (start_h + 5) % 24
                        code = f"{MANUAL_SHIFT_PREFIX}{start_h:02d}-{end_h:02d}"
                        ref_fixed[day] = code

            self.emp_data[self.refuerzo_name] = {
                "name": self.refuerzo_name,
                "gender": "M",
                "can_do_night": True,
                "fixed_shifts": ref_fixed,
                "strict_preferences": True,  # Always hard constraints — MUST work selected days
                "is_refuerzo": True,  # Always flagged — controls OFF/flex_off exclusions
                                     # Partial mode includes it explicitly in active_count + flexibles
            }

            # In partial mode, OFF the refuerzo on non-active days
            if ref_partial and ref_fixed:
                all_days = ["Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue"]
                for d in all_days:
                    if d not in ref_fixed:
                        ref_fixed[d] = "OFF"
        
        # NEW: inject additional named refuerzos from refuerzos[] list
        _new_refuerzos = _normalize_refuerzos(self.config)
        _all_days = ["Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue"]
        for _ref in _new_refuerzos:
            _nombre = _ref.get('nombre', '').strip()
            if not _nombre or _nombre in self.employees:
                continue  # skip duplicates
            self.employees.append(_nombre)
            _tipo = str(_ref.get('tipo') or 'personalizado').lower()
            _ref_sched = _ref.get('schedule', {}) or {}

            if _tipo == 'personalizado':
                # Hard-constraint mode: solver MUST use exactly the configured schedule,
                # EXCEPT days marked AUTO — those are active but the solver picks the
                # shift (or leaves OFF).  Mixed fixed/auto per day.
                _ref_fixed = {}
                _ref_auto = []
                for _day, _times in _ref_sched.items():
                    if not isinstance(_times, dict):
                        continue
                    if _times.get('auto'):
                        _ref_auto.append(_day)
                        continue
                    if _times.get('start') and _times.get('end'):
                        _sh = _parse_refuerzo_hour(_times.get('start'), 7)
                        _eh = _parse_refuerzo_hour(_times.get('end'), 12)
                        if _eh == _sh:
                            _eh = (_sh + 5) % 24
                        _ref_fixed[_day] = f"{MANUAL_SHIFT_PREFIX}{_sh:02d}-{_eh:02d}"
                for _d in _all_days:
                    if _d not in _ref_fixed and _d not in _ref_auto:
                        _ref_fixed[_d] = "OFF"
                self.emp_data[_nombre] = {
                    "name": _nombre,
                    "gender": "M",
                    "can_do_night": False,
                    "fixed_shifts": _ref_fixed,
                    "strict_preferences": True,
                    "is_refuerzo": True,
                    "refuerzo_tipo": _tipo,
                    "refuerzo_auto_days": _ref_auto,
                }
            else:
                # Non-personalizado modes: solver picks the shift within allowed set.
                # Only force OFF on inactive days (OFF is always a hard constraint).
                if _tipo == 'sabado':
                    _active_days = ['Sáb']
                else:
                    _active_days = [d for d in _all_days if d in _ref_sched]
                _off_days = {d: "OFF" for d in _all_days if d not in _active_days}
                self.emp_data[_nombre] = {
                    "name": _nombre,
                    "gender": "M",
                    "can_do_night": _tipo in ('nocturno', 'automatico'),
                    "fixed_shifts": _off_days,
                    "strict_preferences": False,
                    "is_refuerzo": True,
                    "refuerzo_tipo": _tipo,
                    "refuerzo_active_days": _active_days,
                }

        # Determine roles based on input data
        # Refuerzo is NOT flexible for Sunday rotation, NOT night replacement, etc.
        # UNLESS refuerzo_partial_mode is active — then it joins flexibles (but not night replacements).
        ref_partial = self.config.get('refuerzo_partial_mode', False)
        self.flexibles = [
            e for e in self.employees
            if not self.emp_data[e].get('is_refuerzo') or (ref_partial and e == self.refuerzo_name)
        ]
        self.night_replacements = [e for e in self.employees if self.emp_data[e].get('can_do_night', True) and not self.emp_data[e].get('is_refuerzo')]

    def _clone_employee_configs(self):
        cloned = []
        for employee_name in self.employees:
            employee_data = self.emp_data[employee_name]
            if employee_data.get("is_refuerzo", False):
                continue
            cloned.append(copy.deepcopy(employee_data))
        return cloned

    def _format_diagnostic_days(self, working_days):
        labels = []
        for day in working_days:
            if day == "Jue" and self.day_modes.get(day) == SPECIAL_DAY_MODE_HOLY_THURSDAY:
                labels.append("Jue (Santo)")
            elif self.day_modes.get(day) == SPECIAL_DAY_MODE_CLOSED:
                labels.append(f"{day} (cerrado)")
            else:
                labels.append(day)
        return ", ".join(labels)

    def _run_diagnostic_trial_status(self, employees_config, config_overrides=None, max_time=None):
        """Corre un solve de prueba con overrides y devuelve el status resultante."""
        trial_config = copy.deepcopy(self.config)
        trial_config.update(config_overrides or {})
        trial_config["special_days"] = dict(self.special_day_modes)
        trial_config["_skip_infeasible_diagnosis"] = True
        trial_config["log_search_progress"] = False
        trial_config["max_time"] = max_time or INFEASIBLE_DIAGNOSTIC_MAX_TIME_SECONDS
        trial_scheduler = ShiftScheduler(
            employees_config,
            trial_config,
            history_data=copy.deepcopy(self.history),
        )
        return trial_scheduler.solve().get("status")

    def _run_diagnostic_trial(self, employees_config, config_overrides=None):
        return self._run_diagnostic_trial_status(employees_config, config_overrides) == "Success"

    def _build_strict_conflict_message(self, employee_name, working_days):
        day_text = self._format_diagnostic_days(working_days)
        message = (
            "No se pudo generar horario con las restricciones actuales. "
            f"El conflicto más probable está en los turnos fijos estrictos de {employee_name}"
        )
        if day_text:
            message += f" ({day_text})"
        message += "."
        if len(working_days) >= 5:
            message += " Con tantos días obligatorios, el modelo ya no logra acomodar su libre semanal."
        message += " Si ese patrón debe ser preferido y no obligatorio, desactive 'Preferencias estrictas' o deje al menos un día en Auto."
        return message

    def _diagnose_infeasible_result(self):
        if self.config.get("_skip_infeasible_diagnosis"):
            return None

        base_employees = self._clone_employee_configs()

        # 0. COBERTURA / TOPE DE PERSONAS EN PISTA
        # Antes de culpar a las preferencias estrictas, probar si el problema es
        # que la cobertura necesita más personas en pista de las permitidas.
        # El modelo base ya está PROBADO infeasible; si al subir el tope al máximo
        # deja de ser infeasible (Success o incluso Unknown, o sea que desaparece la
        # prueba de infeasibilidad), el tope es la restricción que ata. Se le da tiempo
        # suficiente al solve de prueba para que encuentre una solución factible.
        # Corre UNA sola vez (el diagnóstico se invoca una vez desde solve()).
        current_cap = resolve_overstaff_cap(self.config)
        cover_time = INFEASIBLE_DIAGNOSTIC_COVERAGE_MAX_TIME_SECONDS
        cap_helps = (
            current_cap < OVERSTAFF_CAP_MAX
            and self._run_diagnostic_trial_status(
                base_employees, {"max_simultaneous": OVERSTAFF_CAP_MAX}, max_time=cover_time
            ) != "Infeasible"
        )
        if cap_helps:
            suggested = OVERSTAFF_CAP_MAX
            for candidate_cap in range(current_cap + 1, OVERSTAFF_CAP_MAX):
                if self._run_diagnostic_trial_status(
                    base_employees, {"max_simultaneous": candidate_cap}, max_time=cover_time
                ) != "Infeasible":
                    suggested = candidate_cap
                    break
            return {
                "message": (
                    "No se pudo generar horario: la cobertura requiere más personas en "
                    f"pista de las permitidas. El máximo actual es {current_cap} personas al "
                    f"mismo tiempo, pero el personal activo (incluidos los refuerzos) necesita "
                    f"al menos {suggested} durante varias horas. "
                    f"Subí 'Máximo de personas en pista' a {suggested} o más, o reducí "
                    "personal/refuerzos en los días pico."
                ),
                "reason": "coverage_over_cap",
                "suggested_max_simultaneous": suggested,
            }

        if self.config.get("strict_preferences", False):
            if self._run_diagnostic_trial(base_employees, {"strict_preferences": False}):
                return {
                    "message": (
                        "No se pudo generar horario con las restricciones actuales. "
                        "El conflicto más probable está en 'Preferencias estrictas' globales. "
                        "Al relajarlas, el modelo vuelve a ser factible."
                    )
                }

        night_person_name = self.config.get("fixed_night_person")
        strict_candidates = []
        for employee_name in self.employees:
            employee_data = self.emp_data[employee_name]
            if employee_data.get("is_refuerzo", False):
                continue
            if employee_data.get("is_jefe_pista", False):
                continue
            if employee_name == night_person_name:
                continue
            if not employee_data.get("strict_preferences", False):
                continue

            working_days = _working_fixed_shift_days(employee_data)
            if not working_days:
                continue

            strict_candidates.append((employee_name, working_days))
            trial_employees = self._clone_employee_configs()
            for trial_employee in trial_employees:
                if trial_employee.get("name") == employee_name:
                    trial_employee["strict_preferences"] = False
                    break
            if self._run_diagnostic_trial(trial_employees):
                return {
                    "message": self._build_strict_conflict_message(employee_name, working_days)
                }

        if strict_candidates:
            names = ", ".join(name for name, _ in strict_candidates)
            return {
                "message": (
                    "No se pudo generar horario con las restricciones actuales. "
                    f"Revise los turnos fijos estrictos de: {names}."
                )
            }

        return None

    def assign_tasks(self, schedule):
        """Assign daily tasks (Baños, Tanques, Oficina+Basureros) POST-HOC.
        
        FAIR ROTATION: Uses a weekly task counter to distribute tasks equitably.
        No gender preference. Jefe de Pista only eligible on Sáb.
        Night shift workers (N_22-05), OFF, VAC, and PERM are excluded.
        Refuerzo with fewer than 3 working days gets no tasks.
        """
        schedule_employees = [e for e in self.employees if e in schedule]
        res_tasks = {e: {d: None for d in DAYS} for e in schedule_employees}
        task_count = {e: 0 for e in schedule_employees}
        
        # Count legacy refuerzo working days — skip if < 3
        _ref_name = self.refuerzo_name
        refuerzo_days = sum(
            1 for d in DAYS
            if schedule.get(_ref_name, {}).get(d, "OFF") not in ("OFF", "VAC", "PERM")
        ) if _ref_name in schedule else 0
        skip_refuerzo = refuerzo_days < 3

        for d in DAYS:
            if self.day_modes.get(d) == SPECIAL_DAY_MODE_CLOSED:
                continue

            # Config cache — used by is_task_enabled and oficina check
            _ct = self.config.get("cleaning_tasks") or {}

            # Jefe de pista config (stored as separate column jefe_config)
            _jc = self.config.get("jefe_config") or {}
            jefe_enabled = _jc.get("enabled", False)
            jefe_exclude_regular = _jc.get("exclude_regular", True)
            jefe_assignment = _jc.get("assignment", {})

            JEFE_TASKS = ["banos", "tanques", "oficina", "calibracion", "canos", "canos_glp"]

            def has_jefe_assignment_on_day(day):
                """Check if jefe has any task assigned for this day per the 6×7 matrix."""
                for task in JEFE_TASKS:
                    if jefe_assignment.get(task, {}).get(day, False):
                        return True
                return False

            def is_task_enabled(task_id, day):
                # If config has an explicit value for task_id×day, use it
                if isinstance(_ct, dict) and day in _ct and task_id in _ct[day]:
                    return _ct[day][task_id]
                # Legacy / default fallbacks
                if task_id in ("am_tanques", "pm_tanques") and day == "Dom": return False
                if task_id == "pm_tanques" and day == "Sáb": return False
                if task_id == "oficina": return day in ("Lun", "Jue")
                if task_id == "calibracion": return day == "Mar"
                if task_id == "canos": return day == "Lun"
                if task_id == "canos_glp": return day == "Jue"
                return True

            available = []
            for e in schedule_employees:
                if e == _ref_name and skip_refuerzo:
                    continue
                shift = schedule[e].get(d, "OFF")
                if shift in ["OFF", "VAC", "PERM", "N_22-05"]:
                    continue
                is_jefe = self.emp_data[e].get('is_jefe_pista', False)
                if is_jefe:
                    if not jefe_enabled:
                        continue  # Jefe mode OFF → no tasks at all
                    jefe_has_task = has_jefe_assignment_on_day(d)
                    if jefe_has_task and jefe_exclude_regular:
                        continue  # Tiene tarea específica asignada hoy → no lo metas en limpieza regular
                    if not jefe_has_task:
                        continue  # Sin tarea asignada en la matrix para hoy
                    # Si llegó acá: jefe puede hacer tareas regulares hoy
                shift_hours = get_shift_hours_set(shift)
                if not shift_hours:
                    continue
                available.append({
                    'name': e, 'shift': shift,
                    'start': min(shift_hours), 'hours': shift_hours,
                    'has_am': any(h < 12 for h in shift_hours),
                    'has_pm': any(h >= 12 for h in shift_hours),
                    'is_quebrado': shift.startswith('Q'),
                })
            
            def fair_pick(pool):
                if not pool: return None
                pool.sort(key=lambda w: task_count[w['name']])
                return pool[0]
            
            def q_label(base, is_am):
                """Genera etiqueta de tarea con indicador AM/PM.
                is_am=True para tareas del pool matutino, False para vespertino.
                ANTES usaba worker['start'] pero eso daba ↑AM incorrecto para
                empleados con turno temprano pero asignados a tareas PM."""
                return f"{base} {'↑AM' if is_am else '↓PM'}"
            
            assigned_today = set()
            # AM pool: trabajadores que están presentes durante la mañana (5am-12pm).
            # NO restringimos a start<=5 porque limpiar baños lo puede hacer cualquiera
            # que esté trabajando en la mañana, no solo el que abre a las 5am.
            am_pool = [w for w in available if w['has_am']]
            
            # AM Tanques: SOLO a las 5am — necesita alguien que empiece exactamente a las 5
            am_tanques_pool = [w for w in available if w['start'] <= 5]
            
            # PM pool: tareas se hacen de 3pm (15:00) en adelante
            # ANTES usaba w['has_pm'] (cualquier hora ≥ 12) — incorrecto, PM empieza a las 15
            pm_pool = [w for w in available if any(h >= 15 for h in w['hours'])]
            
            # PM Tanques: después de 4pm (16:00)
            pm_tanques_pool = [w for w in available if any(h >= 16 for h in w['hours'])]

            def pick_one(pool, exclude=frozenset()):
                """Pick the worker with fewest tasks this week.
                A worker already assigned a task today is NEVER re-picked (no fallback).
                Returns None if no eligible worker is available."""
                candidates = [w for w in pool if w['name'] not in exclude]
                return fair_pick(candidates)
            
            # --- AM TANQUES (debe ser a las 5am SÍ O SÍ) ---
            if is_task_enabled("am_tanques", d):
                pick = pick_one(am_tanques_pool, assigned_today)
                if not pick:
                    pick = pick_one(am_pool, assigned_today)
                if pick:
                    res_tasks[pick['name']][d] = q_label("Tanques", True)
                    assigned_today.add(pick['name']); task_count[pick['name']] += 1
            
            # --- AM BAÑOS (entre 5am-12pm) ---
            if is_task_enabled("am_banos", d):
                pick = pick_one(am_pool, assigned_today)
                if pick:
                    oficina_default = d in ["Lun", "Jue"]
                    oficina_enabled = isinstance(_ct, dict) and d in _ct and _ct[d].get("oficina", oficina_default)
                    is_oficina_day = is_weekday_like_mode(get_effective_day_mode(d, self.day_modes)) and oficina_enabled
                    label = "Oficina + Basureros + Baños" if is_oficina_day else "Baños"
                    res_tasks[pick['name']][d] = q_label(label, True)
                    assigned_today.add(pick['name']); task_count[pick['name']] += 1
            
            # --- PM TANQUES (después de 4pm) ---
            if is_task_enabled("pm_tanques", d):
                pick = pick_one(pm_tanques_pool, assigned_today)
                if not pick:
                    pick = pick_one(pm_pool, assigned_today)
                if pick:
                    res_tasks[pick['name']][d] = q_label("Tanques", False)
                    assigned_today.add(pick['name']); task_count[pick['name']] += 1
            
            # --- PM BAÑOS (después de 3pm) ---
            if is_task_enabled("pm_banos", d):
                pick = pick_one(pm_pool, assigned_today)
                if pick:
                    res_tasks[pick['name']][d] = q_label("Baños", False)
                    assigned_today.add(pick['name']); task_count[pick['name']] += 1

            # --- JEFE DE PISTA TASKS (Calibración, Caños, Caños GLP) ---
            # Solo si jefe_enabled y hay tarea activa hoy
            if jefe_enabled and has_jefe_assignment_on_day(d):
                jefe_names = [e for e in schedule_employees if self.emp_data[e].get('is_jefe_pista', False)]
                if jefe_names:
                    jefe_name = jefe_names[0]
                    jefe_shift = schedule.get(jefe_name, {}).get(d, "OFF")
                    if jefe_shift not in ("OFF", "VAC", "PERM", "N_22-05"):
                        jefe_hours_set = get_shift_hours_set(jefe_shift)
                        if jefe_hours_set:
                            if is_task_enabled("calibracion", d) and jefe_name not in assigned_today:
                                res_tasks[jefe_name][d] = "Calibración"
                                assigned_today.add(jefe_name); task_count[jefe_name] += 1
                            if is_task_enabled("canos", d) and jefe_name not in assigned_today:
                                res_tasks[jefe_name][d] = "Caños"
                                assigned_today.add(jefe_name); task_count[jefe_name] += 1
                            if is_task_enabled("canos_glp", d) and jefe_name not in assigned_today:
                                res_tasks[jefe_name][d] = "Caños GLP"
                                assigned_today.add(jefe_name); task_count[jefe_name] += 1

        return res_tasks

    def _build_rest_between_shifts_report(
        self, schedule, most_recent_schedule, shift_min_hour, shift_max_hour, shift_is_working, applied_rest_hours=None
    ):
        """Huecos entre turnos consecutivos (hist Jue→Vie y días dentro de la semana)."""
        non_working = frozenset({"OFF", "VAC", "PERM"})
        target = int(self.config.get("min_rest_hours_target", 12))
        applied = int(applied_rest_hours) if applied_rest_hours is not None else target
        per_employee = {}
        for e in self.employees:
            if self.emp_data[e].get("allow_no_rest", False):
                per_employee[e] = {
                    "min_gap_hours": None,
                    "gaps": [],
                    "skipped": True,
                    "meets_target": True,
                    "meets_applied": True,
                }
                continue
            gaps = []
            min_g = None
            last_j = (most_recent_schedule.get(e) or {}).get("Jue")
            sv = (schedule.get(e) or {}).get("Vie")
            if last_j and last_j not in non_working and sv and sv not in non_working:
                h = rest_hours_between_shifts(last_j, sv, shift_min_hour, shift_max_hour, shift_is_working)
                if h is not None:
                    gaps.append({
                        "from": "Jue (histórico)",
                        "to": "Vie",
                        "hours": h,
                        "meets_target": h >= target,
                        "meets_applied": h >= applied,
                    })
                    min_g = h if min_g is None else min(min_g, h)
            for i in range(len(DAYS) - 1):
                d1, d2 = DAYS[i], DAYS[i + 1]
                s1 = (schedule.get(e) or {}).get(d1)
                s2 = (schedule.get(e) or {}).get(d2)
                if not s1 or not s2 or s1 in non_working or s2 in non_working:
                    continue
                h = rest_hours_between_shifts(s1, s2, shift_min_hour, shift_max_hour, shift_is_working)
                if h is None:
                    continue
                gaps.append({
                    "from": d1,
                    "to": d2,
                    "hours": h,
                    "meets_target": h >= target,
                    "meets_applied": h >= applied,
                })
                min_g = h if min_g is None else min(min_g, h)
            per_employee[e] = {
                "min_gap_hours": min_g,
                "gaps": gaps,
                "meets_target": (min_g >= target) if min_g is not None else True,
                "meets_applied": (min_g >= applied) if min_g is not None else True,
            }
        return {"per_employee": per_employee, "target_hours": target, "applied_hours": applied}

    def solve(self):
        current_refuerzo_custom_shift = sync_refuerzo_custom_shift(self.config)
        sync_custom_shifts(self.config)  # Load custom shifts with priorities
        sync_double_shifts(self.config)  # Load configurable double-shift (DBL_*) combos
        default_diurno_refuerzo_shift = ensure_manual_shift_code(7, 12)
        # Rest handling: the hard floor is 8h (absolute minimum between shifts).
        # Rest between the floor and the target (12h) is modeled as a SOFT
        # penalty inside the solver, so it shortens rest only when coverage or
        # schedule consistency (heavier objective terms) genuinely require it.
        rest_floor = max(8, int(self.config.get("min_rest_hours_floor", 8)))
        rest_target = max(rest_floor, min(int(self.config.get("min_rest_hours_target", 12)), 24))
        last_out = self._solve_with_min_rest(
            rest_floor, current_refuerzo_custom_shift, default_diurno_refuerzo_shift
        )
        if last_out.get("status") == "Success":
            md = last_out.setdefault("metadata", {})
            # Applied = worst rest actually present in the produced schedule
            # (capped at the target: resting more than the target still counts
            # as meeting it).
            observed = None
            rest_report = md.get("rest_between_shifts") or {}
            for _info in (rest_report.get("per_employee") or {}).values():
                g = _info.get("min_gap_hours")
                if g is not None:
                    observed = g if observed is None else min(observed, g)
            applied = rest_target if observed is None else min(rest_target, int(observed))
            md["min_rest_hours_applied"] = applied
            md["min_rest_hours_target"] = rest_target
            md["min_rest_hours_floor"] = rest_floor
            if applied < rest_target:
                logger.warning(
                    "Horario factible con descanso mínimo entre turnos de %sh (objetivo %sh).",
                    applied,
                    rest_target,
                )
            return last_out
        if last_out is None:
            last_out = {"status": "Infeasible", "message": "No se pudo generar horario."}
        # Diagnóstico detallado: corre UNA sola vez acá (no por nivel de descanso).
        if last_out.get("status") == "Infeasible" and not self.config.get("_skip_infeasible_diagnosis"):
            diagnosis = self._diagnose_infeasible_result()
            if diagnosis and diagnosis.get("message"):
                last_out["message"] = diagnosis["message"]
                if diagnosis.get("reason"):
                    last_out["reason"] = diagnosis["reason"]
                if diagnosis.get("suggested_max_simultaneous"):
                    last_out["suggested_max_simultaneous"] = diagnosis["suggested_max_simultaneous"]
        return last_out

    def _solve_with_min_rest(self, min_rest_hours: int, current_refuerzo_custom_shift, default_diurno_refuerzo_shift):
        model = cp_model.CpModel()

        employee_name_map = {}
        for emp in self.employees:
            normalized_name = emp.strip().lower()
            if normalized_name:
                employee_name_map[normalized_name] = emp

        def normalize_history_schedule(schedule_data, source_label="history"):
            """Normaliza schedule histórico (dict o JSON str) a nombres/días confiables."""
            parsed_schedule = schedule_data
            if isinstance(schedule_data, str):
                try:
                    parsed_schedule = json.loads(schedule_data)
                except json.JSONDecodeError:
                    logger.warning("No se pudo parsear schedule JSON en %s", source_label)
                    return {}

            if not isinstance(parsed_schedule, dict):
                logger.warning("Schedule inválido en %s: se esperaba dict/JSON", source_label)
                return {}

            normalized_schedule = {}
            for raw_emp_name, day_assignments in parsed_schedule.items():
                if not isinstance(raw_emp_name, str):
                    continue
                canonical_emp = employee_name_map.get(raw_emp_name.strip().lower())
                if not canonical_emp or not isinstance(day_assignments, dict):
                    continue

                if canonical_emp not in normalized_schedule:
                    normalized_schedule[canonical_emp] = {}

                for raw_day, shift_name in day_assignments.items():
                    if raw_day not in DAYS:
                        logger.warning(
                            "Día histórico inválido '%s' en %s para %s",
                            raw_day,
                            source_label,
                            canonical_emp,
                        )
                        continue
                    normalized_schedule[canonical_emp][raw_day] = shift_name

            return normalized_schedule

        def normalize_history_entries(history_obj):
            entries = []
            if isinstance(history_obj, list):
                for idx, entry in enumerate(history_obj):
                    if not isinstance(entry, dict):
                        continue
                    schedule_obj = entry.get("schedule", {})
                    normalized = normalize_history_schedule(schedule_obj, f"history[{idx}]")
                    entries.append({
                        "schedule": normalized,
                        "special_days": _history_entry_special_days(entry),
                    })
            elif isinstance(history_obj, dict) and history_obj:
                normalized = normalize_history_schedule(history_obj, "history[dict]")
                entries.append({
                    "schedule": normalized,
                    "special_days": _history_entry_special_days(history_obj),
                })
            return entries

        history_entries = normalize_history_entries(self.history)
        most_recent_entry = history_entries[-1] if history_entries else {}
        most_recent_schedule = most_recent_entry.get("schedule", {}) if most_recent_entry else {}
        day_modes = dict(self.day_modes)

        def is_special_sunday_like(day):
            return is_sunday_style_mode(day_modes.get(day, SPECIAL_DAY_MODE_NORMAL))

        def is_special_closed(day):
            return day_modes.get(day) == SPECIAL_DAY_MODE_CLOSED

        def is_weekday_like(day):
            return is_weekday_like_mode(day_modes.get(day))

        known_last_night_employee = set()
        for entry in reversed(history_entries):
            sched = entry.get("schedule", {})
            for e in self.employees:
                if e in known_last_night_employee:
                    continue
                e_sched = sched.get(e, {})
                if any(e_sched.get(d) == "N_22-05" for d in DAYS):
                    known_last_night_employee.add(e)

        # Precomputar propiedades de turnos para evitar llamadas repetidas en loops
        SHIFT_MIN_HOUR = {}
        SHIFT_MAX_HOUR = {}
        SHIFT_IS_WORKING = {}
        for _s in SHIFT_NAMES:
            _hours = SHIFTS[_s]
            if _hours:
                SHIFT_MIN_HOUR[_s] = min(_hours)
                SHIFT_MAX_HOUR[_s] = max(_hours)
                SHIFT_IS_WORKING[_s] = True
            else:
                SHIFT_MIN_HOUR[_s] = None
                SHIFT_MAX_HOUR[_s] = None
                SHIFT_IS_WORKING[_s] = False
        
        explicit_night_to_morning_blocks = {
            s_name for s_name in SHIFT_NAMES
            if SHIFT_IS_WORKING.get(s_name, False)
            and SHIFT_MIN_HOUR.get(s_name) is not None
            and SHIFT_MIN_HOUR[s_name] < 13
        }

        # Pares incompatibles: descanso estrictamente < min_rest_hours (piso duro, 8h).
        INCOMPATIBLE_LT = build_rest_incompatible_pairs(
            min_rest_hours,
            SHIFT_NAMES,
            SHIFT_IS_WORKING,
            SHIFT_MIN_HOUR,
            SHIFT_MAX_HOUR,
        )

        # Soft rest shortfall: transitions resting >= the hard floor but below
        # the target are ALLOWED at a per-hour cost, so the solver shortens
        # rest only when coverage or schedule consistency (heavier objective
        # terms) genuinely require it. Maps (s1, s2) -> hours short of target.
        _rest_target_soft = max(
            min_rest_hours, min(int(self.config.get("min_rest_hours_target", 12)), 24)
        )
        REST_SHORTFALL_PENALTY_PER_HOUR = 100_000
        SOFT_REST_PAIRS = {}
        if _rest_target_soft > min_rest_hours:
            _target_pairs = build_rest_incompatible_pairs(
                _rest_target_soft,
                SHIFT_NAMES,
                SHIFT_IS_WORKING,
                SHIFT_MIN_HOUR,
                SHIFT_MAX_HOUR,
            )
            for (_s1, _s2) in _target_pairs:
                if (_s1, _s2) in INCOMPATIBLE_LT:
                    continue
                # Prune shifts the solver cannot auto-pick (heavy/J_/E_ shifts
                # and DBL_ combos appear only via explicit manual fixes): the
                # 8h hard floor still protects those transitions, they just
                # skip the soft nudge. Keeps the model ~2x smaller.
                if (
                    _s1 in HEAVY_EXTENDED_SHIFTS or _s2 in HEAVY_EXTENDED_SHIFTS
                    or _s1.startswith(DOUBLE_SHIFT_PREFIX)
                    or _s2.startswith(DOUBLE_SHIFT_PREFIX)
                ):
                    continue
                _rest = rest_hours_between_shifts(
                    _s1, _s2, SHIFT_MIN_HOUR, SHIFT_MAX_HOUR, SHIFT_IS_WORKING
                )
                if _rest is None:
                    continue
                SOFT_REST_PAIRS[(_s1, _s2)] = _rest_target_soft - _rest

        # =========================
        # DYNAMIC PENALTY MODE (Standard Mode Detection)
        # =========================
        # Count active employees (not on VAC/PERM all week)
        active_count = 0
        ref_partial_count = self.config.get('refuerzo_partial_mode', False)
        for e in self.employees:
            # Excluir Refuerzo del conteo (salvo que esté en modo parcial)
            if self.emp_data[e].get('is_refuerzo', False) and not (ref_partial_count and e == self.refuerzo_name):
                continue
            # Safety net: exclude employees not included in schedule
            if not self.emp_data[e].get('incluir_en_horario', True):
                continue
            fixed = self.emp_data[e].get('fixed_shifts', {})
            all_absent = all(fixed.get(d) in ['VAC', 'PERM'] for d in DAYS)
            if not all_absent:
                active_count += 1
        
        # THRESHOLD: With >= 10 active employees, standard 8h shifts cover all peaks.
        standard_mode = active_count >= 10

        x = {} 
        penalties = []
        peak_penalties = []

        # --- Lexicographic tiers ---
        # Objective terms are routed into priority tiers by |weight| and solved
        # tier by tier (critical -> major -> minor), freezing each tier's best
        # value before optimizing the next. This keeps every rule's weight
        # intact WITHIN its tier while making it impossible for accumulations
        # of lower-tier penalties to buy a violation of a higher-tier rule.
        # `penalties` / `peak_penalties` remain the default minor tier.
        crit_penalties = []   # tier 1: near-hard rules (|w| >= LEX_TIER1_MIN)
        major_penalties = []  # tier 2: primary quality rules
        LEX_TIER1_MIN = 2_000_000
        LEX_TIER2_MIN = 150_000

        def route_penalty(weight, expr):
            """Append weight*expr to the tier matching the weight's magnitude."""
            w = abs(int(weight))
            if w >= LEX_TIER1_MIN:
                crit_penalties.append(weight * expr)
            elif w >= LEX_TIER2_MIN:
                major_penalties.append(weight * expr)
            else:
                penalties.append(weight * expr)
        
        # Variables
        for e in self.employees:
            for d in DAYS:
                for s in SHIFT_NAMES:
                    x[(e, d, s)] = model.NewBoolVar(f"x_{e}_{d}_{s}")
                
                # CORE: Exactly one shift per day
                model.Add(sum(x[(e, d, s)] for s in SHIFT_NAMES) == 1)

        for e in self.employees:
            for d in DAYS:
                if not is_special_sunday_like(d):
                    model.Add(x[(e, d, "D4_13-22")] == 0)

        for e in self.employees:
            if self.emp_data[e].get('is_refuerzo', False):
                continue
            for d in DAYS:
                for s in SHIFT_NAMES:
                    if s.startswith(MANUAL_SHIFT_PREFIX):
                        model.Add(x[(e, d, s)] == 0)

        def absent_all_week(emp):
            """True when VAC/PERM pills cover every day of the week.

            Such an employee has no day left to place the mandatory weekly rest
            day on, so every rule that demands one must be skipped for them —
            otherwise the model is proven infeasible before the search starts.
            """
            fs = self.emp_data[emp].get('fixed_shifts', {}) or {}
            return all(fs.get(d) in ('VAC', 'PERM') for d in DAYS)

        # CORE: OFF Day Limit (Standard = 1 per week)
        # NOTA: PERM es una ausencia EXENTA — no cuenta como día libre.
        # El empleado con PERM aún recibe su OFF normal por separado.
        # OFF en pills (fixed_shifts) es restricción dura; aquí se alinea el total semanal OFF+VAC.
        for e in self.employees:
            if self.emp_data[e].get('is_refuerzo'): continue
            # forced_quebrado_total: their OFF count is handled exclusively by the
            # forced_quebrado constraint below (sum(OFF+VAC+PERM)==1). Applying
            # required_off_vac here would conflict with that constraint on feriado
            # weeks (forced_closed>0 makes required_off_vac==2 → INFEASIBLE).
            if self.emp_data[e].get('forced_quebrado', False): continue
            fs = self.emp_data[e].get('fixed_shifts', {}) or {}
            
            forced_vac = sum(1 for d in DAYS if fs.get(d) == 'VAC')
            forced_perm = sum(1 for d in DAYS if fs.get(d) == 'PERM')
            forced_closed = sum(
                1 for d in DAYS
                if is_special_closed(d) and fs.get(d) not in ['OFF', 'VAC', 'PERM']
            )

            allow_no_rest = self.emp_data[e].get('allow_no_rest', False)
            off_grid_other = sum(1 for d in DAYS if fs.get(d) == "OFF")
            required_off_vac = forced_vac + forced_closed + off_grid_other
            if not allow_no_rest and off_grid_other == 0:
                # The mandatory weekly rest day only exists if there is a day left
                # to place it on. VAC/PERM pills (plus closed days) can consume the
                # whole week, and then demanding an extra OFF pushes the total above
                # len(DAYS) — infeasible before the search even starts.
                days_taken = forced_vac + forced_perm + forced_closed
                if days_taken < len(DAYS):
                    required_off_vac += 1

            if self.emp_data[e].get('is_jefe_pista'):
                model.Add(
                    sum(x[(e, d, "OFF")] + x[(e, d, "VAC")] for d in DAYS)
                    == required_off_vac
                )
            elif self.config.get('fixed_night_person') == e:
                # Night person already handled in LOGICA NIGHT / ELIGIO
                pass
            else:
                model.Add(
                    sum(x[(e, d, "OFF")] + x[(e, d, "VAC")] for d in DAYS)
                    == required_off_vac
                )

        # Variables para sistema de LIBRES
        persona_hace_libres = {}
        for e in self.flexibles:
            persona_hace_libres[e] = model.NewBoolVar(f"hace_libres_{e}")
        
        # EXACTAMENTE 1 persona hace libres (toda la semana)
        # Filtro: solo night_replacements
        for e in self.flexibles:
            if e not in self.night_replacements:
                model.Add(persona_hace_libres[e] == 0)
            
            # Forced Libres Constraint from Employee Config
            if self.emp_data[e].get('forced_libres', False):
                 model.Add(persona_hace_libres[e] == 1)
        
        candidates = [e for e in self.flexibles if e in self.night_replacements]
        if candidates:
            forced_libres_set = [e for e in candidates if self.emp_data[e].get('forced_libres', False)]
            if forced_libres_set:
                # Forced libres: all flagged employees MUST be libres persons
                for e in forced_libres_set:
                    model.Add(persona_hace_libres[e] == 1)
                # Total: exactly the forced employees — no extra libres person.
                # Night coverage gaps are handled by the fallback_needed_d logic.
                model.Add(sum(persona_hace_libres[e] for e in candidates) == len(forced_libres_set))
            else:
                model.Add(sum(persona_hace_libres[e] for e in candidates) == 1)
        
        # =========================
        # RESTRICCIÓN: HORARIOS CONSISTENTES
        # =========================
        # NOTE: The Libres person switches between N_22-05 and day shifts,
        # so they CANNOT have a single "principal" shift. We skip all
        # night_replacement candidates (they might become Libres)
        # and the primary night person (who only does N_22-05/OFF).
        turno_principal = {}
        consistency_exempt = []  # Track employees exempt from consistency
        
        night_person_name = self.config.get('fixed_night_person', None)
        
        for e in self.employees:
            # Skip primary night person (only does N_22-05 / OFF)
            if e == night_person_name:
                continue
                
            # Skip if fully fixed
            fixed_days_count = len(self.emp_data[e].get('fixed_shifts', {}))
            if fixed_days_count > 5:
                continue
            
            # EXEMPTION: forced_libres employees (persona de libres) are exempt
            # from turno_principal consistency — their role requires variable shifts.
            if self.emp_data[e].get('forced_libres', False):
                consistency_exempt.append(e)
                continue
            
            # Candidatos de libres: tienen turno principal pero la consistencia
            # solo aplica en días donde NO hacen N_22-05
            if e in self.night_replacements:
                turno_principal[e] = {}
                for s in SHIFT_NAMES:
                    if s in ["OFF", "VAC", "PERM", "N_22-05"] or s.startswith("J_") or s.startswith("X_") or s.startswith("Q") or s.startswith(DOUBLE_SHIFT_PREFIX):
                        continue
                    turno_principal[e][s] = model.NewBoolVar(f"principal_{e}_{s}")
                if turno_principal[e]:
                    model.Add(sum(turno_principal[e].values()) == 1)
                continue
            
            # forced_quebrado_total employees only work Q shifts — they have no
            # meaningful non-Q principal shift.  Skip to avoid creating a
            # turno_principal over non-Q shifts that can never be used.
            if self.emp_data[e].get('forced_quebrado', False):
                continue

            turno_principal[e] = {}
            for s in SHIFT_NAMES:
                if s in ["OFF", "VAC", "PERM"] or s.startswith("J_") or s.startswith("X_") or s.startswith("Q") or s.startswith(DOUBLE_SHIFT_PREFIX): continue
                turno_principal[e][s] = model.NewBoolVar(f"principal_{e}_{s}")

            if turno_principal[e]:
                model.Add(sum(turno_principal[e].values()) == 1)

                # Consistency Penalty: Penalize deviations from the assigned turno_principal.
                # If they work a shift `s` on day `d` that is NOT their `turno_principal[s]`, apply penalty.
                # (Excluding special shifts like OFF, VAC, PERM, J_, X_, Q_)
                # Uses module-level CONSISTENCY_PENALTY (500k — near-hard constraint).
                for d in DAYS:
                    if _has_working_fixed_shift(self.emp_data[e], d):
                        continue
                    for s in SHIFT_NAMES:
                        if s in ["OFF", "VAC", "PERM"] or s.startswith("J_") or s.startswith("X_") or s.startswith("Q") or s.startswith(DOUBLE_SHIFT_PREFIX):
                            continue

                        # Deviation happens if x[(e, d, s)] == 1 AND turno_principal[e][s] == 0
                        is_working_s = x[(e, d, s)]
                        is_not_principal = turno_principal[e][s].Not()
                        
                        deviation = model.NewBoolVar(f"dev_{e}_{d}_{s}")
                        model.AddBoolAnd([is_working_s, is_not_principal]).OnlyEnforceIf(deviation)
                        model.AddBoolOr([is_working_s.Not(), turno_principal[e][s]]).OnlyEnforceIf(deviation.Not())
                        
                        route_penalty(CONSISTENCY_PENALTY, deviation)

        # =========================
        # RESTRICCIÓN: TURNOS LARGOS OPCIONALES
        # =========================
        allow_long = self.config.get('allow_long_shifts', False)
        
        for e in self.employees:
            for d in DAYS:
                if not allow_long:
                    for s in SHIFT_NAMES:
                        if s.startswith("X_"):
                            model.Add(x[(e, d, s)] == 0)
                
                if not allow_long:
                    fixed_map = self.emp_data[e].get('fixed_shifts', {})
                    # If the person doesn't have a fixed J_ shift, block all J_ shifts
                    if not any(fixed_map.get(d, "").startswith("J_") for d in DAYS):
                         for s in SHIFT_NAMES:
                             if s.startswith("J_"):
                                 model.Add(x[(e, d, s)] == 0)
        
        # Hard-block Q3 quebrado largo when toggle is off
        if not self.config.get('allow_quebrado_largo', False):
            for e in self.employees:
                for d in DAYS:
                    model.Add(x[(e, d, "Q3_05-11+17-22")] == 0)
        

        # =========================
        # RESTRICCIÓN: TURNOS MANUAL-ONLY (VACACIONES / PERMISOS / T13_13-22)
        # =========================
        # VAC, PERM, T13_13-22 (and any other manual-only shifts) can ONLY be
        # assigned if they are in fixed_shifts. Otherwise they = 0.
        for e in self.employees:
             fixed_map = self.emp_data[e].get('fixed_shifts', {})
             for d in DAYS:
                  for ms in MANUAL_ONLY_SHIFTS:
                      if fixed_map.get(d) != ms:
                          model.Add(x[(e, d, ms)] == 0)

        # =========================
        # RESTRICCIÓN: TURNOS DOBLES (DBL_*)
        # =========================
        # Los DBL_* NUNCA se auto-asignan: solo son elegibles el día en que
        # el empleado tiene la pill "DOBLE" en fixed_shifts. La restricción
        # dura que elige CUÁL DBL_* usar ese día se aplica más abajo, en el
        # bloque FIJOS (junto a fixed_constraints).
        double_shift_codes_all = [s for s in SHIFT_NAMES if s.startswith(DOUBLE_SHIFT_PREFIX)]
        if double_shift_codes_all:
            for e in self.employees:
                fixed_map = self.emp_data[e].get('fixed_shifts', {})
                for d in DAYS:
                    if fixed_map.get(d) == "DOBLE":
                        continue  # habilitado por la pill, ver bloque FIJOS
                    for ds in double_shift_codes_all:
                        model.Add(x[(e, d, ds)] == 0)


        # =========================
        # LOGICA NIGHT PRE-COMPUTE
        # =========================
        night_mode = self.config.get('night_mode', 'rotation')
        night_person_name = self.config.get('fixed_night_person', None)
        
        primary_night = None
        if night_person_name and night_person_name in self.employees:
            primary_night = night_person_name

        # FIJOS (From Config/Input) - STRICT vs FLEXIBLE
        # =========================
        # strict_preferences (default: false) determines if an employee's
        # fixed_shifts are hard constraints or soft preferences.
        # The Night Person is ALWAYS strict regardless of toggle.
        global_strict = self.config.get('strict_preferences', False)
        
        fixed_constraints = {}
        soft_preferences = {}  # (e, d) -> s_code for flexible employees
        jefe_nearhard_keys = set()  # (e, d) whose soft pref is a NEAR-HARD jefe lock
        double_pill_days = []  # [(e, d), ...] — pill "DOBLE": ver más abajo

        for e in self.employees:
            fixed_map = self.emp_data[e].get('fixed_shifts', {})
            is_strict = self.emp_data[e].get('strict_preferences', False)
            is_night = (primary_night and e == primary_night)

            # Jefe de Pista near-absolute-schedule rule: when the jefe's WEEKDAY
            # pattern is ONE uniform working shift (matching a jefe-section preset),
            # the whole selected week (weekdays + the different Sáb/Dom shift) is
            # locked with a NEAR-HARD soft penalty (JEFE_NEAR_HARD_PENALTY) — high
            # enough to dominate coverage (5M/h) and consistency (900k), so it is
            # respected whenever physically feasible, yet still SOFT so it can NEVER
            # make the model INFEASIBLE.  (A true hard lock collided with other hard
            # rules — x==1 vs x==0 — and killed generation entirely.)  If a WEEKDAY is
            # changed to a different shift, the week is no longer uniform and it drops
            # back to the normal soft preference.
            #   • Saturday and Sunday are EXCLUDED from the uniformity test: the jefe
            #     works a different schedule there BY DESIGN (e.g. Jeison's Saturday
            #     shift differs in every preset), so a different Sáb/Dom must NOT make
            #     the week look "mixed"; those working shifts are still near-hard-locked
            #     together with the uniform weekdays.
            #   • OFF/VAC/PERM stay hard; blank (auto) days don't count as "different".
            jefe_week_hard = False
            if self.emp_data[e].get('is_jefe_pista', False):
                weekday_working = [
                    s for d2, s in fixed_map.items()
                    if d2 in DAYS and d2 not in ("Sáb", "Dom")
                    and s in SHIFT_NAMES and s not in ("OFF", "VAC", "PERM")
                ]
                # Uniform week: one single weekday shift, OR a staggered week
                # built entirely from jefe presets (J_* family, e.g. J_07-17
                # some days and J_09-19 others). Staggering the jefe across
                # J_* presets keeps the near-hard lock while letting his 10h
                # block reach the PM peak on the later-start days.
                if weekday_working and (
                    len(set(weekday_working)) == 1
                    or all(s.startswith("J_") for s in weekday_working)
                ):
                    jefe_week_hard = True

            # Night is ALWAYS strict, plus global strict.  The jefe uses a NEAR-HARD
            # soft lock (below), NOT force_strict, to avoid hard-constraint collisions.
            force_strict = global_strict or is_strict or is_night

            for d, s_code in fixed_map.items():
                if d not in DAYS:
                    continue
                if s_code == "DOBLE":
                    # Pill "turno doble": SIEMPRE restricción dura (igual que
                    # OFF/VAC/PERM). El solver elige CUÁL DBL_* usar ese día
                    # — aplicado más abajo, después de fixed_constraints.
                    double_pill_days.append((e, d))
                    continue
                if s_code in SHIFT_NAMES:
                    if is_special_sunday_like(d) and s_code not in ["OFF", "VAC", "PERM"]:
                        continue
                    if is_special_closed(d) and s_code not in ["VAC", "PERM"]:
                        continue
                    # VAC, PERM, OFF are ALWAYS hard constraints (pills / manual)
                    if s_code in ["VAC", "PERM", "OFF"]:
                        fixed_constraints[(e, d)] = s_code
                    elif s_code in MANUAL_ONLY_SHIFTS:
                        # Manual-only shifts (e.g. T13_13-22): if strict, hard constraint;
                        # otherwise soft with fallback to similar-entry shifts.
                        if force_strict:
                            fixed_constraints[(e, d)] = s_code
                        else:
                            soft_preferences[(e, d)] = s_code
                            # Also add similar-entry shifts as weaker preferences
                            similar = SIMILAR_ENTRY_SHIFTS.get(s_code, [])
                            for alt_s in similar:
                                if alt_s in SHIFT_NAMES:
                                    soft_preferences[(e, d, alt_s)] = s_code
                    elif force_strict:
                        fixed_constraints[(e, d)] = s_code
                    else:
                        soft_preferences[(e, d)] = s_code
                        if jefe_week_hard:
                            # Near-hard lock for the jefe's uniform week (incl. Sáb/Dom).
                            jefe_nearhard_keys.add((e, d))

        # Apply HARD constraints (strict employees + VAC/PERM/OFF)
        for (e, d), s_code in fixed_constraints.items():
            for s in SHIFT_NAMES:
                model.Add(x[(e, d, s)] == (1 if s == s_code else 0))

        # Pill "DOBLE": restricción dura — exactamente un DBL_* ese día,
        # respetando can_do_night (si el empleado no puede noche, se excluyen
        # los DBL_* que toquen la franja nocturna). El solver elige cuál según
        # cobertura y consistencia semanal.
        double_shift_codes = [s for s in SHIFT_NAMES if s.startswith(DOUBLE_SHIFT_PREFIX)]
        for (e, d) in double_pill_days:
            valid_double_codes = double_shift_codes
            if not self.emp_data[e].get('can_do_night', True):
                valid_double_codes = [s for s in valid_double_codes if not touches_night(s)]
            if not valid_double_codes:
                logger.warning(
                    "Pill 'DOBLE' para %s en %s sin turnos dobles disponibles "
                    "(max_double_shift_hours=%s%s) -- el horario será infactible.",
                    e, d,
                    resolve_max_double_shift_hours(self.config),
                    ", excluyendo nocturnos por can_do_night=False" if not self.emp_data[e].get('can_do_night', True) else "",
                )
            model.Add(sum(x[(e, d, s)] for s in valid_double_codes) == 1)

        closed_days = [d for d in DAYS if is_special_closed(d)]
        for e in self.employees:
            for d in closed_days:
                if fixed_constraints.get((e, d)) in ["VAC", "PERM"]:
                    continue
                for s in SHIFT_NAMES:
                    model.Add(x[(e, d, s)] == (1 if s == "OFF" else 0))
        
        # Apply SOFT constraints (flexible employees) — Family-Aware Three-Level Hierarchy
        # ─────────────────────────────────────────────────────────────────────────────────
        # When a soft preference is configured (e.g. Maikel: T1_05-13 on Lunes):
        #
        #   Level 1 — exact shift used         → cost 0          (ideal)
        #   Level 2 — same AM/PM family used   → cost PREF_DEVIATION_PENALTY   (acceptable)
        #   Level 3 — opposite family used     → cost PREF_DEVIATION_PENALTY
        #                                          + PREF_FAMILY_PENALTY       (last resort)
        #
        # This ensures that when the solver can't assign T1_05-13, it tries other AM
        # shifts (T2_06-14, T3_07-15 ...) before falling back to a PM shift.
        # Consistency across the week is automatically handled by turno_principal (50K/day).
        #
        # FIX 2026-06-03: La consistencia semanal (500k/día) debe ser más importante
        # que los turnos fijos no-estrictos. Si PREF_DEVIATION > CONSISTENCY,
        # el solver rompe consistencia para cumplir el "capricho" de asignar un día.
        # Ahora: consistencia > preferencia soft > nada.
        # OFF/VAC/PERM siguen siendo hard constraints (se manejan arriba).
        PREF_DEVIATION_PENALTY = 300_000 if standard_mode else 200_000
        PREF_FAMILY_PENALTY    = 100_000   # extra cost for crossing AM<->PM boundary
        # Near-hard jefe lock: dominates coverage (5M/h) and consistency (900k) so the
        # jefe's uniform week is respected whenever feasible — but SOFT, so it can never
        # force the model infeasible.  If another hard rule blocks the jefe's shift on
        # some day, the solver pays this and deviates only there, gracefully.
        JEFE_NEAR_HARD_PENALTY = 50_000_000

        for key, s_code in soft_preferences.items():
            # Support both (e, d) and (e, d, alt_s) keys
            if len(key) == 3:
                e, d, alt_s = key
                # Fallback alternative for manual-only shifts: lower penalty than primary
                # This is weaker than the primary preference for the actual manual shift.
                pref_violated = model.NewBoolVar(f"pref_fallback_{e}_{d}_{alt_s}")
                model.Add(x[(e, d, alt_s)] == 0).OnlyEnforceIf(pref_violated)
                model.Add(x[(e, d, alt_s)] == 1).OnlyEnforceIf(pref_violated.Not())
                route_penalty(int(PREF_DEVIATION_PENALTY * 1.5), pref_violated)
                continue

            e, d = key
            pref_family = _am_pm_token(s_code)  # "AM", "PM", or None
            # Jefe near-hard lock uses a dominant penalty; everyone else the normal one.
            deviation_penalty = (
                JEFE_NEAR_HARD_PENALTY if (e, d) in jefe_nearhard_keys
                else PREF_DEVIATION_PENALTY
            )

            # Level 1: penalize when the exact preferred shift is NOT used
            pref_violated = model.NewBoolVar(f"pref_violated_{e}_{d}")
            model.Add(x[(e, d, s_code)] == 0).OnlyEnforceIf(pref_violated)
            model.Add(x[(e, d, s_code)] == 1).OnlyEnforceIf(pref_violated.Not())
            route_penalty(deviation_penalty, pref_violated)

            # Level 2: when deviated AND landed on the wrong AM/PM family, add extra cost
            if pref_family:
                for s in SHIFT_NAMES:
                    if s == s_code or s in IGNORED_ROTATION_SHIFTS:
                        continue
                    s_family = _am_pm_token(s)
                    if not s_family or s_family == pref_family:
                        continue  # same family -- no extra cost
                    # Wrong family: pref_violated AND x[e,d,s] == 1
                    wrong_family_used = model.NewBoolVar(f"wrong_fam_{e}_{d}_{s}")
                    model.AddBoolAnd([pref_violated, x[(e, d, s)]]).OnlyEnforceIf(wrong_family_used)
                    model.AddBoolOr([pref_violated.Not(), x[(e, d, s)].Not()]).OnlyEnforceIf(wrong_family_used.Not())
                    penalties.append(PREF_FAMILY_PENALTY * wrong_family_used)
        
        # =========================
        # RESTRICCIÓN: SÁBADOS DE JEFE DE PISTA (5AM a 1PM)
        # =========================
        # Legacy fallback: if a Jefe has no explicit Saturday base shift configured,
        # keep the classic Saturday T1. Explicit fixed_shifts always win.
        # Si el sábado está fijado como libre/ausencia en pills, no forzar T1 (chocaría con OFF duro).
        for e in self.employees:
            if self.emp_data[e].get('is_jefe_pista', False):
                sat_fixed = (self.emp_data[e].get('fixed_shifts', {}) or {}).get("Sáb")
                if sat_fixed in ("OFF", "VAC", "PERM"):
                    continue
                if day_modes.get("Sáb") == SPECIAL_DAY_MODE_NORMAL and not sat_fixed:
                    for s in SHIFT_NAMES:
                        model.Add(x[(e, "Sáb", s)] == (1 if s == "T1_05-13" else 0))

        # =========================
        # RESTRICCIÓN: PRACTICANTE (acompaña al Jefe de Pista)
        # =========================
        # El practicante solo puede trabajar turnos cuyas horas caigan dentro
        # del horario del jefe de pista. No puede entrar a las 5am, ni trabajar
        # turnos nocturnos/tarde-noche, ni quebrados.
        jefe_name = None
        for e in self.employees:
            if self.emp_data[e].get('is_jefe_pista', False):
                jefe_name = e
                break

        for e in self.employees:
            if not self.emp_data[e].get('is_practicante', False):
                continue
            if not jefe_name:
                # No hay jefe → no aplicar restricción de acompañamiento
                break

            # Turnos prohibidos para practicante (hard block global):
            # - Noche, quebrados, y cualquier turno que inicie a las 5am o
            #   que cubra tarde-noche (min_hour >= 15 o max_hour >= 22)
            blocked_shifts = set()
            for s in SHIFT_NAMES:
                if not SHIFT_IS_WORKING.get(s):
                    continue
                s_min = SHIFT_MIN_HOUR.get(s)
                s_max = SHIFT_MAX_HOUR.get(s)
                if s_min is None:
                    continue
                # Block night
                if s == "N_22-05":
                    blocked_shifts.add(s)
                    continue
                # Block broken shifts
                if s.startswith("Q"):
                    blocked_shifts.add(s)
                    continue
                # Block shifts starting at 5am
                if s_min == 5:
                    blocked_shifts.add(s)
                    continue
                # Block late evening shifts (end at 10pm+)
                if s_max >= 22:
                    blocked_shifts.add(s)
                    continue
                # Block shifts that start at 3pm or later (pure afternoon/evening)
                if s_min >= 15:
                    blocked_shifts.add(s)
                    continue

            # Per-day: restrict practicante to shifts overlapping with jefe's hours
            jefe_fixed = self.emp_data[jefe_name].get('fixed_shifts', {}) or {}

            for d in DAYS:
                # Always block globally prohibited shifts
                for s in blocked_shifts:
                    if (e, d) not in fixed_constraints:
                        model.Add(x[(e, d, s)] == 0)

                # Determine jefe's hours for this day
                jefe_shift_today = None
                if (jefe_name, d) in fixed_constraints:
                    jefe_shift_today = fixed_constraints[(jefe_name, d)]
                elif jefe_fixed.get(d) and jefe_fixed[d] in SHIFT_NAMES:
                    jefe_shift_today = jefe_fixed[d]

                if not jefe_shift_today or not SHIFT_IS_WORKING.get(jefe_shift_today):
                    # Jefe has OFF/VAC/PERM this day → practicante also OFF
                    if (e, d) not in fixed_constraints:
                        for s in SHIFT_NAMES:
                            model.Add(x[(e, d, s)] == (1 if s == "OFF" else 0))
                    continue

                jefe_hours = SHIFTS.get(jefe_shift_today, set())
                if not jefe_hours:
                    continue

                jefe_start = min(jefe_hours)
                jefe_end = max(jefe_hours)

                # Allow only working shifts whose hours are within jefe's range
                # (practicante arrives 1h after jefe, leaves 1h before)
                # But we don't hard-force that exact window — we just block shifts
                # that go outside the jefe's hours.
                for s in SHIFT_NAMES:
                    if s in blocked_shifts:
                        continue  # Already blocked above
                    if not SHIFT_IS_WORKING.get(s):
                        continue
                    s_min = SHIFT_MIN_HOUR.get(s)
                    s_max = SHIFT_MAX_HOUR.get(s)
                    if s_min is None:
                        continue
                    # Block if shift starts before jefe or ends after jefe
                    if s_min < jefe_start or s_max > jefe_end:
                        if (e, d) not in fixed_constraints:
                            model.Add(x[(e, d, s)] == 0)

        # =========================
        # LOGICA NIGHT / ELIGIO
        # =========================
        if primary_night:
            # a) Cada día: solo puede estar LIBRE (OFF/VAC/PERM) o en N_22-05
            # NOTE: Night person CAN get Sunday OFF via rotation (persona_hace_libres covers N replacement)
            for d in DAYS:
                model.Add(x[(primary_night, d, "OFF")] + x[(primary_night, d, "VAC")] + x[(primary_night, d, "PERM")] + x[(primary_night, d, "N_22-05")] == 1)
                for s in SHIFT_NAMES:
                    if s not in ["OFF", "VAC", "PERM", "N_22-05"]:
                        model.Add(x[(primary_night, d, s)] == 0)
            
            # b) Exactamente el número de libres asignados por base o fijos.
            # Siempre se aplica este límite — incluso si hay fixed_constraints para algún día.
            # Usamos el mismo cálculo que el resto de empleados: base = max(1, forced_off).
            _night_fs = self.emp_data[primary_night].get('fixed_shifts', {}) or {}
            _night_forced_off = sum(1 for d in DAYS if _night_fs.get(d) == 'OFF')
            _night_forced_vac = sum(1 for d in DAYS if _night_fs.get(d) == 'VAC')
            _night_forced_closed = sum(
                1 for d in DAYS
                if is_special_closed(d) and _night_fs.get(d) not in ['OFF', 'VAC', 'PERM']
            )
            _night_base_off = max(1, _night_forced_off)
            if absent_all_week(primary_night):
                # VAC/PERM cover the whole week: the pills already pin every day and
                # there is no room for the extra rest day (see absent_all_week).
                _night_required = len(DAYS)
            else:
                _night_required = _night_base_off + _night_forced_vac + _night_forced_closed
            model.Add(sum(
                x[(primary_night, d, "OFF")] + x[(primary_night, d, "VAC")] + x[(primary_night, d, "PERM")]
                for d in DAYS
            ) == _night_required)

            # c) Reemplazo nocturno:
            #    - Normalmente cubre la persona de libres.
            #    - Si esa persona también está OFF/VAC/PERM el mismo día que Primary,
            #      habilitamos automáticamente fallback a otro nocturno elegible.
            primary_off_by_day = {}
            night_fallback_needed = {}
            for d in DAYS:
                if is_special_closed(d):
                    primary_off_by_day[d] = model.NewConstant(1)
                    night_fallback_needed[d] = model.NewConstant(0)
                    model.Add(
                        sum(x[(e, d, "N_22-05")] for e in self.night_replacements if e != primary_night) == 0
                    )
                    continue

                # Detectar si algún otro empleado tiene N_22-05 fijado manualmente ese día
                manual_night_cover_d = any(
                    emp != primary_night
                    and self.emp_data[emp].get('fixed_shifts', {}).get(d) == "N_22-05"
                    for emp in self.employees
                )

                # Primary is OFF logic includes VAC and PERM
                primary_off_var = model.NewBoolVar(f"primary_off_{d}")
                primary_off_by_day[d] = primary_off_var
                model.Add(x[(primary_night, d, "OFF")] + x[(primary_night, d, "VAC")] + x[(primary_night, d, "PERM")] == 1).OnlyEnforceIf(primary_off_var)
                model.Add(x[(primary_night, d, "OFF")] + x[(primary_night, d, "VAC")] + x[(primary_night, d, "PERM")] == 0).OnlyEnforceIf(primary_off_var.Not())

                # Requirement: If Primary is OFF, EXACTLY one other night-eligible person MUST do N_22-05
                # This handles all "special cases" naturally.
                model.Add(sum(x[(e, d, "N_22-05")] for e in self.night_replacements if e != primary_night) == 1).OnlyEnforceIf(primary_off_var)
                model.Add(sum(x[(e, d, "N_22-05")] for e in self.night_replacements if e != primary_night) == 0).OnlyEnforceIf(primary_off_var.Not())

                selected_libres_absent_terms = []

                # Preference: The assigned "persona_hace_libres" is the STRONGLY preferred candidate
                for e_repl in self.night_replacements:
                    if e_repl == primary_night or e_repl not in persona_hace_libres: continue
                    
                    is_libres = persona_hace_libres[e_repl]
                    libres_is_off_d = model.NewBoolVar(f"libres_is_off_{e_repl}_{d}")
                    model.Add(x[(e_repl, d, "OFF")] + x[(e_repl, d, "VAC")] + x[(e_repl, d, "PERM")] == 1).OnlyEnforceIf(libres_is_off_d)
                    model.Add(x[(e_repl, d, "OFF")] + x[(e_repl, d, "VAC")] + x[(e_repl, d, "PERM")] == 0).OnlyEnforceIf(libres_is_off_d.Not())

                    selected_libres_absent = model.NewBoolVar(f"selected_libres_absent_{e_repl}_{d}")
                    model.AddBoolAnd([is_libres, libres_is_off_d]).OnlyEnforceIf(selected_libres_absent)
                    model.AddBoolOr([is_libres.Not(), libres_is_off_d.Not()]).OnlyEnforceIf(selected_libres_absent.Not())
                    selected_libres_absent_terms.append(selected_libres_absent)
                    
                    # If e is the Libres person and primary is off, they MUST cover UNLESS they are also OFF
                    # If they are OFF, the sum constraint above will pick someone else.
                    should_cover = model.NewBoolVar(f"should_cover_{e_repl}_{d}")
                    model.AddBoolAnd([is_libres, primary_off_var, libres_is_off_d.Not()]).OnlyEnforceIf(should_cover)
                    model.AddBoolOr([is_libres.Not(), primary_off_var.Not(), libres_is_off_d]).OnlyEnforceIf(should_cover.Not())
                    
                    # 1M penalty if the ideal replacement doesn't cover (allows fallback to others)
                    route_penalty(1000000, should_cover.Not())
                    # model.Add(x[(e_repl, d, "N_22-05")] == 1).OnlyEnforceIf(should_cover) # Too aggressive
                    # Instead of hard Add, use another soft penalty to prefer the libres person
                    route_penalty(2000000, should_cover.Not())

                selected_libres_absent_d = model.NewBoolVar(f"selected_libres_absent_{d}")
                if selected_libres_absent_terms:
                    model.Add(sum(selected_libres_absent_terms) == 1).OnlyEnforceIf(selected_libres_absent_d)
                    model.Add(sum(selected_libres_absent_terms) == 0).OnlyEnforceIf(selected_libres_absent_d.Not())
                else:
                    model.Add(selected_libres_absent_d == 0)

                fallback_needed_d = model.NewBoolVar(f"night_fallback_needed_{d}")
                model.AddBoolAnd([primary_off_var, selected_libres_absent_d]).OnlyEnforceIf(fallback_needed_d)
                model.AddBoolOr([primary_off_var.Not(), selected_libres_absent_d.Not()]).OnlyEnforceIf(fallback_needed_d.Not())
                night_fallback_needed[d] = fallback_needed_d

            # Bloquear N_22-05 para quienes no pueden
            # EXCEPCIÓN: empleados con fixed_shift N_22-05 en ese día específico
            # (cobertura manual → se les permite hacer la noche puntualmente).
            for e in self.employees:
                if e == primary_night: continue
                
                if e not in self.night_replacements:
                    for d in DAYS:
                        # Permitir si tiene fijado manualmente N_22-05 ese día
                        if self.emp_data[e].get('fixed_shifts', {}).get(d) == "N_22-05":
                            continue
                        model.Add(x[(e, d, "N_22-05")] == 0)
                else:
                    if e in persona_hace_libres:
                        is_libres = persona_hace_libres[e]
                        for d in DAYS:
                            # Permitir si tiene fijado manualmente N_22-05 ese día
                            if self.emp_data[e].get('fixed_shifts', {}).get(d) == "N_22-05":
                                continue
                            model.Add(x[(e, d, "N_22-05")] == 0).OnlyEnforceIf([is_libres.Not(), night_fallback_needed[d].Not()])
                    else:
                        # e in replacements but not in persona_hace_libres:
                        # they can only cover the night on fallback days.
                        for d in DAYS:
                            if self.emp_data[e].get('fixed_shifts', {}).get(d) == "N_22-05":
                                continue
                            model.Add(x[(e, d, "N_22-05")] == 0).OnlyEnforceIf(night_fallback_needed[d].Not())

        else:
            # NO Primary Night Person (Generic Rotation)
            for e in self.employees:
                if e not in self.night_replacements:
                    for d in DAYS:
                        model.Add(x[(e, d, "N_22-05")] == 0)

        # Un turno por día
        for e in self.employees:
            for d in DAYS:
                model.Add(sum(x[(e, d, s)] for s in SHIFT_NAMES) == 1)

        # RESTRICCIONES ESPECÍFICAS PARA MUJERES (Ileana, Jensy)
        # Solo trabajan 5am-1pm o 1pm-8pm (Días normales)
        # Domingos pueden hacer también 6-2 o 7-3.
        ALLOWED_WOMEN_WEEK = ["T1_05-13", "T8_13-20", "OFF", "VAC", "PERM"]
        ALLOWED_WOMEN_SAT = ["T1_05-13", "T8_13-20", "T3_07-15", "OFF", "VAC", "PERM"] # Agregado T3_07-15
        ALLOWED_WOMEN_SUN = ["T1_05-13", "T8_13-20", "T2_06-14", "T3_07-15", "OFF", "VAC", "PERM"]
        for e in self.employees:
            is_woman = self.emp_data[e].get('gender') == 'F'
            cannot_night = not self.emp_data[e].get('can_do_night', True)

            if is_woman:
                # Night shifts: HARD prohibition for women without a night permit,
                # on par with the non-night men rule below. A woman without a night
                # permit must NEVER be scheduled on a shift that touches the night
                # window. Other non-allowed shifts (e.g. long shifts) stay as a soft
                # penalty so the model does not turn infeasible for lack of daytime slack.
                INVALID_SHIFT_PENALTY = 6000000
                for d in DAYS:
                    # Lógica de selección de lista permitida
                    if is_special_closed(d):
                        allowed = ["OFF", "VAC", "PERM"]
                    elif is_special_sunday_like(d):
                        allowed = ALLOWED_WOMEN_SUN
                    elif d == "Sáb":
                        allowed = ALLOWED_WOMEN_SAT
                    else:
                        allowed = ALLOWED_WOMEN_WEEK

                    for s in SHIFT_NAMES:
                        if s in allowed:
                            continue
                        if cannot_night and touches_night(s):
                            # Hard rule: no night-window shift for a non-night woman.
                            model.Add(x[(e, d, s)] == 0)
                        else:
                            route_penalty(INVALID_SHIFT_PENALTY, x[(e, d, s)])

            if cannot_night and not is_woman:
                # Fallback genérico para otros que no puedan hacer noche
                for d in DAYS:
                    for s in SHIFT_NAMES:
                        if touches_night(s):
                            model.Add(x[(e, d, s)] == 0)

        # =========================
        # DETECCIÓN DE COLISIÓN (para relajar Mujeres Opuestas)
        # =========================
        # On days where 2+ flex employees are OFF, relax the women opposite
        # shifts constraint to allow both women on the same shift type,
        # enabling full peak coverage.
        women_collision = {}
        for d in DAYS:
            flex_off_expr = sum(
                x[(e, d, "OFF")] + x[(e, d, "VAC")] + x[(e, d, "PERM")]
                for e in self.employees
                if not self.emp_data[e].get('is_refuerzo', False)
                and e != primary_night
                and not self.emp_data[e].get('is_jefe_pista', False)
            )
            women_collision[d] = model.NewBoolVar(f"women_collision_{d}")
            model.Add(flex_off_expr >= 2).OnlyEnforceIf(women_collision[d])
            model.Add(flex_off_expr < 2).OnlyEnforceIf(women_collision[d].Not())

        # =========================
        # RESTRICCIÓN: MUJERES EN TURNOS OPUESTOS
        # =========================
        # Si ambas mujeres trabajan el mismo día, una debe estar en turno AM
        # y la otra en turno PM. "AM" = turno inicia antes de las 12.
        # "PM" = turno inicia a las 12 o después.
        # Si una tiene OFF/VAC/PERM, la restricción no aplica ese día.
        # RELAJACIÓN: En días de colisión (2+ flex OFF), se permite que
        # ambas trabajen el mismo tipo de turno para cubrir picos.
        # Alternating pairs: pairs of employees constrained to always be on opposite
        # AM/PM shifts when both work the same day.
        # Configurable via config['alternating_pairs']; defaults to gender-F detection.
        alternating_pairs = _get_alternating_pairs(self.config, self.employees, self.emp_data)
        alternating_pair_members_set = {e for pair in alternating_pairs for e in pair}

        # NUEVA RESTRICCIÓN: Alternancia semanal estricta
        # Si está habilitada, las mujeres en par deben mantener el mismo turno (AM o PM) toda la semana
        strict_weekly = self.config.get("strict_weekly_alternation", False) if self.config else False

        am_shifts = [s for s in SHIFT_NAMES if SHIFT_IS_WORKING.get(s) and SHIFT_MIN_HOUR.get(s) is not None and SHIFT_MIN_HOUR[s] < 12]
        pm_shifts = [s for s in SHIFT_NAMES if SHIFT_IS_WORKING.get(s) and SHIFT_MIN_HOUR.get(s) is not None and SHIFT_MIN_HOUR[s] >= 12]

        # Para alternancia semanal estricta: pre-computar el turno para toda la semana
        # Based on fixed_shifts o historial
        weekly_assignment = {}  # {pair_idx: {"w1": "AM" or "PM", "w2": "AM" or "PM"}}
        
        if strict_weekly and alternating_pairs:
            for pair_idx, (w1, w2) in enumerate(alternating_pairs):
                ed1 = self.emp_data.get(w1) or {}
                ed2 = self.emp_data.get(w2) or {}
                # Try to get from fixed_shifts first
                w1_fixed = ed1.get('fixed_shifts', {}) or {}
                w2_fixed = ed2.get('fixed_shifts', {}) or {}
                
                w1_token = None
                w2_token = None
                
                # Check if any fixed shift is set (not OFF/VAC/PERM)
                for d in DAYS:
                    if w1_fixed.get(d) and w1_fixed[d] not in ['OFF', 'VAC', 'PERM']:
                        w1_token = _fixed_shift_token_for_day(ed1, d)
                        break
                for d in DAYS:
                    if w2_fixed.get(d) and w2_fixed[d] not in ['OFF', 'VAC', 'PERM']:
                        w2_token = _fixed_shift_token_for_day(ed2, d)
                        break
                
                # If no fixed shifts, try history
                if not w1_token and most_recent_schedule:
                    w1_hist = most_recent_schedule.get(w1, {})
                    w1_token = _extract_rotation_token_from_week(ed1, w1_hist)
                if not w2_token and most_recent_schedule:
                    w2_hist = most_recent_schedule.get(w2, {})
                    w2_token = _extract_rotation_token_from_week(ed2, w2_hist)
                
                # If still no token, default: w1=AM, w2=PM
                if not w1_token:
                    w1_token = "AM"
                if not w2_token:
                    w2_token = "PM"
                
                # Ensure they are opposite
                if w1_token == w2_token:
                    w2_token = "PM" if w1_token == "AM" else "AM"
                
                weekly_assignment[pair_idx] = {"w1": w1_token, "w2": w2_token}

        for pair_idx, (w1, w2) in enumerate(alternating_pairs):
            ed1 = self.emp_data.get(w1) or {}
            ed2 = self.emp_data.get(w2) or {}
            # Pre-compute expected rotation direction for this week based on history.
            w1_expected = None  # "AM" or "PM" -- what w1 SHOULD be this week
            w2_expected = None
            if most_recent_schedule:
                w1_hist_sched = most_recent_schedule.get(w1, {})
                w1_hist_token = _extract_rotation_token_from_week(
                    ed1, w1_hist_sched
                )
                w2_hist_sched = most_recent_schedule.get(w2, {})
                w2_hist_token = _extract_rotation_token_from_week(
                    ed2, w2_hist_sched
                )
                if w1_hist_token == "AM":
                    w1_expected = "PM"
                elif w1_hist_token == "PM":
                    w1_expected = "AM"
                if w2_hist_token == "AM":
                    w2_expected = "PM"
                elif w2_hist_token == "PM":
                    w2_expected = "AM"

            for d in DAYS:
                fixed_w1 = ed1.get('fixed_shifts', {}).get(d)
                fixed_w2 = ed2.get('fixed_shifts', {}).get(d)
                if fixed_w1 in ['OFF', 'VAC', 'PERM'] or fixed_w2 in ['OFF', 'VAC', 'PERM']:
                    continue

                fixed_w1_token = _fixed_shift_token_for_day(ed1, d)
                fixed_w2_token = _fixed_shift_token_for_day(ed2, d)

                if fixed_w1_token and fixed_w2_token and fixed_w1_token == fixed_w2_token:
                    continue

                # Para alternancia semanal estricta: usar el token pre-computado para toda la semana
                if strict_weekly and pair_idx in weekly_assignment:
                    # En modo semanal estricto, forzar el mismo turno para toda la semana
                    w1_expected = weekly_assignment[pair_idx]["w1"]
                    w2_expected = weekly_assignment[pair_idx]["w2"]
                    
                    # FIX: Si hay turnos fijos establecidos que contradicen el turno forzado,
                    # dar prioridad al turno fijo y saltarse la restricción de alternancia
                    if fixed_w1_token and fixed_w1_token != w1_expected:
                        # El turno fijo de w1 contradice lo que queremos forzar, saltar
                        continue
                    if fixed_w2_token and fixed_w2_token != w2_expected:
                        # El turno fijo de w2 contradice lo que queremos forzar, saltar
                        continue
                else:
                    w1_is_exception = (fixed_w1_token and w1_expected and fixed_w1_token != w1_expected)
                    w2_is_exception = (fixed_w2_token and w2_expected and fixed_w2_token != w2_expected)
                    if w1_is_exception or w2_is_exception:
                        continue

                w1_working = model.NewBoolVar(f"alt_w1_{pair_idx}_{d}")
                model.Add(x[(w1, d, "OFF")] + x[(w1, d, "VAC")] + x[(w1, d, "PERM")] == 0).OnlyEnforceIf(w1_working)
                model.Add(x[(w1, d, "OFF")] + x[(w1, d, "VAC")] + x[(w1, d, "PERM")] >= 1).OnlyEnforceIf(w1_working.Not())

                w2_working = model.NewBoolVar(f"alt_w2_{pair_idx}_{d}")
                model.Add(x[(w2, d, "OFF")] + x[(w2, d, "VAC")] + x[(w2, d, "PERM")] == 0).OnlyEnforceIf(w2_working)
                model.Add(x[(w2, d, "OFF")] + x[(w2, d, "VAC")] + x[(w2, d, "PERM")] >= 1).OnlyEnforceIf(w2_working.Not())

                both_working = model.NewBoolVar(f"alt_both_{pair_idx}_{d}")
                model.AddBoolAnd([w1_working, w2_working]).OnlyEnforceIf(both_working)
                model.AddBoolOr([w1_working.Not(), w2_working.Not()]).OnlyEnforceIf(both_working.Not())

                enforce_opposite = model.NewBoolVar(f"alt_opposite_{pair_idx}_{d}")
                model.AddBoolAnd([both_working, women_collision[d].Not()]).OnlyEnforceIf(enforce_opposite)
                model.AddBoolOr([both_working.Not(), women_collision[d]]).OnlyEnforceIf(enforce_opposite.Not())

                # Para alternancia semanal estricta: forzar el mismo turno AM/PM toda la semana
                if strict_weekly and pair_idx in weekly_assignment:
                    w1_token = weekly_assignment[pair_idx]["w1"]
                    w2_token = weekly_assignment[pair_idx]["w2"]
                    force_w1_am = (w1_token == "AM")
                elif fixed_w1_token:
                    force_w1_am = fixed_w1_token == "AM"
                elif fixed_w2_token:
                    force_w1_am = fixed_w2_token == "PM"
                else:
                    if w1_expected == "AM":
                        force_w1_am = True
                    elif w1_expected == "PM":
                        force_w1_am = False
                    else:
                        # Determinista: random.choice alteraba el modelo entre ejecuciones y podía
                        # marcar INFEASIBLE en un intento y Success en otro con los mismos datos.
                        force_w1_am = True
                
                if force_w1_am:
                    model.Add(sum(x[(w1, d, s)] for s in am_shifts) == 1).OnlyEnforceIf(enforce_opposite)
                    model.Add(sum(x[(w2, d, s)] for s in pm_shifts) == 1).OnlyEnforceIf(enforce_opposite)
                else:
                    model.Add(sum(x[(w2, d, s)] for s in am_shifts) == 1).OnlyEnforceIf(enforce_opposite)
                    model.Add(sum(x[(w1, d, s)] for s in pm_shifts) == 1).OnlyEnforceIf(enforce_opposite)
                    model.Add(sum(x[(w2, d, s)] for s in am_shifts) == 1).OnlyEnforceIf(enforce_opposite)
        # =========================
        # RESTRICCIÓN: DESCANSO MÍNIMO ENTRE TURNOS (param min_rest_hours, 12→6 vía solve)
        # =========================
        # Misma regla para todos (incl. persona de libres). allow_no_rest: sin esta restricción.
        for e in self.employees:
            if self.emp_data[e].get("allow_no_rest", False):
                continue
            # 1. CROSS-WEEK BOUNDARY: Thursday (History) -> Friday (Current)
            last_jue_shift = most_recent_schedule.get(e, {}).get("Jue", "OFF")
            if last_jue_shift not in SHIFT_NAMES:
                last_jue_shift = "OFF"

            # Determinar si el historial tiene la semana exactamente anterior al target
            _has_exact_prev = self.config.get("_has_exact_previous_week")
            _history_gap = _has_exact_prev is False  # Gap: semana anterior faltante

            # Hard block independiente: N_22-05 (Jue) -> turnos tempranos (Vie)
            # Cuando falta la semana anterior en el historial, usar soft penalty en vez de hard block
            # para evitar INFEASIBLE por datos desactualizados.
            if last_jue_shift == "N_22-05":
                if _history_gap:
                    # Penalty fuerte (6M) en vez de hard block: preserva factibilidad
                    NIGHT_TO_MORNING_PENALTY = 6_000_000
                    for s2 in explicit_night_to_morning_blocks:
                        route_penalty(NIGHT_TO_MORNING_PENALTY, x[(e, "Vie", s2)])
                else:
                    for s2 in explicit_night_to_morning_blocks:
                        model.Add(x[(e, "Vie", s2)] == 0)
            elif "Jue" not in most_recent_schedule.get(e, {}):
                if e in known_last_night_employee:
                    logger.warning(
                        "Historial no confiable para Jue de %s; se aplica fallback conservador por último nocturno conocido",
                        e,
                    )
                    if _history_gap:
                        NIGHT_TO_MORNING_PENALTY = 6_000_000
                        for s2 in explicit_night_to_morning_blocks:
                            route_penalty(NIGHT_TO_MORNING_PENALTY, x[(e, "Vie", s2)])
                    else:
                        for s2 in explicit_night_to_morning_blocks:
                            model.Add(x[(e, "Vie", s2)] == 0)

            if last_jue_shift in SHIFT_NAMES and SHIFT_IS_WORKING.get(last_jue_shift):
                s1 = last_jue_shift
                d2 = "Vie"
                if _history_gap:
                    # Gap: soft penalty en vez de hard block para el descanso general
                    REST_PENALTY = 5_000_000
                    for s2 in SHIFT_NAMES:
                        if (s1, s2) in INCOMPATIBLE_LT:
                            route_penalty(REST_PENALTY, x[(e, d2, s2)])
                else:
                    for s2 in SHIFT_NAMES:
                        if (s1, s2) in INCOMPATIBLE_LT:
                            model.Add(x[(e, d2, s2)] == 0)
                # Soft shortfall (floor..target) also applies across the
                # history boundary: Thursday's shift is known, so the penalty
                # lands directly on the Friday shift variable.
                for s2 in SHIFT_NAMES:
                    _short = SOFT_REST_PAIRS.get((s1, s2))
                    if _short:
                        route_penalty(
                            REST_SHORTFALL_PENALTY_PER_HOUR * _short, x[(e, d2, s2)]
                        )

            # 2. INTRA-WEEK BOUNDARY: Day i -> Day i+1
            for i in range(len(DAYS) - 1):
                d1 = DAYS[i]
                d2 = DAYS[i + 1]
                for (s1, s2) in INCOMPATIBLE_LT:
                    model.Add(x[(e, d2, s2)] == 0).OnlyEnforceIf(x[(e, d1, s1)])
                # 2b. Soft shortfall: rest in [floor, target) allowed at a cost.
                for (s1, s2), _short in SOFT_REST_PAIRS.items():
                    _both = model.NewBoolVar(f"rest_short_{e}_{d1}_{s1}_{s2}")
                    model.Add(x[(e, d1, s1)] + x[(e, d2, s2)] - _both <= 1)
                    route_penalty(REST_SHORTFALL_PENALTY_PER_HOUR * _short, _both)

        # FRIDAY HEURISTIC: Soft reward for OFF/PM after Thursday night shift.
        # If employee worked N_22-05 on Thursday (from history), reward OFF or
        # afternoon shifts on Friday. Steven (forced_libres) is exempt.
        # Weight: -300k (soft — preserves feasibility).
        FRIDAY_NIGHT_REWARD = 300000
        for e in self.employees:
            if self.emp_data[e].get("forced_libres", False):
                continue
            last_jue = most_recent_schedule.get(e, {}).get("Jue", "")
            if last_jue == "N_22-05":
                # Reward OFF on Friday
                route_penalty(-FRIDAY_NIGHT_REWARD, x[(e, "Vie", "OFF")])
                # Reward afternoon shifts on Friday (starts >= 12)
                for s in SHIFT_NAMES:
                    if s in ("OFF", "VAC", "PERM", "N_22-05"):
                        continue
                    if SHIFT_IS_WORKING.get(s, False):
                        min_h = SHIFT_MIN_HOUR.get(s)
                        if min_h is not None and min_h >= 12:
                            route_penalty(-FRIDAY_NIGHT_REWARD, x[(e, "Vie", s)])

        # Empleados no disponibles por día — incluye VAC/PERM/OFF en fixed_constraints
        unavailable_per_day = {}
        for _d in DAYS:
            _count = 0
            for _e in self.employees:
                if fixed_constraints.get((_e, _d)) in ("VAC", "PERM", "OFF"):
                    _count += 1
            unavailable_per_day[_d] = _count

        # Detectar si Q shifts están activos (global o por empleado parcial).
        # Cuando Q está activo, h11/h12 se relajan de hard-min=3 a hard-min=2
        # para que un trabajador AM pueda cambiar a Q sin causar infeasibility.
        _q_shifts_active = (
            self.config.get('allow_collision_quebrado', False) or
            any(self.emp_data[e].get('forced_quebrado_partial', False) for e in self.employees) or
            not standard_mode
        )

        # Cobertura
        coverage = {}
        hour_at_cap = {}
        # Tope configurable de personas en pista al mismo tiempo (por hora).
        # Si el usuario no lo define, se usa el valor por defecto del sistema.
        overstaff_cap = resolve_overstaff_cap(self.config)
        overstaff_policy = get_overstaff_policy_for_days(day_modes, cap_value=overstaff_cap)
        for d in DAYS:
            available_day = len(self.employees) - unavailable_per_day.get(d, 0)
            for h in HOURS:
                mn, mx = effective_coverage_bounds(
                    h,
                    d,
                    standard_mode,
                    special_day_mode=day_modes.get(d),
                    cap_value=overstaff_cap,
                )
                terms = []

                if primary_night and h in SHIFTS["N_22-05"]:
                    # Includes VAC/PERM as OFF
                    terms.append(1 - (x[(primary_night, d, "OFF")] + x[(primary_night, d, "VAC")] + x[(primary_night, d, "PERM")]))

                for e in self.employees:
                    for s in SHIFT_NAMES:
                        if h in SHIFTS[s]:
                             if primary_night and e == primary_night and s == "N_22-05":
                                 continue
                             terms.append(x[(e, d, s)])

                cov = model.NewIntVar(0, len(self.employees) + 1, f"cov_{d}_{h}")
                model.Add(cov == sum(terms))
                coverage[(d, h)] = cov
                # Si hay empleados en VAC/PERM, reducir el mínimo requerido para
                # que el solver nunca sea INFEASIBLE por causa de vacaciones/permisos.
                # Cuando Q está activo, relajar h11/h12 de hard-min=3 a hard-min=2 en días
                # normales: esto permite que un trabajador AM (T1/T3) cambie a Q sin que h11
                # caiga debajo del mínimo. Una penalidad soft separada (200k) compensa.
                if _q_shifts_active and h in (11, 12) and day_modes.get(d) == SPECIAL_DAY_MODE_NORMAL:
                    mn_adjusted = max(0, min(2, available_day))
                else:
                    mn_adjusted = max(0, min(mn, available_day))
                model.Add(cov >= mn_adjusted)
                model.Add(cov <= mx)
                if d in overstaff_policy["days"] and mx >= overstaff_policy["cap_value"]:
                    at_cap = model.NewBoolVar(f"at_cap_{d}_{h}")
                    model.Add(cov == overstaff_policy["cap_value"]).OnlyEnforceIf(at_cap)
                    model.Add(cov != overstaff_policy["cap_value"]).OnlyEnforceIf(at_cap.Not())
                    hour_at_cap[(d, h)] = at_cap
                    peak_penalties.append(50000 * at_cap)

        for d in overstaff_policy.get("limited_days", overstaff_policy["days"]):
            day_cap_hours = [hour_at_cap[(d, h)] for h in HOURS if (d, h) in hour_at_cap]
            if day_cap_hours:
                model.Add(sum(day_cap_hours) <= overstaff_policy["allowed_hours_at_cap_per_day"])

        # =========================
        # SOFT CONSTRAINT: Prefer 4+ people during peak hours (Lun-Sáb, h7-19)
        # Uses broken shifts (Q1/Q2) to achieve this when possible.
        # =========================
        
        # SOFT: h5 (5-6am) is now a hard exact-2 rule via coverage_bounds().
        # Keep only the h6 soft target here.
        for d in DAYS:
            if day_modes.get(d) != SPECIAL_DAY_MODE_NORMAL:
                continue
            # Si hay VAC/PERM que impiden alcanzar 3, no penalizar (no es culpa del horario)
            if len(self.employees) - unavailable_per_day.get(d, 0) < 3:
                continue
            # h6 target 3 (6-7am)
            cov6 = coverage[(d, 6)]
            below_3_h6 = model.NewBoolVar(f"below3_h6_{d}")
            model.Add(cov6 < 3).OnlyEnforceIf(below_3_h6)
            model.Add(cov6 >= 3).OnlyEnforceIf(below_3_h6.Not())
            route_penalty(200000, below_3_h6)

        # SOFT: Cuando Q está activo, penalizar h11/h12 < 3 (200k).
        # Esto compensa la relajación del hard-min (3→2) hecha arriba: el solver
        # solo acepta bajar a 2 en h11/h12 cuando el gain de PM (500k/hr) lo justifica.
        if _q_shifts_active:
            for d in DAYS:
                if day_modes.get(d) != SPECIAL_DAY_MODE_NORMAL:
                    continue
                if len(self.employees) - unavailable_per_day.get(d, 0) < 3:
                    continue
                for h in (11, 12):
                    cov_h = coverage[(d, h)]
                    below_3_h = model.NewBoolVar(f"below3_h{h}_{d}_q")
                    model.Add(cov_h < 3).OnlyEnforceIf(below_3_h)
                    model.Add(cov_h >= 3).OnlyEnforceIf(below_3_h.Not())
                    route_penalty(200000, below_3_h)

        # SOFT: Prefer 4+ people during peak hours (Lun-Sáb, h7-10 and h16-19)
        # AM peak (h7-h10) has a much higher penalty than PM — losing AM coverage can NEVER
        # be compensated by stacking PM shifts. 5M per hour ensures the solver always
        # prioritizes AM coverage over any PM combination.
        for d in DAYS:
            if day_modes.get(d) != SPECIAL_DAY_MODE_NORMAL:
                continue
            # Si VAC/PERM impiden tener 4 personas, no aplicar la penalidad de "bajo 4"
            if len(self.employees) - unavailable_per_day.get(d, 0) < 4:
                continue
            for h in [7, 8, 9, 10, 16, 17, 18, 19]:
                cov = coverage[(d, h)]
                below_4 = model.NewBoolVar(f"below4_{d}_{h}")
                model.Add(cov < 4).OnlyEnforceIf(below_4)
                model.Add(cov >= 4).OnlyEnforceIf(below_4.Not())
                # AM hours get 5M penalty (uncrossable). PM hours: 500k in standard
                # mode (staff is ample, keep it a soft tie-break so consistency holds),
                # 1M in short-staffed mode — above the 900k consistency penalty so the
                # solver prefers reaching the IDEAL (4) at PM peak over keeping a person
                # on their consistent shift, whenever a feasible reassignment exists
                # (policy B: coverage wins the tradeoff, scoped to the short-staffed case).
                pm_penalty = 500000 if standard_mode else 1000000
                am_penalty = 5000000 if h in [7, 8, 9, 10] else pm_penalty
                route_penalty(am_penalty, below_4)

        # SOFT: Prefer 4+ people during off-peak hours as well (Lun-Sáb, h11-15)
        # But this penalty is much lower, so solver drops these hours first if short-staffed
        for d in DAYS:
            if day_modes.get(d) != SPECIAL_DAY_MODE_NORMAL:
                continue
            if len(self.employees) - unavailable_per_day.get(d, 0) < 4:
                continue
            for h in [11, 12, 13, 14, 15]:
                cov = coverage[(d, h)]
                below_4 = model.NewBoolVar(f"below4_{d}_{h}")
                model.Add(cov < 4).OnlyEnforceIf(below_4)
                model.Add(cov >= 4).OnlyEnforceIf(below_4.Not())
                peak_penalties.append(100000 * below_4)

        # Holy Thursday above-target penalties REMOVED.
        # The old penalties (180k-250k per hour for exceeding target coverage)
        # actively discouraged having extra people on Thursday, forcing the solver
        # to redistribute off-days to normal weekdays and creating coverage gaps
        # on Vie-Mié.  Hard coverage_bounds (4 AM, 3 PM) still guarantee minimums.
        # The solver is now free to overstaff Thursday when it improves the
        # overall weekly schedule.

        # =========================
        # SOFT PREFERENCE: Concentrate broken shifts on fewer people
        # Coverage rules are MORE important than concentrating broken shifts.
        # Night person and Jefe de Pista CANNOT have broken shifts (hard).
        # Everyone else CAN, but spreading incurs a penalty.
        # =========================
        # Hard: night person and Jefe de pista never get broken shifts
        for e in self.employees:
            if e == night_person_name or self.emp_data[e].get('is_jefe_pista', False) or self.emp_data[e].get('is_practicante', False):
                for d in DAYS:
                    model.Add(x[(e, d, "Q1_05-11+17-20")] == 0)
                    model.Add(x[(e, d, "Q2_07-11+17-20")] == 0)
                    model.Add(x[(e, d, "Q3_05-11+17-22")] == 0)
        
        # Soft: standard_mode — ligera preferencia por concentrar Q en menos gente.
        if standard_mode:
            for e in self.employees:
                if e == night_person_name or self.emp_data[e].get('is_jefe_pista', False) or self.emp_data[e].get('is_practicante', False):
                    continue
                # forced_quebrado_total always has Q — penalizing spread is meaningless
                if self.emp_data[e].get('forced_quebrado', False):
                    continue
                has_any_q = model.NewBoolVar(f"has_any_q_{e}")
                q_sum = sum(x[(e, d, "Q1_05-11+17-20")] + x[(e, d, "Q2_07-11+17-20")] + x[(e, d, "Q3_05-11+17-22")] for d in DAYS)
                model.Add(q_sum >= 1).OnlyEnforceIf(has_any_q)
                model.Add(q_sum == 0).OnlyEnforceIf(has_any_q.Not())
                pen_q_spread = model.NewIntVar(0, 100, f"pen_q_spread_{e}")
                model.Add(pen_q_spread == 100).OnlyEnforceIf(has_any_q)
                model.Add(pen_q_spread == 0).OnlyEnforceIf(has_any_q.Not())
                peak_penalties.append(pen_q_spread)

        # Short-staff: preferir UNA sola persona distinta con quebrados en la semana.
        if not standard_mode:
            q_carrier_eligible = []
            for e in self.employees:
                if self.emp_data[e].get("is_refuerzo", False):
                    continue
                if e == night_person_name or self.emp_data[e].get("is_jefe_pista", False) or self.emp_data[e].get("is_practicante", False):
                    continue
                q_carrier_eligible.append(e)
            if q_carrier_eligible:
                carrier_bools = []
                for e in q_carrier_eligible:
                    cq = model.NewBoolVar(f"q_week_carrier_{e}")
                    q_week = sum(
                        x[(e, d, "Q1_05-11+17-20")]
                        + x[(e, d, "Q2_07-11+17-20")]
                        + x[(e, d, "Q3_05-11+17-22")]
                        for d in DAYS
                    )
                    model.Add(q_week >= 1).OnlyEnforceIf(cq)
                    model.Add(q_week == 0).OnlyEnforceIf(cq.Not())
                    carrier_bools.append(cq)
                nq_distinct = model.NewIntVar(0, len(carrier_bools), "q_distinct_carriers_week")
                model.Add(nq_distinct == sum(carrier_bools))
                at_most_one_distinct = model.NewBoolVar("q_at_most_one_distinct_carrier")
                model.Add(nq_distinct <= 1).OnlyEnforceIf(at_most_one_distinct)
                model.Add(nq_distinct >= 2).OnlyEnforceIf(at_most_one_distinct.Not())
                q_extra_carriers = model.NewIntVar(0, max(0, len(carrier_bools) - 1), "q_extra_carriers_beyond_first")
                model.Add(q_extra_carriers == 0).OnlyEnforceIf(at_most_one_distinct)
                model.Add(q_extra_carriers == nq_distinct - 1).OnlyEnforceIf(at_most_one_distinct.Not())
                QUEBRADO_EXTRA_CARRIER_PENALTY = 1_200_000
                route_penalty(QUEBRADO_EXTRA_CARRIER_PENALTY, q_extra_carriers)

        # =========================
        # RESTRICCIÓN: PENALIZACIÓN DE TURNOS OVERTIME (T11, T16)
        # =========================
        # The user requested to keep T11, T16 but heavily penalize them so they 
        # are only used when absolutely necessary to satisfy coverage bounds on Saturdays/Peak.
        OVERTIME_PENALTY = 750000
        for e in self.employees:
            for d in DAYS:
                route_penalty(OVERTIME_PENALTY, x[(e, d, "T11_12-20")])
                route_penalty(OVERTIME_PENALTY, x[(e, d, "T16_05-14")])
            
        # =========================
        # CONSTRAINT: Forced Quebrado (Hard)
        # If employee has forced_quebrado=True, they must work Q1/Q2/Q3 on ALL working days.
        # Exactly 1 OFF day (or VAC/PERM). No other shift types allowed.
        # quebrado_preferido narrows allowed Q types to a specific one.
        # =========================
        ALL_Q_SHIFTS = ["Q1_05-11+17-20", "Q2_07-11+17-20", "Q3_05-11+17-22"]
        for e in self.employees:
            if self.emp_data[e].get('forced_quebrado', False):
                if absent_all_week(e):
                    # Whole week on VAC/PERM: the pills pin every day, so neither the
                    # Q-only rule nor the single rest day can apply (see absent_all_week).
                    continue
                qpref = self.emp_data[e].get('quebrado_preferido', 'auto')
                if qpref == 'auto' or qpref not in ALL_Q_SHIFTS:
                    allowed_q = ALL_Q_SHIFTS  # comportamiento actual
                else:
                    allowed_q = [qpref]       # solo el Q preferido
                for d in DAYS:
                    if is_special_sunday_like(d):
                        # Domingos: NO queremos que haga quebrado. Preferencia
                        # fuerte (20M) para que haga turno normal de domingo.
                        # Si cobertura obliga, el solver puede asignar Q igual.
                        for qs in ALL_Q_SHIFTS:
                            route_penalty(20_000_000, x[(e, d, qs)])
                        continue
                    for s in SHIFT_NAMES:
                        if s not in ["OFF", "VAC", "PERM"] + allowed_q:
                            model.Add(x[(e, d, s)] == 0)
                model.Add(sum(x[(e, d, "OFF")] + x[(e, d, "VAC")] + x[(e, d, "PERM")] for d in DAYS) == 1)

        # =========================
        # STRICT OFF-DAY DISTRIBUTION (HARD CONSTRAINTS)
        # =========================
        # Rules:
        #   - Weekdays: normally 1 person OFF per day.
        #   - Exactly 1 "elective collision day" where 2 people are OFF (from OFF distribution).
        #   - Days with >=2 mandatory absences (VAC/PERM) are "forced collision days" — don't count.
        #   - Sunday: up to 2 people OFF.
        #   - The engine CANNOT create additional collision days beyond the 1 elective.
        #   - Refuerzo works on collision days (elective + forced).
        # =========================
        
        # Build flex OFF count per day (excluding Jefe, Night, Refuerzo)
        use_refuerzo = self.refuerzo_name in self.employees
        refuerzo_active_days = {}  # d -> BoolVar
        
        weekdays = [d for d in DAYS if is_weekday_like(d)]
        flex_off_per_day = {}  # d -> CP-SAT expression
        collision_vars = {}   # d -> BoolVar (True if this weekday has 2+ people OFF)
        
        # Pre-count mandatory absences (VAC/PERM from fixed_shifts) per weekday
        mandatory_absent = {}
        for d in weekdays:
            count = 0
            for e in self.employees:
                if self.emp_data[e].get('is_refuerzo', False): continue
                if e == primary_night: continue
                if self.emp_data[e].get('is_jefe_pista', False): continue
                fixed = self.emp_data[e].get('fixed_shifts', {})
                if fixed.get(d) in ['VAC', 'PERM']:
                    count += 1
            mandatory_absent[d] = count
        
        forced_collision_days = [d for d in weekdays if mandatory_absent[d] >= 2]
        elective_days = [d for d in weekdays if d not in forced_collision_days]
        
        # Detect "Sáb+Dom only" employees: those with fixed OFF on every weekday (Lun-Vie).
        # They always work Sunday and should never appear in the Sunday OFF count.
        sat_dom_only = set(
            e for e in self.employees
            if not self.emp_data[e].get('is_refuerzo', False)
            and e != primary_night
            and not self.emp_data[e].get('is_jefe_pista', False)
            and all(
                self.emp_data[e].get('fixed_shifts', {}).get(d) in ['OFF', 'VAC', 'PERM']
                for d in ["Lun", "Mar", "Mié", "Jue", "Vie"]
            )
        )

        for d in DAYS:
            flex_off_per_day[d] = sum(
                x[(e, d, "OFF")] + x[(e, d, "VAC")] + x[(e, d, "PERM")]
                for e in self.employees
                if not self.emp_data[e].get('is_refuerzo', False)
                and e != primary_night
                and not self.emp_data[e].get('is_jefe_pista', False)
                and (not is_special_sunday_like(d) or e not in sat_dom_only)
            )

        # HARD: Sunday allows up to 2 elective flex OFFs + any mandatory fixed DOM OFFs.
        # Fixed DOM OFFs are guaranteed by hard constraints elsewhere and don't consume
        # an elective slot — the cap only limits truly discretionary Sunday absences.
        # Sunday OFF count is coverage-driven.
        # We intentionally avoid an artificial cap here so surplus staff can be
        # sent home on Sunday whenever the Sunday rules and hourly coverage hold.
        
        # =========================
        # HARD CONSTRAINT: D4_13-22 on Sunday
        # =========================
        # Force at least 1 eligible person to use D4_13-22 (1pm-10pm) on Sunday.
        # Eligible: can_do_night (D4 touches night hours 20-21), not jefe, not night person, not refuerzo.
        # EXCEPCIÓN: empleados con fixed_shift N_22-05 el domingo también se excluyen
        # (ya están cubriendo la noche manualmente, no pueden hacer D4 al mismo tiempo).
        d4_sunday_eligible = []
        for e in self.employees:
            if self.emp_data[e].get('is_jefe_pista', False):
                continue
            if self.emp_data[e].get('is_practicante', False):
                continue
            if e == primary_night:
                continue
            if not self.emp_data[e].get('can_do_night', True):
                continue
            if self.emp_data[e].get('is_refuerzo', False):
                continue
            # Excluir a quien tiene N_22-05 fijado el domingo
            if self.emp_data[e].get('fixed_shifts', {}).get('Dom') == "N_22-05":
                continue
            # Skip employees with hard-fixed Sunday shifts that aren't D4
            if (e, "Dom") in fixed_constraints and fixed_constraints[(e, "Dom")] != "D4_13-22":
                continue
            d4_sunday_eligible.append(e)
        
        if is_sunday_style_mode(day_modes.get("Dom", SPECIAL_DAY_MODE_NORMAL)) and d4_sunday_eligible:
            model.Add(sum(x[(e, "Dom", "D4_13-22")] for e in d4_sunday_eligible) >= 1)
        
        # Mínimo de "slots" de ausencia flex por día: debe cubrir todo lo ya fijado en duro
        # (OFF estricto, VAC, PERM). Si no, casos como PERM + 2× OFF el sábado chocan con
        # max_off = max(2, mandatory_absent) aunque mandatory_absent solo contaba VAC/PERM.
        hard_flex_absent_per_day = {}
        for d in weekdays:
            cnt = 0
            for e in self.employees:
                if self.emp_data[e].get('is_refuerzo', False):
                    continue
                if e == primary_night:
                    continue
                if self.emp_data[e].get('is_jefe_pista', False):
                    continue
                if is_special_sunday_like(d) and e in sat_dom_only:
                    continue
                fc = fixed_constraints.get((e, d))
                if fc in ("OFF", "VAC", "PERM"):
                    cnt += 1
            hard_flex_absent_per_day[d] = cnt

        # HARD: Each weekday, allow up to max_off conditionally.
        for d in weekdays:
            # Tope = al menos 4, o ausencias obligatorias VAC/PERM, o ausencias flex en duro.
            # Se usa 4 para dar holgura al LP relaxation de OR-Tools (evita fixed_search crash
            # cuando hay 3+ OFF fijos combinados con refuerzo parcial).
            max_off = max(4, mandatory_absent[d], hard_flex_absent_per_day.get(d, 0))
            model.Add(flex_off_per_day[d] <= max_off)
            
            collision_vars[d] = model.NewBoolVar(f"collision_{d}")
            model.Add(flex_off_per_day[d] >= 2).OnlyEnforceIf(collision_vars[d])
            model.Add(flex_off_per_day[d] < 2).OnlyEnforceIf(collision_vars[d].Not())
        
        # Do not pre-force weekday collision days.
        # Weekly OFF totals plus daily coverage determine when collisions are
        # truly necessary, and the objective keeps them to the minimum.

        # Forced collision days are always True
        for d in forced_collision_days:
            model.Add(collision_vars[d] == 1)
            
        # =========================
        # PREVENT EXCESS COLLISION DAYS
        # =========================
        # Add a strong penalty for every collision day. This prevents the solver from
        # creating unnecessary collision days (and thus scheduling Refuerzo multiple times)
        # just to optimize minor handoff bonuses. It will only create them if mathematically
        # required or if a 5,000,000 strict preference penalty forces it.
        for d in weekdays:
            penalties.append(100000 * collision_vars[d])

        # Homogeneity guard: if a weekday is already compressed at the 5-person cap
        # or piles too many employees into the exact same shift, Sunday should stop
        # being an automatic winner for extra OFFs.
        weekday_congestion = {}
        for d in weekdays:
            day_cap_hours = [hour_at_cap[(d, h)] for h in HOURS if (d, h) in hour_at_cap]
            day_at_cap = model.NewBoolVar(f"day_at_cap_{d}")
            if day_cap_hours:
                model.Add(sum(day_cap_hours) >= 1).OnlyEnforceIf(day_at_cap)
                model.Add(sum(day_cap_hours) == 0).OnlyEnforceIf(day_at_cap.Not())
            else:
                model.Add(day_at_cap == 0)

            shift_stack_signals = []
            for s in HOMOGENEITY_MONITORED_SHIFTS:
                shift_count = sum(
                    x[(e, d, s)]
                    for e in self.employees
                    if not self.emp_data[e].get('is_refuerzo', False)
                )

                stack_3 = model.NewBoolVar(f"shift_stack3_{d}_{s}")
                model.Add(shift_count >= 3).OnlyEnforceIf(stack_3)
                model.Add(shift_count <= 2).OnlyEnforceIf(stack_3.Not())
                penalties.append(SAME_SHIFT_STACK_PENALTY_3 * stack_3)

                stack_4 = model.NewBoolVar(f"shift_stack4_{d}_{s}")
                model.Add(shift_count >= 4).OnlyEnforceIf(stack_4)
                model.Add(shift_count <= 3).OnlyEnforceIf(stack_4.Not())
                penalties.append(SAME_SHIFT_STACK_PENALTY_4 * stack_4)
                shift_stack_signals.append(stack_4)

                stack_5 = model.NewBoolVar(f"shift_stack5_{d}_{s}")
                model.Add(shift_count >= 5).OnlyEnforceIf(stack_5)
                model.Add(shift_count <= 4).OnlyEnforceIf(stack_5.Not())
                penalties.append(SAME_SHIFT_STACK_PENALTY_5 * stack_5)
                shift_stack_signals.append(stack_5)

            day_shift_stack = model.NewBoolVar(f"day_shift_stack_{d}")
            if shift_stack_signals:
                model.Add(sum(shift_stack_signals) >= 1).OnlyEnforceIf(day_shift_stack)
                model.Add(sum(shift_stack_signals) == 0).OnlyEnforceIf(day_shift_stack.Not())
            else:
                model.Add(day_shift_stack == 0)

            weekday_congestion[d] = model.NewBoolVar(f"weekday_congestion_{d}")
            model.Add(day_at_cap + day_shift_stack >= 1).OnlyEnforceIf(weekday_congestion[d])
            model.Add(day_at_cap + day_shift_stack == 0).OnlyEnforceIf(weekday_congestion[d].Not())

        # =========================
        # NIGHT PERSON: Must work on collision day
        # =========================
        # Force the night person to work N_22-05 on collision days
        # so the libres person is free to work a day shift (extra body)
        if primary_night:
            for d in weekdays:
                # RELAXED: Soft constraint instead of hard Add
                # Penalize if night person is NOT working on a collision day
                is_working_night = x[(primary_night, d, "N_22-05")]
                night_not_on_collision = model.NewBoolVar(f"night_not_on_collision_{d}")
                model.AddBoolAnd([collision_vars[d], is_working_night.Not()]).OnlyEnforceIf(night_not_on_collision)
                model.AddBoolOr([collision_vars[d].Not(), is_working_night]).OnlyEnforceIf(night_not_on_collision.Not())
                route_penalty(1000000, night_not_on_collision)
        
        # =========================
        # COLLISION DAY CONFIG
        # =========================
        # Q-shift control is handled entirely via penalties in standard_mode:
        #   allow_collision_q ON  -> q1_penalty = 200k (solver uses Q only when 500k coverage gap)
        #   allow_collision_q OFF -> q1_penalty = 999k + hard block (Q never used)
        allow_collision_q = self.config.get('allow_collision_quebrado', False)
        collision_peak_priority = self.config.get('collision_peak_priority', 'pm')
        
        # =========================
        # PEAK GUARD: Elective Collision Day
        # =========================
        if allow_collision_q:
            # With Q shifts enabled, target 4/4 on collision day
            min_peak_am = 4
            min_peak_pm = 4
        else:
            # Without Q, user chooses which peak gets priority
            if collision_peak_priority == 'am':
                min_peak_am = 4
                min_peak_pm = 3
            else:  # 'pm' (default — gas station PM is busier)
                min_peak_am = 3
                min_peak_pm = 4
        
        elective_collision = {}
        for d in weekdays:
            elective_collision[d] = model.NewBoolVar(f"elective_collision_{d}")
            if d in forced_collision_days:
                model.Add(elective_collision[d] == 0)
            else:
                model.Add(elective_collision[d] == 1).OnlyEnforceIf(collision_vars[d])
                model.Add(elective_collision[d] == 0).OnlyEnforceIf(collision_vars[d].Not())
        
        # =========================
        # Enforce peak coverage minimums on the elective collision day
        # Uses massive SOFT penalties (2,000,000) so it tries desperately to hit targets
        # but won't return INFEASIBLE if the only available person is blocked by 12h rest rules.
        # =========================
        for d in weekdays:
            for h in [7, 8, 9, 10]:
                cov = coverage[(d, h)]
                shortfall_am = model.NewIntVar(0, 10, f"shortfall_am_{d}_{h}")
                # shortfall_am >= min_peak_am - cov
                model.Add(shortfall_am >= min_peak_am - cov).OnlyEnforceIf(elective_collision[d])
                model.Add(shortfall_am >= 0) # never negative
                route_penalty(2000000, shortfall_am)

            for h in [17, 18, 19]:
                cov = coverage[(d, h)]
                shortfall_pm = model.NewIntVar(0, 10, f"shortfall_pm_{d}_{h}")
                model.Add(shortfall_pm >= min_peak_pm - cov).OnlyEnforceIf(elective_collision[d])
                model.Add(shortfall_pm >= 0)
                route_penalty(2000000, shortfall_pm)
        
        # =========================
        # GLOBAL QUEBRADO TOGGLE
        # When disabled, block ALL quebrado shifts for everyone except
        # forced_quebrado/forced_quebrado_partial employees (params panel override).
        # If coverage fails without Q, the solver returns INFEASIBLE.
        # =========================
        allow_global_q = self.config.get('allow_global_quebrado', True)
        if not allow_global_q:
            ALL_Q = ["Q1_05-11+17-20", "Q2_07-11+17-20", "Q3_05-11+17-22"]
            for e in self.employees:
                is_forced_q = self.emp_data[e].get('forced_quebrado', False)
                is_forced_qp = self.emp_data[e].get('forced_quebrado_partial', False)
                if is_forced_q or is_forced_qp:
                    continue  # Respect params panel override
                for d in DAYS:
                    for qs in ALL_Q:
                        model.Add(x[(e, d, qs)] == 0)

        # =========================
        # REFUERZO LOGIC
        # =========================
        # When refuerzo_partial_mode is active, the refuerzo uses fixed_shifts
        # like a regular employee — no special refuerzo logic needed.
        ref_partial_mode = self.config.get('refuerzo_partial_mode', False)
        if use_refuerzo and not ref_partial_mode:
            refuerzo = self.refuerzo_name
            ref_type = self.config.get('refuerzo_type', 'personalizado')
            ref_days_mode = self.config.get('refuerzo_days_mode', 'auto')
            ref_manual_days = self.config.get('refuerzo_manual_days', [])
            saturday_only_refuerzo = ref_type == "sabado"
            effective_ref_type = "automatico" if saturday_only_refuerzo else ref_type

            # Detect per-day schedule (new format) vs legacy single shift
            has_per_day_schedule = isinstance(current_refuerzo_custom_shift, dict)
            has_legacy_shift = isinstance(current_refuerzo_custom_shift, str)

            # Determinar días activos del refuerzo
            refuerzo_active_days = {}

            # Si modo manual, usar días específicos; sino usar collision days
            if has_per_day_schedule:
                # NEW: per-day schedule — schedule keys ARE the manual days
                use_manual_days = True
                ref_manual_days = list(current_refuerzo_custom_shift.keys())
            else:
                use_manual_days = ref_days_mode == "manual" and ref_manual_days

            for d in DAYS:
                if is_special_closed(d):
                    # Local cerrado: nadie trabaja, sin excepción.
                    model.Add(x[(refuerzo, d, "OFF")] == 1)
                    refuerzo_active_days[d] = model.NewConstant(0)
                    continue

                if is_special_sunday_like(d):
                    # Domingo (o "como domingo"): OFF forzado salvo que el día
                    # esté EXPLÍCITAMENTE seleccionado en el horario del refuerzo.
                    day_explicitly_selected = (
                        (has_per_day_schedule and d in current_refuerzo_custom_shift)
                        or (use_manual_days and d in ref_manual_days)
                    )
                    if not day_explicitly_selected:
                        model.Add(x[(refuerzo, d, "OFF")] == 1)
                        refuerzo_active_days[d] = model.NewConstant(0)
                        continue

                if saturday_only_refuerzo:
                    if d == "Sáb":
                        model.Add(x[(refuerzo, d, "OFF")] == 0)
                        refuerzo_active_days[d] = model.NewConstant(1)
                    else:
                        model.Add(x[(refuerzo, d, "OFF")] == 1)
                        refuerzo_active_days[d] = model.NewConstant(0)
                    continue

                if use_manual_days:
                    # Modo manual: Refuerzo trabaja solo en días seleccionados
                    is_auto_day = (
                        has_per_day_schedule
                        and current_refuerzo_custom_shift.get(d) == REFUERZO_AUTO_DAY
                    )
                    if is_auto_day:
                        # Día AUTO: NO forzar OFF — el solver decide si trabaja.
                        works = model.NewBoolVar(f"ref_auto_works_{refuerzo}_{d}")
                        model.Add(x[(refuerzo, d, "OFF")] == 0).OnlyEnforceIf(works)
                        model.Add(x[(refuerzo, d, "OFF")] == 1).OnlyEnforceIf(works.Not())
                        refuerzo_active_days[d] = works
                    elif d in ref_manual_days:
                        model.Add(x[(refuerzo, d, "OFF")] == 0)
                        refuerzo_active_days[d] = model.NewConstant(1)
                    else:
                        model.Add(x[(refuerzo, d, "OFF")] == 1)
                        refuerzo_active_days[d] = model.NewConstant(0)
                else:
                    # Modo automático: Refuerzo trabaja en collision days
                    model.Add(x[(refuerzo, d, "OFF")] == 0).OnlyEnforceIf(collision_vars[d])
                    model.Add(x[(refuerzo, d, "OFF")] == 1).OnlyEnforceIf(collision_vars[d].Not())
                    refuerzo_active_days[d] = collision_vars[d]

            # Pool de turnos para días AUTO (el solver elige uno, o deja OFF).
            if standard_mode:
                refuerzo_auto_pool = {default_diurno_refuerzo_shift, "R2_16-20"}
            else:
                refuerzo_auto_pool = {
                    default_diurno_refuerzo_shift, "R2_16-20",
                    "T1_05-13", "T16_05-14", "T2_06-14", "D1_05-13",
                    "T3_07-15", "T5_09-17", "T17_16-23",
                    "T8_13-20", "T13_16-22", "T12_14-22", "D2_14-22", "D3_15-23",
                    "N_22-05", "Q3_05-11+17-22",
                }

            # Turnos Permitidos — per-day schedule gets its own shift per day
            if has_per_day_schedule:
                for d in DAYS:
                    day_shift = current_refuerzo_custom_shift.get(d)
                    if day_shift == REFUERZO_AUTO_DAY:
                        # Día AUTO: permitir el pool (+ OFF); el solver elige.
                        for s in SHIFT_NAMES:
                            if s != "OFF" and s not in refuerzo_auto_pool:
                                model.Add(x[(refuerzo, d, s)] == 0)
                    elif day_shift is not None:
                        # Día FIJO: solo su turno específico (+ OFF).
                        for s in SHIFT_NAMES:
                            if s != day_shift and s != "OFF":
                                model.Add(x[(refuerzo, d, s)] == 0)
                    else:
                        # Day is OFF — only allow OFF
                        for s in SHIFT_NAMES:
                            if s != "OFF":
                                model.Add(x[(refuerzo, d, s)] == 0)
            else:
                # Legacy: single shift code or automatic/diurno/nocturno/sabado
                allowed_shifts_refuerzo = ["OFF"]
                if effective_ref_type == 'personalizado' and has_legacy_shift:
                    allowed_shifts_refuerzo.append(current_refuerzo_custom_shift)
                elif standard_mode:
                    if effective_ref_type == 'nocturno':
                        allowed_shifts_refuerzo.extend(["R2_16-20"])
                    elif effective_ref_type == 'diurno':
                        allowed_shifts_refuerzo.extend([default_diurno_refuerzo_shift])
                    else: # automatico
                        allowed_shifts_refuerzo.extend([default_diurno_refuerzo_shift, "R2_16-20"])
                else:
                    if effective_ref_type == 'nocturno':
                        allowed_shifts_refuerzo.extend(["R2_16-20", "T17_16-23", "N_22-05", "T10_15-22", "T12_14-22", "T13_16-22", "D2_14-22", "D3_15-23"])
                    elif effective_ref_type == 'diurno':
                        # Daytime-only refuerzo: morning/day shifts exclusively.
                        # Afternoon/evening shifts (start >= 13h) must never be
                        # offered here — that's the 'nocturno'/'automatico' pool.
                        allowed_shifts_refuerzo.extend([
                            default_diurno_refuerzo_shift, "T1_05-13", "T16_05-14", "T2_06-14", "D1_05-13",
                            "T3_07-15", "T5_09-17"
                        ])
                    else: # automatico
                        allowed_shifts_refuerzo.extend([
                            default_diurno_refuerzo_shift, "R2_16-20",
                            "T1_05-13", "T16_05-14", "T2_06-14", "D1_05-13",
                            "T3_07-15", "T5_09-17", "T17_16-23",
                            "T8_13-20", "T13_16-22", "T12_14-22", "D2_14-22", "D3_15-23",
                            "N_22-05", "Q3_05-11+17-22"
                        ])

                for d in DAYS:
                    for s in SHIFT_NAMES:
                        if s not in allowed_shifts_refuerzo:
                            model.Add(x[(refuerzo, d, s)] == 0)

        # =========================
        # ADDITIONAL NAMED REFUERZOS — non-personalizado mode constraints
        # personalizado mode is already handled by fixed_shifts + strict_preferences=True
        # =========================
        for _ae in self.employees:
            _ae_info = self.emp_data.get(_ae, {})
            if not _ae_info.get('is_refuerzo'):
                continue
            if _ae == self.refuerzo_name:
                continue  # legacy refuerzo handled in REFUERZO LOGIC block above
            _ae_tipo = _ae_info.get('refuerzo_tipo', 'personalizado')
            if _ae_tipo == 'personalizado':
                # Fixed/OFF days are handled via fixed_shifts + strict. Only AUTO days
                # need handling here: allow the pool (+ OFF) so the solver picks a
                # shift or leaves OFF (per-day mix of fixed and automatic).
                _ae_auto = _ae_info.get('refuerzo_auto_days', [])
                if _ae_auto:
                    if standard_mode:
                        _auto_pool = {default_diurno_refuerzo_shift, "R2_16-20"}
                    else:
                        _auto_pool = {
                            default_diurno_refuerzo_shift, "R2_16-20",
                            "T1_05-13", "T16_05-14", "T2_06-14", "D1_05-13",
                            "T3_07-15", "T5_09-17", "T17_16-23",
                            "T8_13-20", "T13_16-22", "T12_14-22", "D2_14-22", "D3_15-23",
                            "N_22-05", "Q3_05-11+17-22",
                        }
                    for _d in _ae_auto:
                        if _d not in DAYS or is_special_closed(_d):
                            continue
                        for _s in SHIFT_NAMES:
                            if _s != "OFF" and _s not in _auto_pool:
                                model.Add(x[(_ae, _d, _s)] == 0)
                continue  # handled via fixed_shifts (+ AUTO days above)
            _ae_active = _ae_info.get('refuerzo_active_days', [])
            # Day-level constraints
            for d in DAYS:
                if is_special_closed(d):
                    # Local cerrado: nadie trabaja, sin excepción.
                    model.Add(x[(_ae, d, "OFF")] == 1)
                elif is_special_sunday_like(d) and d not in _ae_active:
                    # Domingo (o "como domingo"): OFF forzado salvo que el día
                    # esté explícitamente seleccionado en el horario del refuerzo.
                    model.Add(x[(_ae, d, "OFF")] == 1)
                elif d in _ae_active:
                    model.Add(x[(_ae, d, "OFF")] == 0)
                else:
                    model.Add(x[(_ae, d, "OFF")] == 1)
            # Allowed shifts by mode
            _ae_allowed = {"OFF", "VAC", "PERM"}
            if _ae_tipo == 'nocturno':
                if standard_mode:
                    _ae_allowed.update(["R2_16-20"])
                else:
                    _ae_allowed.update(["R2_16-20", "T17_16-23", "N_22-05", "T10_15-22", "T12_14-22", "T13_16-22", "D2_14-22", "D3_15-23"])
            elif _ae_tipo == 'diurno':
                if standard_mode:
                    _ae_allowed.update([default_diurno_refuerzo_shift])
                else:
                    # Daytime-only refuerzo: no afternoon/evening shifts (start >= 13h).
                    _ae_allowed.update([default_diurno_refuerzo_shift, "T1_05-13", "T16_05-14", "T2_06-14", "D1_05-13", "T3_07-15", "T5_09-17"])
            else:  # automatico, sabado
                if standard_mode:
                    _ae_allowed.update([default_diurno_refuerzo_shift, "R2_16-20"])
                else:
                    _ae_allowed.update([
                        default_diurno_refuerzo_shift, "R2_16-20", "T1_05-13", "T16_05-14",
                        "T2_06-14", "D1_05-13", "T3_07-15", "T5_09-17", "T17_16-23",
                        "T8_13-20", "T13_16-22", "T12_14-22", "D2_14-22", "D3_15-23",
                        "N_22-05", "Q3_05-11+17-22",
                    ])
            for _d in DAYS:
                for _s in SHIFT_NAMES:
                    if _s not in _ae_allowed:
                        model.Add(x[(_ae, _d, _s)] == 0)

        # =========================
        # SOFT: Seamless Handoffs (Relevos Continuos)
        # If someone leaves at hour h, prefer someone entering at hour h
        # Focus on critical mid-day handoffs: 13:00, 14:00, 15:00
        # =========================
        for d in DAYS:
            if not is_weekday_like(d):
                continue
            for h in [13, 14, 15]:
                # Count people leaving at h (shift ends at h)
                leaving_terms = []
                for e in self.employees:
                    for s in SHIFT_NAMES:
                        if s in ["OFF", "VAC", "PERM"]: continue
                        hours = SHIFTS[s]
                        # Shift ends at h if max(hours) == h-1 ? No, standard is [start, end) usually
                        # Our SHIFTS definition is set of hours present.
                        # So if set is {6,7...15}, they work UNTIL 16:00. They leave AT 16:00.
                        # If set is {5...12}, max is 12, they leave at 13:00.
                        if not hours: continue
                        if max(hours) == (h - 1):
                            leaving_terms.append(x[(e, d, s)])
                
                # Count people entering at h (shift starts at h)
                entering_terms = []
                for e in self.employees:
                    for s in SHIFT_NAMES:
                        if s in ["OFF", "VAC", "PERM"]: continue
                        hours = SHIFTS[s]
                        if not hours: continue
                        if min(hours) == h:
                            entering_terms.append(x[(e, d, s)])

                n_leaving = sum(leaving_terms)
                n_entering = sum(entering_terms)
                
                # If leaving > 0 AND entering == 0 => Penalty
                is_leaving = model.NewBoolVar(f"is_leaving_{d}_{h}")
                model.Add(n_leaving > 0).OnlyEnforceIf(is_leaving)
                model.Add(n_leaving == 0).OnlyEnforceIf(is_leaving.Not())
                
                is_entering = model.NewBoolVar(f"is_entering_{d}_{h}")
                model.Add(n_entering > 0).OnlyEnforceIf(is_entering)
                model.Add(n_entering == 0).OnlyEnforceIf(is_entering.Not())
                
                # Gap condition: Leaving=True AND Entering=False
                gap_handoff = model.NewBoolVar(f"gap_handoff_{d}_{h}")
                model.AddBoolAnd([is_leaving, is_entering.Not()]).OnlyEnforceIf(gap_handoff)
                model.AddBoolOr([is_leaving.Not(), is_entering]).OnlyEnforceIf(gap_handoff.Not())
                
                # Penalty 500 per gap (strong but less than coverage failure)
                pen_gap = model.NewIntVar(0, 500, f"pen_gap_{d}_{h}")
                model.Add(pen_gap == 500).OnlyEnforceIf(gap_handoff)
                model.Add(pen_gap == 0).OnlyEnforceIf(gap_handoff.Not())
                peak_penalties.append(pen_gap)

        # Sistema de LIBRES (Constraints logic)
        for e in self.flexibles:
            # Count only OFF days (VAC is manual and separate)
            off_days = sum(x[(e, d, "OFF")] for d in DAYS)
            
            # Count how many days were manually fixed as OFF by the user
            fixed = self.emp_data[e].get('fixed_shifts', {})
            manual_off_count = sum(1 for d in DAYS if fixed.get(d) == "OFF")
            closed_off_count = sum(
                1 for d in DAYS
                if is_special_closed(d) and fixed.get(d) not in ["OFF", "VAC", "PERM"]
            )
            max_off = max(1, manual_off_count) + closed_off_count
            allow_no_rest = self.emp_data[e].get('allow_no_rest', False)
            # A week fully covered by VAC/PERM has no day left for an OFF, so the
            # rest-day floor cannot be met and must not be imposed.
            needs_rest_day = not allow_no_rest and not absent_all_week(e)

            if e in persona_hace_libres:
                # Libres candidates: conditional constraints
                if needs_rest_day:
                    model.Add(off_days >= 1).OnlyEnforceIf(persona_hace_libres[e])

                model.Add(off_days <= max_off).OnlyEnforceIf(persona_hace_libres[e])

                if needs_rest_day:
                    model.Add(off_days >= 1).OnlyEnforceIf(persona_hace_libres[e].Not())
                model.Add(off_days <= max_off + 1).OnlyEnforceIf(persona_hace_libres[e].Not())
            else:
                # Not in libres system (e.g. can't do night, or is night person)
                # Simple unconditional off-day constraint
                if needs_rest_day:
                    model.Add(off_days >= 1)
                model.Add(off_days <= max_off + 1)

        # RESTRICCIÓN: la persona que hace libres debe trabajar siempre que algún otro flexible esté LIBRE
        # REMOVED: This constraint is too aggressive for a 9-person team where someone is OFF every day.
        # It forces the Libres Person to work 7 days, violating off_days >= 1.
        # The coverage constraints (min X people) will naturally force them to work if needed.
        # for e_libres in self.flexibles:
        #      if e_libres not in self.night_replacements: continue
        #      
        #      for d in DAYS:
        #          # Count VAC as OFF
        #          otros_off_sum = sum((x[(e_otro, d, "OFF")] + x[(e_otro, d, "VAC")]) for e_otro in self.flexibles if e_otro != e_libres)
        #          
        #          hay_alguien_libre = model.NewBoolVar(f"alguien_libre_{e_libres}_{d}")
        #          model.Add(otros_off_sum >= 1).OnlyEnforceIf(hay_alguien_libre)
        #          model.Add(otros_off_sum == 0).OnlyEnforceIf(hay_alguien_libre.Not())
        #          
        #          model.Add(x[(e_libres, d, "OFF")] == 0).OnlyEnforceIf([
        #              persona_hace_libres[e_libres],
        #              hay_alguien_libre
        #          ])
        #          model.Add(x[(e_libres, d, "VAC")] == 0).OnlyEnforceIf([
        #              persona_hace_libres[e_libres],
        #              hay_alguien_libre
        #          ])

        # Preference: persona de libres trabaja cuando otros están libres -> REMOVED/Relaxed
        # Same reason: avoid pressure to work 7 days.
        # for e_libres in self.flexibles:
        #      if e_libres not in self.night_replacements: continue
        #      for d in DAYS:
        #          trabaja = model.NewBoolVar(f"{e_libres}_trabaja_{d}")
        #          # Must not be OFF and not be VAC
        #          model.Add(x[(e_libres, d, "OFF")] + x[(e_libres, d, "VAC")] == 0).OnlyEnforceIf(trabaja)
        #          model.Add(x[(e_libres, d, "OFF")] + x[(e_libres, d, "VAC")] >= 1).OnlyEnforceIf(trabaja.Not())

        # NOTE: Old soft OFF-day limits REMOVED. Replaced by HARD constraints
        # in the "STRICT OFF-DAY DISTRIBUTION" section above (collision_vars).
        # The hard constraints guarantee:
        #   - Max 2 flex OFFs on any day
        #   - Exactly 1 collision day (2 flex OFFs) on weekdays
        #   - Sunday up to 2 flex OFFs

        # Set Q shift penalty dynamically
        # PRIORIDAD: Refuerzo > Q > Coverage Gap
        # Cuando use_refuerzo=True, el refuerzo se usa primero. Q es fallback.
        Q_COVERAGE_REWARD = 80_000  # < CONSISTENCY_PENALTY, Q as last resort
        if standard_mode:
            if allow_collision_q:
                # Q penalty REDUCIDO para hacerlo más atractivo que coverage gap
                # El refuerzo tiene prioridad (penalty 3000), Q es fallback
                # 100k vs 200k anterior - más incentivos para usar Q cuando Refuerzo no alcanza
                q1_penalty = 100000
                q2_penalty = 100000
            else:
                # PROHIBITIVE: solver must NEVER choose Q shifts with 10+ employees.
                q1_penalty = 999999
                q2_penalty = 999999
            # In standard mode, boost PM shift rewards to give solver clear alternatives:
            t8_reward = 0        # T8_13-20: sin preferencia — el solver lo elige solo si cubre la cobertura
            t12_reward = -1200   # T12_14-22 (8h) covers h14-h21 — strong PM coverage
            t9_reward = -800     # T9_14-21 (7h) covers h14-h20
        else:
            # Short-staffed: Q shifts are COVERAGE-DRIVEN, never rewarded.
            # The old unconditional reward (-800k/-600k per Q day) made the
            # solver stack broken shifts even when peaks were already at the
            # ideal (4), producing 5-person bands built on quebrados. With a
            # moderate positive cost, a Q enters ONLY when the coverage-gap
            # penalty it closes (1M/h PM, 5M/h AM) outweighs it — i.e. only
            # when no regular shift combination reaches the preset ideal.
            q1_penalty = 200000
            q2_penalty = 250000
            t8_reward = 0
            t12_reward = -400
            t9_reward = -300
        
        # HARD CONSTRAINT: When standard_mode, physically forbid Q shifts, bridge/short shifts, and T11/T3
        # A soft penalty alone cannot guarantee elimination because coverage
        # soft penalties (500k per hour gap) can outweigh Q penalty.
        # With 10+ employees, standard 8h shifts MUST cover all peaks.
        # T11_12-20 (12md-8pm) is replaced by T8_13-20 (1pm-8pm) in standard_mode.
        # T3_07-15 is eliminated: T1+T2+Jeison cover h7 peak. More people same entry hours.
        # Bridge/short shifts (R1 4h, R2 4h, T13 6h) not needed with full staff.
        if standard_mode:
            for e in self.employees:
                # Skip forced_quebrado_total employees — they NEED Q shifts all week
                if self.emp_data[e].get('forced_quebrado', False):
                    continue
                # Skip forced_quebrado_partial employees — they need Q access on coverage-gap days
                if self.emp_data[e].get('forced_quebrado_partial', False):
                    continue
                # Skip Refuerzo — they legitimately take 4h shifts
                if self.emp_data[e].get('is_refuerzo', False):
                    continue
                for d in DAYS:
                    if is_special_closed(d):
                        for s in SHIFT_NAMES:
                            if s not in ["OFF", "VAC", "PERM"]:
                                model.Add(x[(e, d, s)] == 0)
                    elif is_special_sunday_like(d):
                        # Solo permitir explícitamente los turnos que ensamblan la cobertura perfecta:
                        # 2 AM (T1), 1 Intermedio (T3), 3 PM (T8, D4, T10), 1 Noche (N).
                        allowed_sunday_shifts = [
                            "OFF", "VAC", "PERM",
                            "T1_05-13",   # 5am-1pm
                            "T3_07-15",   # 7am-3pm
                            "T8_13-20",   # 1pm-8pm 
                            "D4_13-22",   # 1pm-10pm
                            "T10_15-22",  # 3pm-10pm
                            "N_22-05"     # 10pm-5am
                        ]
                        for s in SHIFT_NAMES:
                            if s not in allowed_sunday_shifts:
                                model.Add(x[(e, d, s)] == 0)
                    else:
                        # =========================================================
                        # REGLAS DE ENTRE SEMANA (Lun-Sáb)
                        # =========================================================
                        if not allow_collision_q and standard_mode:
                            # Hard block Q shifts in standard mode without collision toggle
                            # In short-staffed mode, Q shifts are controlled by penalties/rewards
                            model.Add(x[(e, d, "Q1_05-11+17-20")] == 0)
                            model.Add(x[(e, d, "Q2_07-11+17-20")] == 0)
                            model.Add(x[(e, d, "Q3_05-11+17-22")] == 0)
                        
                        model.Add(x[(e, d, "T11_12-20")] == 0)  # Eliminar 12md-8pm
                        # T3_07-15 ALLOWED entre semana
                        model.Add(x[(e, d, "R1_07-11")] == 0)   # Eliminar 4h puente AM
                        model.Add(x[(e, d, "R2_16-20")] == 0)   # Eliminar 4h puente PM
                        model.Add(x[(e, d, "T13_16-22")] == 0)  # Eliminar 6h puente
                        model.Add(x[(e, d, "D3_15-23")] == 0)   # Eliminar 3pm-11pm
        
        # =========================
        # OBJETIVO (Penalties)
        # =========================

        # Precomputar es_dia_descanso_libres[e][d] una sola vez
        es_dia_descanso_libres_cache = {}
        for e_cache in self.employees:
            es_dia_descanso_libres_cache[e_cache] = {}
            for d_cache in DAYS:
                var = model.NewBoolVar(f"dia_descanso_libres_{e_cache}_{d_cache}")
                lista_cond = []
                for flex in self.flexibles:
                    if flex not in persona_hace_libres:
                        continue
                    cond = model.NewBoolVar(f"cond_cache_{flex}_{d_cache}")
                    model.AddBoolAnd([persona_hace_libres[flex], x[(flex, d_cache, "OFF")]]).OnlyEnforceIf(cond)
                    model.AddBoolOr([persona_hace_libres[flex].Not(), x[(flex, d_cache, "OFF")].Not()]).OnlyEnforceIf(cond.Not())
                    lista_cond.append(cond)
                if lista_cond:
                    model.Add(sum(lista_cond) >= 1).OnlyEnforceIf(var)
                    model.Add(sum(lista_cond) == 0).OnlyEnforceIf(var.Not())
                else:
                    model.Add(var == 0)
                es_dia_descanso_libres_cache[e_cache][d_cache] = var
        
        # O1. Consistencia
        for e in self.employees:
            if e not in turno_principal: continue

            fq_partial = self.emp_data[e].get('forced_quebrado_partial', False)

            for d in DAYS:
                if _has_working_fixed_shift(self.emp_data[e], d):
                    continue
                # Sunday-like days use special shifts (D1, D2, D3, D4) that
                # differ from weekday turno_principal.  Apply a much lighter
                # penalty so the solver can freely pick the best Sunday shift
                # for coverage without fighting the 900k consistency wall.
                is_sunday_day = is_special_sunday_like(d)

                for s in turno_principal[e]:
                    usa_otro = model.NewBoolVar(f"usa_otro_{e}_{d}_{s}")
                    model.AddBoolAnd([x[(e, d, s)], turno_principal[e][s].Not()]).OnlyEnforceIf(usa_otro)
                    model.AddBoolOr([x[(e, d, s)].Not(), turno_principal[e][s]]).OnlyEnforceIf(usa_otro.Not())

                    penalizacion = model.NewIntVar(0, 1000000, f"pen_{e}_{d}_{s}")

                    exento = model.NewBoolVar(f"exento_{e}_{d}")

                    conditions_exento = [es_dia_descanso_libres_cache[e][d]]

                    if e in persona_hace_libres:
                        conditions_exento.append(persona_hace_libres[e])



                    if primary_night and e == primary_night:
                        model.Add(exento == 1)
                    else:
                        model.AddBoolOr(conditions_exento).OnlyEnforceIf(exento)
                        model.AddBoolAnd([c.Not() for c in conditions_exento]).OnlyEnforceIf(exento.Not())

                    if is_sunday_day:
                        # Reduced penalty on Sunday — still prefer consistency but
                        # allow D-shifts (D4_13-22, D2_14-22, etc.) for coverage
                        model.Add(penalizacion == 50000).OnlyEnforceIf([usa_otro, exento.Not()])
                    else:
                        # Massively increased penalty to force extreme schedule consistency per user request
                        model.Add(penalizacion == 900000).OnlyEnforceIf([usa_otro, exento.Not()])
                    model.Add(penalizacion == 0).OnlyEnforceIf(exento)
                    model.Add(penalizacion == 0).OnlyEnforceIf(usa_otro.Not())

                    major_penalties.append(penalizacion)  # IntVar 0..900k (weight embedded)
                    
        # O3. Broken shifts Q1/Q2/Q3 — penalty depends on mode and employee config.
        # forced_quebrado_total: no penalty for preferred Q type; normal penalty for others.
        # forced_quebrado_partial: COVERAGE-DRIVEN in BOTH modes. A moderate penalty
        #   means the solver inserts the partial-Q only when the below-ideal coverage
        #   gap penalty (5M AM / 500k PM per hour) outweighs it — i.e. only on the days
        #   it is actually needed to hold the IDEAL (4 at peak), never every day.
        FQ_PARTIAL_Q_PENALTY = 200_000
        # When at least one employee is designated quebrado_partial, that person is
        # the coverage-Q carrier.  In short-staffed mode every OTHER employee normally
        # earns the -800k Q reward, which would let a non-designated person steal the
        # carrier role and flood Q (defeating the purpose of the flag).  So while a
        # partial carrier exists, every non-designated employee gets a positive
        # fallback cost instead: above the PM gap (1M, policy B) so they don't chase
        # PM coverage via Q, below the AM gap (5M) so they can still close an AM
        # emergency when the carrier is OFF.  Refuerzos are NOT exempted here — a
        # refuerzo left on the -800k reward would outbid the partial carrier and take
        # the Q itself.
        NONPARTIAL_Q_FALLBACK_PENALTY = 1_300_000
        has_partial_q = any(
            self.emp_data[e].get('forced_quebrado_partial', False)
            for e in self.employees
        )
        ALL_Q_SHIFTS_PEN = ["Q1_05-11+17-20", "Q2_07-11+17-20", "Q3_05-11+17-22"]
        for e in self.employees:
            fq_total = self.emp_data[e].get('forced_quebrado', False)
            fq_partial = self.emp_data[e].get('forced_quebrado_partial', False)
            qpref = self.emp_data[e].get('quebrado_preferido', 'auto')
            steer_to_partial = has_partial_q and not standard_mode
            for d in DAYS:
                if fq_total:
                    if qpref == 'auto':
                        # Auto: sin penalización (comportamiento original)
                        pass
                    else:
                        # Preferencia específica: penalizar solo los Q NO elegidos
                        for qs in ALL_Q_SHIFTS_PEN:
                            if qs == qpref:
                                pass  # sin penalty — es el tipo elegido
                            else:
                                p = q1_penalty if qs in ("Q1_05-11+17-20", "Q3_05-11+17-22") else q2_penalty
                                route_penalty(p, x[(e, d, qs)])
                elif fq_partial:
                    # Coverage-driven in BOTH modes (see note above). The old
                    # short-staffed path used q1_penalty (-800k reward), which made
                    # the partial employee take Q on nearly every working day —
                    # indistinguishable from forced_quebrado_total.
                    p = FQ_PARTIAL_Q_PENALTY
                    route_penalty(p, x[(e, d, "Q1_05-11+17-20")])
                    route_penalty(p, x[(e, d, "Q2_07-11+17-20")])
                    route_penalty(p, x[(e, d, "Q3_05-11+17-22")])
                elif steer_to_partial:
                    # A partial carrier is designated: keep Q off non-designated
                    # employees unless a real AM gap (5M) forces it.
                    route_penalty(NONPARTIAL_Q_FALLBACK_PENALTY, x[(e, d, "Q1_05-11+17-20")])
                    route_penalty(NONPARTIAL_Q_FALLBACK_PENALTY, x[(e, d, "Q2_07-11+17-20")])
                    route_penalty(NONPARTIAL_Q_FALLBACK_PENALTY, x[(e, d, "Q3_05-11+17-22")])
                else:
                    route_penalty(q1_penalty, x[(e, d, "Q1_05-11+17-20")])
                    route_penalty(q2_penalty, x[(e, d, "Q2_07-11+17-20")])
                    route_penalty(q1_penalty, x[(e, d, "Q3_05-11+17-22")])

        # O4. Turnos Cortos T13
        for e in self.employees:
             for d in DAYS:
                 penalties.append(200 * x[(e, d, "T13_16-22")])
                 
                 # Fuerte incentivo para usar el D4_13-22 el domingo (pedido del usuario)
                 if d == "Dom" and is_sunday_style_mode(day_modes.get("Dom", SPECIAL_DAY_MODE_NORMAL)):
                     # Hard limit: D4_13-22 can only be assigned to a maximum of 1 person on Sundays
                     model.Add(sum(x[(e_iter, "Dom", "D4_13-22")] for e_iter in self.employees) <= 1)
                     penalties.append(-10000 * x[(e, d, "D4_13-22")])

        # O5. Preference for Refuerzo to take 4-hour shifts over 8-hour shifts
        # Skip in partial mode — refuerzo behaves as regular employee with fixed_shifts.
        if self.refuerzo_name in self.employees and not self.config.get('refuerzo_partial_mode', False):
            # Collect refuerzo shift codes (dict or single string)
            refuerzo_shifts = set()
            if isinstance(current_refuerzo_custom_shift, dict):
                refuerzo_shifts = set(current_refuerzo_custom_shift.values())
            elif isinstance(current_refuerzo_custom_shift, str):
                refuerzo_shifts.add(current_refuerzo_custom_shift)
            refuerzo_shifts.update(["OFF", "VAC", "PERM", "R1_07-11", "R2_16-20", default_diurno_refuerzo_shift])
            for d in DAYS:
                for s in SHIFT_NAMES:
                    if s not in refuerzo_shifts:
                        penalties.append(3000 * x[(self.refuerzo_name, d, s)])

        # O7. T8_13-20 (1pm-8pm): sin preferencia activa.
        # HARD CAP dinámico: el límite de personas en T8 escala con el tamaño de la plantilla.
        #   <=10 empleados activos → máximo 2 en T8
        #   11-12 empleados activos → máximo 3 en T8
        #   13+ empleados activos  → máximo 4 en T8
        # Esto evita que una plantilla grande se vea artificialmente restringida,
        # pero impide que una plantilla pequeña sacrifique cobertura AM por acumular PM.
        if active_count <= 10:
            t8_max = 2
        elif active_count <= 12:
            t8_max = 3
        else:
            t8_max = 4

        for d_t8 in DAYS:
            if not is_weekday_like_mode(day_modes.get(d_t8)):
                continue
            model.Add(sum(x[(e, d_t8, "T8_13-20")] for e in self.employees) <= t8_max)

        for e in self.employees:
             is_woman = self.emp_data[e].get("gender") == "F"
             for d in DAYS:
                 if not standard_mode:
                     penalties.append(-1500 * x[(e, d, "T11_12-20")])
                 # Recompensar T2_06-14 el sábado para incentivar cobertura AM
                 if d == "Sáb":
                     penalties.append(-2000 * x[(e, d, "T2_06-14")])
                 # Mujeres en sábado/domingo: preferir turnos AM que no empiecen a
                 # las 5am. T3_07-15 o T2_06-14 son mejores que T1_05-13.
                 # El incentivo debe superar la penalización de consistencia (900k)
                 # para que el solver elija T3 en lugar de T1 el fin de semana.
                 if is_woman and d in ("Sáb", "Dom") and is_special_sunday_like(d):
                     route_penalty(950000, x[(e, d, "T1_05-13")])
                     route_penalty(-200000, x[(e, d, "T3_07-15")])
                     route_penalty(-150000, x[(e, d, "T2_06-14")])
        
        # O8. HEAVY EXTENDED SHIFTS - HARD BLOCKING
        # Heavy shifts (E1, E2, J_ 10h+) are FORBIDDEN. Q3 is the correct
        # solution for short-staffed days. When use_refuerzo=True, Refuerzo
        # handles the gap. When use_refuerzo=False, Q3 handles it.
        # If the solver can't find a solution without heavy shifts -> Infeasible.
        
        # HARD BLOCK: No heavy extended shifts for anyone, ever.
        for e in self.employees:
            e_fixed = self.emp_data[e].get('fixed_shifts', {}) or {}
            for d in DAYS:
                for s in HEAVY_EXTENDED_SHIFTS:
                    if s == "T4_08-16" and day_modes.get(d) == SPECIAL_DAY_MODE_HOLY_THURSDAY:
                        continue
                    # Respect an EXPLICIT manual assignment of a heavy shift (e.g. the
                    # jefe de pista's 10h base shift J_07-17/J_08-18/J_09-19/J_10-20).
                    # This block only stops the SOLVER from auto-choosing heavy shifts;
                    # it must NOT override a shift the user fixed on purpose (that
                    # collision is what made the jefe's schedule impossible / infeasible).
                    if e_fixed.get(d) == s:
                        continue
                    model.Add(x[(e, d, s)] == 0)

        for d in DAYS:
            if day_modes.get(d) != SPECIAL_DAY_MODE_HOLY_THURSDAY:
                continue
            holy_t4_total = sum(x[(e, d, "T4_08-16")] for e in self.employees)
            model.Add(holy_t4_total <= 1)
            route_penalty(-180000, holy_t4_total)
            for e in self.employees:
                route_penalty(180000, x[(e, d, "T16_05-14")])
                route_penalty(180000, x[(e, d, "D2_14-22")])

        for d in DAYS:
            # Reuse collision_vars for short-staffed detection on weekdays.
            # On Sunday, we detect short-staffing independently.
            if is_special_closed(d):
                is_short_staffed = model.NewConstant(0)
            elif is_special_sunday_like(d):
                flex_absent_dom = sum(
                    x[(e, d, "OFF")] + x[(e, d, "VAC")] + x[(e, d, "PERM")]
                    for e in self.employees
                    if e != primary_night
                    and not self.emp_data[e].get('is_jefe_pista', False)
                    and not self.emp_data[e].get('is_refuerzo', False)
                )
                is_short_staffed = model.NewBoolVar(f"short_staffed_{d}")
                model.Add(flex_absent_dom >= 2).OnlyEnforceIf(is_short_staffed)
                model.Add(flex_absent_dom < 2).OnlyEnforceIf(is_short_staffed.Not())
            else:
                # Weekdays: short-staffed == collision day (already HARD constrained to exactly 1)
                is_short_staffed = collision_vars[d]
            
            for e in self.employees:
                # ----------------
                # 9-Hour Bridge (T16) - Moderate Penalty when not short-staffed
                # ----------------
                for s in ["T16_05-14"]:
                    using_shift_normally = model.NewBoolVar(f"norm_{e}_{d}_{s}")
                    model.AddBoolAnd([x[(e, d, s)], is_short_staffed.Not()]).OnlyEnforceIf(using_shift_normally)
                    model.AddBoolOr([x[(e, d, s)].Not(), is_short_staffed]).OnlyEnforceIf(using_shift_normally.Not())
                    penalties.append(10000 * using_shift_normally)
                
                # ----------------
                # Q3 Quebrado Largo - ONLY on short-staffed days OR collision days
                # ----------------
                if is_special_sunday_like(d):
                    model.Add(x[(e, d, "Q3_05-11+17-22")] == 0)
                elif not allow_collision_q:
                    model.Add(x[(e, d, "Q3_05-11+17-22")] == 0).OnlyEnforceIf(is_short_staffed.Not())
                # NO EXTRA PENALTY for Q3 anymore, let it compete via q1_penalty (50)

                # Extra Reward for T3 on short staffed days
                using_t3_short = model.NewBoolVar(f"t3_short_{e}_{d}")
                model.AddBoolAnd([x[(e, d, "T3_07-15")], is_short_staffed]).OnlyEnforceIf(using_t3_short)
                model.AddBoolOr([x[(e, d, "T3_07-15")].Not(), is_short_staffed.Not()]).OnlyEnforceIf(using_t3_short.Not())
                penalties.append(-3000 * using_t3_short)

                if e == "Ileana":
                    using_ileana_short = model.NewBoolVar(f"ileana_req_short_{d}")
                    model.AddBoolAnd([x[(e, d, "T3_07-15")], is_short_staffed]).OnlyEnforceIf(using_ileana_short)
                    model.AddBoolOr([x[(e, d, "T3_07-15")].Not(), is_short_staffed.Not()]).OnlyEnforceIf(using_ileana_short.Not())
                    penalties.append(-50000 * using_ileana_short)

                    # SÁBADO ESTÁNDAR: si hay un empleado sat_dom_only trabajando T1 ese día,
                    # Ileana debe preferir T3_07-15 en vez de T1 (evitar 3x T1 AM).
                    # Esta recompensa aplica en standard_mode independientemente de short_staffed.
                    if d == "Sáb" and standard_mode and day_modes.get(d) == SPECIAL_DAY_MODE_NORMAL:
                        sat_dom_t1_count = sum(
                            1 for emp in self.employees
                            if emp in sat_dom_only
                            and self.emp_data[emp].get('fixed_shifts', {}).get('Sáb') == 'T1_05-13'
                        )
                        if sat_dom_t1_count > 0:
                            penalties.append(-80000 * x[(e, d, "T3_07-15")])

                # Make Jensy explicitly favor T16_05-14 on short staffed days
                if e == "Jensy":
                    using_jensy_short = model.NewBoolVar(f"jensy_req_short_{d}")
                    model.AddBoolAnd([x[(e, d, "T16_05-14")], is_short_staffed]).OnlyEnforceIf(using_jensy_short)
                    model.AddBoolOr([x[(e, d, "T16_05-14")].Not(), is_short_staffed.Not()]).OnlyEnforceIf(using_jensy_short.Not())
                    penalties.append(-50000 * using_jensy_short)

        # O9. User specific requests for shift preferences
        # In standard_mode: T3 is blocked, T2 and T4 become essential alternatives → no penalty
        for e in self.employees:
             for d in DAYS:
                 if is_special_closed(d):
                     continue
                 if not standard_mode and is_weekday_like(d):
                     # Only penalize T4/T2 and reward T3 when short-staffed (T3 available)
                     # T2_06-14: no penalizar sábado — es el turno AM natural ese día
                     if d != "Sáb":
                         penalties.append(2000 * x[(e, d, "T2_06-14")])
                     penalties.append(-1000 * x[(e, d, "T3_07-15")])
                 # Reward T1_05-13 to ensure early morning coverage when needed
                 penalties.append(-2000 * x[(e, d, "T1_05-13")])
                 # Short-staff: D3 (15:00–23:00) solo como último recurso; preferir T17 (16:00–23:00).
                 # Antes D3 tenía recompensa (-1500), lo que lo favorecía indebidamente frente a T17.
                 if not standard_mode:
                     route_penalty(800000, x[(e, d, "D3_15-23")])
                     route_penalty(-350000, x[(e, d, "T17_16-23")])
                 # D2_14-22: recompensa condicional (ver O9c abajo)

        # O9c. Preferencia T10_15-22 sobre D2_14-22 de Lun-Vie
        # =========================
        # En días normales de lunes a viernes se prefiere el turno 15-22 sobre el 14-22.
        # D2_14-22 solo se usa en: días conflictivos (collision), Sábado o Domingo.
        # En esos días especiales D2 sigue siendo recompensado normalmente.
        # Lógica de pesos:
        #   - Lun-Vie día normal  : D2 penalizado (+200 000), T10 recompensado (-120 000)
        #   - Lun-Vie día colisión: D2 recompensado (-1 500),  T10 recompensado (-120 000)
        #   - Sáb / Dom           : D2 recompensado (-1 500),  T10 recompensado (-1 500)
        lun_vie = [d for d in DAYS if is_weekday_like(d) and d != "Sáb"]
        for e in self.employees:
            # Sábado: preferir T10_15-22 sobre D2_14-22.
            # D2 empieza a las 14h vs T10 que empieza a las 15h. En la práctica
            # ambos cubren el mismo bloque útil pero D2 tiene más riesgo de romper
            # la restricción de descanso mínimo entre turnos. T10 es la opción correcta.
            for d_special in [d for d in DAYS if is_special_sunday_like(d) or d == "Sáb"]:
                # T10_15-22: reward mayor (preferido)
                penalties.append(-3000 * x[(e, d_special, "T10_15-22")])
                # D2_14-22: reward menor + penalidad extra en Sáb para desincentivar
                if d_special == "Sáb":
                    penalties.append(5000 * x[(e, d_special, "D2_14-22")])  # disuadir en Sáb
                else:
                    penalties.append(-1500 * x[(e, d_special, "D2_14-22")])  # DOM: neutro

            # Lunes a Viernes: comportamiento condicional según si es día de colisión
            for d in lun_vie:
                # D2_14-22 en día normal (no colisión) → penalizar fuerte
                d2_normal = model.NewBoolVar(f"d2_normal_{e}_{d}")
                model.AddBoolAnd([x[(e, d, "D2_14-22")], collision_vars[d].Not()]).OnlyEnforceIf(d2_normal)
                model.AddBoolOr([x[(e, d, "D2_14-22")].Not(), collision_vars[d]]).OnlyEnforceIf(d2_normal.Not())
                route_penalty(200000, d2_normal)

                # D2_14-22 en día colisión → recompensar normalmente
                d2_collision = model.NewBoolVar(f"d2_collision_{e}_{d}")
                model.AddBoolAnd([x[(e, d, "D2_14-22")], collision_vars[d]]).OnlyEnforceIf(d2_collision)
                model.AddBoolOr([x[(e, d, "D2_14-22")].Not(), collision_vars[d].Not()]).OnlyEnforceIf(d2_collision.Not())
                penalties.append(-1500 * d2_collision)

                # T10_15-22 de Lun-Vie: siempre recompensado (turno preferido)
                penalties.append(-120000 * x[(e, d, "T10_15-22")])

        # O9b. ANTI-DUPLICATION: REMOVED
        # Duplicate shifts (e.g. 2x T1_05-13, 2x T8_13-20) are allowed and part
        # of the ideal distribution pattern.

        # O10. Cobertura Estricta de la Persona de Libres
        # La persona de libres debe heredar el turno exacto de la persona que está OFF.
        # Si la persona de libres también está OFF, cualquier otro empleado puede cubrir
        # (GENDER-NEUTRAL: misma recompensa sin importar género).
        
        night_person = self.config.get("fixed_night_person", None)
        
        for d in DAYS:
            for e in self.employees:
                for s in SHIFT_NAMES:
                    if s in ["OFF", "VAC", "PERM"] or s.startswith("J_") or s.startswith("X_"): continue
                    
                    # Determinar si 'e' requiere cobertura de 's' hoy porque está OFF
                    needs_cover = model.NewBoolVar(f"needs_cover_{e}_{d}_{s}")
                    
                    if e == night_person and s == "N_22-05":
                        model.Add(x[(e, d, "OFF")] == 1).OnlyEnforceIf(needs_cover)
                        model.Add(x[(e, d, "OFF")] == 0).OnlyEnforceIf(needs_cover.Not())
                    elif e in turno_principal and s in turno_principal[e]:
                        model.AddBoolAnd([x[(e, d, "OFF")], turno_principal[e][s]]).OnlyEnforceIf(needs_cover)
                        model.AddBoolOr([x[(e, d, "OFF")].Not(), turno_principal[e][s].Not()]).OnlyEnforceIf(needs_cover.Not())
                    else:
                        continue # No tiene turno fijo definible
                        
                    # Si requiere cobertura, premiar fuertemente a la persona de libres (L) por cubrirlo
                    for L in self.flexibles:
                        if L not in persona_hace_libres or L == e: continue
                        
                        L_covers = model.NewBoolVar(f"L_covers_{L}_{e}_{d}_{s}")
                        model.AddBoolAnd([needs_cover, persona_hace_libres[L], x[(L, d, s)]]).OnlyEnforceIf(L_covers)
                        penalties.append(-3000 * L_covers) # Fuerte recompensa para L
                        
                        # ¿Y si L está OFF?
                        L_is_off_and_needs = model.NewBoolVar(f"L_off_needs_{L}_{e}_{d}_{s}")
                        model.AddBoolAnd([needs_cover, persona_hace_libres[L], x[(L, d, "OFF")]]).OnlyEnforceIf(L_is_off_and_needs)
                        
                        is_diurno = max(SHIFTS[s]) <= 17 if s in SHIFTS and SHIFTS[s] else False
                        
                        for c in self.flexibles:
                            if c == L or c == e: continue
                            c_covers = model.NewBoolVar(f"c_covers_{c}_{L}_{e}_{d}_{s}")
                            model.AddBoolAnd([L_is_off_and_needs, x[(c, d, s)]]).OnlyEnforceIf(c_covers)
                            # GENDER-NEUTRAL: same reward for all employees covering shifts
                            penalties.append(-2000 * c_covers)

        # O11. HISTORIAL / ROTACION
        # =========================
        
        rotation_enabled = self.config.get('rotation_enabled', True)
        # Limitar a ROTATION_HISTORY_WINDOW semanas para rachas y rotación de domingos.
        history_window = history_entries[-ROTATION_HISTORY_WINDOW:] if len(history_entries) > ROTATION_HISTORY_WINDOW else history_entries
        rotation_history_context = build_rotation_history_context(
            self.employees,
            self.emp_data,
            history_window,
            allow_long=allow_long,
            night_person_name=night_person_name,
            alternating_pair_members=alternating_pair_members_set,
            rotation_enabled=rotation_enabled,
        )        # 1. EVITAR REPETICION DE HORARIOS (General)
        # HARD CONSTRAINT: No 3-peat — if employee had shift S on day D for the last 
        # 2 consecutive weeks, BLOCK it this week.
        # SOFT PENALTY: Penalize 1-week and 2-week repeats for variety.
        
        recent_entries = history_window[-ROTATION_HISTORY_WINDOW:] if len(history_window) >= ROTATION_HISTORY_WINDOW else history_window

        def _history_window_for_employee(employee_name, entries):
            if not entries:
                return []
            if employee_name in alternating_pair_members_set:
                return entries[-1:]
            return entries
        
        # Soft constraint (High Penalty): prevent 3 consecutive weeks with same shift on same day
        # If employee did S on Day D in Week-1 AND Week-2, avoid it in Week-3.
        # Cost = 10000 (Very high, but allows solution if coverage is at risk)
        for e in self.employees:
            employee_history = _history_window_for_employee(e, history_entries)
            if len(employee_history) < 2:
                continue

            week_minus_1_entry = employee_history[-1]
            week_minus_2_entry = employee_history[-2]
            week_minus_1 = _normalize_history_schedule(week_minus_1_entry.get("schedule", {}))
            week_minus_2 = _normalize_history_schedule(week_minus_2_entry.get("schedule", {}))
            sched_1 = week_minus_1.get(e, {})
            sched_2 = week_minus_2.get(e, {})
            for d in DAYS:
                if _has_working_fixed_shift(self.emp_data[e], d):
                    continue
                if _history_day_is_neutral(week_minus_1_entry, d) or _history_day_is_neutral(week_minus_2_entry, d):
                    continue
                s1 = sched_1.get(d)
                s2 = sched_2.get(d)
                # If same shift on same day for 2 consecutive weeks → penalized heavily
                if s1 and s2 and s1 == s2 and s1 in SHIFT_NAMES and s1 != "OFF" and s1 != "VAC":
                    # EXEMPTION 1: Fixed shifts (manual override)
                    if self.emp_data[e].get("fixed_shifts", {}).get(d) == s1:
                        continue

                    # EXEMPTION 2: Fixed night person (if current shift touches night)
                    night_mode = self.config.get("night_mode", "rotate")
                    night_person = self.config.get("fixed_night_person")
                    if night_mode == "fixed_person" and e == night_person and touches_night(s1):
                        continue

                    is_repeating_3rd = x[(e, d, s1)]
                    penalties.append(10000 * is_repeating_3rd)

        # ANTI-3PEAT AM/PM: Hard constraint — if employee had same AM/PM token
        # for 3+ consecutive weeks on the same day, force the opposite token.
        # Exemptions: forced_libres, fixed shifts, jefe de pista, fixed night person.
        for e in self.employees:
            # Exempt forced_libres (Steven)
            if self.emp_data[e].get("forced_libres", False):
                continue
            # Exempt fixed night person
            night_person = self.config.get("fixed_night_person")
            if e == night_person:
                continue
            # Exempt jefe de pista
            if self.emp_data[e].get("is_jefe_pista", False):
                continue

            employee_history = _history_window_for_employee(e, history_entries)
            if len(employee_history) < 3:
                continue

            # Check last 3 weeks for same AM/PM token on same day
            week_entries = employee_history[-3:]
            tokens = []
            for entry in week_entries:
                sched = _normalize_history_schedule(entry.get("schedule", {}))
                e_sched = sched.get(e, {})
                day_tokens = {}
                for d in DAYS:
                    if _has_working_fixed_shift(self.emp_data[e], d):
                        continue
                    if _history_day_is_neutral(entry, d):
                        continue
                    shift = e_sched.get(d)
                    if shift:
                        day_tokens[d] = _am_pm_token(shift)
                tokens.append(day_tokens)

            for d in DAYS:
                if _has_working_fixed_shift(self.emp_data[e], d):
                    continue
                # Check if all 3 weeks have the same AM/PM token
                t0 = tokens[0].get(d)
                t1 = tokens[1].get(d)
                t2 = tokens[2].get(d)
                if t0 and t1 and t2 and t0 == t1 == t2 and t0 in ("AM", "PM"):
                    # Hard constraint: block the same token
                    opposite = "PM" if t0 == "AM" else "AM"
                    # Block all shifts of the same token type
                    for s in SHIFT_NAMES:
                        if _am_pm_token(s) == t0 and s not in ("OFF", "VAC", "PERM"):
                            model.Add(x[(e, d, s)] == 0)
        
        # Soft penalty: discourage repeating shifts from recent weeks
        for e in self.employees:
            # Only skip employees whose schedule is mostly fixed (>=5 working
            # fixed days).  Previously ANY fixed shift caused a skip, which meant
            # employees like Alejandro (1 Saturday fixed) lost all history guidance
            # and the solver assigned arbitrary shifts instead of their turno_principal.
            working_fixed_count = len(_working_fixed_shift_days(self.emp_data[e]))
            if working_fixed_count >= 5 and e not in alternating_pair_members_set:
                continue
            employee_recent_entries = _history_window_for_employee(e, recent_entries)
            for i, entry in enumerate(reversed(employee_recent_entries)):
                weight = 500 if i == 0 else 300 if i == 1 else 100

                sched = _normalize_history_schedule(entry.get("schedule", {}))
                e_sched = sched.get(e, {})
                for d in DAYS:
                    if _has_working_fixed_shift(self.emp_data[e], d):
                        continue
                    if _history_day_is_neutral(entry, d):
                        continue
                    past_shift = e_sched.get(d)
                    if past_shift and past_shift in SHIFT_NAMES and past_shift != "OFF":
                        is_repeating = x[(e, d, past_shift)]
                        penalties.append(weight * is_repeating)

        # 1.5 ROTACION SEMANAL DEL TURNO PRINCIPAL
        # =======================================
        # Mujeres: solo se mira la semana anterior y se empuja el turno opuesto AM/PM.
        # Resto del equipo: se mira una ventana de N semanas, donde N es el tamano
        # del pool real de rotacion de esa persona, para evitar repetir el mismo
        # turno principal antes de completar el ciclo.
        #
        # FAIRNESS (revisado): el motor priorizó en exceso la cobertura por sobre la
        # equidad de rotación — varios usuarios reportaron personas trabadas en PM
        # 4–5 semanas seguidas mientras otros se quedaban en AM. Cambios:
        #   - El balance personal AM vs PM ahora penaliza desde |delta| >= 2
        #     (antes >= 3) para corregir antes de que se vuelva crónico.
        #   - El streak escala más temprano: streak=2 ya pesa el doble (antes =1x).
        #   - Se agrega un término global de equidad team-wide: si la persona
        #     concentra mucho más PM (o AM) que el promedio del equipo, se penaliza
        #     fuertemente continuar en ese token.
        #   streak=1 → 1x base
        #   streak=2 → 2x  (era 1x antes del fix)
        #   streak=3 → 4x
        #   streak=4 → 8x
        rotation_penalty_weights = [180000, 120000, 80000, 50000, 30000, 18000]

        # Calcular promedio del equipo para equidad team-wide.
        team_am_total = 0
        team_pm_total = 0
        for _ctx in rotation_history_context.values():
            team_am_total += int(_ctx.get("am_count", 0) or 0)
            team_pm_total += int(_ctx.get("pm_count", 0) or 0)
        team_total = team_am_total + team_pm_total
        team_pm_ratio = (team_pm_total / team_total) if team_total > 0 else 0.5

        for e, ctx in rotation_history_context.items():
            if e not in turno_principal or not turno_principal[e]:
                continue
            # Only skip if schedule is mostly fixed (>=5 working fixed days).
            # Employees with 1-4 fixed shifts still need rotation guidance so
            # their turno_principal follows history (e.g. Alejandro with 1 Sat fixed).
            working_fixed_count = len(_working_fixed_shift_days(self.emp_data[e]))
            if working_fixed_count >= 5 and self.emp_data[e].get("gender") != "F":
                continue
            recent_tokens = ctx.get("recent_tokens", [])
            if not recent_tokens:
                continue
            is_alternating = e in alternating_pair_members_set
            # Determine if this employee uses AM/PM token rotation:
            # - Alternating pair members always use AM/PM
            # - All others when rotation_enabled is True and last token is AM/PM
            last_token = recent_tokens[-1] if recent_tokens else None
            uses_ampm = is_alternating or (rotation_enabled and last_token in ("AM", "PM"))

            if uses_ampm and last_token in ("AM", "PM"):
                opposite_token = "PM" if last_token == "AM" else "AM"
                streak = ctx.get("streak", 1)

                # Si los turnos fijos (manuales) ya determinan el token AM/PM del empleado,
                # omitir TODA la lógica de racha — la asignación manual tiene prioridad
                # absoluta y no debe ser interferida por la rotación histórica.
                # IMPORTANTE: antes solo se salteaba cuando fixed_token == last_token,
                # lo que dejaba activa la penalización cuando el fixed shift pedía el
                # turno opuesto al historial (bug: rotación vs preferencia fija).
                fixed_token = _fixed_dominant_token(self.emp_data[e])
                if fixed_token is not None:
                    # El empleado tiene turnos ESTRICTOS que definen su familia AM/PM.
                    # Reforzamos la familia correcta con una recompensa adicional
                    # para asegurar que turno_principal siga la preferencia fija.
                    FIXED_FAMILY_BOOST = 500_000
                    for s, var in turno_principal[e].items():
                        token = _am_pm_token(s)
                        if token == fixed_token:
                            route_penalty(-FIXED_FAMILY_BOOST, var)  # recompensa
                        elif token is not None and token != fixed_token:
                            route_penalty(FIXED_FAMILY_BOOST, var)   # penaliza familia opuesta
                    continue

                # SOFT PREFERENCES OVERRIDE: si el empleado tiene preferencias de turno
                # configuradas manualmente en el panel (no estrictas), esas preferencias
                # definen su familia AM/PM para esta semana y deben ganar al historial.
                # Caso exacto de Keilor: T3_07-15 configurado → no dejar que el historial
                # PM lo arrastre a tarde. SOFT_PREF_BOOST (3M) > penalty_same típica (600K-1.2M).
                soft_pref_token = None
                emp_soft_prefs = {}
                for (pref_key, s_code) in soft_preferences.items():
                    if not isinstance(pref_key, tuple) or len(pref_key) != 2:
                        continue  # skip (e, d, alt_s) fallback keys
                    emp_k, d = pref_key
                    if emp_k == e and _am_pm_token(s_code) is not None:
                        emp_soft_prefs[d] = s_code
                if emp_soft_prefs:
                    am_days = sum(1 for s in emp_soft_prefs.values() if _am_pm_token(s) == "AM")
                    pm_days = sum(1 for s in emp_soft_prefs.values() if _am_pm_token(s) == "PM")
                    if am_days > pm_days:
                        soft_pref_token = "AM"
                    elif pm_days > am_days:
                        soft_pref_token = "PM"
                    elif am_days > 0:  # empate: AM gana como desempate (más común)
                        soft_pref_token = "AM"

                if soft_pref_token is not None:
                    # El panel de parámetros define la familia de turno para esta semana.
                    # Damos prioridad a esa elección por encima del historial de rotación.
                    # SOFT_PREF_BOOST debe superar la penalidad de racha más alta posible
                    # (600K * streak_multiplier, cap 5M) en el caso típico (streak ≤ 2 → 1.2M).
                    SOFT_PREF_BOOST = 3_000_000
                    for s, var in turno_principal[e].items():
                        token = _am_pm_token(s)
                        if token == soft_pref_token:
                            route_penalty(-SOFT_PREF_BOOST, var)  # fuerte recompensa
                        elif token is not None and token != soft_pref_token:
                            route_penalty(SOFT_PREF_BOOST, var)   # fuerte penalidad familia opuesta
                    continue

                # Penalty for repeating same token — scales exponentially with streak.
                # Pair members get base 900K; others get base 600K.
                # Bumped earlier: streak=2 ahora = 2x (antes 1x), porque permitía
                # 2 semanas consecutivas sin presión real para rotar.
                base_same = 900000 if is_alternating else 600000
                # streak=1→1, streak=2→2, streak=3→4, streak=4→8 (cap)
                streak_multiplier = min(8, max(1, 2 ** max(0, streak - 1)))
                if streak >= 2:
                    # Boost extra desde el segundo repetido para evitar mesetas largas.
                    streak_multiplier = max(streak_multiplier, 2)
                penalty_same = min(5_000_000, base_same * streak_multiplier)

                # Reward for switching to opposite token — scales with streak too
                base_opp = 180000 if is_alternating else 120000
                reward_opp = -min(1_500_000, base_opp * streak_multiplier)

                for s, var in turno_principal[e].items():
                    token = _am_pm_token(s)
                    if token == last_token:
                        route_penalty(penalty_same, var)
                    elif token == opposite_token:
                        route_penalty(reward_opp, var)

                # BALANCE CHECK: penalización extra desde |balance| >= 2 (antes 3).
                # Activarla antes evita que un desbalance de 3 (PM-heavy crónico)
                # se vuelva el "estado normal" del solver.
                am_count = ctx.get("am_count", 0)
                pm_count = ctx.get("pm_count", 0)
                balance = pm_count - am_count  # positive = PM-heavy, negative = AM-heavy
                if abs(balance) >= 2:
                    # balance=2 → +800K, balance=3 → +1.6M, balance=4 → +2.4M, ≥5 → +5M cap
                    imbalance_penalty = min(5_000_000, 800_000 * max(1, abs(balance) - 1))
                    dominant_token = "PM" if balance > 0 else "AM"
                    for s, var in turno_principal[e].items():
                        token = _am_pm_token(s)
                        if token == dominant_token:
                            route_penalty(imbalance_penalty, var)

                # TEAM-WIDE EQUITY: penalizar a quien concentra mucho más PM (o AM)
                # que el promedio del equipo. Evita que el solver "elija siempre
                # al mismo" para tarde porque tiene disponibilidad: ahora también
                # mira qué tan desbalanceado está respecto al resto.
                personal_total = am_count + pm_count
                if team_total >= 4 and personal_total >= 2:
                    personal_pm_ratio = pm_count / personal_total
                    pm_excess = personal_pm_ratio - team_pm_ratio  # >0 si la persona hace más PM que la media
                    am_excess = -pm_excess
                    # Umbral: 25 puntos porcentuales de desviación.
                    if pm_excess > 0.25:
                        equity_pen = min(5_000_000, int(2_500_000 * (pm_excess - 0.25) + 400_000))
                        for s, var in turno_principal[e].items():
                            if _am_pm_token(s) == "PM":
                                route_penalty(equity_pen, var)
                    elif am_excess > 0.25:
                        equity_pen = min(5_000_000, int(2_500_000 * (am_excess - 0.25) + 400_000))
                        for s, var in turno_principal[e].items():
                            if _am_pm_token(s) == "AM":
                                route_penalty(equity_pen, var)
                continue
            lookback_weeks = min(max(ctx.get("cycle_weeks", 1) - 1, 0), len(recent_tokens))
            if lookback_weeks <= 0:
                continue
            recent_slice = recent_tokens[-lookback_weeks:]
            for idx, token in enumerate(reversed(recent_slice)):
                if idx < len(rotation_penalty_weights):
                    weight = rotation_penalty_weights[idx]
                else:
                    tail_idx = idx - len(rotation_penalty_weights) + 1
                    weight = max(8000, rotation_penalty_weights[-1] - (tail_idx * 2000))
                for s, var in turno_principal[e].items():
                    if _rotation_token_for_shift(s, self.emp_data[e]) == token:
                        route_penalty(weight, var)
        # 2. SUNDAY ROTATION (History-based queue)
        # Build rotation queue by analyzing history: who had Sunday OFF least recently goes first
        # NOTE: Night person IS eligible for Sunday rotation — the persona_hace_libres
        # covers the N_22-05 replacement when primary night is OFF on Sunday.
        # Exclude sat_dom_only employees from Sunday rotation — they always work Sunday.
        rotation_queue = []
        rotation_target = None
        sunday_absence_vars = {}
        if is_sunday_style_mode(day_modes.get("Dom", SPECIAL_DAY_MODE_NORMAL)):
            eligible = [e for e in sorted(self.employees)
                        if not self.emp_data[e].get('is_jefe_pista', False)
                        and e not in sat_dom_only
                        and not self.emp_data[e].get('forced_quebrado', False)
                        and not self.emp_data[e].get('forced_quebrado_partial', False)
                        and not self.emp_data[e].get('forced_libres', False)
                        and (self.emp_data[e].get('fixed_shifts', {}) or {}).get('Dom') not in ('OFF', 'VAC', 'PERM')]
            
            # Scan history to find each employee's last Sunday OFF (index = recency).
            # Cap at ROTATION_HISTORY_WINDOW semanas para consistencia con el sistema de rachas.
            # NOTA: escaneamos TODOS los empleados (no solo eligible) para preservar el último
            # domingo libre incluso de quienes hoy están excluidos por tener OFF fijo. Así,
            # cuando se les quite el OFF fijo, vuelven a la cola en la posición correcta
            # (al final) y no se "ensucia" la rotación.
            last_sunday_off = {}  # employee -> history_index (higher = more recent)
            sunday_scan_entries = history_window  # ya limitado a 6 semanas
            
            # We need to look at historical schedules to figure out who had Sunday OFF
            for idx, entry in enumerate(sunday_scan_entries):
                if _history_day_is_neutral(entry, "Dom"):
                    continue
                sched = entry.get('schedule', {})
                for emp_name, days in sched.items():
                    if isinstance(days, dict) and days.get('Dom') in ['OFF', 'VAC', 'PERM']:
                        last_sunday_off[emp_name] = idx  # overwrite = keep most recent
            
            # Build queue: sort by last_sunday_off ascending (least recent first)
            # Employees who NEVER had Sunday OFF go to the END (large number), not the front
            # This ensures people WITH history but long wait go first
            max_idx = len(sunday_scan_entries) if sunday_scan_entries else 0
            rotation_queue = sorted(eligible, key=lambda e: last_sunday_off.get(e, max_idx + 1))
            
            rotation_target = rotation_queue[0] if rotation_queue else None
            for e in rotation_queue:
                sunday_absent = model.NewBoolVar(f"sunday_absent_{e}")
                sunday_absence_terms = x[(e, "Dom", "OFF")] + x[(e, "Dom", "VAC")] + x[(e, "Dom", "PERM")]
                model.Add(sunday_absence_terms == 1).OnlyEnforceIf(sunday_absent)
                model.Add(sunday_absence_terms == 0).OnlyEnforceIf(sunday_absent.Not())
                sunday_absence_vars[e] = sunday_absent

            if sunday_absence_vars:
                sunday_absence_total = model.NewIntVar(0, len(sunday_absence_vars), "sunday_absence_total")
                model.Add(sunday_absence_total == sum(sunday_absence_vars.values()))
                # Prefer Sunday OFFs, but let weekday congestion and shift homogeneity
                # win when pushing another Sunday absence would compress the week too much.
                penalties.append(-SUNDAY_ABSENCE_REWARD * sunday_absence_total)

                for idx, e in enumerate(rotation_queue):
                    reward = SUNDAY_QUEUE_REWARDS[idx] if idx < len(SUNDAY_QUEUE_REWARDS) else SUNDAY_QUEUE_REWARDS[-1]
                    route_penalty(-reward, sunday_absence_vars[e])

                for d, congested in weekday_congestion.items():
                    for e, sunday_absent in sunday_absence_vars.items():
                        sunday_absent_with_weekday_congestion = model.NewBoolVar(
                            f"sunday_absent_with_weekday_congestion_{e}_{d}"
                        )
                        model.AddBoolAnd([sunday_absent, congested]).OnlyEnforceIf(
                            sunday_absent_with_weekday_congestion
                        )
                        model.AddBoolOr([sunday_absent.Not(), congested.Not()]).OnlyEnforceIf(
                            sunday_absent_with_weekday_congestion.Not()
                        )
                        penalties.append(
                            SUNDAY_CONGESTED_WEEKDAY_PENALTY * sunday_absent_with_weekday_congestion
                        )

            if rotation_target and rotation_target in sunday_absence_vars:
                # FIX 2026-06-03: Penalización masiva (500M) para que el primero en
                # la cola de rotación tenga domingo libre de forma automática.
                # Excluimos de la cola a quienes ya tienen OFF/VAC/PERM fijo en
                # domingo, así que rotation_target SIEMPRE es quien debe tener libre.
                # Si hay empate en antigüedad (varias personas con el mismo último
                # domingo libre), la optimización del solver evalúa cuál opción
                # genera el mejor horario.
                route_penalty(500_000_000, sunday_absence_vars[rotation_target].Not())

            # Second in queue: strongly prefer Sunday OFF for the next person
            if len(rotation_queue) >= 2:
                second_target = rotation_queue[1]
                if second_target in sunday_absence_vars:
                    route_penalty(20_000_000, sunday_absence_vars[second_target].Not())

            # O6. Sunday Rotation (Historial Compatibility)
            # Verify if they worked last Sunday.
            # We need the MOST RECENT schedule for this.
            if most_recent_schedule and not _history_day_is_neutral(most_recent_entry, "Dom"):
                for e in self.employees:
                    last_sched = most_recent_schedule.get(e, {})
                    last_sunday = last_sched.get("Dom", "OFF") # Default to OFF if missing
                    
                    if last_sunday not in ["OFF", "VAC", "PERM"] and e in sunday_absence_vars:
                        # If they worked last Sunday, gently prefer giving them this Sunday off.
                        penalties.append(150 * sunday_absence_vars[e].Not())

        # ===== CUSTOM SHIFTS PRIORITIES =====
        # Apply priority-based incentives/penalties to custom shifts
        # This runs AFTER all hard constraints and affects soft constraint optimization
        for e in self.employees:
            for d in DAYS:
                for shift_code, priority in CUSTOM_SHIFTS_PRIORITIES.items():
                    if shift_code in SHIFTS and shift_code in x:
                        # Priority affects the solver's preference:
                        # - priority > 50: incentive to use this shift (negative penalty = reward)
                        # - priority < 50: penalty to avoid this shift
                        # - priority = 50: neutral (default behavior)
                        
                        if priority > 50:
                            # High priority: strongly prefer this shift
                            # Reward value scales with priority (e.g., 100 → -50000)
                            reward = -(priority - 50) * 1000  # -5000 for priority 55, -50000 for priority 100
                            penalties.append(reward * x[(e, d, shift_code)])
                        elif priority < 50:
                            # Low priority: avoid this shift unless necessary
                            # Penalty value scales with how low (e.g., 10 → +40000)
                            penalty = (50 - priority) * 1000  # +40000 for priority 10
                            penalties.append(penalty * x[(e, d, shift_code)])
                        # priority == 50: no change (neutral)

        # =========================
        # SOFT: Priorizar cobertura con Jefe de Pista (tie-breaker)
        # Recompensa leve por asignar turnos de trabajo al jefe cuando el solver elige;
        # no sustituye reglas duras ni preferencias fuertes (órdenes de magnitud menores).
        # =========================
        if self.config.get("prioritize_jefe_coverage", True):
            jefe_candidates = [
                e for e in self.employees
                if self.emp_data[e].get("is_jefe_pista")
                and not self.emp_data[e].get("is_refuerzo", False)
            ]
            if len(jefe_candidates) == 1:
                jefe_nm = jefe_candidates[0]
                jefe_reward = 40
                for d in DAYS:
                    if day_modes.get(d) == SPECIAL_DAY_MODE_CLOSED:
                        continue
                    for s in SHIFT_NAMES:
                        if s in ("OFF", "VAC", "PERM"):
                            continue
                        if (jefe_nm, d, s) in x:
                            penalties.append(-jefe_reward * x[(jefe_nm, d, s)])

        # --- Quality tie-breakers (level 4: micro-preferences) ---
        # Weights: 100-1000, two orders of magnitude below consistency penalty

        # 1. Weekly hour balance between employees
        HOUR_BALANCE_PENALTY = 500
        # Target: typical working days per week * typical shift hours
        # (5 working days × 8h = 40h; used as a stable anchor for the penalty)
        avg_weekly_hours_val = 40
        if self.employees:
            for e in self.employees:
                emp_hours = sum(
                    len(SHIFTS.get(s, set())) * x[(e, d, s)]
                    for d in DAYS
                    for s in SHIFT_NAMES
                    if (e, d, s) in x and SHIFT_IS_WORKING.get(s, False)
                )
                excess_hours = model.NewIntVar(0, 60, f"excess_hours_{e}")
                model.AddMaxEquality(excess_hours, [emp_hours - avg_weekly_hours_val, 0])
                penalties.append(HOUR_BALANCE_PENALTY * excess_hours)

        # 2. Preference for early-shift coverage (apertura AM)
        EARLY_COVERAGE_REWARD = 200
        for e in self.employees:
            for d in DAYS:
                for s in SHIFT_NAMES:
                    if s.startswith("T1_05") or s.startswith("T16_05"):
                        if (e, d, s) in x:
                            penalties.append(-EARLY_COVERAGE_REWARD * x[(e, d, s)])

        # NOTE: Clean handoff tie-breaker (level 4 #3) omitted — loop complexity
        # is O(DAYS * hours * employees^2 * shifts^2) ≈ 26M iterations with 15 emp
        # and 30 shifts, which would bloat the model unacceptably.

        # Optimization
        # Lexicographic mode (default): solve tier by tier, freezing each
        # tier's optimum before optimizing the next. Legacy mode (config
        # 'lexicographic': False): single weighted-sum objective as before.
        lex_mode = bool(self.config.get('lexicographic', True))
        lex_tiers = [
            ("critical", crit_penalties),
            ("major", major_penalties),
            ("minor", penalties + peak_penalties),
        ]
        if not lex_mode:
            model.Minimize(
                sum(crit_penalties) + sum(major_penalties)
                + sum(penalties) + sum(peak_penalties)
            )

        solver = cp_model.CpSolver()
        # Allows an external caller to specify a custom max time for the solver.
        # FIX: The model complexity is too high to prove optimality. Force early termination.
        # 'max_time' (interno, ej. trials de diagnóstico) tiene prioridad; si no viene,
        # se usa el 'solver_max_time' configurable desde Parámetros del Motor (60-900s).
        max_t = self.config.get('max_time')
        if max_t is None:
            try:
                max_t = int(self.config.get('solver_max_time') or 180)
            except (TypeError, ValueError):
                max_t = 180
            max_t = min(max(max_t, 30), 900)
        solver.parameters.max_time_in_seconds = max_t
        solver.parameters.relative_gap_limit = 0.005
        solver.parameters.absolute_gap_limit = 50_000
        # Use more threads for speed.
        solver.parameters.log_search_progress = bool(self.config.get("log_search_progress", True))
        # Reproducibilidad: con muchos workers + PORTFOLIO vimos INFEASIBLE esporádico en el mismo modelo.
        solver.parameters.random_seed = int(self.config.get("cp_sat_random_seed", 1))
        
        # --- CAMBIO 3: Solver Optimizations ---
        # PORTFOLIO_SEARCH and num_search_workers allows CP-SAT to run multiple different 
        # heuristic strategies in parallel, wildly improving the schedule quality found in the 5s window.
        _nw = self.config.get("cp_sat_num_search_workers")
        if _nw is not None:
            solver.parameters.num_search_workers = max(1, int(_nw))
        elif hasattr(os, 'cpu_count') and os.cpu_count():
            solver.parameters.num_search_workers = os.cpu_count()
        else:
            solver.parameters.num_search_workers = 8
            
        # PORTFOLIO_SEARCH + interleave_search: múltiples estrategias en paralelo con
        # diversificación entre workers → mejores soluciones en el mismo tiempo.
        # FIX 2026-06-03: hints conflictivos con fixed_shifts causaban crash
        # (`fixed_search != nullptr`). Se filtran hints conflictivos abajo, así que
        # PORTFOLIO + interleave ya es seguro.
        solver.parameters.search_branching = cp_model.PORTFOLIO_SEARCH
        solver.parameters.interleave_search = True

        # Add History Hints to start search close to previous state.
        # FIX: filtrar hints que entran en conflicto con fixed_shifts del empleado.
        # Cuando un usuario asigna "OFF" manual a un día, el hint de la semana anterior
        # (ej. "T1_05-13") contradice la restricción dura → crash interno de OR-Tools.
        if most_recent_schedule:
            for e in self.employees:
                last_sched = most_recent_schedule.get(e, {})
                fixed_shifts = self.emp_data[e].get('fixed_shifts', {}) or {}
                for d in DAYS:
                    s_prev = last_sched.get(d, "OFF")
                    # Saltar hint si el empleado tiene fixed_shift para este día
                    if d in fixed_shifts:
                        continue
                    if s_prev in SHIFT_NAMES:
                        model.AddHint(x[(e, d, s_prev)], 1)
        
        solution_counter = SolutionCounter()
        # Fallback removed: fix_variables_to_their_hinted_value is too aggressive
        # and causes Infeasible when new constraints conflict with old schedules.
        # Just let the first solve finish.
        lex_report = None
        if lex_mode:
            lex_report = []
            deadline = time.monotonic() + max_t
            active_tiers = [(nm, terms) for nm, terms in lex_tiers if terms]
            status = cp_model.UNKNOWN
            for i, (tier_name, terms) in enumerate(active_tiers):
                remaining = deadline - time.monotonic()
                is_last_pass = (i == len(active_tiers) - 1)
                # First pass does the heavy lifting (feasibility from scratch);
                # later passes start hinted at a known solution and converge
                # fast, so give every non-final pass half the remaining budget.
                solver.parameters.max_time_in_seconds = max(
                    5.0, remaining if is_last_pass else remaining * 0.5
                )
                # The 50k absolute gap is calibrated for the big tiers; the
                # minor tier holds weights < 150k, so it needs a finer gap.
                solver.parameters.absolute_gap_limit = 2_000 if tier_name == "minor" else 50_000
                tier_obj = sum(terms)
                model.Minimize(tier_obj)
                status = solver.Solve(model, solution_counter)
                if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE) and i > 0:
                    # Passes after the first are re-finding a known-feasible
                    # solution (bounded by its own tier values, hinted at it),
                    # so a failure here is a timing fluke: retry once with the
                    # rest of the budget.
                    solver.parameters.max_time_in_seconds = max(
                        10.0, deadline - time.monotonic()
                    )
                    status = solver.Solve(model, solution_counter)
                if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                    break
                tier_best = int(round(solver.ObjectiveValue()))
                lex_report.append({
                    "tier": tier_name,
                    "objective": tier_best,
                    "status": solver.StatusName(status),
                })
                if i < len(active_tiers) - 1:
                    # Freeze this tier: lower tiers may not degrade it.
                    model.Add(tier_obj <= tier_best)
                    _refresh_solution_hints(model, solver, x)
        else:
            status = solver.Solve(model, solution_counter)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
             res = {}
             
             for e in self.employees:
                 res[e] = {}
                 for d in DAYS:
                     for s in SHIFT_NAMES:
                         if solver.Value(x[(e, d, s)]):
                             res[e][d] = s
                             break

             # POST-HOC TASK ASSIGNMENT
             res_tasks = self.assign_tasks(res)

             libres_found = None
             for e in self.flexibles:
                 if e in persona_hace_libres and solver.Value(persona_hace_libres[e]):
                     libres_found = e
             
             sunday_off_person = None
             if is_sunday_style_mode(day_modes.get("Dom", SPECIAL_DAY_MODE_NORMAL)):
                 for e_check in self.employees:
                     if (
                         res[e_check].get("Dom") in ["OFF", "VAC"]
                         and not self.emp_data[e_check].get('is_jefe_pista', False)
                         and not self.emp_data[e_check].get('is_refuerzo', False)
                     ):
                         sunday_off_person = e_check
                         break
            
             rotation_target = rotation_queue[0] if rotation_queue else None

             # Guard: rotation_target NUNCA debe ser None si la cola tiene gente.
             # Si por algún bug de flujo quedó None, lo corregimos desde rotation_queue.
             if rotation_queue and not rotation_target:
                 rotation_target = rotation_queue[0]

             rest_report = self._build_rest_between_shifts_report(
                 res,
                 most_recent_schedule,
                 SHIFT_MIN_HOUR,
                 SHIFT_MAX_HOUR,
                 SHIFT_IS_WORKING,
                 min_rest_hours,
             )

             # Rotar la cola de domingos: los primeros de la cola que efectivamente
             # tuvieron libre este domingo se mueven al final.
             _rotated_queue = list(rotation_queue)
             if sunday_absence_vars:
                 _off_count = 0
                 for _e in _rotated_queue:
                     if _e in sunday_absence_vars and solver.Value(sunday_absence_vars[_e]):
                         _off_count += 1
                     else:
                         break  # first non-OFF in queue order stops the rotation
                 if _off_count > 0:
                     _rotated_queue = _rotated_queue[_off_count:] + _rotated_queue[:_off_count]
             
             return {
                  "status": "Success",
                  "schedule": res, 
                  "daily_tasks": res_tasks,
                  "metadata": {
                      "libres_person": libres_found,
                      "rotation_queue": rotation_queue,
                      "next_sunday_rotation_queue": _rotated_queue,  # Rotada: los que descansaron van al final
                     "rotation_target": rotation_target,
                     "sunday_off_person": sunday_off_person,
                     "special_days": dict(self.special_day_modes),
                     "solutions_found": solution_counter.solution_count,
                     "solver_objective_value": solver.ObjectiveValue(),
                     "solver_best_bound": solver.BestObjectiveBound(),
                     "solver_gap_percent": round(
                         (solver.ObjectiveValue() - solver.BestObjectiveBound())
                         / max(1, abs(solver.ObjectiveValue())) * 100,
                         3
                     ),
                     "solver_wall_time": solver.WallTime(),
                     "solver_max_time_applied": max_t,
                     "solver_status_optimal": bool(status == cp_model.OPTIMAL),
                     "min_rest_hours_applied": min_rest_hours,
                     "rest_between_shifts": rest_report,
                     "consistency_penalty": CONSISTENCY_PENALTY,
                     "consistency_exempt": consistency_exempt,
                     "lexicographic": lex_report,
                     "refuerzo_employees": [e for e in self.employees if self.emp_data.get(e, {}).get('is_refuerzo', False)],
                 }
             }
        if status == cp_model.INFEASIBLE:
             # El diagnóstico detallado (que corre solves de prueba) se ejecuta UNA sola
             # vez en solve() tras agotar todos los niveles de descanso, no aquí — así se
             # evita repetirlo por cada nivel del retry loop.
             message = "No se pudo generar horario. Revise los turnos fijos estrictos y la cobertura minima."
             return {"status": "Infeasible", "message": message}

        status_name = {
            cp_model.UNKNOWN: "Unknown",
            cp_model.MODEL_INVALID: "ModelInvalid",
        }.get(status, "Error")
        return {
            "status": status_name,
            "message": "El solver no pudo confirmar una solución dentro del tiempo disponible."
        }
