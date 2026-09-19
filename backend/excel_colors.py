"""Resolución de colores por empleado para el export Excel de un solo horario.

Modulo puro (sin dependencias de base de datos ni de FastAPI) para poder
testearlo de forma aislada. Combina tres fuentes de color, en orden de
prioridad:

1. Colores personalizados guardados por el usuario (clave = nombre EXACTO
   del empleado, tal como aparece en horario_empleados/empleados).
2. Colores por defecto extraidos del libro maestro "HORARIO 2026.xlsx",
   indexados por el PRIMER nombre (ej. "Jeison"). Como el horario guarda
   nombres completos ("Jeison Aleman Tijerino"), se hace un match "empieza
   con <clave por defecto> " (normalizado sin acentos/mayusculas) cuando no
   hay coincidencia exacta.
3. Paleta secuencial de respaldo para cualquier nombre que no matchee nada.

Este modulo se usa SOLO desde el endpoint GET /api/export_excel (y desde el
router backend/routes/excel_colors.py). No afecta el export de carpetas, el
export de imagen ni el render de la tabla en la app.
"""
import unicodedata
from typing import Dict, List, Optional

# Colores extraidos del libro maestro "HORARIO 2026.xlsx" (bg / font, hex sin '#').
# Clave = PRIMER nombre del empleado tal como aparece en el libro maestro.
EXCEL_COLOR_DEFAULTS: Dict[str, Dict[str, str]] = {
    "Antonio": {"bg": "548235", "font": "FFFFFF"},
    "Fabian": {"bg": "4D93D9", "font": "FFFFFF"},
    "Ileana": {"bg": "61CBF3", "font": "000000"},
    "Jeison": {"bg": "663300", "font": "FFFFFF"},
    "Jensy": {"bg": "D86DCD", "font": "000000"},
    "Juan David": {"bg": "BF9000", "font": "FFFFFF"},
    "Maikel": {"bg": "8ED973", "font": "000000"},
    "Natanael": {"bg": "FF0000", "font": "FFFFFF"},
    "Randall": {"bg": "BFBFBF", "font": "000000"},
    "Steven": {"bg": "F1A983", "font": "000000"},
    "Tomas": {"bg": "F9E79F", "font": "000000"},
    "Alejandro": {"bg": "D9EAD3", "font": "000000"},
    "Practicante": {"bg": "BF9000", "font": "FFFFFF"},
    "Refuerzo": {"bg": "D6E4F0", "font": "000000"},
    "Angel": {"bg": "4D93D9", "font": "FFFFFF"},
    "Eligio": {"bg": "FF0000", "font": "FFFFFF"},
    "Keilor": {"bg": "153D64", "font": "FFFFFF"},
}

# Paleta secuencial de respaldo para nombres sin default ni override.
EXCEL_COLOR_PALETTE: List[str] = [
    "4D93D9",
    "FF0000",
    "61CBF3",
    "663300",
    "D86DCD",
    "153D64",
    "8ED973",
    "D9EAD3",
    "BFBFBF",
    "F1A983",
    "F9E79F",
    "D6E4F0",
]

# Precomputado: claves de default ordenadas de mas larga a mas corta (para
# preferir el match mas especifico), junto con su version normalizada.
_DEFAULT_KEYS_BY_LENGTH = sorted(EXCEL_COLOR_DEFAULTS.keys(), key=len, reverse=True)


def _normalize_for_match(name: str) -> str:
    """Sin acentos, sin espacios sobrantes, case-insensitive."""
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.strip().split()).casefold()


def normalize_hex_color(value: Optional[str]) -> Optional[str]:
    """Valida y normaliza un color hex. Acepta '#RRGGBB', 'RRGGBB', 'AARRGGBB'.

    Devuelve el hex en mayusculas de 6 caracteres, o None si es invalido.
    """
    if not value or not isinstance(value, str):
        return None
    v = value.strip().lstrip("#").upper()
    if len(v) == 8:
        v = v[2:]
    if len(v) != 6:
        return None
    try:
        int(v, 16)
    except ValueError:
        return None
    return v


def excel_font_color_for_fill(hex_color: str) -> str:
    """Blanco o negro segun el brillo del color de fondo (contraste automatico)."""
    color = (hex_color or "").strip().lstrip("#")
    if len(color) == 8:
        color = color[2:]
    if len(color) != 6:
        return "000000"

    try:
        red = int(color[0:2], 16)
        green = int(color[2:4], 16)
        blue = int(color[4:6], 16)
    except ValueError:
        return "000000"

    brightness = (red * 299 + green * 587 + blue * 114) / 1000
    return "FFFFFF" if brightness < 145 else "000000"


