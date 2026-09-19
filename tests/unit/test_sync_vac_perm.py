"""Tests for sync_vac_perm_to_fixed_shifts pill provenance.

The sync bridges the payroll tables (vacaciones / permisos) into the scheduler's
turnos_fijos pills. It must only remove pills it created itself: a VAC/PERM pill
placed by hand in the schedule grid has no payroll row behind it and must survive.
"""
import importlib
import json
import os
import sys
from datetime import datetime

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PLAN = os.path.join(_ROOT, "planillas")
if _PLAN not in sys.path:
    sys.path.insert(0, _PLAN)

import database as db  # noqa: E402

# Semana laboral viernes -> jueves
VIERNES = "2026-07-17"
SABADO = "2026-07-18"
JUEVES = "2026-07-23"
SAB = "Sáb"


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point database.py at a throwaway SQLite file with one employee."""
    monkeypatch.setattr(db, "DB_FILE", str(tmp_path / "test.db"))
    db.init_db()
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO empleados (nombre, tipo_pago, activo) VALUES (?, 'tarjeta', 1)",
        ("Ileana",),
    )
    conn.execute("INSERT INTO horario_empleados (nombre) VALUES (?)", ("Ileana",))
    conn.commit()
    conn.close()
    return db


def _set_pills(pills):
    conn = db.get_conn()
    conn.execute(
        "UPDATE horario_empleados SET turnos_fijos=? WHERE nombre='Ileana'",
        (json.dumps(pills, ensure_ascii=False),),
    )
    conn.commit()
    conn.close()


def _add_permiso(fecha, dia_semana):
    conn = db.get_conn()
    eid = conn.execute("SELECT id FROM empleados WHERE nombre='Ileana'").fetchone()[0]
    conn.execute(
        "INSERT INTO permisos (empleado_id, fecha, dia_semana, motivo, anio, "
        "descontado_de_vacaciones, fecha_registro, horas) VALUES (?,?,?,?,?,0,?,?)",
        (eid, fecha, dia_semana, "Permiso personal", 2026, datetime.now().isoformat(), 8),
    )
    conn.commit()
    conn.close()


def _clear_permisos():
    conn = db.get_conn()
    conn.execute("DELETE FROM permisos")
    conn.commit()
    conn.close()


def _sync():
    return db.sync_vac_perm_to_fixed_shifts("Ileana", VIERNES, JUEVES)


class TestManualPillsSurvive:
    def test_manual_perm_survives_when_no_payroll_row(self, temp_db):
        """The reported bug: a hand-placed PERM pill was wiped on every solve."""
        _set_pills({"Vie": "OFF", SAB: "PERM"})
        result = _sync()
        assert result.get(SAB) == "PERM"

    def test_manual_vac_survives_when_no_payroll_row(self, temp_db):
        _set_pills({SAB: "VAC"})
        assert _sync().get(SAB) == "VAC"

    def test_manual_off_is_untouched(self, temp_db):
        _set_pills({"Vie": "OFF", SAB: "OFF"})
        result = _sync()
        assert result.get("Vie") == "OFF"
        assert result.get(SAB) == "OFF"

    def test_manual_perm_survives_repeated_syncs(self, temp_db):
        """Every 'Generar' click runs the sync; the pill must not decay."""
        _set_pills({SAB: "PERM"})
        for _ in range(3):
            _sync()
        assert _sync().get(SAB) == "PERM"


class TestPayrollDrivenPills:
    def test_sync_adds_perm_from_payroll(self, temp_db):
        _set_pills({})
        _add_permiso(SABADO, SAB)
        assert _sync().get(SAB) == "PERM"

    def test_sync_removes_its_own_pill_when_payroll_row_is_deleted(self, temp_db):
        """A pill the sync created must disappear once the permit is cancelled."""
        _set_pills({})
        _add_permiso(SABADO, SAB)
        assert _sync().get(SAB) == "PERM"

        _clear_permisos()
        assert SAB not in _sync()

    def test_sync_does_not_strip_other_days(self, temp_db):
        _set_pills({"Lun": "T1_05-13", "Mar": "OFF"})
        _add_permiso(SABADO, SAB)
        result = _sync()
        assert result.get("Lun") == "T1_05-13"
        assert result.get("Mar") == "OFF"
        assert result.get(SAB) == "PERM"
