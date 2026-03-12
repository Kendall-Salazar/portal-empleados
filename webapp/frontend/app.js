const API_URL = "/api";

// STATE
let employees = [];
let config = {};
let currentGeneratedSchedule = null;
let currentDailyTasks = null;
let currentMetadata = null;
let validationRules = null;

let SHIFT_OPTIONS = [];
let SHIFT_HOURS = {};

// Hourly set mapping mapped dynamically via API now
// Removing hardcoded SHIFT_HOURS_SET

const DAYS = ["Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue"];

let isValidationOn = false;

document.addEventListener("DOMContentLoaded", () => {
    // Default to Dark Mode
    document.body.classList.add('dark-mode');

    loadData().then(() => {
        renderVacationCheckboxes(); // Init new UI logic after data loads
    });

    // Theme toggle
    const btn = document.getElementById('theme-toggle');
    if (btn) btn.onclick = () => document.body.classList.toggle('dark-mode');
});

// OVERLAY NAVIGATION
function openOverlay(id) {
    // Close others
    document.querySelectorAll('.section-overlay').forEach(el => el.classList.add('hidden'));

    const overlay = document.getElementById(id);
    if (overlay) {
        overlay.classList.remove('hidden');
        if (id === 'overlay-history') {
            loadHistory();
            updateSidebarActive('nav-history');
        } else if (id === 'overlay-employees') {
            updateSidebarActive('nav-employees');
        }
    }
}

function closeAllOverlays() {
    document.querySelectorAll('.section-overlay').forEach(el => el.classList.add('hidden'));
    updateSidebarActive('nav-schedule');
}

function updateSidebarActive(id) {
    document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
    const btn = document.getElementById(id);
    if (btn) btn.classList.add('active');
}

// DATA LOADING
async function loadData() {
    try {
        const [empRes, cfgRes, rulesRes] = await Promise.all([
            fetch(`${API_URL}/employees?include_inactive=true`),
            fetch(`${API_URL}/config`),
            fetch(`${API_URL}/validation_rules`)
        ]);
        employees = await empRes.json();
        config = await cfgRes.json();
        validationRules = await rulesRes.json();

        SHIFT_OPTIONS = validationRules.shift_options;
        SHIFT_HOURS = validationRules.shift_hours;

        renderEmployees();
        renderConfig();
        populateShiftSelects();
    } catch (e) { console.error(e); }
}

async function loadEmployees() {
    try {
        const empRes = await fetch(`${API_URL}/employees?include_inactive=true`);
        employees = await empRes.json();
        renderEmployees();
    } catch (e) { console.error("Error reloading employees:", e); }
}

function renderEmployees() {
    const grid = document.getElementById("employeeGrid");
    document.getElementById("employeeCount").textContent = `${employees.length} Empleados`;
    grid.innerHTML = "";

    // Global UI Handlers
    window.setGender = function (val, btn) {
        document.getElementById("empGender").value = val;
        document.querySelectorAll(".gender-pill").forEach(p => p.classList.remove("active"));
        btn.classList.add("active");
    };

    // Select for Night config -> now Pills
    const select = document.getElementById("nightPersonSelect");
    const container = document.getElementById("nightPersonPills");
    const currentVal = select.value || config.fixed_night_person;
    container.innerHTML = "";

    employees.forEach((emp, index) => {
        const card = document.createElement("div");
        card.className = "emp-card";

        const fixedCount = Object.keys(emp.fixed_shifts || {}).length;

        const isInactive = emp.activo === false;
        
        card.innerHTML = `
            <div class="emp-info">
                <h4>${emp.name} ${isInactive ? '<span style="color:#ef4444; font-size: 0.8em;">(Inactivo)</span>' : ''}</h4>
                <div class="tags">
                    ${isInactive ? '<span class="tag inactive" style="background:#fee2e2;color:#ef4444;" title="Usuario Inactivo"><i class="fa-solid fa-ban"></i> Inactivo</span>' : ''}
                    ${emp.is_jefe_pista ? '<span class="tag success" title="Jefe de Pista"><i class="fa-solid fa-star"></i> Jefe</span>' : ''}
                    ${emp.can_do_night ? '<span class="tag night" title="Turno Noche"><i class="fa-solid fa-moon"></i> Noche</span>' : ''}
                    ${emp.forced_libres ? '<span class="tag forced" title="Forzar Libres"><i class="fa-solid fa-thumbtack"></i> Libres</span>' : ''}
                    ${emp.forced_quebrado ? '<span class="tag" style="background:#ede9fe;color:#7c3aed;" title="Forzar Quebrado"><i class="fa-solid fa-bolt"></i> Q (6d)</span>' : ''}
                    ${emp.allow_no_rest ? '<span class="tag" style="background:#fef3c7;color:#f59e0b;" title="Sin Descanso"><i class="fa-solid fa-fire"></i> 7d</span>' : ''}
                    ${emp.strict_preferences ? '<span class="tag" style="background:#fef2f2;color:#ef4444;"><i class="fa-solid fa-lock"></i> Estricto</span>' : ''}
                    ${fixedCount > 0 ? `<span class="tag fixed"><i class="fa-solid fa-lock-open"></i> ${fixedCount}</span>` : ''}
                </div>
            </div>
            <div class="emp-actions">
                <button class="btn-icon" onclick="openEditModal(${index})"><i class="fa-solid fa-pen"></i></button>
                <button class="btn-icon delete" onclick="deleteEmployee(${index})"><i class="fa-solid fa-trash"></i></button>
            </div>
        `;
        // Apply grayscale to inactive cards
        if (isInactive) {
            card.style.filter = "grayscale(100%)";
            card.style.opacity = "0.7";
        }
        grid.appendChild(card);

        if (emp.can_do_night && !isInactive) {
            const npCard = document.createElement("div");
            npCard.className = `night-person-card ${emp.name === currentVal ? 'selected' : ''}`;
            const initials = emp.name.split(' ').map(w => w[0]).join('').substring(0, 2);
            npCard.innerHTML = `
                <div class="night-person-avatar">${initials}</div>
                <span class="night-person-name">${emp.name}</span>
                <div class="night-person-check"><i class="fa-solid fa-check"></i></div>
            `;
            npCard.onclick = () => {
                document.getElementById("nightPersonSelect").value = emp.name;
                document.querySelectorAll("#nightPersonPills .night-person-card").forEach(c => c.classList.remove("selected"));
                npCard.classList.add("selected");
                updateConfig();
            };
            container.appendChild(npCard);
        }
    });

    document.getElementById("nightPersonSelect").value = currentVal || config.fixed_night_person || "";
}

function renderConfig() {
    const mode = config.night_mode || "rotation";
    document.getElementById("nightModeConfig").value = mode;

    document.querySelectorAll("#nightModeSegmented .seg-btn").forEach(btn => {
        if ((mode === "rotation" && btn.textContent.includes("Rotación")) ||
            (mode === "fixed_person" && btn.textContent.includes("Fijo"))) {
            btn.classList.add("active");
        } else {
            btn.classList.remove("active");
        }
    });

    const container = document.getElementById("fixedNightContainer");
    if (mode === "fixed_person") container.classList.remove("hidden");
    else container.classList.add("hidden");

    const person = config.fixed_night_person;
    document.getElementById("nightPersonSelect").value = person || "";
    document.querySelectorAll("#nightPersonPills .night-person-card").forEach(c => {
        const name = c.querySelector('.night-person-name');
        if (name && name.textContent.trim() === person) c.classList.add("selected");
        else c.classList.remove("selected");
    });

    // Extended Shifts Checkbox
    const cb = document.getElementById("allowLongShifts");
    if (cb) cb.checked = config.allow_long_shifts || false;

    // Strict Preferences Checkbox
    const strictCb = document.getElementById("strictPreferencesGlobal");
    if (strictCb) strictCb.checked = config.strict_preferences || false;

    // Refuerzo Config
    const refuerzoCb = document.getElementById("useRefuerzo");
    if (refuerzoCb) refuerzoCb.checked = config.use_refuerzo || false;

    const refuerzoTypeSel = document.getElementById("refuerzoTypeSelect");
    if (refuerzoTypeSel) refuerzoTypeSel.value = config.refuerzo_type || "diurno";

    toggleRefuerzoConfig();

    // Collision Q-shift Config
    const collisionCb = document.getElementById("allowCollisionQuebrado");
    if (collisionCb) collisionCb.checked = config.allow_collision_quebrado || false;

    const collisionPrioritySel = document.getElementById("collisionPeakPriority");
    if (collisionPrioritySel) collisionPrioritySel.value = config.collision_peak_priority || "pm";

    toggleCollisionConfig();
}

function setNightMode(val, btn) {
    document.getElementById("nightModeConfig").value = val;

    // Update segmented button UI
    document.querySelectorAll("#nightModeSegmented .seg-btn").forEach(b => b.classList.remove("active"));
    if (btn) btn.classList.add("active");

    // Show/hide fixed person container
    const container = document.getElementById("fixedNightContainer");
    if (val === "fixed_person") {
        container.classList.remove("hidden");
    } else {
        container.classList.add("hidden");
    }

    updateConfig();
}

function toggleRefuerzoConfig() {
    const isChecked = document.getElementById("useRefuerzo")?.checked;
    const container = document.getElementById("refuerzoTypeContainer");
    if (container) {
        if (isChecked) container.classList.remove("hidden");
        else container.classList.add("hidden");
    }
    updateConfig();
}

