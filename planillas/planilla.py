import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, GradientFill
from openpyxl.styles.differential import DifferentialStyle
from openpyxl.formatting.rule import ColorScaleRule, DataBarRule
from openpyxl.utils import get_column_letter
from datetime import datetime, timedelta

# ══════════════════════════════════════════════════════════════════════════════
#  PALETA DE COLORES
# ══════════════════════════════════════════════════════════════════════════════
F_DEFAULT      = "Calibri"

C_DARK_BLUE    = "0F1923"   # Fondos título / gran total
C_TARJETA      = "1D4ED8"   # Sección PAGO POR TARJETA  (azul vibrante)
C_EFECTIVO     = "059669"   # Sección PAGO EN EFECTIVO  (verde esmeralda)
C_OCEAN        = "0369A1"   # Sub-encabezados días / horas
C_SLATE        = "243447"   # Sub-encabezados deducción
C_HDR_DARK     = "1B2838"   # Cabecera Empleado / Jornada
C_BRUTO_HDR    = "1E40AF"   # Cabecera Bruto
C_DED_HDR      = "991B1B"   # Cabeceras deducciones (Prestamo, etc.)
C_SEGURO_HDR   = "B45309"   # Cabecera Seguro
C_NETO_HDR     = "065F46"   # Cabecera NETO

C_EMP_TARJETA  = "DBEAFE"   # Celda nombre empleado — tarjeta
C_EMP_EFECT    = "D1FAE5"   # Celda nombre empleado — efectivo
C_INPUT        = "F0F9FF"   # Celdas de ingreso de horas
C_INPUT_ALT    = "E8F5E9"   # Celdas alternadas (horas mixtas/extra)
C_J_SUM        = "E0F2FE"   # Columna J totales horizontales
C_DED_CELL     = "FEF2F2"   # Celdas deducciones (M-P)
C_SEGURO_CELL  = "FFFBEB"   # Celda seguro
C_NETO_CELL    = "ECFDF5"   # Celda NETO
C_WHITE        = "FFFFFF"
C_TARIFA_BG    = "F5F3FF"   # Fila tarifas
C_TARIFA_LBL   = "4C1D95"   # Etiquetas tarifas
C_TARIFA_VAL   = "7C3AED"   # Valores tarifas
C_SUBTITLE     = "94A3B8"   # Texto secundario

# Tipos de pago / neto — fuentes de color
C_DED_FG       = "991B1B"
C_SEGURO_FG    = "92400E"
C_NETO_FG      = "065F46"

# Hoja Resumen Mensual — colores de sección total
C_RED_HDR      = "B91C1C"

MONEY    = '"₡"#,##0.00'
HOURS_FMT = '0.00'
SUMMARY_MONEY_FMT = '"₡"#,##0'
SUMMARY_HOURS_FMT = '0'
CCSS_RATE = 0.1067          # Aporte CCSS empleado Costa Rica

# ══════════════════════════════════════════════════════════════════════════════
#  COMPAT MAIN.PY
# ══════════════════════════════════════════════════════════════════════════════
ROW_1      = PatternFill("solid", fgColor=C_WHITE)
ROW_2      = PatternFill("solid", fgColor="F7F9FC")
SAMPLE_EMPS = []
TARIFA_DIURNA   = 50.0
TARIFA_NOCTURNA = 75.0
TARIFA_MIXTA    = 62.5

# Aliases para compatibilidad con main.py (que referencia pl_module.f_data, etc.)
from openpyxl.styles import Side as _Side, Border as _Border
f_data = Font(name=F_DEFAULT, size=10, color="1F2937")
borde  = Border(
    top   =_Side(border_style="thin", color="CBD5E1"),
    left  =_Side(border_style="thin", color="CBD5E1"),
    right =_Side(border_style="thin", color="CBD5E1"),
    bottom=_Side(border_style="thin", color="CBD5E1"),
)

# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS DE ESTILO
# ══════════════════════════════════════════════════════════════════════════════
al_c = Alignment(horizontal="center", vertical="center", wrap_text=False)
al_l = Alignment(horizontal="left",   vertical="center")
al_r = Alignment(horizontal="right",  vertical="center")

def _fill(color):
    return PatternFill("solid", fgColor=color)

def _font(size=10, bold=False, color="1F2937", name=F_DEFAULT):
    return Font(name=name, size=size, bold=bold, color=color)

def _side(style="thin", color="CBD5E1"):
    return Side(border_style=style, color=color)

def _border(left="thin", right="thin", top="thin", bottom="thin",
            lc="CBD5E1", rc="CBD5E1", tc="CBD5E1", bc="CBD5E1"):
    return Border(
        left   = Side(border_style=left,   color=lc),
        right  = Side(border_style=right,  color=rc),
        top    = Side(border_style=top,    color=tc),
        bottom = Side(border_style=bottom, color=bc),
    )

# Borde para celdas de datos normales
B_DATA  = _border()
# Borde izquierdo grueso para columna L (separador visual horas | dinero)
B_THICK_LEFT = _border(left="medium", lc="334155")
# Borde para filas de encabezado de sección total
B_TOTAL = _border(top="medium", tc="334155", bottom="medium", bc="334155")
# Borde de total con separador izquierdo grueso
B_TOTAL_THICK_LEFT = _border(left="medium", lc="334155",
                             top="medium", tc="334155",
                             bottom="medium", bc="334155")

def sc(ws, row, col, val, font=None, fill=None, align=None, border=None, num_format=None):
    c = ws.cell(row=row, column=col)
    if val is not None:
        c.value = val
    if font:       c.font       = font
    if fill:       c.fill       = fill
    if align:      c.alignment  = align
    if border:     c.border     = border
    if num_format: c.number_format = num_format

def _row_fill(ws, row, col_start, col_end, color):
    f = _fill(color)
    for c in range(col_start, col_end + 1):
        ws.cell(row=row, column=c).fill = f

def _summary_ref_or_blank(ref):
    return f'=IF(OR({ref}="",{ref}=0),"",{ref})'

def _summary_expr_or_blank(expr):
    return f'=IF(({expr})=0,"",({expr}))'

# ══════════════════════════════════════════════════════════════════════════════
#  UTILIDADES
# ══════════════════════════════════════════════════════════════════════════════
def num_semana_anual(date_obj):
    if isinstance(date_obj, str):
        date_obj = datetime.strptime(date_obj, "%Y-%m-%d").date()
    return date_obj.isocalendar()[1]

def leer_catalogo(wb):
    if "Catalogo" not in wb.sheetnames:
        return {"tarjeta": [], "efectivo": [], "fijo": []}
    ws = wb["Catalogo"]
    res = {"tarjeta": [], "efectivo": [], "fijo": []}
    for r in range(5, ws.max_row + 1):
        nom = ws.cell(r, 1).value
        if not nom:
            continue
        tipo = str(ws.cell(r, 2).value or "").lower()
        if "tarjeta" in tipo:
            res["tarjeta"].append(nom)
        elif "fijo" in tipo:
            res["fijo"].append(nom)
        else:
            res["efectivo"].append(nom)
    return res

def contar_semanas(wb):
    return sum(1 for s in wb.sheetnames if s.startswith("Semana "))

# ══════════════════════════════════════════════════════════════════════════════
#  HOJA SEMANAL — sección interna
# ══════════════════════════════════════════════════════════════════════════════
_DIAS_ES = ["Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue"]

