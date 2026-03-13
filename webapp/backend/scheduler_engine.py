# scheduler_engine.py
# EXACT PORT OF FUNCIONA.PY LOGIC

from ortools.sat.python import cp_model
import json
import logging

class SolutionCounter(cp_model.CpSolverSolutionCallback):
    def __init__(self):
        cp_model.CpSolverSolutionCallback.__init__(self)
        self.solution_count = 0
    def on_solution_callback(self):
        self.solution_count += 1
from datetime import datetime
import os

logger = logging.getLogger(__name__)

# CONSTANTS
DAYS = ["Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue"]
HOURS = list(range(5, 29))

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
    "R1_07-11": set(range(7, 11)),     # 07:00-11:00 (4h) - Refuerzo Medio Tiempo
    "R2_16-20": set(range(16, 20)),    # 16:00-20:00 (4h) - Refuerzo Medio Tiempo
    "Q1_05-11+17-20": set(range(5, 11)) | set(range(17, 20)),  # 5am-11am + 5pm-8pm
    "Q2_07-11+17-20": set(range(7, 11)) | set(range(17, 20)),  # 7-11am + 5-8pm (Optimal for peak)
    "Q3_05-11+17-22": set(range(5, 11)) | set(range(17, 22)),  # 5am-11am + 5pm-10pm (11h, covers night)
}
SHIFT_NAMES = list(SHIFTS.keys())

def coverage_bounds(h: int, day: str = None, standard_mode: bool = False, num_emps: int = 9):
    """Límites de cobertura según hora y día.
    
    REGLAS (Weekdays):
      h5: exactamente 2  |  h6: min 3  |  h7-h10: hard min 3, soft target 4
      h11: min 3  |  h12: min 3
      h13-h16: min 3  |  h17-h19: hard min 3, soft target 4
      h20-h22: exactamente 2  |  h23-h28: exactamente 1
    
    Hard min=3 at peak hours guarantees feasibility; existing soft constraints
    (500k penalty) strongly push toward 4 people during h7-h10 and h17-h19.
    
    DOMINGO: Relaxed except h17-h19 which keeps hard min 3 + soft target 4.
    """
    N = num_emps  # max employees (used as upper bound for 'min' constraints)
    
    if day == "Dom":
        if standard_mode:
            # PERFECT PUZZLE REQUIREMENTS for Sunday standard mode
            if 5 <= h <= 6: return (2, 2)     # Exactamente 2
            if 7 <= h <= 19: return (3, N)    # Minimum 3, max flexible to scale with workforce
            if 20 <= h <= 21: return (2, 2)   # Exactamente 2
            if 22 <= h <= 28: return (1, 1)   # Exactamente 1
        else:
            # Short-staffed rules
            if h == 5: return (2, 2)
            if h == 6: return (2, 5)
            if 7 <= h <= 16: return (3, N)
            if 17 <= h <= 19: return (3, N)  # Hard min 3 + soft target 4 (peak crítico)
            if 20 <= h <= 21: return (2, 2)    # Exactamente 2 (10pm leaver + 11pm leaver)
            if h == 22: return (1, 2)          # Relaxed: 1 or 2 (night + optional 11pm leaver)
            if 23 <= h <= 28: return (1, 1)    # Solo nocturno
            return (3, N)
    
    # Weekdays (Lun-Sáb)
    if h == 5: return (1, 2)          # Relaxed to min 1 (soft target 2 handled via penalty)
    if h == 6: return (2, N)          # Hard min 2 (soft target 3, J_07-17 compatibility)
    if 7 <= h <= 10: return (3, N)    # Hard min 3 (soft target 4 via 500k penalty)
    if h == 11: return (3, N)         # Mínimo 3
    if h == 12: return (3, N)         # Mínimo 3
    if 13 <= h <= 16: return (3, N)   # Mínimo 3
    if 17 <= h <= 19: return (3, N)   # Hard min 3 (soft target 4 via 500k penalty)
    if 20 <= h <= 22: return (2, 2)   # Exactamente 2
    if 23 <= h <= 28: return (1, 1)   # Exactamente 1
    return (3, N)


def touches_night(shift_name: str) -> bool:
    """Verifica si un turno cubre la franja 20:00-23:00"""
    shift_hours = SHIFTS[shift_name]
    return any(h in shift_hours for h in [20, 21, 22])

