# Empaquetado

Esta carpeta contiene todo lo necesario para reconstruir el ejecutable de la app.

## Archivos

- `Chronos.spec`: configuracion de PyInstaller.
- `build.ps1`: genera la carpeta final con el ejecutable y copia los recursos necesarios.

## Salida esperada

Despues de ejecutar el build, el ejecutable queda en:

`empaquetado/Chronos/Chronos.exe`

La carpeta final tambien incluye:

- `planillas/`
- `webapp/frontend/`
- `webapp/backend/formato_template.xlsm`
- `export_horarios/`
- `acciones de empleado/`
