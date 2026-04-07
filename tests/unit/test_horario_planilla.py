"""Tests for planilla hour rules (feriado, VAC, PERM, OFF)."""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PLAN = os.path.join(_ROOT, "planillas")
if _PLAN not in sys.path:
    sys.path.insert(0, _PLAN)

import horario_db as hd  # noqa: E402


class TestTurnoCategoria:
    def test_vac(self):
        assert hd.turno_categoria_planilla("VAC") == "VAC"
        assert hd.turno_categoria_planilla("vacaciones") == "VAC"

    def test_perm_off(self):
        assert hd.turno_categoria_planilla("PERM") == "PERM"
        assert hd.turno_categoria_planilla("OFF") == "OFF"

    def test_work_shift(self):
        assert hd.turno_categoria_planilla("T1_05-13") == "WORK"


class TestHorasBaseDia:
    def test_vac_eight_diurnas(self):
        d, n, m = hd.horas_base_dia_planilla("VAC")
        assert (d, n, m) == (hd.HORAS_VAC_DIURNAS, 0, 0)

    def test_perm_off_zero(self):
        assert hd.horas_base_dia_planilla("PERM") == (0, 0, 0)
        assert hd.horas_base_dia_planilla("OFF") == (0, 0, 0)

    def test_t1_diurnas(self):
        d, n, m = hd.horas_base_dia_planilla("T1_05-13")
        assert d + n + m == 8


class TestCapJefe:
    def test_split_extra(self):
        d, n, m, x = hd.aplicar_cap_jefe_pista(10, 0, 0, True)
        assert d == 8 and x == 2 and n == 0 and m == 0

    def test_no_jefe_no_cap(self):
        d, n, m, x = hd.aplicar_cap_jefe_pista(10, 0, 0, False)
        assert d == 10 and x == 0


class TestFeriadoCelda:
    def test_vac_zero(self):
        assert hd.feriado_celda_horas("VAC", True) == 0
        assert hd.feriado_celda_horas("VAC", False) == 0

    def test_off_perm_get_standard(self):
        assert hd.feriado_celda_horas("OFF", False) == hd.HORAS_FERIADO_SIN_LABOR
        assert hd.feriado_celda_horas("PERM", False) == hd.HORAS_FERIADO_SIN_LABOR

    def test_work_with_hours_zero_feriado(self):
        assert hd.feriado_celda_horas("WORK", True) == 0

    def test_work_without_hours_like_holiday_pay(self):
        assert hd.feriado_celda_horas("WORK", False) == hd.HORAS_FERIADO_SIN_LABOR


class TestTarifaTipoTotales:
    def test_all_zero(self):
        t, off = hd.tarifa_tipo_desde_totales_semana(0, 0, 0)
        assert t is None and off is True

    def test_dominant_diurna(self):
        t, off = hd.tarifa_tipo_desde_totales_semana(20, 5, 5)
        assert t == "diurna" and off is False
