"""
database.py - Módulo de acceso a datos SQLite para el Gestor de Planilla
=========================================================================
Maneja empleados, tarifas, meses y semanas generadas.
"""
import json
import sqlite3
import os
import sys
from datetime import datetime, timedelta, date
from typing import Any, Dict, List, Optional

# Días de la semana del scheduler (mismo orden que backend/scheduler_engine.DAYS)
_HORARIO_DIAS = ("Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue")


def _get_planillas_base_dir():
    if getattr(sys, "frozen", False):
        runtime_dir = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "planillas")
        os.makedirs(runtime_dir, exist_ok=True)
        return runtime_dir
    return os.path.dirname(os.path.abspath(__file__))


DB_FILE = os.path.join(_get_planillas_base_dir(), "planilla.db")

# Columnas 0/1 que nunca deben pasar por bool() en Python (bool("0") es True).
_HORARIO_INT_FIELDS = (
    "puede_nocturno",
    "allow_no_rest",
    "forced_libres",
    "forced_quebrado",
    "es_jefe_pista",
    "es_practicante",
    "strict_preferences",
    "activo",
)


def _coerce_sql_int(v, default=0):
    """Normaliza flags SQLite (evita TEXT '0' o tipos raros)."""
    if v is None:
        return default
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, int):
        return 1 if v else 0
    if isinstance(v, float):
        return 1 if int(v) != 0 else 0
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return default
        try:
            return 1 if int(float(s)) != 0 else 0
        except ValueError:
            low = s.lower()
            if low in ("true", "yes", "si", "sí", "on"):
                return 1
            return default
    return default


def get_conn():
    """Get a connection to the database with proper timeout and settings."""
    conn = sqlite3.connect(DB_FILE, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # Increase busy timeout to wait up to 30 seconds for locks
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _column_exists(conn, table, column):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _ensure_column(table, column, column_type):
    """Add a column only when it is actually missing."""
    conn = get_conn()
    try:
        if _column_exists(conn, table, column):
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
        conn.commit()
    finally:
        conn.close()


def init_db():
    """Crea las tablas si no existen."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS empleados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            tipo_pago TEXT NOT NULL CHECK(tipo_pago IN ('tarjeta','efectivo','fijo')),
            salario_fijo REAL,
            cedula TEXT,
            activo INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS tarifas (
            id INTEGER PRIMARY KEY DEFAULT 1,
            tarifa_diurna REAL NOT NULL DEFAULT 50.00,
            tarifa_nocturna REAL NOT NULL DEFAULT 75.00,
            tarifa_mixta REAL NOT NULL DEFAULT 62.50,
            seguro REAL NOT NULL DEFAULT 10498.00
        );

        CREATE TABLE IF NOT EXISTS meses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            anio INTEGER NOT NULL,
            mes INTEGER NOT NULL,
            archivo TEXT NOT NULL,
            fecha_creacion TEXT NOT NULL,
            cerrado INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS semanas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes_id INTEGER REFERENCES meses(id),
            num_semana INTEGER NOT NULL,
            viernes TEXT NOT NULL,
            fecha_agregada TEXT NOT NULL
        );

        -- ══ TABLAS DE HORARIOS ══
        CREATE TABLE IF NOT EXISTS horario_empleados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE NOT NULL,
            genero TEXT DEFAULT 'M',
            puede_nocturno INTEGER DEFAULT 1,
            allow_no_rest INTEGER DEFAULT 0,
            forced_libres INTEGER DEFAULT 0,
            forced_quebrado INTEGER DEFAULT 0,
            es_jefe_pista INTEGER DEFAULT 0,
            es_practicante INTEGER DEFAULT 0,
            strict_preferences INTEGER DEFAULT 0,
            turnos_fijos TEXT DEFAULT '{}',
            dia_libre_forzado TEXT DEFAULT '',
            activo INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS horario_config (
            id INTEGER PRIMARY KEY DEFAULT 1,
            night_mode TEXT DEFAULT 'rotation',
            fixed_night_person TEXT,
            allow_long_shifts INTEGER DEFAULT 0,
            use_refuerzo INTEGER DEFAULT 0,
            refuerzo_type TEXT DEFAULT 'personalizado',
            refuerzo_start TEXT DEFAULT '07:00',
            refuerzo_end TEXT DEFAULT '12:00',
            allow_collision_quebrado INTEGER DEFAULT 0,
            collision_peak_priority TEXT DEFAULT 'pm',
            sunday_cycle_index INTEGER DEFAULT 0,
            sunday_rotation_queue TEXT,
            use_history INTEGER DEFAULT 1,
            strict_weekly_alternation INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS horarios_generados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            horario TEXT NOT NULL,
            tareas TEXT,
            metadata TEXT,
            timestamp TEXT NOT NULL,
            deleted INTEGER DEFAULT 0,
            deleted_at TEXT
        );

        -- ══ SALARIOS MENSUALES (para aguinaldo) ══
        CREATE TABLE IF NOT EXISTS salarios_mensuales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empleado_id INTEGER NOT NULL,
            empleado_nombre TEXT NOT NULL,
            anio INTEGER NOT NULL,
            mes INTEGER NOT NULL,
            semana INTEGER,
            salario_bruto REAL NOT NULL DEFAULT 0,
            fecha_registro TEXT NOT NULL
        );

        -- ══ INVENTARIO ══
        CREATE TABLE IF NOT EXISTS inventario_cargas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            archivo_nombre TEXT,
            total_articulos INTEGER DEFAULT 0,
            fecha_registro TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS inventario_articulos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            carga_id INTEGER REFERENCES inventario_cargas(id) ON DELETE CASCADE,
            codigo TEXT,
            nombre TEXT NOT NULL,
            precio REAL DEFAULT 0,
            existencias REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS inventario_base_config (
            id INTEGER PRIMARY KEY DEFAULT 1,
            source_path TEXT,
            last_imported_at TEXT
        );

        CREATE TABLE IF NOT EXISTS inventario_base_articulos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT,
            nombre TEXT NOT NULL,
            precio REAL DEFAULT 0,
            existencias_base REAL DEFAULT 0,
            hoja_origen TEXT,
            orden INTEGER DEFAULT 0,
            activo INTEGER DEFAULT 1
        );
    """)

    # Insertar tarifas por defecto si no existen
    cur = conn.execute("SELECT COUNT(*) FROM tarifas")
    if cur.fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO tarifas (id, tarifa_diurna, tarifa_nocturna, tarifa_mixta, seguro) "
            "VALUES (1, 50.00, 75.00, 62.50, 10498.00)"
        )
    conn.commit()
    conn.close()

    _inventory_base_migrations = [
        ("inventario_base_articulos", "hoja_origen", "TEXT"),
        ("inventario_base_articulos", "orden", "INTEGER DEFAULT 0"),
        ("inventario_base_articulos", "activo", "INTEGER DEFAULT 1"),
    ]
    for table, col, col_type in _inventory_base_migrations:
        _ensure_column(table, col, col_type)

    # Migration: add cedula column if it doesn't exist
    _ensure_column("empleados", "cedula", "TEXT")
    
    # Migration: add strict_preferences column if it doesn't exist
    _ensure_column("horario_empleados", "strict_preferences", "INTEGER DEFAULT 0")

    # Migration: add correo, telefono, fecha_inicio, aplica_seguro columns
    _migrations = [
        ("empleados", "correo", "TEXT"),
        ("empleados", "telefono", "TEXT"),
        ("empleados", "fecha_inicio", "TEXT"),
        ("empleados", "aplica_seguro", "INTEGER DEFAULT 1"),
    ]
    for table, col, col_type in _migrations:
        _ensure_column(table, col, col_type)

    _ensure_column("tarifas", "seguro_modo", "TEXT DEFAULT 'porcentual'")
    _ensure_column("tarifas", "seguro_valor", "REAL DEFAULT 0.1067")

    # Migration: add es_practicante column
    _ensure_column("horario_empleados", "es_practicante", "INTEGER DEFAULT 0")

    # Migration: scheduler config flags
    _scheduler_config_migrations = [
        ("horario_config", "use_history", "INTEGER DEFAULT 1"),
        ("horario_config", "refuerzo_start", "TEXT DEFAULT '07:00'"),
        ("horario_config", "refuerzo_end", "TEXT DEFAULT '12:00'"),
        ("horario_config", "strict_weekly_alternation", "INTEGER DEFAULT 0"),
        ("horario_config", "holidays", "TEXT DEFAULT '[]'"),
        ("horario_config", "use_pref_plantilla", "INTEGER DEFAULT 0"),
        ("horario_config", "jefe_base_shift", "TEXT DEFAULT 'J_06-16'"),
    ]
    for table, col, col_type in _scheduler_config_migrations:
        _ensure_column(table, col, col_type)

    # Migration: soft delete for history entries (papelera de reciclaje)
    _ensure_column("horarios_generados", "deleted", "INTEGER DEFAULT 0")
    _ensure_column("horarios_generados", "deleted_at", "TEXT")

    # Create vacaciones table + documentos RRHH registry
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS documentos_rrhh (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL UNIQUE,
            tipo TEXT NOT NULL,
            empleado_id INTEGER,
            empleado_nombre TEXT,
            datos_json TEXT,
            ruta_archivo TEXT,
            fecha_generacion TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS vacaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empleado_id INTEGER REFERENCES empleados(id),
            fecha_inicio TEXT NOT NULL,
            fecha_fin TEXT NOT NULL,
            dias INTEGER NOT NULL,
            fecha_reingreso TEXT,
            fecha_registro TEXT NOT NULL,
            notas TEXT
        );

        CREATE TABLE IF NOT EXISTS permisos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empleado_id INTEGER REFERENCES empleados(id),
            fecha TEXT NOT NULL,
            dia_semana TEXT,
            motivo TEXT,
            notas TEXT,
            anio INTEGER NOT NULL,
            descontado_de_vacaciones INTEGER DEFAULT 0,
            fecha_registro TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS prestamos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empleado_id INTEGER REFERENCES empleados(id),
            monto_total REAL NOT NULL,
            pago_semanal REAL NOT NULL,
            saldo REAL NOT NULL,
            estado TEXT DEFAULT 'activo',
            fecha_inicio TEXT NOT NULL,
            fecha_liquidacion TEXT,
            notas TEXT,
            fecha_registro TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS prestamo_abonos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prestamo_id INTEGER REFERENCES prestamos(id),
            monto REAL NOT NULL,
            tipo TEXT DEFAULT 'planilla',
            fecha TEXT NOT NULL,
            semana_planilla TEXT,
            notas TEXT,
            fecha_registro TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


