import sqlite3
import json
import os

db_path = r'c:\Users\kenda\OneDrive\Escritorio\filtros\planillas\planilla.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Buscar la semana 15
rows = conn.execute("SELECT * FROM horarios_generados WHERE nombre LIKE '%Semana 15%'").fetchall()

for r in rows:
    print(f"ID: {r['id']}")
    print(f"Nombre: {r['nombre']}")
    print(f"Timestamp: {r['timestamp']}")
    
    metadata = json.loads(r['metadata']) if r['metadata'] else {}
    print(f"Metadata (Special Days): {metadata.get('special_days')}")
    
    horario = json.loads(r['horario']) if r['horario'] else {}
    
    # Buscar Natanael y Steven
    for emp_name in ['Natanael', 'Steven']:
        if emp_name in horario:
            print(f"Horario de {emp_name}: {horario[emp_name]}")
        else:
            # Buscar por nombre parcial si no está exacto
            found = False
            for k in horario.keys():
                if emp_name.lower() in k.lower():
                    print(f"Horario de {k}: {horario[k]}")
                    found = True
            if not found:
                print(f"{emp_name} no encontrado en el horario")
    print("-" * 40)

conn.close()
