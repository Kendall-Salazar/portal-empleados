"""
database.py - Módulo de acceso a datos SQLite para el Gestor de Planilla
=========================================================================
Maneja empleados, tarifas, meses y semanas generadas.
"""
import sqlite3
import os
from datetime import datetime

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "planilla.db")


def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


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
            strict_preferences INTEGER DEFAULT 0,
            turnos_fijos TEXT DEFAULT '{}',
            activo INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS horario_config (
            id INTEGER PRIMARY KEY DEFAULT 1,
            night_mode TEXT DEFAULT 'rotation',
            fixed_night_person TEXT,
            allow_long_shifts INTEGER DEFAULT 0,
            use_refuerzo INTEGER DEFAULT 0,
            refuerzo_type TEXT DEFAULT 'diurno',
            allow_collision_quebrado INTEGER DEFAULT 0,
            collision_peak_priority TEXT DEFAULT 'pm',
            sunday_cycle_index INTEGER DEFAULT 0,
            sunday_rotation_queue TEXT
        );

        CREATE TABLE IF NOT EXISTS horarios_generados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            horario TEXT NOT NULL,
            tareas TEXT,
            metadata TEXT,
            timestamp TEXT NOT NULL
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
    # Migration: add cedula column if it doesn't exist
    conn = get_conn()
    try:
        conn.execute("ALTER TABLE empleados ADD COLUMN cedula TEXT")
        conn.commit()
    except Exception:
        pass  # Column already exists
    conn.close()
    
    # Migration: add strict_preferences column if it doesn't exist
    conn = get_conn()
    try:
        conn.execute("ALTER TABLE horario_empleados ADD COLUMN strict_preferences INTEGER DEFAULT 0")
        conn.commit()
    except Exception:
        pass  # Column already exists
    conn.close()

    # Migration: add correo, telefono, fecha_inicio, aplica_seguro columns
    _migrations = [
        ("empleados", "correo", "TEXT"),
        ("empleados", "telefono", "TEXT"),
        ("empleados", "fecha_inicio", "TEXT"),
        ("empleados", "aplica_seguro", "INTEGER DEFAULT 1"),
    ]
    for table, col, col_type in _migrations:
        conn = get_conn()
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
            conn.commit()
        except Exception:
            pass
        conn.close()

    # Create vacaciones table
    conn = get_conn()
    conn.executescript("""
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
               COALESCE(h.strict_preferences, 0) as strict_preferences,
               COALESCE(h.turnos_fijos, '{{}}') as turnos_fijos
        FROM empleados e
        LEFT JOIN horario_empleados h ON e.nombre = h.nombre
        {where}
        ORDER BY e.nombre
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_empleado(nombre, tipo_pago, salario_fijo=None, cedula=None,
                 correo=None, telefono=None, fecha_inicio=None,
                 aplica_seguro=1, genero='M', puede_nocturno=1,
                 forced_libres=0, forced_quebrado=0, allow_no_rest=0,
                 es_jefe_pista=0, strict_preferences=0, turnos_fijos='{}'):
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
                "INSERT INTO horario_empleados (nombre, genero, puede_nocturno, forced_libres, forced_quebrado, allow_no_rest, es_jefe_pista, strict_preferences, turnos_fijos) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (nombre.strip(), genero, puede_nocturno, forced_libres, forced_quebrado, allow_no_rest, es_jefe_pista, strict_preferences, turnos_fijos)
            )
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
    """Alias for remove_empleado (soft delete)."""
    remove_empleado(emp_id)


def reactivar_empleado(emp_id):
    conn = get_conn()
    row = conn.execute("SELECT nombre FROM empleados WHERE id=?", (emp_id,)).fetchone()
    conn.execute("UPDATE empleados SET activo=1 WHERE id=?", (emp_id,))
    if row:
        conn.execute("UPDATE horario_empleados SET activo=1 WHERE nombre=?", (row["nombre"],))
    conn.commit()
    conn.close()


def update_empleado(emp_id, nombre=None, tipo_pago=None, salario_fijo=None,
                    cedula=None, correo=None, telefono=None, fecha_inicio=None,
                    aplica_seguro=None, genero=None, puede_nocturno=None,
                    forced_libres=None, forced_quebrado=None, allow_no_rest=None,
                    es_jefe_pista=None, strict_preferences=None, turnos_fijos=None):
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
        if strict_preferences is not None:
            conn.execute("UPDATE horario_empleados SET strict_preferences=? WHERE nombre=?", (strict_preferences, old_name))
        if turnos_fijos is not None:
            conn.execute("UPDATE horario_empleados SET turnos_fijos=? WHERE nombre=?", (turnos_fijos, old_name))

    conn.commit()
    conn.close()


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


# ── TARIFAS ──────────────────────────────────────────────────────────────────

def get_tarifas():
    conn = get_conn()
    row = conn.execute("SELECT * FROM tarifas WHERE id=1").fetchone()
    conn.close()
    return dict(row) if row else {
        "tarifa_diurna": 50.0, "tarifa_nocturna": 75.0,
        "tarifa_mixta": 62.5, "seguro": 10498.0
    }


def set_tarifas(diurna, nocturna, mixta, seguro):
    conn = get_conn()
    conn.execute(
        "UPDATE tarifas SET tarifa_diurna=?, tarifa_nocturna=?, tarifa_mixta=?, seguro=? WHERE id=1",
        (diurna, nocturna, mixta, seguro)
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


# Inicializar al importar
init_db()