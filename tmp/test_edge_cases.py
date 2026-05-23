import sys, os
sys.path.insert(0, os.path.abspath('.'))
from backend.scheduler_engine import ShiftScheduler

# Scenario: only ONE 5am worker available — should NOT get double-assigned
employees_data = [
    {"name": "Solo",   "is_jefe_pista": False},
    {"name": "Tarde",  "is_jefe_pista": False},
]
config_data = {"cleaning_tasks": {"Lun": {"am_banos": True, "am_tanques": True, "pm_banos": True, "pm_tanques": True}}}
scheduler = ShiftScheduler(employees_data, config_data, history_data=[])
scheduler.day_modes = {}
schedule = {"Solo": {"Lun": "T1_05-13"}, "Tarde": {"Lun": "D2_14-22"}}
tasks = scheduler.assign_tasks(schedule)
print("=== Solo una persona a las 5am (no debe tener doble asignacion) ===")
for e, t in tasks.items():
    print(f"  {e}: {t.get('Lun')}")

# Scenario: Sabado with 6am worker
employees_data2 = [
    {"name": "Seis",   "is_jefe_pista": False},
    {"name": "Tarde2", "is_jefe_pista": False},
]
config_data2 = {"cleaning_tasks": {"Sab": {"am_banos": True, "am_tanques": True, "pm_banos": True, "pm_tanques": True}}}
scheduler2 = ShiftScheduler(employees_data2, config_data2, history_data=[])
scheduler2.day_modes = {}
schedule2 = {"Seis": {"Sáb": "T2_06-14"}, "Tarde2": {"Sáb": "D2_14-22"}}
tasks2 = scheduler2.assign_tasks(schedule2)
print("\n=== Sabado con alguien a las 6am (debe recibir banos AM) ===")
for e, t in tasks2.items():
    print(f"  {e}: {t.get('Sáb')}")