# ── EMPLEADOS (UNIFICADO: planilla + horario) ────────────────────────────────

def get_empleados(solo_activos=True):
    """Devuelve empleados con datos de planilla Y de horario unidos por nombre."""
    conn = get_conn()
    where = "WHERE e.activo=1" if solo_activos else ""
    rows = conn.execute(f"""
        SELECT e.id, e.nombre, e.tipo_pago, e.salario_fijo, e.cedula,
               e.correo, e.telefono, e.fecha_inicio, e.activo,
               COALESCE(e.aplica_seguro, 1) as aplica_seguro,
               COALESCE(h.genero, 'M') as genero,
               COALESCE(h.puede_nocturno, 1) as puede_nocturno,
               COALESCE(h.allow_no_rest, 0) as allow_no_rest,
               COALESCE(h.forced_libres, 0) as forced_libres,
               COALESCE(h.forced_quebrado, 0) as forced_quebrado,
               COALESCE(h.es_jefe_pista, 0) as es_jefe_pista,
               COALESCE(h.es_practicante, 0) as es_practicante,
                COALESCE(h.strict_preferences, 0) as strict_preferences,
                COALESCE(h.turnos_fijos, '{{}}') as turnos_fijos,
                h.pref_plantilla_id as pref_plantilla_id,
                (SELECT pp.nombre FROM horario_pref_plantilla pp WHERE pp.id = h.pref_plantilla_id) as pref_plantilla_nombre
        FROM empleados e
        LEFT JOIN horario_empleados h ON e.nombre = h.nombre
        {where}
        ORDER BY e.nombre
    """).fetchall()
    conn.close()
    _flag_defaults = {"puede_nocturno": 1, "activo": 1}
    out = []
    for r in rows:
        d = dict(r)
        for k in _HORARIO_INT_FIELDS:
            if k in d:
                d[k] = _coerce_sql_int(d.get(k), _flag_defaults.get(k, 0))
        out.append(d)
    return out


def add_empleado(nombre, tipo_pago, salario_fijo=None, cedula=None,
                 correo=None, telefono=None, fecha_inicio=None,
                 aplica_seguro=1, genero='M', puede_nocturno=1,
                 forced_libres=0, forced_quebrado=0, allow_no_rest=0,
                 es_jefe_pista=0, es_practicante=0, strict_preferences=0,
                 turnos_fijos='{}', pref_plantilla_id=None):
    """Inserta en ambas tablas: empleados + horario_empleados."""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO empleados (nombre, tipo_pago, salario_fijo, cedula, correo, telefono, fecha_inicio, aplica_seguro) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (nombre.strip(), tipo_pago, salario_fijo, cedula, correo, telefono, fecha_inicio, aplica_seguro)
        )
        # Also insert into horario_empleados if not exists
        existing = conn.execute("SELECT id FROM horario_empleados WHERE nombre=?", (nombre.strip(),)).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO horario_empleados (nombre, genero, puede_nocturno, forced_libres, forced_quebrado, allow_no_rest, es_jefe_pista, es_practicante, strict_preferences, turnos_fijos, dia_libre_forzado) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (nombre.strip(), genero, puede_nocturno, forced_libres, forced_quebrado, allow_no_rest, es_jefe_pista, es_practicante, strict_preferences, turnos_fijos, "")
            )
            nm = nombre.strip()
            if _coerce_sql_int(es_jefe_pista, 0) == 1:
                conn.execute(
                    "UPDATE horario_empleados SET es_jefe_pista=0 WHERE nombre != ?",
                    (nm,),
                )
            if pref_plantilla_id:
                try:
                    conn.execute(
                        "UPDATE horario_empleados SET pref_plantilla_id=? WHERE nombre=?",
                        (int(pref_plantilla_id), nombre.strip()),
                    )
                except (TypeError, ValueError):
                    pass
        conn.commit()
        return True, "Empleado agregado"
    except sqlite3.IntegrityError:
        return False, "El empleado ya existe"
    finally:
        conn.close()


def remove_empleado(emp_id):
    """Desactiva empleado en ambas tablas."""
    conn = get_conn()
    row = conn.execute("SELECT nombre FROM empleados WHERE id=?", (emp_id,)).fetchone()
    conn.execute("UPDATE empleados SET activo=0 WHERE id=?", (emp_id,))
    if row:
        conn.execute("UPDATE horario_empleados SET activo=0 WHERE nombre=?", (row["nombre"],))
    conn.commit()
    conn.close()


def delete_empleado(emp_id):
    """Hard delete empleado de todas las tablas."""
    conn = get_conn()
    row = conn.execute("SELECT nombre FROM empleados WHERE id=?", (emp_id,)).fetchone()
    if not row:
        conn.close()
        return

    nombre = row["nombre"]

    # Eliminar registros asociados
    conn.execute("DELETE FROM vacaciones WHERE empleado_id=?", (emp_id,))
    conn.execute("DELETE FROM permisos WHERE empleado_id=?", (emp_id,))
    
    prestamos = conn.execute("SELECT id FROM prestamos WHERE empleado_id=?", (emp_id,)).fetchall()
    for p in prestamos:
        conn.execute("DELETE FROM prestamo_abonos WHERE prestamo_id=?", (p["id"],))
    conn.execute("DELETE FROM prestamos WHERE empleado_id=?", (emp_id,))

    conn.execute("DELETE FROM horario_empleados WHERE nombre=?", (nombre,))
    conn.execute("DELETE FROM empleados WHERE id=?", (emp_id,))

    conn.commit()
    conn.close()


def reactivar_empleado(emp_id):
    conn = get_conn()
    row = conn.execute("SELECT nombre FROM empleados WHERE id=?", (emp_id,)).fetchone()
    conn.execute("UPDATE empleados SET activo=1 WHERE id=?", (emp_id,))
    if row:
        conn.execute("UPDATE horario_empleados SET activo=1 WHERE nombre=?", (row["nombre"],))
    conn.commit()
    conn.close()


_UNSET = object()