def _write_section(ws, start_row, label, sec_color, emp_color, emp_list):
    """
    Escribe una sección (tarjeta / efectivo).
    Bloque por empleado: 4 filas (Diurnas, Mixtas, Nocturnas, Extra).
    Devuelve (next_free_row, total_row, anchor_rows_list).
    """
    COL_LAST = 19  # S

    # ── Encabezado de sección ──────────────────────────────────────────────
    ws.row_dimensions[start_row].height = 28
    ws.merge_cells(start_row=start_row, start_column=1,
                   end_row=start_row, end_column=COL_LAST)
    sc(ws, start_row, 1, f"  {label}",
       _font(12, True, C_WHITE), _fill(sec_color), al_l)
    r = start_row + 1

    # ── Sub-encabezado "Horas | Deducción" ────────────────────────────────
    ws.row_dimensions[r].height = 16
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
    sc(ws, r, 1, None, fill=_fill(C_SLATE))
    ws.merge_cells(start_row=r, start_column=3, end_row=r, end_column=10)
    sc(ws, r, 3, "HORAS POR JORNADA",
       _font(8, True, C_WHITE), _fill(C_OCEAN), al_c)
    sc(ws, r, 11, None, fill=_fill(C_WHITE))
    ws.merge_cells(start_row=r, start_column=12, end_row=r, end_column=COL_LAST)
    sc(ws, r, 12, "DEDUCCIONES / RESUMEN",
       _font(8, True, C_WHITE), _fill(C_SLATE), al_c)
    r += 1

    # ── Cabeceras de columna con día + fecha en una sola fila ─────────────
    ws.row_dimensions[r].height = 32
    col_hdrs = [
        (1,  "Empleado",  C_HDR_DARK),
        (2,  "Jornada",   C_HDR_DARK),
        (10, "TOTAL",     C_OCEAN),
        (11, "",          C_WHITE),
        (12, "Bruto",     C_BRUTO_HDR),
        (13, "Préstamo",  C_DED_HDR),
        (14, "Combust.",  C_DED_HDR),
        (15, "Mercad.",   C_DED_HDR),
        (16, "Adelanto",  C_DED_HDR),
        (17, "Seguro",    C_SEGURO_HDR),
        (18, "Tot. Ded.", C_DED_HDR),
        (19, "NETO",      C_NETO_HDR),
    ]
    for col, txt, bg in col_hdrs:
        sc(ws, r, col, txt or None,
           _font(9, True, C_WHITE), _fill(bg), al_c,
           B_THICK_LEFT if col == 12 else B_DATA)

    # Columnas días: "Vie\n06/03"  (texto fijo del día + fórmula de fecha)
    # Como openpyxl no puede mezclar texto+fórmula en una celda, usamos
    # concatenación: ="Vie"&CHAR(10)&TEXT($C$2+0,"DD/MM")
    for i, dia in enumerate(_DIAS_ES):
        col = 3 + i
        formula = f'="{dia}"&CHAR(10)&TEXT($C$2+{i},"DD/MM")'
        c = ws.cell(row=r, column=col)
        c.value         = formula
        c.font          = _font(9, True, C_WHITE)
        c.fill          = _fill(C_OCEAN)
        c.alignment     = Alignment(horizontal="center", vertical="center",
                                    wrap_text=True)
        c.border        = B_DATA
    r += 1

    # ── Bloques de empleados ───────────────────────────────────────────────
    anchor_rows = []
    conceptos = ["Hrs. Diurnas", "Hrs. Mixtas", "Hrs. Nocturnas", "Hrs. Extra"]
    # Fondo alternado para filas de concepto
    row_bgs   = [C_INPUT, C_INPUT_ALT, C_INPUT, C_INPUT_ALT]

    for emp in emp_list:
        anchor_rows.append(r)
        block_end = r + 3   # 4 filas (0..3)

        ws.row_dimensions[r].height     = 20
        ws.row_dimensions[r+1].height   = 20
        ws.row_dimensions[r+2].height   = 20
        ws.row_dimensions[r+3].height   = 20

        # Columna A — nombre empleado (mergeado 4 filas)
        ws.merge_cells(start_row=r, start_column=1,
                       end_row=block_end, end_column=1)
        sc(ws, r, 1, emp,
           _font(10, True), _fill(emp_color), al_c,
           _border(left="medium", lc="334155", right="thin", rc="CBD5E1",
                   top="medium", tc="334155", bottom="medium", bc="334155"))
        for ri in range(r+1, block_end+1):
            ws.cell(row=ri, column=1).border = _border(
                left="medium", lc="334155", right="thin", rc="CBD5E1",
                top="thin", tc="CBD5E1", bottom="thin", bc="CBD5E1")

        for i, (conc, bg) in enumerate(zip(conceptos, row_bgs)):
            ri   = r + i
            font_c = _font(9, False)
            fill_c = _fill(bg)

            # B — etiqueta concepto
            sc(ws, ri, 2, conc, font_c, fill_c, al_l, B_DATA)

            # C-I — celdas de ingreso de horas (editables)
            for ci in range(3, 10):
                c = ws.cell(row=ri, column=ci)
                c.value       = None
                c.font        = _font(10, False, "1E3A5F")
                c.fill        = _fill(C_WHITE)   # blanco puro → visualmente "ingresar aquí"
                c.alignment   = al_c
                c.border      = _border(lc="93C5FD", rc="93C5FD",
                                        tc="93C5FD", bc="93C5FD")
                c.number_format = HOURS_FMT

            # J — suma horizontal
            ws.cell(row=ri, column=10).value        = f"=C{ri}+D{ri}+E{ri}+F{ri}+G{ri}+H{ri}+I{ri}"
            ws.cell(row=ri, column=10).font         = _font(10, True, "0F4C81")
            ws.cell(row=ri, column=10).fill         = _fill(C_J_SUM)
            ws.cell(row=ri, column=10).alignment    = al_c
            ws.cell(row=ri, column=10).border       = B_DATA
            ws.cell(row=ri, column=10).number_format = HOURS_FMT

            # K — separador invisible
            ws.cell(row=ri, column=11).fill = _fill(C_WHITE)

        # ── Columnas de resumen / deducciones (mergeadas 4 filas) ─────────

        # L — Bruto  (borde izquierdo grueso para separar visualmente)
        ws.merge_cells(start_row=r, start_column=12, end_row=block_end, end_column=12)
        c = ws.cell(row=r, column=12)
        c.value         = f"=J{r}*$D$3+J{r+1}*$F$3+J{r+2}*$H$3+J{r+3}*$J$3"
        c.font          = _font(11, True, "1E3A5F")
        c.fill          = _fill(C_EMP_TARJETA if emp_color == C_EMP_TARJETA else C_EMP_EFECT)
        c.alignment     = al_c
        c.border        = _border(left="medium", lc="334155",
                                  right="thin",  rc="CBD5E1",
                                  top="medium",  tc="334155",
                                  bottom="medium", bc="334155")
        c.number_format = MONEY
        for ri in range(r+1, block_end+1):
            ws.cell(row=ri, column=12).border = _border(
                left="medium", lc="334155", right="thin", rc="CBD5E1",
                top="thin", tc="CBD5E1", bottom="thin", bc="CBD5E1")

        # M-P — Deducciones ingresables
        for col in range(13, 17):
            ws.merge_cells(start_row=r, start_column=col,
                           end_row=block_end, end_column=col)
            c = ws.cell(row=r, column=col)
            c.value        = None
            c.fill         = _fill(C_DED_CELL)
            c.alignment    = al_c
            c.border       = B_DATA
            c.number_format = MONEY
            for ri in range(r+1, block_end+1):
                ws.cell(row=ri, column=col).border = B_DATA

        # Q — Seguro (CCSS auto-calculado: 10.67 % del bruto)
        ws.merge_cells(start_row=r, start_column=17,
                       end_row=block_end, end_column=17)
        c = ws.cell(row=r, column=17)
        c.value        = f"=ROUND(L{r}*$M$3,2)"  # $M$3 = tasa CCSS configurable
        c.font         = _font(10, True, C_SEGURO_FG)
        c.fill         = _fill(C_SEGURO_CELL)
        c.alignment    = al_c
        c.border       = B_DATA
        c.number_format = MONEY
        for ri in range(r+1, block_end+1):
            ws.cell(row=ri, column=17).border = B_DATA

        # R — Total deducciones
        ws.merge_cells(start_row=r, start_column=18,
                       end_row=block_end, end_column=18)
        c = ws.cell(row=r, column=18)
        c.value        = f"=SUM(M{r}:Q{r})"
        c.font         = _font(10, True, C_DED_FG)
        c.fill         = _fill(C_DED_CELL)
        c.alignment    = al_c
        c.border       = B_DATA
        c.number_format = MONEY
        for ri in range(r+1, block_end+1):
            ws.cell(row=ri, column=18).border = B_DATA

        # S — NETO
        ws.merge_cells(start_row=r, start_column=19,
                       end_row=block_end, end_column=19)
        c = ws.cell(row=r, column=19)
        c.value        = f"=L{r}-R{r}"
        c.font         = _font(12, True, C_NETO_FG)
        c.fill         = _fill(C_NETO_CELL)
        c.alignment    = al_c
        c.border       = _border(left="thin", lc="CBD5E1",
                                 right="medium", rc="334155",
                                 top="medium",  tc="334155",
                                 bottom="medium", bc="334155")
        c.number_format = MONEY
        for ri in range(r+1, block_end+1):
            ws.cell(row=ri, column=19).border = _border(
                left="thin", lc="CBD5E1", right="medium", rc="334155",
                top="thin",  tc="CBD5E1", bottom="thin",  bc="CBD5E1")

        r = block_end + 1

    # ── Fila TOTAL DE SECCIÓN ─────────────────────────────────────────────
    total_row = r
    ws.row_dimensions[r].height = 26
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=11)
    sc(ws, r, 1, f"TOTAL {label}",
       _font(10, True, C_WHITE), _fill(sec_color), al_r)

    def _sum_refs(col_idx):
        if not anchor_rows:
            return "0"
        return "+".join(f"{get_column_letter(col_idx)}{a}" for a in anchor_rows)

    for col in range(12, 20):
        c = ws.cell(row=r, column=col)
        c.value       = f"={_sum_refs(col)}" if anchor_rows else "=0"
        c.font        = _font(10, True, C_WHITE)
        c.fill        = _fill(sec_color)
        c.alignment   = al_c
        c.border      = B_TOTAL
        c.number_format = MONEY

    # S total = L - R
    ws.cell(row=r, column=19).value = f"=L{r}-R{r}"

    r += 1
    return r, total_row, anchor_rows


