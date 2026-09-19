"""Repair history entries left behind by an employee rename.

The scheduler indexes history schedules, tasks and metadata by employee NAME.
Renaming someone in the roster before this was propagated automatically left the
old name stranded in the history, so the Sunday rotation queue treated the
renamed employee as brand new ("Sin registrar") and the whole queue drifted.

Usage:
    python tools/reparar_nombres_historial.py              # dry-run (default)
    python tools/reparar_nombres_historial.py --apply      # writes, after backup
    python tools/reparar_nombres_historial.py --apply --map "Viejo=Nuevo,Otro=Otro Nuevo"
"""
import argparse
import os
import shutil
import sys
from datetime import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PLAN = os.path.join(_ROOT, "planillas")
if _PLAN not in sys.path:
    sys.path.insert(0, _PLAN)

import database as db  # noqa: E402


def parse_map(raw):
    mapping = {}
    for pair in (raw or "").split(","):
        pair = pair.strip()
        if not pair:
            continue
        if "=" not in pair:
            raise SystemExit(f"Par inválido (se esperaba 'Viejo=Nuevo'): {pair}")
        old, new = pair.split("=", 1)
        mapping[old.strip()] = new.strip()
    return mapping


def backup_db():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = f"{db.DB_FILE}.bak_{stamp}"
    shutil.copy2(db.DB_FILE, destino)
    return destino


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Write the changes (default is a dry-run)")
    parser.add_argument("--map", dest="raw_map", default=None,
                        help="Explicit mapping 'Old=New,Other=Other New'")
    args = parser.parse_args()

    mapping = parse_map(args.raw_map) if args.raw_map else db.detectar_nombres_huerfanos()

    if not mapping:
        print("No hay nombres huérfanos en el historial. Nada que reparar.")
        return

    print("Mapeo de nombres a aplicar:")
    for old, new in sorted(mapping.items()):
        print(f"  {old:<12} -> {new}")
    print()

    resumen = db.renombrar_en_datos_historicos(mapping, dry_run=not args.apply)
    etiqueta = "Filas actualizadas" if args.apply else "Filas que se actualizarían"
    print(f"{etiqueta}:")
    for tabla, filas in resumen.items():
        print(f"  {tabla:<20} {filas}")

    if not args.apply:
        print("\nDry-run. Volvé a correrlo con --apply para escribir los cambios.")
        return

    print("\nListo. Regenerá la vista de rotación de domingos para verla al día.")


if __name__ == "__main__":
    # El backup se hace antes de tocar nada, solo en modo escritura.
    if "--apply" in sys.argv:
        print(f"Backup: {backup_db()}\n")
    main()