function toggleCollisionConfig() {
    const isChecked = document.getElementById("allowCollisionQuebrado")?.checked;
    const container = document.getElementById("collisionPriorityContainer");
    if (container) {
        // Show priority selector only when Q is DISABLED
        if (isChecked) container.classList.add("hidden");
        else container.classList.remove("hidden");
    }
    updateConfig();
}

async function updateConfig() {
    const mode = document.getElementById("nightModeConfig").value;
    const person = document.getElementById("nightPersonSelect").value;
    const allowLong = document.getElementById("allowLongShifts").checked;
    const useRefuerzo = document.getElementById("useRefuerzo")?.checked || false;
    const refuerzoType = document.getElementById("refuerzoTypeSelect")?.value || "diurno";

    config.night_mode = mode;
    config.fixed_night_person = person;
    config.allow_long_shifts = allowLong;
    config.use_refuerzo = useRefuerzo;
    config.refuerzo_type = refuerzoType;
    config.allow_collision_quebrado = document.getElementById("allowCollisionQuebrado")?.checked || false;
    config.collision_peak_priority = document.getElementById("collisionPeakPriority")?.value || "pm";

    // renderConfig();  <-- Don't call renderConfig here or it loops with toggleRefuerzoConfig
    await fetch(`${API_URL}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
    });
}

// MODALS
function openAddModal() {
    document.getElementById("modalTitle").textContent = "Nuevo Empleado";
    document.getElementById("editingIndex").value = "-1";
    document.getElementById("empName").value = "";
    document.getElementById("empGender").value = "M"; // default value

    // Default Gender UI
    document.querySelectorAll(".gender-pill").forEach(p => {
        if (p.textContent.includes("Masculino")) p.classList.add("active");
        else p.classList.remove("active");
    });

    document.getElementById("empForcedLibres").checked = false;
    document.getElementById("empForcedQuebrado").checked = false;
    document.getElementById("empNoRest").checked = false;
    document.getElementById("empJefePista").checked = false;
    document.getElementById("empStrictPreferences").checked = false;
    
    // Activo by default
    const empActiveStatus = document.getElementById("empActiveStatus");
    if(empActiveStatus) empActiveStatus.checked = true;

    // Reset fixed shifts
    document.querySelectorAll(".shift-select").forEach(s => s.value = "AUTO");
    resetVacationCheckboxes();

    // Reset Jefe config
    document.getElementById("jefeShiftSelect").value = "J_06-16";
    toggleJefeShiftSelect();

    switchTab("tab-general");
    buildDayCards();
    document.getElementById("planillaEmpModal").classList.remove("hidden");
}

function openEditModal(index) {
    const emp = employees[index];
    document.getElementById("modalTitle").textContent = "Editar";
    document.getElementById("editingIndex").value = index;
    document.getElementById("empName").value = emp.name;
    document.getElementById("empGender").value = emp.gender;

    // Sync UI gender pills
    document.querySelectorAll(".gender-pill").forEach(p => {
        if ((emp.gender === "M" && p.textContent.includes("Masculino")) ||
            (emp.gender === "F" && p.textContent.includes("Femenino"))) {
            p.classList.add("active");
        } else {
            p.classList.remove("active");
        }
    });

    document.getElementById("empForcedLibres").checked = emp.forced_libres || false;
    document.getElementById("empForcedQuebrado").checked = emp.forced_quebrado || false;
    document.getElementById("empNoRest").checked = emp.allow_no_rest || false;
    document.getElementById("empJefePista").checked = emp.is_jefe_pista || false;
    document.getElementById("empStrictPreferences").checked = emp.strict_preferences || false;
    
    // Activo flag mapping
    const empActiveStatus = document.getElementById("empActiveStatus");
    if(empActiveStatus) empActiveStatus.checked = (emp.activo !== false);

    const fixed = emp.fixed_shifts || {};
    document.querySelectorAll(".shift-select").forEach(sel => {
        const day = sel.getAttribute("data-day");
        sel.value = fixed[day] ? fixed[day] : "AUTO";
    });

    // Detect if they have a J_07-17 assigned to pre-fill the dropdown
    // Detect if they have a J_ shift assigned to pre-fill the dropdown
    let defaultJefeShift = "J_06-16";
    if (emp.is_jefe_pista) {
        for (let d of ["Lun", "Mar", "Mié", "Jue", "Vie"]) {
            if (fixed[d] && fixed[d].startsWith("J_")) {
                defaultJefeShift = fixed[d];
                break;
            }
        }
    }
    document.getElementById("jefeShiftSelect").value = defaultJefeShift;
    toggleJefeShiftSelect();

    // Sync checkboxes
    syncVacationCheckboxesFromDropdowns();

    switchTab("tab-general");
    buildDayCards();
    document.getElementById("planillaEmpModal").classList.remove("hidden");
}

function toggleJefeShiftSelect() {
    const isJefe = document.getElementById("empJefePista").checked;
    const configDiv = document.getElementById("jefeShiftConfig");
    if (isJefe) {
        configDiv.classList.add("expanded");
        configDiv.style.display = "block";
    } else {
        configDiv.classList.remove("expanded");
        configDiv.style.display = "none";
    }
}

function animateSelect(el) {
    el.classList.remove("pop-anim");
    void el.offsetWidth; // trigger reflow
    el.classList.add("pop-anim");
}

// ================================================
// CAMBIO 2: Day Cards + Pill Selector System
// ================================================
let activePillDay = null;

// PILL_GROUPS is built dynamically from validationRules loaded from the backend.
// This ensures that any shift added/removed in scheduler_engine.py is immediately reflected here.
function buildPillGroups(day = null) {
    const groups = {
        special: [
            { code: "AUTO", label: "Auto", icon: "fa-robot", color: "#6366f1" },
            { code: "VAC", label: "VAC", icon: "fa-plane", color: "#10b981" },
            { code: "PERM", label: "PERM", icon: "fa-file-signature", color: "#f59e0b" },
            { code: "OFF", label: "LIBRE", icon: "fa-mug-hot", color: "#94a3b8" },
            { code: "N_22-05", label: "Noche", icon: "fa-moon", color: "#818cf8" },
        ],
        morning: [],  // starts before 12pm
        afternoon: [],  // starts 12pm+
        extended: [],  // Q/X/E/R/D prefix or 10+ hour shifts
        jefe: [],
    };

    if (!validationRules || !validationRules.shift_sets) return groups;

    const SKIP = new Set(["OFF", "VAC", "PERM", "N_22-05"]);

    // Solo turnos permitidos el domingo según la lógica del scheduler
    const SUNDAY_ONLY_SHIFTS = new Set([
        "T1_05-13", "T3_07-15", "T8_13-20", "D4_13-22", "T10_15-22", "Q3_05-11+17-22"
    ]);

    // Helper: get the start hour from SHIFTS set
    const startOf = (code) => {
        const hrs = validationRules.shift_sets[code];
        if (!hrs || hrs.length === 0) return 99;
        return Math.min(...hrs);
    };

    // Classify each shift
    const allCodes = Object.keys(validationRules.shift_sets).sort((a, b) => {
        return startOf(a) - startOf(b) || a.localeCompare(b);
    });

    for (const code of allCodes) {
        if (SKIP.has(code)) continue;

        // Filter out invalid shifts for Sunday
        if (day === "Dom" && !SUNDAY_ONLY_SHIFTS.has(code)) {
            continue;
        }

        const hrs = validationRules.shift_sets[code] || [];
        const start = Math.min(...hrs);
        const end = Math.max(...hrs);
        const hours = end - start + 1;  // approx shift length

        // Parse label from code: e.g. "T1_05-13" -> "05-13"
        const parts = code.split("_");
        const timeLabel = parts.length >= 2 ? parts.slice(1).join("+") : code;

        const entry = { code, label: timeLabel };

        if (code.startsWith("J_")) {
            entry.icon = "fa-star";
            groups.jefe.push(entry);
        } else if (code.startsWith("Q") || code.startsWith("X") || code.startsWith("E") || code.startsWith("R") || code.startsWith("D")) {
            // Split/extended/refuerzo shifts
            groups.extended.push(entry);
        } else if (start >= 12) {
            groups.afternoon.push(entry);
        } else {
            groups.morning.push(entry);
        }
    }

    // Sort each group by start hour
    for (const key of ["morning", "afternoon", "extended"]) {
        groups[key].sort((a, b) => startOf(a.code) - startOf(b.code));
    }

    return groups;
}


function getDayCardInfo(code) {
    if (!code || code === "AUTO") return { label: "Auto", icon: "fa-robot", cls: "dc-auto" };
    if (code === "OFF") return { label: "LIBRE", icon: "fa-mug-hot", cls: "dc-off" };
    if (code === "VAC") return { label: "VAC", icon: "fa-plane", cls: "dc-vac" };
    if (code === "PERM") return { label: "PERM", icon: "fa-file-signature", cls: "dc-perm" };
    if (code.startsWith("N_")) return { label: "Noche", icon: "fa-moon", cls: "dc-night" };
    if (code.startsWith("J_")) return { label: code.replace("J_", ""), icon: "fa-star", cls: "dc-jefe" };
    // Split / extended / refuerzo / domingo prefixes
    if (code.startsWith("Q") || code.startsWith("X") || code.startsWith("E") ||
        code.startsWith("R") || code.startsWith("D")) {
        const parts = code.split("_");
        const timeLabel = parts.length >= 2 ? parts.slice(1).join("+") : code;
        return { label: timeLabel, icon: "fa-arrows-left-right", cls: "dc-extended" };
    }
    // Regular T-shifts: classify by start hour
    const m = code.match(/(\d{2})-(\d{2})/);
    if (m) {
        const start = parseInt(m[1]);
        if (start < 12) return { label: `${m[1]}-${m[2]}`, icon: "fa-sun", cls: "dc-morning" };
        return { label: `${m[1]}-${m[2]}`, icon: "fa-cloud-sun", cls: "dc-afternoon" };
    }
    return { label: code, icon: "fa-clock", cls: "dc-auto" };
}

function buildDayCards() {
    const grid = document.getElementById("dayCardsGrid");
    if (!grid) return;
    grid.innerHTML = "";

    DAYS.forEach(d => {
        const sel = document.querySelector(`.shift-select[data-day="${d}"]`);
        const code = sel ? sel.value : "AUTO";
        const info = getDayCardInfo(code);

        const card = document.createElement("div");
        card.className = `day-card ${info.cls}`;
        card.setAttribute("data-day", d);
        card.onclick = () => openPillPanel(d, card);

        card.innerHTML = `
            <span class="dc-day-label">${d}</span>
            <i class="fa-solid ${info.icon} dc-icon"></i>
            <span class="dc-shift-label">${info.label}</span>
        `;
        grid.appendChild(card);
    });
}

function openPillPanel(day, cardEl) {
    activePillDay = day;
    const panel = document.getElementById("pillSelectorPanel");
    document.getElementById("pillPanelDay").textContent = day;

    // Highlight active card
    document.querySelectorAll(".day-card").forEach(c => c.classList.remove("dc-active"));
    if (cardEl) cardEl.classList.add("dc-active");

    // Get current value
    const sel = document.querySelector(`.shift-select[data-day="${day}"]`);
    const current = sel ? sel.value : "AUTO";

    // Build groups dynamically from current backend data, filtering by the selected day
    const PILL_GROUPS = buildPillGroups(day);

    // Fill pill groups
    fillPillGroup("pillGroupSpecial", PILL_GROUPS.special, current);
    fillPillGroup("pillGroupMorning", PILL_GROUPS.morning, current);
    fillPillGroup("pillGroupAfternoon", PILL_GROUPS.afternoon, current);
    fillPillGroup("pillGroupExtended", PILL_GROUPS.extended, current);

    const isJefe = document.getElementById("empJefePista")?.checked;
    const jefeWrap = document.getElementById("pillGroupJefeWrap");
    if (jefeWrap) {
        if (isJefe) {
            jefeWrap.style.display = "flex";
            fillPillGroup("pillGroupJefe", PILL_GROUPS.jefe, current);
        } else {
            jefeWrap.style.display = "none";
        }
    }

    panel.classList.remove("hidden");
    panel.style.animation = "slideDown 0.25s ease-out";
}

function fillPillGroup(containerId, options, currentCode) {
    const container = document.getElementById(containerId);
    container.innerHTML = "";
    options.forEach(opt => {
        const pill = document.createElement("button");
        pill.className = `pill-opt ${opt.code === currentCode ? "pill-selected" : ""}`;
        pill.onclick = () => selectPill(opt.code, opt.label);

        let iconHtml = "";
        if (opt.icon) iconHtml = `<i class="fa-solid ${opt.icon}"></i> `;
        pill.innerHTML = `${iconHtml}${opt.label}`;
        container.appendChild(pill);
    });
}

function selectPill(code, label) {
    if (!activePillDay) return;

    // Update hidden select
    const sel = document.querySelector(`.shift-select[data-day="${activePillDay}"]`);
    if (sel) sel.value = code;

    // Update vacation checkboxes sync
    syncVacationCheckboxesFromDropdowns();

    // Rebuild day cards to reflect the change
    buildDayCards();

    // Close panel
    closePillPanel();
}

function closePillPanel() {
    const panel = document.getElementById("pillSelectorPanel");
    panel.classList.add("hidden");
    activePillDay = null;
    document.querySelectorAll(".day-card").forEach(c => c.classList.remove("dc-active"));
}

function syncDayCardsFromSelects() {
    buildDayCards();
}

async function saveEmployee() {
    const index = parseInt(document.getElementById("editingIndex").value);
    const name = document.getElementById("empName").value;
    if (!name) return alert("Nombre requerido");

    const gender = document.getElementById("empGender").value;

    const isJefe = document.getElementById("empJefePista").checked;

    const empData = {
        name: name,
        gender: gender,
        can_do_night: gender === "M",  // Auto: male can, female cannot
        is_jefe_pista: isJefe,
        forced_libres: document.getElementById("empForcedLibres").checked,
        forced_quebrado: document.getElementById("empForcedQuebrado").checked,
        allow_no_rest: document.getElementById("empNoRest").checked,
        strict_preferences: document.getElementById("empStrictPreferences").checked,
        activo: document.getElementById("empActiveStatus") ? document.getElementById("empActiveStatus").checked : true,
        fixed_shifts: {}
    };

    const selectedJefeShift = document.getElementById("jefeShiftSelect").value;
    const weekdays = ["Lun", "Mar", "Mié", "Jue", "Vie"];

    document.querySelectorAll(".shift-select").forEach(sel => {
        const day = sel.getAttribute("data-day");
        let val = sel.value;

        // Auto-assign chosen Jefe shift ONLY to empty weekdays
        // This stops UI from blocking/overwriting customized shifts like Friday
        if (isJefe && weekdays.includes(day)) {
            if (val === "AUTO") {
                val = selectedJefeShift;
            }
        }

        // Auto-assign Jefe de Pista Saturday (T1_05-13) and Sunday (OFF) ONLY if AUTO
        if (isJefe && day === "Sáb" && val === "AUTO") {
            val = "T1_05-13";
        }
        if (isJefe && day === "Dom" && val === "AUTO") {
            val = "OFF";
        }

        if (val !== "AUTO") {
            empData.fixed_shifts[day] = val;
        }
    });

    if (index === -1) employees.push(empData);
    else employees[index] = empData;

    await fetch(`${API_URL}/employees`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(employees)
    });

    closeModal();
    renderEmployees();
}

async function deleteEmployee(index) {
    if (!confirm("Eliminar?")) return;
    employees.splice(index, 1);
    await fetch(`${API_URL}/employees`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(employees)
    });
    renderEmployees();
}

// GENERATE
async function generateSchedule() {
    const status = document.getElementById("statusMessage");
    status.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Generando...';

    // Ensure config is fresh
    config.night_mode = document.getElementById("nightModeConfig").value;
    config.fixed_night_person = document.getElementById('nightPersonSelect').value;
    config.allow_long_shifts = document.getElementById("allowLongShifts").checked;
    config.use_refuerzo = document.getElementById("useRefuerzo")?.checked || false;
    config.refuerzo_type = document.getElementById("refuerzoTypeSelect")?.value || "diurno";
    config.allow_collision_quebrado = document.getElementById("allowCollisionQuebrado")?.checked || false;
    config.collision_peak_priority = document.getElementById("collisionPeakPriority")?.value || "pm";

    try {
        // AUTO-SYNC: Si hay fechas de semana, sincronizar vacaciones/permisos → turnos fijos
        const weekStart = document.getElementById("weekStartDate")?.value;
        const weekEnd = document.getElementById("weekEndDate")?.value;
        if (weekStart && weekEnd) {
            status.innerHTML = '<i class="fa-solid fa-sync fa-spin"></i> Sincronizando vacaciones...';
            const syncRes = await fetch('/api/sync_vac_fixed_shifts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ fecha_inicio: weekStart, fecha_fin: weekEnd })
            });
            if (syncRes.ok) {
                // Reload employees to get updated fixed_shifts
                await loadEmployees();
            }
            status.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Generando...';
        }

        const res = await fetch(`${API_URL}/solve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ employees, config })
        });
        const result = await res.json();

        if (result.status === "Success" || result.status === "Optimal" || result.status === "Feasible") {
            status.textContent = "Generado!";
            currentGeneratedSchedule = result.schedule;
            currentDailyTasks = result.daily_tasks; // Save tasks
            currentMetadata = result.metadata;

            renderSchedule(result.schedule, "#scheduleTable", result.daily_tasks);
            if (isValidationOn) applyValidationUI(); // apply validation immediately if enabled

            document.getElementById("btnSaveSchedule").classList.remove("hidden");
            const libresText = result.metadata?.libres_person ? `Libres: ${result.metadata.libres_person}` : "Éxito";
            const solutionsCount = result.metadata?.solutions_found ? ` | Óptimos procesados: ${result.metadata.solutions_found}` : "";
            document.getElementById("scheduleMeta").textContent = libresText + solutionsCount;
        } else {
            console.error("Solver Status:", result.status);
            if (result.status === "Infeasible") {
                status.innerHTML = '<span class="error"><i class="fa-solid fa-circle-xmark"></i> Infeasible</span>';
                document.getElementById("scheduleMeta").textContent = "Sin solución factible";
                alert("No se encontró una solución factible con las restricciones actuales. Intenta relajar algunos turnos fijos.");
            } else {
                status.textContent = `Error: ${result.status}`;
                document.getElementById("scheduleMeta").textContent = "Error";
            }
        }

    } catch (e) {
        console.error("Generate Error:", e);
        status.textContent = "Error: " + e.message;
    }
}

