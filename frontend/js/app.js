// ========================================================================
// Chronos — App Core
// Inicialización, generación, overlays, employee CRUD, utilidades
// ========================================================================

/* ── Overlays ── */
function openOverlay(id) {
    document.querySelectorAll('.section-overlay').forEach(el => el.classList.add('hidden'));
    const overlay = document.getElementById(id);
    if (overlay) {
        overlay.classList.remove('hidden');
        if (id === 'overlay-history') { loadHistory(); loadFolders(); updateSidebarActive('nav-history'); }
        else if (id === 'overlay-employees') { updateSidebarActive('nav-employees'); }
    }
}
window.openOverlay = openOverlay;

function closeAllOverlays() {
    document.querySelectorAll('.section-overlay').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.history-item').forEach(i => { i.style.display = ''; });
    updateSidebarActive('nav-schedule');
}
window.closeAllOverlays = closeAllOverlays;

function updateSidebarActive(id) {
    document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
    const btn = document.getElementById(id); if (btn) btn.classList.add('active');
}

/* ── Generate Schedule ── */
async function generateSchedule() {
    const status = document.getElementById("statusMessage");
    status.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Generando...';
    config.night_mode = document.getElementById("nightModeConfig").value;
    config.fixed_night_person = document.getElementById('nightPersonSelect').value;
    config.allow_long_shifts = document.getElementById("allowLongShifts").checked;
    config.use_refuerzo = document.getElementById("useRefuerzo")?.checked || false;
    config.refuerzo_type = document.getElementById("refuerzoTypeSelect")?.value || "personalizado";

    // Per-day refuerzo schedule
    const refDays = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
    const schedule = {};
    refDays.forEach(day => {
        const cb = document.getElementById("refDayActive" + day);
        if (cb && cb.checked) {
            const start = document.getElementById("refDayStart" + day)?.value || "07:00";
            const end = document.getElementById("refDayEnd" + day)?.value || "12:00";
            schedule[day] = { start, end };
        }
    });
    config.refuerzo_schedule = Object.keys(schedule).length > 0 ? schedule : null;
    config.allow_collision_quebrado = document.getElementById("allowCollisionQuebrado")?.checked || false;
    config.allow_quebrado_largo = document.getElementById("allowQuebradoLargo")?.checked || false;
    config.collision_peak_priority = document.getElementById("collisionPeakPriority")?.value || "pm";
    config.use_history = document.getElementById("useHistoryContext")?.checked ?? true;
    config.rotation_enabled = document.getElementById("rotationEnabled")?.checked ?? true;
    config.strict_weekly_alternation = document.getElementById("strictWeeklyAlternation")?.checked ?? false;
    const specialDays = getSpecialDaysPayload();
    try {
        const weekStart = document.getElementById("weekStartDate")?.value;
        const weekEnd = document.getElementById("weekEndDate")?.value;
        if (weekStart && weekEnd) {
            status.innerHTML = '<i class="fa-solid fa-sync fa-spin"></i> Sincronizando vacaciones...';
            const syncRes = await fetch('/api/sync_vac_fixed_shifts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ fecha_inicio: weekStart, fecha_fin: weekEnd }) });
            if (syncRes.ok) await loadEmployees();
            status.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Generando...';
        }
        const res = await fetch(`${API_URL}/solve`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ employees, config, target_week_start: weekStart || null, special_days: specialDays }) });
        const result = await res.json();
        if (result.status === "Success" || result.status === "Optimal" || result.status === "Feasible") {
            status.textContent = "Generado!";
            currentGeneratedSchedule = result.schedule;
            currentDailyTasks = result.daily_tasks;
            currentMetadata = result.metadata;
            renderWeekSpecialDays();
            await refreshScheduleValidationRules(specialDays);
            renderSchedule(result.schedule, "#scheduleTable", result.daily_tasks);
            if (isValidationOn) applyValidationUI();
            document.getElementById("btnSaveSchedule").classList.remove("hidden");
            const libresText = result.metadata?.libres_person ? `Libres: ${result.metadata.libres_person}` : "Éxito";
            const solutionsCount = result.metadata?.solutions_found ? ` | Óptimos procesados: ${result.metadata.solutions_found}` : "";
            const historyText = result.metadata?.history_context_label ? ` | ${result.metadata.history_context_label}` : "";
            let metaLine = libresText + solutionsCount + historyText;
            const mr = result.metadata?.min_rest_hours_applied; const mrT = result.metadata?.min_rest_hours_target ?? 12;
            if (mr != null) metaLine += mr < mrT ? ` | Descanso mínimo: ${mr}h (obj. ${mrT}h)` : ` | Descanso mínimo: ${mr}h`;
            document.getElementById("scheduleMeta").textContent = metaLine;
        } else {
            currentMetadata = null;
            if (result.status === "Infeasible") {
                const infeasibleMessage = result.message || "No se encontró una solución factible con las restricciones actuales. Intenta relajar algunos turnos fijos.";
                status.innerHTML = '<span class="error"><i class="fa-solid fa-circle-xmark"></i> Infeasible</span>';
                document.getElementById("scheduleMeta").textContent = infeasibleMessage; alert(infeasibleMessage);
            } else { status.textContent = `Error: ${result.status}`; document.getElementById("scheduleMeta").textContent = result.message || "Error"; }
        }
    } catch (e) { console.error("Generate Error:", e); status.textContent = "Error: " + e.message; }
}
window.generateSchedule = generateSchedule;