# ══════════════════════════════════════════════════════════════════════════════
#  SECCIÓN SALARIO FIJO
#  Empleados con sueldo mensual fijo — sin grilla de horas, sólo deducciones
# ══════════════════════════════════════════════════════════════════════════════
C_FIJO_HDR  = "6D28D9"   # Morado — encabezado sección fijo
C_FIJO_EMP  = "EDE9FE"   # Lavanda claro — celda nombre
C_FIJO_SAL  = "F5F3FF"   # Lavanda muy claro — celda salario

def _write_fijo_section(ws, start_row, fijo_list, wb_catalog):
    """
    Renderiza la sección SALARIO FIJO de la hoja semanal.
    Cada empleado ocupa 1 fila: Nombre | Salario Semanal (calculado) |
    Préstamo | Combust. | Mercad. | Adelanto | Seguro (CCSS auto) |
    Tot.Ded. | NETO

    wb_catalog: el workbook para leer el salario_fijo del Catálogo.
    Devuelve (next_row, total_row, anchor_rows).
    """
    if not fijo_list:
        return start_row, start_row, []

    COL_LAST = 19

    # Leer salarios fijos del catálogo
    salarios = {}
    if wb_catalog and "Catalogo" in wb_catalog.sheetnames:
        ws_cat = wb_catalog["Catalogo"]
        for r_cat in range(5, ws_cat.max_row + 1):
            nom = ws_cat.cell(r_cat, 1).value
            sal = ws_cat.cell(r_cat, 3).value
            if nom and isinstance(sal, (int, float)):
                salarios[nom] = sal

    r = start_row

    # ── Encabezado de sección ──
    ws.row_dimensions[r].height = 28
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=COL_LAST)
    sc(ws, r, 1, "  SALARIO FIJO",
       _font(12, True, C_WHITE), _fill(C_FIJO_HDR), al_l)
    r += 1

    # ── Sub-encabezado ──
    ws.row_dimensions[r].height = 16
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=11)
    sc(ws, r, 1, "COLABORADORES CON SALARIO MENSUAL FIJO",
       _font(8, True, C_WHITE), _fill(C_FIJO_HDR), al_c)
    ws.merge_cells(start_row=r, start_column=12, end_row=r, end_column=COL_LAST)
    sc(ws, r, 12, "DEDUCCIONES / RESUMEN",
       _font(8, True, C_WHITE), _fill(C_SLATE), al_c)
    r += 1

    # ── Cabeceras de columna ──
    ws.row_dimensions[r].height = 24
    hdrs_fijo = [
        (1,  "Empleado",       C_HDR_DARK),
        (2,  "Salario Mensual",C_FIJO_HDR),
        (3,  "Salario Semana", C_FIJO_HDR),
        (11, "",               C_WHITE),
        (12, "Bruto",          C_BRUTO_HDR),
        (13, "Préstamo",       C_DED_HDR),
        (14, "Combust.",       C_DED_HDR),
        (15, "Mercad.",        C_DED_HDR),
        (16, "Adelanto",       C_DED_HDR),
        (17, "Seguro",         C_SEGURO_HDR),
        (18, "Tot. Ded.",      C_DED_HDR),
        (19, "NETO",           C_NETO_HDR),
    ]
    for col, txt, bg in hdrs_fijo:
        sc(ws, r, col, txt or None,
           _font(9, True, C_WHITE), _fill(bg), al_c,
           B_THICK_LEFT if col == 12 else B_DATA)
    # Columnas 4-10 vacías (sin grilla de horas)
    for col in range(4, 11):
        ws.cell(row=r, column=col).fill = _fill(C_FIJO_HDR if col < 11 else C_WHITE)
    r += 1

    anchor_rows = []
    for emp in fijo_list:
        anchor_rows.append(r)
        ws.row_dimensions[r].height = 28

        sal_mensual = salarios.get(emp, 0) or 0

        # A — Nombre
        sc(ws, r, 1, emp, _font(10, True), _fill(C_FIJO_EMP), al_l,
           _border(left="medium", lc="6D28D9", right="thin", rc="CBD5E1",
                   top="medium", tc="6D28D9", bottom="medium", bc="6D28D9"))

        # B — Salario mensual (dato fijo, editable si se quiere cambiar)
        sc(ws, r, 2, sal_mensual, _font(10, False, "4C1D95"), _fill(C_FIJO_SAL),
           al_c, B_DATA, MONEY)

        # C — Salario semanal = mensual / 4.33
        ws.cell(row=r, column=3).value        = f"=ROUND(B{r}/4.33,2)"
        ws.cell(row=r, column=3).font         = _font(10, True, "4C1D95")
        ws.cell(row=r, column=3).fill         = _fill(C_FIJO_SAL)
        ws.cell(row=r, column=3).alignment    = al_c
        ws.cell(row=r, column=3).border       = B_DATA
        ws.cell(row=r, column=3).number_format = MONEY

        # D-J — vacíos (no hay grilla de horas para salario fijo)
        for col in range(4, 12):
            ws.cell(row=r, column=col).fill   = _fill(C_FIJO_SAL if col < 11 else C_WHITE)
            ws.cell(row=r, column=col).border = B_DATA if col < 11 else _border()

        # L — Bruto = salario semanal (columna C)
        c = ws.cell(row=r, column=12)
        c.value        = f"=C{r}"
        c.font         = _font(11, True, "1E3A5F")
        c.fill         = _fill(C_EMP_TARJETA)
        c.alignment    = al_c
        c.border       = _border(left="medium", lc="334155",
                                 right="thin",  rc="CBD5E1",
                                 top="medium",  tc="334155",
                                 bottom="medium", bc="334155")
        c.number_format = MONEY

        # M-P — Deducciones ingresables
        # Obtener préstamo si existe
        import database as db
        conn = db.get_conn()
        prestamo_row = conn.execute("""
            SELECT p.pago_semanal, p.saldo
            FROM prestamos p
            JOIN empleados e ON p.empleado_id = e.id
            WHERE e.nombre = ? AND p.estado = 'activo'
        """, (emp,)).fetchone()
        conn.close()

        prest_val = (
            min(prestamo_row["pago_semanal"], prestamo_row["saldo"])
            if prestamo_row else None
        )

        for col in range(13, 17):
            c2 = ws.cell(row=r, column=col)
            c2.value        = prest_val if col == 13 else None
            c2.fill         = _fill(C_DED_CELL)
            c2.alignment    = al_c
            c2.border       = B_DATA
            c2.number_format = MONEY

        # Q — Seguro CCSS auto
        c3 = ws.cell(row=r, column=17)
        c3.value        = f"=ROUND(L{r}*$M$3,2)"
        c3.font         = _font(10, True, C_SEGURO_FG)
        c3.fill         = _fill(C_SEGURO_CELL)
        c3.alignment    = al_c
        c3.border       = B_DATA
        c3.number_format = MONEY

        # R — Total deducciones
        c4 = ws.cell(row=r, column=18)
        c4.value        = f"=SUM(M{r}:Q{r})"
        c4.font         = _font(10, True, C_DED_FG)
        c4.fill         = _fill(C_DED_CELL)
        c4.alignment    = al_c
        c4.border       = B_DATA
        c4.number_format = MONEY

        # S — NETO
        c5 = ws.cell(row=r, column=19)
        c5.value        = f"=L{r}-R{r}"
        c5.font         = _font(12, True, C_NETO_FG)
        c5.fill         = _fill(C_NETO_CELL)
        c5.alignment    = al_c
        c5.border       = _border(left="thin", lc="CBD5E1",
                                  right="medium", rc="334155",
                                  top="medium",   tc="334155",
                                  bottom="medium", bc="334155")
        c5.number_format = MONEY

        r += 1

    # ── Fila TOTAL SALARIO FIJO ──
    total_row = r
    ws.row_dimensions[r].height = 24
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=11)
    sc(ws, r, 1, "TOTAL SALARIO FIJO",
       _font(10, True, C_WHITE), _fill(C_FIJO_HDR), al_r)

    for col in range(12, 20):
        refs = "+".join(f"{get_column_letter(col)}{a}" for a in anchor_rows) if anchor_rows else "0"
        c = ws.cell(row=r, column=col)
        c.value       = f"={refs}"
        c.font        = _font(10, True, C_WHITE)
        c.fill        = _fill(C_FIJO_HDR)
        c.alignment   = al_c
        c.border      = B_TOTAL
        c.number_format = MONEY

    ws.cell(row=r, column=19).value = f"=L{r}-R{r}"

    r += 1
    return r, total_row, anchor_rows



