"""Tests for merge_partial_schedules (horario parcial: días bloqueados vs activos)."""
import sys
import os

_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_backend = os.path.join(_root, "backend")
if _backend not in sys.path:
    sys.path.insert(0, _backend)

from routes.horarios import merge_partial_schedules


class TestMergePartialSchedules:
    """Mié y Jue activos con Vie–Mar bloqueados (locked_days)."""

    def test_locked_days_keep_base_active_use_solver(self):
        base = {
            "Ana": {
                "Vie": "T1_05-13",
                "Sáb": "OFF",
                "Dom": "OFF",
                "Lun": "T1_05-13",
                "Mar": "T1_05-13",
                "Mié": "OLD_MIE",
                "Jue": "OLD_JUE",
            },
            "Luis": {
                "Vie": "OFF",
                "Sáb": "OFF",
                "Dom": "OFF",
                "Lun": "OFF",
                "Mar": "OFF",
                "Mié": "X",
                "Jue": "Y",
            },
        }
        solver = {
            "Ana": {"Mié": "NEW_MIE", "Jue": "NEW_JUE"},
            "Luis": {"Mié": "LM", "Jue": "LJ"},
        }
        locked = ["Vie", "Sáb", "Dom", "Lun", "Mar"]
        out = merge_partial_schedules(base, solver, locked, departed_last_day=None)

        assert out["Ana"]["Vie"] == "T1_05-13"
        assert out["Ana"]["Mar"] == "T1_05-13"
        assert out["Ana"]["Mié"] == "NEW_MIE"
        assert out["Ana"]["Jue"] == "NEW_JUE"
        assert out["Luis"]["Mié"] == "LM"
        assert out["Luis"]["Jue"] == "LJ"
        assert "Vie" in out["Luis"] and out["Luis"]["Vie"] == "OFF"

    def test_departed_after_last_day_active_days_empty(self):
        base = {
            "Pedro": {
                "Vie": "A",
                "Sáb": "B",
                "Dom": "C",
                "Lun": "D",
                "Mar": "E",
                "Mié": "SHOULD_NOT_APPEAR",
                "Jue": "SHOULD_NOT_APPEAR",
            }
        }
        solver = {"Pedro": {"Mié": "SOLV_M", "Jue": "SOLV_J"}}
        locked = ["Vie", "Sáb", "Dom", "Lun", "Mar"]
        out = merge_partial_schedules(
            base,
            solver,
            locked,
            departed_last_day={"Pedro": "Mar"},
        )
        assert out["Pedro"]["Mar"] == "E"
        assert "Mié" not in out["Pedro"]
        assert "Jue" not in out["Pedro"]

    def test_solver_only_employee_added_with_active_days(self):
        base = {"SoloBase": {"Vie": "Z"}}
        solver = {"Nuevo": {"Mié": "NM", "Jue": "NJ", "Vie": "IGNORED"}}
        locked = ["Vie", "Sáb", "Dom", "Lun", "Mar"]
        out = merge_partial_schedules(base, solver, locked, None)
        assert "Nuevo" in out
        assert out["Nuevo"] == {"Mié": "NM", "Jue": "NJ"}