/* ── Employee CRUD ── */
function openAddModal() {
    if (typeof openUnifiedEmpModal === "function") { openUnifiedEmpModal(null); return; }
    console.warn("openUnifiedEmpModal no está disponible");
}
window.openAddModal = openAddModal;

function openEditModal(index) {
    const emp = employees[index];
    if (typeof openUnifiedEmpModal === "function") { openUnifiedEmpModal(_horariosEmpToPlanillaShape(emp)); return; }
    console.warn("openUnifiedEmpModal no está disponible");
}
window.openEditModal = openEditModal;

async function saveEmployee() {
    const idxEl = document.getElementById("editingIndex"); const nameEl = document.getElementById("empName");
    if (!idxEl || !nameEl) return;
    const index = parseInt(idxEl.value); const name = nameEl.value; if (!name) return alert("Nombre requerido");
    const genderEl = document.getElementById("empGender"); const gender = genderEl ? genderEl.value : "M";
    const jefeEl = document.getElementById("empJefePista"); const isJefe = jefeEl ? jefeEl.checked : false;
    const empData = { name, gender, can_do_night: gender === "M", is_jefe_pista: isJefe, is_practicante: document.getElementById("empPracticante")?.checked ?? false, forced_libres: document.getElementById("empForcedLibres")?.checked ?? false, forced_quebrado: document.getElementById("empForcedQuebrado")?.checked ?? false, allow_no_rest: document.getElementById("empNoRest")?.checked ?? false, strict_preferences: document.getElementById("empStrictPreferences")?.checked ?? false, activo: document.getElementById("empActiveStatus") ? document.getElementById("empActiveStatus").checked : true, incluir_en_horario: document.getElementById("empIncluirEnHorario") ? document.getElementById("empIncluirEnHorario").checked : true, fixed_shifts: {} };
    const jefeShiftSel = document.getElementById("jefeShiftSelect");
    const selectedJefeShift = jefeShiftSel ? jefeShiftSel.value : "CUSTOM";
    const isNewEmployee = index === -1; const weekdays = ["Lun", "Mar", "Mié", "Jue", "Vie"];
    document.querySelectorAll("#planillaEmpModal .shift-select").forEach((sel) => {
        const day = sel.getAttribute("data-day"); let val = sel.value;
        if (isJefe && weekdays.includes(day) && val === "AUTO" && isNewEmployee && selectedJefeShift !== "CUSTOM") val = selectedJefeShift;
        if (isJefe && day === "Sáb" && val === "AUTO" && isNewEmployee) val = "T1_05-13";
        if (isJefe && day === "Dom" && val === "AUTO" && isNewEmployee) val = "OFF";
        if (val !== "AUTO") empData.fixed_shifts[day] = val;
    });
    if (index === -1) {
        employees.push(empData);
        await fetch(`${API_URL}/employees`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify([empData]) });
    } else {
        const originalName = employees[index].name; employees[index] = empData;
        await fetch(`${API_URL}/employees/${encodeURIComponent(originalName)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(empData) });
    }
    closeModal(); await loadEmployees();
}
window.saveEmployee = saveEmployee;

async function deleteEmployee(index) {
    if (!confirm("Eliminar?")) return;
    employees.splice(index, 1);
    await fetch(`${API_URL}/employees`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(employees) });
    renderEmployees();
}
window.deleteEmployee = deleteEmployee;

/* ── Auto-calc Week End ── */
function autoCalcWeekEnd() {
    const startVal = document.getElementById("weekStartDate")?.value;
    const endInput = document.getElementById("weekEndDate");
    if (!startVal || !endInput) return;
    const start = new Date(startVal + "T12:00:00");
    const end = new Date(start); end.setDate(start.getDate() + 6);
    const y = end.getFullYear(); const m = String(end.getMonth() + 1).padStart(2, "0"); const d = String(end.getDate()).padStart(2, "0");
    endInput.value = `${y}-${m}-${d}`;
    const preview = document.getElementById("weekNamePreview");
    if (preview) {
        const weekNum = getAutofillWeekNumber(start);
        preview.textContent = `Semana ${weekNum} — ${start.toLocaleDateString('es-CR', { day: 'numeric', month: 'short' })} al ${end.toLocaleDateString('es-CR', { day: 'numeric', month: 'short', year: 'numeric' })}`;
        preview.style.display = "block";
    }
}
window.autoCalcWeekEnd = autoCalcWeekEnd;

/* ── Init ── */
document.addEventListener("DOMContentLoaded", () => {
    document.body.classList.add('dark-mode');
    loadData().then(() => {
        renderVacationCheckboxes();
        initCustomShiftsUI();
        loadCustomShiftsFromConfig();
        loadHolidaysFromConfig();
        const startInput = document.getElementById("weekStartDate");
        if (startInput && !startInput.value) {
            const d = new Date(); const diff = (5 - d.getDay() + 7) % 7; d.setDate(d.getDate() + diff);
            const y = d.getFullYear(); const m = String(d.getMonth() + 1).padStart(2, "0"); const dayDate = String(d.getDate()).padStart(2, "0");
            startInput.value = `${y}-${m}-${dayDate}`;
            if (typeof autoCalcWeekEnd === "function") autoCalcWeekEnd();
        }
    });
    const btn = document.getElementById('theme-toggle');
    if (btn) btn.onclick = () => document.body.classList.toggle('dark-mode');
});

/* ── Event Listeners ── */
document.addEventListener('keydown', function(e) {
    if (e.key === "Escape") {
        const modal = document.getElementById("acercaDeModal");
        if (modal && !modal.classList.contains("hidden")) closeAcercaDeModal(e);
    }
});

document.addEventListener('click', function(e) {
    const cell = e.target.closest('.jefe-cell');
    if (!cell) return;
    const valueSpan = cell.querySelector('.jefe-cell-value'); if (!valueSpan) return;
    const isJefe = cell.classList.contains('jefe-cell-active');
    cell.classList.toggle('jefe-cell-active', !isJefe);
    valueSpan.textContent = isJefe ? '—' : 'Jefe';
    updateConfig();
});

document.addEventListener('DOMContentLoaded', () => {
    const th = document.getElementById('th-collaborator');
    if (th) {
        th.addEventListener('click', () => {
            currentSortMode = (currentSortMode === 'time') ? 'alpha' : 'time';
            if (currentGeneratedSchedule) renderSchedule(currentGeneratedSchedule, "#scheduleTable", currentDailyTasks);
        });
    }
});

/* ── Task Label CSS Injection ── */
const styleTask = document.createElement('style');
styleTask.innerHTML = `.shift-task-label { font-size: 0.7rem; font-weight: 700; line-height: 1.25; margin-top: 3px; text-align: center; padding: 2px 4px; border-radius: 4px; display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }.task-banos { color: #b45309; background: rgba(180, 83, 9, 0.1); border: 1px solid rgba(180, 83, 9, 0.2); }.task-tanques { color: #1d4ed8; background: rgba(29, 78, 216, 0.1); border: 1px solid rgba(29, 78, 216, 0.2); }.task-oficina { color: #be185d; background: rgba(190, 24, 93, 0.1); border: 1px solid rgba(190, 24, 93, 0.2); width: 100%; font-size: 0.62rem; }.task-calibracion { color: #6b21a8; background: rgba(107, 33, 168, 0.1); border: 1px solid rgba(107, 33, 168, 0.2); }.task-canos { color: #065f46; background: rgba(6, 95, 70, 0.1); border: 1px solid rgba(6, 95, 70, 0.2); }.task-default { color: var(--text-muted); background: rgba(100,116,139,0.1); border: 1px solid rgba(100,116,139,0.2); }.dark-mode .task-banos { color: #fbbf24; background: rgba(251, 191, 36, 0.15); }.dark-mode .task-tanques { color: #60a5fa; background: rgba(96, 165, 250, 0.15); }.dark-mode .task-oficina { color: #f472b6; background: rgba(244, 114, 182, 0.15); }.dark-mode .task-calibracion { color: #c084fc; background: rgba(192, 132, 252, 0.15); }.dark-mode .task-canos { color: #34d399; background: rgba(52, 211, 153, 0.15); }.task-extra { display: inline; color: #be185d; font-weight: 800; font-size: 0.6rem; }.dark-mode .task-extra { color: #f472b6; }.task-suffix { display: inline; font-size: 0.6rem; opacity: 0.7; font-weight: 600; letter-spacing: 0.2px; }.history-task-editable { cursor: pointer; transition: transform 0.15s ease, filter 0.15s ease; }.history-task-editable:hover { transform: scale(1.05); filter: brightness(1.1); }.task-option-item { padding: 12px; border-radius: 8px; border: 1px solid var(--border); margin-bottom: 8px; cursor: pointer; display: flex; align-items: center; gap: 12px; transition: background 0.2s, border-color 0.2s; }.task-option-item:hover { background: var(--bg-hover); border-color: var(--primary); }.task-option-item.selected { background: rgba(99, 102, 241, 0.1); border-color: var(--primary); }.task-option-icon { width: 32px; height: 32px; border-radius: 6px; display: flex; align-items: center; justify-content: center; font-size: 1rem; }`;
document.head.appendChild(styleTask);

const styleCoverage = document.createElement('style');
styleCoverage.innerHTML = `.coverage-info-panel { margin-top: 16px; padding: 16px; border-radius: 12px; background: rgba(99, 102, 241, 0.05); border: 1px solid rgba(99, 102, 241, 0.15); display: none; }.dark-mode .coverage-info-panel { background: rgba(99, 102, 241, 0.08); border-color: rgba(99, 102, 241, 0.2); }.coverage-header { font-size: 0.95rem; font-weight: 700; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; color: #4f46e5; }.dark-mode .coverage-header { color: #818cf8; }.coverage-badge { font-size: 0.75rem; font-weight: 600; padding: 2px 10px; border-radius: 12px; display: inline-flex; align-items: center; gap: 4px; }.coverage-badge-ok { background: rgba(16, 185, 129, 0.15); color: #059669; }.dark-mode .coverage-badge-ok { background: rgba(16, 185, 129, 0.2); color: #34d399; }.coverage-badge-error { background: rgba(239, 68, 68, 0.15); color: #dc2626; }.dark-mode .coverage-badge-error { background: rgba(239, 68, 68, 0.2); color: #f87171; }.coverage-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; text-align: center; }.coverage-table th { padding: 6px 10px; font-weight: 700; background: rgba(99, 102, 241, 0.08); border-bottom: 2px solid rgba(99, 102, 241, 0.2); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; }.dark-mode .coverage-table th { background: rgba(99, 102, 241, 0.12); }.coverage-table td { padding: 4px 8px; border-bottom: 1px solid rgba(0,0,0,0.06); font-weight: 600; font-size: 0.85rem; }.dark-mode .coverage-table td { border-bottom-color: rgba(255,255,255,0.06); }.coverage-hour { font-weight: 700 !important; color: #6366f1; text-align: left !important; font-size: 0.75rem !important; white-space: nowrap; }.dark-mode .coverage-hour { color: #a5b4fc; }.cov-ok { background: rgba(16, 185, 129, 0.1); color: #059669; }.dark-mode .cov-ok { background: rgba(16, 185, 129, 0.15); color: #34d399; }.cov-deficit { background: #fff1f2; color: #881337; font-weight: 800; border: 1px solid #fda4af; }.dark-mode .cov-deficit { background: #450a0a; color: #fecdd3; border-color: #f43f5e; }`;
document.head.appendChild(styleCoverage);
