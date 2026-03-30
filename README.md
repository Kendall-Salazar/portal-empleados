# Chronos

App de escritorio para gestión de turnos y planillas de pago de una estación de servicio.

## Stack

- **Backend**: Python 3 + FastAPI (uvicorn)
- **Frontend**: HTML + JS vanilla + CSS (sin frameworks)
- **Shell de escritorio**: pywebview (EdgeChromium)
- **Base de datos de planillas**: SQLite (`planillas/planilla.db`)
- **Datos de horarios**: JSON (`backend/database.json`)
- **Empaquetado**: PyInstaller

## Estructura del proyecto

```
chronos/
├── run_app.py              # Punto de entrada — arranca el servidor y la ventana nativa
│
├── backend/                # Servidor FastAPI
│   ├── main.py             # Rutas API (horarios, planillas, documentos, inventario)
│   ├── scheduler_engine.py # Motor de generación automática de turnos
│   ├── docx_generator.py   # Generador de documentos Word (préstamos, liquidaciones, etc.)
│   ├── create_formato_template.py  # Utilidad para crear la plantilla Excel base
│   └── formato_template.xlsm      # Plantilla Excel con macros para exportar horarios
│
├── frontend/               # UI web servida por FastAPI
│   ├── index.html
│   ├── app.js              # Módulo principal — turnos y horarios
│   ├── planillas_ui.js     # Módulo de planillas de pago
│   └── style.css
│
├── planillas/              # Módulo de planillas de pago
│   ├── app.py              # App de escritorio standalone (Tkinter/CTk) para planillas
│   ├── planilla.py         # Lógica de planilla semanal en Excel
│   ├── database.py         # Capa de acceso a SQLite (planilla.db)
│   ├── generador_boletas.py # Generación de boletas de pago como imágenes JPEG
│   ├── horario_db.py       # Sincronización horario → planilla
│   ├── prestamo_sync.py    # Sincronización de préstamos con rebajos en planilla
│   ├── logo.png            # Logo corporativo para documentos
│   └── Planilla_de_Pago.xlsx  # Plantilla base de planilla (no editar manualmente)
│
├── packaging/              # Scripts y configuración de empaquetado (PyInstaller)
│   ├── Chronos.spec        # Spec de PyInstaller
│   ├── build.ps1           # Script de build completo
│   └── run_build_and_mark.ps1
│
└── tools/                  # Herramientas de desarrollo
    ├── validate_app.py     # Suite de validación end-to-end de la API
    └── validar_app.ps1     # Script PowerShell para correr la validación
```

## Carpetas generadas (gitignoreadas)

| Carpeta | Contenido |
|---|---|
| `backend/database.json` | Estado de empleados e historial de turnos |
| `planillas/planilla.db` | Base de datos SQLite de planillas |
| `planillas/Planillas YYYY/` | Archivos Excel de planillas generadas |
| `export_horarios/` | Exportaciones de horarios (Excel/PNG) |
| `acciones de empleado/` | Documentos Word generados (préstamos, liquidaciones, etc.) |
| `packaging/Chronos/` | Ejecutable compilado por PyInstaller |
| `.webview_data/` | Perfil de WebView2 (caché de la ventana nativa) |

## Cómo correr en desarrollo

```bash
# Instalar dependencias (una sola vez)
pip install fastapi uvicorn pywebview openpyxl python-docx pillow

# Correr la app
python run_app.py
```

## Cómo compilar el ejecutable

```powershell
# Desde la carpeta packaging/
.\build.ps1
# El ejecutable queda en packaging/Chronos/Chronos.exe
```

## Cómo correr la validación

```powershell
# Desde la raíz del proyecto
python tools/validate_app.py
```
