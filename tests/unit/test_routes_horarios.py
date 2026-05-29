"""Unit tests for routes/horarios module — individual history endpoint."""
import sys
import os

# Add backend to path
backend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'backend')
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)


class TestClassifyShiftType:
    """Test the _classify_shift_type helper function."""

    def test_matutino_shifts(self):
        """Shifts starting before 12:00 are matutino."""
        from routes.horarios import _classify_shift_type
        assert _classify_shift_type("T1_05-13") == "matutino"
        assert _classify_shift_type("T3_07-15") == "matutino"
        assert _classify_shift_type("T4_08-16") == "matutino"

    def test_vespertino_shifts(self):
        """Shifts starting at 12:00 or later are vespertino."""
        from routes.horarios import _classify_shift_type
        assert _classify_shift_type("T11_12-20") == "vespertino"
        assert _classify_shift_type("T8_13-20") == "vespertino"
        assert _classify_shift_type("T10_15-22") == "vespertino"

    def test_nocturno_shift(self):
        """N_22-05 is nocturno."""
        from routes.horarios import _classify_shift_type
        assert _classify_shift_type("N_22-05") == "nocturno"

    def test_libre_shifts(self):
        """OFF, VAC, PERM are libre."""
        from routes.horarios import _classify_shift_type
        assert _classify_shift_type("OFF") == "libre"
        assert _classify_shift_type("VAC") == "libre"
        assert _classify_shift_type("PERM") == "libre"
        assert _classify_shift_type("") == "libre"


class TestComputeDominantType:
    """Test the _compute_dominant_type helper function."""

    def test_clear_dominant(self):
        """When one type has more counts, it's dominant."""
        from routes.horarios import _compute_dominant_type
        counts = {"matutino": 4, "vespertino": 1, "nocturno": 0, "libre": 2}
        assert _compute_dominant_type(counts) == "matutino"

    def test_tie_breaks_by_order(self):
        """Tie breaks by type order: matutino > vespertino > nocturno > libre."""
        from routes.horarios import _compute_dominant_type
        counts = {"matutino": 2, "vespertino": 2, "nocturno": 0, "libre": 0}
        assert _compute_dominant_type(counts) == "matutino"

    def test_empty_week_is_libre(self):
        """All zeros → libre."""
        from routes.horarios import _compute_dominant_type
        counts = {"matutino": 0, "vespertino": 0, "nocturno": 0, "libre": 0}
        assert _compute_dominant_type(counts) == "libre"

    def test_vespertino_dominant(self):
        """Vespertino can be dominant."""
        from routes.horarios import _compute_dominant_type
        counts = {"matutino": 1, "vespertino": 4, "nocturno": 0, "libre": 2}
        assert _compute_dominant_type(counts) == "vespertino"
