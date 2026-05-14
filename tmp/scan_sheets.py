import sys, io, json
sys.path.insert(0, 'planillas')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import horario_excel_import as hei

path = r'C:\Users\kenda\Downloads\horario 2026 (2).xlsx'
sheets = hei.list_sheet_names(path)
print("Hojas:", sheets)

for sname in sheets:
    try:
        r = hei.parse_workbook_sheets(path, [sname])[0]
        if not r['schedule']:
            continue
        tasks = {
            e: {d: v for d, v in ds.items() if v}
            for e, ds in (r.get('daily_tasks') or {}).items()
        }
        tasks_clean = {e: v for e, v in tasks.items() if v}
        if tasks_clean:
            print(f"HOJA {sname} => tiene {len(tasks_clean)} empleados con tareas")
            print(json.dumps(tasks_clean, ensure_ascii=False, indent=2))
        else:
            print(f"HOJA {sname} => {len(r['schedule'])} empleados, sin tareas detectadas (warns: {r['warnings'][:2]})")
    except Exception as ex:
        print(f"HOJA {sname} ERROR: {ex}")
