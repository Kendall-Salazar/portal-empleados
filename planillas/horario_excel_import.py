"""
Parseo de workbooks tipo HORARIO 2026.xlsx (hojas con fila título, fechas, Colaborador + días).
Variantes: split_friday (Vie en col J) y linear_vie_jue (Vie..Jue en B–H).
"""
from __future__ import annotations

import datetime
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

import openpyxl

import horario_db

DAYS_ORDER = ("Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue")

# --- format_shift_code (mismo criterio que backend/main.py para inversa estable) ---


def _format_time_range(time_range: str) -> str:
    try:
        start_s, end_s = time_range.split("-")
        start_h = int(start_s)
        end_h = int(end_s)
        start_dt = datetime.time(start_h % 24, 0)
        end_dt = datetime.time(end_h % 24, 0)
        start_str = start_dt.strftime("%I:%M %p")
        end_str = end_dt.strftime("%I:%M %p")
        return f"{start_str} - {end_str}"
    except (ValueError, TypeError, AttributeError):
        return time_range


def format_shift_code_local(code: str) -> str:
    normalized = horario_db.normalize_manual_shift_code(code) or code
    if not normalized or normalized == "OFF":
        return "LIBRE"
    if normalized == "VAC":
        return "VACACIONES"
    if normalized == "PERM":
        return "PERMISO"
    if "+" in normalized:
        parts = normalized.split("_")
        if len(parts) > 1:
            times = parts[1].split("+")
            readable_times = [_format_time_range(t) for t in times]
            return " / ".join(readable_times)
    parts = normalized.split("_")
    if len(parts) > 1:
        return _format_time_range(parts[1])
    return normalized


def normalize_readable_key(text: str) -> str:
    if text is None:
        return ""
    s = str(text).strip()
    s = re.sub(r"\s+", " ", s)
    return s.upper()


def build_inverse_shift_map() -> Tuple[Dict[str, str], List[str]]:
    """texto_normalizado -> código; lista de advertencias por colisiones."""
    inv: Dict[str, str] = {}
    collisions: List[str] = []
    for code in sorted(horario_db.SHIFTS.keys()):
        if code in ("OFF", "VAC", "PERM"):
            continue
        readable = format_shift_code_local(code)
        key = normalize_readable_key(readable)
        if not key:
            continue
        if key in inv and inv[key] != code:
            collisions.append(f"{key}: {inv[key]} vs {code}")
        elif key not in inv:
            inv[key] = code
    inv[normalize_readable_key("LIBRE")] = "OFF"
    inv[normalize_readable_key("VACACIONES")] = "VAC"
    inv[normalize_readable_key("PERMISO")] = "PERM"
    return inv, collisions


_INVERSE_MAP_CACHE: Optional[Dict[str, str]] = None


def get_inverse_shift_map() -> Dict[str, str]:
    global _INVERSE_MAP_CACHE
    if _INVERSE_MAP_CACHE is None:
        _INVERSE_MAP_CACHE, _ = build_inverse_shift_map()
    return _INVERSE_MAP_CACHE


def readable_cell_to_code(text: Any, warnings: List[str]) -> str:
    if text is None or (isinstance(text, str) and not str(text).strip()):
        return "OFF"
    raw = str(text).strip()
    key = normalize_readable_key(raw)
    if key == "LIBRE" or key == "":
        return "OFF"
    if key == "VACACIONES":
        return "VAC"
    if key == "PERMISO":
        return "PERM"
    inv = get_inverse_shift_map()
    if key in inv:
        return inv[key]
    # Intento MANUAL_: quitar " / " por "+" para normalize_manual_shift_code estilo rangos
    manual_candidate = raw.replace(" / ", "+").replace("/", "-")
    norm = horario_db.normalize_manual_shift_code(manual_candidate)
    if norm and norm.startswith(horario_db.MANUAL_SHIFT_PREFIX):
        return norm
    warnings.append(f"Sin código para texto: {raw[:80]}")
    return "OFF"


def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def parse_day_header(cell_value: Any) -> Optional[str]:
    if cell_value is None:
        return None
    s = _strip_accents(str(cell_value).strip().lower())
    if not s:
        return None
    if s.startswith("vie"):
        return "Vie"
    if s.startswith("sab") or s.startswith("sáb"):
        return "Sáb"
    if s.startswith("dom"):
        return "Dom"
    if s.startswith("lun"):
        return "Lun"
    if s.startswith("mar"):
        return "Mar"
    if s.startswith("mie") or s.startswith("mié"):
        return "Mié"
    if s.startswith("jue"):
        return "Jue"
    return None


def _is_colaborador_a1(cell_a: Any) -> bool:
    if cell_a is None:
        return False
    t = _strip_accents(str(cell_a).strip().lower())
    return t.startswith("colaborador")


def _is_noise_header(cell_value: Any) -> bool:
    if cell_value is None:
        return True
    s = _strip_accents(str(cell_value).strip().lower())
    if not s:
        return True
    if s.startswith("formato"):
        return True
    if s.startswith("horas") and len(s) < 8:
        return True
    if s.startswith("colaborador"):
        return True
    return False


def find_header_and_column_map(ws) -> Tuple[Optional[int], Dict[int, str], List[str]]:
    """
    Retorna (header_row_1based, {col: día}, errors).
    """
    errors: List[str] = []
    max_scan = min(ws.max_row or 0, 40)
    for r in range(1, max_scan + 1):
        a = ws.cell(row=r, column=1).value
        if not _is_colaborador_a1(a):
            continue
        col_map: Dict[int, str] = {}
        max_c = min(ws.max_column or 15, 20)
        for c in range(2, max_c + 1):
            v = ws.cell(row=r, column=c).value
            if _is_noise_header(v):
                continue
            day = parse_day_header(v)
            if day:
                col_map[c] = day
        days_found = set(col_map.values())
        if len(col_map) != len(days_found):
            continue
        if days_found == set(DAYS_ORDER) and len(col_map) == len(DAYS_ORDER):
            return r, col_map, []
    errors.append("No se encontró fila con Colaborador en A y los 7 días (Vie…Jue) en columnas distintas")
    return None, {}, errors


