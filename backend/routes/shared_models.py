"""Shared Pydantic models for the Cronos scheduling system."""

from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any


# ── Solver / Schedule models ─────────────────────────────────────────────────

class Employee(BaseModel):
    name: str
    gender: str = "M"
    can_do_night: bool = True
    allow_no_rest: bool = False
    forced_libres: bool = False
    forced_quebrado: bool = False
    forced_quebrado_partial: bool = False
    quebrado_preferido: str = "auto"
    is_jefe_pista: bool = False
    is_practicante: bool = False
    strict_preferences: bool = False
    activo: bool = True
    incluir_en_horario: bool = True
    fixed_shifts: Dict[str, str] = Field(default_factory=dict)


class Config(BaseModel):
    night_mode: str = "rotation"
    fixed_night_person: Optional[str] = None
    allow_long_shifts: bool = False
    use_refuerzo: bool = False
    refuerzo_type: str = "personalizado"
    refuerzo_start: str = "07:00"
    refuerzo_end: str = "12:00"
    refuerzo_days_mode: str = "auto"  # "auto" = solver decide, "manual" = usuario elige
    refuerzo_manual_days: List[str] = []  # Días específicos cuando refuerzo_days_mode="manual"
    allow_collision_quebrado: bool = False
    allow_quebrado_largo: bool = False
    collision_peak_priority: str = "pm"
    use_history: bool = True
    sunday_cycle_index: int = 0  # Legacy, kept for backwards compat
    sunday_rotation_queue: Optional[List[str]] = None
    strict_weekly_alternation: bool = False
    custom_shifts: list = []
    holidays: list = []  # Días festivos [{date: "YYYY-MM-DD", name: "..."}]
    prioritize_jefe_coverage: bool = True  # Suavizar objetivo: favorece asignar turnos al jefe cuando el solver elige
    jefe_base_shift: str = "J_06-16"  # Turno tipo lun–vie al aplicar plantilla de jefe desde Parámetros
    use_pref_plantilla: bool = False  # Si False, el motor ignora horario_pref_plantilla (preferencias en turnos_fijos)
    cleaning_tasks: Optional[Dict[str, Dict[str, bool]]] = None
    jefe_config: Optional[Dict[str, Any]] = None


class SolverRequest(BaseModel):
    employees: List[Employee]
    config: Config
    target_week_start: Optional[str] = None
    special_days: Dict[str, str] = Field(default_factory=dict)


class HistoryEntry(BaseModel):
    name: str
    schedule: Dict[str, Dict[str, str]]
    daily_tasks: Dict[str, Dict[str, Optional[str]]] = Field(default_factory=dict)
    next_sunday_cycle_index: Optional[int] = None  # Legacy
    next_sunday_rotation_queue: Optional[List[str]] = None
    week_dates: Optional[Dict[str, str]] = None
    special_days: Dict[str, str] = Field(default_factory=dict)
    timestamp: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ── Partial solver models (from horarios.py) ─────────────────────────────────

class PartialOffClassification(BaseModel):
    """
    Clasificación de un día libre (OFF/VAC/PERM) que el usuario hace
    de forma manual en la UI del Generador Parcial.

    fixed=True  → el solver DEBE respetar ese libre (se inyecta en fixed_shifts).
    fixed=False → el solver PUEDE reasignarlo si la cobertura lo requiere.
    """
    employee: str
    day: str      # "Vie" | "Sáb" | "Dom" | "Lun" | "Mar" | "Mié" | "Jue"
    fixed: bool   # True = fijo, False = flexible (reasignable)


class DepartedEmployee(BaseModel):
    """
    Empleado que causó baja durante la semana.
    last_working_day: último día que trabajó. A partir del día siguiente se
    excluye del pool del solver y la celda aparece vacía en el resultado.
    """
    name: str
    last_working_day: str  # Último día trabajado, p.ej. "Dom"


class PartialSolverRequest(BaseModel):
    """
    Request completo para la generación parcial.
    El frontend envía el db_id del horario base junto con la configuración
    de qué días bloquear, quién se fue y cómo tratar los libres.
    """
    base_history_db_id: int                   # id en horarios_generados
    config: Config
    target_week_start: Optional[str] = None   # Fecha del viernes de la semana
    special_days: Dict[str, str] = Field(default_factory=dict)
    locked_days: List[str] = Field(default_factory=list)   # Días pasados, p.ej. ["Vie","Sáb","Dom"]
    departed_employees: List[DepartedEmployee] = Field(default_factory=list)
    off_classifications: List[PartialOffClassification] = Field(default_factory=list)


