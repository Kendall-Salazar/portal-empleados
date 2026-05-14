import sqlite3
import json
import os

db_path = r'c:\Users\kenda\OneDrive\Escritorio\filtros\planillas\planilla.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Buscar la semana 15
rows = list(conn.execute("SELECT * FROM horarios_generados WHERE nombre LIKE '%Semana 15%'").fetchall())

with open(r'c:\Users\kenda\OneDrive\Escritorio\filtros\tmp\history_data.txt', 'w', encoding='utf-8') as f:
    f.write(f"Total rows found: {len(rows)}\n")
    for r in rows:
        f.write(f"ID: {r['id']}\n")
        f.write(f"Nombre: {r['nombre']}\n")
        metadata = json.loads(r['metadata']) if r['metadata'] else {}
        f.write(f"Special Days: {metadata.get('special_days')}\n")
        horario = json.loads(r['horario']) if r['horario'] else {}
        for emp, shifts in horario.items():
            if 'natanael' in emp.lower() or 'steven' in emp.lower():
                f.write(f"  {emp}: {shifts}\n")
        f.write("-" * 40 + "\n")

conn.close()
