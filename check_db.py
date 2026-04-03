import sqlite3
db_path = r'C:/users/kenda/onedrive/escritorio/filtros/planillas/planilla.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
rows = conn.execute('SELECT id, nombre, timestamp, deleted FROM horarios_generados ORDER BY id ASC').fetchall()
print('Total rows:', len(rows))
active = [r for r in rows if r['deleted'] == 0]
deleted = [r for r in rows if r['deleted'] == 1]
print('Active:', len(active))
print('Deleted (trash):', len(deleted))
for r in rows:
    print('  id=%d nombre=%r ts=%s deleted=%s' % (r['id'], r['nombre'], r['timestamp'], r['deleted']))
conn.close()