# ── Planilla models ──────────────────────────────────────────────────────────

class PlanillaPermiso(BaseModel):
    empleado_id: int
    fecha: str
    motivo: Optional[str] = None
    notas: Optional[str] = None
    fecha_fin: Optional[str] = None
    horas: Optional[float] = 0


class DescontarPermisosRequest(BaseModel):
    empleado_id: int
    cantidad: int
    anio: int


class SyncVacPermRequest(BaseModel):
    fecha_inicio: str
    fecha_fin: str


class PlanillaEmpleado(BaseModel):
    nombre: str
    tipo_pago: str
    salario_fijo: Optional[float] = None
    # semanal | quincenal | mensual — el monto salario_fijo es el pago de ese período (solo tipo fijo)
    periodo_salario_fijo: Optional[str] = "mensual"
    cedula: Optional[str] = None
    correo: Optional[str] = None
    telefono: Optional[str] = None
    fecha_inicio: Optional[str] = None
    aplica_seguro: Optional[int] = 1
    genero: Optional[str] = 'M'
    puede_nocturno: Optional[int] = 1
    forced_libres: Optional[int] = 0
    forced_quebrado: Optional[int] = 0
    allow_no_rest: Optional[int] = 0
    es_jefe_pista: Optional[int] = 0
    es_practicante: Optional[int] = 0
    strict_preferences: Optional[int] = 0
    activo: Optional[int] = 1
    incluir_en_horario: Optional[int] = 1
    turnos_fijos: Optional[str] = "{}"
    pref_plantilla_id: Optional[int] = None


class PlanillaEmpleadoUpdate(BaseModel):
    """PUT parcial: solo los campos enviados se persisten (no pisa horario si se omiten)."""

    model_config = ConfigDict(extra="forbid")

    nombre: str
    tipo_pago: str
    salario_fijo: Optional[float] = None
    periodo_salario_fijo: Optional[str] = None
    cedula: Optional[str] = None
    correo: Optional[str] = None
    telefono: Optional[str] = None
    fecha_inicio: Optional[str] = None
    aplica_seguro: Optional[int] = None
    genero: Optional[str] = None
    puede_nocturno: Optional[int] = None
    activo: Optional[int] = None
    incluir_en_horario: Optional[int] = None
    forced_libres: Optional[int] = None
    forced_quebrado: Optional[int] = None
    allow_no_rest: Optional[int] = None
    es_jefe_pista: Optional[int] = None
    es_practicante: Optional[int] = None
    strict_preferences: Optional[int] = None
    turnos_fijos: Optional[str] = None


# ── Generator / Param models ─────────────────────────────────────────────────

class GeneratorParamFlags(BaseModel):
    forced_libres: Optional[bool] = None
    forced_quebrado: Optional[bool] = None
    forced_quebrado_partial: Optional[bool] = None
    quebrado_preferido: Optional[str] = None
    allow_no_rest: Optional[bool] = None
    strict_preferences: Optional[bool] = None
    is_jefe_pista: Optional[bool] = None


class GeneratorEmployeeUpdate(BaseModel):
    employee_id: int
    flags: Optional[GeneratorParamFlags] = None
    shift_preferences: Optional[Dict[str, str]] = None
    pref_plantilla_id: Optional[int] = None


class GeneratorParamsBatchPut(BaseModel):
    week_start: Optional[str] = None
    updates: List[GeneratorEmployeeUpdate]


class GeneratorSyncRrhhRequest(BaseModel):
    week_start: str


# ── Import / Export models ───────────────────────────────────────────────────

class HorarioExcelImportItem(BaseModel):
    name: str = Field(min_length=1)
    schedule: Dict[str, Dict[str, str]]
    week_dates: Dict[str, str]
    daily_tasks: Optional[Dict[str, Dict[str, Optional[str]]]] = None


class HorarioExcelImportConfirm(BaseModel):
    items: List[HorarioExcelImportItem]


# ── Validation / Utility models ──────────────────────────────────────────────

class ValidationRulesRequest(BaseModel):
    special_days: Dict[str, str] = Field(default_factory=dict)


class ImageExportRequest(BaseModel):
    image_data: str  # Base64 string
    filename: str = "horario.png"


# ── Folder models ────────────────────────────────────────────────────────────

class FolderCreate(BaseModel):
    name: str


class FolderAddEntries(BaseModel):
    entry_ids: List[int]