def crear_hoja_semanal(wb, num, viernes_date, empleados, seguro=0):
    if isinstance(viernes_date, str):
        viernes_date = datetime.strptime(viernes_date, "%Y-%m-%d").date()

    sem_num    = num_semana_anual(viernes_date)
    sheet_name = f"Semana {sem_num}"
    if sheet_name in wb.sheetnames:
        wb.remove(wb[sheet_name])
    ws = wb.create_sheet(sheet_name)

    # Color de pestaña
    ws.sheet_properties.tabColor = "1D4ED8"

    COL_LAST = 19
    col_widths = {
        "A": 22, "B": 16, "C": 10, "D": 10, "E": 10,
        "F": 10, "G": 10, "H": 10, "I": 10, "J": 11,
        "K": 1,  "L": 15, "M": 12, "N": 11, "O": 11,
        "P": 11, "Q": 13, "R": 13, "S": 14,
    }
    for col, w in col_widths.items():
        ws.column_dimensions[col].width = w

    # ── Fila 1: Título ───────────────────────────────────────────────────
    ws.row_dimensions[1].height = 40
    ws.merge_cells("A1:S1")
    sc(ws, 1, 1, "PLANILLA DE PAGO SEMANAL",
       _font(16, True, C_WHITE), _fill(C_DARK_BLUE), al_c)

    # ── Fila 2: Período ──────────────────────────────────────────────────
    ws.row_dimensions[2].height = 26
    _row_fill(ws, 2, 1, COL_LAST, C_DARK_BLUE)
    sc(ws, 2, 1, "PERÍODO:", _font(10, True, C_WHITE), _fill(C_DARK_BLUE), al_r)
    sc(ws, 2, 3, viernes_date, _font(11, False, "BFDBFE"),
       _fill(C_DARK_BLUE), al_c, num_format="DD/MM/YYYY")
    sc(ws, 2, 4, "→", _font(11, False, C_SUBTITLE), _fill(C_DARK_BLUE), al_c)
    sc(ws, 2, 5, "=$C$2+6", _font(11, False, "BFDBFE"),
       _fill(C_DARK_BLUE), al_c, num_format="DD/MM/YYYY")
    sc(ws, 2, 7, f"Semana #{sem_num}",
       _font(11, False, C_SUBTITLE), _fill(C_DARK_BLUE), al_c)

    # ── Fila 3: Tarifas + Tasa CCSS ──────────────────────────────────────
    ws.row_dimensions[3].height = 24
    _row_fill(ws, 3, 1, COL_LAST, C_TARIFA_BG)
    ws.merge_cells("A3:B3")
    sc(ws, 3, 1, "TARIFAS (₡/hora):",
       _font(9, True, C_TARIFA_VAL), _fill(C_TARIFA_BG), al_r)
    tarifa_items = [
        (3, "Diurna:",   4,  TARIFA_DIURNA),
        (5, "Mixta:",    6,  TARIFA_MIXTA),
        (7, "Nocturna:", 8,  TARIFA_NOCTURNA),
        (9, "Extra:",   10,  "=$D$3*1.5"),
    ]
    for lc, lbl, vc, val in tarifa_items:
        sc(ws, 3, lc, lbl, _font(8, False, C_TARIFA_LBL), _fill(C_TARIFA_BG), al_r)
        sc(ws, 3, vc, val, _font(10, True, C_TARIFA_VAL), _fill(C_WHITE), al_c)

    # M3 = tasa CCSS (configurable por el usuario)
    sc(ws, 3, 12, "CCSS (%):", _font(8, False, C_TARIFA_LBL), _fill(C_TARIFA_BG), al_r)
    sc(ws, 3, 13, CCSS_RATE,   _font(10, True, C_TARIFA_VAL), _fill(C_WHITE),     al_c,
       num_format="0.00%")

    # ── Fila 4: espaciador ───────────────────────────────────────────────
    ws.row_dimensions[4].height = 5
    _row_fill(ws, 4, 1, COL_LAST, C_DARK_BLUE)

    # ── Secciones de pago ────────────────────────────────────────────────
    tarjeta_emps  = empleados.get("tarjeta",  [])
    efectivo_emps = empleados.get("efectivo", [])

    r = 5
    r, tarjeta_total, _ = _write_section(
        ws, r, "PAGO POR TARJETA", C_TARJETA, C_EMP_TARJETA, tarjeta_emps)

    # separador visual entre secciones
    ws.row_dimensions[r].height = 4
    _row_fill(ws, r, 1, COL_LAST, "E2E8F0")
    r += 1

    r, efectivo_total, _ = _write_section(
        ws, r, "PAGO EN EFECTIVO", C_EFECTIVO, C_EMP_EFECT, efectivo_emps)

    # ── Sección Salario Fijo (sólo si hay empleados fijos) ────────────────
    fijo_emps = empleados.get("fijo", [])
    fijo_total = None
    if fijo_emps:
        ws.row_dimensions[r].height = 4
        _row_fill(ws, r, 1, COL_LAST, "EDE9FE")
        r += 1
        r, fijo_total, _ = _write_fijo_section(ws, r, fijo_emps, wb)

    # ── Gran Total ───────────────────────────────────────────────────────
    ws.row_dimensions[r].height = 4
    _row_fill(ws, r, 1, COL_LAST, C_DARK_BLUE)

    gt = r + 1
    ws.row_dimensions[gt].height = 30
    ws.merge_cells(start_row=gt, start_column=1, end_row=gt, end_column=11)
    sc(ws, gt, 1, "GRAN TOTAL DE LA SEMANA",
       _font(12, True, C_WHITE), _fill(C_DARK_BLUE), al_r)
    gran_cols = {
        12: ("BFDBFE", True),
        13: (C_WHITE, False), 14: (C_WHITE, False),
        15: (C_WHITE, False), 16: (C_WHITE, False),
        17: ("FEF3C7", False),
        18: ("FEE2E2", False),
        19: ("D1FAE5", True),
    }
    for col, (fc, bold) in gran_cols.items():
        cl = get_column_letter(col)
        # Suma las tres secciones si existe fijo, si no sólo las dos primeras
        if fijo_total:
            formula = f"={cl}{tarjeta_total}+{cl}{efectivo_total}+{cl}{fijo_total}"
        else:
            formula = f"={cl}{tarjeta_total}+{cl}{efectivo_total}"
        c = ws.cell(row=gt, column=col)
        c.value       = formula
        c.font        = _font(11 if col in (12, 19) else 10, bold, fc)
        c.fill        = _fill(C_DARK_BLUE)
        c.alignment   = al_c
        c.number_format = MONEY
    ws.cell(row=gt, column=19).value = f"=L{gt}-R{gt}"

    ws.row_dimensions[gt+1].height = 4
    _row_fill(ws, gt+1, 1, COL_LAST, C_DARK_BLUE)

    # ── Freeze panes: fija columnas A-B y filas de título/tarifas ────────
    # Con C5 fijamos: ver siempre columnas Empleado+Jornada al deslizar ↔
    # y el título/tarifas al deslizar ↕
    ws.freeze_panes = "C5"

    # ── Sub-hojas ─────────────────────────────────────────────────────────
    crear_resumen_semanal(wb, sheet_name, sem_num, viernes_date)
    crear_resumen_mensual(wb)
    crear_dashboard(wb)

    return sheet_name, gt + 2, {}