def update_empleado(emp_id, nombre=None, tipo_pago=None, salario_fijo=None,
                    cedula=None, correo=None, telefono=None, fecha_inicio=None,
                    aplica_seguro=None, genero=None, puede_nocturno=None,
                    forced_libres=None, forced_quebrado=None, allow_no_rest=None,
                    es_jefe_pista=None, es_practicante=None, strict_preferences=None,
                    turnos_fijos=None, pref_plantilla_id=_UNSET):
    """Actualiza campos en ambas tablas (empleados + horario_empleados)."""
    conn = get_conn()
    # Get current name for horario_empleados link
    old_row = conn.execute("SELECT nombre FROM empleados WHERE id=?", (emp_id,)).fetchone()
    old_name = old_row["nombre"] if old_row else None

    # --- Update empleados table ---
    if nombre:
        conn.execute("UPDATE empleados SET nombre=? WHERE id=?", (nombre.strip(), emp_id))
    if tipo_pago:
        conn.execute("UPDATE empleados SET tipo_pago=? WHERE id=?", (tipo_pago, emp_id))
    if salario_fijo is not None:
        conn.execute("UPDATE empleados SET salario_fijo=? WHERE id=?", (salario_fijo, emp_id))
    if cedula is not None:
        conn.execute("UPDATE empleados SET cedula=? WHERE id=?", (cedula, emp_id))
    if correo is not None:
        conn.execute("UPDATE empleados SET correo=? WHERE id=?", (correo, emp_id))
    if telefono is not None:
        conn.execute("UPDATE empleados SET telefono=? WHERE id=?", (telefono, emp_id))
    if fecha_inicio is not None:
        conn.execute("UPDATE empleados SET fecha_inicio=? WHERE id=?", (fecha_inicio, emp_id))
    if aplica_seguro is not None:
        conn.execute("UPDATE empleados SET aplica_seguro=? WHERE id=?", (aplica_seguro, emp_id))

    # --- Update horario_empleados table ---
    if old_name:
        if nombre:
            conn.execute("UPDATE horario_empleados SET nombre=? WHERE nombre=?", (nombre.strip(), old_name))
            old_name = nombre.strip()
        if genero is not None:
            conn.execute("UPDATE horario_empleados SET genero=? WHERE nombre=?", (genero, old_name))
        if puede_nocturno is not None:
            conn.execute("UPDATE horario_empleados SET puede_nocturno=? WHERE nombre=?", (puede_nocturno, old_name))
        if forced_libres is not None:
            conn.execute("UPDATE horario_empleados SET forced_libres=? WHERE nombre=?", (forced_libres, old_name))
        if forced_quebrado is not None:
            conn.execute("UPDATE horario_empleados SET forced_quebrado=? WHERE nombre=?", (forced_quebrado, old_name))
        if allow_no_rest is not None:
            conn.execute("UPDATE horario_empleados SET allow_no_rest=? WHERE nombre=?", (allow_no_rest, old_name))
        if es_jefe_pista is not None:
            conn.execute("UPDATE horario_empleados SET es_jefe_pista=? WHERE nombre=?", (es_jefe_pista, old_name))
            if _coerce_sql_int(es_jefe_pista, 0) == 1:
                conn.execute(
                    "UPDATE horario_empleados SET es_jefe_pista=0 WHERE nombre != ?",
                    (old_name,),
                )
        if es_practicante is not None:
            conn.execute("UPDATE horario_empleados SET es_practicante=? WHERE nombre=?", (es_practicante, old_name))
        if strict_preferences is not None:
            conn.execute("UPDATE horario_empleados SET strict_preferences=? WHERE nombre=?", (strict_preferences, old_name))
        if turnos_fijos is not None:
            conn.execute("UPDATE horario_empleados SET turnos_fijos=? WHERE nombre=?", (turnos_fijos, old_name))
        if pref_plantilla_id is not _UNSET:
            if pref_plantilla_id is None or pref_plantilla_id == "":
                pid = None
            else:
                try:
                    pid = int(pref_plantilla_id)
                except (TypeError, ValueError):
                    pid = None
            conn.execute(
                "UPDATE horario_empleados SET pref_plantilla_id=? WHERE nombre=?",
                (pid, old_name),
            )

    conn.commit()
    conn.close()


# ── PLANTILLAS DE PREFERENCIAS DE HORARIO ───────────────────────────────────

def _ensure_pref_plantilla_schema():
    conn = get_conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS horario_pref_plantilla (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL UNIQUE,
                descripcion TEXT,
                activa INTEGER DEFAULT 1,
                turnos_fijos TEXT DEFAULT '{}',
                strict_preferences INTEGER DEFAULT 0,
                allow_no_rest INTEGER DEFAULT 0,
                forced_libres INTEGER DEFAULT 0,
                forced_quebrado INTEGER DEFAULT 0
            )
            """
        )
        conn.commit()
    finally:
        conn.close()
    _ensure_column("horario_empleados", "pref_plantilla_id", "INTEGER")


def list_pref_plantillas(solo_activas: bool = False) -> List[Dict[str, Any]]:
    conn = get_conn()
    try:
        q = "SELECT id, nombre, descripcion, activa, turnos_fijos, strict_preferences, allow_no_rest, forced_libres, forced_quebrado FROM horario_pref_plantilla"
        if solo_activas:
            q += " WHERE COALESCE(activa,1) = 1"
        q += " ORDER BY nombre"
        rows = conn.execute(q).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_pref_plantilla(plantilla_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        r = conn.execute(
            "SELECT * FROM horario_pref_plantilla WHERE id=?",
            (int(plantilla_id),),
        ).fetchone()
        return dict(r) if r else None
    finally:
        conn.close()


def create_pref_plantilla(
    nombre: str,
    descripcion: str = "",
    activa: int = 1,
    turnos_fijos: str = "{}",
    strict_preferences: int = 0,
    allow_no_rest: int = 0,
    forced_libres: int = 0,
    forced_quebrado: int = 0,
) -> int:
    conn = get_conn()
    try:
        cur = conn.execute(
            """
            INSERT INTO horario_pref_plantilla
            (nombre, descripcion, activa, turnos_fijos, strict_preferences, allow_no_rest, forced_libres, forced_quebrado)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                nombre.strip(),
                (descripcion or "").strip(),
                _coerce_sql_int(activa, 1),
                turnos_fijos or "{}",
                _coerce_sql_int(strict_preferences, 0),
                _coerce_sql_int(allow_no_rest, 0),
                _coerce_sql_int(forced_libres, 0),
                _coerce_sql_int(forced_quebrado, 0),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def update_pref_plantilla(
    plantilla_id: int,
    nombre: Optional[str] = None,
    descripcion: Optional[str] = None,
    activa: Optional[int] = None,
    turnos_fijos: Optional[str] = None,
    strict_preferences: Optional[int] = None,
    allow_no_rest: Optional[int] = None,
    forced_libres: Optional[int] = None,
    forced_quebrado: Optional[int] = None,
) -> None:
    conn = get_conn()
    try:
        fields = []
        vals = []
        if nombre is not None:
            fields.append("nombre=?")
            vals.append(nombre.strip())
        if descripcion is not None:
            fields.append("descripcion=?")
            vals.append(descripcion.strip())
        if activa is not None:
            fields.append("activa=?")
            vals.append(_coerce_sql_int(activa, 1))
        if turnos_fijos is not None:
            fields.append("turnos_fijos=?")
            vals.append(turnos_fijos)
        if strict_preferences is not None:
            fields.append("strict_preferences=?")
            vals.append(_coerce_sql_int(strict_preferences, 0))
        if allow_no_rest is not None:
            fields.append("allow_no_rest=?")
            vals.append(_coerce_sql_int(allow_no_rest, 0))
        if forced_libres is not None:
            fields.append("forced_libres=?")
            vals.append(_coerce_sql_int(forced_libres, 0))
        if forced_quebrado is not None:
            fields.append("forced_quebrado=?")
            vals.append(_coerce_sql_int(forced_quebrado, 0))
        if not fields:
            return
        vals.append(int(plantilla_id))
        conn.execute(
            f"UPDATE horario_pref_plantilla SET {', '.join(fields)} WHERE id=?",
            vals,
        )
        conn.commit()
    finally:
        conn.close()


def delete_pref_plantilla(plantilla_id: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE horario_empleados SET pref_plantilla_id=NULL WHERE pref_plantilla_id=?",
            (int(plantilla_id),),
        )
        conn.execute("DELETE FROM horario_pref_plantilla WHERE id=?", (int(plantilla_id),))
        conn.commit()
    finally:
        conn.close()


