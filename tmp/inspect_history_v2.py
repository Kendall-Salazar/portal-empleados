import sqlite3
import json
import os

db_path = r'c:\Users\kenda\OneDrive\Escritorio\filtros\planillas\planilla.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Buscar la semana 15
rows = conn.execute("SELECT * FROM horarios_generados WHERE nombre LIKE '%Semana 15%'").fetchall()

print(f"Total rows found: {len(rows)}")

for r in rows:
    print(f"ID: {r['id']}")
    print(f"Nombre: {r['nombre']}")
    
    metadata = json.loads(r['metadata']) if r['metadata'] else {}
    print(f"Special Days: {metadata.get('special_days')}")
    
    horario = json.loads(r['horario']) if r['horario'] else {}
    
    # List all employee names to avoid missing them
    all_names = list(horario.keys())
    print(f"Employees in schedule: {all_names}")
    
    for emp_name in ['Natanael', 'Steven']:
        target = None
        for k in all_names:
            if emp_name.lower() in k.lower():
                target = k
                break
        
        if target:
            print(f"Horario de {target}: {horario[target]}")
        else:
            print(f"{emp_name} NO encontrado")
    print("-" * 40)

conn.close()
