// ========================================================================
// Chronos — Data Service
// Funciones de carga de datos, API, estado global, utilidades
// ========================================================================

/* ── Estado Global ── */
let employees = [];
let config = {};
let currentGeneratedSchedule = null;
let currentDailyTasks = null;
let currentMetadata = null;
let validationRules = null;
let baseValidationRules = null;
let historyEntriesCache = [];
let expandedHistoryItems = new Set();
let hiddenHistoryHours = new Set();
let foldersCache = [];
let trashCache = [];

let SHIFT_OPTIONS = [];
let SHIFT_HOURS = {};
const MANUAL_SHIFT_PREFIX = "MANUAL_";

const DAYS = ["Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue"];
const DAY_INDEX = Object.fromEntries(DAYS.map((day, index) => [day, index]));

const SPECIAL_DAY_DEFAULT = "normal";
const HOLY_THURSDAY_DAY = "Jue";
const SPECIAL_DAY_OPTIONS = [
    { value: "normal", label: "Normal" },
    { value: "sunday_like", label: "Como Domingo" },
    { value: "holy_thursday", label: "2-4-3-2" },
    { value: "closed", label: "Cerrado" },
];

let isValidationOn = false;
let weekSpecialDays = createDefaultSpecialDays();
let historySelectionState = {
    active: false,
    histIndex: null,
    empName: "",
    anchorDay: null,
    currentDay: null,
    days: [],
    dragged: false,
    suppressClick: false,
};

window.__pillEditorMode = window.__pillEditorMode || "employee";

/** Flag 0/1 desde API/SQLite: en JS la cadena "0" es truthy; solo 1 numérico o true cuenta. */
function sqlIntFlagOn(v) {
    if (v === true || v === 1) return true;
    if (v === false || v === 0 || v == null || v === "") return false;
    const n = Number(v);
    return !Number.isNaN(n) && n !== 0;
}
window.sqlIntFlagOn = sqlIntFlagOn;

/** Opciones por día: el domingo no ofrece «Como domingo» (eso es solo excepción en otros días). */
function getSpecialDayOptionsForGridDay(day) {
    let opts =
        day === HOLY_THURSDAY_DAY
            ? [...SPECIAL_DAY_OPTIONS]
            : SPECIAL_DAY_OPTIONS.filter((o) => o.value !== "holy_thursday");
    if (day === "Dom") {
        opts = opts.filter((o) => o.value !== "sunday_like").map((o) =>
            o.value === "normal" ? { ...o, label: "Domingo" } : o
        );
    }
    return opts;
}

function createDefaultSpecialDays() {
    return DAYS.reduce((acc, day) => {
        acc[day] = SPECIAL_DAY_DEFAULT;
        return acc;
    }, {});
}

function normalizeSpecialDaysState(rawState = {}) {
    const normalized = createDefaultSpecialDays();
    if (!rawState || typeof rawState !== "object") {
        return normalized;
    }
    DAYS.forEach(day => {
        const mode = rawState[day];
        if (mode === "normal" || mode === "sunday_like" || mode === "holy_thursday" || mode === "closed") {
            if (day === "Dom" && mode === "sunday_like") {
                normalized[day] = "normal";
            } else if (day !== HOLY_THURSDAY_DAY && mode === "holy_thursday") {
                normalized[day] = "normal";
            } else {
                normalized[day] = mode;
            }
        }
    });
    return normalized;
}

function getSpecialDaysPayload(sourceState = weekSpecialDays) {
    const normalized = normalizeSpecialDaysState(sourceState);
    const payload = {};
    DAYS.forEach(day => {
        const mode = normalized[day];
        if (mode !== SPECIAL_DAY_DEFAULT) {
            payload[day] = mode;
        }
    });
    return payload;
}
window.getSpecialDaysPayload = getSpecialDaysPayload;

function escapeHtmlAttr(value = "") {
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}
window.escapeHtmlAttr = escapeHtmlAttr;

function cloneHistoryEntry(entry) {
    return JSON.parse(JSON.stringify(entry || {}));
}

function sanitizeFileStem(value, fallback = "horario") {
    const normalized = String(value || "")
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "");
    const cleaned = normalized
        .replace(/[<>:"/\\|?*\x00-\x1F]/g, " ")
        .replace(/\s+/g, "_")
        .replace(/_+/g, "_")
        .replace(/^[._-]+|[._-]+$/g, "");
    return cleaned || fallback;
}

function getHistoryExportBaseName(index) {
    const entry = historyEntriesCache[index];
    return sanitizeFileStem(entry?.name, `historial_${index + 1}`);
}

function setStatusMessage(message, kind = "info", timeoutMs = 2600) {
    const status = document.getElementById("statusMessage");
    if (!status) return;
    const iconByKind = {
        success: "fa-check",
        error: "fa-circle-xmark",
        info: "fa-circle-info",
    };
    const icon = iconByKind[kind] || iconByKind.info;
    const className = kind === "error" ? "error" : "";
    status.innerHTML = className
        ? `<span class="${className}"><i class="fa-solid ${icon}"></i> ${message}</span>`
        : `<i class="fa-solid ${icon}"></i> ${message}`;
    if (timeoutMs > 0) {
        window.clearTimeout(setStatusMessage._timer);
        setStatusMessage._timer = window.setTimeout(() => {
            if (status.textContent.includes(message)) {
                status.innerHTML = "";
            }
        }, timeoutMs);
    }
}
window.setStatusMessage = setStatusMessage;

/* ── Validation Rules ── */
async function fetchValidationRules(specialDays = {}) {
    const res = await fetch("/api/validation_rules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ special_days: specialDays || {} })
    });
    if (!res.ok) throw new Error(`API returned ${res.status}`);
    return res.json();
}
window.fetchValidationRules = fetchValidationRules;

async function refreshBaseValidationRules() {
    baseValidationRules = await fetchValidationRules({});
    SHIFT_OPTIONS = baseValidationRules.shift_options;
    SHIFT_HOURS = baseValidationRules.shift_hours;
    if (!validationRules) validationRules = baseValidationRules;
    return baseValidationRules;
}
window.refreshBaseValidationRules = refreshBaseValidationRules;