def get_use_pref_plantilla() -> bool:
    """Si es True, resolve_prefs_for_solver puede usar horario_pref_plantilla."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT use_pref_plantilla FROM horario_config WHERE id=1").fetchone()
        if not row:
            return False
        if "use_pref_plantilla" not in row.keys():
            return False
        return bool(_coerce_sql_int(row["use_pref_plantilla"], 0))
    finally:
        conn.close()


def resolve_prefs_for_solver(
    emp_row: Dict[str, Any], use_pref_plantilla: Optional[bool] = None
) -> Dict[str, Any]:
    """
    Devuelve fixed_shifts y flags de preferencia para ShiftScheduler.
    Si use_pref_plantilla y hay pref_plantilla_id y la plantilla existe y está activa, usa la plantilla;
    si no, usa columnas de horario_empleados (modo legado).
    """
    if use_pref_plantilla is None:
        use_pref_plantilla = get_use_pref_plantilla()

    pid = emp_row.get("pref_plantilla_id")
    try:
        pid = int(pid) if pid is not None and str(pid).strip() != "" else None
    except (TypeError, ValueError):
        pid = None

    if use_pref_plantilla and pid:
        tpl = get_pref_plantilla(pid)
        if tpl and _coerce_sql_int(tpl.get("activa"), 1):
            try:
                fs = json.loads(tpl.get("turnos_fijos") or "{}")
            except (json.JSONDecodeError, TypeError):
                fs = {}
            if not isinstance(fs, dict):
                fs = {}
            return {
                "fixed_shifts": fs,
                "strict_preferences": bool(_coerce_sql_int(tpl.get("strict_preferences"), 0)),
                "allow_no_rest": bool(_coerce_sql_int(tpl.get("allow_no_rest"), 0)),
                "forced_libres": bool(_coerce_sql_int(tpl.get("forced_libres"), 0)),
                "forced_quebrado": bool(_coerce_sql_int(tpl.get("forced_quebrado"), 0)),
            }

    try:
        fs = json.loads(emp_row.get("turnos_fijos") or "{}")
    except (json.JSONDecodeError, TypeError):
        fs = {}
    if not isinstance(fs, dict):
        fs = {}
    return {
        "fixed_shifts": fs,
        "strict_preferences": bool(_coerce_sql_int(emp_row.get("strict_preferences"), 0)),
        "allow_no_rest": bool(_coerce_sql_int(emp_row.get("allow_no_rest"), 0)),
        "forced_libres": bool(_coerce_sql_int(emp_row.get("forced_libres"), 0)),
        "forced_quebrado": bool(_coerce_sql_int(emp_row.get("forced_quebrado"), 0)),
    }


def _parse_friday_week_start(week_start: Optional[str]) -> date:
    """ISO date; si es viernes se usa tal cual; si no, se retrocede al viernes anterior."""
    if not week_start or not str(week_start).strip():
        d = date.today()
        while d.weekday() != 4:
            d -= timedelta(days=1)
        return d
    d = datetime.strptime(str(week_start).strip()[:10], "%Y-%m-%d").date()
    while d.weekday() != 4:
        d -= timedelta(days=1)
    return d


def _week_day_date_map(week_friday: date) -> Dict[str, str]:
    keys = list(_HORARIO_DIAS)
    out: Dict[str, str] = {}
    cur = week_friday
    for k in keys:
        out[k] = cur.isoformat()
        cur += timedelta(days=1)
    return out


def _absences_from_resolved_shifts(
    resolved_shifts: Dict[str, Any], day_dates: Dict[str, str]
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for dk in _HORARIO_DIAS:
        code = resolved_shifts.get(dk)
        if code in ("VAC", "PERM", "OFF"):
            out.append(
                {
                    "type": code,
                    "date": day_dates.get(dk, ""),
                    "note": "turnos_fijos_resolved",
                }
            )
    return out


def _hr_absence_hints_for_week(
    conn, empleado_id: int, resolved_shifts: Dict[str, Any], day_dates: Dict[str, str]
) -> List[Dict[str, Any]]:
    hints: List[Dict[str, Any]] = []
    for dk, ds in day_dates.items():
        resolved = resolved_shifts.get(dk)
        vac = conn.execute(
            """SELECT id FROM vacaciones
               WHERE empleado_id=? AND fecha_inicio <= ? AND fecha_fin >= ?""",
            (empleado_id, ds, ds),
        ).fetchone()
        if vac and resolved != "VAC":
            hints.append(
                {
                    "type": "VAC",
                    "date": ds,
                    "source": "rrhh",
                    "note": "Registrado en RR.HH.; no coincide con turno fijo del generador",
                }
            )
        perm = conn.execute(
            "SELECT id FROM permisos WHERE empleado_id=? AND fecha=?",
            (empleado_id, ds),
        ).fetchone()
        if perm and resolved != "PERM":
            hints.append(
                {
                    "type": "PERM",
                    "date": ds,
                    "source": "rrhh",
                    "note": "Registrado en RR.HH.; no coincide con turno fijo del generador",
                }
            )
    return hints


def get_generator_employee_params(week_start: Optional[str] = None) -> Dict[str, Any]:
    """
    Panel de Parámetros del Generador: snapshot JSON por employee_id.
    Ausencias efectivas para el solver = turnos fijos resueltos (plantilla o inline).
    hr_absence_hints = solo informativo (vacaciones/permisos en BD vs turnos).
    """
    wf = _parse_friday_week_start(week_start)
    day_dates = _week_day_date_map(wf)
    emps = get_empleados(solo_activos=True)
    employees: Dict[str, Any] = {}
    conn = get_conn()
    try:
        use_tpl = get_use_pref_plantilla()
        for e in emps:
            emp_id = int(e["id"])
            rp = resolve_prefs_for_solver(e, use_pref_plantilla=use_tpl)
            shifts = dict(rp["fixed_shifts"] or {})
            if not isinstance(shifts, dict):
                shifts = {}
            pid = e.get("pref_plantilla_id")
            try:
                pid = int(pid) if pid is not None and str(pid).strip() != "" else None
            except (TypeError, ValueError):
                pid = None
            pref_source = "plantilla" if (use_tpl and pid) else "inline"
            shift_preferences: Dict[str, str] = {}
            for dk in _HORARIO_DIAS:
                v = shifts.get(dk)
                if v is None or v == "":
                    shift_preferences[dk] = "AUTO"
                else:
                    shift_preferences[dk] = str(v)
            absences = _absences_from_resolved_shifts(shifts, day_dates)
            hr_hints = _hr_absence_hints_for_week(conn, emp_id, shifts, day_dates)
            employees[str(emp_id)] = {
                "employee_id": emp_id,
                "nombre": e.get("nombre", ""),
                "flags": {
                    "forced_libres": bool(rp["forced_libres"]),
                    "forced_quebrado": bool(rp["forced_quebrado"]),
                    "allow_no_rest": bool(rp["allow_no_rest"]),
                    "strict_preferences": bool(rp["strict_preferences"]),
                    "is_jefe_pista": bool(_coerce_sql_int(e.get("es_jefe_pista"), 0)),
                },
                "preference_source": pref_source,
                "pref_plantilla_id": pid,
                "pref_plantilla_nombre": e.get("pref_plantilla_nombre"),
                "shift_preferences": shift_preferences,
                "absences": absences,
                "hr_absence_hints": hr_hints,
            }
    finally:
        conn.close()
    return {
        "version": 1,
        "week_context": {
            "week_start": wf.isoformat(),
            "week_end": (wf + timedelta(days=6)).isoformat(),
            "label": f"Semana Vie–Jue desde viernes {wf.isoformat()}",
        },
        "employees": employees,
        "absences_strategy": {
            "solver_source_of_truth": "turnos_fijos_resolved",
            "rrhh_hints": "informational_only",
        },
    }


def apply_generator_employee_params_batch(
    updates: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Actualización por lote. Aplica flags + merge de shift_preferences sobre turnos_fijos.
    Si el payload incluye pref_plantilla_id, también actualiza esa columna (API legado).
    """
    active = {e["id"]: e for e in get_empleados(solo_activos=True)}
    row_results: List[Dict[str, Any]] = []
    for raw in updates:
        eid = raw.get("employee_id")
        if eid is None:
            row_results.append({"employee_id": None, "ok": False, "error": "missing employee_id"})
            continue
        try:
            eid = int(eid)
        except (TypeError, ValueError):
            row_results.append({"employee_id": eid, "ok": False, "error": "invalid employee_id"})
            continue
        e = active.get(eid)
        if not e:
            row_results.append({"employee_id": eid, "ok": False, "error": "employee_not_found_or_inactive"})
            continue
        flags = raw.get("flags") if isinstance(raw.get("flags"), dict) else {}
        shifts_patch = raw.get("shift_preferences") if isinstance(raw.get("shift_preferences"), dict) else None
        pref_in_payload = "pref_plantilla_id" in raw
        warnings: List[str] = []
        kwargs: Dict[str, Any] = {}
        if pref_in_payload:
            v = raw.get("pref_plantilla_id")
            try:
                ep = int(v) if v is not None and str(v).strip() != "" else None
            except (TypeError, ValueError):
                ep = None
            kwargs["pref_plantilla_id"] = ep
        if flags:
            if flags.get("forced_libres") is not None:
                kwargs["forced_libres"] = 1 if flags["forced_libres"] else 0
            if flags.get("forced_quebrado") is not None:
                kwargs["forced_quebrado"] = 1 if flags["forced_quebrado"] else 0
            if flags.get("allow_no_rest") is not None:
                kwargs["allow_no_rest"] = 1 if flags["allow_no_rest"] else 0
            if flags.get("strict_preferences") is not None:
                kwargs["strict_preferences"] = 1 if flags["strict_preferences"] else 0
            if flags.get("is_jefe_pista") is not None:
                kwargs["es_jefe_pista"] = 1 if flags["is_jefe_pista"] else 0
        if shifts_patch:
            try:
                fs = json.loads(e.get("turnos_fijos") or "{}")
            except (json.JSONDecodeError, TypeError):
                fs = {}
            if not isinstance(fs, dict):
                fs = {}
            for k, v in shifts_patch.items():
                if k not in _HORARIO_DIAS:
                    continue
                if v is None or str(v).strip().upper() == "AUTO" or str(v).strip() == "":
                    fs.pop(k, None)
                else:
                    fs[k] = str(v).strip()
            kwargs["turnos_fijos"] = json.dumps(fs, ensure_ascii=False)
        if kwargs:
            update_empleado(eid, **kwargs)
            row_results.append({"employee_id": eid, "ok": True, "warnings": warnings})
        else:
            row_results.append({"employee_id": eid, "ok": True, "warnings": ["sin cambios"]})
    ok_count = sum(1 for r in row_results if r.get("ok"))
    return {
        "ok": (not row_results) or all(r.get("ok") for r in row_results),
        "applied_rows": ok_count,
        "results": row_results,
    }


