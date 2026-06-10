// ========================================================================
// Chronos — Params Panel
// Panel de parámetros del generador, config UI, pill selector, vacaciones
// ========================================================================

/* ── Config UI Toggles ── */
function setNightMode(val, btn) {
    document.getElementById("nightModeConfig").value = val;
    document.querySelectorAll("#nightModeSegmented .seg-btn").forEach(b => b.classList.remove("active"));
    if (btn) btn.classList.add("active");
    const container = document.getElementById("fixedNightContainer");
    if (val === "fixed_person") { container.classList.remove("hidden"); } else { container.classList.add("hidden"); }
    updateConfig();
}
window.setNightMode = setNightMode;

function toggleRefuerzoConfig() {
    const isChecked = document.getElementById("useRefuerzo")?.checked;
    const container = document.getElementById("refuerzoTypeContainer");
    const customContainer = document.getElementById("refuerzoCustomTimeContainer");
    const refuerzoType = document.getElementById("refuerzoTypeSelect")?.value || "personalizado";
    if (container) { if (isChecked) container.classList.remove("hidden"); else container.classList.add("hidden"); }
    if (customContainer) { if (isChecked && refuerzoType === "personalizado") customContainer.classList.remove("hidden"); else customContainer.classList.add("hidden"); }
    updateConfig();
}
window.toggleRefuerzoConfig = toggleRefuerzoConfig;

function toggleRefuerzoDaysConfig() {
    const daysMode = document.getElementById("refuerzoDaysMode")?.value || "auto";
    const manualDaysContainer = document.getElementById("refuerzoManualDaysContainer");
    if (manualDaysContainer) { if (daysMode === "manual") manualDaysContainer.classList.remove("hidden"); else manualDaysContainer.classList.add("hidden"); }
}
window.toggleRefuerzoDaysConfig = toggleRefuerzoDaysConfig;

function toggleJefeConfig() {
    const enabled = document.getElementById("jefeEnabled")?.checked;
    const body = document.getElementById("jefeConfigBody");
    if (body) { if (enabled) body.classList.remove("hidden"); else body.classList.add("hidden"); }
    updateConfig();
}
window.toggleJefeConfig = toggleJefeConfig;

function toggleCollisionConfig() {
    const isChecked = document.getElementById("allowCollisionQuebrado")?.checked;
    const container = document.getElementById("collisionPriorityContainer");
    if (container) { if (isChecked) container.classList.add("hidden"); else container.classList.remove("hidden"); }
    updateConfig();
}
window.toggleCollisionConfig = toggleCollisionConfig;

function toggleAlternatingMode() {
    const isAuto = document.getElementById("alternatingAutoMode")?.checked;
    const container = document.getElementById("alternatingPairsContainer");
    if (!container) return;
    if (isAuto) { container.classList.add("hidden"); config.alternating_pairs = null; }
    else { container.classList.remove("hidden"); if (!Array.isArray(config.alternating_pairs)) config.alternating_pairs = []; renderAlternatingPairs(); }
    updateConfig();
}
window.toggleAlternatingMode = toggleAlternatingMode;

function renderAlternatingPairs() {
    const list = document.getElementById("alternatingPairsList"); if (!list) return;
    const pairs = Array.isArray(config.alternating_pairs) ? config.alternating_pairs : [];
    if (pairs.length === 0) { list.innerHTML = '<p class="helper-text-sm" style="text-align:center; padding:0.4rem 0; color:var(--text-muted);">Sin pares configurados</p>'; return; }
    list.innerHTML = pairs.map((pair, idx) => {
        const [e1, e2] = pair.employees || ["", ""];
        const opts1 = employees.map(e => `<option value="${e.name}" ${e.name === e1 ? 'selected' : ''}>${e.name}</option>`).join('');
        const opts2 = employees.map(e => `<option value="${e.name}" ${e.name === e2 ? 'selected' : ''}>${e.name}</option>`).join('');
        return `<div style="display:flex; gap:0.4rem; align-items:center; margin-bottom:0.5rem;"><select onchange="updateAlternatingPair(${idx}, 0, this.value)" style="flex:1; padding:0.35rem 0.5rem; border-radius:6px; border:1px solid var(--border-color); background:var(--surface-2); color:var(--text-main); font-size:0.8rem;"><option value="">Empleado 1</option>${opts1}</select><i class="fa-solid fa-right-left" style="color:var(--text-muted); font-size:0.72rem; flex-shrink:0;"></i><select onchange="updateAlternatingPair(${idx}, 1, this.value)" style="flex:1; padding:0.35rem 0.5rem; border-radius:6px; border:1px solid var(--border-color); background:var(--surface-2); color:var(--text-main); font-size:0.8rem;"><option value="">Empleado 2</option>${opts2}</select><button onclick="removeAlternatingPair(${idx})" style="background:rgba(239,68,68,0.1); color:#ef4444; border:none; border-radius:6px; width:26px; height:26px; cursor:pointer; flex-shrink:0; display:flex; align-items:center; justify-content:center;" title="Quitar par"><i class="fa-solid fa-xmark" style="font-size:0.68rem;"></i></button></div>`;
    }).join('');
}
window.renderAlternatingPairs = renderAlternatingPairs;

