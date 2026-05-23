import sys, os
sys.path.insert(0, os.path.abspath('.'))
from backend.scheduler_engine import ShiftScheduler

# Two people starting at 5am — one gets tanques, the other gets banos
employees_data = [
    {"name": "Ana",   "is_jefe_pista": False},
    {"name": "Maria", "is_jefe_pista": False},
    {"name": "Juan",  "is_jefe_pista": False},  # starts at 3pm, not in am_pool
]

config_data = {
    "cleaning_tasks": {
        "Lun": {"am_banos": True, "pm_banos": True, "am_tanques": True, "pm_tanques": True},
        "Jue": {"am_banos": True, "pm_banos": True, "am_tanques": True, "pm_tanques": True},
        "Mar": {"am_banos": True, "pm_banos": True, "am_tanques": True, "pm_tanques": True},
    }
}

scheduler = ShiftScheduler(employees_data, config_data, history_data=[])
scheduler.day_modes = {}  # normal mode

schedule = {
    "Ana":   {"Lun": "T1_05-13", "Mar": "T1_05-13", "Jue": "T1_05-13"},
    "Maria": {"Lun": "D1_05-13", "Mar": "D1_05-13", "Jue": "D1_05-13"},
    "Juan":  {"Lun": "D2_14-22", "Mar": "D2_14-22", "Jue": "D2_14-22"},
}

tasks = scheduler.assign_tasks(schedule)

print("=== Lunes (debe haber Oficina+Basureros+Baños) ===")
for emp, t in tasks.items():
    if t.get("Lun"):
        print(f"  {emp}: {t['Lun']}")

print("=== Martes (solo Baños) ===")
for emp, t in tasks.items():
    if t.get("Mar"):
        print(f"  {emp}: {t['Mar']}")

print("=== Jueves (debe haber Oficina+Basureros+Baños) ===")
for emp, t in tasks.items():
    if t.get("Jue"):
        print(f"  {emp}: {t['Jue']}")
