import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import sys
import subprocess
import signal
import webbrowser
from datetime import datetime, date, timedelta
import database as db
import horario_db
import generador_boletas

# Theme Colors extracted from bytecode
BG = '#0F1923'
BG2 = '#1B2838'
BG3 = '#243447'
FG = '#E2E8F0'
FG2 = '#94A3B8'
ACCENT = '#2563EB'
ACCENT_HOVER = '#3B82F6'
GREEN = '#059669'
GREEN_HOVER = '#10B981'
RED = '#B91C1C'
RED_HOVER = '#DC2626'
AMBER = '#D97706'
CARD_BG = '#1E293B'
INPUT_BG = '#334155'
INPUT_FG = '#F1F5F9'
BORDER = '#475569'

FONT = ('Segoe UI', 10)
FONT_BOLD = ('Segoe UI', 10, 'bold')
FONT_TITLE = ('Segoe UI', 16, 'bold')
FONT_SUBTITLE = ('Segoe UI', 12, 'bold')

MESES_ES = {
    1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
    5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
    9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
}

class PlanillaApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gestor de Planilla de Pago")
        self.geometry("1024x768")
        self.configure(bg=BG)
        self.webapp_process = None
        
        db.init_db()
        
        self._configure_styles()
        
        # Layout principal
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        
        self.sidebar = tk.Frame(self, bg=BG2, width=200)
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.grid_propagate(False)
        
        self.main_area = tk.Frame(self, bg=BG)
        self.main_area.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        
        self.current_frame = None
        self.nav_buttons = {}
        
        self._build_sidebar()
        self.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.show_home()

    def _configure_styles(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        
        # Estilos generales adaptados
        style.configure('TFrame', background=BG)
        style.configure('Card.TFrame', background=CARD_BG)
        style.configure('TLabel', background=BG, foreground=FG, font=FONT)
        style.configure('Title.TLabel', font=FONT_TITLE, foreground=ACCENT)
        style.configure('Subtitle.TLabel', font=FONT_SUBTITLE)
        
        # Botones
        style.configure('TButton', font=FONT_BOLD, background=INPUT_BG, foreground=FG, borderwidth=0, padding=6)
        style.map('TButton', background=[('active', BORDER)])
        
        style.configure('Accent.TButton', background=ACCENT)
        style.map('Accent.TButton', background=[('active', ACCENT_HOVER)])
        
        style.configure('Success.TButton', background=GREEN)
        style.map('Success.TButton', background=[('active', GREEN_HOVER)])
        
        style.configure('Danger.TButton', background=RED)
        style.map('Danger.TButton', background=[('active', RED_HOVER)])
        
        # Entradas
        style.configure('TEntry', fieldbackground=INPUT_BG, foreground=INPUT_FG, borderwidth=1, lightcolor=BORDER)
        style.configure('TCombobox', fieldbackground=INPUT_BG, foreground=INPUT_FG, background=INPUT_BG)
        
        # Treeview
        style.configure('Treeview', background=CARD_BG, fieldbackground=CARD_BG, foreground=FG, font=FONT, rowheight=30, borderwidth=0)
        style.map('Treeview', background=[('selected', ACCENT)])
        style.configure('Treeview.Heading', background=BG3, foreground=FG, font=FONT_BOLD, padding=5)

    def _build_sidebar(self):
        tk.Label(self.sidebar, text="SISTEMA\nPLANILLAS", font=FONT_TITLE, bg=BG2, fg=ACCENT, pady=20).pack(fill="x")
        
        navs = [
            ("Inicio", self.show_home),
            ("Empleados", self.show_empleados),
            ("Tarifas", self.show_tarifas),
            ("Planillas", self.show_planilla),
            ("Vacaciones", self.show_vacaciones),
            ("Aguinaldos", self.show_aguinaldo)
        ]
        
        for text, command in navs:
            btn = tk.Button(
                self.sidebar, text=text, command=lambda t=text, c=command: self._nav_click(t, c),
                bg=BG2, fg=FG, font=FONT_BOLD, bd=0, anchor="w", padx=20, pady=12,
                activebackground=BG3, activeforeground=ACCENT, cursor="hand2"
            )
            btn.pack(fill="x")
            self.nav_buttons[text] = btn
            
        # Spacer
        tk.Label(self.sidebar, bg=BG2).pack(fill="both", expand=True)
        
        # Webapp Launcher
        tk.Button(
            self.sidebar, text="🚀 INICIAR WEBAPP", command=self._lanzar_webapp,
            bg=GREEN, fg="white", font=FONT_BOLD, bd=0, pady=15, cursor="hand2"
        ).pack(fill="x", side="bottom")

    def _nav_click(self, text, command):
        for t, btn in self.nav_buttons.items():
            btn.configure(bg=BG2, fg=FG)
        self.nav_buttons[text].configure(bg=BG3, fg=ACCENT)
        command()

    def _clear_main(self):
        for widget in self.main_area.winfo_children():
            widget.destroy()

    def show_home(self):
        self._clear_main()
        ttk.Label(self.main_area, text="Bienvenido al Gestor de Planilla", style='Title.TLabel').pack(pady=20)
        ttk.Label(self.main_area, text="Usa el menú lateral para navegar por los módulos o Inicia la WebApp para utilizar la nueva interfaz unificada con Generación de Horarios Automática en el navegador.", wraplength=700).pack(pady=10)

    def show_empleados(self):
        self._clear_main()
        ttk.Label(self.main_area, text="Gestión de Empleados", style='Title.TLabel').pack(anchor="w", pady=(0,20))
        
        header_frame = ttk.Frame(self.main_area)
        header_frame.pack(fill="x", pady=10)
        ttk.Button(header_frame, text="+ Nuevo Empleado", style='Success.TButton', command=self._dialog_add_empleado).pack(side="left")
        
        columns = ("id", "nombre", "tipo_pago", "cedula", "telefono", "f_inicio")
        self.tree_emp = ttk.Treeview(self.main_area, columns=columns, show="headings", selectmode="browse")
        
        self.tree_emp.heading("id", text="ID")
        self.tree_emp.heading("nombre", text="Nombre")
        self.tree_emp.heading("tipo_pago", text="Pago")
        self.tree_emp.heading("cedula", text="Cédula")
        self.tree_emp.heading("telefono", text="Teléfono")
        self.tree_emp.heading("f_inicio", text="Ingreso")
        
        self.tree_emp.column("id", width=50, anchor="center")
        self.tree_emp.column("tipo_pago", width=100)
        self.tree_emp.column("cedula", width=120)
        self.tree_emp.column("telefono", width=120)
        
        self.tree_emp.pack(fill="both", expand=True)
        self._refresh_emp_tree()

    def _refresh_emp_tree(self):
        for item in self.tree_emp.get_children():
            self.tree_emp.delete(item)
        emps = db.get_empleados()
        for emp in emps:
            self.tree_emp.insert("", "end", values=(emp['id'], emp['nombre'], emp['tipo_pago'], emp['cedula'] or '-', emp['telefono'] or '-', emp['fecha_inicio'] or '-'))

    def _dialog_add_empleado(self):
        dlg = tk.Toplevel(self)
        dlg.title("Nuevo Empleado")
        dlg.geometry("400x500")
        dlg.configure(bg=CARD_BG)
        # Básico stub
        ttk.Label(dlg, text="Nombre:", style='TLabel').pack(pady=5)
        ent_nombre = ttk.Entry(dlg)
        ent_nombre.pack(pady=5)
        
        ttk.Label(dlg, text="Tipo de Pago:", style='TLabel').pack(pady=5)
        cb_tipo = ttk.Combobox(dlg, values=["tarjeta", "efectivo", "fijo"], state="readonly")
        cb_tipo.set("tarjeta")
        cb_tipo.pack(pady=5)
        
        def save():
            db.add_empleado(ent_nombre.get(), cb_tipo.get(), 0.0)
            self._refresh_emp_tree()
            dlg.destroy()
            
        ttk.Button(dlg, text="Guardar", style='Accent.TButton', command=save).pack(pady=20)

    def show_tarifas(self):
        self._clear_main()
        ttk.Label(self.main_area, text="Configuración de Tarifas", style='Title.TLabel').pack(anchor="w", pady=(0,20))
        tarifas = db.get_tarifas()
        
        f = ttk.Frame(self.main_area, style='Card.TFrame', padding=20)
        f.pack(fill="x", anchor="n")
        
        entries = {}
        for i, (k, l) in enumerate([("tarjeta_diurna", "Tarifa Diurna"), ("tarjeta_nocturna", "Tarifa Nocturna"), ("tarjeta_mixta", "Tarifa Mixta"), ("seguro", "Monto Seguro CCSS")]):
            ttk.Label(f, text=l).grid(row=i, column=0, pady=10, sticky="e", padx=10)
            ent = ttk.Entry(f)
            # Map k to dict keys
            val = tarifas.get(k.replace("tarjeta_", "tarifa_"), 0)
            if k == "seguro": val = tarifas.get("seguro", 0)
            ent.insert(0, str(val))
            ent.grid(row=i, column=1, pady=10, sticky="w")
            entries[k] = ent
            
    def show_planilla(self):
        self._clear_main()
        ttk.Label(self.main_area, text="Generación de Planillas", style='Title.TLabel').pack(anchor="w", pady=(0,20))
        ttk.Button(self.main_area, text="Crear Nuevo Mes", style='Accent.TButton', command=self._crear_nuevo_mes).pack(anchor="w", pady=10)
        
        mes = db.get_mes_activo()
        if mes:
            ttk.Label(self.main_area, text=f"Mes Activo: {MESES_ES.get(mes['mes'], mes['mes'])} {mes['anio']}", font=FONT_SUBTITLE).pack(anchor="w", pady=10)
            ttk.Button(self.main_area, text="+ Agregar Semana", style='Success.TButton', command=self._agregar_semana).pack(anchor="w", pady=5)
            # Lista de semanas logic herre

    def _crear_nuevo_mes(self):
        # API logic to create mes via planilla or raw db
        mes = datetime.now().month
        anio = datetime.now().year
        # Stub logic
        db.crear_mes(anio, mes, f"Planillas {anio}/Planilla_{MESES_ES[mes]}_{anio}.xlsx")
        self.show_planilla()

    def _agregar_semana(self):
        messagebox.showinfo("Info", "Utiliza la WebApp para integrar horarios automáticamente.")

    def show_vacaciones(self):
        self._clear_main()
        ttk.Label(self.main_area, text="Control de Vacaciones", style='Title.TLabel').pack(anchor="w", pady=(0,20))
        ttk.Label(self.main_area, text="Seleccione un empleado en la WebApp para registrar sus vacaciones.").pack(anchor="w")

    def show_aguinaldo(self):
        self._clear_main()
        ttk.Label(self.main_area, text="Cálculo de Aguinaldos", style='Title.TLabel').pack(anchor="w", pady=(0,20))
        ttk.Label(self.main_area, text="Las integraciones con CCSS y Aguinaldo ahora se encuentran completas en la versión WebApp.").pack(anchor="w")
        
    def _lanzar_webapp(self):
        if self.webapp_process is not None:
            messagebox.showinfo("Webapp", "La WebApp ya se está ejecutando en segundo plano.")
            webbrowser.open("http://127.0.0.1:8000")
            return
            
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        webapp_dir = os.path.join(parent_dir, "webapp", "backend")
        
        try:
            self.webapp_process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "main:app", "--port", "8000", "--reload"],
                cwd=webapp_dir
            )
            messagebox.showinfo("Éxito", "WebApp iniciada en puerto 8000.\nAbriendo navegador...")
            webbrowser.open("http://127.0.0.1:8000")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo iniciar Uvicorn:\n{e}")

    def _borrar_proceso_webapp(self):
        if self.webapp_process:
            self.webapp_process.terminate()
            self.webapp_process.wait()
            self.webapp_process = None

    def _on_closing(self):
        self._borrar_proceso_webapp()
        self.destroy()

if __name__ == "__main__":
    app = PlanillaApp()
    app.mainloop()