def sync_all_rrhh_to_fixed_shifts_for_week(fecha_viernes: str) -> Dict[str, Any]:
    """Ejecuta sync_vac_perm_to_fixed_shifts para todos los empleados activos."""
    wf = _parse_friday_week_start(fecha_viernes)
    fecha_inicio = wf.isoformat()
    fecha_fin = (wf + timedelta(days=6)).isoformat()
    emps = get_empleados(solo_activos=True)
    for e in emps:
        sync_vac_perm_to_fixed_shifts(e["nombre"], fecha_inicio, fecha_fin)
    return {"ok": True, "empleados": len(emps), "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin}


# ── VACACIONES ───────────────────────────────────────────────────────────────

def get_vacaciones(empleado_id):
    """Obtiene todos los registros de vacaciones de un empleado."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM vacaciones WHERE empleado_id=? ORDER BY fecha_inicio DESC",
        (empleado_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_todas_vacaciones():
    """Obtiene todos los registros de vacaciones."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT v.*, e.nombre FROM vacaciones v JOIN empleados e ON v.empleado_id = e.id "
        "ORDER BY v.fecha_inicio DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_vacacion(empleado_id, fecha_inicio, fecha_fin, dias, fecha_reingreso=None, notas=None):
    """Registra un período de vacaciones."""
    conn = get_conn()
    conn.execute(
        "INSERT INTO vacaciones (empleado_id, fecha_inicio, fecha_fin, dias, fecha_reingreso, fecha_registro, notas) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (empleado_id, fecha_inicio, fecha_fin, dias, fecha_reingreso,
         datetime.now().isoformat(), notas)
    )
    conn.commit()
    conn.close()


def delete_vacacion(vac_id):
    """Elimina un registro de vacación."""
    conn = get_conn()
    conn.execute("DELETE FROM vacaciones WHERE id=?", (vac_id,))
    conn.commit()
    conn.close()


def update_vacacion(vac_id, fecha_inicio, fecha_fin, dias, fecha_reingreso=None, notas=None):
    """Actualiza un registro de vacación existente."""
    conn = get_conn()
    conn.execute(
        "UPDATE vacaciones SET fecha_inicio=?, fecha_fin=?, dias=?, fecha_reingreso=?, notas=? WHERE id=?",
        (fecha_inicio, fecha_fin, dias, fecha_reingreso, notas, vac_id)
    )
    conn.commit()
    conn.close()


