"""Tests for employees whose whole week is covered by VAC/PERM pills.

An absence that spans every day of the week leaves no day where the mandatory
weekly rest day could be placed, so the weekly OFF+VAC balance must not demand
one. Otherwise the model is proven infeasible before the search even starts.
"""
import sys
import os

# Add backend to path
backend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'backend')
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)


def _make_employee(name, **overrides):
    emp = {
        "name": name,
        "gender": "M",
        "can_do_night": True,
        "forced_libres": False,
        "fixed_shifts": {},
    }
    emp.update(overrides)
    return emp


def _base_config(**overrides):
    config = {
        "night_mode": "rotation",
        "use_history": False,
        "max_time": 60,
        "log_search_progress": False,
    }
    config.update(overrides)
    return config


def _roster_with_absent(absence_map, size=9):
    from scheduler_engine import ShiftScheduler

    employees = [_make_employee(f"Emp{i}") for i in range(size)]
    employees.append(_make_employee("Absent", fixed_shifts=absence_map))
    return ShiftScheduler(employees, _base_config())


class TestFullWeekAbsence:
    """VAC/PERM covering all 7 days must stay feasible."""

    def test_full_week_vacation_is_feasible(self):
        """GIVEN an employee with a VAC pill on every day of the week
        WHEN the solver runs
        THEN a schedule is produced and that employee is on VAC all week."""
        from scheduler_engine import DAYS

        scheduler = _roster_with_absent({d: "VAC" for d in DAYS})
        result = scheduler.solve()

        assert result.get("status") == "Success", f"Solver returned: {result.get('status')}"
        week = result["schedule"]["Absent"]
        assert all(week[d] == "VAC" for d in DAYS), week

    def test_full_week_permiso_is_feasible(self):
        """GIVEN an employee with a PERM pill on every day of the week
        WHEN the solver runs
        THEN a schedule is produced and that employee is on PERM all week."""
        from scheduler_engine import DAYS

        scheduler = _roster_with_absent({d: "PERM" for d in DAYS})
        result = scheduler.solve()

        assert result.get("status") == "Success", f"Solver returned: {result.get('status')}"
        week = result["schedule"]["Absent"]
        assert all(week[d] == "PERM" for d in DAYS), week

    def test_full_week_mixed_vacation_and_permiso_is_feasible(self):
        """GIVEN an employee whose week is fully covered by VAC and PERM pills
        WHEN the solver runs
        THEN a schedule is produced and every day keeps its pill."""
        from scheduler_engine import DAYS

        absence_map = {d: ("VAC" if i < 5 else "PERM") for i, d in enumerate(DAYS)}
        scheduler = _roster_with_absent(absence_map)
        result = scheduler.solve()

        assert result.get("status") == "Success", f"Solver returned: {result.get('status')}"
        week = result["schedule"]["Absent"]
        assert {d: week[d] for d in DAYS} == absence_map, week

    def test_partial_week_vacation_still_gets_a_rest_day(self):
        """GIVEN an employee with VAC on 3 days and no OFF pill
        WHEN the solver runs
        THEN the remaining days still include the mandatory weekly rest day."""
        from scheduler_engine import DAYS

        vac_days = DAYS[:3]
        scheduler = _roster_with_absent({d: "VAC" for d in vac_days})
        result = scheduler.solve()

        assert result.get("status") == "Success", f"Solver returned: {result.get('status')}"
        week = result["schedule"]["Absent"]
        assert all(week[d] == "VAC" for d in vac_days), week
        assert sum(1 for d in DAYS if week[d] == "OFF") == 1, week