function getShiftInfo(s) {
    if (!s || s === "OFF") return { class: "pill-off", icon: "fa-mug-hot", text: "LIBRE" };
    if (s === "Q3_05-11+17-22") return { class: "pill-night", icon: "fa-bolt", text: "05-11 / 17-22" };

    // Determine Type
    let typeClass = "pill-morning"; // Default
    let icon = "fa-sun";

    if (s === "VAC") return { class: "pill-vac", icon: "fa-plane", text: "VAC" };
    if (s === "PERM") return { class: "pill-perm", icon: "fa-file-signature", text: "PERM" };

    // Morning/Day Logic (Corrected to User Request)
    // Morning (< 12): Yellow (pill-morning)
    // Afternoon (>= 12): Blue/Cyan (pill-afternoon)
    // Night (>= 20 or <= 4 or N_): Purple/Blue (pill-night)

    // Heuristic
    const match = s.match(/_(\d{1,2})/);
    let startHour = 8;
    if (match) startHour = parseInt(match[1]);

    if (s.includes("N_") || startHour >= 20 || startHour <= 4) {
        typeClass = "pill-night";
        icon = "fa-moon";
    } else if (startHour >= 12) {
        typeClass = "pill-afternoon";
        icon = "fa-cloud-sun";
    } else {
        typeClass = "pill-morning"; // Morning only
    }

    // Format Text
    let rangePart = s.split('_').slice(1).join('_'); // 08-16
    let timeText = formatTimeRange(rangePart);
    if (!timeText) timeText = s;

    return { class: typeClass, icon, text: timeText };
}

