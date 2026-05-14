"""
Layout dinámico de bloques por empleado en la planilla semanal (filas de extras condicionales).
"""
from __future__ import annotations

from typing import Dict, FrozenSet, List, Optional, Tuple

import horario_db as hd

DIAS_SEMANA = hd.DIAS_SEMANA_PLANILLA

# Claves internas para tipos de fila de horas extraordinarias
EXTRA_KEYS_ORDER: Tuple[str, ...] = ("ED", "EM", "EN")
EXTRA_LABELS = {
    "ED": "Hrs. Extraordinarias Diurnas",
    "EM": "Hrs. Extraordinarias Mixtas",
    "EN": "Hrs. Extraordinarias Nocturnas",
}
ALL_EXTRAS: FrozenSet[str] = frozenset(EXTRA_KEYS_ORDER)


def extras_needed_from_schedule_week(sched: Optional[Dict[str, str]]) -> FrozenSet[str]:
    """
    A partir del dict de turnos de la semana (Vie..Jue), indica qué tipos de
    horas extraordinarias pueden aparecer (> 0 en algún día tras split 8/7/6).
    """
    if not sched:
        return ALL_EXTRAS
    need: set = set()
    for dia in DIAS_SEMANA:
        turno = sched.get(dia, "OFF")
        h_d, h_n, h_m = hd.horas_base_dia_planilla(turno)
        _od, _om, _on, ed, em, en = hd.split_jornada_ordinaria_extra(h_d, h_n, h_m)
        if ed > 0:
            need.add("ED")
        if em > 0:
            need.add("EM")
        if en > 0:
            need.add("EN")
    return frozenset(need) if need else frozenset()


def extras_set_for_employee(
    emp_name: str,
    horario_preview: Optional[Dict[str, Dict[str, str]]],
) -> FrozenSet[str]:
    """Si no hay preview o el empleado no está, se asumen las tres filas (compat)."""
    if not horario_preview:
        return ALL_EXTRAS
    sched = horario_preview.get(emp_name) or horario_preview.get(str(emp_name).strip())
    if not sched:
        return ALL_EXTRAS
    return extras_needed_from_schedule_week(sched)


def scan_jornada_block_rows(ws, start_row: int) -> Dict[str, Optional[int]]:
    """
    start_row = fila donde col B es 'Hrs. Diurnas'.
    Devuelve rd, rm, rn, ed, em, en (opcionales), fer (opcional).
    Termina al siguiente bloque (otra 'Hrs. Diurnas' en col B) o fila TOTAL / vacío raro.
    """
    out: Dict[str, Optional[int]] = {
        "rd": start_row,
        "rm": start_row + 1,
        "rn": start_row + 2,
        "ed": None,
        "em": None,
        "en": None,
        "fer": None,
    }
    r = start_row + 3
    max_r = start_row + 22
    while r <= max_r:
        b = ws.cell(row=r, column=2).value
        bs = str(b or "").strip()
        a1 = ws.cell(row=r, column=1).value
        a1s = str(a1 or "").strip()
        if r > start_row and bs == "Hrs. Diurnas":
            break
        if a1s.startswith("TOTAL") and "GRAN" not in a1s.upper():
            break
        if "Extraordinarias Diurnas" in bs:
            out["ed"] = r
        elif "Extraordinarias Mixtas" in bs:
            out["em"] = r
        elif "Extraordinarias Nocturnas" in bs:
            out["en"] = r
        elif "Feriado" in bs:
            out["fer"] = r
            break
        r += 1
    return out


def jornada_block_last_row(scan: Dict[str, Optional[int]]) -> int:
    """Última fila del bloque (feriado o última extra o rn)."""
    if scan.get("fer"):
        return int(scan["fer"])
    for k in ("en", "em", "ed"):
        if scan.get(k):
            return int(scan[k])
    return int(scan["rn"])


def j_sum_ord_plus_extra(base_row: int, extra_key: str, row_by_extra: Dict[str, int]) -> str:
    """Expresión Excel J_fila + J_extra si existe fila extra de ese tipo."""
    s = f"J{base_row}"
    if extra_key in row_by_extra:
        s += f"+J{row_by_extra[extra_key]}"
    return s


def feriado_monto_formula(
    holiday_row: int,
    rd: int,
    rm: int,
    rn: int,
    row_by_extra: Dict[str, int],
) -> str:
    """Fórmula L de recargo feriado (tarifa dominante × horas feriado en J)."""
    jd = j_sum_ord_plus_extra(rd, "ED", row_by_extra)
    jm = j_sum_ord_plus_extra(rm, "EM", row_by_extra)
    jn = j_sum_ord_plus_extra(rn, "EN", row_by_extra)
    return (
        f"=IFERROR(ROUND(J{holiday_row}*IF(MAX({jd},{jm},{jn})=0,$F$3,"
        f"IF(AND({jd}>={jm},{jd}>={jn}),$D$3,"
        f"IF(AND({jm}>={jd},{jm}>={jn}),$F$3,$H$3))),2),0)"
    )