# ══════════════════════════════════════════════════════════════════════════════
#  RESUMEN SEMANAL
# ══════════════════════════════════════════════════════════════════════════════
def crear_resumen_semanal(wb, nombre_hoja_sem, sem_num, viernes_date):
    if isinstance(viernes_date, str):
        viernes_date = datetime.strptime(viernes_date, "%Y-%m-%d").date()

    sheet_name = f"Res. Sem. {sem_num}"
    if sheet_name in wb.sheetnames:
        wb.remove(wb[sheet_name])
    ws = wb.create_sheet(sheet_name)
    ws.sheet_properties.tabColor = "0369A1"

    col_widths = {
        "A": 24, "B": 13, "C": 13, "D": 14, "E": 16, "F": 13,
        "G": 14, "H": 15, "I": 13, "J": 13, "K": 15,
    }
    for col, w in col_widths.items():
        ws.column_dimensions[col].width = w

    ws.row_dimensions[1].height = 36
    ws.merge_cells("A1:K1")
    sc(ws, 1, 1, f"RESUMEN SEMANAL — Semana {sem_num}",
       _font(14, True, C_WHITE), _fill(C_DARK_BLUE), al_c)

    fin = viernes_date + timedelta(days=6)
    ws.row_dimensions[2].height = 20
    ws.merge_cells("A2:K2")
    sc(ws, 2, 1,
       f"{viernes_date.strftime('%d/%m/%Y')}  →  {fin.strftime('%d/%m/%Y')}",
       _font(10, False, C_SUBTITLE), _fill(C_DARK_BLUE), al_c)

    ws.row_dimensions[3].height = 5

    ws.row_dimensions[4].height = 22
    hdrs = [
        (1, "Empleado",      C_HDR_DARK),
        (2, "Hrs Diurnas",   C_OCEAN),
        (3, "Hrs Mixtas",    C_OCEAN),
        (4, "Hrs Nocturnas", C_OCEAN),
        (5, "Monto Extra (₡)", C_BRUTO_HDR),
        (6, "Hrs Extra",     C_OCEAN),
        (7, "Total Hrs",     C_OCEAN),
        (8, "Bruto (₡)",     C_BRUTO_HDR),
        (9, "Rebajos (₡)",   C_RED_HDR),
        (10, "Seguro (₡)",   C_SEGURO_HDR),
        (11, "NETO (₡)",     C_NETO_HDR),
    ]
    hour_cols = {2, 3, 4, 6, 7}
    money_cols = {5, 8, 9, 10, 11}
    for col, txt, bg in hdrs:
        sc(ws, 4, col, txt, _font(9, True, C_WHITE), _fill(bg), al_c,
           B_THICK_LEFT if col == 8 else B_DATA)

    try:
        hs = wb[nombre_hoja_sem]
    except Exception:
        return

    def _write_sem_section(start_r, sec_label, sec_color):
        ws.row_dimensions[start_r].height = 24
        ws.merge_cells(start_row=start_r, start_column=1,
                       end_row=start_r, end_column=11)
        sc(ws, start_r, 1, f"  {sec_label}",
           _font(11, True, C_WHITE), _fill(sec_color), al_l)
        r = start_r + 1

        emp_rows = []
        in_section = False
        sn = nombre_hoja_sem
        for hr in range(1, hs.max_row + 1):
            v = hs.cell(row=hr, column=1).value
            if isinstance(v, str) and sec_label in v and "PAGO" in v:
                in_section = True
                continue
            if in_section and isinstance(v, str) and v.startswith("TOTAL") and "GRAN" not in v:
                break
            if in_section and v and hs.cell(row=hr, column=2).value == "Hrs. Diurnas":
                emp_name = v
                rd, rm, rn, re = hr, hr+1, hr+2, hr+3
                alt = (len(emp_rows) % 2 == 0)
                bg  = "F7F9FC" if alt else C_WHITE
                sc(ws, r, 1, emp_name, _font(10), _fill(bg), al_l, B_DATA)
                ws.cell(row=r, column=2).value = _summary_ref_or_blank(f"'{sn}'!J{rd}")
                ws.cell(row=r, column=3).value = _summary_ref_or_blank(f"'{sn}'!J{rm}")
                ws.cell(row=r, column=4).value = _summary_ref_or_blank(f"'{sn}'!J{rn}")
                ws.cell(row=r, column=5).value = _summary_expr_or_blank(
                    f"'{sn}'!J{re}*'{sn}'!$J$3")
                ws.cell(row=r, column=6).value = _summary_ref_or_blank(f"'{sn}'!J{re}")
                ws.cell(row=r, column=7).value = _summary_expr_or_blank(
                    f"SUM('{sn}'!J{rd},'{sn}'!J{rm},'{sn}'!J{rn},'{sn}'!J{re})")
                ws.cell(row=r, column=8).value = _summary_ref_or_blank(f"'{sn}'!L{rd}")
                ws.cell(row=r, column=9).value = _summary_expr_or_blank(
                    f"'{sn}'!R{rd}-'{sn}'!Q{rd}")
                ws.cell(row=r, column=10).value = _summary_ref_or_blank(f"'{sn}'!Q{rd}")
                ws.cell(row=r, column=11).value = _summary_ref_or_blank(f"'{sn}'!S{rd}")
                for ci in range(1, 12):
                    ws.cell(row=r, column=ci).fill      = _fill(bg)
                    ws.cell(row=r, column=ci).alignment = al_c if ci > 1 else al_l
                    ws.cell(row=r, column=ci).border    = (
                        B_THICK_LEFT if ci == 8 else B_DATA)
                    if ci in hour_cols:
                        ws.cell(row=r, column=ci).number_format = SUMMARY_HOURS_FMT
                    if ci in money_cols:
                        ws.cell(row=r, column=ci).number_format = SUMMARY_MONEY_FMT
                emp_rows.append(r)
                r += 1

        # Fila total de sección
        tot = r
        ws.row_dimensions[r].height = 22
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=1)
        sc(ws, r, 1, f"TOTAL {sec_label}",
           _font(10, True, C_WHITE), _fill(sec_color), al_r, B_TOTAL)
        if emp_rows:
            fr, lr = emp_rows[0], emp_rows[-1]
            for ci in range(2, 12):
                cl = get_column_letter(ci)
                ws.cell(row=r, column=ci).value       = _summary_expr_or_blank(
                    f"SUM({cl}{fr}:{cl}{lr})")
                ws.cell(row=r, column=ci).font        = _font(10, True, C_WHITE)
                ws.cell(row=r, column=ci).fill        = _fill(sec_color)
                ws.cell(row=r, column=ci).alignment   = al_c
                ws.cell(row=r, column=ci).border      = (
                    B_TOTAL_THICK_LEFT if ci == 8 else B_TOTAL)
                if ci in hour_cols:
                    ws.cell(row=r, column=ci).number_format = SUMMARY_HOURS_FMT
                if ci in money_cols:
                    ws.cell(row=r, column=ci).number_format = SUMMARY_MONEY_FMT
        return r + 1, tot

    r5 = 5
    r5, tot_tarjeta = _write_sem_section(r5, "PAGO POR TARJETA", C_TARJETA)
    r5 += 1
    r5, tot_efectivo = _write_sem_section(r5, "PAGO EN EFECTIVO", C_EFECTIVO)

    # ── Sección Salario Fijo en el Resumen Semanal ──
    # Para empleados fijos: hrs = 0, bruto = salario semanal leído del Excel
    tot_fijo = None
    if hs:
        # Buscar si hay sección SALARIO FIJO en la hoja semanal
        for hr in range(1, hs.max_row + 1):
            v = hs.cell(row=hr, column=1).value
            if isinstance(v, str) and "SALARIO FIJO" in v and not v.startswith("TOTAL"):
                # Encontramos la sección; extraer empleados de ella
                r5 += 1
                ws.row_dimensions[r5].height = 22
                ws.merge_cells(start_row=r5, start_column=1, end_row=r5, end_column=11)
                sc(ws, r5, 1, "  SALARIO FIJO",
                   _font(11, True, C_WHITE), _fill(C_FIJO_HDR), al_l)
                r5 += 1
                emp_fijo_rows = []
                sn = nombre_hoja_sem
                fr2 = hr + 3  # saltar sub-encabezado + cabeceras
                while fr2 <= hs.max_row:
                    v2 = hs.cell(row=fr2, column=1).value
                    if isinstance(v2, str) and v2.startswith("TOTAL SALARIO FIJO"):
                        break
                    if v2 and isinstance(v2, str) and not v2.startswith("TOTAL"):
                        alt = (len(emp_fijo_rows) % 2 == 0)
                        bg  = "F5F3FF" if alt else "EDE9FE"
                        sc(ws, r5, 1, v2, _font(10), _fill(bg), al_l, B_DATA)
                        for ci in range(2, 8):
                            ws.cell(row=r5, column=ci).value       = None
                            ws.cell(row=r5, column=ci).fill        = _fill(bg)
                            ws.cell(row=r5, column=ci).alignment   = al_c
                            ws.cell(row=r5, column=ci).border      = B_DATA
                            if ci in hour_cols:
                                ws.cell(row=r5, column=ci).number_format = SUMMARY_HOURS_FMT
                            if ci in money_cols:
                                ws.cell(row=r5, column=ci).number_format = SUMMARY_MONEY_FMT
                        ws.cell(row=r5, column=8).value  = _summary_ref_or_blank(f"'{sn}'!L{fr2}")
                        ws.cell(row=r5, column=9).value  = _summary_expr_or_blank(
                            f"'{sn}'!R{fr2}-'{sn}'!Q{fr2}")
                        ws.cell(row=r5, column=10).value = _summary_ref_or_blank(f"'{sn}'!Q{fr2}")
                        ws.cell(row=r5, column=11).value = _summary_ref_or_blank(f"'{sn}'!S{fr2}")
                        for ci in range(8, 12):
                            ws.cell(row=r5, column=ci).fill      = _fill(bg)
                            ws.cell(row=r5, column=ci).alignment = al_c
                            ws.cell(row=r5, column=ci).border    = B_THICK_LEFT if ci == 8 else B_DATA
                            ws.cell(row=r5, column=ci).number_format = SUMMARY_MONEY_FMT
                        emp_fijo_rows.append(r5)
                        r5 += 1
                    fr2 += 1

                if emp_fijo_rows:
                    tot_fijo = r5
                    ws.row_dimensions[r5].height = 22
                    ws.merge_cells(start_row=r5, start_column=1, end_row=r5, end_column=1)
                    sc(ws, r5, 1, "TOTAL SALARIO FIJO",
                       _font(10, True, C_WHITE), _fill(C_FIJO_HDR), al_r, B_TOTAL)
                    frf, lrf = emp_fijo_rows[0], emp_fijo_rows[-1]
                    for ci in range(2, 12):
                        cl = get_column_letter(ci)
                        ws.cell(row=r5, column=ci).value       = _summary_expr_or_blank(
                            f"SUM({cl}{frf}:{cl}{lrf})")
                        ws.cell(row=r5, column=ci).font        = _font(10, True, C_WHITE)
                        ws.cell(row=r5, column=ci).fill        = _fill(C_FIJO_HDR)
                        ws.cell(row=r5, column=ci).alignment   = al_c
                        ws.cell(row=r5, column=ci).border      = (
                            B_TOTAL_THICK_LEFT if ci == 8 else B_TOTAL)
                        if ci in hour_cols:
                            ws.cell(row=r5, column=ci).number_format = SUMMARY_HOURS_FMT
                        if ci in money_cols:
                            ws.cell(row=r5, column=ci).number_format = SUMMARY_MONEY_FMT
                    r5 += 1
                break

    r5 += 1
    # Gran total semanal
    gt = r5
    ws.row_dimensions[gt].height = 26
    ws.merge_cells(start_row=gt, start_column=1, end_row=gt, end_column=1)
    sc(ws, gt, 1, "GRAN TOTAL SEMANAL",
       _font(11, True, C_WHITE), _fill(C_DARK_BLUE), al_r, B_TOTAL)
    for ci in range(2, 12):
        cl = get_column_letter(ci)
        refs = [f"{cl}{tot_tarjeta}", f"{cl}{tot_efectivo}"]
        if tot_fijo:
            refs.append(f"{cl}{tot_fijo}")
        ws.cell(row=gt, column=ci).value       = _summary_expr_or_blank(
            f"SUM({','.join(refs)})")
        ws.cell(row=gt, column=ci).font        = _font(10, True, C_WHITE)
        ws.cell(row=gt, column=ci).fill        = _fill(C_DARK_BLUE)
        ws.cell(row=gt, column=ci).alignment   = al_c
        ws.cell(row=gt, column=ci).border      = (
            B_TOTAL_THICK_LEFT if ci == 8 else B_TOTAL)
        if ci in hour_cols:
            ws.cell(row=gt, column=ci).number_format = SUMMARY_HOURS_FMT
        if ci in money_cols:
            ws.cell(row=gt, column=ci).number_format = SUMMARY_MONEY_FMT

    ws.freeze_panes = "B5"