function formatTimeRange(rangeStr) {
    // 08-16 -> 08:00 AM - 04:00 PM
    // 14-22 -> 02:00 PM - 10:00 PM
    // Q1_... -> Logic might need split handling if passed here, but usually passed as "05-11+17-20"

    if (!rangeStr) return "";
    if (rangeStr.includes("+")) {
        return rangeStr.split("+").map(formatTimeRange).join(" / ");
    }

    const parts = rangeStr.split("-");
    if (parts.length !== 2) return rangeStr;

    const start = parseInt(parts[0]);
    const end = parseInt(parts[1]);

    const formatH = (h) => {
        let period = h >= 12 && h < 24 ? "PM" : "AM";
        if (h >= 24) period = "AM"; // Next day
        let hour = h % 12;
        if (hour === 0) hour = 12;
        return `${hour.toString().padStart(2, '0')}:00 ${period}`;
    };

    return `${formatH(start)} - ${formatH(end)}`;
}


let currentSortMode = 'time';

function getAverageStartHour(name, schedule) {
    const days = ["Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue"];
    let sum = 0;
    let count = 0;
    if (!schedule[name]) return 24;

    days.forEach(d => {
        const s = schedule[name][d];
        if (!s || s === "OFF" || s === "VAC") {
            sum += 24;
            count++;
            return;
        }
        const m = s.match(/_(\d{2})/);
        if (m) {
            sum += parseInt(m[1]);
            count++;
        } else {
            sum += 24;
            count++;
        }
    });
    return count === 0 ? 24 : sum / count;
}

let isVerticalView = false;
function toggleVerticalView() {
    isVerticalView = !isVerticalView;
    const btn = document.getElementById("btnToggleVertical");
    if (btn) {
        if (isVerticalView) {
            btn.classList.add("primary");
            btn.innerHTML = `<i class="fa-solid fa-table"></i> Vista Horizontal`;
        } else {
            btn.classList.remove("primary");
            btn.innerHTML = `<i class="fa-solid fa-bars-staggered"></i> Vista Vertical`;
        }
    }

    // Check if main schedule exists to re-render
    if (currentGeneratedSchedule) {
        renderSchedule(currentGeneratedSchedule, "#scheduleTable", currentDailyTasks || {});
        // Also re-apply validation coloring if it was on
        if (isValidationOn) applyValidationUI();
    }
}

function renderSchedule(schedule, tableSelector, tasks = {}) {
    const tableEl = document.querySelector(tableSelector);
    const thead = document.querySelector(`${tableSelector} thead tr`);
    const tbody = document.querySelector(`${tableSelector} tbody`);
    if (!tbody || !thead || !tableEl) return;

    tbody.innerHTML = "";
    thead.innerHTML = "";

    let keys = Object.keys(schedule);
    if (currentSortMode === 'time' && !tableSelector.includes("hist")) {
        // Only sort main schedule by time, history usually static or same logic
        keys.sort((a, b) => {
            const avgA = getAverageStartHour(a, schedule);
            const avgB = getAverageStartHour(b, schedule);
            if (Math.abs(avgA - avgB) < 0.01) return a.localeCompare(b); // Tie-break with name
            return avgA - avgB;
        });
    } else {
        keys.sort(); // Alphabetical default
    }

    let isHistory = tableSelector.includes("hist");
    let historyIndex = isHistory ? parseInt(tableSelector.split("-").pop()) : null;

    if (isVerticalView) {
        tableEl.classList.add("vertical-table");

        // --- VERTICAL (CALENDAR) HEADERS ---
        thead.innerHTML = `<th style="width:120px; text-align:center;">Horario</th>`;
        DAYS.forEach(d => {
            thead.innerHTML += `<th style="text-align:center; min-width:140px;">
                <div style="font-size:1.1rem; font-weight:800; color:var(--text-main);">${d}</div>
            </th>`;
        });

        // --- 1. FIND ALL UNIQUE SHIFTS IN THIS SCHEDULE ---
        let uniqueShifts = new Set();
        keys.forEach(name => {
            DAYS.forEach(d => {
                const s = schedule[name][d];
                if (s && s !== "OFF" && s !== "VAC" && s !== "PERM") {
                    uniqueShifts.add(s);
                }
            });
        });

        // Convert to array and sort chronologically based on 'getAverageStartHour' logic
        let shiftArray = Array.from(uniqueShifts).sort((a, b) => {
            const hA = getAverageStartHour("dummy", { "dummy": { "Vie": a } });
            const hB = getAverageStartHour("dummy", { "dummy": { "Vie": b } });
            return hA - hB;
        });

        // Keep a "Libres / Ausencias" row at the end
        shiftArray.push("OFF_GROUP");

        // --- VERTICAL (CALENDAR) BODY ---
        shiftArray.forEach(shiftCode => {
            const row = document.createElement("tr");

            // Render Row Label (The Time or "Libres")
            if (shiftCode === "OFF_GROUP") {
                row.innerHTML = `<td style="font-weight:700; color:var(--text-muted); text-align:center; font-size:0.9rem; background:var(--bg-app);">
                    <i class="fa-solid fa-bed"></i> Descanso / Ausentes
                </td>`;
            } else {
                const info = getShiftInfo(shiftCode);
                row.innerHTML = `<td style="font-weight:700; color:var(--text-main); text-align:center; font-size:0.9rem;">
                    <div style="margin-bottom:4px;"><i class="fa-solid ${info.icon}" style="color:var(--text-muted);"></i></div>
                    ${info.text}
                </td>`;
            }

            // Render Cells for Each Day
            DAYS.forEach(d => {
                let cellHtml = `<td style="vertical-align: top;">
                                  <div style="display:flex; flex-direction:column; gap:0.5rem; min-height:60px;">`;

                // Find all employees that have exactly THIS shift on THIS day
                keys.forEach(name => {
                    const s = schedule[name][d] || "OFF";

                    // Logic to see if employee belongs in this row
                    let belongsInRow = false;
                    if (shiftCode === "OFF_GROUP") {
                        belongsInRow = (s === "OFF" || s === "VAC" || s === "PERM");
                    } else {
                        belongsInRow = (s === shiftCode);
                    }

                    if (belongsInRow) {
                        const emp = employees.find(e => e.name === name);
                        const role = name === "Refuerzo" ? "REF" : (emp && emp.is_jefe_pista ? "JEFE" : "");
                        const nightBadge = emp && emp.can_do_night ? '<i class="fa-solid fa-moon" style="font-size:0.7em;"></i> ' : '';

                        let info = getShiftInfo(s); // To get colors

                        let tagHtml = role ? `<div style="font-size:0.6rem; opacity:0.8; margin-top:2px;">${role}</div>` : "";
                        let taskHtml = getTaskLabelHTML(tasks, name, d);

                        let editAttr = isHistory ? `onclick="editHistoryShift('${name}', '${d}', ${historyIndex})"` : "";
                        let cursorStyle = isHistory ? "cursor:pointer" : "";

                        cellHtml += `
                            <div class="shift-pill ${info.class}" ${editAttr} style="min-height:auto; padding:0.4rem; flex-direction:row; justify-content:space-between; ${cursorStyle}">
                                <div style="display:flex; flex-direction:column; align-items:flex-start; text-align:left;">
                                    <span style="font-weight:700; font-size:0.9rem;">${nightBadge}${name}</span>
                                    ${tagHtml}
                                </div>
                                <div style="display:flex; align-items:center;">
                                   ${taskHtml}
                                </div>
                            </div>
                        `;
                    }
                });

                cellHtml += `</div></td>`;
                row.innerHTML += cellHtml;
            });

            tbody.appendChild(row);
        });

    } else {
        tableEl.classList.remove("vertical-table");

        // --- HORIZONTAL HEADERS ---
        thead.innerHTML = `
            <th id="th-collaborator" style="cursor:pointer; min-width:160px;" title="Click para ordenar (Nombre / Hora)">
                Empleado <i class="fa-solid fa-sort"></i>
            </th>
            <th>Vie</th><th>S\u00e1b</th><th>Dom</th><th>Lun</th><th>Mar</th><th>Mi\u00e9</th><th>Jue</th>
            <th class="col-hours">Horas</th>
        `;

        // Setup sort listener on main table
        if (!isHistory) {
            thead.querySelector('#th-collaborator').addEventListener('click', () => {
                currentSortMode = currentSortMode === 'time' ? 'alpha' : 'time';
                if (currentGeneratedSchedule) renderSchedule(currentGeneratedSchedule, '#scheduleTable', currentDailyTasks);
            });
        }

        // --- HORIZONTAL BODY ---
        keys.forEach(name => {
            const row = document.createElement("tr");

            const initials = name === "Refuerzo" ? "RF" : name.substring(0, 2).toUpperCase();
            const emp = employees.find(e => e.name === name);
            const nightBadge = emp && emp.can_do_night ? '<i class="fa-solid fa-moon" style="font-size:0.7em; margin-left:4px; color:#6366f1;" title="Turno Noche"></i>' : '';
            const noRestBadge = emp && emp.allow_no_rest ? '<i class="fa-solid fa-battery-empty" style="font-size:0.7em; margin-left:4px; color:#ef4444;" title="Sin Descanso"></i>' : '';
            const forcedLibresBadge = emp && emp.forced_libres ? '<i class="fa-solid fa-thumbtack forced-libres-icon" title="Rol Libres Forzado"></i>' : '';
            const forcedQuebradoBadge = emp && emp.forced_quebrado ? '<i class="fa-solid fa-bolt" style="font-size:0.7em; margin-left:4px; color:#7c3aed;" title="Forzar Quebrado"></i>' : '';
            const refBadge = name === "Refuerzo" ? '<span class="tag night" style="font-size:0.6em; margin-left:4px;">REF</span>' : '';

            row.innerHTML = `
                <td>
                    <div class="emp-cell-content">
                        <div class="emp-avatar" style="${name === "Refuerzo" ? 'background: var(--accent-color);' : ''}">${initials}</div>
                        <div class="emp-details">
                            <span class="emp-name">${name} ${nightBadge} ${noRestBadge} ${forcedLibresBadge} ${forcedQuebradoBadge} ${refBadge}</span>
                            <span class="emp-role">${name === "Refuerzo" ? 'Apoyo Extra' : (emp && emp.is_jefe_pista ? 'Jefe de Pista' : 'Colaborador')}</span>
                        </div>
                    </div>
                </td>
            `;

            let totalHours = 0;

            DAYS.forEach(d => {
                const s = schedule[name][d] || "OFF";
                const info = getShiftInfo(s);

                totalHours += SHIFT_HOURS[s] || 0;

                let fixedClass = "";
                if (emp && emp.fixed_shifts && emp.fixed_shifts[d]) fixedClass = "pill-fixed";

                let editAttr = isHistory ? `onclick="editHistoryShift('${name}', '${d}', ${historyIndex})"` : "";
                let cursorStyle = isHistory ? "cursor:pointer" : "";

                row.innerHTML += `
                    <td>
                        <div class="shift-pill ${info.class} ${fixedClass}" ${editAttr} style="${cursorStyle}">
                            <i class="fa-solid ${info.icon} pill-icon"></i>
                            <span class="pill-time">${info.text}</span>
                            ${getTaskLabelHTML(tasks, name, d)}
                        </div>
                    </td>
                `;
            });

            row.innerHTML += `
                <td class="col-hours">
                    <div class="hours-cell">
                        <strong>${totalHours}</strong> hrs
                    </div>
                </td>
            `;

            tbody.appendChild(row);
        });
    }
}