async function refreshScheduleValidationRules(specialDays = getSpecialDaysPayload()) {
    validationRules = await fetchValidationRules(specialDays);
    return validationRules;
}
window.refreshScheduleValidationRules = refreshScheduleValidationRules;

function formatSpecialDayDate(day) {
    const weekDates = getWeekDatesMap();
    const raw = weekDates?.[day];
    if (!raw) return "";
    const parts = raw.split("/");
    if (parts.length !== 3) return raw;
    return `${parts[0]}/${parts[1]}`;
}

/* ── Custom Shifts ── */
let customShiftsData = [];

const STANDARD_SHIFTS = [
    { name: "T1_05-13", hours: "5am-1pm" },
    { name: "T2_06-14", hours: "6am-2pm" },
    { name: "T3_07-15", hours: "7am-3pm" },
    { name: "T4_08-16", hours: "8am-4pm" },
    { name: "PM", hours: "1pm-10pm" },
    { name: "OFF", hours: "Libre" },
    { name: "VAC", hours: "Vacaciones" },
    { name: "N_22-05", hours: "10pm-5am" },
    { name: "J_06-16", hours: "6am-4pm" },
];

function initCustomShiftsUI() {
    const list = document.getElementById('standardShiftsList');
    if (list) {
        list.innerHTML = STANDARD_SHIFTS.map(s =>
            `<span style="background: var(--surface-2); padding: 2px 8px; border-radius: 12px; font-size: 0.7rem; color: var(--text-muted);">${s.name}</span>`
        ).join('');
    }
    renderCustomShiftsList();
}
window.initCustomShiftsUI = initCustomShiftsUI;

function addCustomShift() {
    const name = document.getElementById('customShiftName')?.value?.trim();
    const start = parseInt(document.getElementById('customShiftStart')?.value);
    const end = parseInt(document.getElementById('customShiftEnd')?.value);
    const priority = parseInt(document.getElementById('customShiftPriority')?.value || '50');
    if (!name || isNaN(start) || isNaN(end)) { alert('Completá nombre, hora inicio y hora fin'); return; }
    if (start < 0 || start > 23 || end < 0 || end > 23) { alert('Las horas deben estar entre 0 y 23'); return; }
    if (start === end) { alert('Hora inicio y fin no pueden ser iguales'); return; }
    if (customShiftsData.some(s => s.name === name)) { alert('Ya existe un turno con ese nombre'); return; }
    customShiftsData.push({ name, start, end, priority, hours: `${start}-${end}` });
    document.getElementById('customShiftName').value = '';
    document.getElementById('customShiftStart').value = '';
    document.getElementById('customShiftEnd').value = '';
    renderCustomShiftsList();
    saveCustomShiftsToConfig();
}
window.addCustomShift = addCustomShift;

function removeCustomShift(index) {
    customShiftsData.splice(index, 1);
    renderCustomShiftsList();
    saveCustomShiftsToConfig();
}
window.removeCustomShift = removeCustomShift;

function renderCustomShiftsList() {
    const container = document.getElementById('customShiftsList');
    if (!container) return;
    if (customShiftsData.length === 0) {
        container.innerHTML = '<p style="margin: 0; color: var(--text-muted); font-size: 0.8rem; text-align: center; padding: 1rem;">Sin turnos personalizados</p>';
        return;
    }
    container.innerHTML = customShiftsData.map((shift, idx) => {
        const priorityLabel = shift.priority === 100 ? '🔴 Alta' : (shift.priority === 50 ? '🟡 Media' : '🟢 Baja');
        const priorityColor = shift.priority === 100 ? '#ef4444' : (shift.priority === 50 ? '#f59e0b' : '#10b981');
        const hours = `${shift.start}:00 - ${shift.end}:00`;
        return `<div style="display: flex; justify-content: space-between; align-items: center; padding: 0.6rem; border-bottom: 1px solid var(--border-color);">
            <div><span style="font-weight: 600; color: var(--text-main);">${shift.name}</span><span style="font-size: 0.75rem; color: var(--text-muted); margin-left: 0.5rem;">${hours}</span></div>
            <div style="display: flex; align-items: center; gap: 0.5rem;"><span style="font-size: 0.7rem; color: ${priorityColor}">${priorityLabel}</span>
            <button type="button" onclick="removeCustomShift(${idx})" style="background: none; border: none; color: #ef4444; cursor: pointer; padding: 2px 6px;"><i class="fa-solid fa-trash"></i></button></div></div>`;
    }).join('');
}
window.renderCustomShiftsList = renderCustomShiftsList;

