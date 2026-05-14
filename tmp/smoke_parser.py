"""Smoke test del parser con el Excel real."""
import sys, json
sys.path.insert(0, "planillas")

import horario_excel_import as hei

path = r"C:\Users\kenda\Downloads\horario 2026 (2).xlsx"
sheets = hei.list_sheet_names(path)
print("Hojas encontradas:", sheets[:8])

# Parsear la primera hoja numérica disponible
target = next((s for s in sheets if s.isdigit()), sheets[0] if sheets else None)
if not target:
    print("No hay hojas numéricas")
    sys.exit(1)

print(f"\nAnalizando hoja: {target}")
result = hei.parse_workbook_sheets(path, [target])[0]

print("Errores:", result["errors"])
print("Warnings:", result["warnings"][:5])
print("Empleados:", list(result["schedule"].keys())[:6])

tasks = result.get("daily_tasks", {})
print("\nTareas de limpieza detectadas:")
for emp, days in tasks.items():
    tasks_found = {d: v for d, v in days.items() if v}
    if tasks_found:
        print(f"  {emp}: {tasks_found}")