// HISTORY
async function loadHistory() {
    const listContainer = document.getElementById('historyList');
    listContainer.innerHTML = '<div class="loading"><i class="fa-solid fa-spinner fa-spin"></i> Cargando...</div>';

    try {
        const res = await fetch('/api/history');
        const data = await res.json();
        listContainer.innerHTML = "";

        if (!data.length) {
            listContainer.innerHTML = '<div class="empty-msg">No hay historiales guardados</div>';
            return;
        }

        data.forEach((h, i) => {
            const item = document.createElement("div");
            item.className = "history-item";

            // Date formatting
            const dateStr = new Date(h.timestamp).toLocaleDateString() + ' ' + new Date(h.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

            item.innerHTML = `
                <div class="history-header" onclick="toggleHistory(this)">
                    <div class="h-info">
                        <i class="fa-solid fa-calendar-week"></i>
                        <span class="h-name">${h.name}</span>
                        <span class="h-date">${dateStr}</span>
                    </div>
                    <div class="h-actions">
                        <button class="btn-icon" onclick="validateHistory(${i}, event)" title="Verificar Cobertura">
                            <i class="fa-solid fa-shield-check"></i>
                        </button>
                        <button class="btn-icon" onclick="exportHistoryImage(${i}, event)" title="Exportar Foto">
                            <i class="fa-solid fa-camera"></i>
                        </button>
                        <button class="btn-icon" onclick="exportHistoryExcel(${i}, event)" title="Exportar Excel">
                            <i class="fa-solid fa-file-excel"></i>
                        </button>
                        <i class="fa-solid fa-chevron-down arrow"></i>
                        <button class="btn-icon delete" onclick="deleteHistory(${i}, event)">
                            <i class="fa-solid fa-trash"></i>
                        </button>
                    </div>
                </div>
                <div class="history-body">
                    <div class="history-table-wrapper">
                         <!-- Table injected on expand if needed, or pre-render -->
                         <table class="clean-table" id="hist-table-${i}">
                             <thead>
                                 <tr>
                                     <th>Empleado</th>
                                     <th>Vie</th>
                                     <th>Sáb</th>
                                     <th>Dom</th>
                                     <th>Lun</th>
                                     <th>Mar</th>
                                     <th>Mié</th>
                                     <th>Jue</th>
                                     <th class="col-hours">Horas</th>
                                 </tr>
                             </thead>
                             <tbody>
                             </tbody>
                         </table>
                    </div>
                </div>
            `;
            listContainer.appendChild(item);

            // Render the table immediately (or lazy load)
            renderSchedule(h.schedule, `#hist-table-${i}`, h.daily_tasks);
        });
    } catch (e) {
        listContainer.innerHTML = '<div class="error-msg">Error al cargar historial</div>';
    }
}

function toggleHistory(header) {
    const item = header.parentElement;
    item.classList.toggle('expanded');
}

async function deleteHistory(i, event) {
    if (event) event.stopPropagation(); // prevent toggle
    if (!confirm("¿Borrar este historial permanentemente?")) return;

    await fetch(`/api/history/${i}`, { method: 'DELETE' });
    loadHistory();
}

function exportToExcel() {
    window.location.href = "/api/export_excel";
}

function exportToImage() {
    // Temporarily expand height/width and remove shadows for a clean capture
    const captureElement = document.getElementById("scheduleCapture");
    if (!captureElement) return;

    captureElement.style.overflow = "visible";
    captureElement.style.height = "auto";
    captureElement.style.width = "fit-content";

    // Remove box-shadows (Bug: "cuadrado de otro color")
    const pills = captureElement.querySelectorAll('.shift-pill');
    const originalShadows = Array.from(pills).map(p => p.style.boxShadow);
    pills.forEach(p => p.style.boxShadow = "none");

    html2canvas(captureElement, {
        scale: 2,
        useCORS: true,
        backgroundColor: document.body.classList.contains("dark-mode") ? "#0f172a" : "#ffffff",
    }).then(canvas => {
        // Restore
        captureElement.style.overflow = "";
        captureElement.style.height = "";
        captureElement.style.width = "";
        pills.forEach((p, idx) => p.style.boxShadow = originalShadows[idx]);

        const link = document.createElement('a');
        link.download = 'horario_completo.png';
        link.href = canvas.toDataURL("image/png");
        link.click();
    }).catch(err => {
        console.error("Capture failed:", err);
        // Restore in case of error
        captureElement.style.overflow = "";
        captureElement.style.height = "";
        captureElement.style.width = "";
    });
}

function toggleHoursColumn() {
    const targets = document.querySelectorAll(".col-hours");
    targets.forEach(el => el.classList.toggle("hidden-col"));
}

async function toggleValidation() {
    isValidationOn = !isValidationOn;
    const btn = document.getElementById("btnToggleValidation");
    if (isValidationOn) {
        btn.classList.add("primary");
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Cargando...`;

        try {
            // Fetch dynamically computed rules directly from the python backend engine
            const res = await fetch("/api/validation_rules");
            if (!res.ok) throw new Error(`API returned ${res.status}`);
            validationRules = await res.json();
            btn.innerHTML = `<i class="fa-solid fa-check"></i> Validando...`;
        } catch (err) {
            console.error("Error fetching validation rules:", err);
            alert("Error al obtener reglas de validaci\u00f3n del servidor.\n\n\u00bfEst\u00e1 el servidor corriendo?");
            btn.innerHTML = `<i class="fa-solid fa-check-double"></i> Validaci\u00f3n`;
            isValidationOn = false;
            return;
        }
        // Apply UI outside the fetch try/catch so JS errors don't show as server errors
        try {
            applyValidationUI();
        } catch (uiErr) {
            console.error("Error en applyValidationUI:", uiErr);
        }

    } else {
        btn.classList.remove("primary");
        btn.innerHTML = `<i class="fa-solid fa-check-double"></i> Validación`;
        document.querySelectorAll(".col-valid, .col-invalid, .th-invalid, .td-invalid").forEach(el => {
            el.classList.remove("col-valid", "col-invalid", "th-invalid", "td-invalid");
        });
        const summaryPanel = document.getElementById("validationSummaryPanel");
        if (summaryPanel) summaryPanel.style.display = "none";
        const coveragePanel = document.getElementById("coverageInfoPanel");
        if (coveragePanel) coveragePanel.style.display = "none";
    }
}

function applyValidationUI() {
    // Clear existing validation classes
    document.querySelectorAll(".col-valid, .col-invalid, .col-warn, .th-invalid, .td-invalid, .validation-error-msg, .validation-warn-msg")
        .forEach(el => {
            el.classList.remove("col-valid", "col-invalid", "col-warn", "th-invalid", "td-invalid");
            if (el.classList.contains("validation-error-msg") || el.classList.contains("validation-warn-msg")) el.remove();
        });

    // Remove old panels
    ["validationSummaryPanel", "coverageInfoPanel"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.remove();
    });

    if (!isValidationOn || !currentGeneratedSchedule) return;

    const formatHour = (h) => {
        let d = h >= 24 ? h - 24 : h;
        let h12 = d % 12 || 12;
        return `${h12}${d >= 12 && d < 24 ? "PM" : "AM"}`;
    };

    let hasGlobalErrors = false;
    let hasGlobalWarnings = false;
    const allCoverage = {};
    const dayResults = {};

    // === COMPUTE COVERAGE + VALIDATE ===
    DAYS.forEach((day, index) => {
        const coverage = {};
        for (let i = 5; i <= 28; i++) coverage[i] = 0;

        Object.entries(currentGeneratedSchedule).forEach(([, daysData]) => {
            const s = daysData[day] || "OFF";
            if (!["OFF", "VAC", "PERM"].includes(s)) {
                (validationRules.shift_sets[s] || []).forEach(h => {
                    if (coverage[h] !== undefined) coverage[h]++;
                });
            }
        });

        allCoverage[day] = coverage;

        let errors = [], warnings = [];
        for (let h = 5; h <= 28; h++) {
            const minReq = validationRules.bounds[day]?.[String(h)] ?? 0;
            const softReq = validationRules.soft_bounds?.[day]?.[String(h)] ?? minReq;
            const actual = coverage[h];
            const label = formatHour(h);
            if (minReq > 0 && actual < minReq) {
                errors.push({ label, actual, minReq, softReq });
            } else if (softReq > minReq && actual < softReq) {
                warnings.push({ label, actual, minReq, softReq });
            }
        }

        dayResults[day] = { errors, warnings, colIndex: index + 2 };

        const isDayValid = errors.length === 0;
        const hasWarns = warnings.length > 0;
        if (!isDayValid) hasGlobalErrors = true;
        else if (hasWarns) hasGlobalWarnings = true;

        // Color schedule table columns
        const th = document.querySelector(`#scheduleTable th:nth-child(${index + 2})`);
        const tds = document.querySelectorAll(`#scheduleTable tbody td:nth-child(${index + 2})`);
        if (th) {
            if (!isDayValid) {
                th.classList.add("th-invalid");
                tds.forEach(td => td.classList.add("col-invalid"));
            } else if (hasWarns) {
                th.classList.add("col-warn");
                tds.forEach(td => td.classList.add("col-warn"));
            } else {
                th.classList.add("col-valid");
                tds.forEach(td => td.classList.add("col-valid"));
            }
        }
    });

    // === GLOBAL STATUS BADGE ===
    const overallState = hasGlobalErrors ? "error" : hasGlobalWarnings ? "warn" : "ok";
    const stateConfig = {
        ok: { icon: "fa-circle-check", label: "Horario Óptimo", cls: "vb-ok" },
        warn: { icon: "fa-circle-exclamation", label: "Sub-óptimo", cls: "vb-warn" },
        error: { icon: "fa-triangle-exclamation", label: "Déficit de Cobertura", cls: "vb-error" }
    }[overallState];

    // === FULLSCREEN OVERLAY ===
    let overlay = document.getElementById("validatorOverlay");
    if (!overlay) {
        overlay = document.createElement("div");
        overlay.id = "validatorOverlay";
        overlay.className = "val-overlay";
        document.body.appendChild(overlay);
    }

    // === DAY STATUS CARDS ROW ===
    const summaryEl = document.createElement("div");
    summaryEl.id = "validationSummaryPanel";
    summaryEl.className = "val-summary-wrap";

    const hmEl = document.createElement("div");
    hmEl.id = "coverageInfoPanel";
    hmEl.className = "val-heatmap-wrap";

    const displayHours = Array.from({ length: 19 }, (_, i) => i + 5); // 5..23

    const hmCells = displayHours.map(h => {
        const hourLabel = `<div class="hm-hour">${formatHour(h)}</div>`;
        const cells = DAYS.map(day => {
            const count = allCoverage[day][h] || 0;
            const minReq = validationRules.bounds[day]?.[String(h)] ?? 0;
            const softReq = validationRules.soft_bounds?.[day]?.[String(h)] ?? minReq;
            let cls = count < minReq ? "hmc-deficit" : count < softReq ? "hmc-warn" : "hmc-ok";
            const intensity = minReq > 0 ? Math.min(count / Math.max(softReq, 1), 1) : 1;
            const tooltip = `${day} ${formatHour(h)}: ${count} pers. (min ${minReq}, ideal ${softReq})`;
            return `<div class="hm-cell ${cls}" title="${tooltip}" style="--intensity:${intensity.toFixed(2)}">${count}</div>`;
        }).join("");
        return `<div class="hm-row">${hourLabel}${cells}</div>`;
    }).join("");

    const dayHeaders = DAYS.map(d => `<div class="hm-day-label">${d}</div>`).join("");

    hmEl.innerHTML = `
        <div class="val-heatmap-header">
            <span><i class="fa-solid fa-fire"></i> Mapa de Calor — Cobertura por Hora</span>
            <div class="hm-legend">
                <span class="hml hml-ok">Ideal</span>
                <span class="hml hml-warn">Sub-óptimo</span>
                <span class="hml hml-deficit">Déficit</span>
            </div>
        </div>
        <div class="hm-grid">
            <div class="hm-row hm-header-row"><div class="hm-hour"></div>${dayHeaders}</div>
            ${hmCells}
        </div>`;

    // === BUILD DAY CARDS ===
    const cardsHTML = DAYS.map(day => {
        const { errors, warnings, colIndex } = dayResults[day];
        const st = errors.length > 0 ? "error" : warnings.length > 0 ? "warn" : "ok";
        const cfg = {
            ok: { icon: "✅", pill: "Óptimo", pillCls: "vpill-ok" },
            warn: { icon: "⚠️", pill: "Sub-óptimo", pillCls: "vpill-warn" },
            error: { icon: "🚨", pill: "Déficit", pillCls: "vpill-error" }
        }[st];

        let details = [...errors.map(e =>
            `<div class="vcard-detail vcard-err"><i class="fa-solid fa-xmark"></i>${e.label}: ${e.actual}/${e.minReq}</div>`
        ), ...warnings.map(w =>
            `<div class="vcard-detail vcard-wrn"><i class="fa-solid fa-arrow-up"></i>${w.label}: ${w.actual}\u2192${w.softReq}</div>`
        )].join("") || `<div class="vcard-detail vcard-ok"><i class="fa-solid fa-check"></i>Sin problemas</div>`;

        let allHoursHTML = `<div class="vcard-all-hours" style="display:flex; flex-wrap:wrap; gap:4px; font-size:0.75rem; margin-top:8px;">`;
        for (let h = 5; h <= 28; h++) {
            const actual = allCoverage[day][h] || 0;
            const minReq = validationRules.bounds[day]?.[String(h)] || 0;
            if (actual === 0 && minReq === 0) continue;
            let color = actual < minReq ? "var(--danger)" : "var(--text-muted)";
            allHoursHTML += `<div style="background:var(--bg-app); padding:2px 4px; border-radius:4px; border:1px solid var(--border-color);"><span style="color:${color}; font-weight:bold;">${formatHour(h)}:</span> ${actual}p</div>`;
        }
        allHoursHTML += `</div>`;
        details += allHoursHTML;

        return `
            <div class="vcard vcard-${st}" onclick="document.querySelector('#scheduleTable th:nth-child(${colIndex})').scrollIntoView({behavior:'smooth',block:'nearest',inline:'center'})">
                <div class="vcard-top">
                    <span class="vcard-day">${day}</span>
                    <span class="vpill ${cfg.pillCls}">${cfg.icon} ${cfg.pill}</span>
                </div>
                <div class="vcard-details">${details}</div>
            </div>`;
    }).join("");

    summaryEl.innerHTML = `
        <div class="val-header">
            <div class="val-badge val-badge-${overallState}">
                <i class="fa-solid ${stateConfig.icon}"></i>
                <span>${stateConfig.label}</span>
            </div>
            <span class="val-subtitle">${hasGlobalErrors ? "Hay horas con menos personal del m\u00ednimo requerido" : hasGlobalWarnings ? "Algunas horas no alcanzan el nivel ideal de cobertura" : "Todos los d\u00edas cumplen los requisitos de cobertura"}</span>
        </div>
        <div class="vcards-row">${cardsHTML}</div>`;

    // Build overlay contents

    overlay.innerHTML = `
        <div class="val-overlay-backdrop" onclick="closeValidatorOverlay()"></div>
        <div class="val-overlay-panel">
            <div class="val-overlay-topbar">
                <span class="val-overlay-title"><i class="fa-solid fa-shield-check"></i> Validación de Cobertura</span>
                <button class="val-overlay-close" onclick="closeValidatorOverlay()" title="Minimizar">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            </div>
            <div class="val-overlay-body" id="valOverlayBody"></div>
        </div>`;

    const body = overlay.querySelector("#valOverlayBody");
    body.appendChild(summaryEl);
    body.appendChild(hmEl);

    overlay.classList.remove("val-overlay-hidden");
    overlay.classList.add("val-overlay-visible");
}

