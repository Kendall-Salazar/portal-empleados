import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from backend.scheduler_engine import ShiftScheduler

employees_data = [
    {"name": "E1", "is_jefe_pista": False},
    {"name": "E2", "is_jefe_pista": False},
]

config_data = {
    "cleaning_tasks": {
        "Lun": {"am_banos": True, "pm_banos": True, "am_tanques": True, "pm_tanques": True}
    }
}

scheduler = ShiftScheduler(employees_data, config_data, history_data=[])
scheduler.day_modes = {"Lun": "normal"}

schedule = {
    "E1": {"Lun": "MANUAL_14-22"},
    "E2": {"Lun": "07:00am - 03:00pm"}
}

tasks = scheduler.assign_tasks(schedule)

print(f"Tasks for E1 (14-22): {tasks.get('E1')}")
print(f"Tasks for E2 (07-15): {tasks.get('E2')}")
