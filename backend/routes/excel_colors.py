"""API router for per-employee and per-status Excel export colors.

Only feeds GET /api/export_excel (the single-schedule "Exportar" button).
Storage is isolated from the rest of horario_config — see the
load/save_excel_*_colors_custom helpers in .helpers — so that a regular
POST /api/config can never wipe these out.
"""
from fastapi import APIRouter, Request

from excel_colors import (
    EXCEL_STATUS_DEFAULTS,
    normalize_hex_color,
    resolve_excel_employee_colors,
    resolve_excel_status_colors,
)

from .helpers import (
    load_db,
    load_excel_colors_custom,
    load_excel_status_colors_custom,
    save_excel_colors_custom,
    save_excel_status_colors_custom,
)

router = APIRouter(prefix="/api", tags=["excel-colors"])


def _active_names():
    return [e["name"] for e in load_db().get("employees", []) if e.get("name")]


def _build_payload():
    resolved = resolve_excel_employee_colors(_active_names(), load_excel_colors_custom())
    employees = [
        {"name": name, "bg": info["bg"], "font": info["font"], "source": info["source"]}
        for name, info in resolved.items()
    ]
    statuses = [
        {"code": code, **info}
        for code, info in resolve_excel_status_colors(load_excel_status_colors_custom()).items()
    ]
    return {"employees": employees, "statuses": statuses}


def _clean_color_map(raw, allowed_keys=None):
    """Keep only entries with at least one valid hex; normalize them."""
    clean = {}
    if not isinstance(raw, dict):
        return clean
    for key, entry in raw.items():
        if not isinstance(key, str) or not isinstance(entry, dict):
            continue
        if allowed_keys is not None and key not in allowed_keys:
            continue
        bg = normalize_hex_color(entry.get("bg"))
        font = normalize_hex_color(entry.get("font"))
        if not bg and not font:
            # Nothing valid to keep -> treat as "reset to default"
            continue
        item = {}
        if bg:
            item["bg"] = bg
        if font:
            item["font"] = font
        clean[key] = item
    return clean


@router.get("/excel-colors")
def get_excel_colors():
    return _build_payload()


@router.put("/excel-colors")
async def put_excel_colors(request: Request):
    body = await request.json()
    body = body if isinstance(body, dict) else {}

    clean = _clean_color_map(body.get("colors"))
    # The panel only lists active employees: keep stored entries for anyone
    # not listed (e.g. inactive) so a save never silently drops their colors.
    listed = set(_active_names())
    for name, entry in load_excel_colors_custom().items():
        if name not in listed and name not in clean:
            clean[name] = entry
    save_excel_colors_custom(clean)

    # Absent key = leave stored status colors untouched (older clients).
    if "status_colors" in body:
        save_excel_status_colors_custom(
            _clean_color_map(body.get("status_colors"), allowed_keys=EXCEL_STATUS_DEFAULTS)
        )

    return _build_payload()
