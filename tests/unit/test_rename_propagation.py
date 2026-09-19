"""Tests for employee rename propagation across name-keyed data.

The scheduler stores history schedules, tasks and metadata as JSON keyed by the
employee NAME, not by id. Renaming an employee in the roster used to leave that
history behind, which silently reset the Sunday rotation queue: the renamed
employee looked like somebody who had never had a Sunday off.
"""
import json
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_PLAN = os.path.join(_ROOT, "planillas")
if _PLAN not in sys.path:
    sys.path.insert(0, _PLAN)

import database as db  # noqa: E402

OLD = "Jeison"
NEW = "Jeison Aleman Tijerino"

SCHEDULE = {
    OLD: {"Vie": "D_6-14", "Dom": "OFF"},
    "Refuerzo": {"Vie": "D_6-14", "Dom": "OFF"},
    "Tomas": {"Vie": "D_6-14", "Dom": "D_6-14"},
}
TASKS = {
    OLD: {"Vie": "Baños ↓PM", "Dom": None},
    "Tomas": {"Vie": None, "Dom": None},
}
METADATA = {
    "rotation_queue": ["Tomas", OLD],
    "next_sunday_rotation_queue": [OLD, "Tomas"],
    "rotation_target": OLD,
    "sunday_off_person": OLD,
    "libres_person": "Tomas",
    "refuerzo_employees": ["Refuerzo"],
    "daily_tasks": {OLD: {"Vie": "Baños ↓PM"}},
    "history_entries_used": 6,
}


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point database.py at a throwaway SQLite file with one history entry."""
    monkeypatch.setattr(db, "DB_FILE", str(tmp_path / "test.db"))
    db.init_db()
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO empleados (nombre, tipo_pago, activo) VALUES (?, 'tarjeta', 1)",
        (OLD,),
    )
    conn.execute(
        "INSERT INTO empleados (nombre, tipo_pago, activo) VALUES (?, 'tarjeta', 1)",
        ("Tomas",),
    )
    conn.execute("INSERT INTO horario_empleados (nombre) VALUES (?)", (OLD,))
    conn.execute("INSERT INTO horario_empleados (nombre) VALUES (?)", ("Tomas",))
    conn.execute(
        "INSERT INTO horarios_generados (nombre, horario, tareas, metadata, timestamp) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            "Semana 35",
            json.dumps(SCHEDULE, ensure_ascii=False),
            json.dumps(TASKS, ensure_ascii=False),
            json.dumps(METADATA, ensure_ascii=False),
            "2026-08-20T10:00:00",
        ),
    )
    conn.execute(
        "INSERT OR REPLACE INTO horario_config (id, fixed_night_person) VALUES (1, ?)",
        (OLD,),
    )
    conn.commit()
    conn.close()
    return db


def _emp_id(nombre):
    conn = db.get_conn()
    row = conn.execute("SELECT id FROM empleados WHERE nombre=?", (nombre,)).fetchone()
    conn.close()
    return row["id"]


def _history():
    conn = db.get_conn()
    row = conn.execute(
        "SELECT horario, tareas, metadata FROM horarios_generados LIMIT 1"
    ).fetchone()
    conn.close()
    return (
        json.loads(row["horario"]),
        json.loads(row["tareas"]),
        json.loads(row["metadata"]),
    )


def test_rename_moves_schedule_keys_in_history(temp_db):
    db.update_empleado(_emp_id(OLD), nombre=NEW)

    schedule, _, _ = _history()
    assert NEW in schedule
    assert OLD not in schedule
    assert schedule[NEW]["Dom"] == "OFF"


def test_rename_leaves_other_rows_untouched(temp_db):
    db.update_empleado(_emp_id(OLD), nombre=NEW)

    schedule, tasks, _ = _history()
    assert schedule["Refuerzo"]["Dom"] == "OFF"
    assert schedule["Tomas"]["Dom"] == "D_6-14"
    assert "Tomas" in tasks


def test_rename_moves_task_keys_in_history(temp_db):
    db.update_empleado(_emp_id(OLD), nombre=NEW)

    _, tasks, _ = _history()
    assert tasks[NEW]["Vie"] == "Baños ↓PM"
    assert OLD not in tasks


def test_rename_rewrites_metadata_rotation_queues(temp_db):
    db.update_empleado(_emp_id(OLD), nombre=NEW)

    _, _, metadata = _history()
    assert metadata["rotation_queue"] == ["Tomas", NEW]
    assert metadata["next_sunday_rotation_queue"] == [NEW, "Tomas"]
    assert metadata["rotation_target"] == NEW
    assert metadata["sunday_off_person"] == NEW
    assert metadata["libres_person"] == "Tomas"
    assert NEW in metadata["daily_tasks"]
    assert metadata["history_entries_used"] == 6


def test_rename_rewrites_fixed_night_person(temp_db):
    db.update_empleado(_emp_id(OLD), nombre=NEW)

    conn = db.get_conn()
    row = conn.execute("SELECT fixed_night_person FROM horario_config WHERE id=1").fetchone()
    conn.close()
    assert row["fixed_night_person"] == NEW


def test_rename_moves_excel_color_override(temp_db):
    """Custom export colors (horario_config.excel_colors_json) are keyed by
    employee name too — a rename must move the entry, not orphan it."""
    conn = db.get_conn()
    conn.execute(
        "UPDATE horario_config SET excel_colors_json=? WHERE id=1",
        (json.dumps({OLD: {"bg": "112233", "font": "AABBCC"}}, ensure_ascii=False),),
    )
    conn.commit()
    conn.close()

    db.update_empleado(_emp_id(OLD), nombre=NEW)

    conn = db.get_conn()
    row = conn.execute("SELECT excel_colors_json FROM horario_config WHERE id=1").fetchone()
    conn.close()
    colors = json.loads(row["excel_colors_json"])
    assert NEW in colors and OLD not in colors
    assert colors[NEW] == {"bg": "112233", "font": "AABBCC"}


def test_rename_without_name_change_is_a_noop(temp_db):
    db.update_empleado(_emp_id(OLD), genero="M")

    schedule, _, _ = _history()
    assert OLD in schedule


def test_repair_maps_orphan_history_names(temp_db):
    """The already-broken case: history still holds the pre-rename names."""
    conn = db.get_conn()
    conn.execute("UPDATE empleados SET nombre=? WHERE nombre=?", (NEW, OLD))
    conn.execute("UPDATE horario_empleados SET nombre=? WHERE nombre=?", (NEW, OLD))
    conn.commit()
    conn.close()

    pendientes = db.detectar_nombres_huerfanos()
    assert pendientes.get(OLD) == NEW
    assert "Refuerzo" not in pendientes
    assert "Tomas" not in pendientes

    resumen = db.renombrar_en_datos_historicos(pendientes)
    assert resumen["horarios_generados"] == 1

    schedule, tasks, metadata = _history()
    assert NEW in schedule and OLD not in schedule
    assert NEW in tasks
    assert metadata["rotation_queue"] == ["Tomas", NEW]


def test_repair_dry_run_does_not_write(temp_db):
    conn = db.get_conn()
    conn.execute("UPDATE empleados SET nombre=? WHERE nombre=?", (NEW, OLD))
    conn.commit()
    conn.close()

    db.renombrar_en_datos_historicos({OLD: NEW}, dry_run=True)

    schedule, _, _ = _history()
    assert OLD in schedule