function addAlternatingPair() {
    if (!Array.isArray(config.alternating_pairs)) config.alternating_pairs = [];
    config.alternating_pairs.push({ employees: ["", ""] }); renderAlternatingPairs();
}
window.addAlternatingPair = addAlternatingPair;

function removeAlternatingPair(idx) {
    if (!Array.isArray(config.alternating_pairs)) return;
    config.alternating_pairs.splice(idx, 1); renderAlternatingPairs(); updateConfig();
}
window.removeAlternatingPair = removeAlternatingPair;

function updateAlternatingPair(idx, pos, value) {
    if (!Array.isArray(config.alternating_pairs)) return;
    if (!config.alternating_pairs[idx]) return;
    if (!config.alternating_pairs[idx].employees) config.alternating_pairs[idx].employees = ["", ""];
    config.alternating_pairs[idx].employees[pos] = value; updateConfig();
}
window.updateAlternatingPair = updateAlternatingPair;

/* ── Update Config ── */
async function updateConfig() {
    const mode = document.getElementById("nightModeConfig").value;
    const person = document.getElementById("nightPersonSelect").value;
    const allowLong = document.getElementById("allowLongShifts").checked;
    const useRefuerzo = document.getElementById("useRefuerzo")?.checked || false;
    const refuerzoType = document.getElementById("refuerzoTypeSelect")?.value || "personalizado";
    const refuerzoStart = document.getElementById("refuerzoStartTime")?.value || "07:00";
    const refuerzoEnd = document.getElementById("refuerzoEndTime")?.value || "12:00";
    config.night_mode = mode; config.fixed_night_person = person; config.allow_long_shifts = allowLong;
    config.use_refuerzo = useRefuerzo; config.refuerzo_type = refuerzoType;

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
    config.refuerzo_partial_mode = document.getElementById("refuerzoPartialMode")?.checked || false;
    config.allow_collision_quebrado = document.getElementById("allowCollisionQuebrado")?.checked || false;
    config.allow_quebrado_largo = document.getElementById("allowQuebradoLargo")?.checked || false;
    config.collision_peak_priority = document.getElementById("collisionPeakPriority")?.value || "pm";
    config.use_history = document.getElementById("useHistoryContext")?.checked ?? true;
    config.rotation_enabled = document.getElementById("rotationEnabled")?.checked ?? true;
    config.cleaning_tasks = {};
    const ctDays = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
    const ctTasks = ["am_banos", "pm_banos", "am_tanques", "pm_tanques", "oficina", "calibracion", "canos", "canos_glp"];
    ctDays.forEach(d => { config.cleaning_tasks[d] = {}; ctTasks.forEach(t => { const cb = document.getElementById(`clean_${t}_${d}`); if (cb) config.cleaning_tasks[d][t] = cb.checked; }); });
    config.jefe_config = { enabled: document.getElementById("jefeEnabled").checked, exclude_regular: document.getElementById("jefeExcludeRegular").checked, assignment: {} };
    document.querySelectorAll('.jefe-cell').forEach(cell => {
        const task = cell.dataset.task; const day = cell.dataset.day; if (!task || !day) return;
        if (!config.jefe_config.assignment[task]) config.jefe_config.assignment[task] = {};
        config.jefe_config.assignment[task][day] = cell.classList.contains('jefe-cell-active');
    });
    const jefeBaseSel = document.getElementById("jefeBaseShiftSelect");
    if (jefeBaseSel && jefeBaseSel.value) config.jefe_base_shift = jefeBaseSel.value;
    const customContainer = document.getElementById("refuerzoCustomTimeContainer");
    if (customContainer) { if (useRefuerzo && refuerzoType === "personalizado") customContainer.classList.remove("hidden"); else customContainer.classList.add("hidden"); }
    await fetch(`${API_URL}/config`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config) });
    try {
        await refreshBaseValidationRules();
        if (currentGeneratedSchedule && isValidationOn) {
            await refreshScheduleValidationRules(currentMetadata?.special_days || getSpecialDaysPayload());
            applyValidationUI();
        }
    } catch (e) { console.error("Error refreshing validation rules:", e); }
}
window.updateConfig = updateConfig;

