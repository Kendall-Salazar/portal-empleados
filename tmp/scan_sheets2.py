import sys, json, codecs
sys.path.insert(0, 'planillas')
import horario_excel_import as hei

path = r'C:\Users\kenda\Downloads\horario 2026 (2).xlsx'
sheets = hei.list_sheet_names(path)

output_lines = []
output_lines.append("Hojas: " + str(sheets))
output_lines.append("")

for sname in sheets:
    try:
        r = hei.parse_workbook_sheets(path, [sname])[0]
        if not r['schedule']:
            output_lines.append(f"HOJA [{sname}] => sin empleados. Errores: {r['errors'][:1]}")
            continue
        tasks = {
            e: {d: v for d, v in ds.items() if v}
            for e, ds in (r.get('daily_tasks') or {}).items()
        }
        tasks_clean = {e: v for e, v in tasks.items() if v}
        if tasks_clean:
            output_lines.append(f"HOJA [{sname}] => {len(tasks_clean)} empleados CON TAREAS:")
            for e, t in tasks_clean.items():
                output_lines.append(f"  {e}: {t}")
        else:
            warn_str = str(r['warnings'][:2]) if r['warnings'] else ''
            output_lines.append(f"HOJA [{sname}] => {len(r['schedule'])} empleados, sin tareas. warns:{warn_str}")
    except Exception as ex:
        output_lines.append(f"HOJA [{sname}] ERROR: {ex}")

out_path = 'tmp/scan_result.txt'
with codecs.open(out_path, 'w', 'utf-8') as f:
    f.write('\n'.join(output_lines))
print("Listo, revisa tmp/scan_result.txt")