async function saveCustomShiftsToConfig() {
    try {
        const cfg = getCurrentConfig();
        cfg.custom_shifts = customShiftsData;
        await fetch('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cfg) });
    } catch (e) { console.error('Error saving custom shifts:', e); }
}

async function loadCustomShiftsFromConfig() {
    try {
        const res = await fetch('/api/config');
        if (res.ok) {
            const cfg = await res.json();
            if (cfg.custom_shifts && Array.isArray(cfg.custom_shifts)) {
                customShiftsData = cfg.custom_shifts;
                renderCustomShiftsList();
            }
        }
    } catch (e) { console.error('Error loading custom shifts:', e); }
}

/* ── Holidays ── */
let holidaysData = [];

const CR_DEFAULT_HOLIDAYS = [
    { date: "2026-01-01", name: "Año Nuevo" },
    { date: "2026-04-11", name: "Juan Santamaría" },
    { date: "2026-05-01", name: "Día del Trabajador" },
    { date: "2026-07-25", name: "Anexión de Nicoya" },
    { date: "2026-08-02", name: "Virgen de los Ángeles" },
    { date: "2026-08-15", name: "Día de la Madre" },
    { date: "2026-09-15", name: "Independencia" },
    { date: "2026-12-25", name: "Navidad" },
];

function getHolidaysForYear(year) {
    return CR_DEFAULT_HOLIDAYS.map(h => ({ ...h, date: `${year}-${h.date.slice(5)}` }));
}

function isHoliday(dateStr) {
    return holidaysData.find(h => h.date === dateStr);
}

function weekDateCellToIso(raw) {
    if (raw == null || raw === "") return null;
    const s = String(raw).trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
    const parts = s.split("/");
    if (parts.length === 3) {
        const dd = parts[0].padStart(2, "0");
        const mm = parts[1].padStart(2, "0");
        const yy = parts[2];
        return `${yy}-${mm}-${dd}`;
    }
    return null;
}

function getHolidayForDay(dayName, weekDatesMap, metadataHolidayDays = null) {
    let calHoliday = null;
    if (weekDatesMap && weekDatesMap[dayName]) {
        const iso = weekDateCellToIso(weekDatesMap[dayName]);
        if (iso) calHoliday = isHoliday(iso) || null;
    }
    const metaName = metadataHolidayDays?.[dayName];
    const hasMeta = metaName != null && String(metaName).trim() !== "";
    if (calHoliday) return calHoliday;
    if (hasMeta) return { name: String(metaName).trim(), isMetadata: true };
    return null;
}

function renderHolidaysList() {
    const container = document.getElementById('holidaysList');
    if (!container) return;
    if (holidaysData.length === 0) {
        container.innerHTML = '<p style="margin: 0; color: var(--text-muted); font-size: 0.8rem; text-align: center; padding: 1rem;">Sin días festivos configurados</p>';
        return;
    }
    const sorted = [...holidaysData].sort((a, b) => a.date.localeCompare(b.date));
    container.innerHTML = sorted.map((holiday, idx) => {
        const realIdx = holidaysData.indexOf(holiday);
        const parts = holiday.date.split('-');
        const displayDate = `${parts[2]}/${parts[1]}/${parts[0]}`;
        return `<div style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0.6rem; border-bottom: 1px solid var(--border-color);">
            <div style="display: flex; align-items: center; gap: 0.5rem;">
                <i class="fa-solid fa-star" style="color: #f59e0b; font-size: 0.7rem;"></i>
                <div><span style="font-weight: 600; color: var(--text-main); font-size: 0.82rem;">${holiday.name}</span><span style="font-size: 0.72rem; color: var(--text-muted); margin-left: 0.5rem;">${displayDate}</span></div>
            </div>
            <button type="button" onclick="removeHoliday(${realIdx})" style="background: none; border: none; color: #ef4444; cursor: pointer; padding: 2px 6px;"><i class="fa-solid fa-trash"></i></button></div>`;
    }).join('');
}
window.renderHolidaysList = renderHolidaysList;

function addHoliday() {
    const date = document.getElementById('holidayDateInput')?.value?.trim();
    const name = document.getElementById('holidayNameInput')?.value?.trim();
    if (!date || !name) { alert('Completá fecha y nombre del feriado'); return; }
    if (holidaysData.some(h => h.date === date)) { alert('Ya existe un feriado para esa fecha'); return; }
    holidaysData.push({ date, name });
    document.getElementById('holidayDateInput').value = '';
    document.getElementById('holidayNameInput').value = '';
    renderHolidaysList();
    saveHolidaysToConfig();
}
window.addHoliday = addHoliday;

function removeHoliday(index) {
    holidaysData.splice(index, 1);
    renderHolidaysList();
    saveHolidaysToConfig();
}
window.removeHoliday = removeHoliday;

function loadDefaultCRHolidays() {
    const currentYear = new Date().getFullYear();
    const yearHolidays = getHolidaysForYear(currentYear);
    let added = 0;
    yearHolidays.forEach(h => {
        if (!holidaysData.some(existing => existing.date === h.date)) {
            holidaysData.push(h);
            added++;
        }
    });
    renderHolidaysList();
    saveHolidaysToConfig();
    if (added > 0) setStatusMessage(`${added} feriados de CR cargados`, 'success');
    else setStatusMessage('Los feriados de CR ya están cargados', 'info');
}
window.loadDefaultCRHolidays = loadDefaultCRHolidays;

function clearAllHolidays() {
    if (!confirm('¿Eliminar todos los días festivos?')) return;
    holidaysData = [];
    renderHolidaysList();
    saveHolidaysToConfig();
}
window.clearAllHolidays = clearAllHolidays;

async function saveHolidaysToConfig() {
    try {
        const res = await fetch('/api/config');
        if (res.ok) {
            const currentConfig = await res.json();
            currentConfig.holidays = holidaysData;
            await fetch('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(currentConfig) });
        }
    } catch (e) { console.error('Error saving holidays:', e); }
}

async function loadHolidaysFromConfig() {
    try {
        const res = await fetch('/api/config');
        if (res.ok) {
            const cfg = await res.json();
            if (cfg.holidays && Array.isArray(cfg.holidays)) {
                holidaysData = cfg.holidays;
                renderHolidaysList();
            }
        }
    } catch (e) { console.error('Error loading holidays:', e); }
}

/* ── Special Days Chips ── */
let selectedSpecialDay = null;

function refreshSpecialDayModeRadios() {
    const day = selectedSpecialDay;
    const isDom = day === "Dom";
    const sundayLikeLbl = document.getElementById("specialModeSundayLike");
    const holyLbl = document.getElementById("specialModeHolyThursday");
    const normalTitle = document.querySelector("#specialModeNormal .special-mode-title");
    const normalDesc = document.querySelector("#specialModeNormal .special-mode-desc");
    if (sundayLikeLbl) sundayLikeLbl.style.display = isDom ? "none" : "";
    if (holyLbl) holyLbl.style.display = day === HOLY_THURSDAY_DAY ? "" : "none";
    if (normalTitle && normalDesc) {
        if (isDom) {
            normalTitle.textContent = "Domingo";
            normalDesc.textContent = "Cobertura y turnos de domingo (por defecto)";
        } else {
            normalTitle.textContent = "Normal";
            normalDesc.textContent = "Cobertura estándar de ese día";
        }
    }
}

function renderSpecialDayChips() {
    const chipsContainer = document.getElementById('specialDaysChips');
    const optionsContainer = document.getElementById('specialDayOptions');
    if (!chipsContainer) return;
    chipsContainer.innerHTML = '';
    DAYS.forEach(day => {
        const chip = document.createElement('div');
        const hasSpecial = weekSpecialDays[day] && weekSpecialDays[day] !== SPECIAL_DAY_DEFAULT;
        chip.className = `special-day-chip ${selectedSpecialDay === day ? 'active' : ''} ${hasSpecial ? 'has-special' : ''}`;
        chip.textContent = day;
        chip.onclick = () => selectSpecialDay(day);
        chipsContainer.appendChild(chip);
    });
    if (selectedSpecialDay && optionsContainer) {
        document.getElementById('selectedDayLabel').textContent = `Configurando: ${selectedSpecialDay}`;
        optionsContainer.style.display = 'block';
        const currentValue = weekSpecialDays[selectedSpecialDay] || SPECIAL_DAY_DEFAULT;
        document.querySelectorAll('input[name="specialDayMode"]').forEach(radio => {
            radio.checked = radio.value === currentValue;
        });
        refreshSpecialDayModeRadios();
    } else if (optionsContainer) {
        optionsContainer.style.display = 'none';
    }
}
window.renderSpecialDayChips = renderSpecialDayChips;

function selectSpecialDay(day) {
    if (selectedSpecialDay === day) { selectedSpecialDay = null; }
    else {
        selectedSpecialDay = day;
        if (day === "Dom" && weekSpecialDays[day] === "sunday_like") weekSpecialDays[day] = SPECIAL_DAY_DEFAULT;
    }
    renderSpecialDayChips();
}
window.selectSpecialDay = selectSpecialDay;

function setSpecialDayMode(mode) {
    if (!selectedSpecialDay) return;
    if (selectedSpecialDay === "Dom" && mode === "sunday_like") return;
    weekSpecialDays[selectedSpecialDay] = mode;
    if (currentGeneratedSchedule && isValidationOn) {
        refreshScheduleValidationRules(currentMetadata?.special_days || getSpecialDaysPayload())
            .then(() => { if (typeof applyValidationUI === "function") applyValidationUI(); })
            .catch(err => console.error("Error refreshing validation:", err));
    }
    renderSpecialDayChips();
}
window.setSpecialDayMode = setSpecialDayMode;

function renderWeekSpecialDays() {
    const section = document.getElementById("weekSpecialDaysSection");
    const grid = document.getElementById("weekSpecialDaysGrid");
    const startInput = document.getElementById("weekStartDate");
    if (!section || !grid) return;
    section.style.display = "block";
    grid.innerHTML = "";
    weekSpecialDays = normalizeSpecialDaysState(weekSpecialDays);
    const normalized = weekSpecialDays;
    const hasWeekDate = startInput && startInput.value;
    DAYS.forEach(day => {
        const wrapper = document.createElement("div");
        wrapper.style.display = "grid";
        wrapper.style.gap = "0.45rem";
        wrapper.style.padding = "0.7rem";
        wrapper.style.border = "1px solid var(--border)";
        wrapper.style.borderRadius = "10px";
        wrapper.style.background = "var(--bg-app)";
        const dayDateDisplay = hasWeekDate ? formatSpecialDayDate(day) : '(configure fecha de semana para ver fecha)';
        const label = document.createElement("div");
        label.innerHTML = `<strong style="font-size:0.85rem;">${day}</strong><span style="font-size:0.78rem; color:var(--text-muted); margin-left:0.35rem;">${dayDateDisplay}</span>`;
        const select = document.createElement("select");
        select.className = "custom-input";
        select.style.width = "100%";
        select.style.padding = "0.45rem";
        select.style.background = "var(--bg-panel)";
        select.style.border = "1px solid var(--border)";
        select.style.color = "var(--text-main)";
        select.style.borderRadius = "8px";
        const dayOptions = getSpecialDayOptionsForGridDay(day);
        dayOptions.forEach(option => {
            const opt = document.createElement("option");
            opt.value = option.value;
            opt.textContent = option.label;
            select.appendChild(opt);
        });
        select.value = normalized[day] || SPECIAL_DAY_DEFAULT;
        select.onchange = async (event) => {
            weekSpecialDays[day] = event.target.value;
            weekSpecialDays = normalizeSpecialDaysState(weekSpecialDays);
            if (event.target.value !== weekSpecialDays[day]) { renderWeekSpecialDays(); return; }
            if (currentGeneratedSchedule && isValidationOn) {
                try {
                    await refreshScheduleValidationRules(currentMetadata?.special_days || getSpecialDaysPayload());
                    if (typeof applyValidationUI === "function") applyValidationUI();
                } catch (err) { console.error("Error refreshing validation rules:", err); }
            }
        };
        wrapper.appendChild(label);
        wrapper.appendChild(select);
        grid.appendChild(wrapper);
    });
    if (document.getElementById('specialDaysChips')) renderSpecialDayChips();
}
window.renderWeekSpecialDays = renderWeekSpecialDays;

/* ── Data Loading ── */
const API_URL = "/api";

async function loadData() {
    try {
        const [empRes, cfgRes] = await Promise.all([
            fetch(`${API_URL}/employees?include_inactive=true`),
            fetch(`${API_URL}/config`)
        ]);
        employees = await empRes.json();
        config = await cfgRes.json();
        await refreshBaseValidationRules();
        validationRules = baseValidationRules;
        renderEmployees();
        renderConfig();
        renderWeekSpecialDays();
        populateShiftSelects();
    } catch (e) { console.error(e); }
}
window.loadData = loadData;

async function loadEmployees() {
    try {
        const empRes = await fetch(`${API_URL}/employees?include_inactive=true`);
        employees = await empRes.json();
        renderEmployees();
    } catch (e) { console.error("Error reloading employees:", e); }
}
window.loadEmployees = loadEmployees;

function renderEmployees() {
    const grid = document.getElementById("employeeGrid");
    document.getElementById("employeeCount").textContent = `${employees.length} Empleados`;
    grid.innerHTML = "";
    window.setGender = function (val, btn) {
        document.getElementById("empGender").value = val;
        document.querySelectorAll(".gender-pill").forEach(p => p.classList.remove("active"));
        btn.classList.add("active");
    };
    const select = document.getElementById("nightPersonSelect");
    const container = document.getElementById("nightPersonPills");
    const currentVal = config.fixed_night_person || select.value || "";
    container.innerHTML = "";
    let foundSelection = false;
    employees.forEach((emp, index) => {
        const includedInHorario = emp.incluir_en_horario !== false && emp.incluir_en_horario !== 0;
        if (!includedInHorario && emp.name !== currentVal) return;
        if (!emp.can_do_night && emp.name !== currentVal && emp.activo !== false) return;
        const pill = document.createElement("div");
        const isSelected = emp.name === currentVal;
        const isInactive = emp.activo === false;
        if (isSelected) foundSelection = true;
        pill.className = "night-pill-item";
        pill.style.cssText = `padding: 0.5rem 1rem; border-radius: 20px; border: 2px solid ${isSelected ? 'var(--primary)' : 'var(--border-color)'}; background: ${isSelected ? 'rgba(99, 102, 241, 0.15)' : 'var(--surface-2)'}; color: ${isSelected ? 'var(--primary)' : 'var(--text-main)'}; cursor: pointer; font-size: 0.85rem; font-weight: 500; transition: all 0.2s ease; display: flex; align-items: center; gap: 0.4rem; opacity: ${isInactive ? '0.5' : '1'};`;
        if (!isInactive) {
            pill.onmouseenter = () => { pill.style.borderColor = 'var(--primary)'; pill.style.transform = 'scale(1.05)'; };
            pill.onmouseleave = () => { if (!isSelected) { pill.style.borderColor = 'var(--border-color)'; pill.style.transform = 'scale(1)'; } };
            pill.onclick = () => {
                Array.from(container.children).forEach(c => {
                    c.style.borderColor = 'var(--border-color)'; c.style.background = 'var(--surface-2)'; c.style.color = 'var(--text-main)';
                    const circle = c.querySelector('.night-initials');
                    if (circle) { circle.style.background = 'var(--border-color)'; circle.style.color = 'var(--text-muted)'; }
                });
                pill.style.borderColor = 'var(--primary)'; pill.style.background = 'rgba(99, 102, 241, 0.15)'; pill.style.color = 'var(--primary)';
                const circle = pill.querySelector('.night-initials');
                if (circle) { circle.style.background = 'var(--primary)'; circle.style.color = 'white'; }
                select.value = emp.name;
                updateConfig();
            };
        }
        const names = emp.name.split(' ');
        const initials = names.length > 1 ? names[0][0] + names[names.length - 1][0] : names[0].substring(0, 2);
        const canDoNightBadge = emp.can_do_night ? '' : '<span style="background: #fef3c7; color: #f59e0b; padding: 2px 6px; border-radius: 4px; font-size: 0.65rem; margin-left: 4px;">Sin noche</span>';
        pill.innerHTML = `<span class="night-initials" style="width: 24px; height: 24px; border-radius: 50%; background: ${isSelected ? 'var(--primary)' : 'var(--border-color)'}; color: ${isSelected ? 'white' : 'var(--text-muted)'}; display: flex; align-items: center; justify-content: center; font-size: 0.7rem; font-weight: 700;">${initials}</span><span style="flex: 1;">${emp.name}</span>${canDoNightBadge}`;
        container.appendChild(pill);
    });
    if (container.children.length === 0) {
        container.innerHTML = '<p style="color: var(--text-muted); font-size: 0.8rem; width: 100%; text-align: center; padding: 0.5rem;"><i class="fa-solid fa-triangle-exclamation"></i> Ningún empleado puede hacer turno de noche</p>';
    }
    select.value = currentVal;
}
window.renderEmployees = renderEmployees;

function renderConfig() {
    const mode = config.night_mode || "rotation";
    document.getElementById("nightModeConfig").value = mode;
    document.querySelectorAll("#nightModeSegmented .seg-btn").forEach(btn => {
        if ((mode === "rotation" && btn.textContent.includes("Rotación")) || (mode === "fixed_person" && btn.textContent.includes("Fijo"))) {
            btn.classList.add("active");
        } else { btn.classList.remove("active"); }
    });
    const container = document.getElementById("fixedNightContainer");
    if (mode === "fixed_person") container.classList.remove("hidden"); else container.classList.add("hidden");
    document.getElementById("nightPersonSelect").value = config.fixed_night_person || "";
    const cb = document.getElementById("allowLongShifts");
    if (cb) cb.checked = config.allow_long_shifts || false;
    const strictCb = document.getElementById("strictPreferencesGlobal");
    if (strictCb) strictCb.checked = config.strict_preferences || false;
    const refuerzoCb = document.getElementById("useRefuerzo");
    if (refuerzoCb) refuerzoCb.checked = config.use_refuerzo || false;
    const refuerzoTypeSel = document.getElementById("refuerzoTypeSelect");
    if (refuerzoTypeSel) refuerzoTypeSel.value = config.refuerzo_type || "personalizado";

    // Load per-day schedule (or build from legacy format)
    const refDays = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
    const schedule = config.refuerzo_schedule || {};
    const hasLegacy = config.refuerzo_manual_days && config.refuerzo_manual_days.length > 0;
    refDays.forEach(day => {
        const cb = document.getElementById("refDayActive" + day);
        const startInput = document.getElementById("refDayStart" + day);
        const endInput = document.getElementById("refDayEnd" + day);
        if (!cb || !startInput || !endInput) return;

        if (schedule[day]) {
            cb.checked = true;
            startInput.value = schedule[day].start || "07:00";
            endInput.value = schedule[day].end || "12:00";
        } else if (hasLegacy && config.refuerzo_manual_days.includes(day)) {
            cb.checked = true;
            startInput.value = config.refuerzo_start || "07:00";
            endInput.value = config.refuerzo_end || "12:00";
        } else {
            cb.checked = false;
            startInput.value = "07:00";
            endInput.value = "12:00";
        }
    });
    const partialCb = document.getElementById("refuerzoPartialMode");
    if (partialCb) partialCb.checked = config.refuerzo_partial_mode || false;

    const globalQCb = document.getElementById("allowGlobalQuebrado");
    if (globalQCb) globalQCb.checked = config.allow_global_quebrado !== false;

    toggleRefuerzoConfig();
    const collisionCb = document.getElementById("allowCollisionQuebrado");
    if (collisionCb) collisionCb.checked = config.allow_collision_quebrado || false;
    const q3Cb = document.getElementById("allowQuebradoLargo");
    if (q3Cb) q3Cb.checked = config.allow_quebrado_largo || false;
    const collisionPrioritySel = document.getElementById("collisionPeakPriority");
    if (collisionPrioritySel) collisionPrioritySel.value = config.collision_peak_priority || "pm";
    const historyCb = document.getElementById("useHistoryContext");
    if (historyCb) historyCb.checked = config.use_history !== false;
    toggleCollisionConfig();
    const altAutoMode = config.alternating_pairs === null || config.alternating_pairs === undefined;
    const altAutoToggle = document.getElementById("alternatingAutoMode");
    if (altAutoToggle) {
        altAutoToggle.checked = altAutoMode;
        const altPairsContainer = document.getElementById("alternatingPairsContainer");
        if (altPairsContainer) { if (altAutoMode) altPairsContainer.classList.add("hidden"); else altPairsContainer.classList.remove("hidden"); }
        renderAlternatingPairs();
    }
    const rotCb = document.getElementById("rotationEnabled");
    if (rotCb) rotCb.checked = config.rotation_enabled !== false;
    const strictWeeklyCb = document.getElementById("strictWeeklyAlternation");
    if (strictWeeklyCb) strictWeeklyCb.checked = config.strict_weekly_alternation || false;
    const ctDays = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
    const ctTasks = ["am_banos", "pm_banos", "am_tanques", "pm_tanques", "oficina", "calibracion", "canos", "canos_glp"];
    const cleaningTasks = config.cleaning_tasks || {};
    ctDays.forEach(d => {
        const dayConfig = cleaningTasks[d] || {};
        ctTasks.forEach(t => {
            const cb = document.getElementById(`clean_${t}_${d}`);
            if (cb) {
                if (cleaningTasks[d] && typeof dayConfig[t] === "boolean") { cb.checked = dayConfig[t]; }
                else {
                    if (d === "Dom" && (t === "am_tanques" || t === "pm_tanques")) cb.checked = false;
                    else if (d === "Sáb" && t === "pm_tanques") cb.checked = false;
                    else if (t === "calibracion") cb.checked = d === "Mar";
                    else if (t === "canos") cb.checked = d === "Lun";
                    else if (t === "canos_glp") cb.checked = d === "Jue";
                    else if (t === "oficina") cb.checked = d === "Lun" || d === "Jue";
                    else cb.checked = true;
                }
            }
        });
    });
    const jc = config.jefe_config || {};
    document.getElementById("jefeEnabled").checked = jc.enabled ?? false;
    document.getElementById("jefeExcludeRegular").checked = jc.exclude_regular ?? true;
    let jefeAssignment = jc.assignment;
    if (!jefeAssignment || Object.keys(jefeAssignment).length === 0) {
        jefeAssignment = {};
        document.querySelectorAll('.jefe-cell.jefe-cell-active').forEach(cell => {
            const task = cell.dataset.task; const day = cell.dataset.day;
            if (!task || !day) return;
            if (!jefeAssignment[task]) jefeAssignment[task] = {};
            jefeAssignment[task][day] = true;
        });
    }
    document.querySelectorAll('.jefe-cell').forEach(cell => {
        const task = cell.dataset.task; const day = cell.dataset.day;
        const valueSpan = cell.querySelector('.jefe-cell-value');
        if (!task || !day || !valueSpan) return;
        const isJefe = jefeAssignment[task]?.[day] === true;
        cell.classList.toggle('jefe-cell-active', isJefe);
        valueSpan.textContent = isJefe ? 'Jefe' : '—';
    });
    toggleJefeConfig();
    fillJefeBaseShiftSelectFromRules();
}
window.renderConfig = renderConfig;

/* ── History ── */
async function fetchHistoryEntries(forceRefresh = false) {
    if (!forceRefresh && historyEntriesCache.length) return historyEntriesCache;
    const res = await fetch('/api/history');
    if (!res.ok) throw new Error(`API returned ${res.status}`);
    let entries = await res.json();
    if (!Array.isArray(entries)) entries = [];
    entries.sort((a, b) => {
        const tb = new Date(b.timestamp || 0).getTime();
        const ta = new Date(a.timestamp || 0).getTime();
        if (tb !== ta) return tb - ta;
        return (Number(b.db_id) || 0) - (Number(a.db_id) || 0);
    });
    historyEntriesCache = entries;
    return historyEntriesCache;
}
window.fetchHistoryEntries = fetchHistoryEntries;

async function loadHistory(forceRefresh = false) {
    const listContainer = document.getElementById('historyList');
    if (!listContainer) return;
    listContainer.innerHTML = '<div class="loading"><i class="fa-solid fa-spinner fa-spin"></i> Cargando...</div>';
    try {
        await fetchHistoryEntries(forceRefresh);
        await loadTrash();
        renderHistoryList();
        renderTrashList();
        await loadFolders();
    } catch (e) { console.error(e); listContainer.innerHTML = '<div class="error-msg">Error al cargar historial</div>'; }
}
window.loadHistory = loadHistory;

/* ── Trash ── */
async function loadTrash() {
    try {
        const res = await fetch('/api/history/trash');
        if (!res.ok) return;
        trashCache = await res.json();
    } catch (err) { console.error('Error loading trash:', err); trashCache = []; }
}
window.loadTrash = loadTrash;

function renderTrashList() {
    const trashContainer = document.getElementById('trashList');
    if (!trashContainer) return;
    if (!trashCache.length) { trashContainer.innerHTML = '<div class="empty-msg">La papelera está vacía</div>; return; }
    trashContainer.innerHTML = trashCache.map((t, i) => {
        const deletedDate = t.deleted_at ? new Date(t.deleted_at).toLocaleDateString() : 'N/A';
        return `<div class="trash-item" data-trash-index="${i}"><div class="trash-info"><i class="fa-solid fa-trash-can" style="color: var(--error);"></i><span class="t-name">${t.name}</span><span class="t-date">Eliminado: ${deletedDate}</span></div><div class="trash-actions"><button type="button" class="btn-icon btn-restore" onclick="restoreHistory(${i}, event)" title="Restaurar"><i class="fa-solid fa-rotate-left"></i> Restaurar</button><button type="button" class="btn-icon btn-perm-delete" onclick="permanentDeleteTrash(${i}, event)" title="Eliminar permanentemente"><i class="fa-solid fa-ban"></i></button></div></div>`;
    }).join('');
}
window.renderTrashList = renderTrashList;

/* ── Folders ── */
function toggleFoldersSection() {
    const body = document.getElementById("foldersBody"); const arrow = document.getElementById("foldersArrow");
    if (!body || !arrow) return; body.classList.toggle("hidden"); arrow.classList.toggle("rotated");
}
window.toggleFoldersSection = toggleFoldersSection;

function toggleFolderCreate() {
    const input = document.getElementById("folderNameInput"); const btn = document.getElementById("btnToggleFolderCreate");
    if (!input || !btn) return;
    const isHidden = input.style.display === "none" || !input.style.display;
    input.style.display = isHidden ? "inline-block" : "none";
    if (isHidden) { input.focus(); btn.innerHTML = '<i class="fa-solid fa-times"></i> Cancelar'; }
    else { btn.innerHTML = '<i class="fa-solid fa-folder-plus"></i> Nueva'; }
}
window.toggleFolderCreate = toggleFolderCreate;

async function createFolder() {
    const input = document.getElementById("folderNameInput");
    if (!input) return;
    const name = input.value.trim();
    if (!name) { alert("Ingresá un nombre para la carpeta (ej: 2026)."); return; }
    try {
        const res = await fetch('/api/folders', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) });
        if (!res.ok) throw new Error(await res.text());
        input.value = ""; input.style.display = "none";
        document.getElementById("btnToggleFolderCreate").innerHTML = '<i class="fa-solid fa-folder-plus"></i> Nueva';
        await loadFolders();
        setStatusMessage(`Carpeta "${name}" creada.`, "success");
    } catch (e) { alert("Error al crear carpeta: " + e.message); }
}
window.createFolder = createFolder;

async function loadFolders() {
    const container = document.getElementById("foldersList");
    if (!container) return;
    try {
        const res = await fetch('/api/folders');
        const folders = await res.json();
        foldersCache = folders;
        if (!folders.length) { container.innerHTML = '<div class="empty-msg" style="padding:1rem;text-align:center;color:var(--text-muted);font-size:0.85rem;"><i class="fa-solid fa-folder-open"></i> Sin carpetas aún. Creá una para agrupar horarios del año.</div>'; return; }
        container.innerHTML = folders.map(f => `<div class="folder-card"><div class="folder-card-info" onclick="openFolderDetail(${f.id})" style="cursor:pointer;flex:1;"><div class="folder-card-icon"><i class="fa-solid fa-folder"></i></div><div><div class="folder-card-name">${escapeHtml(f.name)}</div><div class="folder-card-count">${f.entry_count} horario${f.entry_count !== 1 ? 's' : ''}</div></div></div><div class="folder-card-actions"><button class="btn-icon" onclick="event.stopPropagation();deleteFolder(${f.id})" title="Eliminar carpeta"><i class="fa-solid fa-trash"></i></button></div></div>`).join('');
    } catch (e) { console.error("Error loading folders:", e); container.innerHTML = '<div class="error-msg">Error al cargar carpetas</div>'; }
}
window.loadFolders = loadFolders;

async function deleteFolder(folderId) {
    const folder = foldersCache.find(f => f.id === folderId);
    const hasEntries = folder && folder.entry_count > 0;
    let msg = `¿Eliminar la carpeta "${folder?.name || ''}"?`;
    if (hasEntries) {
        msg = `¡ATENCIÓN! La carpeta "${folder?.name || ''}" contiene ${folder.entry_count} horario(s).\n\nAl eliminarla, TODOS los horarios se irán a la papelera por 7 días.\n\n¿Estás ABSOLUTAMENTE seguro? (3 clics necesarios)`;
    }
    if (hasEntries) {
        if (!confirm(msg)) return;
        if (!confirm(`⚠️ CONFIRMACIÓN 2/3: ¿Seguro que querés eliminar "${folder?.name || ''}" con TODOS sus horarios?`)) return;
        if (!confirm(`🚨 CONFIRMACIÓN 3/3: Esta acción es irreversible. ¿Eliminar definitivamente?`)) return;
    } else { if (!confirm(msg)) return; }
    try {
        const res = await fetch(`/api/folders/${folderId}?purge=${hasEntries ? 'false' : 'false'}`, { method: 'DELETE' });
        if (!res.ok) throw new Error(await res.text());
        await loadFolders();
        setStatusMessage(hasEntries ? `Carpeta enviada a papelera.` : "Carpeta eliminada.", "success");
    } catch (e) { alert("Error: " + e.message); }
}
window.deleteFolder = deleteFolder;

async function openFolderDetail(folderId) {
    const folder = foldersCache.find(f => f.id === folderId);
    if (!folder) return;
    try {
        const res = await fetch(`/api/folders/${folderId}/entries`);
        if (!res.ok) throw new Error(await res.text());
        const entries = await res.json();
        const existing = document.getElementById("folderDetailModal");
        if (existing) existing.remove();
        const modal = document.createElement("div");
        modal.id = "folderDetailModal";
        modal.className = "modal-backdrop";
        modal.innerHTML = `<div class="modal-dialog large" style="max-width: 600px;"><div class="modal-header-simple"><h3><i class="fa-solid fa-folder-open" style="color:var(--primary);"></i> ${escapeHtml(folder.name)}</h3><button class="close-icon" onclick="document.getElementById('folderDetailModal').remove()"><i class="fa-solid fa-xmark"></i></button></div><div class="modal-body-scroll">${entries.length === 0 ? '<p style="text-align:center;color:var(--text-muted);padding:2rem 0;">La carpeta está vacía.</p>' : ''}${entries.map(e => `<div class="folder-detail-entry"><div><span class="folder-detail-entry-name">${escapeHtml(e.name)}</span><span class="folder-detail-entry-date">${e.timestamp ? new Date(e.timestamp).toLocaleDateString() : ''}</span></div><div style="display:flex;gap:0.4rem;"><button class="btn-icon" onclick="exportHistoryExcelByDbId(${e.db_id})" title="Exportar Excel"><i class="fa-solid fa-file-excel"></i></button><button class="btn-icon" onclick="removeFromFolder(${folderId}, ${e.db_id})" title="Quitar de carpeta"><i class="fa-solid fa-xmark" style="color:var(--danger);"></i></button></div></div>`).join('')}</div>${entries.length > 0 ? `<div class="modal-actions-footer" style="justify-content:space-between;"><span style="font-size:0.8rem;color:var(--text-muted);">${entries.length} horario${entries.length !== 1 ? 's' : ''}</span><button class="btn-action primary" onclick="exportFolderExcel(${folderId})"><i class="fa-solid fa-file-excel"></i> Exportar todo como Excel</button></div>` : ''}</div>`;
        document.body.appendChild(modal);
        modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    } catch (e) { alert("Error: " + e.message); }
}
window.openFolderDetail = openFolderDetail;

function addHistoryToFolder(i, event) {
    event.stopPropagation();
    const entry = historyEntriesCache[i];
    if (!entry || !entry.db_id) { alert("No se pudo identificar este historial."); return; }
    if (!foldersCache || !foldersCache.length) { alert("No hay carpetas creadas aún. Creá una carpeta primero."); return; }
    const existing = document.getElementById("addToFolderModal");
    if (existing) existing.remove();
    const modal = document.createElement("div");
    modal.id = "addToFolderModal";
    modal.className = "modal-backdrop";
    modal.innerHTML = `<div class="modal-dialog" style="max-width: 360px;"><div class="modal-header-simple"><h3>Agregar a carpeta</h3><button class="close-icon" onclick="document.getElementById('addToFolderModal').remove()"><i class="fa-solid fa-xmark"></i></button></div><div class="modal-body-scroll" style="max-height: 60vh;">${foldersCache.map(f => `<div class="folder-select-item" onclick="addToFolder(${f.id}, ${entry.db_id}); document.getElementById('addToFolderModal').remove();" style="cursor:pointer;padding:0.6rem 0.8rem;display:flex;align-items:center;gap:0.5rem;border-bottom:1px solid var(--border);transition:background 0.15s;" onmouseover="this.style.background='var(--bg-hover)'" onmouseout="this.style.background='transparent'"><i class="fa-solid fa-folder" style="color:var(--primary);"></i><span>${escapeHtml(f.name)}</span><span style="margin-left:auto;font-size:0.75rem;color:var(--text-muted);">${f.entry_count} horario${f.entry_count !== 1 ? 's' : ''}</span></div>`).join('')}</div></div>`;
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
}
window.addHistoryToFolder = addHistoryToFolder;

async function addToFolder(folderId, entryDbId) {
    try {
        const res = await fetch(`/api/folders/${folderId}/entries`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ entry_ids: [entryDbId] }) });
        if (!res.ok) throw new Error(await res.text());
        setStatusMessage("Horario agregado a carpeta.", "success");
        await loadFolders();
    } catch (e) { alert("Error: " + e.message); }
}
window.addToFolder = addToFolder;

