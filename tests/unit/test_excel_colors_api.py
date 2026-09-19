"""Tests for GET/PUT /api/excel-colors and its isolation from POST /api/config.

excel_colors_json is stored on horario_config but read/written through
dedicated helpers (load_excel_colors_custom / save_excel_colors_custom) so
that a normal POST /api/config — which replaces the whole horario_config row
— can never wipe out the user's saved export colors.
"""
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PLAN = os.path.join(_ROOT, "planillas")
_BACKEND = os.path.join(_ROOT, "backend")
for _p in (_PLAN, _BACKEND):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import database as db  # noqa: E402

EMP = "Jeison Aleman Tijerino"  # matches the "Jeison" default by leading-name


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_FILE", str(tmp_path / "test.db"))
    db.init_db()
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO empleados (nombre, tipo_pago, activo) VALUES (?, 'tarjeta', 1)",
        (EMP,),
    )
    conn.execute("INSERT INTO horario_empleados (nombre) VALUES (?)", (EMP,))
    conn.commit()
    conn.close()

    from fastapi.testclient import TestClient
    import main as app_main  # noqa: E402

    return TestClient(app_main.app)


def _entry(payload, name=EMP):
    return next(e for e in payload["employees"] if e["name"] == name)


def test_get_excel_colors_returns_default_and_legend(client):
    res = client.get("/api/excel-colors")
    assert res.status_code == 200
    data = res.json()

    entry = _entry(data)
    assert entry["bg"] == "663300"
    assert entry["font"] == "FFFFFF"
    assert entry["source"] == "default"

    assert [row["label"] for row in data["statuses"]] == ["LIBRE", "VACACIONES", "PERMISO"]


def test_put_then_get_roundtrip(client):
    put_res = client.put(
        "/api/excel-colors",
        json={"colors": {EMP: {"bg": "#112233", "font": "aabbcc"}}},
    )
    assert put_res.status_code == 200
    put_entry = _entry(put_res.json())
    assert put_entry["bg"] == "112233"
    assert put_entry["font"] == "AABBCC"
    assert put_entry["source"] == "custom"

    get_entry = _entry(client.get("/api/excel-colors").json())
    assert get_entry["bg"] == "112233"
    assert get_entry["font"] == "AABBCC"
    assert get_entry["source"] == "custom"


def test_put_omitting_employee_resets_to_default(client):
    client.put("/api/excel-colors", json={"colors": {EMP: {"bg": "112233"}}})
    assert _entry(client.get("/api/excel-colors").json())["source"] == "custom"

    reset_res = client.put("/api/excel-colors", json={"colors": {}})
    reset_entry = _entry(reset_res.json())
    assert reset_entry["source"] == "default"
    assert reset_entry["bg"] == "663300"


def test_put_invalid_hex_is_dropped(client):
    put_res = client.put(
        "/api/excel-colors",
        json={"colors": {EMP: {"bg": "not-a-color", "font": "also-bad"}}},
    )
    entry = _entry(put_res.json())
    assert entry["source"] == "default"
    assert entry["bg"] == "663300"


def test_post_config_does_not_wipe_excel_colors(client):
    put_res = client.put(
        "/api/excel-colors",
        json={"colors": {EMP: {"bg": "112233", "font": "aabbcc"}}},
    )
    assert put_res.status_code == 200

    cfg = client.get("/api/config").json()
    cfg["night_mode"] = "rotation"
    post_res = client.post("/api/config", json=cfg)
    assert post_res.status_code == 200

    entry = _entry(client.get("/api/excel-colors").json())
    assert entry["bg"] == "112233"
    assert entry["font"] == "AABBCC"
    assert entry["source"] == "custom"


def test_put_keeps_custom_colors_of_employees_not_listed(client):
    """The panel only lists active employees, so a save must not drop the
    custom colors of someone currently inactive (e.g. on leave)."""
    import json

    client.put(
        "/api/excel-colors",
        json={"colors": {"Empleado Inactivo": {"bg": "123456", "font": "FFFFFF"}}},
    )
    client.put("/api/excel-colors", json={"colors": {EMP: {"bg": "112233"}}})

    conn = db.get_conn()
    row = conn.execute("SELECT excel_colors_json FROM horario_config WHERE id=1").fetchone()
    conn.close()
    stored = json.loads(row["excel_colors_json"])
    assert stored["Empleado Inactivo"] == {"bg": "123456", "font": "FFFFFF"}
    assert stored[EMP] == {"bg": "112233"}


def test_post_config_before_any_color_save_leaves_colors_empty(client):
    """A config save on a brand-new DB (horario_config row not yet created by
    excel-colors) must not error out and must still leave defaults resolvable."""
    cfg = client.get("/api/config").json()
    post_res = client.post("/api/config", json=cfg)
    assert post_res.status_code == 200

    entry = _entry(client.get("/api/excel-colors").json())
    assert entry["source"] == "default"
