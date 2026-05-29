"""Unit tests for scheduler_engine module."""
import sys
import os

# Add backend to path
backend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'backend')
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)


class TestSchedulerImports:
    """Test that the scheduler module can be imported."""

    def test_import_scheduler_engine(self):
        """Test that scheduler_engine can be imported."""
        import scheduler_engine
        assert scheduler_engine is not None

    def test_import_shift_scheduler_class(self):
        """Test that ShiftScheduler class exists."""
        from scheduler_engine import ShiftScheduler
        assert ShiftScheduler is not None

    def test_import_constants(self):
        """Test that constants are defined."""
        from scheduler_engine import DAYS, HOURS, SHIFTS
        assert DAYS == ["Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue"]
        assert 5 in HOURS
        assert len(HOURS) > 0


class TestSchedulerInstantiation:
    """Test ShiftScheduler instantiation with minimal data."""

    def test_create_scheduler_with_empty_employees(self):
        """Test that ShiftScheduler can be created with empty employee list."""
        from scheduler_engine import ShiftScheduler
        
        employees = []
        config = {
            "night_mode": "rotation",
            "use_history": False,
        }
        
        scheduler = ShiftScheduler(employees, config)
        assert scheduler is not None

    def test_create_scheduler_with_single_employee(self):
        """Test scheduler with one employee."""
        from scheduler_engine import ShiftScheduler
        
        employees = [
            {
                "name": "Test Employee",
                "gender": "M",
                "can_do_night": True,
                "fixed_shifts": {},
            }
        ]
        config = {
            "night_mode": "rotation",
            "use_history": False,
        }
        
        scheduler = ShiftScheduler(employees, config)
        assert scheduler is not None


class TestSchedulerSolve:
    """Test scheduler solve method."""

    def test_solve_returns_dict(self):
        """Test that solve returns a dictionary."""
        from scheduler_engine import ShiftScheduler
        
        employees = [
            {
                "name": "Test Employee",
                "gender": "M",
                "can_do_night": True,
                "fixed_shifts": {},
            }
        ]
        config = {
            "night_mode": "rotation",
            "use_history": False,
        }
        
        scheduler = ShiftScheduler(employees, config)
        result = scheduler.solve()
        
        assert isinstance(result, dict)

    def test_solve_with_history(self):
        """Test scheduler with history data."""
        from scheduler_engine import ShiftScheduler
        
        employees = [
            {
                "name": "Test Employee",
                "gender": "M",
                "can_do_night": True,
                "fixed_shifts": {},
            }
        ]
        
        history = [
            {
                "name": "week_1",
                "schedule": {
                    "Test Employee": {
                        "Vie": "T1_05-13",
                        "Sáb": "OFF",
                        "Dom": "OFF",
                        "Lun": "T1_05-13",
                        "Mar": "OFF",
                        "Mié": "OFF",
                        "Jue": "T1_05-13",
                    }
                },
                "daily_tasks": {},
            }
        ]
        
        config = {
            "night_mode": "rotation",
            "use_history": True,
        }
        
        scheduler = ShiftScheduler(employees, config, history_data=history)
        result = scheduler.solve()
        
        assert isinstance(result, dict)


class TestConsistencyPenalty:
    """Test that CONSISTENCY_PENALTY=500k enforces near-hard turno_principal consistency."""

    def _make_employee(self, name, forced_libres=False):
        return {
            "name": name,
            "gender": "M",
            "can_do_night": True,
            "forced_libres": forced_libres,
            "fixed_shifts": {},
        }

    def test_consistency_penalty_value_is_500k(self):
        """RED: Verify CONSISTENCY_PENALTY constant was raised to 500000."""
        from scheduler_engine import CONSISTENCY_PENALTY
        assert CONSISTENCY_PENALTY == 500000, (
            f"Expected 500000, got {CONSISTENCY_PENALTY}"
        )

    def test_solver_assigns_consistent_turno_principal_when_feasible(self):
        """GREEN: With 500k penalty, solver reports the penalty and mostly maintains consistency.
        
        GIVEN enough employees for feasible coverage
        WHEN the solver runs
        THEN the metadata should report consistency_penalty=500000
        AND most employees should have consistent shift types
        """
        from scheduler_engine import ShiftScheduler, SHIFTS

        # Need >= 10 employees for standard_mode feasibility
        employees = [
            self._make_employee(f"Emp{i}")
            for i in range(10)
        ]
        config = {
            "night_mode": "rotation",
            "use_history": False,
            "max_time": 30,
            "log_search_progress": False,
        }

        scheduler = ShiftScheduler(employees, config)
        result = scheduler.solve()

        assert isinstance(result, dict)
        assert result.get("status") == "Success", f"Solver returned: {result.get('status')}"

        # Metadata MUST report the penalty value
        metadata = result.get("metadata", {})
        assert metadata.get("consistency_penalty") == 500000, (
            f"Expected consistency_penalty=500000 in metadata, got {metadata.get('consistency_penalty')}"
        )

        # Behavioral check: most employees should have consistent AM/PM shifts
        # (coverage may force some exceptions — spec allows this)
        schedule = result.get("schedule", {})
        consistent_count = 0
        total_with_multiple = 0
        for emp_name in [f"Emp{i}" for i in range(10)]:
            emp_shifts = schedule.get(emp_name, {})
            working_shifts = [
                s for s in emp_shifts.values()
                if s not in ("OFF", "VAC", "PERM", "N_22-05")
            ]
            if len(working_shifts) > 1:
                total_with_multiple += 1
                is_consistent = True
                first = working_shifts[0]
                for s in working_shifts[1:]:
                    first_is_am = min(SHIFTS.get(first, {0})) < 12
                    s_is_am = min(SHIFTS.get(s, {0})) < 12
                    if first_is_am != s_is_am:
                        is_consistent = False
                        break
                if is_consistent:
                    consistent_count += 1

        # At least 50% of employees with multiple working shifts should be consistent
        if total_with_multiple > 0:
            ratio = consistent_count / total_with_multiple
            assert ratio >= 0.5, (
                f"Only {consistent_count}/{total_with_multiple} ({ratio:.0%}) employees are consistent"
            )


class TestStevenExemption:
    """Test that Steven (forced_libres) is exempt from consistency penalty."""

    def test_forced_libres_exempt_from_consistency(self):
        """GREEN: Employee with forced_libres=True should be listed in consistency_exempt.
        
        GIVEN Steven has forced_libres=True among enough employees for feasibility
        WHEN the solver runs
        THEN Steven should be listed in consistency_exempt metadata
        """
        from scheduler_engine import ShiftScheduler

        # 10 employees total — Steven replaces one regular employee
        employees = [
            {
                "name": "Steven",
                "gender": "M",
                "can_do_night": True,
                "forced_libres": True,
                "fixed_shifts": {},
            },
        ]
        for i in range(9):
            employees.append({
                "name": f"Emp{i}",
                "gender": "M",
                "can_do_night": True,
                "forced_libres": False,
                "fixed_shifts": {},
            })
        config = {
            "night_mode": "rotation",
            "use_history": False,
            "max_time": 30,
            "log_search_progress": False,
        }

        scheduler = ShiftScheduler(employees, config)
        result = scheduler.solve()

        assert isinstance(result, dict)
        assert result.get("status") == "Success", f"Solver returned: {result.get('status')}"

        # Steven should be listed as exempt in metadata
        metadata = result.get("metadata", {})
        exempt_list = metadata.get("consistency_exempt", [])
        assert "Steven" in exempt_list, (
            f"Steven should be in consistency_exempt list, got {exempt_list}"
        )