/* ── Pill Groups & Day Cards ── */
let activePillDay = null;

function buildPillGroups(day = null) {
    const rules = baseValidationRules || validationRules;
    const groups = { special: [{ code: "AUTO", label: "Auto", icon: "fa-robot", color: "#6366f1" }, { code: "VAC", label: "VAC", icon: "fa-plane", color: "#10b981" }, { code: "PERM", label: "PERM", icon: "fa-file-signature", color: "#f59e0b" }, { code: "OFF", label: "LIBRE", icon: "fa-mug-hot", color: "#94a3b8" }, { code: "N_22-05", label: "Noche", icon: "fa-moon", color: "#818cf8" }], morning: [], afternoon: [], extended: [], jefe: [] };
    if (!rules || !rules.shift_sets) return groups;
    const SKIP = new Set(["OFF", "VAC", "PERM", "N_22-05"]);
    const allowedForDay = Array.isArray(rules?.day_allowed_shifts?.[day]) ? new Set(rules.day_allowed_shifts[day]) : null;
    const startOf = (code) => { const hrs = rules.shift_sets[code]; if (!hrs || hrs.length === 0) return 99; return Math.min(...hrs); };
    const allCodes = Object.keys(rules.shift_sets).sort((a, b) => startOf(a) - startOf(b) || a.localeCompare(b));
    for (const code of allCodes) {
        if (SKIP.has(code)) continue;
        if (allowedForDay && !allowedForDay.has(code)) continue;
        const hrs = rules.shift_sets[code] || []; const start = Math.min(...hrs); const end = Math.max(...hrs);
        const parts = code.split("_"); const timeLabel = parts.length >= 2 ? parts.slice(1).join("+") : code;
        const entry = { code, label: timeLabel };
        if (code.startsWith("J_")) { entry.icon = "fa-star"; groups.jefe.push(entry); }
        else if (code.startsWith("Q") || code.startsWith("X") || code.startsWith("E") || code.startsWith("R") || code.startsWith("D")) { groups.extended.push(entry); }
        else if (start >= 12) { groups.afternoon.push(entry); }
        else { groups.morning.push(entry); }
    }
    for (const key of ["morning", "afternoon", "extended"]) groups[key].sort((a, b) => startOf(a.code) - startOf(b.code));
    return groups;
}
window.buildPillGroupsForDay = buildPillGroups;

function fillJefeBaseShiftSelectFromRules() {
    const sel = document.getElementById("jefeBaseShiftSelect"); if (!sel) return;
    const cur = config && config.jefe_base_shift ? config.jefe_base_shift : "J_06-16";
    const codes = new Set(["J_06-16", "T1_05-13", "T2_06-14", "T3_07-15", "T4_08-16", "PM"]);
    if (typeof buildPillGroups === "function") {
        try { const g = buildPillGroups("Lun"); (g.jefe || []).forEach((x) => codes.add(x.code)); (g.morning || []).forEach((x) => codes.add(x.code)); } catch (e) { /* validation rules may not be ready */ }
    }
    const sorted = [...codes].sort((a, b) => a.localeCompare(b, "es"));
    const lab = typeof formatGeneratorShiftLabel === "function" ? formatGeneratorShiftLabel : (x) => x;
    sel.innerHTML = sorted.map((c) => `<option value="${c.replace(/"/g, "&quot;")}">${String(lab(c)).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;")}</option>`).join("");
    const pick = sorted.includes(cur) ? cur : sorted[0] || "J_06-16";
    sel.value = pick; if (config) config.jefe_base_shift = pick;
}
window.fillJefeBaseShiftSelectFromRules = fillJefeBaseShiftSelectFromRules;

