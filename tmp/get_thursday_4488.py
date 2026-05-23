import sqlite3
import json

db_path = r'c:\Users\kenda\OneDrive\Escritorio\filtros\planillas\cronos.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Get ID 4488 Thursday
r = conn.execute("SELECT horario FROM horarios_generados WHERE id=4488").fetchone()
horario = json.loads(r['horario'])

print("Current Thursday Schedule (ID 4488):")
thursday = {}
for emp, shifts in horario.items():
    s = shifts.get('Jue', 'OFF')
    thursday[emp] = s
    print(f"{emp:12}: {s}")

conn.close()