function closeValidatorOverlay() {
    const overlay = document.getElementById("validatorOverlay");
    if (overlay) {
        overlay.classList.remove("val-overlay-visible");
        overlay.classList.add("val-overlay-hidden");
    }
    // Show/create the floating reopen button
    let reopenBtn = document.getElementById("validatorReopenBtn");
    if (!reopenBtn) {
        reopenBtn = document.createElement("button");
        reopenBtn.id = "validatorReopenBtn";
        reopenBtn.className = "validator-reopen-btn";
        reopenBtn.onclick = reopenValidatorOverlay;
        reopenBtn.innerHTML = `<i class="fa-solid fa-shield-check"></i> Ver Validación`;
        document.body.appendChild(reopenBtn);
    }
    reopenBtn.style.display = "inline-flex";
}

function reopenValidatorOverlay() {
    const overlay = document.getElementById("validatorOverlay");
    if (overlay) {
        overlay.classList.remove("val-overlay-hidden");
        overlay.classList.add("val-overlay-visible");
    }
    const reopenBtn = document.getElementById("validatorReopenBtn");
    if (reopenBtn) reopenBtn.style.display = "none";
}


function exportHistoryExcel(index, event) {
    if (event) event.stopPropagation();
    window.location.href = `/api/export_excel?history_index=${index}`;
}