async function removeFromFolder(folderId, entryDbId) {
    try {
        const res = await fetch(`/api/folders/${folderId}/entries/${entryDbId}`, { method: 'DELETE' });
        if (!res.ok) throw new Error(await res.text());
        openFolderDetail(folderId);
        await loadFolders();
    } catch (e) { alert("Error: " + e.message); }
}
window.removeFromFolder = removeFromFolder;

async function exportFolderExcel(folderId) {
    try {
        const res = await fetch(`/api/folders/${folderId}/export-excel`);
        if (!res.ok) { const err = await res.json(); throw new Error(err.detail || "Error al exportar"); }
        const data = await res.json();
        showExportConfirmationModal(data.filename, 'excel');
    } catch (e) { alert(e.message); }
}
window.exportFolderExcel = exportFolderExcel;

async function exportHistoryExcelByDbId(dbId) {
    window.open(`/api/export_excel?history_db_id=${dbId}`, '_blank');
}
window.exportHistoryExcelByDbId = exportHistoryExcelByDbId;

/* ── Helpers ── */
function getWeekDatesMap() {
    const startVal = document.getElementById("weekStartDate")?.value;
    if (!startVal) return {};
    const start = new Date(startVal + "T12:00:00");
    const result = {};
    DAYS.forEach((day, i) => {
        const d = new Date(start);
        d.setDate(start.getDate() + i);
        const dd = String(d.getDate()).padStart(2, "0");
        const mm = String(d.getMonth() + 1).padStart(2, "0");
        const yyyy = d.getFullYear();
        result[day] = `${dd}/${mm}/${yyyy}`;
    });
    return result;
}
window.getWeekDatesMap = getWeekDatesMap;

function getAutofillWeekNumber(date) {
    const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
    const dayNum = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() + 4 - dayNum);
    const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    return Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
}

function _fridayToWeekDates(fridayIso) {
    const fri = new Date(fridayIso + "T12:00:00");
    const wd = {};
    const manualDays = ["Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue"];
    manualDays.forEach((day, i) => {
        const d = new Date(fri);
        d.setDate(fri.getDate() + i);
        const dd = String(d.getDate()).padStart(2, "0");
        const mm = String(d.getMonth() + 1).padStart(2, "0");
        const yyyy = d.getFullYear();
        wd[day] = `${dd}/${mm}/${yyyy}`;
    });
    return wd;
}

/* ── getCurrentConfig ── */
function getCurrentConfig() {
    return { ...config };
}
window.getCurrentConfig = getCurrentConfig;