# ══════════════════════════════════════════════════════════════════════════════
#  RESUMEN MENSUAL
# ══════════════════════════════════════════════════════════════════════════════
def crear_resumen_mensual(wb):
    sheet_name = "Resumen Mensual"
    if sheet_name in wb.sheetnames:
        wb.remove(wb[sheet_name])
    ws = wb.create_sheet(sheet_name)
    ws.sheet_properties.tabColor = "374151"

    col_widths = {
        "A": 24, "B": 18, "C": 12, "D": 12, "E": 12, "F": 16,
        "G": 12, "H": 12, "I": 16, "J": 15, "K": 15, "L": 16,
    }
    for col, w in col_widths.items():
        ws.column_dimensions[col].width = w

    ws.row_dimensions[1].height = 36
    ws.merge_cells("A1:L1")
    sc(ws, 1, 1, "RESUMEN MENSUAL DE PLANILLA",
       _font(14, True, C_WHITE), _fill(C_DARK_BLUE), al_c)

    ws.row_dimensions[2].height = 20
    ws.merge_cells("A2:L2")
    sc(ws, 2, 1, "Totales acumulados del mes por empleado",
       _font(9, False, C_SUBTITLE), _fill(C_DARK_BLUE), al_c)

    ws.row_dimensions[3].height = 5

    ws.row_dimensions[4].height = 22
    hdrs = [
        (1,  "Empleado",       C_HDR_DARK),
        (2,  "Semana",         C_HDR_DARK),
        (3,  "Hrs Diurnas",    C_OCEAN),
        (4,  "Hrs Mixtas",     C_OCEAN),
        (5,  "Hrs Nocturnas",  C_OCEAN),
        (6,  "Monto Extra (₡)", C_BRUTO_HDR),
        (7,  "Hrs Extra",      C_OCEAN),
        (8,  "Hrs Totales",    C_OCEAN),
        (9,  "Salario Bruto",  C_BRUTO_HDR),
        (10, "Rebajos",        C_RED_HDR),
        (11, "Seguro",         C_SEGURO_HDR),
        (12, "Neto a Pagar",   C_NETO_HDR),
    ]
    hour_cols = {3, 4, 5, 7, 8}
    money_cols = {6, 9, 10, 11, 12}
    for col, txt, bg in hdrs:
        sc(ws, 4, col, txt, _font(9, True, C_WHITE), _fill(bg), al_c,
           B_THICK_LEFT if col == 9 else B_DATA)

    cur_r = 5
    empleados = leer_catalogo(wb)
    sections = [
        ("PAGO POR TARJETA", empleados.get("tarjeta",  []), C_TARJETA,  C_EMP_TARJETA),
        ("PAGO EN EFECTIVO", empleados.get("efectivo", []), C_EFECTIVO, C_EMP_EFECT),
        ("SALARIO FIJO",     empleados.get("fijo",     []), C_FIJO_HDR, C_FIJO_EMP),
    ]
    sec_total_rows = []

    for sec_label, emp_list, sec_color, emp_bg in sections:
        ws.row_dimensions[cur_r].height = 24
        ws.merge_cells(start_row=cur_r, start_column=1,
                       end_row=cur_r, end_column=12)
        sc(ws, cur_r, 1, f"  {sec_label}",
           _font(11, True, C_WHITE), _fill(sec_color), al_l)
        cur_r += 1
        sec_emp_total_rows = []

        for emp in emp_list:
            emp_data_rows = []
            for sname in wb.sheetnames:
                if not sname.startswith("Res. Sem. "):
                    continue
                sws = wb[sname]
                for sr in range(4, sws.max_row + 1):
                    if sws.cell(row=sr, column=1).value == emp:
                        alt = len(emp_data_rows) % 2 == 0
                        bg  = "F7F9FC" if alt else C_WHITE
                        sc(ws, cur_r, 1, emp, _font(10), _fill(bg), al_l, B_DATA)
                        sc(ws, cur_r, 2,
                           sname.replace("Res. Sem. ", "Semana "),
                           _font(10), _fill(bg), al_c, B_DATA)
                        col_map = {
                            3: 2, 4: 3, 5: 4, 6: 5, 7: 6,
                            8: 7, 9: 8, 10: 9, 11: 10, 12: 11,
                        }
                        for dst, src in col_map.items():
                            c = ws.cell(row=cur_r, column=dst)
                            ref = f"'{sname}'!{get_column_letter(src)}{sr}"
                            c.value     = _summary_ref_or_blank(ref)
                            c.fill      = _fill(bg)
                            c.alignment = al_c
                            c.border    = B_THICK_LEFT if dst == 9 else B_DATA
                            if dst in hour_cols:
                                c.number_format = SUMMARY_HOURS_FMT
                            if dst in money_cols:
                                c.number_format = SUMMARY_MONEY_FMT
                        emp_data_rows.append(cur_r)
                        cur_r += 1

            if emp_data_rows:
                ws.row_dimensions[cur_r].height = 20
                ws.merge_cells(start_row=cur_r, start_column=1,
                               end_row=cur_r, end_column=2)
                sc(ws, cur_r, 1, "TOTAL MENSUAL",
                   _font(10, True), _fill(emp_bg), al_r, B_DATA)
                fr, lr = emp_data_rows[0], emp_data_rows[-1]
                for ci in range(3, 13):
                    cl = get_column_letter(ci)
                    fg = (C_SEGURO_FG if ci == 11 else
                          C_NETO_FG   if ci == 12 else "1F2937")
                    bg2 = (C_SEGURO_CELL if ci == 11 else
                           C_NETO_CELL   if ci == 12 else emp_bg)
                    c = ws.cell(row=cur_r, column=ci)
                    c.value       = _summary_expr_or_blank(f"SUM({cl}{fr}:{cl}{lr})")
                    c.font        = _font(10, True, fg)
                    c.fill        = _fill(bg2)
                    c.alignment   = al_c
                    c.border      = B_THICK_LEFT if ci == 9 else B_DATA
                    if ci in hour_cols:
                        c.number_format = SUMMARY_HOURS_FMT
                    if ci in money_cols:
                        c.number_format = SUMMARY_MONEY_FMT
                sec_emp_total_rows.append(cur_r)
                cur_r += 1

        sec_tot = cur_r
        ws.row_dimensions[cur_r].height = 22
        ws.merge_cells(start_row=cur_r, start_column=1,
                       end_row=cur_r, end_column=2)
        sc(ws, cur_r, 1, f"TOTAL {sec_label}",
           _font(10, True, C_WHITE), _fill(sec_color), al_r, B_TOTAL)
        if sec_emp_total_rows:
            for ci in range(3, 13):
                cl = get_column_letter(ci)
                expr = f"SUM({','.join(f'{cl}{row}' for row in sec_emp_total_rows)})"
                c = ws.cell(row=cur_r, column=ci)
                c.value       = _summary_expr_or_blank(expr)
                c.font        = _font(10, True, C_WHITE)
                c.fill        = _fill(sec_color)
                c.alignment   = al_c
                c.border      = B_TOTAL_THICK_LEFT if ci == 9 else B_TOTAL
                if ci in hour_cols:
                    c.number_format = SUMMARY_HOURS_FMT
                if ci in money_cols:
                    c.number_format = SUMMARY_MONEY_FMT
        sec_total_rows.append(cur_r)
        cur_r += 1

    cur_r += 1
    ws.row_dimensions[cur_r].height = 28
    ws.merge_cells(start_row=cur_r, start_column=1,
                   end_row=cur_r, end_column=2)
    sc(ws, cur_r, 1, "GRAN TOTAL MENSUAL",
       _font(11, True, C_WHITE), _fill(C_DARK_BLUE), al_r, B_TOTAL)
    for ci in range(3, 13):
        cl = get_column_letter(ci)
        refs = ",".join(f"{cl}{tr}" for tr in sec_total_rows)
        c = ws.cell(row=cur_r, column=ci)
        c.value       = _summary_expr_or_blank(f"SUM({refs})")
        c.font        = _font(10, True, C_WHITE)
        c.fill        = _fill(C_DARK_BLUE)
        c.alignment   = al_c
        c.border      = B_TOTAL_THICK_LEFT if ci == 9 else B_TOTAL
        if ci in hour_cols:
            c.number_format = SUMMARY_HOURS_FMT
        if ci in money_cols:
            c.number_format = SUMMARY_MONEY_FMT

    ws.freeze_panes = "C5"


