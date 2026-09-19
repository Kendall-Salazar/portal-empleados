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


class TestDoubleShifts:
    """Tests for configurable double shifts (DBL_*, pill 'DOBLE')."""

    def _make_employees(self, n=10):
        return [
            {
                "name": f"Emp{i}",
                "gender": "M",
                "can_do_night": True,
                "fixed_shifts": {},
            }
            for i in range(n)
        ]

    def test_contiguous_pair_generates_double_shift_with_union_hours(self):
        """A contiguous pair (T10_15-22 + N_22-05) generates DBL_15-05 with the correct union of hours.

        NOTE: T4_08-16 + R2_16-20 (the 12h example from the task spec) is NOT
        generated because T4_08-16 is a member of HEAVY_EXTENDED_SHIFTS, which
        the spec's own component-exclusion rule says must be excluded from
        double-shift components. This is a contradiction between the spec's
        explicit rule and its "verified" reference data -- flagged in the
        implementation report. This test uses the spec's OTHER validated
        reference combo instead (T10_15-22 + N_22-05 = 14h), which does not
        involve a HEAVY_EXTENDED_SHIFTS member.
        """
        from scheduler_engine import sync_double_shifts, SHIFTS

        sync_double_shifts({"max_double_shift_hours": 14})

        assert "DBL_15-05" in SHIFTS, f"Expected DBL_15-05 in SHIFTS, got: {[s for s in SHIFTS if s.startswith('DBL_')]}"
        assert SHIFTS["DBL_15-05"] == set(range(15, 29))

        sync_double_shifts({})  # reset to default state for other tests

    def test_noncontiguous_pair_does_not_generate_a_double(self):
        """A non-contiguous pair (e.g. T1_05-13 + T3_07-15, overlapping) never produces a DBL_* shift."""
        from scheduler_engine import sync_double_shifts, SHIFTS

        sync_double_shifts({"max_double_shift_hours": 15})

        union = set(range(5, 13)) | set(range(7, 15))  # T1_05-13 | T3_07-15
        generated_hour_sets = [v for k, v in SHIFTS.items() if k.startswith("DBL_")]
        assert union not in generated_hour_sets, (
            "Non-contiguous pair T1_05-13 + T3_07-15 should never generate a DBL_* shift"
        )

        sync_double_shifts({})  # reset

    def test_s1_touching_night_never_generates_a_double(self):
        """N_22-05 (touches 22..28) can never be the entering component (s1) of a double."""
        from scheduler_engine import sync_double_shifts, SHIFTS

        sync_double_shifts({"max_double_shift_hours": 15})

        # N_22-05 + T1_05-13 would be "contiguous" only under naive wraparound
        # logic; s1=N_22-05 touches the night range and must be rejected outright.
        forbidden_union = set(range(22, 29)) | set(range(5, 13))
        generated_hour_sets = [v for k, v in SHIFTS.items() if k.startswith("DBL_")]
        assert forbidden_union not in generated_hour_sets, (
            "A double where s1 touches night hours (N_22-05 + T1_05-13) must never be generated"
        )

        sync_double_shifts({})  # reset

    def test_max_hours_cap_is_respected(self):
        """With cap=12, no DBL_* exceeds 12h (in fact none are generated at all --
        see the note in test_contiguous_pair_generates_double_shift_with_union_hours
        about the T4_08-16/HEAVY_EXTENDED_SHIFTS contradiction). With cap=15,
        14-15h combos appear."""
        from scheduler_engine import sync_double_shifts, SHIFTS

        sync_double_shifts({"max_double_shift_hours": 12})
        dbl_12 = {k: v for k, v in SHIFTS.items() if k.startswith("DBL_")}
        for code, hours in dbl_12.items():
            assert len(hours) <= 12, f"{code} has {len(hours)}h, exceeds the 12h cap"

        sync_double_shifts({"max_double_shift_hours": 15})
        dbl_15 = {k: v for k, v in SHIFTS.items() if k.startswith("DBL_")}
        assert any(14 <= len(hours) <= 15 for hours in dbl_15.values()), (
            "Expected 14-15h combos to appear once the cap is raised to 15h"
        )
        # T1_05-13 + T8_13-20 = 05:00-20:00 (15h)
        assert "DBL_05-20" in dbl_15
        assert dbl_15["DBL_05-20"] == set(range(5, 20))
        # T10_15-22 + N_22-05 = 15:00-05:00+1d (14h)
        assert "DBL_15-05" in dbl_15
        assert dbl_15["DBL_15-05"] == set(range(15, 29))

        sync_double_shifts({})  # reset

    def test_default_max_double_shift_hours_is_12(self):
        from scheduler_engine import resolve_max_double_shift_hours

        assert resolve_max_double_shift_hours({}) == 12
        assert resolve_max_double_shift_hours(None) == 12

    def test_default_max_double_shift_hours_in_config_model(self):
        from routes.shared_models import Config

        assert Config().max_double_shift_hours == 12

    def test_double_shifts_not_auto_assigned_without_pill(self):
        """DBL_* shifts must never appear in the schedule unless the DOBLE pill is set."""
        from scheduler_engine import ShiftScheduler

        employees = self._make_employees(10)
        config = {
            "night_mode": "rotation",
            "use_history": False,
            "max_time": 30,
            "log_search_progress": False,
            # Raise the cap so DBL_* combos actually exist (default 12h yields
            # none, see the HEAVY_EXTENDED_SHIFTS note above) -- otherwise this
            # test would pass vacuously.
            "max_double_shift_hours": 14,
        }

        scheduler = ShiftScheduler(employees, config)
        result = scheduler.solve()

        assert isinstance(result, dict)
        assert result.get("status") == "Success", f"Solver returned: {result.get('status')}"

        schedule = result.get("schedule", {})
        for emp_name, days in schedule.items():
            for day, shift in days.items():
                assert not str(shift).startswith("DBL_"), (
                    f"{emp_name}/{day} got auto-assigned {shift} without the DOBLE pill"
                )

    def test_double_pill_assigns_a_dbl_shift(self):
        """With the DOBLE pill set on (employee, day), the solution assigns some DBL_* that day."""
        from scheduler_engine import ShiftScheduler

        employees = self._make_employees(10)
        employees[0]["fixed_shifts"] = {"Vie": "DOBLE"}
        config = {
            "night_mode": "rotation",
            "use_history": False,
            "max_time": 30,
            "log_search_progress": False,
            "max_double_shift_hours": 14,
        }

        scheduler = ShiftScheduler(employees, config)
        result = scheduler.solve()

        assert isinstance(result, dict)
        assert result.get("status") == "Success", f"Solver returned: {result.get('status')}"

        schedule = result.get("schedule", {})
        assigned = schedule.get("Emp0", {}).get("Vie")
        assert str(assigned).startswith("DBL_"), (
            f"Expected Emp0/Vie to be assigned a DBL_* shift, got: {assigned}"
        )