def parse_date_cell(val: Any) -> Optional[datetime.date]:
    if val is None:
        return None
    if isinstance(val, datetime.datetime):
        return val.date()
    if isinstance(val, datetime.date):
        return val
    if isinstance(val, str):
        s = val.strip()
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.datetime.strptime(s, fmt).date()
            except ValueError:
                continue
    return None


def build_week_dates_from_row(ws, date_row: int, col_map: Dict[int, str]) -> Tuple[Dict[str, str], List[str], List[str]]:
    """week_dates DD/MM/YYYY, errors críticos, warnings."""
    errors: List[str] = []
    warnings: List[str] = []
    wd: Dict[str, str] = {}
    for col, day in col_map.items():
        val = ws.cell(row=date_row, column=col).value
        d = parse_date_cell(val)
        if d is None:
            errors.append(f"Fecha inválida columna {col} día {day}")
            continue
        wd[day] = f"{d.day:02d}/{d.month:02d}/{d.year}"
    for d in DAYS_ORDER:
        if d not in wd:
            errors.append(f"Falta fecha para {d}")
    if not errors and wd.get("Vie") and wd.get("Jue"):
        try:
            vie = datetime.datetime.strptime(wd["Vie"], "%d/%m/%Y").date()
            jue = datetime.datetime.strptime(wd["Jue"], "%d/%m/%Y").date()
            if (jue - vie).days != 6:
                warnings.append(f"Vie→Jue no son 6 días ({vie} → {jue})")
            if vie.weekday() != 4:
                warnings.append(f"La fecha en Vie no es viernes ({wd['Vie']})")
        except ValueError:
            pass
    return wd, errors, warnings


def extract_title_name(ws, header_row: int, sheet_title: str) -> str:
    if header_row > 1:
        v = ws.cell(row=1, column=1).value
        if v and isinstance(v, str):
            m = re.search(r"semana\s*(\d+)", v, re.I)
            if m:
                return f"Semana {m.group(1)}"
            s = v.strip()
            if s:
                return s[:120]
    st = (sheet_title or "").strip()
    if st.isdigit():
        return f"Semana {st}"
    return f"Semana {sheet_title}"[:120] if st else "Horario importado"


def parse_horario_sheet(ws, sheet_name: str) -> Dict[str, Any]:
    """
    Devuelve dict con keys: sheet, name_sugerido, week_dates, schedule, warnings, errors.
    """
    warnings: List[str] = []
    errors: List[str] = []
    header_row, col_map, ferr = find_header_and_column_map(ws)
    errors.extend(ferr)
    if header_row is None or not col_map:
        return {
            "sheet": sheet_name,
            "name_sugerido": extract_title_name(ws, 2, sheet_name),
            "week_dates": {},
            "schedule": {},
            "warnings": warnings,
            "errors": errors,
        }
    date_row = header_row - 1
    if date_row < 1:
        errors.append("No hay fila de fechas sobre el encabezado")
        return {
            "sheet": sheet_name,
            "name_sugerido": extract_title_name(ws, header_row, sheet_name),
            "week_dates": {},
            "schedule": {},
            "warnings": warnings,
            "errors": errors,
        }
    week_dates, date_errors, date_warn = build_week_dates_from_row(ws, date_row, col_map)
    errors.extend(date_errors)
    warnings.extend(date_warn)

    schedule: Dict[str, Dict[str, str]] = {}
    r = header_row + 1
    max_r = ws.max_row or 0
    stop_tokens = ("obligaciones", "limpieza", "formato")
    while r <= max_r:
        name_cell = ws.cell(row=r, column=1).value
        if name_cell is None or str(name_cell).strip() == "":
            r += 1
            continue
        name = str(name_cell).strip()
        low = name.lower()
        if any(low.startswith(t) for t in stop_tokens):
            break
        if _is_colaborador_a1(name_cell):
            break
        row_sched: Dict[str, str] = {}
        for col, day in col_map.items():
            cell_val = ws.cell(row=r, column=col).value
            row_sched[day] = readable_cell_to_code(cell_val, warnings)
        if any(v != "OFF" for v in row_sched.values()) or name:
            schedule[name] = {d: row_sched.get(d, "OFF") for d in DAYS_ORDER}
        r += 1

    if not schedule:
        errors.append("No se encontraron filas de empleados con datos")

    return {
        "sheet": sheet_name,
        "name_sugerido": extract_title_name(ws, header_row, sheet_name),
        "week_dates": week_dates,
        "schedule": schedule,
        "warnings": warnings,
        "errors": errors,
    }


def list_sheet_names(path: str) -> List[str]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def parse_workbook_sheets(path: str, sheet_names: List[str]) -> List[Dict[str, Any]]:
    wb = openpyxl.load_workbook(path, data_only=True)
    try:
        out = []
        for sn in sheet_names:
            if sn not in wb.sheetnames:
                out.append({
                    "sheet": sn,
                    "name_sugerido": sn,
                    "week_dates": {},
                    "schedule": {},
                    "warnings": [],
                    "errors": [f"Hoja '{sn}' no existe en el archivo"],
                })
                continue
            out.append(parse_horario_sheet(wb[sn], sn))
        return out
    finally:
        wb.close()
