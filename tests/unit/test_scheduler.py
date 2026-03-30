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