function getDayCardInfo(code) {
    if (!code || code === "AUTO") return { label: "Auto", icon: "fa-robot", cls: "dc-auto" };
    if (code === "OFF") return { label: "LIBRE", icon: "fa-mug-hot", cls: "dc-off" };
    if (code === "VAC") return { label: "VAC", icon: "fa-plane", cls: "dc-vac" };
    if (code === "PERM") return { label: "PERM", icon: "fa-file-signature", cls: "dc-perm" };
    if (code.startsWith("N_")) return { label: "Noche", icon: "fa-moon", cls: "dc-night" };
    if (code.startsWith("J_")) return { label: code.replace("J_", ""), icon: "fa-star", cls: "dc-jefe" };
    if (code.startsWith("Q") || code.startsWith("X") || code.startsWith("E") || code.startsWith("R") || code.startsWith("D")) {
        const parts = code.split("_"); const timeLabel = parts.length >= 2 ? parts.slice(1).join("+") : code;
        return { label: timeLabel, icon: "fa-arrows-left-right", cls: "dc-extended" };
    }
    const m = code.match(/(\d{2})-(\d{2})/);
    if (m) { const start = parseInt(m[1]); if (start < 12) return { label: `${m[1]}-${m[2]}`, icon: "fa-sun", cls: "dc-morning" }; return { label: `${m[1]}-${m[2]}`, icon: "fa-cloud-sun", cls: "dc-afternoon" }; }
    return { label: code, icon: "fa-clock", cls: "dc-auto" };
}

function _hour24ToAmPm(h) {
    h = ((Math.round(Number(h)) % 24) + 24) % 24;
    const am = h < 12; const h12 = h % 12 === 0 ? 12 : h % 12;
    return `${h12}${am ? "am" : "pm"}`;
}

function formatGeneratorShiftLabel(code) {
    if (!code || code === "AUTO") return "Auto";
    const c = String(code).trim();
    const std = STANDARD_SHIFTS.find((s) => s.name === c);
    if (std && std.hours) return std.hours.replace(/-/g, " – ");
    if (c === "PERM") return "Permiso";
    const rules = typeof baseValidationRules !== "undefined" ? baseValidationRules : validationRules;
    if (rules && rules.shift_sets && rules.shift_sets[c]) {
        const hrs = rules.shift_sets[c];
        if (Array.isArray(hrs) && hrs.length) { const lo = Math.min(...hrs); const hi = Math.max(...hrs); return `${_hour24ToAmPm(lo)} – ${_hour24ToAmPm(hi + 1)}`; }
    }
    const jm = c.match(/^J_(\d{1,2})-(\d{1,2})$/);
    if (jm) return `${_hour24ToAmPm(parseInt(jm[1], 10))} – ${_hour24ToAmPm(parseInt(jm[2], 10))}`;
    if (c.startsWith("N_")) { const stdN = STANDARD_SHIFTS.find((s) => s.name === "N_22-05"); if (stdN) return stdN.hours.replace(/-/g, " – "); }
    const m = c.match(/(\d{2})-(\d{2})/);
    if (m) return `${_hour24ToAmPm(parseInt(m[1], 10))} – ${_hour24ToAmPm(parseInt(m[2], 10))}`;
    const info = getDayCardInfo(c); return info && info.label ? info.label : c;
}
window.formatGeneratorShiftLabel = formatGeneratorShiftLabel;

function _isPlantillaPillMode() { return window.__pillEditorMode === "plantilla"; }

function buildDayCards() {
    const isPpt = _isPlantillaPillMode();
    const gridId = isPpt ? "pptDayCardsGrid" : "dayCardsGrid";
    const grid = document.getElementById(gridId);
    const root = isPpt ? document.getElementById("prefPlantillaModal") : document.getElementById("planillaEmpModal");
    if (!grid || !root) return; grid.innerHTML = "";
    const selQ = isPpt ? ".ppt-shift-select" : ".shift-select";
    DAYS.forEach(d => {
        const sel = root.querySelector(`${selQ}[data-day="${d}"]`); const code = sel ? sel.value : "AUTO";
        const info = getDayCardInfo(code);
        const card = document.createElement("div"); card.className = `day-card ${info.cls}`; card.setAttribute("data-day", d);
        card.onclick = () => openPillPanel(d, card);
        card.innerHTML = `<span class="dc-day-label">${d}</span><i class="fa-solid ${info.icon} dc-icon"></i><span class="dc-shift-label">${info.label}</span>`;
        grid.appendChild(card);
    });
}
window.buildDayCards = buildDayCards;