# ══════════════════════════════════════════════════════════════════════════════
#  DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
def crear_dashboard(wb):
    sheet_name = "Dashboard"
    if sheet_name in wb.sheetnames:
        wb.remove(wb[sheet_name])
    ws = wb.create_sheet(sheet_name)
    ws.sheet_properties.tabColor = "065F46"

    col_widths = {"A": 20, "B": 18, "C": 14, "D": 14,
                  "E": 14, "F": 24, "G": 18, "H": 14, "I": 14, "J": 14}
    for col, w in col_widths.items():
        ws.column_dimensions[col].width = w

    ws.row_dimensions[1].height = 36
    ws.merge_cells("A1:J1")
    sc(ws, 1, 1, "DASHBOARD — RESUMEN GRÁFICO DEL MES",
       _font(14, True, C_WHITE), _fill(C_DARK_BLUE), al_c)

    num_sem = contar_semanas(wb)
    ws.row_dimensions[2].height = 20
    ws.merge_cells("A2:J2")
    sc(ws, 2, 1, f"Semanas procesadas: {num_sem}",
       _font(10, False, C_SUBTITLE), _fill(C_DARK_BLUE), al_c)

    ws.row_dimensions[3].height = 6

    # Panel "Datos por semana"
    ws.row_dimensions[4].height = 22
    ws.merge_cells("A4:D4")
    sc(ws, 4, 1, "DATOS POR SEMANA",
       _font(10, True, C_WHITE), _fill(C_SLATE), al_c)

    ws.row_dimensions[5].height = 20
    for col, txt, bg in [
        (1, "Semana", C_HDR_DARK),
        (2, "Bruto",  C_BRUTO_HDR),
        (3, "Neto",   C_NETO_HDR),
    ]:
        sc(ws, 5, col, txt, _font(9, True, C_WHITE), _fill(bg), al_c, B_DATA)

    row_idx = 6
    for sname in wb.sheetnames:
        if not sname.startswith("Res. Sem. "):
            continue
        sem_ws = wb[sname]
        gt_row = None
        for r in range(1, sem_ws.max_row + 1):
            if isinstance(sem_ws.cell(row=r, column=1).value, str) \
               and "GRAN TOTAL" in sem_ws.cell(row=r, column=1).value:
                gt_row = r
                break
        if gt_row is None:
            continue
        ws.row_dimensions[row_idx].height = 19
        alt = (row_idx % 2 == 0)
        sc(ws, row_idx, 1,
           sname.replace("Res. Sem. ", "Sem. "),
           _font(10), _fill("F7F9FC" if alt else C_WHITE), al_c, B_DATA)
        for ci, src_col, bg_cell, fc in [
            (2, "H", C_EMP_TARJETA, "1E3A5F"),
            (3, "K", C_NETO_CELL,   C_NETO_FG),
        ]:
            c = ws.cell(row=row_idx, column=ci)
            c.value        = f"='{sname}'!{src_col}{gt_row}"
            c.font         = _font(10, True, fc)
            c.fill         = _fill(bg_cell)
            c.alignment    = al_c
            c.border       = B_DATA
            c.number_format = MONEY
        row_idx += 1

    # Panel "Totales del mes"
    ws.row_dimensions[14].height = 22
    ws.merge_cells("A14:D14")
    sc(ws, 14, 1, "TOTALES DEL MES",
       _font(10, True, C_WHITE), _fill(C_SLATE), al_c)
    ws.merge_cells("F14:H14")
    sc(ws, 14, 6, "DISTRIBUCIÓN POR MÉTODO",
       _font(10, True, C_WHITE), _fill(C_SLATE), al_c)

    rm = wb.get("Resumen Mensual") if hasattr(wb, "get") else (
        wb["Resumen Mensual"] if "Resumen Mensual" in wb.sheetnames else None)
    gt_rm = None
    if rm:
        for r in range(1, rm.max_row + 1):
            v = rm.cell(row=r, column=1).value
            if isinstance(v, str) and "GRAN TOTAL" in v:
                gt_rm = r
                break

    totals_panel = [
        (15, "Total Bruto",  "F7F9FC",    9,  "1E3A5F", C_EMP_TARJETA),
        (16, "Tot. Rebajos", C_WHITE,     10, C_DED_FG,  C_DED_CELL),
        (17, "Tot. Seguros", "F7F9FC",    11, C_SEGURO_FG, C_SEGURO_CELL),
        (18, "TOTAL NETO",   C_NETO_HDR,  12, C_WHITE,   C_NETO_CELL),
    ]
    for row_n, lbl, bg_lbl, src_ci, fc_val, bg_val in totals_panel:
        ws.row_dimensions[row_n].height = 22
        is_neto = lbl == "TOTAL NETO"
        sc(ws, row_n, 1, lbl,
           _font(10, is_neto, C_WHITE if is_neto else "1F2937"),
           _fill(bg_lbl if not is_neto else C_NETO_HDR), al_c, B_DATA)
        c = ws.cell(row=row_n, column=2)
        if gt_rm:
            c.value = f"='Resumen Mensual'!{get_column_letter(src_ci)}{gt_rm}"
        c.font         = _font(10, True, fc_val)
        c.fill         = _fill(bg_val)
        c.alignment    = al_c
        c.border       = B_DATA
        c.number_format = MONEY

    sc(ws, 15, 6, "Método",          _font(9, True, C_WHITE), _fill(C_HDR_DARK), al_c, B_DATA)
    sc(ws, 15, 7, "Total Neto",      _font(9, True, C_WHITE), _fill(C_NETO_HDR), al_c, B_DATA)
    sc(ws, 16, 6, "PAGO POR TARJETA",_font(9),               _fill(C_EMP_TARJETA), al_c, B_DATA)
    sc(ws, 17, 6, "PAGO EN EFECTIVO",_font(9),               _fill(C_EMP_EFECT),   al_c, B_DATA)

    if gt_rm:
        # Tarjeta total neto
        c16 = ws.cell(row=16, column=7)
        c16.value       = f"='Resumen Mensual'!L{gt_rm}"
        c16.fill        = _fill(C_EMP_TARJETA)
        c16.alignment   = al_c
        c16.number_format = MONEY
        # Efectivo total neto
        c17 = ws.cell(row=17, column=7)
        c17.value       = f"='Resumen Mensual'!L{gt_rm}"
        c17.fill        = _fill(C_EMP_EFECT)
        c17.alignment   = al_c
        c17.number_format = MONEY


