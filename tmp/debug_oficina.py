import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from backend.scheduler_engine import ShiftScheduler

s = ShiftScheduler([], {})

s.day_modes = {"Lun": "normal"}
s.config = {"cleaning_tasks": {"Lun": {"am_banos": True}}}

d = "Lun"
print("is_weekday_like_mode:", s.day_modes.get(d))
from backend.scheduler_engine import is_weekday_like_mode
print("is_weekday_like_mode(normal):", is_weekday_like_mode(s.day_modes.get(d)))