class ShiftScheduler:
    def __init__(self, employees_config, global_config, history_data=None):
        self.employees = [e['name'] for e in employees_config]
        self.emp_data = {e['name']: e for e in employees_config}
        self.config = global_config
        self.history = history_data or {}
        
        # INJECT REFUERZO si está activado
        if self.config.get('use_refuerzo', False):
            self.employees.append("Refuerzo")
            self.emp_data["Refuerzo"] = {
                "name": "Refuerzo",
                "gender": "M",  # Doesn't matter for Refuerzo
                "can_do_night": True, # Managed specifically by constraints
                "fixed_shifts": {},
                "is_refuerzo": True # Custom flag
            }
        
        # Determine roles based on input data
        # Refuerzo is NOT flexible for Sunday rotation, NOT night replacement, etc.
        self.flexibles = [e for e in self.employees if not self.emp_data[e].get('is_refuerzo')] 
        self.night_replacements = [e for e in self.employees if self.emp_data[e].get('can_do_night', True) and not self.emp_data[e].get('is_refuerzo')]

    def assign_tasks(self, schedule):
        """Assign daily tasks (Baños, Tanques, Oficina+Basureros) POST-HOC.
        
        FAIR ROTATION: Uses a weekly task counter to distribute tasks equitably.
        No gender preference. Jefe de Pista only eligible on Sáb.
        Night shift workers (N_22-05), OFF, VAC, and PERM are excluded.
        """
        res_tasks = {e: {d: None for d in DAYS} for e in self.employees}
        task_count = {e: 0 for e in self.employees}  # Weekly fairness counter
        
        for d in DAYS:
            available = []
            for e in self.employees:
                shift = schedule[e].get(d, "OFF")
                if shift in ["OFF", "VAC", "PERM", "N_22-05"]:
                    continue
                is_jefe = self.emp_data[e].get('is_jefe_pista', False)
                if is_jefe and d != "Sáb":
                    continue
                shift_hours = SHIFTS.get(shift, set())
                if not shift_hours:
                    continue
                available.append({
                    'name': e, 'shift': shift,
                    'start': min(shift_hours), 'hours': shift_hours,
                    'has_am': any(h < 12 for h in shift_hours),
                    'has_pm': any(h >= 12 for h in shift_hours),
                    'is_quebrado': shift.startswith('Q'),
                })
            
            assigned_today = set()
            
            def fair_pick(pool):
                """Pick person with fewest accumulated tasks (fair rotation)."""
                if not pool: return None
                pool.sort(key=lambda w: task_count[w['name']])
                return pool[0]
            
            def q_label(base, worker):
                if worker['is_quebrado']:
                    return f"{base} {'↑AM' if worker['start'] < 12 else '↓PM'}"
                return base
            
            # --- AM TANQUES: 5 AM starter (gender-neutral) ---
            pool = [w for w in available if w['start'] == 5 and w['name'] not in assigned_today]
            pick = fair_pick(pool)
            if pick:
                res_tasks[pick['name']][d] = q_label("Tanques", pick)
                assigned_today.add(pick['name']); task_count[pick['name']] += 1
            
            # --- AM BAÑOS: starts ≤ 7 AM (gender-neutral, fair rotation) ---
            pool = [w for w in available if w['start'] <= 7 and w['has_am'] and w['name'] not in assigned_today]
            oficina_person = None
            if d in ["Lun", "Jue"]:
                ofi_pool = [w for w in pool if w['start'] <= 6 or w['is_quebrado']]
                ofi_pick = fair_pick(ofi_pool)
                if ofi_pick:
                    oficina_person = ofi_pick['name']
                    pool = [w for w in pool if w['name'] == oficina_person] + [w for w in pool if w['name'] != oficina_person]
            pick = fair_pick(pool) if not oficina_person else (pool[0] if pool else None)
            if pick:
                if d in ["Lun", "Jue"] and pick['name'] == oficina_person:
                    res_tasks[pick['name']][d] = q_label("Oficina + Basureros + Baños", pick)
                else:
                    res_tasks[pick['name']][d] = q_label("Baños", pick)
                assigned_today.add(pick['name']); task_count[pick['name']] += 1
            
            # --- PM TANQUES: starts ≥ 12 PM OR quebrado with PM (gender-neutral) ---
            pool = [w for w in available if (w['start'] >= 12 or w['is_quebrado']) and w['has_pm'] and w['name'] not in assigned_today]
            pick = fair_pick(pool)
            if pick:
                res_tasks[pick['name']][d] = q_label("Tanques", pick)
                assigned_today.add(pick['name']); task_count[pick['name']] += 1
            
            # --- PM BAÑOS: starts ≥ 12 PM OR quebrado with PM (gender-neutral) ---
            pool = [w for w in available if (w['start'] >= 12 or w['is_quebrado']) and w['has_pm'] and w['name'] not in assigned_today]
            pick = fair_pick(pool)
            if pick:
                res_tasks[pick['name']][d] = q_label("Baños", pick)
                assigned_today.add(pick['name']); task_count[pick['name']] += 1
            
            # Oficina fallback
            if d in ["Lun", "Jue"] and oficina_person and oficina_person not in assigned_today:
                res_tasks[oficina_person][d] = "Oficina + Basureros"
                assigned_today.add(oficina_person); task_count[oficina_person] += 1
        
        return res_tasks


    def solve(self):
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
                    entries.append({"schedule": normalized})
            elif isinstance(history_obj, dict) and history_obj:
                normalized = normalize_history_schedule(history_obj, "history[dict]")
                entries.append({"schedule": normalized})
            return entries

        history_entries = normalize_history_entries(self.history)
        most_recent_schedule = history_entries[-1].get("schedule", {}) if history_entries else {}

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

        # Precomputar pares de turnos incompatibles por descanso mínimo
        # 12h para empleados normales, 8h para la persona de libres
        _min_rest_normal = 12
        _min_rest_libres = 8
        INCOMPATIBLE_REST_PAIRS_12H = set()
        INCOMPATIBLE_REST_PAIRS_8H = set()
        for _s1 in SHIFT_NAMES:
            if not SHIFT_IS_WORKING[_s1]:
                continue
            _end1 = SHIFT_MAX_HOUR[_s1] + 1
            for _s2 in SHIFT_NAMES:
                if not SHIFT_IS_WORKING[_s2]:
                    continue
                _start2 = SHIFT_MIN_HOUR[_s2]
                _rest = (_start2 + 24) - _end1
                if _rest < _min_rest_normal:
                    INCOMPATIBLE_REST_PAIRS_12H.add((_s1, _s2))
                if _rest < _min_rest_libres:
                    INCOMPATIBLE_REST_PAIRS_8H.add((_s1, _s2))
        # Pares que SOLO aplican con 12h (no con 8h) — para condicional de libres
        INCOMPATIBLE_ONLY_12H = INCOMPATIBLE_REST_PAIRS_12H - INCOMPATIBLE_REST_PAIRS_8H

        x = {} 
        penalties = []
        peak_penalties = []
        
        # Variables
        for e in self.employees:
            for d in DAYS:
                for s in SHIFT_NAMES:
                    x[(e, d, s)] = model.NewBoolVar(f"x_{e}_{d}_{s}")
                
                # CORE: Exactly one shift per day
                model.Add(sum(x[(e, d, s)] for s in SHIFT_NAMES) == 1)

        # CORE: OFF Day Limit (Standard = 1 per week)
        # NOTA: PERM es una ausencia EXENTA — no cuenta como día libre.
        # El empleado con PERM aún recibe su OFF normal por separado.
        # Si el empleado tiene N días de VAC u OFF forzados, el constraint es
        # OFF+VAC == base_off + forced_vac_or_off.
        for e in self.employees:
            if self.emp_data[e].get('is_refuerzo'): continue
            fs = self.emp_data[e].get('fixed_shifts', {}) or {}
            
            forced_vac = sum(1 for d in DAYS if fs.get(d) == 'VAC')
            forced_off = sum(1 for d in DAYS if fs.get(d) == 'OFF')
            
            # Base off is 1, but if they have more forced OFFs, we allow that many.
            base_off = max(1, forced_off)
            
            if self.emp_data[e].get('is_jefe_pista'):
                model.Add(sum(x[(e, d, "OFF")] + x[(e, d, "VAC")] for d in DAYS) == base_off + forced_vac)
            elif self.config.get('fixed_night_person') == e:
                # Night person already handled in LOGICA NIGHT / ELIGIO
                pass
            else:
                model.Add(sum(x[(e, d, "OFF")] + x[(e, d, "VAC")] for d in DAYS) == base_off + forced_vac)

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
            model.Add(sum(persona_hace_libres[e] for e in candidates) == 1)
        
        # =========================
        # RESTRICCIÓN: HORARIOS CONSISTENTES
        # =========================
        # NOTE: The Libres person switches between N_22-05 and day shifts,
        # so they CANNOT have a single "principal" shift. We skip all
        # night_replacement candidates (they might become Libres)
        # and the primary night person (who only does N_22-05/OFF).
        turno_principal = {}
        
        night_person_name = self.config.get('fixed_night_person', None)
        
        for e in self.employees:
            # Skip primary night person (only does N_22-05 / OFF)
            if e == night_person_name:
                continue
                
            # Skip if fully fixed
            fixed_days_count = len(self.emp_data[e].get('fixed_shifts', {}))
            if fixed_days_count > 5:
                continue
            
            # Candidatos de libres: tienen turno principal pero la consistencia
            # solo aplica en días donde NO hacen N_22-05
            if e in self.night_replacements:
                turno_principal[e] = {}
                for s in SHIFT_NAMES:
                    if s in ["OFF", "VAC", "PERM", "N_22-05"] or s.startswith("J_") or s.startswith("X_") or s.startswith("Q"):
                        continue
                    turno_principal[e][s] = model.NewBoolVar(f"principal_{e}_{s}")
                if turno_principal[e]:
                    model.Add(sum(turno_principal[e].values()) == 1)
                continue
            
            turno_principal[e] = {}
            for s in SHIFT_NAMES:
                if s in ["OFF", "VAC", "PERM"] or s.startswith("J_") or s.startswith("X_") or s.startswith("Q"): continue
                turno_principal[e][s] = model.NewBoolVar(f"principal_{e}_{s}")
            
            if turno_principal[e]:
                model.Add(sum(turno_principal[e].values()) == 1)
                
                # Consistency Penalty: Penalize deviations from the assigned turno_principal.
                # If they work a shift `s` on day `d` that is NOT their `turno_principal[s]`, apply penalty.
                # (Excluding special shifts like OFF, VAC, PERM, J_, X_, Q_)
                CONSISTENCY_PENALTY = 50000
                for d in DAYS:
                    for s in SHIFT_NAMES:
                        if s in ["OFF", "VAC", "PERM"] or s.startswith("J_") or s.startswith("X_") or s.startswith("Q"):
                            continue
                        
                        # Deviation happens if x[(e, d, s)] == 1 AND turno_principal[e][s] == 0
                        is_working_s = x[(e, d, s)]
                        is_not_principal = turno_principal[e][s].Not()
                        
                        deviation = model.NewBoolVar(f"dev_{e}_{d}_{s}")
                        model.AddBoolAnd([is_working_s, is_not_principal]).OnlyEnforceIf(deviation)
                        model.AddBoolOr([is_working_s.Not(), turno_principal[e][s]]).OnlyEnforceIf(deviation.Not())
                        
                        penalties.append(CONSISTENCY_PENALTY * deviation)

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
        

        # =========================
        # RESTRICCIÓN: ESTRICTAMENTE VACACIONES / PERMISOS (MANUAL)
        # =========================
        # VAC and PERM can ONLY be assigned if they are in fixed_shifts.
        for e in self.employees:
             fixed_map = self.emp_data[e].get('fixed_shifts', {})
             for d in DAYS:
                  if fixed_map.get(d) != "VAC":
                      model.Add(x[(e, d, "VAC")] == 0)
                  if fixed_map.get(d) != "PERM":
                      model.Add(x[(e, d, "PERM")] == 0)


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
        # Jefe de Pista and Night Person are ALWAYS strict regardless of toggle.
        global_strict = self.config.get('strict_preferences', False)
        
        fixed_constraints = {}
        soft_preferences = {}  # (e, d) -> s_code for flexible employees
        
        for e in self.employees:
            fixed_map = self.emp_data[e].get('fixed_shifts', {})
            is_strict = self.emp_data[e].get('strict_preferences', False)
            is_jefe = self.emp_data[e].get('is_jefe_pista', False)
            is_night = (primary_night and e == primary_night)
            
            # Jefe and Night are ALWAYS strict, plus global strict
            force_strict = global_strict or is_strict or is_jefe or is_night
            
            for d, s_code in fixed_map.items():
                if d in DAYS and s_code in SHIFT_NAMES:
                    # Prevent clashing constraints for Jefe de Pista on Saturday
                    if is_jefe and d == "Sáb" and s_code not in ["VAC", "PERM"]:
                        continue
                    # VAC and PERM are ALWAYS hard constraints (manual overrides)
                    if s_code in ["VAC", "PERM"]:
                        fixed_constraints[(e, d)] = s_code
                    elif force_strict:
                        fixed_constraints[(e, d)] = s_code
                    else:
                        soft_preferences[(e, d)] = s_code
                    
        # Apply HARD constraints (strict employees + VAC/PERM)
        for (e, d), s_code in fixed_constraints.items():
            for s in SHIFT_NAMES:
                model.Add(x[(e, d, s)] == (1 if s == s_code else 0))
        
        # Apply SOFT constraints (flexible employees)
        # Penalty: 5000000 per day of deviation. This is extremely high, making it
        # act essentially like a hard constraint but without causing Infeasible crashes
        # if mathematically impossible (it will just eat the penalty and warn).
        PREF_DEVIATION_PENALTY = 5000000
        for (e, d), s_code in soft_preferences.items():
            pref_violated = model.NewBoolVar(f"pref_violated_{e}_{d}")
            model.Add(x[(e, d, s_code)] == 0).OnlyEnforceIf(pref_violated)
            model.Add(x[(e, d, s_code)] == 1).OnlyEnforceIf(pref_violated.Not())
            penalties.append(PREF_DEVIATION_PENALTY * pref_violated)
                
        # =========================
        # RESTRICCIÓN: SÁBADOS DE JEFE DE PISTA (5AM a 1PM)
        # =========================
        # Jefe de Pista must always work T1_05-13 on Saturdays
        for e in self.employees:
            if self.emp_data[e].get('is_jefe_pista', False):
                # Overrides any other rule for Jefe on Saturday unless they have VAC/PERM
                if fixed_constraints.get((e, "Sáb")) not in ["VAC", "PERM"]:
                    for s in SHIFT_NAMES:
                        model.Add(x[(e, "Sáb", s)] == (1 if s == "T1_05-13" else 0))

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
            _night_base_off = max(1, _night_forced_off)
            model.Add(sum(
                x[(primary_night, d, "OFF")] + x[(primary_night, d, "VAC")] + x[(primary_night, d, "PERM")]
                for d in DAYS
            ) == _night_base_off + _night_forced_vac)

            # c) Reemplazo nocturno: solo la persona de libres cubre a Primary,
            #    EXCEPTO cuando hay un empleado con fixed_shift N_22-05 ese día
            #    (cobertura manual explícita → la persona de libres queda libre).
            for d in DAYS:
                # Detectar si algún otro empleado tiene N_22-05 fijado manualmente ese día
                manual_night_cover_d = any(
                    emp != primary_night
                    and self.emp_data[emp].get('fixed_shifts', {}).get(d) == "N_22-05"
                    for emp in self.employees
                )

                # Primary is OFF logic includes VAC and PERM
                primary_off_var = model.NewBoolVar(f"primary_off_{d}")
                model.Add(x[(primary_night, d, "OFF")] + x[(primary_night, d, "VAC")] + x[(primary_night, d, "PERM")] == 1).OnlyEnforceIf(primary_off_var)
                model.Add(x[(primary_night, d, "OFF")] + x[(primary_night, d, "VAC")] + x[(primary_night, d, "PERM")] == 0).OnlyEnforceIf(primary_off_var.Not())

                # Requirement: If Primary is OFF, EXACTLY one other night-eligible person MUST do N_22-05
                # This handles all "special cases" naturally.
                model.Add(sum(x[(e, d, "N_22-05")] for e in self.night_replacements if e != primary_night) == 1).OnlyEnforceIf(primary_off_var)
                model.Add(sum(x[(e, d, "N_22-05")] for e in self.night_replacements if e != primary_night) == 0).OnlyEnforceIf(primary_off_var.Not())

                # Preference: The assigned "persona_hace_libres" is the STRONGLY preferred candidate
                for e_repl in self.night_replacements:
                    if e_repl == primary_night or e_repl not in persona_hace_libres: continue
                    
                    is_libres = persona_hace_libres[e_repl]
                    libres_is_off_d = model.NewBoolVar(f"libres_is_off_{e_repl}_{d}")
                    model.Add(x[(e_repl, d, "OFF")] + x[(e_repl, d, "VAC")] + x[(e_repl, d, "PERM")] == 1).OnlyEnforceIf(libres_is_off_d)
                    model.Add(x[(e_repl, d, "OFF")] + x[(e_repl, d, "VAC")] + x[(e_repl, d, "PERM")] == 0).OnlyEnforceIf(libres_is_off_d.Not())
                    
                    # If e is the Libres person and primary is off, they MUST cover UNLESS they are also OFF
                    # If they are OFF, the sum constraint above will pick someone else.
                    should_cover = model.NewBoolVar(f"should_cover_{e_repl}_{d}")
                    model.AddBoolAnd([is_libres, primary_off_var, libres_is_off_d.Not()]).OnlyEnforceIf(should_cover)
                    model.AddBoolOr([is_libres.Not(), primary_off_var.Not(), libres_is_off_d]).OnlyEnforceIf(should_cover.Not())
                    
                    # 1M penalty if the ideal replacement doesn't cover (allows fallback to others)
                    penalties.append(1000000 * should_cover.Not())
                    # model.Add(x[(e_repl, d, "N_22-05")] == 1).OnlyEnforceIf(should_cover) # Too aggressive
                    # Instead of hard Add, use another soft penalty to prefer the libres person
                    penalties.append(2000000 * should_cover.Not())

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
                            model.Add(x[(e, d, "N_22-05")] == 0).OnlyEnforceIf(is_libres.Not())
                    else:
                        # e in replacements but not in flexibles? (e.g. Jefe de Pista if can_do_night=True)
                        # Then he cannot be 'persona_hace_libres', so he cannot do night replacement here.
                        for d in DAYS:
                            if self.emp_data[e].get('fixed_shifts', {}).get(d) == "N_22-05":
                                continue
                            model.Add(x[(e, d, "N_22-05")] == 0)

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
                # RELAXED: Use high penalty instead of hard Add(x == 0) to prevent Infeasible.
                # Penalty (6M) is higher than coverage (5M), so it only breaks if strictly necessary.
                INVALID_SHIFT_PENALTY = 6000000
                for d in DAYS:
                    # Lógica de selección de lista permitida
                    if d == "Dom":
                        allowed = ALLOWED_WOMEN_SUN
                    elif d == "Sáb":
                        allowed = ALLOWED_WOMEN_SAT 
                    else:
                        allowed = ALLOWED_WOMEN_WEEK
                        
                    for s in SHIFT_NAMES:
                        if s not in allowed:
                            penalties.append(INVALID_SHIFT_PENALTY * x[(e, d, s)])

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
        women = [e for e in self.employees if self.emp_data[e].get('gender') == 'F']
        if len(women) == 2:
            w1, w2 = women[0], women[1]
            
            # Classify shifts as AM (start < 12) or PM (start >= 12)
            am_shifts = [s for s in SHIFT_NAMES if SHIFT_IS_WORKING.get(s) and SHIFT_MIN_HOUR.get(s) is not None and SHIFT_MIN_HOUR[s] < 12]
            pm_shifts = [s for s in SHIFT_NAMES if SHIFT_IS_WORKING.get(s) and SHIFT_MIN_HOUR.get(s) is not None and SHIFT_MIN_HOUR[s] >= 12]
            
            for d in DAYS:
                # Skip if either has a fixed OFF/VAC/PERM for this day
                fixed_w1 = self.emp_data[w1].get('fixed_shifts', {}).get(d)
                fixed_w2 = self.emp_data[w2].get('fixed_shifts', {}).get(d)
                if fixed_w1 in ['OFF', 'VAC', 'PERM'] or fixed_w2 in ['OFF', 'VAC', 'PERM']:
                    continue
                
                # Bool: is each woman working (not OFF/VAC/PERM)?
                w1_working = model.NewBoolVar(f"w1_working_{d}")
                model.Add(x[(w1, d, "OFF")] + x[(w1, d, "VAC")] + x[(w1, d, "PERM")] == 0).OnlyEnforceIf(w1_working)
                model.Add(x[(w1, d, "OFF")] + x[(w1, d, "VAC")] + x[(w1, d, "PERM")] >= 1).OnlyEnforceIf(w1_working.Not())
                
                w2_working = model.NewBoolVar(f"w2_working_{d}")
                model.Add(x[(w2, d, "OFF")] + x[(w2, d, "VAC")] + x[(w2, d, "PERM")] == 0).OnlyEnforceIf(w2_working)
                model.Add(x[(w2, d, "OFF")] + x[(w2, d, "VAC")] + x[(w2, d, "PERM")] >= 1).OnlyEnforceIf(w2_working.Not())
                
                both_working = model.NewBoolVar(f"both_women_working_{d}")
                model.AddBoolAnd([w1_working, w2_working]).OnlyEnforceIf(both_working)
                model.AddBoolOr([w1_working.Not(), w2_working.Not()]).OnlyEnforceIf(both_working.Not())
                
                # w1 is AM if she works an AM shift
                w1_am = model.NewBoolVar(f"w1_am_{d}")
                model.Add(sum(x[(w1, d, s)] for s in am_shifts) >= 1).OnlyEnforceIf([both_working, w1_am])
                model.Add(sum(x[(w1, d, s)] for s in am_shifts) == 0).OnlyEnforceIf([both_working, w1_am.Not()])
                
                # If both working, penalize if they are not opposite.
                # W1 AM -> W2 should be PM. W1 PM -> W2 should be AM.
                # Make this a very strong soft constraint rather than a hard constraint,
                # to prevent Infeasibility crashes when combined with strict preferences.
                w2_pm = model.NewBoolVar(f"w2_pm_{d}")
                model.Add(sum(x[(w2, d, s)] for s in pm_shifts) >= 1).OnlyEnforceIf([both_working, w2_pm])
                model.Add(sum(x[(w2, d, s)] for s in pm_shifts) == 0).OnlyEnforceIf([both_working, w2_pm.Not()])
                
                w2_am = model.NewBoolVar(f"w2_am_{d}")
                model.Add(sum(x[(w2, d, s)] for s in am_shifts) >= 1).OnlyEnforceIf([both_working, w2_am])
                model.Add(sum(x[(w2, d, s)] for s in am_shifts) == 0).OnlyEnforceIf([both_working, w2_am.Not()])
                
                # We want (W1_AM and W2_PM) OR (not W1_AM and W2_AM)
                # If neither is true while both are working and it isn't a collision day, penalize heavily.
                opposite_satisfied = model.NewBoolVar(f"opposite_{d}")
                model.AddBoolOr([
                    w1_am.Not(), w2_pm.Not() # If either is false, this AND is false... wait, better logic:
                ]) # This is getting too complex. Let's do a direct penalty on the overlapping states.
                
                # Overlap 1: Both AM
                both_am = model.NewBoolVar(f"both_am_{d}")
                model.AddBoolAnd([both_working, w1_am, w2_am]).OnlyEnforceIf(both_am)
                model.AddBoolOr([both_working.Not(), w1_am.Not(), w2_am.Not()]).OnlyEnforceIf(both_am.Not())
                
                # Overlap 2: Both PM
                both_pm = model.NewBoolVar(f"both_pm_{d}")
                model.AddBoolAnd([both_working, w1_am.Not(), w2_pm]).OnlyEnforceIf(both_pm)
                model.AddBoolOr([both_working.Not(), w1_am, w2_pm.Not()]).OnlyEnforceIf(both_pm.Not())
                
                # Penalize overlaps only on non-collision days
                not_collision = women_collision[d].Not()
                penalized_am_overlap = model.NewBoolVar(f"penalized_am_overlap_{d}")
                model.AddBoolAnd([both_am, not_collision]).OnlyEnforceIf(penalized_am_overlap)
                model.AddBoolOr([both_am.Not(), not_collision.Not()]).OnlyEnforceIf(penalized_am_overlap.Not())
                
                penalized_pm_overlap = model.NewBoolVar(f"penalized_pm_overlap_{d}")
                model.AddBoolAnd([both_pm, not_collision]).OnlyEnforceIf(penalized_pm_overlap)
                model.AddBoolOr([both_pm.Not(), not_collision.Not()]).OnlyEnforceIf(penalized_pm_overlap.Not())
                
                # Huge penalty for violation, ensuring it's respected unless mathematically impossible
                # Relaxed: Lower penalties for violation to allow "brief overlaps" as requested
                # ensuring it's avoided if possible but not at the cost of feasibility.
                penalties.append(200000 * penalized_am_overlap)
                penalties.append(200000 * penalized_pm_overlap)

                # --- NEW: Same Shift Guard for Women ---
                # If they share the exact same shift code, add moderate penalty
                for s_shared in SHIFT_NAMES:
                    if s_shared in ["OFF", "VAC", "PERM"]: continue
                    both_on_same_s = model.NewBoolVar(f"both_on_same_{s_shared}_{d}")
                    model.AddBoolAnd([x[(w1, d, s_shared)], x[(w2, d, s_shared)], not_collision]).OnlyEnforceIf(both_on_same_s)
                    penalties.append(300000 * both_on_same_s)

        # =========================
        # RESTRICCIÓN: DESCANSO MÍNIMO (12h normal, 8h libres)
        # =========================
        # Empleados normales: 12h de descanso entre turnos consecutivos.
        # Persona de libres: solo 8h (por ley, al cubrir distintos turnos).
        # OPTIMIZADO: pares precomputados en 3 grupos:
        #   - 8H pairs: SIEMPRE prohibidos para TODOS
        #   - ONLY_12H pairs: prohibidos SOLO si NO eres la persona de libres
        
        for e in self.employees:
            # 1. CROSS-WEEK BOUNDARY: Thursday (History) -> Friday (Current)
            last_jue_shift = most_recent_schedule.get(e, {}).get("Jue", "OFF")
            if last_jue_shift not in SHIFT_NAMES:
                last_jue_shift = "OFF"

            # Hard block independiente: N_22-05 (Jue) -> turnos tempranos (Vie)
            if last_jue_shift == "N_22-05":
                for s2 in explicit_night_to_morning_blocks:
                    model.Add(x[(e, "Vie", s2)] == 0)
            elif "Jue" not in most_recent_schedule.get(e, {}):
                if e in known_last_night_employee:
                    logger.warning(
                        "Historial no confiable para Jue de %s; se aplica fallback conservador por último nocturno conocido",
                        e,
                    )
                    for s2 in explicit_night_to_morning_blocks:
                        model.Add(x[(e, "Vie", s2)] == 0)

            if last_jue_shift in SHIFT_NAMES and SHIFT_IS_WORKING.get(last_jue_shift):
                s1 = last_jue_shift
                d2 = "Vie"
                for s2 in SHIFT_NAMES:
                    if (s1, s2) in INCOMPATIBLE_REST_PAIRS_8H:
                        model.Add(x[(e, d2, s2)] == 0)
                    if (s1, s2) in INCOMPATIBLE_ONLY_12H:
                        if e in persona_hace_libres:
                            model.Add(x[(e, d2, s2)] == 0).OnlyEnforceIf(persona_hace_libres[e].Not())
                        else:
                            model.Add(x[(e, d2, s2)] == 0)
                            
            # 2. INTRA-WEEK BOUNDARY: Day i -> Day i+1
            for i in range(len(DAYS) - 1):
                d1 = DAYS[i]
                d2 = DAYS[i + 1]
                # 8h pairs: hard constraint for everyone (including libres)
                for (s1, s2) in INCOMPATIBLE_REST_PAIRS_8H:
                    model.Add(x[(e, d2, s2)] == 0).OnlyEnforceIf(x[(e, d1, s1)])
                
                # 12h-only pairs: only for non-libres employees
                if e in persona_hace_libres:
                    for (s1, s2) in INCOMPATIBLE_ONLY_12H:
                        model.Add(x[(e, d2, s2)] == 0).OnlyEnforceIf(
                            [x[(e, d1, s1)], persona_hace_libres[e].Not()]
                        )
                else:
                    # Not a libres candidate — always apply 12h
                    for (s1, s2) in INCOMPATIBLE_ONLY_12H:
                        model.Add(x[(e, d2, s2)] == 0).OnlyEnforceIf(x[(e, d1, s1)])

        # =========================
        # DYNAMIC PENALTY MODE (Standard Mode Detection)
        # =========================
        # Count active employees (not on VAC/PERM all week)
        active_count = 0
        for e in self.employees:
            # Excluir Refuerzo del conteo
            if self.emp_data[e].get('is_refuerzo', False):
                continue
            fixed = self.emp_data[e].get('fixed_shifts', {})
            all_absent = all(fixed.get(d) in ['VAC', 'PERM'] for d in DAYS)
            if not all_absent:
                active_count += 1
        
        # THRESHOLD: With >= 10 active employees, standard 8h shifts cover all peaks.
        standard_mode = active_count >= 10

        # Cobertura
        coverage = {}
        for d in DAYS:
            for h in HOURS:
                mn, mx = coverage_bounds(h, d, standard_mode)
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
                model.Add(cov >= mn)
                model.Add(cov <= mx)

        # =========================
        # SOFT CONSTRAINT: Prefer 4+ people during peak hours (Lun-Sáb, h7-19)
        # Uses broken shifts (Q1/Q2) to achieve this when possible.
        # =========================
        
        # SOFT: Strongly prefer 2 people at h5-h6 on weekdays (penalty 3000 per hour below 2)
        # SOFT: Strongly prefer 2 people at h5 (5-6am)
        for d in DAYS:
            if d == "Dom": continue
            # h5 target 2
            cov = coverage[(d, 5)]
            below_2_h5 = model.NewBoolVar(f"below2_h5_{d}")
            model.Add(cov < 2).OnlyEnforceIf(below_2_h5)
            model.Add(cov >= 2).OnlyEnforceIf(below_2_h5.Not())
            peak_penalties.append(200000 * below_2_h5)

            # h6 target 3 (6-7am)
            cov6 = coverage[(d, 6)]
            below_3_h6 = model.NewBoolVar(f"below3_h6_{d}")
            model.Add(cov6 < 3).OnlyEnforceIf(below_3_h6)
            model.Add(cov6 >= 3).OnlyEnforceIf(below_3_h6.Not())
            peak_penalties.append(200000 * below_3_h6)
        
        # SOFT: Prefer 4+ people during peak hours (Lun-Sáb, h7-10 and h16-19)
        # AM peak (h7-h10) has a much higher penalty than PM — losing AM coverage can NEVER
        # be compensated by stacking PM shifts. 5M per hour ensures the solver always
        # prioritizes AM coverage over any PM combination.
        for d in DAYS:
            if d == "Dom":
                continue
            for h in [7, 8, 9, 10, 16, 17, 18, 19]:
                cov = coverage[(d, h)]
                below_4 = model.NewBoolVar(f"below4_{d}_{h}")
                model.Add(cov < 4).OnlyEnforceIf(below_4)
                model.Add(cov >= 4).OnlyEnforceIf(below_4.Not())
                # AM hours get 5M penalty (uncrossable), PM hours keep 500k
                am_penalty = 5000000 if h in [7, 8, 9, 10] else 500000
                peak_penalties.append(am_penalty * below_4)
                
        # SOFT: Prefer 4+ people during off-peak hours as well (Lun-Sáb, h11-15)
        # But this penalty is much lower, so solver drops these hours first if short-staffed
        for d in DAYS:
            if d == "Dom":
                continue
            for h in [11, 12, 13, 14, 15]:
                cov = coverage[(d, h)]
                below_4 = model.NewBoolVar(f"below4_{d}_{h}")
                model.Add(cov < 4).OnlyEnforceIf(below_4)
                model.Add(cov >= 4).OnlyEnforceIf(below_4.Not())
                peak_penalties.append(100000 * below_4)

        # =========================
        # SOFT PREFERENCE: Concentrate broken shifts on fewer people
        # Coverage rules are MORE important than concentrating broken shifts.
        # Night person and Jefe de Pista CANNOT have broken shifts (hard).
        # Everyone else CAN, but spreading incurs a penalty.
        # =========================
        # Hard: night person and Jefe de pista never get broken shifts
        for e in self.employees:
            if e == night_person_name or self.emp_data[e].get('is_jefe_pista', False):
                for d in DAYS:
                    model.Add(x[(e, d, "Q1_05-11+17-20")] == 0)
                    model.Add(x[(e, d, "Q2_07-11+17-20")] == 0)
                    model.Add(x[(e, d, "Q3_05-11+17-22")] == 0)
        
        # Soft: penalize each person who has ANY broken shift (prefer concentration)
        for e in self.employees:
            if e == night_person_name or self.emp_data[e].get('is_jefe_pista', False):
                continue
            has_any_q = model.NewBoolVar(f"has_any_q_{e}")
            q_sum = sum(x[(e, d, "Q1_05-11+17-20")] + x[(e, d, "Q2_07-11+17-20")] + x[(e, d, "Q3_05-11+17-22")] for d in DAYS)
            model.Add(q_sum >= 1).OnlyEnforceIf(has_any_q)
            model.Add(q_sum == 0).OnlyEnforceIf(has_any_q.Not())
            # 100 penalty per person with broken shifts (much less than 2000/hour coverage penalty)
            pen_q_spread = model.NewIntVar(0, 100, f"pen_q_spread_{e}")
            model.Add(pen_q_spread == 100).OnlyEnforceIf(has_any_q)
            model.Add(pen_q_spread == 0).OnlyEnforceIf(has_any_q.Not())
            peak_penalties.append(pen_q_spread)
            
        # =========================
        # RESTRICCIÓN: PENALIZACIÓN DE TURNOS OVERTIME (T11, T16)
        # =========================
        # The user requested to keep T11, T16 but heavily penalize them so they 
        # are only used when absolutely necessary to satisfy coverage bounds on Saturdays/Peak.
        OVERTIME_PENALTY = 750000
        for e in self.employees:
            for d in DAYS:
                peak_penalties.append(OVERTIME_PENALTY * x[(e, d, "T11_12-20")])
                peak_penalties.append(OVERTIME_PENALTY * x[(e, d, "T16_05-14")])
            
        # =========================
        # CONSTRAINT: Forced Quebrado (Hard)
        # If employee has forced_quebrado=True, they must work Q1/Q2/Q3 on ALL working days.
        # Exactly 1 OFF day (or VAC/PERM). No other shift types allowed.
        # =========================
        for e in self.employees:
            if self.emp_data[e].get('forced_quebrado', False):
                for d in DAYS:
                    for s in SHIFT_NAMES:
                        if s not in ["OFF", "VAC", "PERM", "Q1_05-11+17-20", "Q2_07-11+17-20", "Q3_05-11+17-22"]:
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
        use_refuerzo = "Refuerzo" in self.employees
        refuerzo_active_days = {}  # d -> BoolVar
        
        weekdays = [d for d in DAYS if d != "Dom"]
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
                and (d != "Dom" or e not in sat_dom_only)  # exclude sat_dom_only from Sunday count
            )

        # HARD: Sunday allows up to 2 elective flex OFFs + any mandatory fixed DOM OFFs.
        # Fixed DOM OFFs are guaranteed by hard constraints elsewhere and don't consume
        # an elective slot — the cap only limits truly discretionary Sunday absences.
        mandatory_dom_off_count = sum(
            1 for e in self.employees
            if not self.emp_data[e].get('is_refuerzo', False)
            and e != primary_night
            and not self.emp_data[e].get('is_jefe_pista', False)
            and e not in sat_dom_only
            and self.emp_data[e].get('fixed_shifts', {}).get('Dom') in ['OFF', 'VAC', 'PERM']
        )
        model.Add(flex_off_per_day["Dom"] <= 3 + mandatory_dom_off_count)
        
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
        
        if d4_sunday_eligible:
            model.Add(sum(x[(e, "Dom", "D4_13-22")] for e in d4_sunday_eligible) >= 1)
        
        # HARD: Each weekday, allow up to max_off conditionally.
        for d in weekdays:
            # We allow 2 people OFF generally.
            max_off = max(2, mandatory_absent[d])
            model.Add(flex_off_per_day[d] <= max_off)
            
            collision_vars[d] = model.NewBoolVar(f"collision_{d}")
            model.Add(flex_off_per_day[d] >= 2).OnlyEnforceIf(collision_vars[d])
            model.Add(flex_off_per_day[d] < 2).OnlyEnforceIf(collision_vars[d].Not())
        
        # HARD: We MUST have enough collision days to satisfy total needed OFF days
        # Needed: 1 for every flexible worker, minus 2 for Sunday, minus 5 for regular weekday singles.
        # This handles anywhere from 8 to 11 employees cleanly without breaking.
        total_flex_employees = len([e for e in self.employees 
                                  if not self.emp_data[e].get('is_refuerzo', False) 
                                  and e != primary_night 
                                  and not self.emp_data[e].get('is_jefe_pista', False)])
        
        # If total_flex_employees > 7, we mathematically NEED collision days.
        required_collisions = max(0, total_flex_employees - 7)
        if required_collisions > 0:
             # We need at least `required_collisions` days with >= 2 people off
             model.Add(sum(collision_vars[d] for d in weekdays) >= required_collisions)
             
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
                penalties.append(1000000 * night_not_on_collision)
        
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
                peak_penalties.append(2000000 * shortfall_am)

            for h in [17, 18, 19]:
                cov = coverage[(d, h)]
                shortfall_pm = model.NewIntVar(0, 10, f"shortfall_pm_{d}_{h}")
                model.Add(shortfall_pm >= min_peak_pm - cov).OnlyEnforceIf(elective_collision[d])
                model.Add(shortfall_pm >= 0)
                peak_penalties.append(2000000 * shortfall_pm)
        
        # =========================
        # REFUERZO LOGIC - Works ONLY on the single collision day
        # =========================
        if use_refuerzo:
            refuerzo = "Refuerzo"
            ref_type = self.config.get('refuerzo_type', 'diurno')
            
            # Sunday: Refuerzo always OFF
            model.Add(x[(refuerzo, "Dom", "OFF")] == 1)
            refuerzo_active_days["Dom"] = model.NewConstant(0)
            
            # Weekdays: Refuerzo works IFF it's the collision day
            for d in weekdays:
                # HARD: If collision day -> Refuerzo MUST work
                model.Add(x[(refuerzo, d, "OFF")] == 0).OnlyEnforceIf(collision_vars[d])
                # HARD: If NOT collision day -> Refuerzo MUST be OFF
                model.Add(x[(refuerzo, d, "OFF")] == 1).OnlyEnforceIf(collision_vars[d].Not())
                
                refuerzo_active_days[d] = collision_vars[d]
            
            # Turnos Permitidos segun preferencia
            allowed_shifts_refuerzo = ["OFF"]
            if standard_mode:
                if ref_type == 'nocturno':
                    allowed_shifts_refuerzo.extend(["R2_16-20"])
                elif ref_type == 'diurno':
                    allowed_shifts_refuerzo.extend(["R1_07-11"])
                else: # automatico
                    allowed_shifts_refuerzo.extend(["R1_07-11", "R2_16-20"])
            else:
                if ref_type == 'nocturno':
                    allowed_shifts_refuerzo.extend(["R2_16-20", "T17_16-23", "N_22-05", "T10_15-22", "T12_14-22", "T13_16-22", "D2_14-22", "D3_15-23"])
                elif ref_type == 'diurno':
                    allowed_shifts_refuerzo.extend([
                        "R1_07-11", "T1_05-13", "T16_05-14", "T2_06-14", "D1_05-13",
                        "T3_07-15", "T5_09-17",
                        "T8_13-20", "T13_16-22", "D2_14-22"
                    ])
                else: # automatico
                    # Allowed to pick either 4-hour shifts OR standard 8-hour shifts
                    allowed_shifts_refuerzo.extend([
                        "R1_07-11", "R2_16-20",
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
        # SOFT: Seamless Handoffs (Relevos Continuos)
        # If someone leaves at hour h, prefer someone entering at hour h
        # Focus on critical mid-day handoffs: 13:00, 14:00, 15:00
        # =========================
        for d in DAYS:
            if d == "Dom": continue
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
            max_off = max(1, manual_off_count)
            allow_no_rest = self.emp_data[e].get('allow_no_rest', False)
            
            if e in persona_hace_libres:
                # Libres candidates: conditional constraints
                if not allow_no_rest:
                    model.Add(off_days >= 1).OnlyEnforceIf(persona_hace_libres[e])
                
                model.Add(off_days <= max_off).OnlyEnforceIf(persona_hace_libres[e])
                
                if not allow_no_rest:
                    model.Add(off_days >= 1).OnlyEnforceIf(persona_hace_libres[e].Not())
                model.Add(off_days <= max_off + 1).OnlyEnforceIf(persona_hace_libres[e].Not())
            else:
                # Not in libres system (e.g. can't do night, or is night person)
                # Simple unconditional off-day constraint
                if not allow_no_rest:
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
        if standard_mode:
            if allow_collision_q:
                # When collision Q is enabled, use moderate penalty
                # (200k < 500k coverage penalty, so solver uses Q when needed)
                q1_penalty = 200000
                q2_penalty = 200000
            else:
                # PROHIBITIVE: solver must NEVER choose Q shifts with 10+ employees.
                q1_penalty = 999999
                q2_penalty = 999999
            # In standard mode, boost PM shift rewards to give solver clear alternatives:
            t8_reward = 0        # T8_13-20: sin preferencia — el solver lo elige solo si cubre la cobertura
            t12_reward = -1200   # T12_14-22 (8h) covers h14-h21 — strong PM coverage
            t9_reward = -800     # T9_14-21 (7h) covers h14-h20
        else:
            # Short-staffed: Q shifts are needed for peak coverage (low penalty)
            q1_penalty = 50
            q2_penalty = 25
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
                # Skip forced_quebrado employees — they NEED Q shifts
                if self.emp_data[e].get('forced_quebrado', False):
                    continue
                # Skip Refuerzo — they legitimately take 4h shifts
                if self.emp_data[e].get('is_refuerzo', False):
                    continue
                for d in DAYS:
                    # =========================================================
                    # ESTRICTA ESTRUCTURA DE DOMINGO (Standard Mode)
                    # =========================================================
                    if d == "Dom":
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
                        if not allow_collision_q:
                            # Hard block Q shifts in standard mode without collision toggle
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
            
            for d in DAYS:
                for s in turno_principal[e]:
                    usa_otro = model.NewBoolVar(f"usa_otro_{e}_{d}_{s}")
                    model.AddBoolAnd([x[(e, d, s)], turno_principal[e][s].Not()]).OnlyEnforceIf(usa_otro)
                    model.AddBoolOr([x[(e, d, s)].Not(), turno_principal[e][s]]).OnlyEnforceIf(usa_otro.Not())
                    
                    penalizacion = model.NewIntVar(0, 100000, f"pen_{e}_{d}_{s}")
                    
                    exento = model.NewBoolVar(f"exento_{e}_{d}")
                    
                    conditions_exento = [es_dia_descanso_libres_cache[e][d]]
                    
                    if e in persona_hace_libres:
                        conditions_exento.append(persona_hace_libres[e])
                        
                    if primary_night and e == primary_night:
                        model.Add(exento == 1)
                    else:
                        model.AddBoolOr(conditions_exento).OnlyEnforceIf(exento)
                        model.AddBoolAnd([c.Not() for c in conditions_exento]).OnlyEnforceIf(exento.Not())
                    
                    # Massively increased penalty to force extreme schedule consistency per user request
                    model.Add(penalizacion == 900000).OnlyEnforceIf([usa_otro, exento.Not()])
                    model.Add(penalizacion == 0).OnlyEnforceIf(exento)
                    model.Add(penalizacion == 0).OnlyEnforceIf(usa_otro.Not())
                    
                    penalties.append(penalizacion)
                    
        # O3. Broken shifts Q1/Q2/Q3 — penalty depends on standard_mode
        for e in self.employees:
            for d in DAYS:
                penalties.append(q1_penalty * x[(e, d, "Q1_05-11+17-20")])
                penalties.append(q2_penalty * x[(e, d, "Q2_07-11+17-20")])
                penalties.append(q1_penalty * x[(e, d, "Q3_05-11+17-22")])  # Same penalty as Q1

        # O4. Turnos Cortos T13
        for e in self.employees:
             for d in DAYS:
                 penalties.append(200 * x[(e, d, "T13_16-22")])
                 
                 # Fuerte incentivo para usar el D4_13-22 el domingo (pedido del usuario)
                 if d == "Dom":
                     # Hard limit: D4_13-22 can only be assigned to a maximum of 1 person on Sundays
                     model.Add(sum(x[(e_iter, "Dom", "D4_13-22")] for e_iter in self.employees) <= 1)
                     penalties.append(-10000 * x[(e, d, "D4_13-22")])

        # O5. Preference for Refuerzo to take 4-hour shifts over 8-hour shifts
        if "Refuerzo" in self.employees:
            for d in DAYS:
                for s in SHIFT_NAMES:
                    # If shift is NOT OFF and NOT a 4-hour shift and NOT VAC/PERM
                    if s not in ["OFF", "VAC", "PERM", "R1_07-11", "R2_16-20"]:
                        # Much higher penalty (3000) to force Refuerzo to stay 4-hours (R1/R2)
                        # unless coverage needs are absolutely desperate.
                        penalties.append(3000 * x[("Refuerzo", d, s)])

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
            if d_t8 == "Dom": continue
            model.Add(sum(x[(e, d_t8, "T8_13-20")] for e in self.employees) <= t8_max)

        for e in self.employees:
             for d in DAYS:
                 if not standard_mode:
                     penalties.append(-1500 * x[(e, d, "T11_12-20")])
                 # Recompensar T2_06-14 el sábado para incentivar cobertura AM
                 if d == "Sáb":
                     penalties.append(-2000 * x[(e, d, "T2_06-14")])
        
        # O8. HEAVY EXTENDED SHIFTS - HARD BLOCKING
        # Heavy shifts (E1, E2, J_ 10h+) are FORBIDDEN. Q3 is the correct
        # solution for short-staffed days. When use_refuerzo=True, Refuerzo
        # handles the gap. When use_refuerzo=False, Q3 handles it.
        # If the solver can't find a solution without heavy shifts -> Infeasible.
        
        heavy_extended_shifts = ['J_07-17', 'J_08-18', 'J_09-19', 'J_10-20', 'E1_07-18', 'E2_08-19', 'T4_08-16']
        
        # HARD BLOCK: No heavy extended shifts for anyone, ever.
        for e in self.employees:
            for d in DAYS:
                for s in heavy_extended_shifts:
                    model.Add(x[(e, d, s)] == 0)
        
        for d in DAYS:
            # Reuse collision_vars for short-staffed detection on weekdays.
            # On Sunday, we detect short-staffing independently.
            if d == "Dom":
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
                if d == "Dom":
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
                    if d == "Sáb" and standard_mode:
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
                 if not standard_mode:
                     # Only penalize T4/T2 and reward T3 when short-staffed (T3 available)
                     # T2_06-14: no penalizar sábado — es el turno AM natural ese día
                     if d != "Sáb":
                         penalties.append(2000 * x[(e, d, "T2_06-14")])
                     penalties.append(-1000 * x[(e, d, "T3_07-15")])
                 # Reward T1_05-13 to ensure early morning coverage when needed
                 penalties.append(-2000 * x[(e, d, "T1_05-13")])
                 # Prefer 15-23 over 14-23
                 penalties.append(-1500 * x[(e, d, "D3_15-23")])
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
        lun_vie = [d for d in DAYS if d not in ["Sáb", "Dom"]]
        for e in self.employees:
            # Sábado y Domingo: recompensar ambos igual que antes
            for d_special in ["Sáb", "Dom"]:
                penalties.append(-1500 * x[(e, d_special, "D2_14-22")])
                penalties.append(-1500 * x[(e, d_special, "T10_15-22")])

            # Lunes a Viernes: comportamiento condicional según si es día de colisión
            for d in lun_vie:
                # D2_14-22 en día normal (no colisión) → penalizar fuerte
                d2_normal = model.NewBoolVar(f"d2_normal_{e}_{d}")
                model.AddBoolAnd([x[(e, d, "D2_14-22")], collision_vars[d].Not()]).OnlyEnforceIf(d2_normal)
                model.AddBoolOr([x[(e, d, "D2_14-22")].Not(), collision_vars[d]]).OnlyEnforceIf(d2_normal.Not())
                penalties.append(200000 * d2_normal)

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
        
        # 1. EVITAR REPETICION DE HORARIOS (General)
        # HARD CONSTRAINT: No 3-peat — if employee had shift S on day D for the last 
        # 2 consecutive weeks, BLOCK it this week.
        # SOFT PENALTY: Penalize 1-week and 2-week repeats for variety.
        
        recent_entries = history_entries[-3:] if len(history_entries) >= 3 else history_entries
        
        # Soft constraint (High Penalty): prevent 3 consecutive weeks with same shift on same day
        # If employee did S on Day D in Week-1 AND Week-2, avoid it in Week-3.
        # Cost = 10000 (Very high, but allows solution if coverage is at risk)
        if len(history_entries) >= 2:
            week_minus_1 = history_entries[-1].get("schedule", {})
            week_minus_2 = history_entries[-2].get("schedule", {})
            
            for e in self.employees:
                sched_1 = week_minus_1.get(e, {})
                sched_2 = week_minus_2.get(e, {})
                for d in DAYS:
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
        
        # Soft penalty: discourage repeating shifts from recent weeks
        for i, entry in enumerate(reversed(recent_entries)):
            weight = 500 if i == 0 else 300 if i == 1 else 100
            
            sched = entry.get("schedule", {})
            for e in self.employees:
                e_sched = sched.get(e, {})
                for d in DAYS:
                    past_shift = e_sched.get(d)
                    if past_shift and past_shift in SHIFT_NAMES and past_shift != "OFF":
                        is_repeating = x[(e, d, past_shift)]
                        penalties.append(weight * is_repeating)

        # 1.5 GLOBAL AM/PM ROTATION
        # =========================
        # If an employee worked mostly AM last week, penalize assigning them an AM
        # turno_principal this week, and vice versa. This creates organic N=2 cyclical rotation.
        if most_recent_schedule:
            AM_SHIFTS = [s for s in SHIFT_NAMES if s not in ["OFF", "VAC", "PERM"] and SHIFTS.get(s) and min(SHIFTS[s]) < 12]
            PM_SHIFTS = [s for s in SHIFT_NAMES if s not in ["OFF", "VAC", "PERM"] and SHIFTS.get(s) and min(SHIFTS[s]) >= 12]
            
            for e in self.employees:
                if e == night_person_name or self.emp_data[e].get('is_jefe_pista', False) or self.emp_data[e].get('is_refuerzo', False):
                    continue
                    
                # Calculate majority group last week
                last_sched = most_recent_schedule.get(e, {})
                am_count = 0
                pm_count = 0
                for d in DAYS:
                    s_prev = last_sched.get(d)
                    if s_prev in AM_SHIFTS: am_count += 1
                    elif s_prev in PM_SHIFTS: pm_count += 1
                
                if am_count == 0 and pm_count == 0:
                    continue
                    
                was_am_majority = am_count > pm_count  # strictly greater to avoid oscillating evenly split weeks unnecessarily 
                was_pm_majority = pm_count > am_count
                
                if e in turno_principal and turno_principal[e]:
                    ROTATION_PENALTY = 200000  # High enough to force rotation
                    for s, var in turno_principal[e].items():
                        if was_am_majority and s in AM_SHIFTS:
                            penalties.append(ROTATION_PENALTY * var)
                        elif was_pm_majority and s in PM_SHIFTS:
                            penalties.append(ROTATION_PENALTY * var)
                    
                    # Extra penalty for Women repeating majority type
                    if self.emp_data[e].get('gender') == 'F':
                        GENDER_ROTATION_PENALTY = 500000
                        for s, var in turno_principal[e].items():
                            if was_am_majority and s in AM_SHIFTS:
                                penalties.append(GENDER_ROTATION_PENALTY * var)
                            elif was_pm_majority and s in PM_SHIFTS:
                                penalties.append(GENDER_ROTATION_PENALTY * var)

        # 2. SUNDAY ROTATION (History-based queue)
        # Build rotation queue by analyzing history: who had Sunday OFF least recently goes first
        # NOTE: Night person IS eligible for Sunday rotation — the persona_hace_libres
        # covers the N_22-05 replacement when primary night is OFF on Sunday.
        # Exclude sat_dom_only employees from Sunday rotation — they always work Sunday.
        eligible = [e for e in sorted(self.employees)
                    if not self.emp_data[e].get('is_jefe_pista', False)
                    and e not in sat_dom_only]
        
        # Scan history to find each employee's last Sunday OFF (index = recency)
        last_sunday_off = {}  # employee -> history_index (higher = more recent)
        
        # We need to look at historical schedules to figure out who had Sunday OFF
        for idx, entry in enumerate(history_entries):
            sched = entry.get('schedule', {})
            for emp_name, days in sched.items():
                if isinstance(days, dict) and days.get('Dom') in ['OFF', 'VAC', 'PERM'] and emp_name in eligible:
                    last_sunday_off[emp_name] = idx  # overwrite = keep most recent
        
        # Build queue: sort by last_sunday_off ascending (least recent first)
        # Employees who NEVER had Sunday OFF get -1 → they go to the very front
        rotation_queue = sorted(eligible, key=lambda e: last_sunday_off.get(e, -1))
        
        # Detect manual Sunday OFF override from fixed_shifts
        manual_sunday_off = None
        for e in self.employees:
            fixed = self.emp_data[e].get('fixed_shifts', {})
            if fixed.get('Dom') in ['OFF', 'VAC', 'PERM'] and not self.emp_data[e].get('is_jefe_pista', False):
                manual_sunday_off = e
        
        rotation_target = rotation_queue[0] if rotation_queue else None
        
        if rotation_target:
            # Always guarantee the rotation_target their Sunday OFF (5M if denied)
            if rotation_target in x and (rotation_target, "Dom", "OFF") in x:
                penalties.append(5000000 * (x[(rotation_target, "Dom", "OFF")].Not()))

            # Build the set of employees who are "free" to take Sunday OFF without issue:
            # manual_sunday_off and rotation_target are already accounted for.
            # All remaining flex employees are divided into:
            #   - secondary_candidate: the next person in the rotation queue (low penalty ~5k)
            #     This allows a 4th Sunday OFF when coverage permits.
            #   - everyone else: penalized at 500k to avoid gratuitous extra OFFs.
            accounted = set()
            if manual_sunday_off:
                accounted.add(manual_sunday_off)
            accounted.add(rotation_target)

            remaining_queue = [e for e in rotation_queue if e not in accounted]
            secondary_candidate = remaining_queue[0] if remaining_queue else None

            for e in rotation_queue:
                if e in accounted:
                    continue
                if e == secondary_candidate:
                    # Low penalty: solver will give this person Sunday OFF when
                    # coverage allows it (i.e. the 4th libre scenario).
                    penalties.append(5000 * x[(e, "Dom", "OFF")])
                else:
                    # Strong penalty: discourage anyone else from taking Sunday OFF.
                    penalties.append(500000 * x[(e, "Dom", "OFF")])

        # O6. Sunday Rotation (Historial Compatibility)
        # Verify if they worked last Sunday.
        # We need the MOST RECENT schedule for this.
        if most_recent_schedule:
            for e in self.employees:
                last_sched = most_recent_schedule.get(e, {})
                last_sunday = last_sched.get("Dom", "OFF") # Default to OFF if missing
                
                if last_sunday != "OFF" and (e, "Dom", "OFF") in x:
                    # They worked last Sunday. Penalize working this Sunday.
                    # We want them to have OFF this Sunday.
                    is_working_sunday = model.NewBoolVar(f"working_sunday_{e}")
                    model.Add(x[(e, "Dom", "OFF")] == 0).OnlyEnforceIf(is_working_sunday)
                    model.Add(x[(e, "Dom", "OFF")] == 1).OnlyEnforceIf(is_working_sunday.Not())
                    
                    # Penalty weight.
                    penalties.append(150 * is_working_sunday)

        # Optimization
        model.Minimize(sum(penalties) + sum(peak_penalties))
        
        solver = cp_model.CpSolver()
        # Allows an external caller to specify a custom max time for the solver.
        # FIX: The model complexity is too high to prove optimality. Force early termination.
        max_t = self.config.get('max_time', 180)
        solver.parameters.max_time_in_seconds = max_t
        # Use more threads for speed.
        solver.parameters.log_search_progress = True
        
        # --- CAMBIO 3: Solver Optimizations ---
        # PORTFOLIO_SEARCH and num_search_workers allows CP-SAT to run multiple different 
        # heuristic strategies in parallel, wildly improving the schedule quality found in the 5s window.
        if hasattr(os, 'cpu_count') and os.cpu_count():
            solver.parameters.num_search_workers = os.cpu_count()
        else:
            solver.parameters.num_search_workers = 8
            
        solver.parameters.search_branching = cp_model.PORTFOLIO_SEARCH
        # Removed linearization_level=0 to allow the solver to perform better LP bounding and search deeper for better objective values
        # instead of getting stuck in local booleans.

        # Add History Hints to start search close to previous state
        if most_recent_schedule:
            for e in self.employees:
                last_sched = most_recent_schedule.get(e, {})
                for d in DAYS:
                    s_prev = last_sched.get(d, "OFF")
                    if s_prev in SHIFT_NAMES:
                        model.AddHint(x[(e, d, s_prev)], 1)
        
        solution_counter = SolutionCounter()
        # Fallback removed: fix_variables_to_their_hinted_value is too aggressive 
        # and causes Infeasible when new constraints conflict with old schedules.
        # Just let the first solve finish.
        status = solver.Solve(model, solution_counter)
        
        # Fallback removed: fix_variables_to_their_hinted_value is too aggressive 
        # and causes Infeasible when new constraints conflict with old schedules.
        # Just let the first solve finish.
        
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
             for e_check in self.employees:
                 if res[e_check].get("Dom") in ["OFF", "VAC"] and not self.emp_data[e_check].get('is_jefe_pista', False):
                     sunday_off_person = e_check
                     break
            
             rotation_target = rotation_queue[0] if rotation_queue else None
             
             return {
                 "status": "Success",
                 "schedule": res, 
                 "daily_tasks": res_tasks,
                 "metadata": {
                     "libres_person": libres_found,
                     "rotation_queue": rotation_queue,
                     "rotation_target": rotation_target,
                     "sunday_off_person": sunday_off_person,
                     "solutions_found": solution_counter.solution_count
                 }
             }
        else:
             return {"status": "Infeasible", "message": "No se pudo generar horario. Considere activar la opcion de Refuerzo para dias con falta de personal."}