# ══════════════════════════════════════════════════════════════════════════════
#  CATÁLOGO
# ══════════════════════════════════════════════════════════════════════════════
def crear_catalogo(wb):
    sheet_name = "Catalogo"
    if sheet_name in wb.sheetnames:
        wb.remove(wb[sheet_name])
    ws = wb.create_sheet(sheet_name, 0)
    ws.sheet_properties.tabColor = "1D4ED8"

    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 15
    ws.column_dimensions["C"].width = 15

    ws.row_dimensions[1].height = 36
    ws.merge_cells("A1:D1")
    sc(ws, 1, 1, "CATÁLOGO DE EMPLEADOS",
       _font(14, True, C_WHITE), _fill(C_DARK_BLUE), al_c)

    ws.row_dimensions[2].height = 22
    ws.merge_cells("A2:D2")
    sc(ws, 2, 1,
       "Edite esta lista y luego use: python planilla.py agregar --viernes YYYY-MM-DD",
       _font(9, False, C_SUBTITLE), _fill(C_DARK_BLUE), al_c)

    ws.row_dimensions[4].height = 22
    hdrs = ["Nombre Completo", "Tipo de Pago", "Salario Fijo (₡)"]
    for i, h in enumerate(hdrs):
        sc(ws, 4, i+1, h, _font(9, True, C_WHITE), _fill(C_HDR_DARK), al_c, B_DATA)
