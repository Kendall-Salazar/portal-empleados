from __future__ import annotations

import argparse
import asyncio
import importlib
import io
import json
import shutil
import sys
import tempfile
import time
import traceback
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import openpyxl
from fastapi.routing import APIRoute


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_NAMES = {
    "main",
    "database",
    "planilla",
    "horario_db",
    "scheduler_engine",
    "generador_boletas",
    "docx_generator",
}
TINY_PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO2Z1l8AAAAASUVORK5CYII="
)


class ValidationError(RuntimeError):
    pass


@dataclass
class Profile:
    name: str
    source_root: Path


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        if not self.body:
            return None
        return json.loads(self.text)


async def asgi_request(
    app: Any,
    method: str,
    url: str,
    *,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
) -> Response:
    split = urlsplit(url)
    request_headers = {"host": "testserver"}
    if headers:
        request_headers.update(headers)
    if "content-length" not in {k.lower() for k in request_headers}:
        request_headers["content-length"] = str(len(body))

    sent = False
    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": "http",
        "path": unquote(split.path),
        "raw_path": split.path.encode("utf-8"),
        "query_string": split.query.encode("utf-8"),
        "root_path": "",
        "headers": [
            (key.lower().encode("utf-8"), value.encode("utf-8"))
            for key, value in request_headers.items()
        ],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
        "state": {},
    }

    await app(scope, receive, send)

    start = next((msg for msg in messages if msg["type"] == "http.response.start"), None)
    if start is None:
        raise ValidationError(f"No response start received for {method} {url}")

    chunks = [msg.get("body", b"") for msg in messages if msg["type"] == "http.response.body"]
    response_headers = {
        key.decode("utf-8").lower(): value.decode("utf-8")
        for key, value in start.get("headers", [])
    }
    return Response(start["status"], response_headers, b"".join(chunks))


