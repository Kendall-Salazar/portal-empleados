"""Unit tests for lexicographic (tiered) objective optimization."""
import sys
import os

# Add backend to path
backend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'backend')
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)


def _make_employee(name, forced_libres=False):
    return {
        "name": name,
        "gender": "M",
        "can_do_night": True,
        "forced_libres": forced_libres,
        "fixed_shifts": {},
    }


def _base_config(**overrides):
    config = {
        "night_mode": "rotation",
        "use_history": False,
        "max_time": 30,
        "log_search_progress": False,
    }
    config.update(overrides)
    return config


class TestLexicographicSolve:
    """Lexicographic mode solves tier by tier and reports each tier."""

    def test_lexicographic_is_default_and_reports_tiers(self):
        """GIVEN a feasible roster with default config
        WHEN the solver runs
        THEN it succeeds and metadata reports the per-tier objective values."""
        from scheduler_engine import ShiftScheduler

        employees = [_make_employee(f"Emp{i}") for i in range(10)]
        scheduler = ShiftScheduler(employees, _base_config())
        result = scheduler.solve()

        assert result.get("status") == "Success", f"Solver returned: {result.get('status')}"
        lex_report = result.get("metadata", {}).get("lexicographic")
        assert isinstance(lex_report, list) and len(lex_report) >= 1, (
            f"Expected non-empty lexicographic tier report, got {lex_report!r}"
        )
        for entry in lex_report:
            assert "tier" in entry and "objective" in entry and "status" in entry
            assert isinstance(entry["objective"], int)
        tier_names = [entry["tier"] for entry in lex_report]
        assert tier_names == sorted(
            tier_names, key=["critical", "major", "minor"].index
        ), f"Tiers out of priority order: {tier_names}"

    def test_legacy_single_objective_mode_still_works(self):
        """GIVEN lexicographic explicitly disabled
        WHEN the solver runs
        THEN it succeeds via the single weighted-sum objective and reports no tiers."""
        from scheduler_engine import ShiftScheduler

        employees = [_make_employee(f"Emp{i}") for i in range(10)]
        # 60s: the soft rest-shortfall terms enlarge the model, and the legacy
        # single-objective solve gets no lexicographic warm-start help.
        scheduler = ShiftScheduler(employees, _base_config(lexicographic=False, max_time=60))
        result = scheduler.solve()

        assert result.get("status") == "Success", f"Solver returned: {result.get('status')}"
        assert result.get("metadata", {}).get("lexicographic") is None

    def test_forced_libres_respected_in_lexicographic_mode(self):
        """GIVEN one employee forced into the libres role
        WHEN the solver runs in lexicographic mode
        THEN exactly that employee holds the role."""
        from scheduler_engine import ShiftScheduler

        employees = [_make_employee(f"Emp{i}", forced_libres=(i == 0)) for i in range(10)]
        scheduler = ShiftScheduler(employees, _base_config())
        result = scheduler.solve()

        assert result.get("status") == "Success", f"Solver returned: {result.get('status')}"
        assert result.get("metadata", {}).get("libres_person") == "Emp0"