window.validateHistory = async function (index, event) {
    if (event) event.stopPropagation();
    try {
        const res = await fetch('/api/history');
        const history = await res.json();
        const entry = history[index];
        if (!entry) return;

        const oldSchedule = currentGeneratedSchedule;
        currentGeneratedSchedule = entry.schedule;

        if (!validationRules) {
            const rulesRes = await fetch("/api/validation_rules");
            validationRules = await rulesRes.json();
        }

        isValidationOn = true;
        applyValidationUI();

        currentGeneratedSchedule = oldSchedule;
    } catch (err) {
        console.error(err);
        alert("Error al validar historial");
    }
};

window.exportHistoryImage = function (index, event) {
    if (event) event.stopPropagation();

    const histTableWrapper = document.getElementById(`hist-table-${index}`);
    if (!histTableWrapper) return;

    const captureElement = histTableWrapper.parentElement;

    const originalBg = captureElement.style.backgroundColor;
    const originalPadding = captureElement.style.padding;
    captureElement.style.backgroundColor = document.body.classList.contains("dark-mode") ? "#0f172a" : "#ffffff";
    captureElement.style.padding = "10px";

    html2canvas(captureElement, {
        scale: 2,
        useCORS: true,
        backgroundColor: document.body.classList.contains("dark-mode") ? "#0f172a" : "#ffffff",
    }).then(canvas => {
        captureElement.style.backgroundColor = originalBg;
        captureElement.style.padding = originalPadding;

        const link = document.createElement('a');
        link.download = `historial_${index}_horario.png`;
        link.href = canvas.toDataURL("image/png");
        link.click();
    }).catch(err => {
        console.error("Capture failed:", err);
        captureElement.style.backgroundColor = originalBg;
        captureElement.style.padding = originalPadding;
    });
};

// EDIT HISTORY SHIFT
async function editHistoryShift(empName, day, histIndex) {
    const res = await fetch('/api/history');
    const history = await res.json();
    const entry = history[histIndex];
    if (!entry) return;

    const currentShift = entry.schedule[empName][day] || "OFF";

    // Create a simple custom prompt or modal for simplicity here
    // In a real app we'd use a nice modal
    const codes = Object.keys(SHIFT_HOURS);
    let msg = `Cambiar turno para ${empName} el ${day}:\n\nOpciones:\n` + codes.join(", ");
    // Allow Free Text Input (User Request)
    // No validation against SHIFT_HOURS keys.
    const newShift = prompt(msg, currentShift);

    if (newShift !== null && newShift.trim() !== "") {
        const val = newShift.trim();
        entry.schedule[empName][day] = val;

        // Save back
        await fetch(`/api/history/${histIndex}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(entry)
        });

        loadHistory(); // Refresh UI
    }
}

// SAVE
function getISOWeekNumber(date) {
    const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
    const dayNum = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() + 4 - dayNum);
    const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    return Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
}

function autoCalcWeekEnd() {
    const startInput = document.getElementById("weekStartDate");
    const endInput = document.getElementById("weekEndDate");
    const preview = document.getElementById("weekNamePreview");
    if (!startInput || !startInput.value) return;

    const start = new Date(startInput.value + "T00:00:00");
    // End = start + 6 days (Viernes→Jueves)
    const end = new Date(start);
    end.setDate(end.getDate() + 6);
    endInput.value = end.toISOString().split("T")[0];

    // Show preview of week name
    const weekNum = getISOWeekNumber(start);
    preview.textContent = `Semana ${weekNum}`;
    preview.style.display = "block";
}

function getWeekDatesMap() {
    const startInput = document.getElementById("weekStartDate");
    if (!startInput || !startInput.value) return null;

    const start = new Date(startInput.value + "T00:00:00");
    const dayNames = ["Vie", "Sab", "Dom", "Lun", "Mar", "Mie", "Jue"];
    // Use Spanish abbreviated day names matching the schedule
    const dayNamesCorrect = ["Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue"];
    const dates = {};
    for (let i = 0; i < 7; i++) {
        const d = new Date(start);
        d.setDate(d.getDate() + i);
        const dd = String(d.getDate()).padStart(2, '0');
        const mm = String(d.getMonth() + 1).padStart(2, '0');
        dates[dayNamesCorrect[i]] = `${dd}/${mm}/${d.getFullYear()}`;
    }
    return dates;
}

function openSaveModal() {
    document.getElementById("saveModal").classList.remove("hidden");
    // Auto-populate name based on week dates
    const startInput = document.getElementById("weekStartDate");
    const nameInput = document.getElementById("scheduleNameInput");
    if (startInput && startInput.value && nameInput) {
        const start = new Date(startInput.value + "T00:00:00");
        const weekNum = getISOWeekNumber(start);
        nameInput.value = `Semana ${weekNum}`;
    } else {
        nameInput.value = "";
    }
}
function closeSaveModal() { document.getElementById("saveModal").classList.add("hidden"); }
async function confirmSaveSchedule() {
    const name = document.getElementById("scheduleNameInput").value;
    if (!name) return;

    const weekDates = getWeekDatesMap();

    await fetch('/api/history', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            name,
            schedule: currentGeneratedSchedule,
            daily_tasks: currentDailyTasks,
            next_sunday_cycle_index: currentMetadata?.next_sunday_cycle_index,
            next_sunday_rotation_queue: currentMetadata?.next_sunday_rotation_queue,
            week_dates: weekDates
        })
    });
    alert("Guardado!");
    closeSaveModal();
}

// UTILS
function populateShiftSelects() {
    document.querySelectorAll(".shift-select").forEach(sel => {
        SHIFT_OPTIONS.forEach(o => {
            const opt = document.createElement("option");
            opt.value = o.code; opt.textContent = o.label;
            sel.appendChild(opt);
        });
    });
}

function switchTab(id) {
    document.querySelectorAll(".m-tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".m-tab-content").forEach(c => c.classList.remove("active"));
    document.getElementById(id).classList.add("active");
    // Find button to active... simplified for now
}
function closeModal() { document.getElementById("employeeModal").classList.add("hidden"); }

// VACATION UI LOGIC
function renderVacationCheckboxes() {
    const container = document.getElementById("vacationCheckboxes");
    if (!container) return;
    container.innerHTML = "";

    DAYS.forEach(d => {
        const wrapper = document.createElement("div");
        wrapper.className = "vac-day-box";

        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.id = `vac-check-${d}`; // Good for labels if needed
        cb.dataset.day = d;
        cb.onchange = (e) => toggleVacation(d, e.target.checked);

        const label = document.createElement("label");
        label.className = "vac-day-label";
        label.setAttribute("for", cb.id); // Although wrapping works too, explicit is safer or just onClick on wrapper

        // Allow clicking the label to toggle input
        label.onclick = (e) => {
            // e.preventDefault(); // Default behavior handles checkbox inside/associate
            // If we click label, it toggles checkbox.
        };

        label.innerHTML = `
           <span>${d}</span>
           <i class="fa-solid fa-plane"></i>
       `;

        wrapper.appendChild(cb);
        wrapper.appendChild(label);
        container.appendChild(wrapper);
    });
}

function resetVacationCheckboxes() {
    const boxes = document.querySelectorAll("#vacationCheckboxes input[type='checkbox']");
    boxes.forEach(b => b.checked = false);
}

function syncVacationCheckboxesFromDropdowns() {
    // If a dropdown says "VAC", check the box
    const selects = document.querySelectorAll(".shift-select");
    selects.forEach(sel => {
        const d = sel.getAttribute("data-day");
        const isVac = sel.value === "VAC";
        const cb = document.querySelector(`#vacationCheckboxes input[data-day='${d}']`);
        if (cb) cb.checked = isVac;
    });
}

function toggleVacation(day, isChecked) {
    const sel = document.querySelector(`.shift-select[data-day='${day}']`);
    if (sel) {
        if (isChecked) sel.value = "VAC";
        else sel.value = "AUTO"; // Revert to auto if unchecked
    }
}