def json_request(
    app: Any,
    method: str,
    url: str,
    *,
    payload: Any | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    body = b""
    merged_headers = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        merged_headers["content-type"] = "application/json; charset=utf-8"
    return asyncio.run(asgi_request(app, method, url, body=body, headers=merged_headers))


def multipart_request(
    app: Any,
    method: str,
    url: str,
    *,
    field_name: str,
    filename: str,
    content: bytes,
) -> Response:
    boundary = "----ChronosValidationBoundary"
    buffer = io.BytesIO()
    buffer.write(f"--{boundary}\r\n".encode("utf-8"))
    buffer.write(
        (
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
            "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n"
        ).encode("utf-8")
    )
    buffer.write(content)
    buffer.write(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return asyncio.run(
        asgi_request(
            app,
            method,
            url,
            body=buffer.getvalue(),
            headers={"content-type": f"multipart/form-data; boundary={boundary}"},
        )
    )


def ensure(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def iso_week_name(day_value: date) -> str:
    return f"Semana {day_value.isocalendar().week}"


def build_week_dates(friday_iso: str, day_names: list[str]) -> dict[str, str]:
    friday = date.fromisoformat(friday_iso)
    return {
        day_names[index]: (friday + timedelta(days=index)).strftime("%d/%m/%Y")
        for index in range(7)
    }


def build_inventory_excel(rows: list[tuple[str, float, str, float]]) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Inventario"
    sheet.append(["Nombre", "Precio", "Codigo", "Existencias"])
    for row in rows:
        sheet.append(list(row))
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def clear_profile_modules() -> None:
    for module_name in list(sys.modules):
        if module_name in MODULE_NAMES or module_name.startswith("_shared_docx_generator"):
            sys.modules.pop(module_name, None)


def prepare_workspace(profile: Profile) -> tuple[Path, Path]:
    base_tmp = PROJECT_ROOT / ".validation_tmp"
    base_tmp.mkdir(exist_ok=True)
    temp_root = base_tmp / f"chronos_validate_{profile.name}_{uuid.uuid4().hex[:8]}"
    temp_root.mkdir()
    app_root = temp_root / profile.name

    shutil.copytree(profile.source_root / "backend", app_root / "backend")
    shutil.copytree(profile.source_root / "frontend", app_root / "frontend")
    shutil.copytree(profile.source_root / "planillas", app_root / "planillas")

    for file_name in ("database.json", "run_app.py"):
        source_file = profile.source_root / file_name
        if source_file.exists():
            shutil.copy2(source_file, app_root / file_name)

    (app_root / "export_horarios").mkdir(parents=True, exist_ok=True)
    (app_root / "acciones de empleado").mkdir(parents=True, exist_ok=True)

    db_file = app_root / "planillas" / "planilla.db"
    if db_file.exists():
        db_file.unlink()

    return temp_root, app_root


class Validator:
    def __init__(self, profile: Profile, app_root: Path):
        self.profile = profile
        self.app_root = app_root
        self.covered_routes: set[tuple[str, str]] = set()
        self.available_routes: set[tuple[str, str]] = set()
        self.main: Any | None = None
        self.scheduler_engine: Any | None = None
        self.docx_generator: Any | None = None
        self.app: Any | None = None
        self.scheduler_employees: list[dict[str, Any]] = []
        self.config: dict[str, Any] = {}
        self.planilla_employees: list[dict[str, Any]] = []
        self.primary_employee: dict[str, Any] | None = None
        self.secondary_employee: dict[str, Any] | None = None
        self.fixed_employee: dict[str, Any] | None = None
        self.week_start = "2026-03-13"
        self.week_dates: dict[str, str] = {}
        self.schedule_result: dict[str, Any] = {}
        self.history_entry: dict[str, Any] = {}
        self.fixture_result: dict[str, Any] = {}
        self.horario_id: int | None = None
        self.month_id: int | None = None
        self.week_id: int | None = None
        self.week_name: str | None = None
        self.closed_week_id: int | None = None
        self.closed_week_name: str | None = None
        self.vacation_id: int | None = None
        self.permission_id: int | None = None
        self.loan_id: int | None = None
        self.liquidation_data: dict[str, Any] = {}
        self.inventory_latest_id: int | None = None

    def log(self, message: str) -> None:
        print(f"[{self.profile.name}] {message}")

    def load_modules(self) -> None:
        clear_profile_modules()
        sys.path.insert(0, str(self.app_root / "planillas"))
        sys.path.insert(0, str(self.app_root / "backend"))

        self.main = importlib.import_module("main")
        self.scheduler_engine = importlib.import_module("scheduler_engine")
        self.docx_generator = importlib.import_module("docx_generator")
        self.fixture_result = self.load_schedule_fixture()

        original_scheduler = self.main.ShiftScheduler
        fixture_result = self.fixture_result
        day_names = list(self.scheduler_engine.DAYS)

        class ValidationShiftScheduler(original_scheduler):
            def __init__(self, employees_config: Any, global_config: Any, history_data: Any = None):
                patched_config = dict(global_config or {})
                patched_config.setdefault("max_time", 20)
                super().__init__(employees_config, patched_config, history_data)

            def solve(self):
                if fixture_result.get("schedule"):
                    schedule = {}
                    for employee in self.employees:
                        source_days = fixture_result["schedule"].get(employee, {})
                        schedule[employee] = {
                            day: source_days.get(day, "OFF")
                            for day in day_names
                        }

                    tasks_source = fixture_result.get("daily_tasks", {}) or {}
                    if tasks_source:
                        daily_tasks = {
                            employee: {
                                day: tasks_source.get(employee, {}).get(day)
                                for day in day_names
                            }
                            for employee in self.employees
                        }
                    else:
                        daily_tasks = self.assign_tasks(schedule)

                    return {
                        "status": "Success",
                        "schedule": schedule,
                        "daily_tasks": daily_tasks,
                        "metadata": {
                            "fixture_based": True,
                            "solutions_found": 1,
                        },
                    }
                return super().solve()

        self.main.ShiftScheduler = ValidationShiftScheduler
        self.scheduler_engine.ShiftScheduler = ValidationShiftScheduler

        if hasattr(self.main.os, "startfile"):
            self.main.os.startfile = lambda *_args, **_kwargs: None
        if hasattr(self.docx_generator, "_open_folder"):
            self.docx_generator._open_folder = lambda *_args, **_kwargs: None

        self.app = self.main.app
        self.available_routes = {
            (method, route.path)
            for route in self.app.routes
            if isinstance(route, APIRoute)
            for method in sorted(route.methods - {"HEAD", "OPTIONS"})
        }

    def load_schedule_fixture(self) -> dict[str, Any]:
        db_json = self.app_root / "database.json"
        if not db_json.exists():
            return {}
        with db_json.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        last_result = payload.get("last_result") or {}
        if last_result.get("schedule"):
            return {
                "schedule": last_result.get("schedule", {}),
                "daily_tasks": last_result.get("daily_tasks", {}),
            }
        history_log = payload.get("history_log") or []
        if history_log:
            latest = history_log[-1]
            return {
                "schedule": latest.get("schedule", {}),
                "daily_tasks": latest.get("daily_tasks", {}),
            }
        return {}

    def unload_modules(self) -> None:
        sys.path = [
            entry
            for entry in sys.path
            if entry not in {
                str(self.app_root / "planillas"),
                str(self.app_root / "backend"),
            }
        ]
        clear_profile_modules()

    def has_route(self, method: str, path: str) -> bool:
        return (method, path) in self.available_routes

    def request(
        self,
        method: str,
        url: str,
        *,
        template: str | None = None,
        payload: Any | None = None,
        expected_status: int = 200,
    ) -> Response:
        template = template or urlsplit(url).path
        self.covered_routes.add((method, template))
        response = json_request(self.app, method, url, payload=payload)
        ensure(
            response.status == expected_status,
            f"{method} {url} returned {response.status}: {response.text[:400]}",
        )
        return response

    def upload(
        self,
        url: str,
        *,
        template: str,
        filename: str,
        content: bytes,
        expected_status: int = 200,
    ) -> Response:
        self.covered_routes.add(("POST", template))
        response = multipart_request(self.app, "POST", url, field_name="file", filename=filename, content=content)
        ensure(
            response.status == expected_status,
            f"POST {url} returned {response.status}: {response.text[:400]}",
        )
        return response

    def refresh_planilla_employees(self) -> list[dict[str, Any]]:
        response = self.request("GET", "/api/planillas/empleados", template="/api/planillas/empleados")
        self.planilla_employees = response.json()
        return self.planilla_employees

    def ensure_planilla_employee_baseline(self, minimum: int = 3) -> list[dict[str, Any]]:
        employees = self.refresh_planilla_employees()
        if len(employees) >= minimum:
            return employees

        existing_names = {employee["nombre"] for employee in employees}
        for index, scheduler_employee in enumerate(self.scheduler_employees):
            if len(employees) >= minimum:
                break

            candidate_name = scheduler_employee["name"]
            if candidate_name in existing_names:
                continue

            payload = {
                "nombre": candidate_name,
                "tipo_pago": "efectivo",
                "salario_fijo": None,
                "cedula": None,
                "correo": f"qa.seed{index + 1}@example.com",
                "telefono": None,
                "fecha_inicio": f"2025-01-{index + 1:02d}",
                "aplica_seguro": 1,
                "genero": scheduler_employee.get("gender") or "M",
                "puede_nocturno": int(scheduler_employee.get("can_do_night", True)),
                "forced_libres": int(scheduler_employee.get("forced_libres", False)),
                "forced_quebrado": int(scheduler_employee.get("forced_quebrado", False)),
                "allow_no_rest": int(scheduler_employee.get("allow_no_rest", False)),
                "es_jefe_pista": int(scheduler_employee.get("is_jefe_pista", False)),
                "strict_preferences": int(scheduler_employee.get("strict_preferences", False)),
                "activo": 1,
                "turnos_fijos": json.dumps(scheduler_employee.get("fixed_shifts", {}), ensure_ascii=False),
            }
            self.request("POST", "/api/planillas/empleados", template="/api/planillas/empleados", payload=payload)
            existing_names.add(candidate_name)
            employees = self.refresh_planilla_employees()

        ensure(len(employees) >= minimum, "Planilla module did not expose enough employees")
        return employees

    def find_planilla_employee(self, name: str) -> dict[str, Any]:
        matches = [employee for employee in self.planilla_employees if employee["nombre"] == name]
        ensure(bool(matches), f"Employee {name} not found in planilla data")
        return matches[0]

    def planilla_payload(self, employee: dict[str, Any], **overrides: Any) -> dict[str, Any]:
        turnos_fijos = employee.get("turnos_fijos", "{}")
        if isinstance(turnos_fijos, dict):
            turnos_fijos = json.dumps(turnos_fijos, ensure_ascii=False)
        payload = {
            "nombre": employee["nombre"],
            "tipo_pago": employee.get("tipo_pago") or "efectivo",
            "salario_fijo": employee.get("salario_fijo"),
            "cedula": employee.get("cedula"),
            "correo": employee.get("correo"),
            "telefono": employee.get("telefono"),
            "fecha_inicio": employee.get("fecha_inicio"),
            "aplica_seguro": int(employee.get("aplica_seguro", 1) or 0),
            "genero": employee.get("genero") or "M",
            "puede_nocturno": int(employee.get("puede_nocturno", 1) or 0),
            "forced_libres": int(employee.get("forced_libres", 0) or 0),
            "forced_quebrado": int(employee.get("forced_quebrado", 0) or 0),
            "allow_no_rest": int(employee.get("allow_no_rest", 0) or 0),
            "es_jefe_pista": int(employee.get("es_jefe_pista", 0) or 0),
            "strict_preferences": int(employee.get("strict_preferences", 0) or 0),
            "activo": int(employee.get("activo", 1) or 0),
            "turnos_fijos": turnos_fijos or "{}",
        }
        payload.update(overrides)
        return payload

    def validate_static_frontend(self) -> None:
        self.log("Checking static frontend delivery")
        index_response = json_request(self.app, "GET", "/")
        ensure(index_response.status == 200, f"GET / failed: {index_response.status}")
        ensure("app.js" in index_response.text, "Frontend index did not reference app.js")
        ensure("planillas_ui.js" in index_response.text, "Frontend index did not reference planillas_ui.js")
        ensure("style.css" in index_response.text, "Frontend index did not reference style.css")

        for asset in ("/app.js", "/planillas_ui.js", "/style.css"):
            asset_response = json_request(self.app, "GET", asset)
            ensure(asset_response.status == 200, f"GET {asset} failed with {asset_response.status}")
            ensure(len(asset_response.body) > 50, f"Static asset {asset} looked empty")

    def validate_scheduler(self) -> None:
        self.log("Seeding scheduler employees and solving a schedule")
        seed = self.main.load_db()["employees"]
        ensure(seed, "Scheduler seed employees were not initialized")

        self.request("POST", "/api/employees", template="/api/employees", payload=seed)

        employees_response = self.request("GET", "/api/employees?include_inactive=true", template="/api/employees")
        self.scheduler_employees = employees_response.json()
        ensure(len(self.scheduler_employees) >= 8, "Scheduler employee sync returned too few employees")

        config_response = self.request("GET", "/api/config", template="/api/config")
        self.config = config_response.json()
        night_candidates = [employee["name"] for employee in self.scheduler_employees if employee.get("can_do_night")]
        ensure(night_candidates, "No night-capable employees available for config validation")
        self.config.update(
            {
                "night_mode": "rotation",
                "fixed_night_person": night_candidates[0],
                "allow_long_shifts": True,
                "use_refuerzo": False,
                "refuerzo_type": "automatico",
                "allow_collision_quebrado": False,
                "collision_peak_priority": "pm",
                "use_history": True,
            }
        )
        self.request("POST", "/api/config", template="/api/config", payload=self.config)

        self.request("GET", "/api/history", template="/api/history")
        self.request("GET", "/api/validation_rules", template="/api/validation_rules")

        solve_payload = {
            "employees": self.scheduler_employees,
            "config": self.config,
            "target_week_start": self.week_start,
        }
        solve_response = self.request("POST", "/api/solve", template="/api/solve", payload=solve_payload)
        self.schedule_result = solve_response.json()
        ensure(self.schedule_result.get("status") == "Success", f"Scheduler did not return success: {self.schedule_result}")
        ensure(self.schedule_result.get("schedule"), "Scheduler did not return a schedule")

        self.week_dates = build_week_dates(self.week_start, list(self.scheduler_engine.DAYS))
        history_payload = {
            "name": iso_week_name(date.fromisoformat(self.week_start)),
            "schedule": self.schedule_result["schedule"],
            "daily_tasks": self.schedule_result.get("daily_tasks", {}),
            "week_dates": self.week_dates,
            "timestamp": "",
        }
        self.request("POST", "/api/history", template="/api/history", payload=history_payload)

        history_response = self.request("GET", "/api/history", template="/api/history")
        history_items = history_response.json()
        ensure(len(history_items) == 1, f"Expected one history item, found {len(history_items)}")
        self.history_entry = history_items[0]

        patched_payload = {
            "name": self.history_entry["name"],
            "schedule": self.history_entry["schedule"],
            "daily_tasks": self.history_entry.get("daily_tasks", {}),
            "week_dates": self.history_entry.get("week_dates"),
            "timestamp": self.history_entry.get("timestamp", ""),
        }
        self.request("PATCH", "/api/history/0", template="/api/history/{index}", payload=patched_payload)

        if self.has_route("GET", "/api/rotacion-domingos"):
            rotation_response = self.request("GET", "/api/rotacion-domingos", template="/api/rotacion-domingos")
            ensure(bool(rotation_response.json()), "Sunday rotation endpoint returned no queue")

        excel_response = self.request("GET", "/api/export_excel", template="/api/export_excel")
        ensure(excel_response.body[:2] == b"PK", "Exported Excel did not look like an Office file")
        history_excel = self.request(
            "GET",
            "/api/export_excel?history_index=0",
            template="/api/export_excel",
        )
        ensure(history_excel.body[:2] == b"PK", "History Excel export did not look like an Office file")

        if self.has_route("POST", "/api/export_image"):
            image_response = self.request(
                "POST",
                "/api/export_image",
                template="/api/export_image",
                payload={"image_data": TINY_PNG_DATA_URL, "filename": "validate.png"},
            )
            image_data = image_response.json()
            ensure(Path(image_data["path"]).exists(), "Image export did not create a file")

    def validate_planilla_people(self) -> None:
        self.log("Validating employee CRUD and profile updates")
        employees = self.ensure_planilla_employee_baseline()

        temp_payload = {
            "nombre": "QA Temporal",
            "tipo_pago": "efectivo",
            "salario_fijo": None,
            "cedula": "9-9999-9999",
            "correo": "qa.temporal@example.com",
            "telefono": "8000-0000",
            "fecha_inicio": "2026-01-01",
            "aplica_seguro": 1,
            "genero": "M",
            "puede_nocturno": 1,
            "forced_libres": 0,
            "forced_quebrado": 0,
            "allow_no_rest": 0,
            "es_jefe_pista": 0,
            "strict_preferences": 0,
            "activo": 1,
            "turnos_fijos": "{}",
        }
        self.request("POST", "/api/planillas/empleados", template="/api/planillas/empleados", payload=temp_payload)
        employees = self.refresh_planilla_employees()
        temp_employee = next((employee for employee in employees if employee["nombre"] == "QA Temporal"), None)
        ensure(temp_employee is not None, "Temporary employee was not created")
        self.request(
            "DELETE",
            f"/api/planillas/empleados/{temp_employee['id']}",
            template="/api/planillas/empleados/{emp_id}",
        )

        employees = self.refresh_planilla_employees()
        self.primary_employee = employees[0]
        self.secondary_employee = employees[1]
        self.fixed_employee = employees[2]

        primary_payload = self.planilla_payload(
            self.primary_employee,
            tipo_pago="tarjeta",
            cedula="1-1111-1111",
            correo="colaborador1@example.com",
            telefono="8888-1001",
            fecha_inicio="2024-01-10",
            aplica_seguro=1,
        )
        secondary_payload = self.planilla_payload(
            self.secondary_employee,
            tipo_pago="efectivo",
            cedula="2-2222-2222",
            telefono="8888-1002",
            fecha_inicio="2025-02-01",
        )
        fixed_payload = self.planilla_payload(
            self.fixed_employee,
            tipo_pago="fijo",
            salario_fijo=250000,
            cedula="3-3333-3333",
            fecha_inicio="2023-06-01",
        )

        self.request(
            "PUT",
            f"/api/planillas/empleados/{self.primary_employee['id']}",
            template="/api/planillas/empleados/{emp_id}",
            payload=primary_payload,
        )
        self.request(
            "PUT",
            f"/api/planillas/empleados/{self.secondary_employee['id']}",
            template="/api/planillas/empleados/{emp_id}",
            payload=secondary_payload,
        )
        self.request(
            "PUT",
            f"/api/planillas/empleados/{self.fixed_employee['id']}",
            template="/api/planillas/empleados/{emp_id}",
            payload=fixed_payload,
        )

        employees = self.refresh_planilla_employees()
        self.primary_employee = self.find_planilla_employee(primary_payload["nombre"])
        self.secondary_employee = self.find_planilla_employee(secondary_payload["nombre"])
        self.fixed_employee = self.find_planilla_employee(fixed_payload["nombre"])

    def validate_vacations_permissions_and_loans(self) -> None:
        ensure(self.primary_employee is not None, "Primary employee was not prepared")
        self.log("Validating vacations, permissions, sync and loan flows")

        vacation_payload = {
            "empleado_id": self.primary_employee["id"],
            "fecha_inicio": "2026-03-13",
            "fecha_fin": "2026-03-14",
            "dias": 2.0,
            "fecha_reingreso": "2026-03-15",
            "notas": "Prueba QA",
        }
        self.request("POST", "/api/planillas/vacaciones", template="/api/planillas/vacaciones", payload=vacation_payload)
        vacations_response = self.request(
            "GET",
            f"/api/planillas/vacaciones/{self.primary_employee['id']}",
            template="/api/planillas/vacaciones/{emp_id}",
        )
        vacations_data = vacations_response.json()
        ensure(vacations_data["registros"], "Vacation endpoint did not return the created record")
        self.vacation_id = vacations_data["registros"][0]["id"]

        updated_vacation = dict(vacation_payload)
        updated_vacation["dias"] = 1.5
        updated_vacation["notas"] = "Prueba QA actualizada"
        self.request(
            "PUT",
            f"/api/planillas/vacaciones/{self.vacation_id}",
            template="/api/planillas/vacaciones/{vac_id}",
            payload=updated_vacation,
        )

        if self.has_route("POST", "/api/planillas/permisos"):
            permission_payload = {
                "empleado_id": self.primary_employee["id"],
                "fecha": "2026-03-16",
                "motivo": "Cita medica",
                "notas": "Validacion automatica",
            }
            second_permission_payload = {
                "empleado_id": self.primary_employee["id"],
                "fecha": "2026-03-17",
                "motivo": "Tramite",
                "notas": "Validacion automatica 2",
            }
            permission_response = self.request(
                "POST",
                "/api/planillas/permisos",
                template="/api/planillas/permisos",
                payload=permission_payload,
            )
            self.permission_id = permission_response.json()["id"]
            second_permission_id = self.request(
                "POST",
                "/api/planillas/permisos",
                template="/api/planillas/permisos",
                payload=second_permission_payload,
            ).json()["id"]

            self.request(
                "GET",
                f"/api/planillas/permisos/{self.primary_employee['id']}?anio=2026",
                template="/api/planillas/permisos/{emp_id}",
            )
            self.request(
                "POST",
                "/api/planillas/permisos/descontar-vacaciones",
                template="/api/planillas/permisos/descontar-vacaciones",
                payload={"empleado_id": self.primary_employee["id"], "cantidad": 1, "anio": 2026},
            )
            self.request(
                "DELETE",
                f"/api/planillas/permisos/{second_permission_id}",
                template="/api/planillas/permisos/{permiso_id}",
            )

        if self.has_route("POST", "/api/sync_vac_fixed_shifts"):
            self.request(
                "POST",
                "/api/sync_vac_fixed_shifts",
                template="/api/sync_vac_fixed_shifts",
                payload={"fecha_inicio": "2026-03-13", "fecha_fin": "2026-03-19"},
            )
            scheduler_employees = self.request(
                "GET",
                "/api/employees?include_inactive=true",
                template="/api/employees",
            ).json()
            synced = next((employee for employee in scheduler_employees if employee["name"] == self.primary_employee["nombre"]), None)
            ensure(synced is not None, "Primary employee not found after sync")
            fixed_values = set((synced.get("fixed_shifts") or {}).values())
            ensure("VAC" in fixed_values, "Vacation sync did not propagate VAC fixed shifts")

        if self.has_route("POST", "/api/planillas/prestamos"):
            loan_response = self.request(
                "POST",
                "/api/planillas/prestamos",
                template="/api/planillas/prestamos",
                payload={
                    "empleado_id": self.primary_employee["id"],
                    "monto_total": 100000,
                    "pago_semanal": 10000,
                    "notas": "Prestamo de prueba",
                },
            )
            self.loan_id = loan_response.json()["id"]
            self.request("GET", "/api/planillas/prestamos", template="/api/planillas/prestamos")
            self.request(
                "GET",
                f"/api/planillas/prestamos/{self.primary_employee['id']}?solo_activos=true",
                template="/api/planillas/prestamos/{emp_id}",
            )
            self.request(
                "POST",
                f"/api/planillas/prestamos/{self.loan_id}/abono",
                template="/api/planillas/prestamos/{prestamo_id}/abono",
                payload={"monto": 5000, "tipo": "manual", "semana_planilla": "Semana QA", "notas": "Abono QA"},
            )
            self.request(
                "GET",
                f"/api/planillas/prestamos/{self.loan_id}/abonos",
                template="/api/planillas/prestamos/{prestamo_id}/abonos",
            )

    def validate_tariffs_months_and_payroll(self) -> None:
        self.log("Validating payroll configuration, month lifecycle and exports")
        self.request("GET", "/api/planillas/tarifas", template="/api/planillas/tarifas")
        self.request(
            "POST",
            "/api/planillas/tarifas",
            template="/api/planillas/tarifas",
            payload={
                "tarifa_diurna": 51.0,
                "tarifa_nocturna": 76.0,
                "tarifa_mixta": 63.0,
                "seguro": 10500.0,
            },
        )

        self.request("GET", "/api/planillas/meses", template="/api/planillas/meses")
        self.request("GET", "/api/planillas/meses/activo", template="/api/planillas/meses/activo")

        month_response = self.request(
            "POST",
            "/api/planillas/meses",
            template="/api/planillas/meses",
            payload={"anio": 2026, "mes": 3},
        )
        self.month_id = month_response.json()["mes"]["id"]
        self.request("GET", "/api/planillas/meses/activo", template="/api/planillas/meses/activo")
        self.request("GET", "/api/planillas/meses", template="/api/planillas/meses")

        week_response = self.request(
            "POST",
            "/api/planillas/semanas",
            template="/api/planillas/semanas",
            payload={"mes_id": self.month_id, "viernes": self.week_start},
        )
        weeks = week_response.json()["semanas"]
        ensure(weeks, "Week creation did not return any week entries")
        active_week = weeks[-1]
        self.week_id = active_week["id"]
        self.week_name = iso_week_name(date.fromisoformat(self.week_start))

        horarios_response = self.request(
            "GET",
            "/api/planillas/horarios-disponibles",
            template="/api/planillas/horarios-disponibles",
        )
        horarios = horarios_response.json()["horarios"]
        ensure(horarios, "No generated schedules available for planilla import")
        self.horario_id = horarios[0]["id"]

        self.request(
            "POST",
            "/api/planillas/semanas/importar",
            template="/api/planillas/semanas/importar",
            payload={
                "horario_id": self.horario_id,
                "semana_nombre": self.week_name,
                "sync_empleados": True,
            },
        )

        self.request(
            "POST",
            "/api/planillas/boletas/generar",
            template="/api/planillas/boletas/generar",
            payload={"semana_nombre": self.week_name},
        )
        self.request("GET", "/api/planillas/excel/abrir", template="/api/planillas/excel/abrir")
        self.request(
            "GET",
            f"/api/planillas/excel/abrir/{self.month_id}",
            template="/api/planillas/excel/abrir/{mes_id}",
        )

        liquidation_response = self.request(
            "GET",
            f"/api/planillas/liquidacion/{self.primary_employee['id']}",
            template="/api/planillas/liquidacion/{emp_id}",
        )
        self.liquidation_data = liquidation_response.json()

        self.request(
            "POST",
            "/api/planillas/salarios",
            template="/api/planillas/salarios",
            payload={
                "salarios": [
                    {
                        "empleado_id": self.secondary_employee["id"],
                        "empleado_nombre": self.secondary_employee["nombre"],
                        "anio": 2026,
                        "mes": 3,
                        "semana": 99,
                        "salario_bruto": 12345.67,
                    }
                ]
            },
        )
        self.request(
            "POST",
            "/api/planillas/sincronizar-aguinaldo/2026",
            template="/api/planillas/sincronizar-aguinaldo/{anio}",
        )
        self.request(
            "GET",
            "/api/planillas/aguinaldo/2026",
            template="/api/planillas/aguinaldo/{anio}",
        )

        self.request(
            "POST",
            f"/api/planillas/meses/{self.month_id}/cerrar",
            template="/api/planillas/meses/{mes_id}/cerrar",
        )

        second_week_start = "2026-03-20"
        second_week_response = self.request(
            "POST",
            f"/api/planillas/meses/{self.month_id}/semanas",
            template="/api/planillas/meses/{mes_id}/semanas",
            payload={"mes_id": self.month_id, "viernes": second_week_start},
        )
        closed_weeks = second_week_response.json()["semanas"]
        target_week = next((week for week in closed_weeks if week["viernes"] == second_week_start), None)
        ensure(target_week is not None, "Historical week creation did not register the new week")
        self.closed_week_id = target_week["id"]
        self.closed_week_name = iso_week_name(date.fromisoformat(second_week_start))

        self.request(
            "POST",
            f"/api/planillas/meses/{self.month_id}/semanas/{self.closed_week_name}/importar",
            template="/api/planillas/meses/{mes_id}/semanas/{semana_nombre}/importar",
            payload={
                "horario_id": self.horario_id,
                "semana_nombre": self.closed_week_name,
                "sync_empleados": True,
            },
        )

        self.request(
            "DELETE",
            f"/api/planillas/semanas/{self.closed_week_id}",
            template="/api/planillas/semanas/{semana_id}",
        )

    def validate_documents(self) -> None:
        if not self.has_route("POST", "/api/utilidades/prestamo"):
            return
        self.log("Validating document generation utilities")

        prestamo_doc = self.request(
            "POST",
            "/api/utilidades/prestamo",
            template="/api/utilidades/prestamo",
            payload={"emp_id": self.primary_employee["id"], "monto_total": 80000, "pago_semanal": 10000},
        ).json()
        ensure(Path(prestamo_doc["path"]).exists(), "Prestamo document was not generated")

        amonestacion_doc = self.request(
            "POST",
            "/api/utilidades/amonestacion",
            template="/api/utilidades/amonestacion",
            payload={
                "emp_id": self.primary_employee["id"],
                "tipo": "faltantes",
                "datos": [{"fecha": "2026-03-15", "monto": 2500.0}],
            },
        ).json()
        ensure(Path(amonestacion_doc["path"]).exists(), "Amonestacion document was not generated")

        vacaciones_doc = self.request(
            "POST",
            "/api/utilidades/vacaciones",
            template="/api/utilidades/vacaciones",
            payload={
                "emp_id": self.primary_employee["id"],
                "tipo": "total",
                "fecha_inicio": "2026-03-13",
                "fecha_reingreso": "2026-03-15",
            },
        ).json()
        ensure(Path(vacaciones_doc["path"]).exists(), "Vacaciones document was not generated")

        total_renuncia = self.liquidation_data.get("total_renuncia", 0) or 0
        total_despido = self.liquidation_data.get("total_despido", 0) or 0
        despido_doc = self.request(
            "POST",
            "/api/utilidades/despido",
            template="/api/utilidades/despido",
            payload={
                "emp_id": self.primary_employee["id"],
                "vacaciones_dias": self.liquidation_data.get("vacaciones_dias", 0),
                "vacaciones_monto": self.liquidation_data.get("vacaciones_monto", 0),
                "aguinaldo_monto": self.liquidation_data.get("aguinaldo_monto", 0),
                "cesantia_monto": self.liquidation_data.get("cesantia_monto", 0),
                "preaviso_monto": self.liquidation_data.get("preaviso_monto", 0),
                "total_pagar": total_despido,
                "modo_pago": "Total",
            },
        ).json()
        ensure(Path(despido_doc["path"]).exists(), "Despido document was not generated")

        renuncia_doc = self.request(
            "POST",
            "/api/utilidades/renuncia",
            template="/api/utilidades/renuncia",
            payload={
                "emp_id": self.primary_employee["id"],
                "vacaciones_dias": self.liquidation_data.get("vacaciones_dias", 0),
                "vacaciones_monto": self.liquidation_data.get("vacaciones_monto", 0),
                "aguinaldo_monto": self.liquidation_data.get("aguinaldo_monto", 0),
                "cesantia_monto": 0,
                "preaviso_monto": 0,
                "total_pagar": total_renuncia,
                "modo_pago": "Abonos",
            },
        ).json()
        ensure(Path(renuncia_doc["path"]).exists(), "Renuncia document was not generated")

        recomendacion_doc = self.request(
            "POST",
            "/api/utilidades/recomendacion",
            template="/api/utilidades/recomendacion",
            payload={
                "emp_id": self.primary_employee["id"],
                "puesto": "Asistente QA",
                "texto_adicional": "Documento generado durante la validacion automatica.",
            },
        ).json()
        ensure(Path(recomendacion_doc["path"]).exists(), "Recomendacion document was not generated")

    def validate_inventory(self) -> None:
        if not self.has_route("POST", "/api/inventario/upload"):
            return
        self.log("Validating inventory uploads and diff logic")

        first_file = build_inventory_excel(
            [
                ("Cafe", 2500.0, "A1", 10),
                ("Azucar", 1200.0, "A2", 8),
                ("Leche", 1800.0, "A3", 6),
            ]
        )
        second_file = build_inventory_excel(
            [
                ("Cafe", 2500.0, "A1", 7),
                ("Azucar", 1200.0, "A2", 8),
                ("Leche", 1800.0, "A3", 9),
                ("Te", 900.0, "A4", 4),
            ]
        )

        upload_one = self.upload(
            "/api/inventario/upload",
            template="/api/inventario/upload",
            filename="inventario_1.xlsx",
            content=first_file,
        ).json()
        ensure(upload_one["total_articulos"] == 3, "First inventory upload returned an unexpected count")
        self.request("GET", "/api/inventario/latest", template="/api/inventario/latest")
        self.request("GET", "/api/inventario/diff", template="/api/inventario/diff")
        self.request("GET", "/api/inventario/history", template="/api/inventario/history")

        upload_two = self.upload(
            "/api/inventario/upload",
            template="/api/inventario/upload",
            filename="inventario_2.xlsx",
            content=second_file,
        ).json()
        self.inventory_latest_id = upload_two["carga_id"]
        diff_data = self.request("GET", "/api/inventario/diff", template="/api/inventario/diff").json()
        ensure(diff_data["resumen"]["total_consumidos"] >= 1, "Inventory diff did not detect consumed items")
        ensure(diff_data["resumen"]["total_nuevos"] >= 1, "Inventory diff did not detect new items")

        self.request(
            "DELETE",
            f"/api/inventario/{self.inventory_latest_id}",
            template="/api/inventario/{carga_id}",
        )

    def cleanup(self) -> None:
        self.log("Running cleanup-only API checks")
        if self.loan_id is not None and self.has_route("DELETE", "/api/planillas/prestamos/{prestamo_id}"):
            self.request(
                "DELETE",
                f"/api/planillas/prestamos/{self.loan_id}",
                template="/api/planillas/prestamos/{prestamo_id}",
            )

        if self.vacation_id is not None:
            self.request(
                "DELETE",
                f"/api/planillas/vacaciones/{self.vacation_id}",
                template="/api/planillas/vacaciones/{vac_id}",
            )

        if self.permission_id is not None and self.has_route("DELETE", "/api/planillas/permisos/{permiso_id}"):
            self.request(
                "DELETE",
                f"/api/planillas/permisos/{self.permission_id}",
                template="/api/planillas/permisos/{permiso_id}",
            )

        if self.month_id is not None and self.has_route("DELETE", "/api/planillas/meses/{mes_id}"):
            self.request(
                "DELETE",
                f"/api/planillas/meses/{self.month_id}",
                template="/api/planillas/meses/{mes_id}",
            )

        if self.has_route("DELETE", "/api/history/{index}"):
            self.request("DELETE", "/api/history/0", template="/api/history/{index}")

    def ensure_full_route_coverage(self) -> None:
        missing = sorted(self.available_routes - self.covered_routes)
        ensure(not missing, "Missing API coverage for routes: " + ", ".join(f"{method} {path}" for method, path in missing))

    def run(self) -> None:
        start = time.perf_counter()
        self.load_modules()
        try:
            self.validate_static_frontend()
            self.validate_scheduler()
            self.validate_planilla_people()
            self.validate_vacations_permissions_and_loans()
            self.validate_tariffs_months_and_payroll()
            self.validate_documents()
            self.validate_inventory()
            self.cleanup()
            self.ensure_full_route_coverage()
        finally:
            self.unload_modules()
        elapsed = time.perf_counter() - start
        self.log(f"Validation completed in {elapsed:.1f}s")


def selected_profiles(profile_arg: str) -> list[Profile]:
    profiles = [Profile("root", PROJECT_ROOT)]

    if profile_arg == "all":
        return profiles

    selected = [profile for profile in profiles if profile.name.lower() == profile_arg.lower()]
    if not selected:
        raise ValidationError(f"Unknown profile: {profile_arg}")
    return selected


def run_profile(profile: Profile, keep_temp: bool) -> None:
    temp_root, app_root = prepare_workspace(profile)
    try:
        validator = Validator(profile, app_root)
        validator.run()
    finally:
        if keep_temp:
            print(f"[{profile.name}] Temp workspace kept at {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Chronos application profiles end-to-end.")
    parser.add_argument(
        "--profile",
        default="all",
        choices=["all", "root"],
        help="Profile to validate. Default: all (excludes backup folders)",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temporary workspaces for debugging.",
    )
    args = parser.parse_args()

    profiles = selected_profiles(args.profile)
    failures: list[tuple[str, str]] = []

    for profile in profiles:
        try:
            run_profile(profile, keep_temp=args.keep_temp)
        except Exception as exc:
            failures.append((profile.name, "".join(traceback.format_exception(exc))))

    if failures:
        print("\nValidation failed:\n")
        for profile_name, details in failures:
            print(f"--- {profile_name} ---")
            print(details)
        return 1

    print("\nAll selected profiles validated successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