def _find_default_entry(name: str) -> Optional[Dict[str, str]]:
    if name in EXCEL_COLOR_DEFAULTS:
        return EXCEL_COLOR_DEFAULTS[name]

    normalized_name = _normalize_for_match(name)
    if not normalized_name:
        return None

    for key in _DEFAULT_KEYS_BY_LENGTH:
        normalized_key = _normalize_for_match(key)
        if normalized_name == normalized_key or normalized_name.startswith(normalized_key + " "):
            return EXCEL_COLOR_DEFAULTS[key]
    return None


def resolve_excel_employee_colors(
    names: List[str], custom: Optional[Dict[str, Dict[str, str]]] = None
) -> Dict[str, Dict[str, str]]:
    """Resuelve {bg, font, source} por cada nombre en `names`.

    source es "custom" | "default" | "palette".
    Prioridad: override exacto del usuario > default (exacto o por nombre
    inicial) > paleta secuencial para lo que quede sin resolver.
    """
    custom = custom if isinstance(custom, dict) else {}
    result: Dict[str, Dict[str, str]] = {}
    palette_index = 0

    for name in names:
        raw_entry = custom.get(name)
        custom_bg = None
        custom_font = None
        if isinstance(raw_entry, dict):
            custom_bg = normalize_hex_color(raw_entry.get("bg"))
            custom_font = normalize_hex_color(raw_entry.get("font"))

        default_entry = _find_default_entry(name)

        if custom_bg or custom_font:
            bg = custom_bg or (default_entry["bg"] if default_entry else None)
            if bg is None:
                bg = EXCEL_COLOR_PALETTE[palette_index % len(EXCEL_COLOR_PALETTE)]
                palette_index += 1

            if custom_font:
                font = custom_font
            elif custom_bg:
                font = excel_font_color_for_fill(custom_bg)
            elif default_entry:
                font = default_entry["font"]
            else:
                font = excel_font_color_for_fill(bg)

            result[name] = {"bg": bg, "font": font, "source": "custom"}
        elif default_entry:
            result[name] = {
                "bg": default_entry["bg"],
                "font": default_entry["font"],
                "source": "default",
            }
        else:
            bg = EXCEL_COLOR_PALETTE[palette_index % len(EXCEL_COLOR_PALETTE)]
            palette_index += 1
            result[name] = {
                "bg": bg,
                "font": excel_font_color_for_fill(bg),
                "source": "palette",
            }

    return result


# Colores de celdas de estado (shift code -> label/bg/font), tomados del libro
# maestro. El orden define el orden en que se muestran en la UI.
EXCEL_STATUS_DEFAULTS: Dict[str, Dict[str, str]] = {
    "OFF": {"label": "LIBRE", "bg": "FFFF00", "font": "999999"},
    "VAC": {"label": "VACACIONES", "bg": "C6EFCE", "font": "006100"},
    "PERM": {"label": "PERMISO", "bg": "FCE4D6", "font": "9A3412"},
}


def resolve_excel_status_colors(
    custom: Optional[Dict[str, Dict[str, str]]] = None
) -> Dict[str, Dict[str, str]]:
    """Resuelve {label, bg, font, source} por cada código de estado (OFF/VAC/PERM).

    Mismas reglas que para empleados: override del usuario > default; un
    override con solo bg recibe fuente por contraste automatico. Codigos
    desconocidos y hex invalidos se ignoran.
    """
    custom = custom if isinstance(custom, dict) else {}
    result: Dict[str, Dict[str, str]] = {}

    for code, default in EXCEL_STATUS_DEFAULTS.items():
        raw_entry = custom.get(code)
        custom_bg = custom_font = None
        if isinstance(raw_entry, dict):
            custom_bg = normalize_hex_color(raw_entry.get("bg"))
            custom_font = normalize_hex_color(raw_entry.get("font"))

        if custom_bg or custom_font:
            bg = custom_bg or default["bg"]
            if custom_font:
                font = custom_font
            elif custom_bg:
                font = excel_font_color_for_fill(custom_bg)
            else:
                font = default["font"]
            result[code] = {"label": default["label"], "bg": bg, "font": font, "source": "custom"}
        else:
            result[code] = {**default, "source": "default"}

    return result