function openPillPanel(day, cardEl) {
    activePillDay = day;
    const isPpt = _isPlantillaPillMode();
    const panel = document.getElementById(isPpt ? "pptPillSelectorPanel" : "pillSelectorPanel");
    const dayEl = document.getElementById(isPpt ? "pptPanelDay" : "pillPanelDay");
    if (dayEl) dayEl.textContent = day;
    const root = isPpt ? document.getElementById("prefPlantillaModal") : document.getElementById("planillaEmpModal");
    if (root) { root.querySelectorAll(".day-card").forEach(c => c.classList.remove("dc-active")); }
    if (cardEl) cardEl.classList.add("dc-active");
    const selQ = isPpt ? ".ppt-shift-select" : ".shift-select";
    const sel = root ? root.querySelector(`${selQ}[data-day="${day}"]`) : null;
    const current = sel ? sel.value : "AUTO";
    const PILL_GROUPS = buildPillGroups(day);
    fillPillGroup(isPpt ? "pptPillGroupSpecial" : "pillGroupSpecial", PILL_GROUPS.special, current);
    fillPillGroup(isPpt ? "pptPillGroupMorning" : "pillGroupMorning", PILL_GROUPS.morning, current);
    fillPillGroup(isPpt ? "pptPillGroupAfternoon" : "pillGroupAfternoon", PILL_GROUPS.afternoon, current);
    fillPillGroup(isPpt ? "pptPillGroupExtended" : "pillGroupExtended", PILL_GROUPS.extended, current);
    const isJefe = !isPpt && document.getElementById("empJefePista")?.checked;
    const jefeWrap = document.getElementById(isPpt ? "pptPillGroupJefeWrap" : "pillGroupJefeWrap");
    if (jefeWrap) { if (isJefe) { jefeWrap.style.display = "flex"; fillPillGroup(isPpt ? "pptPillGroupJefe" : "pillGroupJefe", PILL_GROUPS.jefe, current); } else { jefeWrap.style.display = "none"; } }
    if (panel) { panel.classList.remove("hidden"); panel.style.animation = "slideDown 0.25s ease-out"; }
}
window.openPillPanel = openPillPanel;

function fillPillGroup(containerId, options, currentCode) {
    const container = document.getElementById(containerId); container.innerHTML = "";
    options.forEach(opt => {
        const pill = document.createElement("button"); pill.className = `pill-opt ${opt.code === currentCode ? "pill-selected" : ""}`;
        pill.onclick = () => selectPill(opt.code, opt.label);
        let iconHtml = ""; if (opt.icon) iconHtml = `<i class="fa-solid ${opt.icon}"></i> `;
        pill.innerHTML = `${iconHtml}${opt.label}`; container.appendChild(pill);
    });
}

function selectPill(code, label) {
    if (!activePillDay) return;
    const isPpt = _isPlantillaPillMode();
    const root = isPpt ? document.getElementById("prefPlantillaModal") : document.getElementById("planillaEmpModal");
    const selQ = isPpt ? ".ppt-shift-select" : ".shift-select";
    const sel = root ? root.querySelector(`${selQ}[data-day="${activePillDay}"]`) : null;
    if (sel) sel.value = code;
    if (!isPpt) syncVacationCheckboxesFromDropdowns();
    buildDayCards(); closePillPanel();
}
window.selectPill = selectPill;

function closePillPanel() {
    const isPpt = _isPlantillaPillMode();
    const panel = document.getElementById(isPpt ? "pptPillSelectorPanel" : "pillSelectorPanel");
    if (panel) panel.classList.add("hidden"); activePillDay = null;
    const root = isPpt ? document.getElementById("prefPlantillaModal") : document.getElementById("planillaEmpModal");
    if (root) root.querySelectorAll(".day-card").forEach(c => c.classList.remove("dc-active"));
}
window.closePillPanel = closePillPanel;

function syncDayCardsFromSelects() { buildDayCards(); }

/* ── Jefe Helpers ── */
function getJefeBaseSelection(fixed = {}, isJefe = false) {
    if (!isJefe) return "J_06-16";
    const weekdays = ["Lun", "Mar", "Mié", "Jue", "Vie"];
    const weekdayValues = weekdays.map(day => fixed?.[day]).filter(value => typeof value === "string" && value.length > 0);
    if (weekdayValues.length === 0) return "J_06-16";
    const uniqueValues = [...new Set(weekdayValues)];
    if (uniqueValues.length === 1 && uniqueValues[0].startsWith("J_")) return uniqueValues[0];
    return "CUSTOM";
}

