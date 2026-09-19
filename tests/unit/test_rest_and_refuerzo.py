"""Tests for the 8h rest floor with soft shortfall and the daytime-only refuerzo pool."""
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
        "max_time": 30,
        "log_search_progress": False,
    }
    config.update(overrides)
    return config


class TestRestFloor:
    """Hard rest floor is 8h; shortening below the 12h target is solver-decided."""

    def test_rest_floor_is_8_and_no_gap_below_it(self):
        """GIVEN a feasible roster
        WHEN the solver runs
        THEN the floor reported is 8h and no rest gap in the schedule is below it."""
        from scheduler_engine import ShiftScheduler

        employees = [_make_employee(f"Emp{i}") for i in range(10)]
        scheduler = ShiftScheduler(employees, _base_config())
        result = scheduler.solve()

        assert result.get("status") == "Success", f"Solver returned: {result.get('status')}"
        md = result.get("metadata", {})
        assert md.get("min_rest_hours_floor") == 8
        assert md.get("min_rest_hours_target") == 12
        applied = md.get("min_rest_hours_applied")
        assert applied is not None and 8 <= applied <= 12, f"applied={applied}"

        rest_report = md.get("rest_between_shifts", {})
        for emp, info in (rest_report.get("per_employee") or {}).items():
            if info.get("skipped"):
                continue
            for gap in info.get("gaps", []):
                assert gap["hours"] >= 8, (
                    f"{emp}: rest of {gap['hours']}h between {gap['from']} and "
                    f"{gap['to']} is below the 8h hard floor"
                )


class TestRefuerzoDiurno:
    """A daytime-only refuerzo must never receive afternoon/evening shifts."""

    def test_diurno_refuerzo_gets_only_daytime_shifts(self):
        """GIVEN a short-staffed roster with a daytime-only refuerzo
        WHEN the solver runs
        THEN every working shift assigned to the refuerzo starts before 13h."""
        from scheduler_engine import ShiftScheduler, SHIFTS

        employees = [_make_employee(f"Emp{i}") for i in range(8)]
        config = _base_config(
            use_refuerzo=True,
            refuerzo_type="diurno",
            refuerzo_nombre="Refuerzo",
            max_time=90,  # short-staffed models need more budget than the default test 30s
        )
        scheduler = ShiftScheduler(employees, config)
        result = scheduler.solve()

        assert result.get("status") == "Success", f"Solver returned: {result.get('status')}"
        ref_schedule = result.get("schedule", {}).get("Refuerzo", {})
        assert ref_schedule, "Refuerzo missing from the schedule"
        for day, shift in ref_schedule.items():
            if shift in ("OFF", "VAC", "PERM"):
                continue
            hours = SHIFTS.get(shift) or set()
            assert hours and min(hours) < 13, (
                f"Refuerzo diurno got non-daytime shift {shift} on {day}"
            )