function getTaskLabelHTML(tasks, name, d) {
    if (!tasks || !tasks[name] || !tasks[name][d]) return "";
    let t = tasks[name][d];
    let label = t;
    let colorClass = "task-default";

    if (t === "Baños") {
        label = "Limpiar<br>Baños";
        colorClass = "task-banos";
    } else if (t === "Tanques") {
        label = "Medir<br>Tanque";
        colorClass = "task-tanques";
    } else if (t.includes("Oficina")) {
        // Compound label: "Oficina + Basureros + [Other]"
        // Backend text is "Oficina + Basureros + Baños" or just "Oficina + Basureros"
        // We want to format it nicely:
        // "Oficina +"
        // "Basureros"
        // "+ Baños" (if any)

        // Remove "Oficina + Basureros" base
        let extra = t.replace("Oficina + Basureros", "").trim();
        // Remove leading "+" if present
        if (extra.startsWith("+")) extra = extra.substring(1).trim();

        label = `Oficina +<br>Basureros`;
        if (extra) {
            label += `<br><span class="task-extra">+ ${extra}</span>`;
        }
        colorClass = "task-oficina";
    }

    return `<span class="shift-task-label ${colorClass}">${label}</span>`;
}

// Inject CSS for task labels
const styleTask = document.createElement('style');
styleTask.innerHTML = `
    .shift-task-label {
        font-size: 0.7rem;
        font-weight: 700;
        line-height: 1.1;
        margin-top: 3px;
        text-align: center;
        padding: 2px 4px;
        border-radius: 4px;
        display: block;
    }
    .task-banos { color: #b45309; background: rgba(180, 83, 9, 0.1); border: 1px solid rgba(180, 83, 9, 0.2); }
    .task-tanques { color: #1d4ed8; background: rgba(29, 78, 216, 0.1); border: 1px solid rgba(29, 78, 216, 0.2); }
    .task-oficina { 
        color: #be185d; 
        background: rgba(190, 24, 93, 0.1); 
        border: 1px solid rgba(190, 24, 93, 0.2);
        width: 100%; 
        white-space: nowrap; 
        font-size: 0.65rem; 
        letter-spacing: -0.3px;
        text-shadow: none;
    }
    .dark-mode .task-banos { color: #fbbf24; background: rgba(251, 191, 36, 0.15); }
    .dark-mode .task-tanques { color: #60a5fa; background: rgba(96, 165, 250, 0.15); }
    .dark-mode .task-oficina { color: #f472b6; background: rgba(244, 114, 182, 0.15); }
    .task-extra {
        color: #be185d;
        font-weight: 800;
        font-size: 0.7rem;
    }
    .dark-mode .task-extra { color: #f472b6; }
`;
document.head.appendChild(styleTask);

// Inject CSS for coverage info panel
const styleCoverage = document.createElement('style');
styleCoverage.innerHTML = `
    .coverage-info-panel {
        margin-top: 16px;
        padding: 16px;
        border-radius: 12px;
        background: rgba(99, 102, 241, 0.05);
        border: 1px solid rgba(99, 102, 241, 0.15);
        display: none;
    }
    .dark-mode .coverage-info-panel {
        background: rgba(99, 102, 241, 0.08);
        border-color: rgba(99, 102, 241, 0.2);
    }
    .coverage-header {
        font-size: 0.95rem;
        font-weight: 700;
        margin-bottom: 12px;
        display: flex;
        align-items: center;
        gap: 8px;
        color: #4f46e5;
    }
    .dark-mode .coverage-header { color: #818cf8; }
    .coverage-badge {
        font-size: 0.75rem;
        font-weight: 600;
        padding: 2px 10px;
        border-radius: 12px;
        display: inline-flex;
        align-items: center;
        gap: 4px;
    }
    .coverage-badge-ok {
        background: rgba(16, 185, 129, 0.15);
        color: #059669;
    }
    .dark-mode .coverage-badge-ok {
        background: rgba(16, 185, 129, 0.2);
        color: #34d399;
    }
    .coverage-badge-error {
        background: rgba(239, 68, 68, 0.15);
        color: #dc2626;
    }
    .dark-mode .coverage-badge-error {
        background: rgba(239, 68, 68, 0.2);
        color: #f87171;
    }
    .coverage-table-wrapper {
        overflow-x: auto;
    }
    .coverage-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.8rem;
        text-align: center;
    }
    .coverage-table th {
        padding: 6px 10px;
        font-weight: 700;
        background: rgba(99, 102, 241, 0.08);
        border-bottom: 2px solid rgba(99, 102, 241, 0.2);
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .dark-mode .coverage-table th {
        background: rgba(99, 102, 241, 0.12);
    }
    .coverage-table td {
        padding: 4px 8px;
        border-bottom: 1px solid rgba(0,0,0,0.06);
        font-weight: 600;
        font-size: 0.85rem;
        transition: background 0.2s;
    }
    .dark-mode .coverage-table td {
        border-bottom-color: rgba(255,255,255,0.06);
    }
    .coverage-hour {
        font-weight: 700 !important;
        color: #6366f1;
        text-align: left !important;
        font-size: 0.75rem !important;
        white-space: nowrap;
    }
    .dark-mode .coverage-hour { color: #a5b4fc; }
    .cov-ok {
        background: rgba(16, 185, 129, 0.1);
        color: #059669;
    }
    .dark-mode .cov-ok {
        background: rgba(16, 185, 129, 0.15);
        color: #34d399;
    }
    .cov-deficit {
        background: rgba(239, 68, 68, 0.15);
        color: #dc2626;
        font-weight: 800;
        animation: pulse-deficit 1.5s infinite;
    }
    .dark-mode .cov-deficit {
        background: rgba(239, 68, 68, 0.2);
        color: #f87171;
    }
    @keyframes pulse-deficit {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.7; }
    }
`;
document.head.appendChild(styleCoverage);

// Event Listener for Sorting
document.addEventListener('DOMContentLoaded', () => {
    const th = document.getElementById('th-collaborator');
    if (th) {
        th.addEventListener('click', () => {
            // Toggle Mode
            currentSortMode = (currentSortMode === 'time') ? 'name' : 'time';

            // Render active schedule if available
            // Render active schedule if available
            if (currentGeneratedSchedule) {
                renderSchedule(currentGeneratedSchedule, "#scheduleTable", currentDailyTasks);
            }

            // Update Icon
            // Update Icon
            const icon = th.querySelector('i');
            if (icon) {
                icon.className = (currentSortMode === 'time')
                    ? "fa-solid fa-clock"
                    : "fa-solid fa-sort-alpha-down";
            }
        });
    }
});

// ============================================
// SUNDAY ROTATION VIEWER
// ============================================

function openSundayRotationModal() {
    const modal = document.getElementById('sundayRotationModal');
    if (modal) modal.classList.remove('hidden');
    loadSundayRotation();
}

function closeSundayRotationModal() {
    const modal = document.getElementById('sundayRotationModal');
    if (modal) modal.classList.add('hidden');
}

async function loadSundayRotation() {
    const container = document.getElementById('sundayRotationContent');
    if (!container) return;
    
    container.innerHTML = '<div style="text-align: center; padding: 2rem; color: var(--text-muted);"><i class="fa-solid fa-circle-notch fa-spin"></i> Cargando...</div>';
    
    try {
        const res = await fetch(`${API_URL}/rotacion-domingos`);
        const data = await res.json();
        
        if (!data || data.length === 0) {
            container.innerHTML = '<div style="padding: 1rem; text-align: center; color: var(--text-muted);">No hay historial o empleados elegibles.</div>';
            return;
        }
        
        container.innerHTML = '';
        data.forEach((emp, index) => {
            let colorCls = "var(--text-main)";
            let bgCls = "var(--bg-panel)";
            let icon = "fa-user";
            
            if (index === 0) {
                colorCls = "#10b981"; // green (Priority 1)
                bgCls = "rgba(16, 185, 129, 0.1)";
                icon = "fa-star";
            } else if (index < 3) {
                colorCls = "#3b82f6"; // blue
                bgCls = "rgba(59, 130, 246, 0.1)";
                icon = "fa-arrow-up";
            } else {
                colorCls = "#ef4444"; // red (Must work)
                bgCls = "rgba(239, 68, 68, 0.05)";
                icon = "fa-briefcase";
            }
            
            const row = document.createElement('div');
            row.style.cssText = `display: flex; justify-content: space-between; align-items: center; padding: 0.75rem; background: ${bgCls}; border-radius: 6px; border: 1px solid rgba(255,255,255,0.05); transition: transform 0.2s;`;
            row.className = "hover-glow";
            
            row.innerHTML = `
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div style="width: 28px; height: 28px; border-radius: 50%; background: ${colorCls}; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: bold; box-shadow: 0 2px 5px rgba(0,0,0,0.2);">
                        ${index + 1}
                    </div>
                    <div>
                        <div style="font-weight: 600; font-size: 0.95rem; color: var(--text-main); margin-bottom: 2px;">${emp.name}</div>
                        <div style="font-size: 0.7rem; color: var(--text-muted);"><i class="fa-solid ${icon}" style="color:${colorCls};"></i> ${emp.priority}</div>
                    </div>
                </div>
                <div style="text-align: right;">
                    <span style="font-size: 0.75rem; font-weight: 600; color: ${colorCls}; background: var(--bg-app); padding: 4px 8px; border-radius: 12px; border: 1px solid var(--border); box-shadow: inset 0 1px 3px rgba(0,0,0,0.1);"><i class="fa-solid fa-clock-rotate-left"></i> ${emp.last_off}</span>
                </div>
            `;
            container.appendChild(row);
        });
        
    } catch (e) {
        console.error(e);
        container.innerHTML = '<div style="padding: 1rem; text-align: center; color: #ef4444;"><i class="fa-solid fa-triangle-exclamation"></i> Error cargando rotación. Verifica la conexión con el servidor.</div>';
    }
}