function toggleJefeShiftSelect() {
    const isJefe = document.getElementById("empJefePista").checked;
    const configDiv = document.getElementById("jefeShiftConfig");
    if (isJefe) { configDiv.classList.add("expanded"); configDiv.style.display = "block"; }
    else { configDiv.classList.remove("expanded"); configDiv.style.display = "none"; }
}
window.toggleJefeShiftSelect = toggleJefeShiftSelect;

function animateSelect(el) { el.classList.remove("pop-anim"); void el.offsetWidth; el.classList.add("pop-anim"); }

function _horariosEmpToPlanillaShape(emp) {
    if (!emp) return null;
    return { id: emp.id, nombre: emp.name, genero: emp.gender || "M", cedula: emp.cedula || "", telefono: emp.telefono || "", correo: emp.correo || "", tipo_pago: emp.tipo_pago || "tarjeta", fecha_inicio: emp.fecha_inicio || "", salario_fijo: emp.salario_fijo, aplica_seguro: emp.aplica_seguro !== undefined ? emp.aplica_seguro : 1, puede_nocturno: emp.can_do_night ? 1 : 0, forced_libres: emp.forced_libres ? 1 : 0, forced_quebrado: emp.forced_quebrado ? 1 : 0, allow_no_rest: emp.allow_no_rest ? 1 : 0, es_jefe_pista: sqlIntFlagOn(emp.is_jefe_pista) ? 1 : 0, es_practicante: emp.is_practicante ? 1 : 0, strict_preferences: emp.strict_preferences ? 1 : 0, activo: emp.activo !== false ? 1 : 0, turnos_fijos: JSON.stringify(emp.fixed_shifts || {}) };
}

/* ── Vacation UI ── */
function renderVacationCheckboxes() {
    const container = document.getElementById("vacationCheckboxes"); if (!container) return; container.innerHTML = "";
    DAYS.forEach(d => {
        const wrapper = document.createElement("div"); wrapper.className = "vac-day-box";
        const cb = document.createElement("input"); cb.type = "checkbox"; cb.id = `vac-check-${d}`; cb.dataset.day = d;
        cb.onchange = (e) => toggleVacation(d, e.target.checked);
        const label = document.createElement("label"); label.className = "vac-day-label"; label.setAttribute("for", cb.id);
        label.innerHTML = `<span>${d}</span><i class="fa-solid fa-plane"></i>`;
        wrapper.appendChild(cb); wrapper.appendChild(label); container.appendChild(wrapper);
    });
}
window.renderVacationCheckboxes = renderVacationCheckboxes;

function resetVacationCheckboxes() { document.querySelectorAll("#vacationCheckboxes input[type='checkbox']").forEach(b => b.checked = false); }

function syncVacationCheckboxesFromDropdowns() {
    if (window.__pillEditorMode === "plantilla") return;
    document.querySelectorAll("#planillaEmpModal .shift-select").forEach(sel => {
        const d = sel.getAttribute("data-day"); const isVac = sel.value === "VAC";
        const cb = document.querySelector(`#vacationCheckboxes input[data-day='${d}']`);
        if (cb) cb.checked = isVac;
    });
}

function toggleVacation(day, isChecked) {
    const sel = document.querySelector(`#planillaEmpModal .shift-select[data-day='${day}']`);
    if (sel) { if (isChecked) sel.value = "VAC"; else sel.value = "AUTO"; }
}
window.toggleVacation = toggleVacation;

/* ── Populate Shift Selects ── */
function populateShiftSelects() {
    const rules = baseValidationRules || validationRules;
    if (!rules || !rules.shift_options) return;
    document.querySelectorAll(".shift-select, .ppt-shift-select").forEach(sel => {
        const current = sel.value;
        sel.innerHTML = "";
        rules.shift_options.forEach(o => {
            const opt = document.createElement("option"); opt.value = o.code; opt.textContent = o.label;
            if (o.code === current) opt.selected = true;
            sel.appendChild(opt);
        });
    });
}
window.populateShiftSelects = populateShiftSelects;

/* ── Tab Switching ── */
function switchTab(id) {
    document.querySelectorAll(".m-tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".m-tab-content").forEach(c => c.classList.remove("active"));
    const pane = document.getElementById(id); if (pane) pane.classList.add("active");
    if (id === "tab-schedule") window.__pillEditorMode = "employee";
}
window.switchTab = switchTab;

function closeModal() { document.getElementById("employeeModal").classList.add("hidden"); }
window.closeModal = closeModal;
