import sqlite3
db_path = r'C:\users\kenda\onedrive\escritorio\filtros\packaging\Chronos\planillas\planilla.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
try:
    rows = conn.execute('SELECT id, nombre, timestamp, deleted FROM horarios_generados ORDER BY id ASC').fetchall()
    print('Total rows in packaging DB:', len(rows))
    for r in rows:
        print('  id=%d nombre=%s ts=%s deleted=%d' % (r['id'], r['nombre'], r['timestamp'], r['deleted']))
except Exception as e:
    print('Error querying horarios_generados:', e)
    # Try to list tables
    try:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        print('Tables:', [t['name'] for t in tables])
    except Exception as e2:
        print('Error listing tables:', e2)
conn.close()