def calcular_dias_vacaciones(fecha_inicio_str):
    """Calcula los días de vacaciones acumulados según ley de Costa Rica.
    
    Reglas:
    - Primer año (< 50 semanas): 1 día por mes completo trabajado
    - A partir de 50 semanas: 14 días por año completo
    - Proporcional para fracciones de año después del primer año
    """
    if not fecha_inicio_str:
        return 0
    try:
        inicio = datetime.strptime(fecha_inicio_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return 0
    
    from datetime import date as _date
    hoy = _date.today()
    if inicio > hoy:
        return 0
    
    delta = hoy - inicio
    semanas = delta.days / 7
    meses_totales = delta.days / 30.44  # aprox meses
    
    if semanas < 50:
        # Primer año: 1 día por mes completo trabajado
        return int(meses_totales)
    else:
        # 50+ semanas: 14 días por año completo
        anios = delta.days / 365.25
        return int(anios * 14)


def total_dias_vacaciones_tomados(empleado_id):
    """Suma los días de vacaciones ya tomados por el empleado."""
    conn = get_conn()
    row = conn.execute(
        "SELECT COALESCE(SUM(dias), 0) as total FROM vacaciones WHERE empleado_id=?",
        (empleado_id,)
    ).fetchone()
    conn.close()
    return row["total"] if row else 0


# ── PERMISOS ─────────────────────────────────────────────────────────────────

def add_permiso(empleado_id, fecha, motivo=None, notas=None):
    """Registra un permiso para un empleado en una fecha específica."""
    from datetime import date as _date
    try:
        dt = datetime.strptime(fecha, "%Y-%m-%d")
        anio = dt.year
        dias_semana_map = {
            0: "Lun", 1: "Mar", 2: "Mié", 3: "Jue",
            4: "Vie", 5: "Sáb", 6: "Dom"
        }
        dia_semana = dias_semana_map.get(dt.weekday(), "")
    except ValueError:
        print(f"add_permiso: fecha inválida '{fecha}', usando año actual sin día de semana")
        anio = _date.today().year
        dia_semana = ""

    conn = get_conn()
    conn.execute(
        """INSERT INTO permisos 
           (empleado_id, fecha, dia_semana, motivo, notas, anio, descontado_de_vacaciones, fecha_registro)
           VALUES (?, ?, ?, ?, ?, ?, 0, ?)""",
        (empleado_id, fecha, dia_semana, motivo, notas, anio, datetime.now().isoformat())
    )
    conn.commit()
    permiso_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return permiso_id


def get_permisos_empleado(empleado_id, anio=None):
    """Obtiene permisos de un empleado, opcionalmente filtrado por año."""
    conn = get_conn()
    if anio:
        rows = conn.execute(
            "SELECT * FROM permisos WHERE empleado_id=? AND anio=? ORDER BY fecha DESC",
            (empleado_id, anio)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM permisos WHERE empleado_id=? ORDER BY fecha DESC",
            (empleado_id,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_todos_permisos(anio=None):
    """Obtiene todos los permisos, opcionalmente filtrados por año."""
    conn = get_conn()
    if anio:
        rows = conn.execute(
            """SELECT p.*, e.nombre FROM permisos p 
               JOIN empleados e ON p.empleado_id = e.id 
               WHERE p.anio=? ORDER BY p.fecha DESC""",
            (anio,)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT p.*, e.nombre FROM permisos p 
               JOIN empleados e ON p.empleado_id = e.id 
               ORDER BY p.fecha DESC"""
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_conteo_permisos_anio(empleado_id, anio):
    """Retorna el conteo de permisos en un año y cuántos ya fueron descontados."""
    conn = get_conn()
    row = conn.execute(
        """SELECT COUNT(*) as total, 
           COALESCE(SUM(CASE WHEN descontado_de_vacaciones=1 THEN 1 ELSE 0 END), 0) as descontados
           FROM permisos WHERE empleado_id=? AND anio=?""",
        (empleado_id, anio)
    ).fetchone()
    conn.close()
    return {"total": row["total"], "descontados": row["descontados"],
            "pendientes": row["total"] - row["descontados"]}


def delete_permiso(permiso_id, restaurar_vacaciones=True):
    """Elimina un permiso. Si estaba descontado de vacaciones y restaurar=True, restaura los días."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM permisos WHERE id=?", (permiso_id,)).fetchone()
    if restaurar_vacaciones and row and row["descontado_de_vacaciones"] == 1:
        # Restaurar: buscar el registro de vacación por descuento y restar 1 día
        emp_id = row["empleado_id"]
        anio = row["anio"]
        vac_row = conn.execute(
            """SELECT id, dias FROM vacaciones 
               WHERE empleado_id=? AND notas LIKE ? ORDER BY id DESC LIMIT 1""",
            (emp_id, f"%Descuento por%permiso%{anio}%")
        ).fetchone()
        if vac_row:
            new_dias = vac_row["dias"] - 1
            if new_dias <= 0:
                conn.execute("DELETE FROM vacaciones WHERE id=?", (vac_row["id"],))
            else:
                conn.execute("UPDATE vacaciones SET dias=? WHERE id=?", (new_dias, vac_row["id"]))
    conn.execute("DELETE FROM permisos WHERE id=?", (permiso_id,))
    conn.commit()
    conn.close()


def descontar_permisos_de_vacaciones(empleado_id, cantidad, anio):
    """Descuenta permisos de los días de vacaciones creando un registro de vacación negativo.
    
    Marca los permisos como 'descontados' y crea un registro de vacación con
    los días negativos correspondientes.
    
    Returns: (success: bool, message: str)
    """
    conn = get_conn()
    # Verificar que hay suficientes permisos pendientes
    pendientes = conn.execute(
        """SELECT id FROM permisos 
           WHERE empleado_id=? AND anio=? AND descontado_de_vacaciones=0
           ORDER BY fecha""",
        (empleado_id, anio)
    ).fetchall()
    
    if len(pendientes) < cantidad:
        conn.close()
        return False, f"Solo hay {len(pendientes)} permisos pendientes para descontar"
    
    # Marcar los primeros N permisos como descontados
    for i in range(cantidad):
        conn.execute(
            "UPDATE permisos SET descontado_de_vacaciones=1 WHERE id=?",
            (pendientes[i]["id"],)
        )
    
    # Crear registro de vacación con los días descontados (como "Descuento por permisos")
    conn.execute(
        """INSERT INTO vacaciones 
           (empleado_id, fecha_inicio, fecha_fin, dias, fecha_reingreso, fecha_registro, notas) 
           VALUES (?, ?, ?, ?, NULL, ?, ?)""",
        (empleado_id, f"{anio}-01-01", f"{anio}-12-31", cantidad,
         datetime.now().isoformat(),
         f"Descuento por {cantidad} permiso(s) del año {anio}")
    )
    
    conn.commit()
    conn.close()
    return True, f"{cantidad} permiso(s) descontados de vacaciones"


# ── SINCRONIZACIÓN VACACIONES/PERMISOS → HORARIO ─────────────────────────────

def sync_vac_perm_to_fixed_shifts(empleado_nombre, fecha_inicio_semana, fecha_fin_semana):
    """Sincroniza vacaciones y permisos activos con los turnos fijos del horario.
    
    Dado un rango de fechas (viernes a jueves), verifica si el empleado tiene
    vacaciones o permisos en esos días y actualiza sus turnos_fijos.
    
    Args:
        empleado_nombre: nombre del empleado
        fecha_inicio_semana: fecha del viernes (inicio de semana laboral)
        fecha_fin_semana: fecha del jueves (fin de semana laboral)
    
    Returns: dict con los turnos_fijos actualizados
    """
    import json
    from datetime import timedelta
    
    conn = get_conn()
    
    # Obtener empleado_id
    emp = conn.execute("SELECT id FROM empleados WHERE nombre=?", (empleado_nombre,)).fetchone()
    if not emp:
        conn.close()
        return {}
    emp_id = emp["id"]
    
    # Obtener turnos_fijos actuales
    h_row = conn.execute(
        "SELECT turnos_fijos FROM horario_empleados WHERE nombre=?", (empleado_nombre,)
    ).fetchone()
    current_shifts = {}
    if h_row and h_row["turnos_fijos"]:
        try:
            current_shifts = json.loads(h_row["turnos_fijos"])
        except json.JSONDecodeError:
            print(f"sync_vac_perm_to_fixed_shifts: turnos_fijos JSON inválido para {empleado_nombre}")
            current_shifts = {}
    
    # Mapear fecha → día de la semana (Vie, Sáb, Dom, Lun, Mar, Mié, Jue)
    try:
        start = datetime.strptime(fecha_inicio_semana, "%Y-%m-%d").date()
        end = datetime.strptime(fecha_fin_semana, "%Y-%m-%d").date()
    except ValueError:
        print(f"sync_vac_perm_to_fixed_shifts: rango de fechas inválido inicio={fecha_inicio_semana}, fin={fecha_fin_semana}")
        conn.close()
        return current_shifts
    
    dia_map = {
        4: "Vie", 5: "Sáb", 6: "Dom", 0: "Lun", 1: "Mar", 2: "Mié", 3: "Jue"
    }
    
    # Iterar cada día de la semana
    current_date = start
    while current_date <= end:
        dia_nombre = dia_map.get(current_date.weekday(), "")
        fecha_str = current_date.strftime("%Y-%m-%d")
        
        if dia_nombre:
            # Verificar si hay vacación activa este día
            vac = conn.execute(
                """SELECT id FROM vacaciones 
                   WHERE empleado_id=? AND fecha_inicio <= ? AND fecha_fin >= ?""",
                (emp_id, fecha_str, fecha_str)
            ).fetchone()
            
            if vac:
                current_shifts[dia_nombre] = "VAC"
            else:
                # Verificar si hay permiso este día
                perm = conn.execute(
                    "SELECT id FROM permisos WHERE empleado_id=? AND fecha=?",
                    (emp_id, fecha_str)
                ).fetchone()
                if perm:
                    current_shifts[dia_nombre] = "PERM"
                else:
                    # Si había VAC o PERM antes y ya no aplica, quitar
                    if current_shifts.get(dia_nombre) in ["VAC", "PERM"]:
                        del current_shifts[dia_nombre]
        
        current_date += timedelta(days=1)
    
    # Guardar los turnos actualizados
    conn.execute(
        "UPDATE horario_empleados SET turnos_fijos=? WHERE nombre=?",
        (json.dumps(current_shifts, ensure_ascii=False), empleado_nombre)
    )
    conn.commit()
    conn.close()
    
    return current_shifts


# ── PRÉSTAMOS ─────────────────────────────────────────────────────────────────

def add_prestamo(empleado_id, monto_total, pago_semanal, notas=None):
    """Crea un nuevo préstamo para un empleado."""
    conn = get_conn()
    fecha = datetime.now().strftime("%Y-%m-%d")
    conn.execute(
        """INSERT INTO prestamos 
           (empleado_id, monto_total, pago_semanal, saldo, estado, fecha_inicio, notas, fecha_registro)
           VALUES (?, ?, ?, ?, 'activo', ?, ?, ?)""",
        (empleado_id, monto_total, pago_semanal, monto_total, fecha, notas, datetime.now().isoformat())
    )
    conn.commit()
    pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return pid


def get_prestamos_empleado(empleado_id, solo_activos=False):
    conn = get_conn()
    if solo_activos:
        rows = conn.execute(
            "SELECT * FROM prestamos WHERE empleado_id=? AND estado='activo' ORDER BY fecha_inicio DESC",
            (empleado_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM prestamos WHERE empleado_id=? ORDER BY fecha_inicio DESC",
            (empleado_id,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_todos_prestamos_activos():
    conn = get_conn()
    rows = conn.execute(
        """SELECT p.*, e.nombre FROM prestamos p
           JOIN empleados e ON p.empleado_id = e.id
           WHERE p.estado='activo' ORDER BY e.nombre"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_prestamo(prestamo_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM prestamos WHERE id=?", (prestamo_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def _recalcular_prestamo_conn(conn, prestamo_id):
    """Recalcula saldo y estado desde los abonos realmente registrados."""
    prest = conn.execute(
        "SELECT id, monto_total FROM prestamos WHERE id=?",
        (prestamo_id,)
    ).fetchone()
    if not prest:
        return None

    total_abonos_row = conn.execute(
        "SELECT COALESCE(SUM(monto), 0) AS total FROM prestamo_abonos WHERE prestamo_id=?",
        (prestamo_id,)
    ).fetchone()
    total_abonos = float(total_abonos_row["total"] or 0)
    monto_total = float(prest["monto_total"] or 0)
    saldo = max(round(monto_total - total_abonos, 2), 0)

    fecha_liquidacion = None
    estado = "activo"
    if saldo <= 0:
        estado = "liquidado"
        last_abono = conn.execute(
            "SELECT MAX(fecha) AS fecha FROM prestamo_abonos WHERE prestamo_id=?",
            (prestamo_id,)
        ).fetchone()
        fecha_liquidacion = (
            last_abono["fecha"]
            if last_abono and last_abono["fecha"]
            else datetime.now().strftime("%Y-%m-%d")
        )

    conn.execute(
        "UPDATE prestamos SET saldo=?, estado=?, fecha_liquidacion=? WHERE id=?",
        (saldo, estado, fecha_liquidacion, prestamo_id)
    )
    return {"saldo": saldo, "estado": estado, "fecha_liquidacion": fecha_liquidacion}


def recalcular_prestamo(prestamo_id):
    conn = get_conn()
    try:
        data = _recalcular_prestamo_conn(conn, prestamo_id)
        conn.commit()
        return data
    finally:
        conn.close()


def add_abono(prestamo_id, monto, tipo='planilla', semana_planilla=None, notas=None, fecha=None):
    """Registra un abono a un préstamo y recalcula el saldo."""
    conn = get_conn()
    fecha = fecha or datetime.now().strftime("%Y-%m-%d")
    conn.execute(
        """INSERT INTO prestamo_abonos
           (prestamo_id, monto, tipo, fecha, semana_planilla, notas, fecha_registro)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (prestamo_id, monto, tipo, fecha, semana_planilla, notas, datetime.now().isoformat())
    )
    _recalcular_prestamo_conn(conn, prestamo_id)
    conn.commit()
    abono_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return abono_id


def get_abonos(prestamo_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM prestamo_abonos WHERE prestamo_id=? ORDER BY fecha DESC",
        (prestamo_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_prestamo(prestamo_id):
    conn = get_conn()
    conn.execute("DELETE FROM prestamo_abonos WHERE prestamo_id=?", (prestamo_id,))
    conn.execute("DELETE FROM prestamos WHERE id=?", (prestamo_id,))
    conn.commit()
    conn.close()


def get_rebajo_prestamo_empleado(empleado_id):
    """Retorna el monto de rebajo semanal para un empleado con préstamo activo."""
    conn = get_conn()
    row = conn.execute(
        "SELECT pago_semanal, saldo FROM prestamos WHERE empleado_id=? AND estado='activo' LIMIT 1",
        (empleado_id,)
    ).fetchone()
    conn.close()
    if row:
        return min(row["pago_semanal"], row["saldo"])
    return 0


# ── TARIFAS ──────────────────────────────────────────────────────────────────

def get_tarifas():
    conn = get_conn()
    row = conn.execute("SELECT * FROM tarifas WHERE id=1").fetchone()
    conn.close()
    if not row:
        return {
            "tarifa_diurna": 50.0,
            "tarifa_nocturna": 75.0,
            "tarifa_mixta": 62.5,
            "seguro": 10498.0,
            "seguro_modo": "porcentual",
            "seguro_valor": 0.1067,
        }
    d = dict(row)
    if d.get("seguro_modo") is None:
        d["seguro_modo"] = "porcentual"
    if d.get("seguro_valor") is None:
        d["seguro_valor"] = 0.1067
    return d


def set_tarifas(diurna, nocturna, mixta, seguro_modo, seguro_valor):
    conn = get_conn()
    conn.execute(
        """
        UPDATE tarifas SET
            tarifa_diurna=?, tarifa_nocturna=?, tarifa_mixta=?,
            seguro_modo=?, seguro_valor=?
        WHERE id=1
        """,
        (diurna, nocturna, mixta, seguro_modo, seguro_valor),
    )
    conn.commit()
    conn.close()


# ── MESES Y SEMANAS ─────────────────────────────────────────────────────────

def get_mes_activo():
    """Retorna el mes activo (no cerrado) o None."""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM meses WHERE cerrado=0 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def crear_mes(anio, mes, archivo):
    conn = get_conn()
    # Evitar duplicados: si ya existe un mes activo para este año+mes, devolverlo
    existing = conn.execute(
        "SELECT * FROM meses WHERE anio=? AND mes=? AND cerrado=0", (anio, mes)
    ).fetchone()
    if existing:
        conn.close()
        return dict(existing)
    conn.execute(
        "INSERT INTO meses (anio, mes, archivo, fecha_creacion) VALUES (?, ?, ?, ?)",
        (anio, mes, archivo, datetime.now().isoformat())
    )
    conn.commit()
    mes_row = conn.execute("SELECT * FROM meses ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return dict(mes_row)


def cerrar_mes(mes_id):
    conn = get_conn()
    conn.execute("UPDATE meses SET cerrado=1 WHERE id=?", (mes_id,))
    conn.commit()
    conn.close()


def get_semanas_del_mes(mes_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM semanas WHERE mes_id=? ORDER BY num_semana", (mes_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_semana(mes_id, num_semana, viernes_str):
    conn = get_conn()
    conn.execute(
        "INSERT INTO semanas (mes_id, num_semana, viernes, fecha_agregada) VALUES (?, ?, ?, ?)",
        (mes_id, num_semana, viernes_str, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def delete_semana(semana_id):
    """Elimina una semana del registro."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM semanas WHERE id=?", (semana_id,)).fetchone()
    conn.execute("DELETE FROM semanas WHERE id=?", (semana_id,))
    conn.commit()
    conn.close()
    return dict(row) if row else None


def get_todos_meses():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM meses ORDER BY anio DESC, mes DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_mes(mes_id):
    """Elimina un mes y todas sus semanas asociadas de la base de datos.
    
    No elimina el archivo Excel físico — eso se maneja desde el endpoint.
    """
    conn = get_conn()
    # Primero eliminar semanas (FK dependencia)
    conn.execute("DELETE FROM semanas WHERE mes_id=?", (mes_id,))
    # Luego eliminar salarios relacionados: buscar anio/mes del registro
    mes_row = conn.execute("SELECT anio, mes FROM meses WHERE id=?", (mes_id,)).fetchone()
    if mes_row:
        conn.execute(
            "DELETE FROM salarios_mensuales WHERE anio=? AND mes=?",
            (mes_row["anio"], mes_row["mes"])
        )
    conn.execute("DELETE FROM meses WHERE id=?", (mes_id,))
    conn.commit()
    conn.close()


# ── AGUINALDO ────────────────────────────────────────────────────────────────

def get_meses_del_anio(anio):
    """Obtiene todos los meses cerrados de un año específico, sin duplicados por archivo."""
    conn = get_conn()
    # GROUP BY archivo evita procesar el mismo Excel varias veces si hay
    # registros duplicados de un mismo mes (e.g. creados durante pruebas).
    rows = conn.execute(
        """SELECT MIN(id) as id, anio, mes, archivo, MIN(fecha_creacion) as fecha_creacion, MAX(cerrado) as cerrado
           FROM meses WHERE anio=? AND cerrado=1
           GROUP BY archivo ORDER BY mes""",
        (anio,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── SALARIOS MENSUALES ───────────────────────────────────────────────────────

def guardar_salario_semanal(empleado_id, empleado_nombre, anio, mes, semana, salario_bruto):
    """Guarda o actualiza el salario bruto de una semana para un empleado."""
    conn = get_conn()
    # Check if already exists
    existing = conn.execute(
        "SELECT id FROM salarios_mensuales WHERE empleado_id=? AND anio=? AND mes=? AND semana=?",
        (empleado_id, anio, mes, semana)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE salarios_mensuales SET salario_bruto=?, empleado_nombre=?, fecha_registro=? WHERE id=?",
            (salario_bruto, empleado_nombre, datetime.now().isoformat(), existing['id'])
        )
    else:
        conn.execute(
            "INSERT INTO salarios_mensuales (empleado_id, empleado_nombre, anio, mes, semana, salario_bruto, fecha_registro) VALUES (?,?,?,?,?,?,?)",
            (empleado_id, empleado_nombre, anio, mes, semana, salario_bruto, datetime.now().isoformat())
        )
    conn.commit()
    conn.close()


def get_salarios_anio(anio):
    """Retorna todos los registros de salarios de un año."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM salarios_mensuales WHERE anio=? ORDER BY empleado_nombre, mes, semana", (anio,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_salarios_anio_desglose(anio):
    """Retorna desglose mensual agrupado por empleado para cálculo de aguinaldo."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT empleado_id, empleado_nombre, mes, SUM(salario_bruto) as total_bruto
        FROM salarios_mensuales
        WHERE anio=?
        GROUP BY empleado_id, mes
        ORDER BY empleado_nombre, mes
    """, (anio,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── INVENTARIO ───────────────────────────────────────────────────────────────

def guardar_carga_inventario(fecha, archivo_nombre, articulos_list):
    """Guarda una carga de inventario con sus artículos.
    
    articulos_list: lista de dicts con keys: codigo, nombre, precio, existencias
    """
    conn = get_conn()
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT INTO inventario_cargas (fecha, archivo_nombre, total_articulos, fecha_registro) VALUES (?, ?, ?, ?)",
        (fecha, archivo_nombre, len(articulos_list), datetime.now().isoformat())
    )
    carga_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    for art in articulos_list:
        conn.execute(
            "INSERT INTO inventario_articulos (carga_id, codigo, nombre, precio, existencias) VALUES (?, ?, ?, ?, ?)",
            (carga_id, art.get('codigo', ''), art.get('nombre', ''), art.get('precio', 0), art.get('existencias', 0))
        )
    conn.commit()
    conn.close()
    return carga_id


def get_ultima_carga():
    """Devuelve la carga más reciente con sus artículos."""
    conn = get_conn()
    carga = conn.execute("SELECT * FROM inventario_cargas ORDER BY id DESC LIMIT 1").fetchone()
    if not carga:
        conn.close()
        return None
    articulos = conn.execute(
        "SELECT * FROM inventario_articulos WHERE carga_id=? ORDER BY nombre", (carga['id'],)
    ).fetchall()
    conn.close()
    return {'carga': dict(carga), 'articulos': [dict(a) for a in articulos]}


def get_carga_por_id(carga_id):
    """Devuelve una carga específica con sus artículos."""
    conn = get_conn()
    carga = conn.execute("SELECT * FROM inventario_cargas WHERE id=?", (carga_id,)).fetchone()
    if not carga:
        conn.close()
        return None
    articulos = conn.execute(
        "SELECT * FROM inventario_articulos WHERE carga_id=? ORDER BY nombre", (carga_id,)
    ).fetchall()
    conn.close()
    return {'carga': dict(carga), 'articulos': [dict(a) for a in articulos]}


def get_carga_anterior(carga_id):
    """Devuelve la carga inmediatamente anterior a carga_id."""
    conn = get_conn()
    carga = conn.execute(
        "SELECT * FROM inventario_cargas WHERE id < ? ORDER BY id DESC LIMIT 1", (carga_id,)
    ).fetchone()
    if not carga:
        conn.close()
        return None
    articulos = conn.execute(
        "SELECT * FROM inventario_articulos WHERE carga_id=? ORDER BY nombre", (carga['id'],)
    ).fetchall()
    conn.close()
    return {'carga': dict(carga), 'articulos': [dict(a) for a in articulos]}


def get_historial_cargas(limit=30):
    """Lista de cargas recientes sin artículos."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM inventario_cargas ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_carga_inventario(carga_id):
    """Elimina una carga y sus artículos (ON DELETE CASCADE)."""
    conn = get_conn()
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("DELETE FROM inventario_articulos WHERE carga_id=?", (carga_id,))
    conn.execute("DELETE FROM inventario_cargas WHERE id=?", (carga_id,))
    conn.commit()
    conn.close()


def get_articulos_carga(carga_id):
    """Artículos de una carga específica."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM inventario_articulos WHERE carga_id=? ORDER BY nombre", (carga_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def replace_inventario_base(articulos, source_path=None):
    """Reemplaza la base maestra de inventario."""
    conn = get_conn()
    conn.execute("DELETE FROM inventario_base_articulos")
    for idx, art in enumerate(articulos, start=1):
        conn.execute(
            """
            INSERT INTO inventario_base_articulos
            (codigo, nombre, precio, existencias_base, hoja_origen, orden, activo)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (
                art.get("codigo", ""),
                art.get("nombre", "").strip(),
                art.get("precio", 0),
                art.get("existencias_base", 0),
                art.get("hoja_origen"),
                art.get("orden", idx),
            ),
        )
    conn.execute(
        """
        INSERT INTO inventario_base_config (id, source_path, last_imported_at)
        VALUES (1, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            source_path=excluded.source_path,
            last_imported_at=excluded.last_imported_at
        """,
        (source_path, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def get_inventario_base():
    conn = get_conn()
    items = conn.execute(
        """
        SELECT * FROM inventario_base_articulos
        WHERE COALESCE(activo, 1)=1
        ORDER BY hoja_origen, orden, nombre
        """
    ).fetchall()
    cfg = conn.execute(
        "SELECT * FROM inventario_base_config WHERE id=1"
    ).fetchone()
    conn.close()
    return {
        "config": dict(cfg) if cfg else None,
        "articulos": [dict(r) for r in items],
    }


def upsert_inventario_base_articulo(articulo):
    conn = get_conn()
    art_id = articulo.get("id")
    payload = (
        articulo.get("codigo", ""),
        articulo.get("nombre", "").strip(),
        articulo.get("precio", 0),
        articulo.get("existencias_base", 0),
        articulo.get("hoja_origen"),
        articulo.get("orden", 999999),
    )
    if art_id:
        conn.execute(
            """
            UPDATE inventario_base_articulos
            SET codigo=?, nombre=?, precio=?, existencias_base=?, hoja_origen=?, orden=?, activo=1
            WHERE id=?
            """,
            payload + (art_id,),
        )
        new_id = art_id
    else:
        conn.execute(
            """
            INSERT INTO inventario_base_articulos
            (codigo, nombre, precio, existencias_base, hoja_origen, orden, activo)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            payload,
        )
        new_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return new_id


def delete_inventario_base_articulo(articulo_id):
    conn = get_conn()
    conn.execute("DELETE FROM inventario_base_articulos WHERE id=?", (articulo_id,))
    conn.commit()
    conn.close()




# -- DOCUMENTOS RRHH ----------------------------------------------------------

def _next_rrhh_codigo(tipo):
    """Genera el siguiente codigo RRHH: RRHH-TIPO-YYYY-NNNN."""
    conn = get_conn()
    anio = datetime.now().year
    prefix = f"RRHH-{tipo.upper()[:4]}-{anio}-"
    row = conn.execute(
        "SELECT codigo FROM documentos_rrhh WHERE codigo LIKE ? ORDER BY id DESC LIMIT 1",
        (f"{prefix}%",)
    ).fetchone()
    conn.close()
    if row:
        last_num = int(row["codigo"].split("-")[-1])
        return f"{prefix}{last_num + 1:04d}"
    return f"{prefix}0001"


def registrar_documento_rrhh(tipo, empleado_id, empleado_nombre, datos_json, ruta_archivo):
    """Registra un documento generado y devuelve el codigo RRHH."""
    codigo = _next_rrhh_codigo(tipo)
    conn = get_conn()
    conn.execute(
        """INSERT INTO documentos_rrhh
           (codigo, tipo, empleado_id, empleado_nombre, datos_json, ruta_archivo, fecha_generacion)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (codigo, tipo, empleado_id, empleado_nombre, datos_json, ruta_archivo,
         datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    return codigo


def get_documentos_rrhh(empleado_id=None, tipo=None, limit=50):
    """Lista documentos RRHH con filtros opcionales."""
    conn = get_conn()
    q = "SELECT * FROM documentos_rrhh WHERE 1=1"
    params = []
    if empleado_id:
        q += " AND empleado_id=?"
        params.append(empleado_id)
    if tipo:
        q += " AND tipo=?"
        params.append(tipo)
    q += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _migrate_dia_libre_forzado_into_turnos_fijos():
    """Una vez: copia dia_libre_forzado → turnos_fijos[día]=OFF y limpia la columna legada."""
    conn = get_conn()
    try:
        if not _column_exists(conn, "horario_empleados", "dia_libre_forzado"):
            return
        rows = conn.execute(
            "SELECT nombre, turnos_fijos, dia_libre_forzado FROM horario_empleados"
        ).fetchall()
        for r in rows:
            dlf = (r["dia_libre_forzado"] or "").strip()
            if not dlf or dlf not in _HORARIO_DIAS:
                continue
            raw_tf = r["turnos_fijos"] or "{}"
            try:
                tf = json.loads(raw_tf) if raw_tf else {}
            except (json.JSONDecodeError, TypeError):
                tf = {}
            if not isinstance(tf, dict):
                tf = {}
            existing = tf.get(dlf)
            ex = str(existing).strip() if existing is not None else ""
            if not ex:
                tf[dlf] = "OFF"
                conn.execute(
                    "UPDATE horario_empleados SET turnos_fijos=?, dia_libre_forzado=? WHERE nombre=?",
                    (json.dumps(tf, ensure_ascii=False), "", r["nombre"]),
                )
            elif ex in ("OFF", "VAC", "PERM"):
                conn.execute(
                    "UPDATE horario_empleados SET dia_libre_forzado=? WHERE nombre=?",
                    ("", r["nombre"]),
                )
            else:
                # Conflicto con turno ya fijado en pills: no sobrescribir; dejar de usar la columna legada.
                conn.execute(
                    "UPDATE horario_empleados SET dia_libre_forzado=? WHERE nombre=?",
                    ("", r["nombre"]),
                )
        conn.commit()
    finally:
        conn.close()


# Inicializar al importar
init_db()

# Migración: agregar columna dia_libre_forzado si no existe (legado; ya no se expone en API)
_ensure_column("horario_empleados", "dia_libre_forzado", "TEXT DEFAULT ''")
_migrate_dia_libre_forzado_into_turnos_fijos()
_ensure_pref_plantilla_schema()
