const API_URL = "/api";

// STATE
let employees = [];
window.__pillEditorMode = window.__pillEditorMode || "employee";

let config = {};
let currentGeneratedSchedule = null;
let currentDailyTasks = null;
let currentMetadata = null;
let validationRules = null;
let baseValidationRules = null;
let historyEntriesCache = [];
let expandedHistoryItems = new Set();
let hiddenHistoryHours = new Set();

let SHIFT_OPTIONS = [];
let SHIFT_HOURS = {};
const MANUAL_SHIFT_PREFIX = "MANUAL_";

// Hourly set mapping mapped dynamically via API now
// Removing hardcoded SHIFT_HOURS_SET

const DAYS = ["Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue"];

/** Flag 0/1 desde API/SQLite: en JS la cadena "0" es truthy; solo 1 numérico o true cuenta. */
function sqlIntFlagOn(v) {
    if (v === true || v === 1) return true;
    if (v === false || v === 0 || v == null || v === "") return false;
    const n = Number(v);
    return !Number.isNaN(n) && n !== 0;
}

const SPECIAL_DAY_DEFAULT = "normal";
const HOLY_THURSDAY_DAY = "Jue";
const SPECIAL_DAY_OPTIONS = [
    { value: "normal", label: "Normal" },
    { value: "sunday_like", label: "Como Domingo" },
    { value: "holy_thursday", label: "2-4-3-2" },
    { value: "closed", label: "Cerrado" },
];

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
const DAY_INDEX = Object.fromEntries(DAYS.map((day, index) => [day, index]));

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

document.addEventListener("DOMContentLoaded", () => {
    // Default to Dark Mode
    document.body.classList.add('dark-mode');

    loadData().then(() => {
        renderVacationCheckboxes(); // Init new UI logic after data loads
        initCustomShiftsUI(); // Init custom shifts UI
        loadCustomShiftsFromConfig(); // Load saved custom shifts
        loadHolidaysFromConfig(); // Load saved holidays
        
        // Auto-fill main week start date with upcoming Friday if empty
        const startInput = document.getElementById("weekStartDate");
        if (startInput && !startInput.value) {
            const d = new Date();
            const diff = (5 - d.getDay() + 7) % 7;
            d.setDate(d.getDate() + diff);
            const y = d.getFullYear();
            const m = String(d.getMonth() + 1).padStart(2, "0");
            const dayDate = String(d.getDate()).padStart(2, "0");
            startInput.value = `${y}-${m}-${dayDate}`;
            if (typeof autoCalcWeekEnd === "function") autoCalcWeekEnd();
        }
    });

    // Theme toggle
    const btn = document.getElementById('theme-toggle');
    if (btn) btn.onclick = () => document.body.classList.toggle('dark-mode');
});

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

function escapeHtmlAttr(value = "") {
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

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

async function fetchValidationRules(specialDays = {}) {
    const res = await fetch("/api/validation_rules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ special_days: specialDays || {} })
    });
    if (!res.ok) {
        throw new Error(`API returned ${res.status}`);
    }
    return res.json();
}

async function refreshBaseValidationRules() {
    baseValidationRules = await fetchValidationRules({});
    SHIFT_OPTIONS = baseValidationRules.shift_options;
    SHIFT_HOURS = baseValidationRules.shift_hours;
    if (!validationRules) {
        validationRules = baseValidationRules;
    }
    return baseValidationRules;
}

async function refreshScheduleValidationRules(specialDays = getSpecialDaysPayload()) {
    validationRules = await fetchValidationRules(specialDays);
    return validationRules;
}

function formatSpecialDayDate(day) {
    const weekDates = getWeekDatesMap();
    const raw = weekDates?.[day];
    if (!raw) return "";
    const parts = raw.split("/");
    if (parts.length !== 3) return raw;
    return `${parts[0]}/${parts[1]}`;
}

// ===== TURNOS PERSONALIZADOS (AVANZADO) =====
let customShiftsData = []; // Array of { name, start, end, priority }

// Standard shifts (read from backend or hardcoded)
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
    // Render standard shifts info
    const list = document.getElementById('standardShiftsList');
    if (list) {
        list.innerHTML = STANDARD_SHIFTS.map(s => 
            `<span style="background: var(--surface-2); padding: 2px 8px; border-radius: 12px; font-size: 0.7rem; color: var(--text-muted);">${s.name}</span>`
        ).join('');
    }
    renderCustomShiftsList();
}

function addCustomShift() {
    const name = document.getElementById('customShiftName')?.value?.trim();
    const start = parseInt(document.getElementById('customShiftStart')?.value);
    const end = parseInt(document.getElementById('customShiftEnd')?.value);
    const priority = parseInt(document.getElementById('customShiftPriority')?.value || '50');
    
    if (!name || isNaN(start) || isNaN(end)) {
        alert('Completá nombre, hora inicio y hora fin');
        return;
    }
    
    if (start < 0 || start > 23 || end < 0 || end > 23) {
        alert('Las horas deben estar entre 0 y 23');
        return;
    }
    
    if (start === end) {
        alert('Hora inicio y fin no pueden ser iguales');
        return;
    }
    
    // Check if already exists
    if (customShiftsData.some(s => s.name === name)) {
        alert('Ya existe un turno con ese nombre');
        return;
    }
    
    // Add to data
    customShiftsData.push({
        name: name,
        start: start,
        end: end,
        priority: priority,
        hours: `${start}-${end}`
    });
    
    // Clear form
    document.getElementById('customShiftName').value = '';
    document.getElementById('customShiftStart').value = '';
    document.getElementById('customShiftEnd').value = '';
    
    renderCustomShiftsList();
    saveCustomShiftsToConfig();
}

function removeCustomShift(index) {
    customShiftsData.splice(index, 1);
    renderCustomShiftsList();
    saveCustomShiftsToConfig();
}

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
        return `
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.6rem; border-bottom: 1px solid var(--border-color);">
                <div>
                    <span style="font-weight: 600; color: var(--text-main);">${shift.name}</span>
                    <span style="font-size: 0.75rem; color: var(--text-muted); margin-left: 0.5rem;">${hours}</span>
                </div>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                    <span style="font-size: 0.7rem; color: ${priorityColor}">${priorityLabel}</span>
                    <button type="button" onclick="removeCustomShift(${idx})" style="background: none; border: none; color: #ef4444; cursor: pointer; padding: 2px 6px;">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

async function saveCustomShiftsToConfig() {
    try {
        const config = getCurrentConfig();
        config.custom_shifts = customShiftsData;
        await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
    } catch (e) {
        console.error('Error saving custom shifts:', e);
    }
}

async function loadCustomShiftsFromConfig() {
    try {
        const res = await fetch('/api/config');
        if (res.ok) {
            const config = await res.json();
            if (config.custom_shifts && Array.isArray(config.custom_shifts)) {
                customShiftsData = config.custom_shifts;
                renderCustomShiftsList();
            }
        }
    } catch (e) {
        console.error('Error loading custom shifts:', e);
    }
}

// ===== END TURNOS PERSONALIZADOS =====

// ===== DÍAS FESTIVOS (FERIADOS CR) =====
let holidaysData = []; // Array of { date: "YYYY-MM-DD", name: "..." }

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
    return CR_DEFAULT_HOLIDAYS.map(h => ({
        ...h,
        date: `${year}-${h.date.slice(5)}`
    }));
}

function isHoliday(dateStr) {
    // dateStr is "YYYY-MM-DD"
    return holidaysData.find(h => h.date === dateStr);
}

/** Convierte fecha de celda week_dates (DD/MM/YYYY o YYYY-MM-DD) a ISO YYYY-MM-DD. */
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
    // Cruza feriados globales (holidaysData) con la fecha REAL de esa columna en la semana mostrada.
    // Importante en historial: weekDatesMap debe ser entry.week_dates, no la semana del selector del motor.
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
    
    // Sort by date
    const sorted = [...holidaysData].sort((a, b) => a.date.localeCompare(b.date));
    
    container.innerHTML = sorted.map((holiday, idx) => {
        const realIdx = holidaysData.indexOf(holiday);
        const parts = holiday.date.split('-');
        const displayDate = `${parts[2]}/${parts[1]}/${parts[0]}`;
        return `
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0.6rem; border-bottom: 1px solid var(--border-color);">
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                    <i class="fa-solid fa-star" style="color: #f59e0b; font-size: 0.7rem;"></i>
                    <div>
                        <span style="font-weight: 600; color: var(--text-main); font-size: 0.82rem;">${holiday.name}</span>
                        <span style="font-size: 0.72rem; color: var(--text-muted); margin-left: 0.5rem;">${displayDate}</span>
                    </div>
                </div>
                <button type="button" onclick="removeHoliday(${realIdx})" style="background: none; border: none; color: #ef4444; cursor: pointer; padding: 2px 6px;">
                    <i class="fa-solid fa-trash"></i>
                </button>
            </div>
        `;
    }).join('');
}

function addHoliday() {
    const dateInput = document.getElementById('holidayDateInput');
    const nameInput = document.getElementById('holidayNameInput');
    
    const date = dateInput?.value?.trim();
    const name = nameInput?.value?.trim();
    
    if (!date || !name) {
        alert('Completá fecha y nombre del feriado');
        return;
    }
    
    // Check if already exists
    if (holidaysData.some(h => h.date === date)) {
        alert('Ya existe un feriado para esa fecha');
        return;
    }
    
    holidaysData.push({ date, name });
    
    // Clear form
    dateInput.value = '';
    nameInput.value = '';
    
    renderHolidaysList();
    saveHolidaysToConfig();
}

function removeHoliday(index) {
    holidaysData.splice(index, 1);
    renderHolidaysList();
    saveHolidaysToConfig();
}

function loadDefaultCRHolidays() {
    // Get current year
    const currentYear = new Date().getFullYear();
    const yearHolidays = getHolidaysForYear(currentYear);
    
    // Only add holidays that don't already exist
    let added = 0;
    yearHolidays.forEach(h => {
        if (!holidaysData.some(existing => existing.date === h.date)) {
            holidaysData.push(h);
            added++;
        }
    });
    
    renderHolidaysList();
    saveHolidaysToConfig();
    
    if (added > 0) {
        setStatusMessage(`${added} feriados de CR cargados`, 'success');
    } else {
        setStatusMessage('Los feriados de CR ya están cargados', 'info');
    }
}

function clearAllHolidays() {
    if (!confirm('¿Eliminar todos los días festivos?')) return;
    holidaysData = [];
    renderHolidaysList();
    saveHolidaysToConfig();
}

async function saveHolidaysToConfig() {
    try {
        const res = await fetch('/api/config');
        if (res.ok) {
            const currentConfig = await res.json();
            currentConfig.holidays = holidaysData;
            await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(currentConfig)
            });
        }
    } catch (e) {
        console.error('Error saving holidays:', e);
    }
}

async function loadHolidaysFromConfig() {
    try {
        const res = await fetch('/api/config');
        if (res.ok) {
            const config = await res.json();
            if (config.holidays && Array.isArray(config.holidays)) {
                holidaysData = config.holidays;
                renderHolidaysList();
            }
        }
    } catch (e) {
        console.error('Error loading holidays:', e);
    }
}

// ===== END DÍAS FESTIVOS =====

// ===== NEW SPECIAL DAYS CHIPS UI =====
let selectedSpecialDay = null;

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
    
    // Show options for selected day
    if (selectedSpecialDay && optionsContainer) {
        document.getElementById('selectedDayLabel').textContent = `Configurando: ${selectedSpecialDay}`;
        optionsContainer.style.display = 'block';
        
        // Set current value
        const currentValue = weekSpecialDays[selectedSpecialDay] || SPECIAL_DAY_DEFAULT;
        document.querySelectorAll('input[name="specialDayMode"]').forEach(radio => {
            radio.checked = radio.value === currentValue;
        });
        refreshSpecialDayModeRadios();
    } else if (optionsContainer) {
        optionsContainer.style.display = 'none';
    }
}

function selectSpecialDay(day) {
    // Toggle: if clicking the same day, deselect it
    if (selectedSpecialDay === day) {
        selectedSpecialDay = null;
    } else {
        selectedSpecialDay = day;
        if (day === "Dom" && weekSpecialDays[day] === "sunday_like") {
            weekSpecialDays[day] = SPECIAL_DAY_DEFAULT;
        }
    }
    renderSpecialDayChips();
}

function setSpecialDayMode(mode) {
    if (!selectedSpecialDay) return;
    if (selectedSpecialDay === "Dom" && mode === "sunday_like") return;

    weekSpecialDays[selectedSpecialDay] = mode;
    
    // Refresh validation if needed
    if (currentGeneratedSchedule && isValidationOn) {
        refreshScheduleValidationRules(currentMetadata?.special_days || getSpecialDaysPayload())
            .then(() => applyValidationUI())
            .catch(err => console.error("Error refreshing validation:", err));
    }
    
    // Re-render chips to show state
    renderSpecialDayChips();
}

// ===== END NEW SPECIAL DAYS =====

function renderWeekSpecialDays() {
    const section = document.getElementById("weekSpecialDaysSection");
    const grid = document.getElementById("weekSpecialDaysGrid");
    const startInput = document.getElementById("weekStartDate");
    if (!section || !grid) return;

    // Always show the section - allow setting special days without a specific week date
    section.style.display = "block";
    grid.innerHTML = "";

    weekSpecialDays = normalizeSpecialDaysState(weekSpecialDays);
    const normalized = weekSpecialDays;

    // Check if we have a valid week date for displaying dates
    const hasWeekDate = startInput && startInput.value;

    DAYS.forEach(day => {
        const wrapper = document.createElement("div");
        wrapper.style.display = "grid";
        wrapper.style.gap = "0.45rem";
        wrapper.style.padding = "0.7rem";
        wrapper.style.border = "1px solid var(--border)";
        wrapper.style.borderRadius = "10px";
        wrapper.style.background = "var(--bg-app)";

        // Show date only if weekStartDate is set, otherwise just show day name
        const dayDateDisplay = hasWeekDate ? formatSpecialDayDate(day) : '(configure fecha de semana para ver fecha)';
        
        const label = document.createElement("div");
        label.innerHTML = `
            <strong style="font-size:0.85rem;">${day}</strong>
            <span style="font-size:0.78rem; color:var(--text-muted); margin-left:0.35rem;">${dayDateDisplay}</span>
        `;

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
            if (event.target.value !== weekSpecialDays[day]) {
                renderWeekSpecialDays();
                return;
            }
            if (currentGeneratedSchedule && isValidationOn) {
                try {
                    await refreshScheduleValidationRules(currentMetadata?.special_days || getSpecialDaysPayload());
                    applyValidationUI();
                } catch (err) {
                    console.error("Error refreshing validation rules:", err);
                }
            }
        };

        wrapper.appendChild(label);
        wrapper.appendChild(select);
        grid.appendChild(wrapper);
    });
    
    // Also render the new chips UI if available
    if (document.getElementById('specialDaysChips')) {
        renderSpecialDayChips();
    }
}

// OVERLAY NAVIGATION
function openOverlay(id) {
    // Close others
    document.querySelectorAll('.section-overlay').forEach(el => el.classList.add('hidden'));

    const overlay = document.getElementById(id);
    if (overlay) {
        overlay.classList.remove('hidden');
        if (id === 'overlay-history') {
            loadHistory();
            loadFolders();
            updateSidebarActive('nav-history');
        } else if (id === 'overlay-employees') {
            updateSidebarActive('nav-employees');
        }
    }
}

function closeAllOverlays() {
    document.querySelectorAll('.section-overlay').forEach(el => el.classList.add('hidden'));
    // Resetear visibilidad de items del historial
    document.querySelectorAll('.history-item').forEach(i => {
        i.style.display = '';
    });
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

    // Global UI Handlers
    window.setGender = function (val, btn) {
        document.getElementById("empGender").value = val;
        document.querySelectorAll(".gender-pill").forEach(p => p.classList.remove("active"));
        btn.classList.add("active");
    };

    // Select for Night config -> now Simple Pills
    const select = document.getElementById("nightPersonSelect");
    const container = document.getElementById("nightPersonPills");
    const currentVal = config.fixed_night_person || select.value || "";
    container.innerHTML = "";

    let foundSelection = false;
    employees.forEach((emp, index) => {
        // Excluir personas marcadas como "no incluir en horarios" del selector de
        // turno noche (a menos que sean la selección actual, para no perder la referencia).
        const includedInHorario = emp.incluir_en_horario !== false && emp.incluir_en_horario !== 0;
        if (!includedInHorario && emp.name !== currentVal) return;
        // Only show employees who can do night OR are already selected
        if (!emp.can_do_night && emp.name !== currentVal && emp.activo !== false) return;
        
        const pill = document.createElement("div");
        const isSelected = emp.name === currentVal;
        const isInactive = emp.activo === false;
        
        if (isSelected) foundSelection = true;
        
        pill.className = "night-pill-item";
        pill.style.cssText = `
            padding: 0.5rem 1rem;
            border-radius: 20px;
            border: 2px solid ${isSelected ? 'var(--primary)' : 'var(--border-color)'};
            background: ${isSelected ? 'rgba(99, 102, 241, 0.15)' : 'var(--surface-2)'};
            color: ${isSelected ? 'var(--primary)' : 'var(--text-main)'};
            cursor: pointer;
            font-size: 0.85rem;
            font-weight: 500;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 0.4rem;
            opacity: ${isInactive ? '0.5' : '1'};
        `;
        
        if (!isInactive) {
            pill.onmouseenter = () => {
                pill.style.borderColor = 'var(--primary)';
                pill.style.transform = 'scale(1.05)';
            };
            pill.onmouseleave = () => {
                if (!isSelected) {
                    pill.style.borderColor = 'var(--border-color)';
                    pill.style.transform = 'scale(1)';
                }
            };
            pill.onclick = () => {
                // Deselect all
                Array.from(container.children).forEach(c => {
                    c.style.borderColor = 'var(--border-color)';
                    c.style.background = 'var(--surface-2)';
                    c.style.color = 'var(--text-main)';
                    // Reset the circle too
                    const circle = c.querySelector('.night-initials');
                    if (circle) {
                        circle.style.background = 'var(--border-color)';
                        circle.style.color = 'var(--text-muted)';
                    }
                });
                // Select this
                pill.style.borderColor = 'var(--primary)';
                pill.style.background = 'rgba(99, 102, 241, 0.15)';
                pill.style.color = 'var(--primary)';
                const circle = pill.querySelector('.night-initials');
                if (circle) {
                    circle.style.background = 'var(--primary)';
                    circle.style.color = 'white';
                }
                select.value = emp.name;
                updateConfig();
            };
        }
        
        // Get initials
        const names = emp.name.split(' ');
        const initials = names.length > 1 
            ? names[0][0] + names[names.length - 1][0] 
            : names[0].substring(0, 2);
        
        const canDoNightBadge = emp.can_do_night ? '' : '<span style="background: #fef3c7; color: #f59e0b; padding: 2px 6px; border-radius: 4px; font-size: 0.65rem; margin-left: 4px;">Sin noche</span>';
        
        pill.innerHTML = `
            <span class="night-initials" style="
                width: 24px; 
                height: 24px; 
                border-radius: 50%; 
                background: ${isSelected ? 'var(--primary)' : 'var(--border-color)'};
                color: ${isSelected ? 'white' : 'var(--text-muted)'};
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 0.7rem;
                font-weight: 700;
            ">${initials}</span>
            <span style="flex: 1;">${emp.name}</span>
            ${canDoNightBadge}
        `;
        
        container.appendChild(pill);
    });
    
    // Show hint if no one can do night
    if (container.children.length === 0) {
        container.innerHTML = '<p style="color: var(--text-muted); font-size: 0.8rem; width: 100%; text-align: center; padding: 0.5rem;"><i class="fa-solid fa-triangle-exclamation"></i> Ningún empleado puede hacer turno de noche</p>';
    }

    // Update hidden select and ensure visual selection
    select.value = currentVal;
    if (currentVal && !foundSelection) {
        // Selected person can't do night, show warning
        console.log("Advertencia: La persona seleccionada no puede hacer turno de noche");
    }
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
    if (refuerzoTypeSel) refuerzoTypeSel.value = config.refuerzo_type || "personalizado";

    const refuerzoStartInput = document.getElementById("refuerzoStartTime");
    if (refuerzoStartInput) refuerzoStartInput.value = config.refuerzo_start || "07:00";

    const refuerzoEndInput = document.getElementById("refuerzoEndTime");
    if (refuerzoEndInput) refuerzoEndInput.value = config.refuerzo_end || "12:00";

    // Refuerzo days mode (auto/manual)
    const refuerzoDaysModeSel = document.getElementById("refuerzoDaysMode");
    if (refuerzoDaysModeSel) refuerzoDaysModeSel.value = config.refuerzo_days_mode || "auto";
    
    // Cargar días manuales seleccionados
    const manualDays = config.refuerzo_manual_days || [];
    const dayCheckboxes = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
    dayCheckboxes.forEach(day => {
        const cb = document.getElementById("refuerzoDay" + day);
        if (cb) cb.checked = manualDays.includes(day);
    });
    
    toggleRefuerzoConfig();
    toggleRefuerzoDaysConfig();;

    // Collision Q-shift Config
    const collisionCb = document.getElementById("allowCollisionQuebrado");
    if (collisionCb) collisionCb.checked = config.allow_collision_quebrado || false;

    const collisionPrioritySel = document.getElementById("collisionPeakPriority");
    if (collisionPrioritySel) collisionPrioritySel.value = config.collision_peak_priority || "pm";

    const historyCb = document.getElementById("useHistoryContext");
    if (historyCb) historyCb.checked = config.use_history !== false;

    toggleCollisionConfig();

    // Alternating pairs
    const altAutoMode = config.alternating_pairs === null || config.alternating_pairs === undefined;
    const altAutoToggle = document.getElementById("alternatingAutoMode");
    if (altAutoToggle) {
        altAutoToggle.checked = altAutoMode;
        const altPairsContainer = document.getElementById("alternatingPairsContainer");
        if (altPairsContainer) {
            if (altAutoMode) altPairsContainer.classList.add("hidden");
            else altPairsContainer.classList.remove("hidden");
        }
        renderAlternatingPairs();
    }

    // Rotation enabled
    const rotCb = document.getElementById("rotationEnabled");
    if (rotCb) rotCb.checked = config.rotation_enabled !== false;

    // Strict weekly alternation
    const strictWeeklyCb = document.getElementById("strictWeeklyAlternation");
    if (strictWeeklyCb) strictWeeklyCb.checked = config.strict_weekly_alternation || false;

    // Cleaning tasks config
    const ctDays = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
    const ctTasks = ["am_banos", "pm_banos", "am_tanques", "pm_tanques", "oficina", "calibracion", "canos", "canos_glp"];
    const cleaningTasks = config.cleaning_tasks || {};
    ctDays.forEach(d => {
        const dayConfig = cleaningTasks[d] || {};
        ctTasks.forEach(t => {
            const cb = document.getElementById(`clean_${t}_${d}`);
            if (cb) {
                if (cleaningTasks[d] && typeof dayConfig[t] === "boolean") {
                    cb.checked = dayConfig[t];
                } else {
                    // Defaults as requested
                    if (d === "Dom" && (t === "am_tanques" || t === "pm_tanques")) {
                        cb.checked = false;
                    } else if (d === "Sáb" && t === "pm_tanques") {
                        cb.checked = false;
                    } else if (t === "calibracion") {
                        cb.checked = d === "Mar";
                    } else if (t === "canos") {
                        cb.checked = d === "Lun";
                    } else if (t === "canos_glp") {
                        cb.checked = d === "Jue";
                    } else if (t === "oficina") {
                        cb.checked = d === "Lun" || d === "Jue";
                    } else {
                        cb.checked = true;
                    }
                }
            }
        });
    });

    // Jefe config
    const jc = config.jefe_config || {};
    document.getElementById("jefeEnabled").checked = jc.enabled ?? false;
    document.getElementById("jefeExcludeRegular").checked = jc.exclude_regular ?? true;
    // Render 6×7 matrix
    let jefeAssignment = jc.assignment;
    if (!jefeAssignment || Object.keys(jefeAssignment).length === 0) {
        // First load — read defaults from HTML jefe-cell-active classes
        jefeAssignment = {};
        document.querySelectorAll('.jefe-cell.jefe-cell-active').forEach(cell => {
            const task = cell.dataset.task;
            const day = cell.dataset.day;
            if (!task || !day) return;
            if (!jefeAssignment[task]) jefeAssignment[task] = {};
            jefeAssignment[task][day] = true;
        });
    }
    document.querySelectorAll('.jefe-cell').forEach(cell => {
        const task = cell.dataset.task;
        const day = cell.dataset.day;
        const valueSpan = cell.querySelector('.jefe-cell-value');
        if (!task || !day || !valueSpan) return;
        const isJefe = jefeAssignment[task]?.[day] === true;
        cell.classList.toggle('jefe-cell-active', isJefe);
        valueSpan.textContent = isJefe ? 'Jefe' : '—';
    });
    toggleJefeConfig();

    fillJefeBaseShiftSelectFromRules();
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
    const customContainer = document.getElementById("refuerzoCustomTimeContainer");
    const refuerzoType = document.getElementById("refuerzoTypeSelect")?.value || "personalizado";
    if (container) {
        if (isChecked) container.classList.remove("hidden");
        else container.classList.add("hidden");
    }
    if (customContainer) {
        if (isChecked && refuerzoType === "personalizado") customContainer.classList.remove("hidden");
        else customContainer.classList.add("hidden");
    }
    updateConfig();
}

// Toggle para mostrar/ocultar la sección de días manuales del refuerzo
function toggleRefuerzoDaysConfig() {
    const daysMode = document.getElementById("refuerzoDaysMode")?.value || "auto";
    const manualDaysContainer = document.getElementById("refuerzoManualDaysContainer");
    if (manualDaysContainer) {
        if (daysMode === "manual") {
            manualDaysContainer.classList.remove("hidden");
        } else {
            manualDaysContainer.classList.add("hidden");
        }
    }
}

function toggleJefeConfig() {
    const enabled = document.getElementById("jefeEnabled")?.checked;
    const body = document.getElementById("jefeConfigBody");
    if (body) {
        if (enabled) body.classList.remove("hidden");
        else body.classList.add("hidden");
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

function toggleAlternatingMode() {
    const isAuto = document.getElementById("alternatingAutoMode")?.checked;
    const container = document.getElementById("alternatingPairsContainer");
    if (!container) return;
    if (isAuto) {
        container.classList.add("hidden");
        config.alternating_pairs = null;
    } else {
        container.classList.remove("hidden");
        if (!Array.isArray(config.alternating_pairs)) config.alternating_pairs = [];
        renderAlternatingPairs();
    }
    updateConfig();
}

function renderAlternatingPairs() {
    const list = document.getElementById("alternatingPairsList");
    if (!list) return;
    const pairs = Array.isArray(config.alternating_pairs) ? config.alternating_pairs : [];
    if (pairs.length === 0) {
        list.innerHTML = '<p class="helper-text-sm" style="text-align:center; padding:0.4rem 0; color:var(--text-muted);">Sin pares configurados</p>';
        return;
    }
    list.innerHTML = pairs.map((pair, idx) => {
        const [e1, e2] = pair.employees || ["", ""];
        const opts1 = employees.map(e => `<option value="${e.name}" ${e.name === e1 ? 'selected' : ''}>${e.name}</option>`).join('');
        const opts2 = employees.map(e => `<option value="${e.name}" ${e.name === e2 ? 'selected' : ''}>${e.name}</option>`).join('');
        return `<div style="display:flex; gap:0.4rem; align-items:center; margin-bottom:0.5rem;">
            <select onchange="updateAlternatingPair(${idx}, 0, this.value)" style="flex:1; padding:0.35rem 0.5rem; border-radius:6px; border:1px solid var(--border-color); background:var(--surface-2); color:var(--text-main); font-size:0.8rem;">
                <option value="">Empleado 1</option>${opts1}
            </select>
            <i class="fa-solid fa-right-left" style="color:var(--text-muted); font-size:0.72rem; flex-shrink:0;"></i>
            <select onchange="updateAlternatingPair(${idx}, 1, this.value)" style="flex:1; padding:0.35rem 0.5rem; border-radius:6px; border:1px solid var(--border-color); background:var(--surface-2); color:var(--text-main); font-size:0.8rem;">
                <option value="">Empleado 2</option>${opts2}
            </select>
            <button onclick="removeAlternatingPair(${idx})" style="background:rgba(239,68,68,0.1); color:#ef4444; border:none; border-radius:6px; width:26px; height:26px; cursor:pointer; flex-shrink:0; display:flex; align-items:center; justify-content:center;" title="Quitar par">
                <i class="fa-solid fa-xmark" style="font-size:0.68rem;"></i>
            </button>
        </div>`;
    }).join('');
}

function addAlternatingPair() {
    if (!Array.isArray(config.alternating_pairs)) config.alternating_pairs = [];
    config.alternating_pairs.push({ employees: ["", ""] });
    renderAlternatingPairs();
}

function removeAlternatingPair(idx) {
    if (!Array.isArray(config.alternating_pairs)) return;
    config.alternating_pairs.splice(idx, 1);
    renderAlternatingPairs();
    updateConfig();
}

function updateAlternatingPair(idx, pos, value) {
    if (!Array.isArray(config.alternating_pairs)) return;
    if (!config.alternating_pairs[idx]) return;
    if (!config.alternating_pairs[idx].employees) config.alternating_pairs[idx].employees = ["", ""];
    config.alternating_pairs[idx].employees[pos] = value;
    updateConfig();
}


async function updateConfig() {
    const mode = document.getElementById("nightModeConfig").value;
    const person = document.getElementById("nightPersonSelect").value;
    const allowLong = document.getElementById("allowLongShifts").checked;
    const useRefuerzo = document.getElementById("useRefuerzo")?.checked || false;
    const refuerzoType = document.getElementById("refuerzoTypeSelect")?.value || "personalizado";
    const refuerzoStart = document.getElementById("refuerzoStartTime")?.value || "07:00";
    const refuerzoEnd = document.getElementById("refuerzoEndTime")?.value || "12:00";

    config.night_mode = mode;
    config.fixed_night_person = person;
    config.allow_long_shifts = allowLong;
    config.use_refuerzo = useRefuerzo;
    config.refuerzo_type = refuerzoType;
    config.refuerzo_start = refuerzoStart;
    config.refuerzo_end = refuerzoEnd;
    config.allow_collision_quebrado = document.getElementById("allowCollisionQuebrado")?.checked || false;
    config.collision_peak_priority = document.getElementById("collisionPeakPriority")?.value || "pm";
    config.use_history = document.getElementById("useHistoryContext")?.checked ?? true;
    config.rotation_enabled = document.getElementById("rotationEnabled")?.checked ?? true;

    config.cleaning_tasks = {};
    const ctDays = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
    const ctTasks = ["am_banos", "pm_banos", "am_tanques", "pm_tanques", "oficina", "calibracion", "canos", "canos_glp"];
    ctDays.forEach(d => {
        config.cleaning_tasks[d] = {};
        ctTasks.forEach(t => {
            const cb = document.getElementById(`clean_${t}_${d}`);
            if (cb) {
                config.cleaning_tasks[d][t] = cb.checked;
            }
        });
    });

    // Jefe config
    config.jefe_config = {
        enabled: document.getElementById("jefeEnabled").checked,
        exclude_regular: document.getElementById("jefeExcludeRegular").checked,
        assignment: {}
    };
    document.querySelectorAll('.jefe-cell').forEach(cell => {
        const task = cell.dataset.task;
        const day = cell.dataset.day;
        if (!task || !day) return;
        if (!config.jefe_config.assignment[task]) config.jefe_config.assignment[task] = {};
        config.jefe_config.assignment[task][day] = cell.classList.contains('jefe-cell-active');
    });

    const jefeBaseSel = document.getElementById("jefeBaseShiftSelect");
    if (jefeBaseSel && jefeBaseSel.value) {
        config.jefe_base_shift = jefeBaseSel.value;
    }

    const customContainer = document.getElementById("refuerzoCustomTimeContainer");
    if (customContainer) {
        if (useRefuerzo && refuerzoType === "personalizado") customContainer.classList.remove("hidden");
        else customContainer.classList.add("hidden");
    }

    await fetch(`${API_URL}/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
    });

    try {
        await refreshBaseValidationRules();
        if (currentGeneratedSchedule && isValidationOn) {
            await refreshScheduleValidationRules(currentMetadata?.special_days || getSpecialDaysPayload());
            applyValidationUI();
        }
    } catch (e) {
        console.error("Error refreshing validation rules:", e);
    }
}

// MODALS (unificado con #planillaEmpModal / openUnifiedEmpModal en planillas_ui.js)
function openAddModal() {
    if (typeof openUnifiedEmpModal === "function") {
        openUnifiedEmpModal(null);
        return;
    }
    console.warn("openUnifiedEmpModal no está disponible");
}

function _horariosEmpToPlanillaShape(emp) {
    if (!emp) return null;
    return {
        id: emp.id,
        nombre: emp.name,
        genero: emp.gender || "M",
        cedula: emp.cedula || "",
        telefono: emp.telefono || "",
        correo: emp.correo || "",
        tipo_pago: emp.tipo_pago || "tarjeta",
        fecha_inicio: emp.fecha_inicio || "",
        salario_fijo: emp.salario_fijo,
        aplica_seguro: emp.aplica_seguro !== undefined ? emp.aplica_seguro : 1,
        puede_nocturno: emp.can_do_night ? 1 : 0,
        forced_libres: emp.forced_libres ? 1 : 0,
        forced_quebrado: emp.forced_quebrado ? 1 : 0,
        allow_no_rest: emp.allow_no_rest ? 1 : 0,
        es_jefe_pista: sqlIntFlagOn(emp.is_jefe_pista) ? 1 : 0,
        es_practicante: emp.is_practicante ? 1 : 0,
        strict_preferences: emp.strict_preferences ? 1 : 0,
        activo: emp.activo !== false ? 1 : 0,
        turnos_fijos: JSON.stringify(emp.fixed_shifts || {}),
    };
}

function openEditModal(index) {
    const emp = employees[index];
    if (typeof openUnifiedEmpModal === "function") {
        openUnifiedEmpModal(_horariosEmpToPlanillaShape(emp));
        return;
    }
    console.warn("openUnifiedEmpModal no está disponible");
}

function getJefeBaseSelection(fixed = {}, isJefe = false) {
    if (!isJefe) {
        return "J_06-16";
    }

    const weekdays = ["Lun", "Mar", "Mié", "Jue", "Vie"];
    const weekdayValues = weekdays
        .map(day => fixed?.[day])
        .filter(value => typeof value === "string" && value.length > 0);

    if (weekdayValues.length === 0) {
        return "J_06-16";
    }

    const uniqueValues = [...new Set(weekdayValues)];
    if (uniqueValues.length === 1 && uniqueValues[0].startsWith("J_")) {
        return uniqueValues[0];
    }

    return "CUSTOM";
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
    const rules = baseValidationRules || validationRules;
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

    if (!rules || !rules.shift_sets) return groups;

    const SKIP = new Set(["OFF", "VAC", "PERM", "N_22-05"]);

    const allowedForDay = Array.isArray(rules?.day_allowed_shifts?.[day])
        ? new Set(rules.day_allowed_shifts[day])
        : null;

    // Helper: get the start hour from SHIFTS set
    const startOf = (code) => {
        const hrs = rules.shift_sets[code];
        if (!hrs || hrs.length === 0) return 99;
        return Math.min(...hrs);
    };

    // Classify each shift
    const allCodes = Object.keys(rules.shift_sets).sort((a, b) => {
        return startOf(a) - startOf(b) || a.localeCompare(b);
    });

    for (const code of allCodes) {
        if (SKIP.has(code)) continue;

        if (allowedForDay && !allowedForDay.has(code)) {
            continue;
        }

        const hrs = rules.shift_sets[code] || [];
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

window.buildPillGroupsForDay = buildPillGroups;

function fillJefeBaseShiftSelectFromRules() {
    const sel = document.getElementById("jefeBaseShiftSelect");
    if (!sel) return;
    const cur = config && config.jefe_base_shift ? config.jefe_base_shift : "J_06-16";
    const codes = new Set(["J_06-16", "T1_05-13", "T2_06-14", "T3_07-15", "T4_08-16", "PM"]);
    if (typeof buildPillGroups === "function") {
        try {
            const g = buildPillGroups("Lun");
            (g.jefe || []).forEach((x) => codes.add(x.code));
            (g.morning || []).forEach((x) => codes.add(x.code));
        } catch (e) {
            /* validation rules may not be ready */
        }
    }
    const sorted = [...codes].sort((a, b) => a.localeCompare(b, "es"));
    const lab = typeof formatGeneratorShiftLabel === "function" ? formatGeneratorShiftLabel : (x) => x;
    sel.innerHTML = sorted
        .map(
            (c) =>
                `<option value="${c.replace(/"/g, "&quot;")}">${String(lab(c))
                    .replace(/&/g, "&amp;")
                    .replace(/</g, "&lt;")
                    .replace(/"/g, "&quot;")}</option>`
        )
        .join("");
    const pick = sorted.includes(cur) ? cur : sorted[0] || "J_06-16";
    sel.value = pick;
    if (config) config.jefe_base_shift = pick;
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

/** Etiqueta legible para panel generador / selects (evita mostrar códigos como J_06-16). */
function _hour24ToAmPm(h) {
    h = ((Math.round(Number(h)) % 24) + 24) % 24;
    const am = h < 12;
    const h12 = h % 12 === 0 ? 12 : h % 12;
    return `${h12}${am ? "am" : "pm"}`;
}

function formatGeneratorShiftLabel(code) {
    if (!code || code === "AUTO") return "Auto";
    const c = String(code).trim();
    const std = STANDARD_SHIFTS.find((s) => s.name === c);
    if (std && std.hours) {
        return std.hours.replace(/-/g, " – ");
    }
    if (c === "PERM") return "Permiso";
    const rules = typeof baseValidationRules !== "undefined" ? baseValidationRules : validationRules;
    if (rules && rules.shift_sets && rules.shift_sets[c]) {
        const hrs = rules.shift_sets[c];
        if (Array.isArray(hrs) && hrs.length) {
            const lo = Math.min(...hrs);
            const hi = Math.max(...hrs);
            return `${_hour24ToAmPm(lo)} – ${_hour24ToAmPm(hi + 1)}`;
        }
    }
    const jm = c.match(/^J_(\d{1,2})-(\d{1,2})$/);
    if (jm) {
        return `${_hour24ToAmPm(parseInt(jm[1], 10))} – ${_hour24ToAmPm(parseInt(jm[2], 10))}`;
    }
    if (c.startsWith("N_")) {
        const stdN = STANDARD_SHIFTS.find((s) => s.name === "N_22-05");
        if (stdN) return stdN.hours.replace(/-/g, " – ");
    }
    const m = c.match(/(\d{2})-(\d{2})/);
    if (m) {
        return `${_hour24ToAmPm(parseInt(m[1], 10))} – ${_hour24ToAmPm(parseInt(m[2], 10))}`;
    }
    const info = getDayCardInfo(c);
    return info && info.label ? info.label : c;
}

window.formatGeneratorShiftLabel = formatGeneratorShiftLabel;

function _isPlantillaPillMode() {
    return window.__pillEditorMode === "plantilla";
}

function buildDayCards() {
    const isPpt = _isPlantillaPillMode();
    const gridId = isPpt ? "pptDayCardsGrid" : "dayCardsGrid";
    const grid = document.getElementById(gridId);
    const root = isPpt ? document.getElementById("prefPlantillaModal") : document.getElementById("planillaEmpModal");
    if (!grid || !root) return;
    grid.innerHTML = "";

    const selQ = isPpt ? ".ppt-shift-select" : ".shift-select";

    DAYS.forEach(d => {
        const sel = root.querySelector(`${selQ}[data-day="${d}"]`);
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
    const isPpt = _isPlantillaPillMode();
    const panel = document.getElementById(isPpt ? "pptPillSelectorPanel" : "pillSelectorPanel");
    const dayEl = document.getElementById(isPpt ? "pptPanelDay" : "pillPanelDay");
    if (dayEl) dayEl.textContent = day;

    const root = isPpt ? document.getElementById("prefPlantillaModal") : document.getElementById("planillaEmpModal");
    if (root) {
        root.querySelectorAll(".day-card").forEach(c => c.classList.remove("dc-active"));
    }
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
    if (jefeWrap) {
        if (isJefe) {
            jefeWrap.style.display = "flex";
            fillPillGroup(isPpt ? "pptPillGroupJefe" : "pillGroupJefe", PILL_GROUPS.jefe, current);
        } else {
            jefeWrap.style.display = "none";
        }
    }

    if (panel) {
        panel.classList.remove("hidden");
        panel.style.animation = "slideDown 0.25s ease-out";
    }
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

    const isPpt = _isPlantillaPillMode();
    const root = isPpt ? document.getElementById("prefPlantillaModal") : document.getElementById("planillaEmpModal");
    const selQ = isPpt ? ".ppt-shift-select" : ".shift-select";
    const sel = root ? root.querySelector(`${selQ}[data-day="${activePillDay}"]`) : null;
    if (sel) sel.value = code;

    if (!isPpt) syncVacationCheckboxesFromDropdowns();

    buildDayCards();
    closePillPanel();
}

function closePillPanel() {
    const isPpt = _isPlantillaPillMode();
    const panel = document.getElementById(isPpt ? "pptPillSelectorPanel" : "pillSelectorPanel");
    if (panel) panel.classList.add("hidden");
    activePillDay = null;
    const root = isPpt ? document.getElementById("prefPlantillaModal") : document.getElementById("planillaEmpModal");
    if (root) root.querySelectorAll(".day-card").forEach(c => c.classList.remove("dc-active"));
}

function syncDayCardsFromSelects() {
    buildDayCards();
}

async function saveEmployee() {
    const idxEl = document.getElementById("editingIndex");
    const nameEl = document.getElementById("empName");
    if (!idxEl || !nameEl) return;
    const index = parseInt(idxEl.value);
    const name = nameEl.value;
    if (!name) return alert("Nombre requerido");

    const genderEl = document.getElementById("empGender");
    const gender = genderEl ? genderEl.value : "M";

    const jefeEl = document.getElementById("empJefePista");
    const isJefe = jefeEl ? jefeEl.checked : false;

    const empData = {
        name: name,
        gender: gender,
        can_do_night: gender === "M",  // Auto: male can, female cannot
        is_jefe_pista: isJefe,
        is_practicante: document.getElementById("empPracticante")?.checked ?? false,
        forced_libres: document.getElementById("empForcedLibres")?.checked ?? false,
        forced_quebrado: document.getElementById("empForcedQuebrado")?.checked ?? false,
        allow_no_rest: document.getElementById("empNoRest")?.checked ?? false,
        strict_preferences: document.getElementById("empStrictPreferences")?.checked ?? false,
        activo: document.getElementById("empActiveStatus") ? document.getElementById("empActiveStatus").checked : true,
        incluir_en_horario: document.getElementById("empIncluirEnHorario") ? document.getElementById("empIncluirEnHorario").checked : true,
        fixed_shifts: {},
    };

    const jefeShiftSel = document.getElementById("jefeShiftSelect");
    const selectedJefeShift = jefeShiftSel ? jefeShiftSel.value : "CUSTOM";
    const isNewEmployee = index === -1;
    const weekdays = ["Lun", "Mar", "Mié", "Jue", "Vie"];

    document.querySelectorAll("#planillaEmpModal .shift-select").forEach((sel) => {
        const day = sel.getAttribute("data-day");
        let val = sel.value;

        // Auto-assign chosen Jefe shift ONLY to empty weekdays
        // This stops UI from blocking/overwriting customized shifts like Friday
        if (isJefe && weekdays.includes(day) && val === "AUTO" && isNewEmployee && selectedJefeShift !== "CUSTOM") {
            val = selectedJefeShift;
        }

        // Auto-assign Jefe de Pista Saturday (T1_05-13) and Sunday (OFF) ONLY if AUTO
        if (isJefe && day === "Sáb" && val === "AUTO" && isNewEmployee) {
            val = "T1_05-13";
        }
        if (isJefe && day === "Dom" && val === "AUTO" && isNewEmployee) {
            val = "OFF";
        }

        if (val !== "AUTO") {
            empData.fixed_shifts[day] = val;
        }
    });

    if (index === -1) {
        // Nuevo empleado — enviar solo este empleado en el array
        employees.push(empData);
        await fetch(`${API_URL}/employees`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify([empData])
        });
    } else {
        // Empleado existente — usar PUT individual para no tocar a los demás
        const originalName = employees[index].name;
        employees[index] = empData;
        await fetch(`${API_URL}/employees/${encodeURIComponent(originalName)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(empData)
        });
    }

    closeModal();
    await loadEmployees();
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
    config.refuerzo_type = document.getElementById("refuerzoTypeSelect")?.value || "personalizado";
    config.refuerzo_start = document.getElementById("refuerzoStartTime")?.value || "07:00";
    config.refuerzo_end = document.getElementById("refuerzoEndTime")?.value || "12:00";
    
    // Refuerzo days mode (auto/manual)
    config.refuerzo_days_mode = document.getElementById("refuerzoDaysMode")?.value || "auto";
    if (config.refuerzo_days_mode === "manual") {
        // Recopilar días manuales seleccionados
        const selectedDays = [];
        const dayCheckboxes = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
        dayCheckboxes.forEach(day => {
            const cb = document.getElementById("refuerzoDay" + day);
            if (cb && cb.checked) selectedDays.push(day);
        });
        config.refuerzo_manual_days = selectedDays;
    } else {
        config.refuerzo_manual_days = [];
    }
    
    config.allow_collision_quebrado = document.getElementById("allowCollisionQuebrado")?.checked || false;
    config.collision_peak_priority = document.getElementById("collisionPeakPriority")?.value || "pm";
    config.use_history = document.getElementById("useHistoryContext")?.checked ?? true;
    config.rotation_enabled = document.getElementById("rotationEnabled")?.checked ?? true;
    config.strict_weekly_alternation = document.getElementById("strictWeeklyAlternation")?.checked ?? false;
    const specialDays = getSpecialDaysPayload();

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
            body: JSON.stringify({ employees, config, target_week_start: weekStart || null, special_days: specialDays })
        });
        const result = await res.json();

        if (result.status === "Success" || result.status === "Optimal" || result.status === "Feasible") {
            status.textContent = "Generado!";
            currentGeneratedSchedule = result.schedule;
            currentDailyTasks = result.daily_tasks; // Save tasks
            currentMetadata = result.metadata;
            // NO sobrescribir weekSpecialDays con el resultado del backend
            // El usuario configuró los special_days antes de generar, mantenerlos
            renderWeekSpecialDays();
            await refreshScheduleValidationRules(specialDays);

            renderSchedule(result.schedule, "#scheduleTable", result.daily_tasks);
            if (isValidationOn) applyValidationUI(); // apply validation immediately if enabled

            document.getElementById("btnSaveSchedule").classList.remove("hidden");
            const libresText = result.metadata?.libres_person ? `Libres: ${result.metadata.libres_person}` : "Éxito";
            const solutionsCount = result.metadata?.solutions_found ? ` | Óptimos procesados: ${result.metadata.solutions_found}` : "";
            const historyText = result.metadata?.history_context_label ? ` | ${result.metadata.history_context_label}` : "";
            let metaLine = libresText + solutionsCount + historyText;
            const mr = result.metadata?.min_rest_hours_applied;
            const mrT = result.metadata?.min_rest_hours_target ?? 12;
            if (mr != null) {
                metaLine +=
                    mr < mrT
                        ? ` | Descanso mínimo: ${mr}h (obj. ${mrT}h)`
                        : ` | Descanso mínimo: ${mr}h`;
            }
            document.getElementById("scheduleMeta").textContent = metaLine;
        } else {
            console.error("Solver Status:", result.status);
            currentMetadata = null;
            if (result.status === "Infeasible") {
                const infeasibleMessage = result.message || "No se encontró una solución factible con las restricciones actuales. Intenta relajar algunos turnos fijos.";
                status.innerHTML = '<span class="error"><i class="fa-solid fa-circle-xmark"></i> Infeasible</span>';
                document.getElementById("scheduleMeta").textContent = infeasibleMessage;
                alert(infeasibleMessage);
            } else {
                status.textContent = `Error: ${result.status}`;
                document.getElementById("scheduleMeta").textContent = result.message || "Error";
            }
        }

    } catch (e) {
        console.error("Generate Error:", e);
        status.textContent = "Error: " + e.message;
    }
}

function getShiftInfo(s) {
    const effectiveShift = normalizeFlexibleShiftInput(s) || s;
    if (!effectiveShift || effectiveShift === "OFF") return { class: "pill-off", icon: "fa-mug-hot", text: "LIBRE" };
    if (effectiveShift === "Q3_05-11+17-22") return { class: "pill-night", icon: "fa-bolt", text: "05-11 / 17-22" };

    // Determine Type
    let typeClass = "pill-morning"; // Default
    let icon = "fa-sun";

    if (effectiveShift === "VAC") return { class: "pill-vac", icon: "fa-plane", text: "VAC" };
    if (effectiveShift === "PERM") return { class: "pill-perm", icon: "fa-file-signature", text: "PERM" };

    // Morning/Day Logic (Corrected to User Request)
    // Morning (< 12): Yellow (pill-morning)
    // Afternoon (>= 12): Blue/Cyan (pill-afternoon)
    // Night (>= 20 or <= 4 or N_): Purple/Blue (pill-night)

    // Heuristic
    const match = typeof effectiveShift === "string" ? effectiveShift.match(/_(\d{1,2})/) : null;
    let startHour = 8;
    if (match) startHour = parseInt(match[1]);

    if (effectiveShift.includes("N_") || startHour >= 20 || startHour <= 4) {
        typeClass = "pill-night";
        icon = "fa-moon";
    } else if (startHour >= 12) {
        typeClass = "pill-afternoon";
        icon = "fa-cloud-sun";
    } else {
        typeClass = "pill-morning"; // Morning only
    }

    // Format Text
    let rangePart = effectiveShift.split('_').slice(1).join('_'); // 08-16
    if (!rangePart && effectiveShift.includes("-")) rangePart = effectiveShift;
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

function parseFlexibleTimeToken(token) {
    if (!token) return null;
    const compact = token
        .toString()
        .trim()
        .toLowerCase()
        .replace(/\./g, "")
        .replace(/\s+/g, "");

    if (!compact) return null;

    let match = compact.match(/^(\d{1,2})(?::(\d{2}))?(am|pm)$/);
    if (match) {
        let hour = parseInt(match[1], 10);
        const minutes = match[2] ? parseInt(match[2], 10) : 0;
        const suffix = match[3];
        if (Number.isNaN(hour) || Number.isNaN(minutes) || minutes !== 0 || hour < 1 || hour > 12) {
            return null;
        }
        if (suffix === "am") {
            if (hour === 12) hour = 0;
        } else if (hour !== 12) {
            hour += 12;
        }
        return hour;
    }

    match = compact.match(/^(\d{1,2})(?::(\d{2}))?$/);
    if (!match) return null;

    const hour = parseInt(match[1], 10);
    const minutes = match[2] ? parseInt(match[2], 10) : 0;
    if (Number.isNaN(hour) || Number.isNaN(minutes) || minutes !== 0 || hour < 0 || hour > 29) {
        return null;
    }
    return hour;
}

function splitFlexibleRangeSegment(segment) {
    const cleaned = (segment || "").trim().replace(/[–—]/g, "-");
    if (!cleaned) return null;

    let parts = cleaned.split(/\s*-\s*/);
    if (parts.length === 2) return parts;

    parts = cleaned.split(/\s+a\s+/i);
    if (parts.length === 2) return parts;

    parts = cleaned.split(/\s+to\s+/i);
    if (parts.length === 2) return parts;

    return null;
}

function normalizeFlexibleShiftInput(value) {
    if (value === null || value === undefined) return null;

    const raw = value.toString().trim();
    if (!raw) return null;

    const upper = raw.toUpperCase();
    if (["OFF", "LIBRE", "DESCANSO"].includes(upper)) return "OFF";
    if (["VAC", "VACACIONES"].includes(upper)) return "VAC";
    if (["PERM", "PERMISO"].includes(upper)) return "PERM";
    if (upper === "AUTO") return "AUTO";
    if (SHIFT_HOURS[upper] !== undefined) return upper;

    let candidate = raw;
    if (upper.startsWith(MANUAL_SHIFT_PREFIX)) {
        candidate = raw.slice(MANUAL_SHIFT_PREFIX.length);
    }

    const segments = candidate.split(/\s*(?:\+|\/|,)\s*/).filter(Boolean);
    if (!segments.length) return null;

    const normalizedSegments = [];
    for (const segment of segments) {
        const split = splitFlexibleRangeSegment(segment);
        if (!split) return null;

        const start = parseFlexibleTimeToken(split[0]);
        const end = parseFlexibleTimeToken(split[1]);
        if (start === null || end === null) return null;

        normalizedSegments.push(
            `${String(start).padStart(2, "0")}-${String(end).padStart(2, "0")}`
        );
    }

    return `${MANUAL_SHIFT_PREFIX}${normalizedSegments.join("+")}`;
}

function getShiftHoursList(shiftCode) {
    const normalized = normalizeFlexibleShiftInput(shiftCode) || shiftCode;
    const rules = validationRules || baseValidationRules;
    const knownHours = rules?.shift_sets?.[normalized];
    if (knownHours && knownHours.length) {
        return [...knownHours];
    }

    if (!normalized || typeof normalized !== "string" || !normalized.startsWith(MANUAL_SHIFT_PREFIX)) {
        return [];
    }

    const rangePart = normalized.slice(MANUAL_SHIFT_PREFIX.length);
    const hours = new Set();

    rangePart.split("+").forEach(segment => {
        const [startRaw, endRaw] = segment.split("-");
        const start = parseInt(startRaw, 10);
        let end = parseInt(endRaw, 10);
        if (Number.isNaN(start) || Number.isNaN(end)) return;
        if (end <= start) end += 24;
        for (let h = start; h < end; h++) {
            hours.add(h);
        }
    });

    return Array.from(hours).sort((a, b) => a - b);
}

function getShiftHoursCount(shiftCode) {
    if (SHIFT_HOURS[shiftCode] !== undefined) return SHIFT_HOURS[shiftCode];
    return getShiftHoursList(shiftCode).length;
}

function getShiftStartHour(shiftCode) {
    const normalized = normalizeFlexibleShiftInput(shiftCode) || shiftCode;
    const match = typeof normalized === "string" ? normalized.match(/_(\d{2})/) : null;
    if (match) return parseInt(match[1], 10);

    const hours = getShiftHoursList(shiftCode);
    return hours.length ? Math.min(...hours) : 24;
}

/** Fin del turno en escala 5–29 (hora exclusiva), alineado al motor Python. */
function getShiftEndExclusiveHour(shiftCode) {
    const hours = getShiftHoursList(shiftCode);
    if (!hours.length) return null;
    return Math.max(...hours) + 1;
}

/** Horas de descanso entre fin(s1) e inicio(s2) al día siguiente. */
function restHoursBetweenShiftsClient(s1, s2) {
    const non = ["OFF", "VAC", "PERM"];
    if (!s1 || !s2 || non.includes(s1) || non.includes(s2)) return null;
    const end1 = getShiftEndExclusiveHour(s1);
    const start2 = getShiftStartHour(s2);
    if (end1 == null || start2 == null) return null;
    return (start2 + 24) - end1;
}

/** Vista validación cuando no hay metadata del solver (p. ej. historial antiguo). */
function buildRestReportClient(schedule, targetHours = 12) {
    const per = {};
    const names = Object.keys(schedule || {});
    names.forEach((e) => {
        const gaps = [];
        let minG = null;
        for (let i = 0; i < DAYS.length - 1; i++) {
            const d1 = DAYS[i];
            const d2 = DAYS[i + 1];
            const a = schedule[e]?.[d1];
            const b = schedule[e]?.[d2];
            const h = restHoursBetweenShiftsClient(a, b);
            if (h == null) continue;
            gaps.push({
                from: d1,
                to: d2,
                hours: h,
                meets_target: h >= targetHours,
                meets_applied: h >= targetHours,
            });
            minG = minG === null ? h : Math.min(minG, h);
        }
        per[e] = {
            min_gap_hours: minG,
            gaps,
            meets_target: minG === null || minG >= targetHours,
            meets_applied: minG === null || minG >= targetHours,
        };
    });
    return { per_employee: per, target_hours: targetHours, applied_hours: targetHours, client_only: true };
}


let currentSortMode = 'time';
// Per-history-entry sort mode (independent from main schedule)
const historySortModes = new Map(); // historyIndex -> 'time' | 'alpha'


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
        sum += getShiftStartHour(s);
        count++;
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

function renderSchedule(
    schedule,
    tableSelector,
    tasks = {},
    specialDaysOverride = null,
    metadataHolidayDays = null,
    weekDatesOverride = null
) {
    const tableEl = document.querySelector(tableSelector);
    const thead = document.querySelector(`${tableSelector} thead tr`);
    const tbody = document.querySelector(`${tableSelector} tbody`);
    if (!tbody || !thead || !tableEl) return;

    tbody.innerHTML = "";
    thead.innerHTML = "";

    let keys = Object.keys(schedule);
    let isHistory = tableSelector.includes("hist");
    let historyIndex = isHistory ? parseInt(tableSelector.split("-").pop()) : null;
    const effectiveSortMode = isHistory
        ? (historySortModes.get(historyIndex) || 'time')
        : currentSortMode;

    if (effectiveSortMode === 'time') {
        keys.sort((a, b) => {
            const avgA = getAverageStartHour(a, schedule);
            const avgB = getAverageStartHour(b, schedule);
            if (Math.abs(avgA - avgB) < 0.01) return a.localeCompare(b);
            return avgA - avgB;
        });
    } else {
        keys.sort((a, b) => a.localeCompare(b, 'es', { sensitivity: 'base' }));
    }

    const verticalAliases = isHistory
        ? (historyEntriesCache[historyIndex]?.metadata?.display_aliases || {})
        : {};

    if (isVerticalView) {
        tableEl.classList.add("vertical-table");

        // --- VERTICAL (CALENDAR) HEADERS ---
        const weekDatesMapV = weekDatesOverride != null ? weekDatesOverride : getWeekDatesMap();
        const specialDaysV = specialDaysOverride ?? currentMetadata?.special_days ?? {};
        thead.innerHTML = `<th class="th-horario-col" style="width:120px; text-align:center;">Horario</th>`;
        DAYS.forEach(d => {
            const holiday = getHolidayForDay(d, weekDatesMapV, metadataHolidayDays);
            const isClosedV = specialDaysV[d] === 'closed';
            const closedBadgeV = isClosedV ? `<span class="th-day-head-badge-closed">CERRADO</span>` : '';
            const holidayIcon = holiday ? `<i class="fa-solid fa-star th-day-head-star" title="${escapeHtmlAttr(holiday.name)}"></i>` : '';
            const closedHdrClass = isClosedV ? " th-closed" : "";
            const holidayHdrClass = holiday ? " th-holiday" : "";
            // Clickeable para agregar feriados en historial
            const clickAction = isHistory ? `onclick="openHolidayDayModal('${d}', ${historyIndex})" style="cursor:pointer;"` : '';
            thead.innerHTML += `<th class="th-day-col${closedHdrClass}${holidayHdrClass}" style="min-width:140px;" ${clickAction} title="${isHistory ? 'Click para marcar como feriado' : ''}">
                <div class="th-day-col-inner" style="font-size:1.1rem; font-weight:800; color:var(--text-main);">
                    <span class="th-day-name">${d}</span>${closedBadgeV}${holidayIcon}
                </div>
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
                const holidayTd = getHolidayForDay(d, weekDatesMapV, metadataHolidayDays);
                const isClosedTd = specialDaysV[d] === "closed";
                const tdParts = [];
                if (isClosedTd) tdParts.push("closed-col");
                if (holidayTd) tdParts.push("holiday-col");
                const tdDayClass = tdParts.length ? ` ${tdParts.join(" ")}` : "";
                let cellHtml = `<td class="${tdDayClass.trim()}" style="vertical-align: top;">
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
                        const role = name === "Refuerzo" ? "REF" : (emp && sqlIntFlagOn(emp.is_jefe_pista) ? "JEFE" : (emp && emp.is_practicante ? "PRACT" : ""));
                        const nightBadge = emp && emp.can_do_night ? '<i class="fa-solid fa-moon" style="font-size:0.7em;"></i> ' : '';

                        let info = getShiftInfo(s); // To get colors
                        const closedOffCard = isHistory && isClosedTd && s === "OFF";

                        let tagHtml = role ? `<div style="font-size:0.6rem; opacity:0.8; margin-top:2px;">${role}</div>` : "";
                        
                        let taskData = {...(tasks || {})};
                        if (isHistory) {
                            taskData._is_history = true;
                            taskData._history_index = historyIndex;
                        }
                        let taskHtml = getTaskLabelHTML(taskData, name, d);
                        // El click en el shift-pill ahora abre el modal de turno + tarea
                        // Ya no necesitamos el placeholder de tarea vacía separado

                        let historyAttrs = "";
                        let cursorStyle = "";
                        if (isHistory) {
                            historyAttrs = `
                                data-history-index="${historyIndex}"
                                data-employee-name="${escapeHtmlAttr(name)}"
                                data-day="${escapeHtmlAttr(d)}"
                                onmousedown="beginHistorySelection(event, this)"
                                onmouseenter="extendHistorySelection(event, this)"
                                onclick="handleHistoryCellClick(event, this)"
                            `;
                            cursorStyle = "cursor:pointer; user-select:none;";
                        }

                        const pillClass = closedOffCard
                            ? `shift-pill pill-closed-establishment${isHistory ? " history-shift-pill" : ""}`
                            : `shift-pill ${info.class}${isHistory ? " history-shift-pill" : ""}`;

                        const verticalDisplayName = isHistory && verticalAliases[name] ? verticalAliases[name] : name;
                        cellHtml += `
                            <div class="${pillClass}" ${historyAttrs} style="min-height:auto; padding:0.4rem; flex-direction:row; justify-content:space-between; ${cursorStyle}">
                                <div style="display:flex; flex-direction:column; align-items:flex-start; text-align:left;">
                                    <span style="font-weight:700; font-size:0.9rem;">${nightBadge}${verticalDisplayName}</span>
                                    ${closedOffCard ? '<span class="pill-closed-inline-label">Cerrado</span>' : ""}
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

        // Determine active sort mode for icon feedback
        const activeSortMode = isHistory
            ? (historySortModes.get(historyIndex) || 'time')
            : currentSortMode;
        const sortIconClass = activeSortMode === 'time'
            ? 'fa-solid fa-clock sort-active-time'
            : 'fa-solid fa-sort-alpha-down sort-active-alpha';
        const sortTitle = activeSortMode === 'time'
            ? 'Ordenado por hora — click para ordenar A-Z'
            : 'Ordenado A-Z — click para ordenar por hora';

        const weekDatesMap = weekDatesOverride != null ? weekDatesOverride : getWeekDatesMap();
        const specialDays = specialDaysOverride ?? currentMetadata?.special_days ?? {};

        thead.innerHTML = `
            <th id="${isHistory ? `th-collaborator-hist-${historyIndex}` : 'th-collaborator'}" style="cursor:pointer; min-width:160px; user-select:none;" title="${sortTitle}">
                Empleado <i class="${sortIconClass}" style="font-size:0.75rem; margin-left:4px;"></i>
            </th>
            ${DAYS.map(d => {
                const holiday = getHolidayForDay(d, weekDatesMap, metadataHolidayDays);
                const isClosed = specialDays[d] === 'closed';
                const closedClass = isClosed ? ' th-closed' : '';
                const holidayClass = holiday ? ' th-holiday' : '';
                const closedBadge = isClosed ? `<span class="th-day-head-badge-closed">CERRADO</span>` : '';
                const holidayIcon = holiday ? `<i class="fa-solid fa-star th-day-head-star" title="${escapeHtmlAttr(holiday.name)}"></i>` : '';
                const clickAction = isHistory ? `onclick="openHolidayDayModal('${d}', ${isHistory ? historyIndex : -1})" style="cursor:pointer;"` : '';
                return `<th class="th-day-col${closedClass}${holidayClass}" ${clickAction} title="${isHistory ? 'Click para marcar como feriado' : ''}"><div class="th-day-col-inner"><span class="th-day-name">${d}</span>${closedBadge}${holidayIcon}</div></th>`;
            }).join('')}
            <th class="col-hours">Horas</th>
        `;

        // Setup sort listener
        const thCollab = thead.querySelector(`#${isHistory ? `th-collaborator-hist-${historyIndex}` : 'th-collaborator'}`);
        if (thCollab) {
            thCollab.addEventListener('click', () => {
                if (isHistory) {
                    const prev = historySortModes.get(historyIndex) || 'time';
                    historySortModes.set(historyIndex, prev === 'time' ? 'alpha' : 'time');
                    renderHistoryEntryTable(historyIndex);
                } else {
                    currentSortMode = currentSortMode === 'time' ? 'alpha' : 'time';
                    if (currentGeneratedSchedule) renderSchedule(currentGeneratedSchedule, '#scheduleTable', currentDailyTasks);
                }
            });
        }

        // --- HORIZONTAL BODY ---
        const historyAliases = isHistory
            ? (historyEntriesCache[historyIndex]?.metadata?.display_aliases || {})
            : {};
        keys.forEach(name => {
            const row = document.createElement("tr");

            const displayName = isHistory && historyAliases[name] ? historyAliases[name] : name;
            const aliasIndicator = isHistory && historyAliases[name] && historyAliases[name] !== name
                ? `<i class="fa-solid fa-link" style="font-size:0.65em; margin-left:4px; color:var(--text-muted);" title="Vinculado a ${escapeHtmlAttr(name)}"></i>`
                : '';
            const initials = name === "Refuerzo" ? "RF" : (displayName || name).substring(0, 2).toUpperCase();
            const emp = employees.find(e => e.name === name);
            const nightBadge = emp && emp.can_do_night ? '<i class="fa-solid fa-moon" style="font-size:0.7em; margin-left:4px; color:#6366f1;" title="Turno Noche"></i>' : '';
            const noRestBadge = emp && emp.allow_no_rest ? '<i class="fa-solid fa-battery-empty" style="font-size:0.7em; margin-left:4px; color:#ef4444;" title="Sin Descanso"></i>' : '';
            const forcedLibresBadge = emp && emp.forced_libres ? '<i class="fa-solid fa-thumbtack forced-libres-icon" title="Rol Libres Forzado"></i>' : '';
            const forcedQuebradoBadge = emp && emp.forced_quebrado ? '<i class="fa-solid fa-bolt" style="font-size:0.7em; margin-left:4px; color:#7c3aed;" title="Forzar Quebrado"></i>' : '';
            const refBadge = name === "Refuerzo" ? '<span class="tag night" style="font-size:0.6em; margin-left:4px;">REF</span>' : '';
            // Libres person badge for current week (from metadata)
            const libresPerson = currentMetadata?.libres_person || "";
            const libresWeekBadge = name === libresPerson
                ? '<span class="libres-week-badge" title="Persona de Libres esta semana">★ LIBRES</span>'
                : '';

            const nameJsLiteral = JSON.stringify(name).replace(/"/g, "&quot;");
            const nameClickAttrs = isHistory
                ? `class="emp-name hist-name-edit" onclick="openHistoryNameModal(${historyIndex}, ${nameJsLiteral})" title="Click para renombrar o vincular" style="cursor:pointer; text-decoration: underline dotted; text-underline-offset: 2px;"`
                : `class="emp-name"`;

            row.innerHTML = `
                <td>
                    <div class="emp-cell-content">
                        <div class="emp-avatar" style="${name === "Refuerzo" ? 'background: var(--accent-color);' : ''}">${initials}</div>
                        <div class="emp-details">
                            <span ${nameClickAttrs}>${displayName}${aliasIndicator} ${nightBadge} ${noRestBadge} ${forcedLibresBadge} ${forcedQuebradoBadge} ${libresWeekBadge} ${refBadge}</span>
                            <span class="emp-role">${name === "Refuerzo" ? 'Apoyo Extra' : (emp && sqlIntFlagOn(emp.is_jefe_pista) ? 'Jefe de Pista' : (emp && emp.is_practicante ? 'Practicante' : 'Colaborador'))}</span>
                        </div>
                    </div>
                </td>
            `;

            let totalHours = 0;

            DAYS.forEach(d => {
                const s = schedule[name][d] || "OFF";
                const info = getShiftInfo(s);

                totalHours += getShiftHoursCount(s);

                let fixedClass = "";
                if (emp && emp.fixed_shifts && emp.fixed_shifts[d]) fixedClass = "pill-fixed";

                const holiday = getHolidayForDay(d, weekDatesMap, metadataHolidayDays);
                const isClosedDay = specialDays[d] === 'closed';
                const cellParts = [];
                if (isClosedDay) cellParts.push('closed-col');
                if (holiday) cellParts.push('holiday-col');
                const cellClass = cellParts.length ? ` ${cellParts.join(' ')}` : '';

                let historyAttrs = "";
                let cursorStyle = "";
                if (isHistory) {
                    historyAttrs = `
                        data-history-index="${historyIndex}"
                        data-employee-name="${escapeHtmlAttr(name)}"
                        data-day="${escapeHtmlAttr(d)}"
                        onmousedown="beginHistorySelection(event, this)"
                        onmouseenter="extendHistorySelection(event, this)"
                        onclick="handleHistoryCellClick(event, this)"
                    `;
                    cursorStyle = "cursor:pointer; user-select:none;";
                }

                // Día cerrado + sin turno: tarjeta "Cerrado" (no LIBRE); en historial sigue siendo editable
                const showClosedEstablishmentPill = isClosedDay && s === "OFF";

                // Día cerrado en horario principal: tarjeta coherente con diseño (no editable)
                if (isClosedDay && !isHistory) {
                    row.innerHTML += `
                        <td class="${cellClass}">
                            <div class="shift-pill pill-closed-establishment" style="cursor:default;">
                                <i class="fa-solid fa-store-slash pill-icon"></i>
                                <span class="pill-time">Cerrado</span>
                                <span class="pill-closed-hint">Sin servicio</span>
                            </div>
                        </td>
                    `;
                } else if (showClosedEstablishmentPill && isHistory) {
                    row.innerHTML += `
                        <td class="${cellClass}">
                            <div class="shift-pill pill-closed-establishment ${fixedClass} history-shift-pill" ${historyAttrs} style="${cursorStyle}">
                                <i class="fa-solid fa-store-slash pill-icon"></i>
                                <span class="pill-time">Cerrado</span>
                                <span class="pill-closed-hint">Sin servicio</span>
                                ${getTaskLabelHTML(tasks, name, d)}
                            </div>
                        </td>
                    `;
                } else {
                    row.innerHTML += `
                        <td class="${cellClass}">
                            <div class="shift-pill ${info.class} ${fixedClass}${isHistory ? " history-shift-pill" : ""}" ${historyAttrs} style="${cursorStyle}">
                                <i class="fa-solid ${info.icon} pill-icon"></i>
                                <span class="pill-time">${info.text}</span>
                                ${getTaskLabelHTML(tasks, name, d)}
                            </div>
                        </td>
                    `;
                }
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
async function fetchHistoryEntries(forceRefresh = false) {
    if (!forceRefresh && historyEntriesCache.length) {
        return historyEntriesCache;
    }

    const res = await fetch('/api/history');
    if (!res.ok) {
        throw new Error(`API returned ${res.status}`);
    }

    let entries = await res.json();
    if (!Array.isArray(entries)) {
        entries = [];
    }

    // Más reciente primero; mismo timestamp → mayor db_id primero (varias filas con el mismo nombre).
    entries.sort((a, b) => {
        const tb = new Date(b.timestamp || 0).getTime();
        const ta = new Date(a.timestamp || 0).getTime();
        if (tb !== ta) return tb - ta;
        return (Number(b.db_id) || 0) - (Number(a.db_id) || 0);
    });
    
    historyEntriesCache = entries;
    return historyEntriesCache;
}

function renderHistoryEntryTable(index) {
    const entry = historyEntriesCache[index];
    if (!entry) return;
    const metadataHolidayDays = entry.metadata?.holiday_days || null;
    renderSchedule(
        entry.schedule,
        `#hist-table-${index}`,
        entry.daily_tasks || {},
        entry.special_days || {},
        metadataHolidayDays,
        entry.week_dates || null
    );
    applyHistoryHoursVisibility(index);
}

function applyHistoryHoursVisibility(index) {
    const table = document.getElementById(`hist-table-${index}`);
    if (!table) return;
    table.querySelectorAll(".col-hours").forEach(el => {
        el.classList.toggle("hidden-col", hiddenHistoryHours.has(index));
    });
}

function renderHistoryList() {
    const listContainer = document.getElementById('historyList');
    if (!listContainer) return;

    listContainer.innerHTML = "";

    if (!historyEntriesCache.length) {
        listContainer.innerHTML = '<div class="empty-msg">No hay historiales guardados</div>';
        return;
    }

    historyEntriesCache.forEach((h, i) => {
        const item = document.createElement("div");
        item.className = "history-item";
        item.dataset.historyIndex = String(i);
        if (expandedHistoryItems.has(i)) {
            item.classList.add("expanded");
        }

        const dateValue = h.timestamp ? new Date(h.timestamp) : new Date();
        const dateStr = dateValue.toLocaleDateString() + ' ' + dateValue.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        item.innerHTML = `
            <div class="history-header" onclick="toggleHistory(this)">
                <div class="h-info">
                    <i class="fa-solid fa-calendar-week"></i>
                    <span class="h-name">${h.name}</span>
                    <button type="button" class="btn-icon" onclick="renameHistory(${i}, event)" title="Renombrar" style="padding: 2px 6px;">
                        <i class="fa-solid fa-pen" style="font-size: 0.75rem;"></i>
                    </button>
                    <span class="h-date">${dateStr}</span>
                </div>
                <div class="h-actions">
                    <i class="fa-solid fa-chevron-down arrow"></i>
                    <button type="button" class="btn-icon delete" onclick="deleteHistory(${i}, event)">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </div>
            </div>
            <div class="history-body">
                <div class="history-body-toolbar">
                    <button type="button" class="btn-icon history-action-button" onclick="validateHistory(${i}, event)" title="Validar Historial">
                        <i class="fa-solid fa-shield-check"></i>
                        <span>Validar</span>
                    </button>
                    <button type="button" class="btn-icon history-action-button" onclick="reassignHistoryTasks(${i}, event)" title="Recalcular Limpieza">
                        <i class="fa-solid fa-broom"></i>
                        <span>Limpieza</span>
                    </button>
                    <button
                        type="button"
                        class="btn-icon history-action-button${hiddenHistoryHours.has(i) ? "" : " is-active"}"
                        data-history-hours-button="${i}"
                        onclick="toggleHistoryHours(${i}, event)"
                        title="Mostrar u ocultar horas"
                        aria-pressed="${hiddenHistoryHours.has(i) ? "false" : "true"}"
                    >
                        <i class="fa-solid fa-clock"></i>
                        <span>Horas</span>
                    </button>
                    <button type="button" class="btn-icon" onclick="exportHistoryImage(${i}, event)" title="Exportar Foto">
                        <i class="fa-solid fa-camera"></i>
                    </button>
                    <button type="button" class="btn-icon" onclick="exportHistoryExcel(${i}, event)" title="Exportar Excel">
                        <i class="fa-solid fa-file-excel"></i>
                    </button>
                    <button type="button" class="btn-icon history-action-button" onclick="swapHistoryEmployees(${i}, event)" title="Intercambiar horarios de dos empleados">
                        <i class="fa-solid fa-right-left"></i>
                        <span>Intercambiar</span>
                    </button>
                    <button type="button" class="btn-icon history-action-button" onclick="addHistoryToFolder(${i}, event)" title="Agregar a carpeta">
                        <i class="fa-solid fa-folder-plus"></i>
                        <span>Carpeta</span>
                    </button>
                </div>
                <div class="history-table-wrapper">
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
                        <tbody></tbody>
                    </table>
                </div>
            </div>
        `;
        listContainer.appendChild(item);
        renderHistoryEntryTable(i);
    });
}

async function loadHistory(forceRefresh = false) {
    const listContainer = document.getElementById('historyList');
    if (!listContainer) return;
    listContainer.innerHTML = '<div class="loading"><i class="fa-solid fa-spinner fa-spin"></i> Cargando...</div>';

    try {
        // No forzar refetch por defecto — preserva ediciones locales en el cache.
        // El cache ya se pobló al abrir el overlay. Forzar refetch pisaría
        // cualquier edición manual que el usuario haya hecho en entradas expandidas.
        await fetchHistoryEntries(forceRefresh);
        await loadTrash();
        renderHistoryList();
        renderTrashList();
        await loadFolders();
    } catch (e) {
        console.error(e);
        listContainer.innerHTML = '<div class="error-msg">Error al cargar historial</div>';
    }
}

let importHorarioExcelHistorialFile = null;
let importHorarioExcelHistorialDrafts = [];

function closeImportHorarioExcelHistorialModal() {
    const m = document.getElementById("importHorarioExcelHistorialModal");
    if (m) m.classList.add("hidden");
}

function openImportHorarioExcelHistorialModal() {
    importHorarioExcelHistorialFile = null;
    importHorarioExcelHistorialDrafts = [];
    const inp = document.getElementById("importHorarioExcelFileInput");
    if (inp) inp.value = "";
    const sl = document.getElementById("importHorarioExcelSheetList");
    if (sl) sl.innerHTML = "";
    const pv = document.getElementById("importHorarioExcelPreview");
    if (pv) pv.innerHTML = "";
    const st = document.getElementById("importHorarioExcelStatus");
    if (st) st.textContent = "";
    const iw = document.getElementById("importHorarioExcelInverseWarnings");
    if (iw) iw.textContent = "";
    const btn = document.getElementById("importHorarioExcelConfirmBtn");
    if (btn) btn.disabled = true;
    const m = document.getElementById("importHorarioExcelHistorialModal");
    if (m) m.classList.remove("hidden");
}

function _importHorarioExcelApiErrorMessage(data, fallback) {
    const d = data && data.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) {
        return d.map((x) => (x && (x.msg || x.message)) || JSON.stringify(x)).join("; ");
    }
    if (d && typeof d === "object") return JSON.stringify(d);
    return fallback || "Error";
}

async function onImportHorarioExcelHistorialFileChange(ev) {
    const f = ev.target.files && ev.target.files[0];
    const sl = document.getElementById("importHorarioExcelSheetList");
    const st = document.getElementById("importHorarioExcelStatus");
    if (!f) return;
    importHorarioExcelHistorialFile = f;
    importHorarioExcelHistorialDrafts = [];
    if (sl) sl.innerHTML = "";
    const pv = document.getElementById("importHorarioExcelPreview");
    if (pv) pv.innerHTML = "";
    const btn = document.getElementById("importHorarioExcelConfirmBtn");
    if (btn) btn.disabled = true;
    if (st) st.textContent = "Leyendo pestañas…";
    const fd = new FormData();
    fd.append("file", f);
    fd.append("sheets", "[]");
    try {
        const res = await fetch("/api/history/import-horario-excel/preview", { method: "POST", body: fd });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(_importHorarioExcelApiErrorMessage(data, res.statusText));
        if (st) st.textContent = `Archivo: ${f.name} — elija pestañas y pulse Vista previa.`;
        (data.sheetnames || []).forEach((name) => {
            const n = String(name).trim();
            const isDefault = /^(10|11|12|13)$/.test(n);
            const safeId = `import-excel-sheet-${String(name).replace(/\W/g, "_")}`;

            // Hidden real checkbox (drives the form logic)
            const cb = document.createElement("input");
            cb.type = "checkbox";
            cb.value = name;
            cb.id = safeId;
            cb.checked = isDefault;
            cb.style.display = "none";

            // Visual pill chip
            const chip = document.createElement("label");
            chip.htmlFor = safeId;
            chip.className = "excel-sheet-chip" + (isDefault ? " selected" : "");
            chip.textContent = n || name;
            chip.title = name;

            cb.addEventListener("change", () => {
                chip.classList.toggle("selected", cb.checked);
            });

            sl.appendChild(cb);
            sl.appendChild(chip);
        });
    } catch (e) {
        console.error(e);
        if (st) st.textContent = e.message || String(e);
    }
}

async function runImportHorarioExcelHistorialPreview() {
    const st = document.getElementById("importHorarioExcelStatus");
    const iw = document.getElementById("importHorarioExcelInverseWarnings");
    const btn = document.getElementById("importHorarioExcelConfirmBtn");
    if (!importHorarioExcelHistorialFile) {
        if (st) st.textContent = "Seleccione un archivo Excel.";
        return;
    }
    const checks = [...document.querySelectorAll("#importHorarioExcelSheetList input[type=checkbox]:checked")];
    const sheets = checks.map((c) => c.value);
    if (!sheets.length) {
        if (st) st.textContent = "Marque al menos una hoja.";
        return;
    }
    if (st) st.textContent = "Generando vista previa…";
    if (iw) iw.textContent = "";
    btn.disabled = true;
    const fd = new FormData();
    fd.append("file", importHorarioExcelHistorialFile);
    fd.append("sheets", JSON.stringify(sheets));
    try {
        const res = await fetch("/api/history/import-horario-excel/preview", { method: "POST", body: fd });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(_importHorarioExcelApiErrorMessage(data, res.statusText));
        importHorarioExcelHistorialDrafts = data.drafts || [];
        if (Array.isArray(data.inverse_map_warnings) && data.inverse_map_warnings.length) {
            iw.textContent =
                "Avisos catálogo turnos (colisiones texto→código): " +
                data.inverse_map_warnings.slice(0, 6).join("; ");
        }
        renderImportHorarioExcelHistorialPreview(importHorarioExcelHistorialDrafts);
        const anyOk = importHorarioExcelHistorialDrafts.some(
            (d) =>
                (!d.errors || !d.errors.length) &&
                d.week_dates &&
                Object.keys(d.week_dates).length >= 7
        );
        btn.disabled = !anyOk;
        if (st) {
            st.textContent = anyOk
                ? "Revise la vista previa y pulse Aceptar (solo se guardan las hojas sin errores)."
                : "Ninguna hoja es importable: corrija el Excel o elija otras pestañas.";
        }
    } catch (e) {
        console.error(e);
        if (st) st.textContent = e.message || String(e);
    }
}

function renderImportHorarioExcelHistorialPreview(drafts) {
    const pv = document.getElementById("importHorarioExcelPreview");
    if (!pv) return;
    pv.innerHTML = "";
    drafts.forEach((d, i) => {
        const card = document.createElement("div");
        card.className = "import-excel-draft-card";
        card.dataset.draftIndex = String(i);
        card.style.marginBottom = "1.25rem";
        card.style.padding = "12px";
        card.style.border = "1px solid var(--border, #e2e8f0)";
        card.style.borderRadius = "10px";

        const h = document.createElement("h4");
        h.style.margin = "0 0 8px";
        h.textContent = `Hoja: ${d.sheet || ""}`;
        card.appendChild(h);

        const errBox = document.createElement("div");
        if (d.errors && d.errors.length) {
            errBox.style.color = "var(--danger, #dc2626)";
            errBox.style.fontSize = "0.85rem";
            errBox.style.marginBottom = "8px";
            errBox.textContent = "Errores: " + d.errors.join(" · ");
        }
        card.appendChild(errBox);

        const warnBox = document.createElement("div");
        if (d.warnings && d.warnings.length) {
            warnBox.style.color = "var(--warning, #d97706)";
            warnBox.style.fontSize = "0.85rem";
            warnBox.style.marginBottom = "8px";
            warnBox.textContent = "Avisos: " + d.warnings.slice(0, 14).join(" · ");
        }
        card.appendChild(warnBox);

        const nameL = document.createElement("label");
        nameL.textContent = "Nombre en historial";
        nameL.style.display = "block";
        nameL.style.fontSize = "0.85rem";
        nameL.style.marginBottom = "4px";
        const nameInp = document.createElement("input");
        nameInp.type = "text";
        nameInp.className = "import-draft-name form-input";
        nameInp.style.width = "100%";
        nameInp.style.marginBottom = "10px";
        nameInp.value = (d.name_sugerido || "").trim();
        nameInp.placeholder = "Ej. Semana 10";
        card.appendChild(nameL);
        card.appendChild(nameInp);

        const wrap = document.createElement("div");
        wrap.className = "history-table-wrapper";
        wrap.style.overflowX = "auto";
        const table = document.createElement("table");
        table.className = "clean-table";
        table.id = `import-hist-prev-${i}`;
        table.innerHTML = `
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
            <tbody></tbody>
        `;
        wrap.appendChild(table);
        card.appendChild(wrap);
        pv.appendChild(card);
        renderSchedule(d.schedule || {}, `#import-hist-prev-${i}`, d.daily_tasks || {}, {}, null, d.week_dates || null);

        // ── Cleaning tasks preview ────────────────────────────────────────────
        const tasks = d.daily_tasks || {};
        const DAYS_PREVIEW = ["Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue"];
        const taskEntries = Object.entries(tasks).filter(
            ([, days]) => DAYS_PREVIEW.some((day) => days[day])
        );
        if (taskEntries.length) {
            const tasksWrap = document.createElement("div");
            tasksWrap.className = "import-tasks-preview";
            const tasksTitle = document.createElement("div");
            tasksTitle.className = "import-tasks-title";
            tasksTitle.innerHTML = `<i class="fa-solid fa-broom"></i> Tareas de Limpieza Detectadas`;
            tasksWrap.appendChild(tasksTitle);
            const tasksGrid = document.createElement("div");
            tasksGrid.className = "import-tasks-grid";
            for (const [emp, days] of taskEntries) {
                const empRow = document.createElement("div");
                empRow.className = "import-tasks-row";
                const empName = document.createElement("span");
                empName.className = "import-tasks-emp";
                empName.textContent = emp;
                empRow.appendChild(empName);
                for (const day of DAYS_PREVIEW) {
                    const task = days[day];
                    const cell = document.createElement("span");
                    let taskColorCls = "";
                    if (task) {
                        const { base } = _taskBaseAndSuffix(task);
                        taskColorCls = " itc-" + _taskColorClass(base).replace("task-", "");
                    }
                    cell.className = "import-tasks-cell" + (task ? " has-task" + taskColorCls : "");
                    cell.textContent = task ? _taskBaseAndSuffix(task).base : "–";
                    cell.title = task ? `${day}: ${task}` : "";
                    empRow.appendChild(cell);
                }
                tasksGrid.appendChild(empRow);
            }
            tasksWrap.appendChild(tasksGrid);
            card.appendChild(tasksWrap);
        }
    });
}

async function confirmImportHorarioExcelHistorial() {
    const st = document.getElementById("importHorarioExcelStatus");
    const cards = [...document.querySelectorAll("#importHorarioExcelPreview .import-excel-draft-card")];
    const items = [];
    const days = ["Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue"];
    for (const card of cards) {
        const i = Number(card.dataset.draftIndex);
        const d = importHorarioExcelHistorialDrafts[i];
        if (!d) continue;
        if (d.errors && d.errors.length) continue;
        if (!d.week_dates || days.some((day) => !(day in d.week_dates))) continue;
        const nameInp = card.querySelector(".import-draft-name");
        const name = (nameInp && nameInp.value.trim()) || (d.name_sugerido || "").trim();
        if (!name) {
            if (st) st.textContent = "Indique un nombre en historial para cada semana válida.";
            return;
        }
        items.push({
            name,
            schedule: d.schedule || {},
            week_dates: d.week_dates,
            daily_tasks: d.daily_tasks || {},
        });
    }
    if (!items.length) {
        if (st) st.textContent = "No hay borradores válidos para guardar.";
        return;
    }
    if (st) st.textContent = "Guardando…";
    try {
        const res = await fetch("/api/history/import-horario-excel/confirm", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ items }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(_importHorarioExcelApiErrorMessage(data, res.statusText));
        closeImportHorarioExcelHistorialModal();
        await loadHistory(true);
    } catch (e) {
        console.error(e);
        if (st) st.textContent = e.message || String(e);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// ENTRADA MANUAL DE SEMANAS
// ─────────────────────────────────────────────────────────────────────────────

const MANUAL_DAYS = ["Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue"];
const MANUAL_CLEANING_TASKS = ["", "Baños", "Tanques", "Oficina + Basureros + Baños"];
const MANUAL_SHIFTS_OPTIONS = [
    { code: "OFF",     label: "Libre" },
    { code: "VAC",     label: "Vacaciones" },
    { code: "PERM",    label: "Permiso" },
    { code: "T1_05-13", label: "T1 5am-1pm" },
    { code: "T2_06-14", label: "T2 6am-2pm" },
    { code: "T3_07-15", label: "T3 7am-3pm" },
    { code: "T4_08-16", label: "T4 8am-4pm" },
    { code: "PM_13-22", label: "PM 1pm-10pm" },
    { code: "J_06-16",  label: "J 6am-4pm" },
    { code: "N_22-05",  label: "N 10pm-5am" },
];

function toggleManualWeekForm() {
    const form = document.getElementById("importManualWeekForm");
    const btn = document.getElementById("toggleManualWeekBtn");
    if (!form) return;
    const isHidden = form.classList.toggle("hidden");
    btn.innerHTML = isHidden
        ? '<i class="fa-solid fa-plus"></i> Agregar semana manualmente'
        : '<i class="fa-solid fa-minus"></i> Ocultar entrada manual';
    if (!isHidden) {
        _buildManualWeekTable();
    }
}

function _getManualShiftOptsHTML() {
    // Usar el catálogo completo cargado desde el backend
    const base = (SHIFT_OPTIONS && SHIFT_OPTIONS.length)
        ? SHIFT_OPTIONS.map(o => `<option value="${o.code}">${o.label}</option>`).join("")
        : MANUAL_SHIFTS_OPTIONS.map(o => `<option value="${o.code}">${o.label}</option>`).join("");
    return base + `<option value="__OTRO__">⌨ Horario manual…</option>`;
}

function _getManualTaskOptsHTML() {
    return MANUAL_CLEANING_TASKS.map(t => `<option value="${t}">${t || "—"}</option>`).join("");
}

function _buildManualWeekRow(empName, isEditable) {
    const shiftOptsHTML = _getManualShiftOptsHTML();
    const taskOptsHTML = _getManualTaskOptsHTML();
    const tr = document.createElement("tr");

    // Celda de nombre
    const nameTd = document.createElement("td");
    nameTd.style.padding = "4px 5px";
    if (isEditable) {
        const inp = document.createElement("input");
        inp.type = "text";
        inp.placeholder = "Nombre colaborador";
        inp.className = "form-input manual-emp-name-input";
        inp.style.cssText = "width:100%;font-size:0.78rem;padding:3px 6px;border-radius:6px;";
        inp.dataset.empName = "";
        inp.addEventListener("input", () => { inp.dataset.empName = inp.value.trim(); nameTd.dataset.empName = inp.value.trim(); });
        nameTd.appendChild(inp);
    } else {
        nameTd.textContent = empName;
        nameTd.dataset.empName = empName;
        nameTd.style.fontWeight = "500";
        nameTd.style.fontSize = "0.82rem";
    }
    tr.appendChild(nameTd);

    for (const day of MANUAL_DAYS) {
        const td = document.createElement("td");
        td.style.padding = "3px 2px";

        const shiftSel = document.createElement("select");
        shiftSel.className = "manual-shift-sel";
        shiftSel.dataset.emp = empName;
        shiftSel.dataset.day = day;
        shiftSel.innerHTML = shiftOptsHTML;
        shiftSel.style.cssText = "width:100%;min-width:82px;font-size:0.7rem;padding:2px 3px;border-radius:6px;background:var(--bg-app);border:1px solid var(--border);color:var(--text-main);display:block;";

        const customInp = document.createElement("input");
        customInp.type = "text";
        customInp.placeholder = "Ej: 8:00-16:00";
        customInp.className = "manual-custom-time hidden";
        customInp.style.cssText = "width:100%;font-size:0.68rem;padding:2px 4px;margin-top:2px;border-radius:5px;background:var(--bg-app);border:1px solid var(--primary,#6366f1);color:var(--text-main);display:none;";

        shiftSel.addEventListener("change", () => {
            const isOtro = shiftSel.value === "__OTRO__";
            customInp.style.display = isOtro ? "block" : "none";
        });

        const taskSel = document.createElement("select");
        taskSel.className = "manual-task-sel";
        taskSel.dataset.emp = empName;
        taskSel.dataset.day = day;
        taskSel.innerHTML = taskOptsHTML;
        taskSel.style.cssText = "width:100%;font-size:0.67rem;padding:1px 3px;margin-top:2px;border-radius:5px;background:var(--surface-2);border:1px solid var(--border);color:var(--text-muted);display:block;";

        td.appendChild(shiftSel);
        td.appendChild(customInp);
        td.appendChild(taskSel);
        tr.appendChild(td);
    }

    // Botón eliminar fila
    const delTd = document.createElement("td");
    delTd.style.padding = "4px 3px";
    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.innerHTML = `<i class="fa-solid fa-xmark"></i>`;
    delBtn.title = "Eliminar esta fila";
    delBtn.style.cssText = "background:none;border:none;color:var(--danger,#dc2626);cursor:pointer;font-size:0.9rem;padding:2px 5px;border-radius:4px;";
    delBtn.addEventListener("click", () => tr.remove());
    delTd.appendChild(delBtn);
    tr.appendChild(delTd);

    return tr;
}

function _buildManualWeekTable() {
    const tbody = document.getElementById("manualWeekTableBody");
    if (!tbody) return;
    tbody.innerHTML = "";

    const activeEmps = employees.filter(e => e.activo !== false && e.activo !== 0);

    for (const emp of activeEmps) {
        tbody.appendChild(_buildManualWeekRow(emp.name || "", false));
    }

    if (!activeEmps.length) {
        _addManualEmptyRow();
    }
}

function _addManualEmptyRow() {
    const tbody = document.getElementById("manualWeekTableBody");
    if (!tbody) return;
    const tr = _buildManualWeekRow("", true);
    tbody.appendChild(tr);
    // Focus the name input
    const inp = tr.querySelector(".manual-emp-name-input");
    if (inp) setTimeout(() => inp.focus(), 50);
}

function onManualWeekDateChange() {
    // noop — fechas se calculan al agregar al preview
}

function _fridayToWeekDates(fridayIso) {
    const fri = new Date(fridayIso + "T12:00:00");
    const wd = {};
    MANUAL_DAYS.forEach((day, i) => {
        const d = new Date(fri);
        d.setDate(fri.getDate() + i);
        const dd = String(d.getDate()).padStart(2, "0");
        const mm = String(d.getMonth() + 1).padStart(2, "0");
        const yyyy = d.getFullYear();
        wd[day] = `${dd}/${mm}/${yyyy}`;
    });
    return wd;
}

function addManualWeekToPreview() {
    const nameVal = (document.getElementById("manualWeekName")?.value || "").trim();
    const fridayVal = document.getElementById("manualWeekFridayDate")?.value || "";
    const statusEl = document.getElementById("manualWeekStatus");

    if (!nameVal) {
        if (statusEl) statusEl.textContent = "Ingresá un nombre para la semana.";
        return;
    }
    if (!fridayVal) {
        if (statusEl) statusEl.textContent = "Seleccioná la fecha del Viernes.";
        return;
    }

    const weekDates = _fridayToWeekDates(fridayVal);

    // Leer turnos y tareas del formulario
    const schedule = {};
    const dailyTasks = {};

    document.querySelectorAll("#manualWeekTableBody tr").forEach(tr => {
        // Obtener el nombre del empleado (puede venir de data-emp-name en td o del input)
        const nameTd = tr.querySelector("td[data-emp-name]");
        const nameInp = tr.querySelector(".manual-emp-name-input");
        const empName = (nameTd?.dataset?.empName || nameInp?.value || "").trim();
        if (!empName) return;

        schedule[empName] = {};
        dailyTasks[empName] = {};

        MANUAL_DAYS.forEach(day => {
            const shiftSel = tr.querySelector(`.manual-shift-sel[data-day="${day}"]`);
            const taskSel = tr.querySelector(`.manual-task-sel[data-day="${day}"]`);

            let shiftVal = shiftSel?.value || "OFF";
            if (shiftVal === "__OTRO__") {
                // Buscar el input de tiempo libre dentro del mismo td que el select
                const td = shiftSel?.closest("td");
                const timeInp = td?.querySelector(".manual-custom-time");
                const raw = timeInp?.value?.trim() || "";
                if (typeof normalizeFlexibleShiftInput === 'function') {
                    shiftVal = normalizeFlexibleShiftInput(raw) || "OFF";
                } else {
                    shiftVal = raw ? (raw.startsWith("MANUAL_") ? raw : "MANUAL_" + raw) : "OFF";
                }
            }
            schedule[empName][day] = shiftVal;
            const tv = taskSel?.value || "";
            dailyTasks[empName][day] = tv || null;
        });
    });

    if (!Object.keys(schedule).length) {
        if (statusEl) statusEl.textContent = "No hay empleados en la tabla.";
        return;
    }

    const draft = {
        sheet: "Manual",
        name_sugerido: nameVal,
        week_dates: weekDates,
        schedule,
        daily_tasks: dailyTasks,
        warnings: [],
        errors: [],
        _manual: true,
    };

    importHorarioExcelHistorialDrafts.push(draft);
    renderImportHorarioExcelHistorialPreview(importHorarioExcelHistorialDrafts);

    const anyOk = importHorarioExcelHistorialDrafts.some(
        d => (!d.errors || !d.errors.length) && d.week_dates && MANUAL_DAYS.every(day => day in d.week_dates)
    );
    const confirmBtn = document.getElementById("importHorarioExcelConfirmBtn");
    if (confirmBtn) confirmBtn.disabled = !anyOk;

    if (statusEl) statusEl.textContent = `✓ Semana "${nameVal}" agregada al preview.`;
}

// =====================================================
// HORARIO MANUAL — editor completo con guardado al historial
// =====================================================
const _manualSchedState = {
    weekDates: {},
    specialDays: {},     // { Vie: 'closed' | 'open_holiday' | undefined }
    holidayDays: {},     // { Vie: { name } }
    hoursVisible: true,
    holidayMode: false,
};

function _manualSchedSetStatus(text, kind = "info") {
    const el = document.getElementById("manualSchedStatus");
    if (!el) return;
    const colors = {
        info: "var(--text-muted)",
        success: "var(--success, #10b981)",
        error: "var(--error, #ef4444)",
        warn: "var(--warn, #f59e0b)",
    };
    el.style.color = colors[kind] || colors.info;
    el.textContent = text || "";
}

function _manualSchedDefaultFridayIso() {
    const today = new Date();
    const day = today.getDay(); // 0=Sun..6=Sat
    const diff = (5 - day + 7) % 7; // distancia hasta el próximo viernes (incluye hoy si es viernes)
    const fri = new Date(today);
    fri.setDate(today.getDate() + diff - 7); // viernes pasado por defecto
    const yyyy = fri.getFullYear();
    const mm = String(fri.getMonth() + 1).padStart(2, "0");
    const dd = String(fri.getDate()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd}`;
}

function _manualSchedRefreshHeader() {
    const fridayIso = document.getElementById("manualSchedFriday")?.value || "";
    if (fridayIso) {
        _manualSchedState.weekDates = _fridayToWeekDates(fridayIso);
    } else {
        _manualSchedState.weekDates = {};
    }
    const headerRow = document.getElementById("manualSchedHeaderRow");
    if (!headerRow) return;
    MANUAL_DAYS.forEach(day => {
        const th = headerRow.querySelector(`th[data-day="${day}"]`);
        if (!th) return;
        const dateLabel = _manualSchedState.weekDates[day] || "";
        const isClosed = _manualSchedState.specialDays[day] === "closed";
        const holiday = _manualSchedState.holidayDays[day];
        th.classList.toggle("th-closed", isClosed);
        th.classList.toggle("th-holiday", !!holiday);
        th.classList.toggle("manual-sched-day-clickable", _manualSchedState.holidayMode);
        const closedBadge = isClosed ? `<span class="ms-day-mini-badge closed">CERRADO</span>` : "";
        const holidayBadge = holiday ? `<span class="ms-day-mini-badge holiday"><i class="fa-solid fa-star"></i></span>` : "";
        const dateBadge = dateLabel ? `<span class="ms-day-date-badge">${dateLabel}</span>` : "";
        th.innerHTML = `<span>${day}${closedBadge}${holidayBadge}</span>${dateBadge}`;
        if (_manualSchedState.holidayMode) {
            th.onclick = () => _manualSchedToggleDayState(day);
        } else {
            th.onclick = null;
        }
    });
}

function manualSchedRefreshHeaderDates() {
    _manualSchedRefreshHeader();
}

function _manualSchedToggleDayState(day) {
    const isClosed = _manualSchedState.specialDays[day] === "closed";
    const holiday = _manualSchedState.holidayDays[day];
    if (!isClosed && !holiday) {
        _manualSchedState.specialDays[day] = "closed";
    } else if (isClosed && !holiday) {
        delete _manualSchedState.specialDays[day];
        _manualSchedState.holidayDays[day] = { name: "Feriado" };
    } else {
        delete _manualSchedState.specialDays[day];
        delete _manualSchedState.holidayDays[day];
    }
    _manualSchedRefreshHeader();
}

function manualSchedToggleHolidayMode() {
    _manualSchedState.holidayMode = !_manualSchedState.holidayMode;
    const btn = document.getElementById("manualSchedHolidayBtn");
    if (btn) {
        btn.classList.toggle("is-active", _manualSchedState.holidayMode);
    }
    _manualSchedRefreshHeader();
    _manualSchedSetStatus(
        _manualSchedState.holidayMode
            ? "Modo feriado/cerrado activo. Click en un día del header para alternar entre normal → cerrado → feriado."
            : ""
    );
}

function manualSchedToggleHours() {
    _manualSchedState.hoursVisible = !_manualSchedState.hoursVisible;
    document.querySelectorAll("#manualSchedTable .col-hours, #manualSchedTable .ms-col-hours").forEach(el => {
        el.classList.toggle("hidden-col", !_manualSchedState.hoursVisible);
    });
    const btn = document.getElementById("manualSchedHoursBtn");
    if (btn) btn.classList.toggle("is-active", _manualSchedState.hoursVisible);
}

function _manualSchedAvatarInitials(name) {
    const parts = (name || "").trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return "?";
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return (parts[0][0] + parts[1][0]).toUpperCase();
}

function _manualSchedUpdateRowsCount() {
    const tbody = document.getElementById("manualSchedTbody");
    const chip = document.getElementById("manualSchedStatRows");
    if (chip && tbody) chip.textContent = String(tbody.querySelectorAll("tr").length);
}

function _manualSchedBuildRow(name, isEditable) {
    const shiftOptsHTML = _getManualShiftOptsHTML();
    const taskOptsHTML = _getManualTaskOptsHTML();
    const tr = document.createElement("tr");
    tr.dataset.empName = name || "";

    const nameTd = document.createElement("td");
    nameTd.className = "ms-col-name ms-name-cell";
    if (isEditable) {
        const inp = document.createElement("input");
        inp.type = "text";
        inp.placeholder = "Nombre colaborador";
        inp.className = "ms-name-input";
        inp.value = name || "";
        inp.addEventListener("input", () => {
            tr.dataset.empName = inp.value.trim();
        });
        nameTd.appendChild(inp);
    } else {
        const wrap = document.createElement("span");
        wrap.className = "ms-name-pill";
        const avatar = document.createElement("span");
        avatar.className = "ms-name-avatar";
        avatar.textContent = _manualSchedAvatarInitials(name);
        const txt = document.createElement("span");
        txt.textContent = name;
        wrap.appendChild(avatar);
        wrap.appendChild(txt);
        nameTd.appendChild(wrap);
    }
    tr.appendChild(nameTd);

    const updateHours = () => {
        let total = 0;
        MANUAL_DAYS.forEach(day => {
            const sel = tr.querySelector(`.manual-shift-sel[data-day="${day}"]`);
            if (!sel) return;
            let val = sel.value;
            if (val === "__OTRO__") {
                const ci = tr.querySelector(`.manual-custom-time[data-day="${day}"]`);
                const raw = (ci?.value || "").trim();
                if (raw) {
                    const norm = normalizeFlexibleShiftInput(raw);
                    if (norm && norm !== "AUTO") val = norm;
                }
            }
            total += getShiftHoursCount(val) || 0;
        });
        const hoursTd = tr.querySelector(".manual-sched-hours-cell");
        if (hoursTd) hoursTd.textContent = total + "h";
    };

    MANUAL_DAYS.forEach(day => {
        const td = document.createElement("td");
        const stack = document.createElement("div");
        stack.className = "ms-cell-stack";

        const shiftSel = document.createElement("select");
        shiftSel.className = "manual-shift-sel";
        shiftSel.dataset.day = day;
        shiftSel.innerHTML = shiftOptsHTML;
        shiftSel.value = "OFF";

        const customInp = document.createElement("input");
        customInp.type = "text";
        customInp.className = "manual-custom-time";
        customInp.dataset.day = day;
        customInp.placeholder = "Ej: 13-22 ó 1pm-10pm";
        customInp.style.display = "none";

        shiftSel.addEventListener("change", () => {
            customInp.style.display = shiftSel.value === "__OTRO__" ? "block" : "none";
            updateHours();
        });
        customInp.addEventListener("input", updateHours);

        const taskSel = document.createElement("select");
        taskSel.className = "manual-task-sel";
        taskSel.dataset.day = day;
        taskSel.innerHTML = taskOptsHTML;

        stack.appendChild(shiftSel);
        stack.appendChild(customInp);
        stack.appendChild(taskSel);
        td.appendChild(stack);
        tr.appendChild(td);
    });

    const hoursTd = document.createElement("td");
    hoursTd.className = "ms-col-hours col-hours manual-sched-hours-cell";
    hoursTd.textContent = "0h";
    if (!_manualSchedState.hoursVisible) hoursTd.classList.add("hidden-col");
    tr.appendChild(hoursTd);

    const delTd = document.createElement("td");
    delTd.className = "ms-col-action";
    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "manual-row-del";
    delBtn.title = "Eliminar fila";
    delBtn.innerHTML = `<i class="fa-solid fa-xmark"></i>`;
    delBtn.addEventListener("click", () => {
        tr.remove();
        _manualSchedUpdateRowsCount();
    });
    delTd.appendChild(delBtn);
    tr.appendChild(delTd);

    return tr;
}

async function _manualSchedFetchActiveEmployees() {
    try {
        const res = await fetch('/api/planillas/empleados');
        if (!res.ok) return [];
        const all = await res.json();
        return all
            .filter(e => (e.activo === 1 || e.activo === true)
                && (e.incluir_en_horario === 1 || e.incluir_en_horario === true || e.incluir_en_horario == null))
            .map(e => e.nombre || "")
            .filter(Boolean)
            .sort((a, b) => a.localeCompare(b, 'es', { sensitivity: 'base' }));
    } catch (err) {
        console.error("No se pudieron cargar empleados:", err);
        return [];
    }
}

window.manualSchedReloadEmployees = async function () {
    const tbody = document.getElementById("manualSchedTbody");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding:1.25rem; color:var(--text-muted);"><i class="fa-solid fa-spinner fa-spin"></i> Cargando empleados...</td></tr>`;
    const names = await _manualSchedFetchActiveEmployees();
    tbody.innerHTML = "";
    if (!names.length) {
        _manualSchedAddRow();
        _manualSchedSetStatus("No hay empleados activos incluidos en horario. Se agregó una fila vacía.", "warn");
        _manualSchedUpdateRowsCount();
        return;
    }
    names.forEach(n => tbody.appendChild(_manualSchedBuildRow(n, false)));
    _manualSchedSetStatus(`${names.length} empleados cargados.`, "info");
    _manualSchedUpdateRowsCount();
};

function _manualSchedAddRow() {
    const tbody = document.getElementById("manualSchedTbody");
    if (!tbody) return;
    const tr = _manualSchedBuildRow("", true);
    tbody.appendChild(tr);
    _manualSchedUpdateRowsCount();
    setTimeout(() => tr.querySelector(".ms-name-input")?.focus(), 30);
}

window.manualSchedAddRow = _manualSchedAddRow;

window.openManualScheduleOverlay = async function () {
    document.querySelectorAll('.section-overlay').forEach(el => el.classList.add('hidden'));
    const overlay = document.getElementById('overlay-manual-schedule');
    if (!overlay) return;
    overlay.classList.remove('hidden');
    updateSidebarActive('nav-manual-schedule');

    const fridayInput = document.getElementById('manualSchedFriday');
    if (fridayInput && !fridayInput.value) {
        fridayInput.value = _manualSchedDefaultFridayIso();
    }
    const nameInput = document.getElementById('manualSchedName');
    if (nameInput && !nameInput.value && fridayInput?.value) {
        nameInput.value = `Manual ${fridayInput.value}`;
    }

    _manualSchedState.specialDays = {};
    _manualSchedState.holidayDays = {};
    _manualSchedState.holidayMode = false;
    _manualSchedRefreshHeader();
    await window.manualSchedReloadEmployees();
};

function _manualSchedReadSchedule() {
    const schedule = {};
    const dailyTasks = {};
    const tbody = document.getElementById("manualSchedTbody");
    if (!tbody) return { schedule, dailyTasks };
    tbody.querySelectorAll("tr").forEach(tr => {
        const empName = (tr.dataset.empName || "").trim();
        if (!empName) return;
        schedule[empName] = {};
        dailyTasks[empName] = {};
        MANUAL_DAYS.forEach(day => {
            const sel = tr.querySelector(`.manual-shift-sel[data-day="${day}"]`);
            const ci = tr.querySelector(`.manual-custom-time[data-day="${day}"]`);
            const taskSel = tr.querySelector(`.manual-task-sel[data-day="${day}"]`);
            let val = sel?.value || "OFF";
            if (val === "__OTRO__") {
                const raw = (ci?.value || "").trim();
                const norm = raw ? normalizeFlexibleShiftInput(raw) : null;
                val = (norm && norm !== "AUTO") ? norm : "OFF";
            }
            schedule[empName][day] = val;
            const taskBase = taskSel?.value || "";
            if (taskBase) {
                const startHour = getShiftStartHour(val);
                let suffix = "";
                if (val !== "OFF" && val !== "VAC" && val !== "PERM") {
                    suffix = startHour >= 12 ? "↓PM" : "↑AM";
                }
                dailyTasks[empName][day] = taskBase + (suffix ? " " + suffix : "");
            } else {
                dailyTasks[empName][day] = "";
            }
        });
    });
    return { schedule, dailyTasks };
}

window.manualSchedValidate = async function () {
    const { schedule } = _manualSchedReadSchedule();
    if (!Object.keys(schedule).length) {
        _manualSchedSetStatus("Agregá al menos una fila con turnos para validar.", "warn");
        return;
    }
    try {
        const oldSchedule = currentGeneratedSchedule;
        const oldRules = validationRules;
        const oldMeta = currentMetadata;
        currentGeneratedSchedule = schedule;
        currentMetadata = {
            special_days: { ...(_manualSchedState.specialDays || {}) },
            holiday_days: { ...(_manualSchedState.holidayDays || {}) },
        };
        validationRules = await fetchValidationRules(_manualSchedState.specialDays || {});
        isValidationOn = true;
        applyValidationUI();
        currentGeneratedSchedule = oldSchedule;
        validationRules = oldRules || baseValidationRules;
        currentMetadata = oldMeta;
        _manualSchedSetStatus("Validación corrida. Mirá el panel emergente para detalles.", "success");
    } catch (err) {
        console.error(err);
        _manualSchedSetStatus("Error al validar: " + (err.message || err), "error");
    }
};

window.manualSchedSave = async function () {
    const name = (document.getElementById('manualSchedName')?.value || "").trim();
    const fridayIso = document.getElementById('manualSchedFriday')?.value || "";
    if (!name) {
        _manualSchedSetStatus("Ingresá un nombre para la semana.", "error");
        return;
    }
    if (!fridayIso) {
        _manualSchedSetStatus("Seleccioná la fecha del viernes.", "error");
        return;
    }
    const { schedule, dailyTasks } = _manualSchedReadSchedule();
    if (!Object.keys(schedule).length) {
        _manualSchedSetStatus("Agregá al menos una fila con un nombre antes de guardar.", "error");
        return;
    }

    const weekDates = _fridayToWeekDates(fridayIso);
    const payload = {
        name,
        schedule,
        daily_tasks: dailyTasks,
        week_dates: weekDates,
        special_days: { ..._manualSchedState.specialDays },
        metadata: {
            source: "manual_editor",
            holiday_days: { ..._manualSchedState.holidayDays },
        },
        timestamp: new Date().toISOString(),
    };

    _manualSchedSetStatus("Guardando...", "info");
    try {
        const res = await fetch('/api/history', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (!res.ok) {
            let detail = "No se pudo guardar.";
            try { detail = (await res.json()).detail || detail; } catch (_) { }
            throw new Error(detail);
        }
        _manualSchedSetStatus(`Guardado al historial: "${name}".`, "success");
        // Si el overlay del historial está abierto en algún momento, refrescar
        historyEntriesCache = [];
    } catch (err) {
        console.error(err);
        _manualSchedSetStatus("Error al guardar: " + (err.message || err), "error");
    }
};

function toggleHistory(header) {
    const item = header.parentElement;
    const index = Number(item.dataset.historyIndex);
    const isExpanding = !item.classList.contains('expanded');
    
    // Obtener todos los items del historial
    const allItems = document.querySelectorAll('.history-item');
    
    if (isExpanding) {
        // Primero minimizar cualquier otro que esté expandido con animación
        allItems.forEach(i => {
            if (i !== item && i.classList.contains('expanded')) {
                i.classList.remove('expanded');
                i.classList.add('hidden-by-expand');
            }
        });
        
        // Ocultar los demás después de un pequeño delay para la animación
        setTimeout(() => {
            allItems.forEach(i => {
                if (i !== item) {
                    i.style.display = 'none';
                    i.classList.remove('hidden-by-expand');
                }
            });
            // Ahora expandir el actual
            item.classList.add('expanded');
            expandedHistoryItems.add(index);
        }, 50);
    } else {
        // Minimizar el actual
        item.classList.remove('expanded');
        expandedHistoryItems.delete(index);
        
        // Mostrar todos los demás
        setTimeout(() => {
            allItems.forEach(i => {
                i.style.display = '';
            });
        }, 100);
    }
}

function clearHistorySelectionStyles() {
    document.querySelectorAll('.history-shift-pill.history-pill-selected').forEach(el => {
        el.classList.remove('history-pill-selected');
    });
}

function getHistorySelectionRange(startDay, endDay) {
    const startIndex = DAY_INDEX[startDay];
    const endIndex = DAY_INDEX[endDay];
    if (startIndex === undefined || endIndex === undefined) {
        return startDay ? [startDay] : [];
    }
    const from = Math.min(startIndex, endIndex);
    const to = Math.max(startIndex, endIndex);
    return DAYS.slice(from, to + 1);
}

function applyHistorySelectionStyles() {
    clearHistorySelectionStyles();
    if (
        historySelectionState.histIndex === null ||
        !historySelectionState.empName ||
        !historySelectionState.days.length
    ) {
        return;
    }

    document.querySelectorAll('.history-shift-pill').forEach(el => {
        if (
            Number(el.dataset.historyIndex) === historySelectionState.histIndex &&
            el.dataset.employeeName === historySelectionState.empName &&
            historySelectionState.days.includes(el.dataset.day)
        ) {
            el.classList.add('history-pill-selected');
        }
    });
}

function beginHistorySelection(event, element) {
    if (event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();

    historySelectionState.active = true;
    historySelectionState.histIndex = Number(element.dataset.historyIndex);
    historySelectionState.empName = element.dataset.employeeName || "";
    historySelectionState.anchorDay = element.dataset.day || null;
    historySelectionState.currentDay = element.dataset.day || null;
    historySelectionState.days = element.dataset.day ? [element.dataset.day] : [];
    historySelectionState.dragged = false;

    applyHistorySelectionStyles();
    document.addEventListener('mouseup', finishHistorySelection, { once: true });
}

function extendHistorySelection(event, element) {
    if (!historySelectionState.active) return;
    if ((event.buttons & 1) !== 1) return;

    const histIndex = Number(element.dataset.historyIndex);
    const empName = element.dataset.employeeName || "";
    const day = element.dataset.day || null;

    if (
        histIndex !== historySelectionState.histIndex ||
        empName !== historySelectionState.empName ||
        !day
    ) {
        return;
    }

    if (day !== historySelectionState.currentDay) {
        historySelectionState.dragged = true;
        historySelectionState.currentDay = day;
        historySelectionState.days = getHistorySelectionRange(historySelectionState.anchorDay, day);
        applyHistorySelectionStyles();
    }
}

function finishHistorySelection() {
    if (!historySelectionState.active) return;

    const selection = {
        histIndex: historySelectionState.histIndex,
        empName: historySelectionState.empName,
        days: [...historySelectionState.days],
        dragged: historySelectionState.dragged,
    };

    historySelectionState.active = false;

    if (selection.dragged && selection.days.length > 1) {
        historySelectionState.suppressClick = true;
        window.setTimeout(() => {
            editHistoryShiftBatch(selection.empName, selection.days, selection.histIndex);
        }, 0);
        return;
    }

    clearHistorySelectionStyles();
    historySelectionState.anchorDay = null;
    historySelectionState.currentDay = null;
    historySelectionState.days = [];
}

function handleHistoryCellClick(event, element) {
    event.preventDefault();
    event.stopPropagation();

    if (historySelectionState.suppressClick) {
        historySelectionState.suppressClick = false;
        clearHistorySelectionStyles();
        return;
    }

    openShiftTaskModal(
        element.dataset.employeeName,
        element.dataset.day,
        Number(element.dataset.historyIndex)
    );
}

// Variables para el modal de turno + tarea
let shiftTaskModalData = {
    empName: null,
    day: null,
    histIndex: null,
    currentShift: null,
    currentTask: null
};

function _populateShiftTaskLegend() {
    const el = document.getElementById('shiftTaskLegend');
    if (!el) return;
    const rows = [];
    const codes = Object.keys(SHIFT_HOURS || {})
        .filter(c => c && !["OFF", "VAC", "PERM"].includes(c))
        .sort((a, b) => {
            const ha = (SHIFT_HOURS[a] && SHIFT_HOURS[a].start) || 0;
            const hb = (SHIFT_HOURS[b] && SHIFT_HOURS[b].start) || 0;
            return ha - hb;
        });
    const friendly = (code) => {
        const info = (typeof getShiftInfo === "function") ? getShiftInfo(code) : null;
        return info && info.text ? info.text : code;
    };
    rows.push(`<div style="margin-bottom:0.4rem;"><b>Códigos rápidos</b></div>`);
    if (codes.length) {
        const items = codes.map(c => `<code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">${escapeHtmlAttr(c)}</code> = <span style="color:var(--text-muted);">${escapeHtmlAttr(friendly(c))}</span>`).join('<br/>');
        rows.push(`<div style="margin-bottom:0.6rem;">${items}</div>`);
    }
    rows.push(`<div style="margin-bottom:0.4rem;"><b>Horarios manuales</b></div>`);
    rows.push(`<div style="margin-bottom:0.6rem; color:var(--text-muted);">
        Escribí el rango directamente, ejemplos:<br/>
        <code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">13-22</code> · <code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">1pm-10pm</code> · <code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">5am-11am + 5pm-8pm</code>
    </div>`);
    rows.push(`<div style="margin-bottom:0.4rem;"><b>Códigos especiales</b></div>`);
    rows.push(`<div style="color:var(--text-muted);">
        <code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">OFF</code> = Libre &nbsp;·&nbsp;
        <code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">VAC</code> = Vacaciones &nbsp;·&nbsp;
        <code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">PERM</code> = Permiso
    </div>`);
    el.innerHTML = rows.join("");
}

window.openShiftTaskModal = function(empName, day, histIndex) {
    const entry = historyEntriesCache[histIndex];
    if (!entry) return;

    const currentShift = entry.schedule?.[empName]?.[day] || "OFF";
    const currentTasks = entry.daily_tasks || {};
    const currentTask = (currentTasks[empName] || {})[day] || "";

    _populateShiftTaskLegend();

    // Guardar datos
    shiftTaskModalData = { empName, day, histIndex, currentShift, currentTask };

    // Setear título
    document.getElementById('shiftTaskTitle').textContent = `Editar: ${empName} (${day})`;

    // Setear turno actual
    const shiftInput = document.getElementById('shiftTaskShiftInput');
    shiftInput.value = currentShift.startsWith("MANUAL_") ? currentShift.slice(7) : currentShift;

    // Setear tarea actual (separar base de sufijo)
    const taskSelect = document.getElementById('shiftTaskSelect');
    const { base } = _taskBaseAndSuffix(currentTask);
    taskSelect.value = base || "";

    // Inferir AM/PM basado en el turno
    const hintEl = document.getElementById('shiftTaskAmPmHint');
    const hintText = document.getElementById('shiftTaskAmPmText');
    const startHour = getShiftStartHour(currentShift);
    
    // Mostrar hint si el turno tiene horario definido
    if (currentShift && currentShift !== "OFF" && currentShift !== "VAC" && currentShift !== "PERM") {
        if (startHour >= 12) {
            hintEl.style.display = 'block';
            hintText.innerHTML = `Turno PM (empieza a las ${startHour}:00). La tarea se marcará con <b>↓PM</b>.`;
        } else {
            hintEl.style.display = 'block';
            hintText.innerHTML = `Turno AM (empieza a las ${startHour}:00). La tarea se marcará con <b>↑AM</b>.`;
        }
    } else {
        hintEl.style.display = 'none';
    }

    // Mostrar modal
    document.getElementById('shiftTaskModal').classList.remove('hidden');
    shiftInput.focus();
};

window.closeShiftTaskModal = function() {
    document.getElementById('shiftTaskModal').classList.add('hidden');
};

window.confirmShiftTaskEdit = async function() {
    const { empName, day, histIndex } = shiftTaskModalData;
    const entry = historyEntriesCache[histIndex];
    if (!entry) return;

    const newShiftInput = document.getElementById('shiftTaskShiftInput').value.trim();
    const taskSelect = document.getElementById('shiftTaskSelect');
    const taskBase = taskSelect.value;

    // Procesar turno
    let newShift = null;
    if (newShiftInput && newShiftInput !== "") {
        const normalized = normalizeFlexibleShiftInput(newShiftInput);
        if (normalized && normalized !== "AUTO") {
            newShift = normalized;
        }
    }

    // Si el turno queda vacío o es "OFF", borrar el turno
    if (!newShift || newShift === "OFF") {
        newShift = "OFF";
    }

    // Procesar tarea con sufijo AM/PM basado en el turno
    let newTask = null;
    if (taskBase) {
        const startHour = getShiftStartHour(newShift);
        let suffix = "";
        if (newShift !== "OFF" && newShift !== "VAC" && newShift !== "PERM") {
            if (startHour >= 12) {
                suffix = "↓PM";
            } else {
                suffix = "↑AM";
            }
        }
        newTask = taskBase + (suffix ? " " + suffix : "");
    }

    // Actualizar entrada
    const nextEntry = cloneHistoryEntry(entry);
    nextEntry.schedule = nextEntry.schedule || {};
    nextEntry.schedule[empName] = nextEntry.schedule[empName] || {};
    nextEntry.daily_tasks = nextEntry.daily_tasks || {};
    nextEntry.daily_tasks[empName] = nextEntry.daily_tasks[empName] || {};
    
    nextEntry.schedule[empName][day] = newShift;
    nextEntry.daily_tasks[empName][day] = newTask;

    try {
        await persistHistoryEntry(histIndex, nextEntry);
        closeShiftTaskModal();
        renderHistoryEntryTable(histIndex);
        setStatusMessage(`Actualizado: ${empName} - ${day}`, "success");
    } catch (err) {
        console.error(err);
        setStatusMessage("Error al guardar: " + err.message, "error");
    }
};

function buildHistoryShiftPromptMessage(empName, days) {
    const dayLabel = days.length === 1 ? days[0] : days.join(", ");
    return `Cambiar turno de ${empName} (${dayLabel})`;
}

function getHistoryPromptDefaultValue(shiftCode) {
    if (!shiftCode) return "";
    return shiftCode.startsWith(MANUAL_SHIFT_PREFIX)
        ? shiftCode.slice(MANUAL_SHIFT_PREFIX.length)
        : shiftCode;
}

// Variable para guardar el callback del modal de turno
let shiftPromptCallback = null;

function promptHistoryShiftValue(empName, days, currentValue = "") {
    return new Promise((resolve) => {
        const message = buildHistoryShiftPromptMessage(empName, days);
        const defaultVal = getHistoryPromptDefaultValue(currentValue);
        
        // Abrir modal con el mensaje y valor por defecto
        document.getElementById('textEditTitle').textContent = message;
        document.getElementById('textEditLabel').textContent = 'Turno';
        document.getElementById('textEditInput').value = defaultVal;
        document.getElementById('textEditInput').placeholder = "Ej: 5am-1pm, 13-22, OFF";

        // Mostrar leyenda colapsable con los formatos aceptados (no listamos códigos crudos)
        const legendWrap = document.getElementById('textEditLegendWrap');
        const legendBody = document.getElementById('textEditLegend');
        if (legendWrap && legendBody) {
            legendWrap.style.display = 'block';
            const codes = Object.keys(SHIFT_HOURS || {})
                .filter(c => c && !["OFF", "VAC", "PERM"].includes(c))
                .sort((a, b) => {
                    const ha = (SHIFT_HOURS[a] && SHIFT_HOURS[a].start) || 0;
                    const hb = (SHIFT_HOURS[b] && SHIFT_HOURS[b].start) || 0;
                    return ha - hb;
                });
            const friendly = (code) => {
                const info = (typeof getShiftInfo === "function") ? getShiftInfo(code) : null;
                return info && info.text ? info.text : code;
            };
            const fastItems = codes.map(c => `<code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">${escapeHtmlAttr(c)}</code> = <span style="color:var(--text-muted);">${escapeHtmlAttr(friendly(c))}</span>`).join('<br/>');
            legendBody.innerHTML = `
                <div style="margin-bottom:0.4rem;"><b>Códigos rápidos</b></div>
                <div style="margin-bottom:0.6rem;">${fastItems}</div>
                <div style="margin-bottom:0.4rem;"><b>Horario manual</b></div>
                <div style="margin-bottom:0.6rem; color:var(--text-muted);">
                    Escribí el rango directamente:<br/>
                    <code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">13-22</code> · <code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">1pm-10pm</code> · <code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">5am-11am + 5pm-8pm</code>
                </div>
                <div style="margin-bottom:0.4rem;"><b>Códigos especiales</b></div>
                <div style="color:var(--text-muted);">
                    <code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">OFF</code> Libre &nbsp;·&nbsp;
                    <code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">VAC</code> Vacaciones &nbsp;·&nbsp;
                    <code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">PERM</code> Permiso
                </div>`;
        }
        
        shiftPromptCallback = (input) => {
            if (!input || input.trim() === "") {
                resolve(null);
                return;
            }
            
            const trimmed = input.trim();
            const normalized = normalizeFlexibleShiftInput(trimmed);
            
            if (!normalized || normalized === "AUTO") {
                // Mostrar error en el mismo modal
                document.getElementById('textEditInput').style.borderColor = 'var(--error)';
                setTimeout(() => {
                    document.getElementById('textEditInput').style.borderColor = '';
                }, 2000);
                return;
            }
            
            resolve(normalized);
        };
        
        document.getElementById('textEditModal').classList.remove('hidden');
        document.getElementById('textEditInput').focus();
    });
}

async function persistHistoryEntry(index, nextEntry) {
    const payload = {
        name: nextEntry.name,
        schedule: nextEntry.schedule || {},
        daily_tasks: nextEntry.daily_tasks || {},
        next_sunday_cycle_index: nextEntry.next_sunday_cycle_index ?? null,
        next_sunday_rotation_queue: nextEntry.next_sunday_rotation_queue ?? null,
        week_dates: nextEntry.week_dates ?? null,
        special_days: nextEntry.special_days || {},
        timestamp: nextEntry.timestamp || "",
        metadata: nextEntry.metadata || {},
    };

    const entry = historyEntriesCache[index];
    const patchUrl =
        entry && entry.db_id != null
            ? `/api/history/entry/${entry.db_id}`
            : `/api/history/${index}`;

    const res = await fetch(patchUrl, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });

    if (!res.ok) {
        let detail = "No se pudo guardar el historial.";
        try {
            const err = await res.json();
            detail = err.detail || detail;
        } catch (_) { }
        throw new Error(detail);
    }

    historyEntriesCache[index] = nextEntry;
}

// =====================================================
// HISTORY NAME RENAME / LINK MODAL
// =====================================================
let _historyNameModalState = {
    histIndex: null,
    canonical: null,
    suggestions: [],
    selectedCanonical: null,
};

async function _loadHistoryNameSuggestions() {
    try {
        const res = await fetch('/api/planillas/empleados');
        if (!res.ok) return [];
        const all = await res.json();
        return all
            .filter(e => (e.activo === 1 || e.activo === true)
                && (e.incluir_en_horario === 1 || e.incluir_en_horario === true || e.incluir_en_horario == null))
            .map(e => ({ id: e.id, nombre: e.nombre || "" }))
            .filter(e => e.nombre)
            .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es', { sensitivity: 'base' }));
    } catch (err) {
        console.error("No se pudieron cargar las sugerencias:", err);
        return [];
    }
}

function _renderHistoryNameSuggestions(filterText) {
    const container = document.getElementById('histNameSuggestions');
    if (!container) return;
    const ft = (filterText || "").trim().toLowerCase();
    const list = _historyNameModalState.suggestions
        .filter(s => !ft || s.nombre.toLowerCase().includes(ft));
    if (!list.length) {
        container.innerHTML = `<div style="padding: 0.5rem; font-size: 0.8rem; color: var(--text-muted);">Sin coincidencias. El nombre se guardará como etiqueta libre.</div>`;
        return;
    }
    container.innerHTML = list.slice(0, 20).map(s => `
        <div class="hist-name-option" data-name="${escapeHtmlAttr(s.nombre)}"
             style="padding: 0.45rem 0.6rem; border-radius: 6px; cursor: pointer; font-size: 0.85rem; display: flex; align-items: center; gap: 0.5rem;">
            <i class="fa-solid fa-user" style="color: var(--text-muted); font-size: 0.75rem;"></i>
            <span>${escapeHtmlAttr(s.nombre)}</span>
        </div>
    `).join("");
    container.querySelectorAll('.hist-name-option').forEach(el => {
        el.addEventListener('mouseenter', () => { el.style.background = 'var(--surface-3, rgba(99,102,241,0.12))'; });
        el.addEventListener('mouseleave', () => { el.style.background = 'transparent'; });
        el.addEventListener('click', () => {
            const picked = el.dataset.name;
            const input = document.getElementById('histNameInput');
            if (input) input.value = picked;
            _historyNameModalState.selectedCanonical = picked;
            _updateHistoryNameLinkBadge();
        });
    });
}

function _updateHistoryNameLinkBadge() {
    const badge = document.getElementById('histNameLinkBadge');
    if (!badge) return;
    const input = document.getElementById('histNameInput');
    const text = (input?.value || "").trim();
    const lower = text.toLowerCase();
    const match = _historyNameModalState.suggestions.find(s => s.nombre.toLowerCase() === lower);
    if (match) {
        _historyNameModalState.selectedCanonical = match.nombre;
        badge.style.display = 'block';
        badge.style.color = 'var(--success, #10b981)';
        badge.innerHTML = `<i class="fa-solid fa-link"></i> Vinculado a <b>${escapeHtmlAttr(match.nombre)}</b> — esta semana contará para su rotación.`;
    } else if (text) {
        _historyNameModalState.selectedCanonical = null;
        badge.style.display = 'block';
        badge.style.color = 'var(--text-muted)';
        badge.innerHTML = `<i class="fa-solid fa-tag"></i> Etiqueta libre — la fila seguirá vinculada a <b>${escapeHtmlAttr(_historyNameModalState.canonical || "")}</b> en el motor.`;
    } else {
        _historyNameModalState.selectedCanonical = null;
        badge.style.display = 'none';
    }
}

window.openHistoryNameModal = async function(histIndex, currentCanonical) {
    const entry = historyEntriesCache[histIndex];
    if (!entry) return;
    const aliases = (entry.metadata && entry.metadata.display_aliases) || {};
    const currentDisplay = aliases[currentCanonical] || currentCanonical;

    _historyNameModalState = {
        histIndex,
        canonical: currentCanonical,
        suggestions: [],
        selectedCanonical: null,
    };

    const errorEl = document.getElementById('histNameError');
    if (errorEl) errorEl.style.display = 'none';

    const input = document.getElementById('histNameInput');
    if (input) input.value = currentDisplay || "";

    const container = document.getElementById('histNameSuggestions');
    if (container) container.innerHTML = `<div style="padding: 0.5rem; font-size: 0.8rem; color: var(--text-muted);"><i class="fa-solid fa-spinner fa-spin"></i> Cargando...</div>`;

    document.getElementById('historyNameModal').classList.remove('hidden');
    if (input) input.focus();

    _historyNameModalState.suggestions = await _loadHistoryNameSuggestions();
    _renderHistoryNameSuggestions(currentDisplay);
    _updateHistoryNameLinkBadge();

    if (input && !input._histNameBound) {
        input.addEventListener('input', () => {
            _renderHistoryNameSuggestions(input.value);
            _updateHistoryNameLinkBadge();
        });
        input._histNameBound = true;
    }
};

window.closeHistoryNameModal = function() {
    document.getElementById('historyNameModal').classList.add('hidden');
};

window.confirmHistoryNameEdit = async function() {
    const { histIndex, canonical, suggestions } = _historyNameModalState;
    const entry = historyEntriesCache[histIndex];
    if (!entry) {
        closeHistoryNameModal();
        return;
    }

    const input = document.getElementById('histNameInput');
    const errorEl = document.getElementById('histNameError');
    const text = (input?.value || "").trim();
    if (!text) {
        if (errorEl) {
            errorEl.style.display = 'block';
            errorEl.textContent = 'El nombre no puede estar vacío.';
        }
        return;
    }

    const lower = text.toLowerCase();
    const match = suggestions.find(s => s.nombre.toLowerCase() === lower);

    const nextEntry = cloneHistoryEntry(entry);
    nextEntry.metadata = nextEntry.metadata || {};
    nextEntry.metadata.display_aliases = { ...(nextEntry.metadata.display_aliases || {}) };

    let targetKey = canonical;
    if (match && match.nombre !== canonical) {
        if (nextEntry.schedule && nextEntry.schedule[match.nombre]) {
            if (errorEl) {
                errorEl.style.display = 'block';
                errorEl.textContent = `Ya existe una fila para "${match.nombre}" en este historial. Eliminala antes de vincular.`;
            }
            return;
        }
        nextEntry.schedule = nextEntry.schedule || {};
        if (nextEntry.schedule[canonical]) {
            nextEntry.schedule[match.nombre] = nextEntry.schedule[canonical];
            delete nextEntry.schedule[canonical];
        }
        if (nextEntry.daily_tasks && nextEntry.daily_tasks[canonical]) {
            nextEntry.daily_tasks[match.nombre] = nextEntry.daily_tasks[canonical];
            delete nextEntry.daily_tasks[canonical];
        }
        if (nextEntry.metadata.display_aliases[canonical]) {
            delete nextEntry.metadata.display_aliases[canonical];
        }
        targetKey = match.nombre;
    }

    if (text === targetKey) {
        delete nextEntry.metadata.display_aliases[targetKey];
    } else {
        nextEntry.metadata.display_aliases[targetKey] = text;
    }

    if (Object.keys(nextEntry.metadata.display_aliases).length === 0) {
        delete nextEntry.metadata.display_aliases;
    }

    try {
        await persistHistoryEntry(histIndex, nextEntry);
        closeHistoryNameModal();
        renderHistoryEntryTable(histIndex);
        const msg = match
            ? `Vinculado: "${text}" → ${match.nombre}`
            : `Renombrado: ${canonical} → "${text}"`;
        setStatusMessage(msg, "success");
    } catch (err) {
        console.error(err);
        if (errorEl) {
            errorEl.style.display = 'block';
            errorEl.textContent = err.message || 'Error al guardar.';
        }
    }
};

async function editHistoryShiftBatch(empName, days, histIndex) {
    try {
        const entry = historyEntriesCache[histIndex];
        if (!entry || !empName || !days?.length) {
            clearHistorySelectionStyles();
            return;
        }

        const currentValues = days.map(day => entry.schedule?.[empName]?.[day] || "OFF");
        const sharedValue = currentValues.every(value => value === currentValues[0]) ? currentValues[0] : "";
        const newShift = await promptHistoryShiftValue(empName, days, sharedValue);
        if (!newShift) {
            clearHistorySelectionStyles();
            return;
        }

        const nextEntry = cloneHistoryEntry(entry);
        nextEntry.schedule[empName] = nextEntry.schedule[empName] || {};
        nextEntry.daily_tasks = nextEntry.daily_tasks || {};
        nextEntry.daily_tasks[empName] = nextEntry.daily_tasks[empName] || {};
        days.forEach(day => {
            nextEntry.schedule[empName][day] = newShift;
            nextEntry.daily_tasks[empName][day] = null;
        });

        await persistHistoryEntry(histIndex, nextEntry);
        renderHistoryEntryTable(histIndex);
        setStatusMessage(`Historial actualizado para ${empName}.`, "success");
    } catch (err) {
        console.error(err);
        alert(err.message || "Error al guardar el historial");
    } finally {
        historySelectionState.suppressClick = false;
        historySelectionState.anchorDay = null;
        historySelectionState.currentDay = null;
        historySelectionState.days = [];
        clearHistorySelectionStyles();
    }
}

async function renameHistory(i, event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    
    const entry = historyEntriesCache[i];
    if (!entry) return;
    
    // Usar modal en lugar de prompt
    openTextEditModal("Renombrar Semana", "Nombre", entry.name, async (newName) => {
        if (!newName || newName.trim() === "" || newName === entry.name) return;
        
        entry.name = newName.trim();
        
        // Guardar en el backend
        try {
            const body =
                entry.db_id != null
                    ? { db_id: entry.db_id, name: newName.trim() }
                    : { index: i, name: newName.trim() };
            const res = await fetch('/api/history', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            
            if (!res.ok) {
                alert("No se pudo renombrar el historial.");
                return;
            }
            
            // Actualizar la UI
            const nameSpan = document.querySelector(`.history-item[data-history-index="${i}"] .h-name`);
            if (nameSpan) {
                nameSpan.textContent = newName.trim();
            }
        } catch (e) {
            console.error(e);
            alert("Error al renombrar: " + e.message);
        }
    });
}

// Variables para el modal de edición de texto
let textEditCallback = null;

function openTextEditModal(title, label, defaultValue, callback) {
    document.getElementById('textEditTitle').textContent = title;
    document.getElementById('textEditLabel').textContent = label;
    document.getElementById('textEditInput').value = defaultValue;
    document.getElementById('textEditInput').placeholder = "";
    const legendWrap = document.getElementById('textEditLegendWrap');
    if (legendWrap) legendWrap.style.display = 'none';
    textEditCallback = callback;
    
    document.getElementById('textEditModal').classList.remove('hidden');
    
    // Agregar listener para Enter
    const inputEl = document.getElementById('textEditInput');
    inputEl.onkeydown = (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            confirmTextEdit();
        } else if (e.key === 'Escape') {
            closeTextEditModal();
        }
    };
    
    inputEl.focus();
}

function closeTextEditModal() {
    document.getElementById('textEditModal').classList.add('hidden');
    textEditCallback = null;
    shiftPromptCallback = null;
    const legendWrap = document.getElementById('textEditLegendWrap');
    if (legendWrap) legendWrap.style.display = 'none';
}

// Toggle para tarjetas de parámetros colapsables
function toggleParamCard(header) {
    const card = header.parentElement;
    card.classList.toggle('expanded');
}

function toggleParamGroup(header) {
    const group = header.parentElement;
    group.classList.toggle('collapsed');
}

function confirmTextEdit() {
    const value = document.getElementById('textEditInput').value;
    
    //优先使用 shiftPromptCallback（用于选择班次）
    if (shiftPromptCallback) {
        shiftPromptCallback(value);
        shiftPromptCallback = null;
    } else if (textEditCallback) {
        textEditCallback(value);
    }
    
    closeTextEditModal();
}

async function deleteHistory(i, event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    const entry = historyEntriesCache[i];
    if (!entry) return;
    
    if (!confirm(`¿Mover "${entry.name}" a la papelera?\nPodrás restaurarla dentro de 7 días.`)) return;

    const delUrl =
        entry.db_id != null ? `/api/history/entry/${entry.db_id}` : `/api/history/${i}`;
    const res = await fetch(delUrl, { method: 'DELETE' });
    if (!res.ok) {
        alert("No se pudo mover a la papelera.");
        return;
    }
    
    // Remover del cache local
    historyEntriesCache.splice(i, 1);
    expandedHistoryItems = new Set(
        [...expandedHistoryItems]
            .filter(index => index !== i)
            .map(index => (index > i ? index - 1 : index))
    );
    hiddenHistoryHours = new Set(
        [...hiddenHistoryHours]
            .filter(index => index !== i)
            .map(index => (index > i ? index - 1 : index))
    );
    
    // Recargar papelera y re-renderizar
    await loadTrash();
    renderHistoryList();
    setStatusMessage(`"${entry.name}" movido a la papelera.`, "success");
}

// ── PAPELERA DE RECICLAJE ──
let trashCache = [];

async function loadTrash() {
    try {
        const res = await fetch('/api/history/trash');
        if (!res.ok) return;
        trashCache = await res.json();
    } catch (err) {
        console.error('Error loading trash:', err);
        trashCache = [];
    }
}

async function restoreHistory(i, event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    const entry = trashCache[i];
    if (!entry) return;

    const restoreUrl =
        entry.db_id != null
            ? `/api/history/trash/restore/${entry.db_id}`
            : `/api/history/${i}/restore`;
    const res = await fetch(restoreUrl, { method: 'POST' });
    if (!res.ok) {
        alert("No se pudo restaurar la semana.");
        return;
    }
    
    trashCache.splice(i, 1);
    await fetchHistoryEntries(true);
    renderHistoryList();
    renderTrashList();
    setStatusMessage(`"${entry.name}" restaurada del historial.`, "success");
}

async function permanentDeleteTrash(i, event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    const entry = trashCache[i];
    if (!entry) return;
    
    if (!confirm(`¿Eliminar "${entry.name}" PERMANENTEMENTE?\nEsta acción no se puede deshacer.`)) return;

    const delUrl =
        entry.db_id != null
            ? `/api/history/trash/entry/${entry.db_id}`
            : `/api/history/trash/${i}`;
    const res = await fetch(delUrl, { method: 'DELETE' });
    if (!res.ok) {
        alert("No se pudo eliminar permanentemente.");
        return;
    }
    
    trashCache.splice(i, 1);
    renderTrashList();
    setStatusMessage(`"${entry.name}" eliminada permanentemente.`, "success");
}

async function purgeTrash(event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    if (!confirm('¿Eliminar permanentemente todas las entradas con más de 7 días en la papelera?')) return;

    const res = await fetch('/api/history/trash/purge', { method: 'POST' });
    if (!res.ok) {
        alert("No se pudo purgar la papelera.");
        return;
    }
    
    await loadTrash();
    renderTrashList();
    setStatusMessage("Papelera purgada.", "success");
}

function renderTrashList() {
    const trashContainer = document.getElementById('trashList');
    if (!trashContainer) return;

    if (!trashCache.length) {
        trashContainer.innerHTML = '<div class="empty-msg">La papelera está vacía</div>';
        return;
    }

    trashContainer.innerHTML = trashCache.map((t, i) => {
        const deletedDate = t.deleted_at ? new Date(t.deleted_at).toLocaleDateString() : 'N/A';
        return `
            <div class="trash-item" data-trash-index="${i}">
                <div class="trash-info">
                    <i class="fa-solid fa-trash-can" style="color: var(--error);"></i>
                    <span class="t-name">${t.name}</span>
                    <span class="t-date">Eliminado: ${deletedDate}</span>
                </div>
                <div class="trash-actions">
                    <button type="button" class="btn-icon btn-restore" onclick="restoreHistory(${i}, event)" title="Restaurar">
                        <i class="fa-solid fa-rotate-left"></i> Restaurar
                    </button>
                    <button type="button" class="btn-icon btn-perm-delete" onclick="permanentDeleteTrash(${i}, event)" title="Eliminar permanentemente">
                        <i class="fa-solid fa-ban"></i>
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

function toggleTrashSection() {
    const body = document.getElementById('trashBody');
    const arrow = document.getElementById('trashArrow');
    if (!body) return;
    body.classList.toggle('hidden');
    if (arrow) arrow.classList.toggle('rotated');
}

async function downloadExcel(url) {
    const status = document.getElementById("statusMessage");
    const previousStatus = status ? status.innerHTML : "";

    if (status) {
        status.innerHTML = '<i class="fa-solid fa-file-excel"></i> Exportando Excel...';
    }

    try {
        const res = await fetch(url);

        if (!res.ok) {
            let detail = "No se pudo exportar el horario.";
            try {
                const err = await res.json();
                detail = err.detail || detail;
            } catch (_) { }
            throw new Error(detail);
        }

        const blob = await res.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        const contentDisposition = res.headers.get("content-disposition") || "";
        const match = contentDisposition.match(/filename="?([^";]+)"?/i);
        const exportedFilename = match ? match[1] : "horario.xlsx";

        link.href = downloadUrl;
        link.download = exportedFilename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(downloadUrl);

        // Show confirmation modal
        showExportConfirmationModal(exportedFilename);

        if (status) {
            status.innerHTML = '<i class="fa-solid fa-check"></i> Exportación completada';
        }
    } catch (e) {
        if (status) {
            status.innerHTML = `<span class="error"><i class="fa-solid fa-circle-xmark"></i> ${e.message}</span>`;
        } else {
            alert(e.message);
        }
    } finally {
        if (status) {
            setTimeout(() => {
                status.innerHTML = previousStatus;
            }, 4000);
        }
    }
}

function showExportConfirmationModal(filename, type = 'excel') {
    // Remove existing modal if any
    let existing = document.getElementById("exportConfirmModal");
    if (existing) existing.remove();

    const titles = {
        excel: { icon: 'fa-file-excel', color: '#10b981', msg: 'Excel exportado exitosamente' },
        image: { icon: 'fa-image', color: '#3b82f6', msg: 'Imagen exportada exitosamente' },
    };
    const cfg = titles[type] || titles.excel;

    const modal = document.createElement("div");
    modal.id = "exportConfirmModal";
    modal.className = "modal-backdrop";
    modal.innerHTML = `
        <div class="modal-dialog" style="max-width: 440px; animation: modalSpringUp 0.35s cubic-bezier(0.175, 0.885, 0.32, 1.2) both;">
            <div class="modal-content" style="text-align: center; padding: 2rem;">
                <div style="margin-bottom: 1.25rem;">
                    <div style="width: 64px; height: 64px; border-radius: 50%; background: linear-gradient(135deg, ${cfg.color}, ${cfg.color}dd); display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem;">
                        <i class="fa-solid fa-check" style="font-size: 1.75rem; color: white;"></i>
                    </div>
                    <h3 style="margin: 0 0 0.5rem; font-size: 1.2rem; color: var(--text-main);">${cfg.msg}</h3>
                    <p style="margin: 0; color: var(--text-muted); font-size: 0.9rem;">
                        <i class="fa-solid ${cfg.icon}" style="color: ${cfg.color}; margin-right: 4px;"></i>
                        ${_escapeHtml(filename)}
                    </p>
                </div>
                <div style="display: flex; gap: 0.75rem; justify-content: center; flex-wrap: wrap;">
                    <button type="button" onclick="openExportFolder(); closeExportConfirmModal();"
                        class="action-btn" style="background: linear-gradient(135deg, #3b82f6, #2563eb); color: white; border: none; padding: 0.6rem 1.25rem; border-radius: 8px; cursor: pointer; font-size: 0.9rem; display: inline-flex; align-items: center; gap: 6px;">
                        <i class="fa-solid fa-folder-open"></i> Abrir carpeta
                    </button>
                    <button type="button" onclick="closeExportConfirmModal();"
                        class="action-btn" style="background: var(--bg-card); color: var(--text-main); border: 1px solid var(--border-color); padding: 0.6rem 1.25rem; border-radius: 8px; cursor: pointer; font-size: 0.9rem;">
                        Cerrar
                    </button>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(modal);

    // Close on backdrop click
    modal.addEventListener("click", (e) => {
        if (e.target === modal) closeExportConfirmModal();
    });
}

function closeExportConfirmModal() {
    const modal = document.getElementById("exportConfirmModal");
    if (modal) modal.remove();
}

async function openExportFolder() {
    try {
        await fetch("/api/open_export_folder", { method: "POST" });
    } catch (e) {
        console.error("Error opening export folder:", e);
    }
}

function _escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function escapeHtml(text) {
    return _escapeHtml(text);
}

function exportToExcel() {
    downloadExcel("/api/export_excel");
}

async function renderScheduleCaptureCanvas(captureElement) {
    if (!captureElement) {
        throw new Error("No se encontro el contenedor para exportar.");
    }

    const rect = captureElement.getBoundingClientRect();
    const captureWidth = Math.ceil(Math.max(captureElement.scrollWidth || 0, rect.width || 0));
    const captureHeight = Math.ceil(Math.max(captureElement.scrollHeight || 0, rect.height || 0));
    const exportToken = `export-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const bodyBg = getComputedStyle(document.body).backgroundColor || (
        document.body.classList.contains("dark-mode") ? "#0f172a" : "#ffffff"
    );

    captureElement.dataset.exportCaptureId = exportToken;

    try {
        return await html2canvas(captureElement, {
            scale: 2,
            useCORS: true,
            backgroundColor: bodyBg,
            width: captureWidth,
            height: captureHeight,
            windowWidth: Math.max(window.innerWidth, captureWidth),
            windowHeight: Math.max(window.innerHeight, captureHeight),
            onclone: (clonedDocument) => {
                const clone = clonedDocument.querySelector(`[data-export-capture-id="${exportToken}"]`);
                if (!clone) return;

                clone.style.overflow = "visible";
                clone.style.width = `${captureWidth}px`;
                clone.style.minWidth = `${captureWidth}px`;
                clone.style.maxWidth = "none";
                clone.style.height = "auto";
                clone.style.maxHeight = "none";
                clone.style.margin = "0";
                clone.style.transform = "none";
                clone.style.contain = "none";

                clone.querySelectorAll(".shift-pill").forEach((element) => {
                    element.style.boxShadow = "none";
                    element.style.filter = "none";
                    element.style.transform = "none";
                    element.style.transition = "none";
                    element.style.outline = "none";
                    element.style.willChange = "auto";
                    element.style.boxSizing = "border-box";
                });

                clone.querySelectorAll(".history-shift-pill.history-pill-selected").forEach((element) => {
                    element.style.outline = "none";
                    element.style.boxShadow = "none";
                    element.style.transform = "none";
                });

                clone.querySelectorAll("*").forEach((element) => {
                    const computed = clonedDocument.defaultView.getComputedStyle(element);
                    if (computed.position === "sticky") {
                        element.style.position = "static";
                        element.style.top = "auto";
                        element.style.left = "auto";
                        element.style.zIndex = "auto";
                    }
                });
            },
        });
    } finally {
        delete captureElement.dataset.exportCaptureId;
    }
}

async function exportToImage() {
    const captureElement = document.getElementById("scheduleCapture");
    if (!captureElement) return;

    try {
        const canvas = await renderScheduleCaptureCanvas(captureElement);
        const filename = 'horario_completo.png';
        const imgData = canvas.toDataURL("image/png");
        const link = document.createElement('a');
        link.download = filename;
        link.href = imgData;
        link.click();

        const saveRes = await fetch(`${API_URL}/export_image`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image_data: imgData, filename })
        });
        if (!saveRes.ok) {
            let detail = "No se pudo guardar la imagen en export_horarios.";
            try { const err = await saveRes.json(); detail = err.detail || detail; } catch (_) {}
            throw new Error(detail);
        }

        showExportConfirmationModal(filename, 'image');
    } catch (err) {
        console.error("Capture failed:", err);
        alert(err.message || "Error al exportar imagen");
    }
}

function toggleHoursColumn() {
    const targets = document.querySelectorAll(".col-hours");
    targets.forEach(el => el.classList.toggle("hidden-col"));
}

// =====================================================
// SCHEDULE HEADER ACTIONS DROPDOWN
// =====================================================
window.toggleScheduleActionsMenu = function (event) {
    if (event) event.stopPropagation();
    const dropdown = document.getElementById("scheduleActionsDropdown");
    const trigger = document.getElementById("btnScheduleActionsMenu");
    if (!dropdown) return;
    const isOpen = !dropdown.classList.contains("hidden");
    if (isOpen) {
        dropdown.classList.add("hidden");
        if (trigger) trigger.setAttribute("aria-expanded", "false");
    } else {
        dropdown.classList.remove("hidden");
        if (trigger) trigger.setAttribute("aria-expanded", "true");
        // Cerrar al hacer click fuera
        setTimeout(() => {
            const handler = (e) => {
                if (!dropdown.contains(e.target) && e.target !== trigger && !trigger?.contains(e.target)) {
                    dropdown.classList.add("hidden");
                    if (trigger) trigger.setAttribute("aria-expanded", "false");
                    document.removeEventListener("click", handler);
                }
            };
            document.addEventListener("click", handler);
        }, 0);
    }
};

window.closeScheduleActionsMenu = function () {
    const dropdown = document.getElementById("scheduleActionsDropdown");
    const trigger = document.getElementById("btnScheduleActionsMenu");
    if (dropdown) dropdown.classList.add("hidden");
    if (trigger) trigger.setAttribute("aria-expanded", "false");
};

async function toggleValidation() {
    isValidationOn = !isValidationOn;
    const btn = document.getElementById("btnToggleValidation");
    if (isValidationOn) {
        btn.classList.add("primary");
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Cargando...`;

        try {
            await refreshScheduleValidationRules(currentMetadata?.special_days || getSpecialDaysPayload());
            btn.innerHTML = `<i class="fa-solid fa-check"></i> Validación activa`;
        } catch (err) {
            console.error("Error fetching validation rules:", err);
            alert("Error al obtener reglas de validaci\u00f3n del servidor.\n\n\u00bfEst\u00e1 el servidor corriendo?");
            btn.innerHTML = `<i class="fa-solid fa-check-double"></i> Validaci\u00f3n`;
            btn.classList.remove("primary");
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
        const restPanel = document.getElementById("restBetweenShiftsPanel");
        if (restPanel) restPanel.style.display = "none";
        // Cerrar también el overlay (sin pasar por closeValidatorOverlay para evitar
        // recursión: closeValidatorOverlay llama a toggleValidation cuando está ON).
        const overlay = document.getElementById("validatorOverlay");
        if (overlay) {
            overlay.classList.remove("val-overlay-visible");
            overlay.classList.add("val-overlay-hidden");
        }
        // Asegurar que cualquier pill viejo del DOM no sobreviva.
        const stale = document.getElementById("validatorReopenBtn");
        if (stale) stale.remove();
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
    ["validationSummaryPanel", "coverageInfoPanel", "restBetweenShiftsPanel"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.remove();
    });

    if (!isValidationOn || !currentGeneratedSchedule) return;

    const formatHour = (h) => {
        let d = h >= 24 ? h - 24 : h;
        let h12 = d % 12 || 12;
        return `${h12}${d >= 12 && d < 24 ? "PM" : "AM"}`;
    };
    const overstaffPolicy = validationRules.overstaff_policy || {};
    const capValue = overstaffPolicy.cap_value ?? 5;
    const allowedHoursAtCap = overstaffPolicy.allowed_hours_at_cap_per_day ?? 1;
    const cappedDays = new Set(overstaffPolicy.limited_days || overstaffPolicy.days || []);
    const getMinReq = (day, h) => validationRules.bounds[day]?.[String(h)] ?? 0;
    const getSoftReq = (day, h) => validationRules.soft_bounds?.[day]?.[String(h)] ?? getMinReq(day, h);
    const getMaxReq = (day, h) => validationRules.max_bounds?.[day]?.[String(h)] ?? Number.POSITIVE_INFINITY;
    const formatCapHours = (hours) => hours.length ? hours.join(", ") : "ninguna";

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
                getShiftHoursList(s).forEach(h => {
                    if (coverage[h] !== undefined) coverage[h]++;
                });
            }
        });

        allCoverage[day] = coverage;

        let errors = [];
        let warnings = [];
        let capHours = [];
        for (let h = 5; h <= 28; h++) {
            const minReq = getMinReq(day, h);
            const softReq = getSoftReq(day, h);
            const maxReq = getMaxReq(day, h);
            const actual = coverage[h];
            const label = formatHour(h);
            if (minReq > 0 && actual < minReq) {
                errors.push({ type: "under", label, actual, minReq, softReq, maxReq });
            } else if (actual > maxReq) {
                errors.push({ type: "over", label, actual, minReq, softReq, maxReq });
            } else if (softReq > minReq && actual < softReq) {
                warnings.push({ type: "soft", label, actual, minReq, softReq, maxReq });
            }

            if (cappedDays.has(day) && maxReq === capValue && actual === capValue) {
                capHours.push(label);
            }
        }

        const capStatus = !cappedDays.has(day)
            ? "ok"
            : capHours.length > allowedHoursAtCap
                ? "error"
                : capHours.length > 0
                    ? "warn"
                    : "ok";
        if (capStatus === "error") {
            errors.unshift({
                type: "cap_limit",
                actual: capHours.length,
                allowed: allowedHoursAtCap,
                capValue,
                hours: capHours
            });
        }

        dayResults[day] = {
            errors,
            warnings,
            colIndex: index + 2,
            capStatus,
            capHours,
            capHoursUsed: capHours.length,
            capHoursAllowed: allowedHoursAtCap
        };

        const isDayValid = errors.length === 0;
        const hasWarns = warnings.length > 0 || capStatus === "warn";
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
        ok: { icon: "fa-circle-check", label: "Horario optimo", cls: "vb-ok" },
        warn: { icon: "fa-circle-exclamation", label: "Sub-optimo", cls: "vb-warn" },
        error: { icon: "fa-triangle-exclamation", label: "Incumple reglas", cls: "vb-error" }
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
            const minReq = getMinReq(day, h);
            const softReq = getSoftReq(day, h);
            const maxReq = getMaxReq(day, h);
            const capExceeded = dayResults[day].capStatus === "error" && count === capValue && maxReq === capValue;
            const atCap = cappedDays.has(day) && count === capValue && maxReq === capValue;
            let cls = "hmc-ok";
            if (capExceeded) cls = "hmc-cap";
            else if (count < minReq) cls = "hmc-under";
            else if (count > maxReq) cls = "hmc-over";
            else if (count < softReq || atCap) cls = "hmc-warn";
            const intensityBase = Math.max(softReq || 0, minReq || 0, 1);
            const intensity = Math.min(count / intensityBase, 1);
            const capText = cappedDays.has(day)
                ? ` | tolerancia ${dayResults[day].capHoursUsed}/${allowedHoursAtCap} en ${capValue}`
                : "";
            const stateHint =
                cls === "hmc-under"
                    ? " — por debajo del mínimo"
                    : cls === "hmc-over"
                      ? " — por encima del máximo"
                      : cls === "hmc-cap"
                        ? " — exceso en tolerancia de plantilla"
                        : cls === "hmc-warn"
                          ? " — subóptimo / en tope"
                          : "";
            const tooltip = `${day} ${formatHour(h)}: ${count} pers. (min ${minReq}, ideal ${softReq}, max ${maxReq}${capText})${stateHint}`;
            return `<div class="hm-cell ${cls}" title="${tooltip}" style="--intensity:${intensity.toFixed(2)}">${count}</div>`;
        }).join("");
        return `<div class="hm-row">${hourLabel}${cells}</div>`;
    }).join("");

    const dayHeaders = DAYS.map(d => `<div class="hm-day-label">${d}</div>`).join("");

    hmEl.innerHTML = `
        <div class="val-heatmap-header">
            <span><i class="fa-solid fa-fire"></i> Mapa de Calor - Cobertura por Hora</span>
            <div class="hm-legend">
                <span class="hml hml-ok">Ideal</span>
                <span class="hml hml-warn">Sub-optimo</span>
                <span class="hml hml-under">Bajo mínimo</span>
                <span class="hml hml-over">Sobre máximo</span>
                <span class="hml hml-cap">Tolerancia tope</span>
            </div>
        </div>
        <div class="hm-grid">
            <div class="hm-row hm-header-row"><div class="hm-hour"></div>${dayHeaders}</div>
            ${hmCells}
        </div>`;

    // === Descanso entre turnos (metadata del solver o cálculo local) ===
    const restSrc =
        currentMetadata?.rest_between_shifts ||
        buildRestReportClient(currentGeneratedSchedule, currentMetadata?.min_rest_hours_target ?? 12);
    const targetRest = currentMetadata?.min_rest_hours_target ?? restSrc.target_hours ?? 12;
    const appliedRest =
        currentMetadata?.min_rest_hours_applied != null
            ? currentMetadata.min_rest_hours_applied
            : restSrc.applied_hours != null
              ? restSrc.applied_hours
              : targetRest;
    const perRest = restSrc.per_employee || {};
    const restNames = Object.keys(perRest).sort((a, b) => a.localeCompare(b, "es"));
    const showRelaxedBand = appliedRest < targetRest;

    const restGapClass = (hours) => {
        if (hours < appliedRest) return "rest-gap-bad";
        if (hours < targetRest) return "rest-gap-relaxed";
        return "rest-gap-ok";
    };

    let restBanner = "";
    if (appliedRest < targetRest) {
        restBanner = `<div class="val-rest-banner val-rest-banner-relaxed"><i class="fa-solid fa-moon"></i> El generador aplicó <strong>${appliedRest}h</strong> de descanso mínimo entre turnos laborables (objetivo <strong>${targetRest}h</strong>).</div>`;
    } else {
        restBanner = `<div class="val-rest-banner val-rest-banner-ok"><i class="fa-solid fa-bed"></i> Descanso mínimo aplicado: <strong>${appliedRest}h</strong> (objetivo <strong>${targetRest}h</strong>).</div>`;
    }
    if (restSrc.client_only) {
        restBanner += `<div class="val-rest-note"><i class="fa-solid fa-circle-info"></i> Estimación en el navegador (entrada sin metadata del solver); mismas reglas de horas que el motor.</div>`;
    }

    const restCards = restNames.map((name) => {
        const row = perRest[name] || {};
        if (row.skipped) {
            return `<div class="rest-card rest-card-skipped"><div class="rest-card-top"><span class="rest-name">${escapeHtmlAttr(name)}</span><span class="rest-pill rest-pill-skip">Sin regla</span></div><div class="rest-card-body">Exento de descanso mínimo entre turnos.</div></div>`;
        }
        const minG = row.min_gap_hours;
        const meetsApplied =
            typeof row.meets_applied === "boolean"
                ? row.meets_applied
                : minG == null || minG >= appliedRest;
        const meetsTarget =
            typeof row.meets_target === "boolean" ? row.meets_target : minG == null || minG >= targetRest;
        const minLabel = minG == null ? "—" : `${minG}h`;
        const minPill =
            minG == null
                ? "rest-pill-neutral"
                : !meetsApplied
                  ? "rest-pill-bad"
                  : !meetsTarget
                    ? "rest-pill-warn"
                    : "rest-pill-ok";
        const gaps = (row.gaps || [])
            .map(
                (g) =>
                    `<span class="rest-gap ${restGapClass(g.hours)}" title="${escapeHtmlAttr(g.from)} → ${escapeHtmlAttr(g.to)}: ${g.hours}h">${escapeHtmlAttr(g.from)}→${escapeHtmlAttr(g.to)}: <strong>${g.hours}h</strong></span>`
            )
            .join("");
        const gapsHtml = gaps || `<span class="rest-no-gaps">Sin pares de turnos consecutivos en la semana.</span>`;
        return `<div class="rest-card"><div class="rest-card-top"><span class="rest-name">${escapeHtmlAttr(name)}</span><span class="rest-pill ${minPill}">Mín: ${minLabel}</span></div><div class="rest-gaps-row">${gapsHtml}</div></div>`;
    }).join("");

    const restEl = document.createElement("div");
    restEl.id = "restBetweenShiftsPanel";
    restEl.className = "val-rest-wrap";
    restEl.innerHTML = `
        <div class="val-heatmap-header">
            <span><i class="fa-solid fa-hourglass-half"></i> Descanso entre turnos consecutivos</span>
            <div class="rest-legend">
                <span class="rest-leg rest-leg-ok">≥ ${targetRest}h (objetivo)</span>
                ${showRelaxedBand ? `<span class="rest-leg rest-leg-relaxed">${appliedRest}h–${targetRest - 1}h (relajado)</span>` : ""}
                <span class="rest-leg rest-leg-bad">&lt; ${appliedRest}h (incumple mínimo aplicado)</span>
            </div>
        </div>
        ${restBanner}
        <div class="rest-cards-grid">${restCards}</div>`;

    // === BUILD DAY CARDS ===
    const cardsHTML = DAYS.map(day => {
        const { errors, warnings, colIndex, capStatus, capHours, capHoursUsed, capHoursAllowed } = dayResults[day];
        const st = errors.length > 0 ? "error" : (warnings.length > 0 || capStatus === "warn") ? "warn" : "ok";
        const cfg = {
            ok: { icon: "<i class=\"fa-solid fa-check\"></i>", pill: "Optimo", pillCls: "vpill-ok" },
            warn: { icon: "<i class=\"fa-solid fa-triangle-exclamation\"></i>", pill: "Sub-optimo", pillCls: "vpill-warn" },
            error: { icon: "<i class=\"fa-solid fa-ban\"></i>", pill: "Incumple", pillCls: "vpill-error" }
        }[st];

        const errorDetails = errors.map(e => {
            if (e.type === "cap_limit") {
                return `<div class="vcard-detail vcard-cap"><i class="fa-solid fa-ban"></i>Tolerancia ${e.capValue} personas: ${e.actual}/${e.allowed} horas (${formatCapHours(e.hours)})</div>`;
            }
            if (e.type === "over") {
                return `<div class="vcard-detail vcard-over"><i class="fa-solid fa-arrow-up"></i>${e.label}: ${e.actual} pers. (máx. ${e.maxReq})</div>`;
            }
            return `<div class="vcard-detail vcard-under"><i class="fa-solid fa-arrow-down"></i>${e.label}: ${e.actual} pers. (mín. ${e.minReq})</div>`;
        });
        const warningDetails = warnings.map(w =>
            `<div class="vcard-detail vcard-wrn"><i class="fa-solid fa-arrow-up"></i>${w.label}: ${w.actual}->${w.softReq} ideal</div>`
        );
        const toleranceClass = capStatus === "error" ? "vcard-cap" : capStatus === "warn" ? "vcard-wrn" : "vcard-ok";
        const toleranceIcon = capStatus === "error" ? "fa-solid fa-ban" : capStatus === "warn" ? "fa-solid fa-clock" : "fa-solid fa-check";
        const toleranceLine = cappedDays.has(day)
            ? `<div class="vcard-detail ${toleranceClass}"><i class="${toleranceIcon}"></i>Tolerancia ${capValue} personas: ${capHoursUsed}/${capHoursAllowed}${capHours.length ? ` (${formatCapHours(capHours)})` : ""}</div>`
            : "";

        let details = [...errorDetails, ...warningDetails, toleranceLine].join("")
            || `<div class="vcard-detail vcard-ok"><i class="fa-solid fa-check"></i>Sin problemas</div>`;

        let allHoursHTML = `<div class="vcard-all-hours">`;
        for (let h = 5; h <= 28; h++) {
            const actual = allCoverage[day][h] || 0;
            const minReq = getMinReq(day, h);
            const softReq = getSoftReq(day, h);
            const maxReq = getMaxReq(day, h);
            if (actual === 0 && minReq === 0) continue;
            const capExceeded = dayResults[day].capStatus === "error" && actual === capValue && maxReq === capValue;
            const atCap = cappedDays.has(day) && actual === capValue && maxReq === capValue;
            let pillCls = "vhp-neutral";
            if (capExceeded) pillCls = "vhp-cap";
            else if (actual < minReq) pillCls = "vhp-under";
            else if (actual > maxReq) pillCls = "vhp-over";
            else if (actual < softReq || atCap) pillCls = "vhp-warn";
            else if (actual > 0 || minReq > 0) pillCls = "vhp-ok";
            allHoursHTML += `<div class="vhp ${pillCls}" title="min ${minReq} | ideal ${softReq} | max ${maxReq}"><span class="vhp-time">${formatHour(h)}:</span> ${actual}p <span class="vhp-bounds">[${minReq}/${softReq}/${maxReq}]</span></div>`;
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
            <span class="val-subtitle">${hasGlobalErrors ? "Hay horas por debajo del mínimo, por encima del máximo o fuera de la tolerancia diaria (leyenda: colores distintos para cada caso)" : hasGlobalWarnings ? "Hay horas por debajo del ideal o en tope de plantilla; revise el mapa y las tarjetas" : "Todos los días cumplen mínimos, máximos y tolerancias"}</span>
        </div>
        <div class="vcards-row">${cardsHTML}</div>`;

    // Build overlay contents

    overlay.innerHTML = `
        <div class="val-overlay-backdrop" onclick="closeValidatorOverlay()"></div>
        <div class="val-overlay-panel">
            <div class="val-overlay-topbar">
                <span class="val-overlay-title"><i class="fa-solid fa-shield-check"></i> Validacion de reglas y cobertura</span>
                <button class="val-overlay-close" onclick="closeValidatorOverlay()" title="Cerrar validación">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            </div>
            <div class="val-overlay-body" id="valOverlayBody"></div>
        </div>`;

    const body = overlay.querySelector("#valOverlayBody");
    body.appendChild(summaryEl);
    body.appendChild(hmEl);
    body.appendChild(restEl);

    overlay.classList.remove("val-overlay-hidden");
    overlay.classList.add("val-overlay-visible");
}

// Cierre del overlay = apaga la validación completa.
// El botón principal "Validación" del header es el único punto de control:
// no usamos un pill flotante separado, evita duplicidad y se siente más limpio.
function closeValidatorOverlay() {
    const overlay = document.getElementById("validatorOverlay");
    if (overlay) {
        overlay.classList.remove("val-overlay-visible");
        overlay.classList.add("val-overlay-hidden");
    }
    // Si la validación estaba activa, sincronizar el botón principal apagándola.
    if (typeof isValidationOn !== "undefined" && isValidationOn) {
        try {
            toggleValidation();
        } catch (err) {
            console.error("Error al apagar validación desde el overlay:", err);
        }
    }
    // Por si alguna versión previa dejó pegado el pill flotante en el DOM,
    // lo removemos para no mostrar dos puntos de control.
    const stale = document.getElementById("validatorReopenBtn");
    if (stale) stale.remove();
}

// Compatibilidad con código existente que pueda invocar reopen.
function reopenValidatorOverlay() {
    const overlay = document.getElementById("validatorOverlay");
    if (overlay) {
        overlay.classList.remove("val-overlay-hidden");
        overlay.classList.add("val-overlay-visible");
    }
}


function exportHistoryExcel(index, event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    const entry = historyEntriesCache[index];
    // Preferimos db_id para evitar desincronía entre índice del array y orden en SQLite.
    // Fallback al índice posicional si por alguna razón no hay db_id.
    const param = (entry && entry.db_id != null)
        ? `history_db_id=${entry.db_id}`
        : `history_index=${index}`;
    downloadExcel(`/api/export_excel?${param}`);
}

window.toggleHistoryHours = function (index, event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }

    if (hiddenHistoryHours.has(index)) {
        hiddenHistoryHours.delete(index);
    } else {
        hiddenHistoryHours.add(index);
    }

    applyHistoryHoursVisibility(index);

    const button = document.querySelector(`[data-history-hours-button="${index}"]`);
    if (button) {
        const isVisible = !hiddenHistoryHours.has(index);
        button.classList.toggle("is-active", isVisible);
        button.setAttribute("aria-pressed", isVisible ? "true" : "false");
    }
};

// Modal para marcar días como feriados en el historial
let holidayModalData = { histIndex: null };

window.toggleDayAsHoliday = function(index, event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    
    const entry = historyEntriesCache[index];
    if (!entry) return;
    
    holidayModalData = { histIndex: index };
    
    // Leer días ya marcados como feriado
    const existingHolidays = entry.metadata?.holiday_days || {};
    
    // Construir HTML del modal
    const modalHtml = `
        <div id="holidayModal" class="modal-backdrop">
            <div class="modal-dialog" style="max-width: 400px;">
                <div class="modal-content">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; border-bottom: 1px solid var(--border-color); padding-bottom: 0.75rem;">
                        <h3 style="margin: 0; font-size: 1.1rem;">Marcar Día como Feriado</h3>
                        <button type="button" onclick="closeHolidayModal()" style="background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 1.25rem;">
                            <i class="fa-solid fa-xmark"></i>
                        </button>
                    </div>
                    <p class="helper-text" style="margin-bottom: 1rem;">
                        <i class="fa-solid fa-info-circle"></i> 
                        Seleccioná el día de la semana para marcarlo como feriado. Esto agregará la fila de feriados en la planilla.
                    </p>
                    <div id="holidayDaysContainer" style="display: flex; flex-direction: column; gap: 0.5rem;">
                        ${DAYS.map(d => {
                            const isChecked = !!existingHolidays[d];
                            const holidayName = existingHolidays[d] || "";
                            return `
                                <label style="display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem; background: var(--surface-2); border-radius: 8px; cursor: pointer; border: 1px solid ${isChecked ? 'var(--primary)' : 'var(--border-color)'};">
                                    <input type="checkbox" class="holiday-day-checkbox" data-day="${d}" ${isChecked ? 'checked' : ''} 
                                        style="width: 18px; height: 18px; accent-color: var(--primary);"
                                        onchange="toggleHolidayDayInput('${d}', this.checked)">
                                    <span style="font-weight: 600; min-width: 50px;">${d}</span>
                                    <input type="text" id="holidayName_${d}" class="custom-input" 
                                        placeholder="Nombre del feriados (ej: Fiesta Purís)"
                                        value="${holidayName}"
                                        style="flex: 1; padding: 0.4rem; font-size: 0.85rem; ${isChecked ? '' : 'display: none;'}"
                                        ${isChecked ? '' : 'disabled'}>
                                </label>
                            `;
                        }).join('')}
                    </div>
                    <div class="modal-actions" style="margin-top: 1rem;">
                        <button type="button" class="btn-text" onclick="closeHolidayModal()">Cancelar</button>
                        <button type="button" class="btn-action primary" onclick="saveHolidayDays()">Guardar</button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Remover modal existente
    const existing = document.getElementById('holidayModal');
    if (existing) existing.remove();
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    document.getElementById('holidayModal').classList.remove('hidden');
};

window.toggleHolidayDayInput = function(day, checked) {
    const input = document.getElementById(`holidayName_${day}`);
    if (input) {
        input.style.display = checked ? 'block' : 'none';
        input.disabled = !checked;
        if (!checked) input.value = '';
    }
};

window.closeHolidayModal = function() {
    const modal = document.getElementById('holidayModal');
    if (modal) modal.remove();
};

function syncHolidayDayModalNameField() {
    const cb = document.getElementById("holidayDayCheckbox");
    const inp = document.getElementById("holidayNameInput");
    if (!cb || !inp) return;
    const on = cb.checked;
    inp.disabled = !on;
    inp.style.display = on ? "block" : "none";
    if (on) {
        requestAnimationFrame(() => {
            void inp.offsetHeight;
            inp.focus();
        });
    }
}

// Abrir modal para marcar un día específico como feriado (click en columna del día)
window.openHolidayDayModal = function(day, histIndex) {
    if (histIndex < 0) return; // Solo para historial
    
    const entry = historyEntriesCache[histIndex];
    if (!entry) return;
    
    holidayModalData = { histIndex, day };
    
    // Leer días ya marcados como feriado
    const existingHolidays = entry.metadata?.holiday_days || {};
    const isChecked = !!existingHolidays[day];
    const holidayName = existingHolidays[day] || "";
    
    // Construir HTML del modal para un solo día
    const modalHtml = `
        <div id="holidayModal" class="modal-backdrop">
            <div class="modal-dialog" style="max-width: 350px;">
                <div class="modal-content">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; border-bottom: 1px solid var(--border-color); padding-bottom: 0.75rem;">
                        <h3 style="margin: 0; font-size: 1.1rem;">Marcar ${day} como Feriado</h3>
                        <button type="button" onclick="closeHolidayModal()" style="background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 1.25rem;">
                            <i class="fa-solid fa-xmark"></i>
                        </button>
                    </div>
                    <p class="helper-text" style="margin-bottom: 1rem;">
                        <i class="fa-solid fa-info-circle"></i> 
                        Esto agregará la fila de feriados en la planilla para este día.
                    </p>
                    <div style="margin-bottom: 1rem;">
                        <label class="option-card hover-glow holiday-modal-toggle-row" style="padding: 12px 16px; display: flex; align-items: center; gap: 12px; cursor: pointer;">
                            <div class="toggle-container" style="flex-shrink: 0;">
                                <input type="checkbox" id="holidayDayCheckbox" ${isChecked ? 'checked' : ''} 
                                    class="toggle-checkbox"
                                    onchange="syncHolidayDayModalNameField()">
                                <div class="toggle-slider"></div>
                            </div>
                            <div class="opt-content" style="flex: 1;">
                                <div class="opt-icon" style="background: rgba(245, 158, 11, 0.1); color: #f59e0b;">
                                    <i class="fa-solid fa-star"></i>
                                </div>
                                <div class="opt-text">
                                    <strong style="font-size: 0.9rem;">Marcar como feriado</strong>
                                </div>
                            </div>
                        </label>
                        <input type="text" id="holidayNameInput" class="custom-input holiday-modal-name-input" 
                            placeholder="Nombre (vacío = Feriado (${day}))"
                            value="${escapeHtmlAttr(holidayName)}"
                            style="width: 100%; margin-top: 0.75rem; padding: 0.6rem 0.8rem; ${isChecked ? '' : 'display: none;'}"
                            ${isChecked ? '' : 'disabled'}>
                    </div>
                    <div class="modal-actions" style="margin-top: 1rem;">
                        <button type="button" class="btn-text" onclick="closeHolidayModal()">Cancelar</button>
                        <button type="button" class="btn-action primary" onclick="saveSingleHolidayDay()">Guardar</button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Remover modal existente
    const existing = document.getElementById('holidayModal');
    if (existing) existing.remove();
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    document.getElementById('holidayModal').classList.remove('hidden');
    syncHolidayDayModalNameField();
};

window.saveSingleHolidayDay = async function() {
    const { histIndex, day } = holidayModalData;
    const entry = historyEntriesCache[histIndex];
    if (!entry) {
        console.error("No entry found for histIndex:", histIndex);
        return;
    }
    
    const checkbox = document.getElementById('holidayDayCheckbox');
    const nameInput = document.getElementById('holidayNameInput');
    
    const holidayDays = { ...(entry.metadata?.holiday_days || {}) };
    
    if (checkbox && checkbox.checked && nameInput) {
        const raw = nameInput.value.trim();
        holidayDays[day] = raw || `Feriado (${day})`;
    } else {
        delete holidayDays[day];
    }

    // Actualizar metadata
    const nextEntry = cloneHistoryEntry(entry);
    nextEntry.metadata = nextEntry.metadata || {};
    nextEntry.metadata.holiday_days = holidayDays;

    const savedDbId = nextEntry.db_id ?? historyEntriesCache[histIndex]?.db_id;

    try {
        await persistHistoryEntry(histIndex, nextEntry);

        await fetchHistoryEntries(true);

        let renderIdx = histIndex;
        if (savedDbId != null) {
            const found = historyEntriesCache.findIndex((e) => e.db_id === savedDbId);
            if (found >= 0) renderIdx = found;
        }

        closeHolidayModal();
        renderHistoryEntryTable(renderIdx);
        setStatusMessage(
            checkbox && checkbox.checked ? `${day} marcado como feriado.` : `${day}: feriado quitado.`,
            "success"
        );
    } catch (err) {
        console.error("Error saving holiday:", err);
        setStatusMessage("Error al guardar: " + err.message, "error");
    }
};

window.saveHolidayDays = async function() {
    const { histIndex } = holidayModalData;
    const entry = historyEntriesCache[histIndex];
    if (!entry) return;
    
    // Recolectar días marcados
    const holidayDays = {};
    DAYS.forEach(d => {
        const checkbox = document.querySelector(`.holiday-day-checkbox[data-day="${d}"]`);
        const nameInput = document.getElementById(`holidayName_${d}`);
        if (checkbox && checkbox.checked && nameInput) {
            const name = nameInput.value.trim();
            holidayDays[d] = name || `Feriado (${d})`;
        }
    });
    
    // Actualizar metadata
    const nextEntry = cloneHistoryEntry(entry);
    nextEntry.metadata = nextEntry.metadata || {};
    nextEntry.metadata.holiday_days = holidayDays;
    
    try {
        await persistHistoryEntry(histIndex, nextEntry);
        await fetchHistoryEntries(true);
        closeHolidayModal();
        renderHistoryList();
        setStatusMessage("Días feriados actualizados.", "success");
    } catch (err) {
        console.error(err);
        setStatusMessage("Error al guardar: " + err.message, "error");
    }
};

window.reassignHistoryTasks = async function (index, event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }

    try {
        setStatusMessage("Recalculando limpieza...", "info", 0);
        await fetchHistoryEntries();

        const entry = historyEntriesCache[index];
        const reassignUrl =
            entry && entry.db_id != null
                ? `/api/history/entry/${entry.db_id}/reassign_tasks`
                : `/api/history/${index}/reassign_tasks`;
        const res = await fetch(reassignUrl, {
            method: "POST"
        });
        const payload = await res.json().catch(() => ({}));
        if (!res.ok) {
            throw new Error(payload.detail || `API returned ${res.status}`);
        }

        if (!entry) return;

        entry.daily_tasks = payload.daily_tasks || {};
        entry.special_days = payload.special_days || entry.special_days || {};

        renderHistoryEntryTable(index);
        setStatusMessage("Limpieza recalculada para esta semana.", "success");
    } catch (err) {
        console.error(err);
        setStatusMessage("No se pudo recalcular la limpieza.", "error");
        alert(err.message || "Error al recalcular limpieza");
    }
};

window.editHistoryTasks = async function (index, event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    
    const entry = historyEntriesCache[index];
    if (!entry) {
        setStatusMessage("Entrada de historial no encontrada.", "error");
        return;
    }
    
    const currentTasks = entry.daily_tasks || {};
    
    // Construir HTML del modal
    const modalHtml = `
        <div id="editTasksModal" class="modal-backdrop">
            <div class="modal-dialog" style="max-width: 600px; width: 90%;">
                <div class="modal-header-simple">
                    <h3>Editar Tareas de Limpieza</h3>
                    <button class="close-icon" onclick="closeEditTasksModal()"><i class="fa-solid fa-xmark"></i></button>
                </div>
                <div class="modal-body-scroll" style="max-height: 60vh; overflow-y: auto;">
                    <p class="helper-text" style="margin-bottom: 1rem;">
                        <i class="fa-solid fa-info-circle"></i> 
                        Edita las tareas de limpieza para este horario. Deja en blanco para eliminar.
                    </p>
                    <div id="editTasksContainer"></div>
                </div>
                <div class="modal-actions-footer">
                    <button class="btn-text" onclick="closeEditTasksModal()">Cancelar</button>
                    <button class="btn-action primary" onclick="saveEditedTasks(${index})">Guardar Cambios</button>
                </div>
            </div>
        </div>
    `;
    
    // Remover modal existente si hay
    const existingModal = document.getElementById('editTasksModal');
    if (existingModal) existingModal.remove();
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    // Llenar el container con las tareas actuales
    const container = document.getElementById('editTasksContainer');
    
    // Obtener lista de empleados del horario
    const employees = Object.keys(entry.schedule || {});
    
    if (employees.length === 0) {
        container.innerHTML = '<p class="helper-text">No hay empleados en este horario.</p>';
        return;
    }
    
    // Días de la semana
    const dias = ['Vie', 'Sáb', 'Dom', 'Lun', 'Mar', 'Mié', 'Jue'];
    
    // Construir tabla de tareas
    let tableHtml = '<table class="clean-table" style="width: 100%; font-size: 0.85rem;">';
    tableHtml += '<thead><tr><th>Empleado</th>';
    dias.forEach(d => { tableHtml += `<th>${d}</th>`; });
    tableHtml += '</tr></thead><tbody>';
    
    employees.forEach(emp => {
        tableHtml += `<tr><td style="font-weight: 500;">${emp}</td>`;
        dias.forEach(dia => {
            const taskKey = `${emp}_${dia}`;
            const currentTask = currentTasks[taskKey] || '';
            tableHtml += `<td><input type="text" class="task-input" data-emp="${emp}" data-day="${dia}" 
                value="${currentTask}" placeholder="Tarea..." 
                style="width: 100%; padding: 4px 8px; border: 1px solid var(--border-color); border-radius: 4px; 
                background: var(--surface-2); color: var(--text-main); font-size: 0.8rem;"></td>`;
        });
        tableHtml += '</tr>';
    });
    tableHtml += '</tbody></table>';
    
    container.innerHTML = tableHtml;
    
    // Mostrar modal
    document.getElementById('editTasksModal').classList.remove('hidden');
};

window.closeEditTasksModal = function() {
    const modal = document.getElementById('editTasksModal');
    if (modal) modal.remove();
};

window.saveEditedTasks = async function(index) {
    const entry = historyEntriesCache[index];
    if (!entry) return;
    
    // Recolectar tareas del form
    const nuevosTasks = {};
    document.querySelectorAll('#editTasksContainer .task-input').forEach(input => {
        const emp = input.dataset.emp;
        const dia = input.dataset.day;
        const taskKey = `${emp}_${dia}`;
        const valor = input.value.trim();
        
        if (valor) {
            nuevosTasks[taskKey] = valor;
        }
    });
    
    try {
        // Si tiene db_id, usar endpoint de API
        if (entry.db_id) {
            const res = await fetch(`/api/planillas/horarios/${entry.db_id}/tareas`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(nuevosTasks)
            });
            if (!res.ok) {
                throw new Error('Error al guardar tareas');
            }
        }
        
        // Actualizar localmente también
        entry.daily_tasks = nuevosTasks;
        
        // Cerrar modal y re-renderizar
        closeEditTasksModal();
        renderHistoryEntryTable(index);
        setStatusMessage("Tareas de limpieza guardadas.", "success");
    } catch (err) {
        console.error(err);
        setStatusMessage("Error al guardar tareas: " + err.message, "error");
    }
};

window.validateHistory = async function (index, event) {
    if (event) event.stopPropagation();
    try {
        await fetchHistoryEntries();
        const entry = historyEntriesCache[index];
        if (!entry) return;

        const oldSchedule = currentGeneratedSchedule;
        const oldRules = validationRules;
        const oldMeta = currentMetadata;
        currentGeneratedSchedule = entry.schedule;
        currentMetadata = oldMeta && typeof oldMeta === "object" ? { ...oldMeta } : {};
        delete currentMetadata.rest_between_shifts;
        delete currentMetadata.min_rest_hours_applied;
        delete currentMetadata.min_rest_hours_target;
        if (entry.rest_between_shifts) currentMetadata.rest_between_shifts = entry.rest_between_shifts;
        if (entry.min_rest_hours_applied != null) currentMetadata.min_rest_hours_applied = entry.min_rest_hours_applied;
        if (entry.min_rest_hours_target != null) currentMetadata.min_rest_hours_target = entry.min_rest_hours_target;

        validationRules = await fetchValidationRules(entry.special_days || {});

        isValidationOn = true;
        applyValidationUI();

        currentGeneratedSchedule = oldSchedule;
        validationRules = oldRules || baseValidationRules;
        currentMetadata = oldMeta;
    } catch (err) {
        console.error(err);
        alert("Error al validar historial");
    }
};

window.exportHistoryImage = async function (index, event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }

    try {
        await fetchHistoryEntries();
    } catch (err) {
        console.error(err);
    }

    const histTableWrapper = document.getElementById(`hist-table-${index}`);
    if (!histTableWrapper) return;

    const captureElement = histTableWrapper.parentElement;
    const filename = `${getHistoryExportBaseName(index)}.png`;

    try {
        setStatusMessage("Exportando imagen del historial...", "info", 0);
        const canvas = await renderScheduleCaptureCanvas(captureElement);

        const imageData = canvas.toDataURL("image/png");
        const link = document.createElement('a');
        link.download = filename;
        link.href = imageData;
        link.click();

        const saveRes = await fetch(`${API_URL}/export_image`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image_data: imageData, filename })
        });
        if (!saveRes.ok) {
            let detail = "No se pudo guardar la imagen en export_horarios.";
            try {
                const err = await saveRes.json();
                detail = err.detail || detail;
            } catch (_) { }
            throw new Error(detail);
        }

        showExportConfirmationModal(filename, 'image');
    } catch (err) {
        console.error("Capture failed:", err);
        setStatusMessage("No se pudo exportar la imagen del historial.", "error");
        alert(err.message || "Error al exportar imagen del historial");
    }
};

// SWAP HISTORY EMPLOYEES
window.swapHistoryEmployees = function (index, event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }

    const entry = historyEntriesCache[index];
    if (!entry) return;

    const employees = Object.keys(entry.schedule || {});
    if (employees.length < 2) {
        setStatusMessage("Se necesitan al menos 2 empleados para intercambiar.", "error");
        return;
    }

    const selA = document.getElementById("swapEmpA");
    const selB = document.getElementById("swapEmpB");
    if (!selA || !selB) return;

    selA.innerHTML = "";
    selB.innerHTML = "";
    employees.forEach(name => {
        selA.appendChild(new Option(name, name));
        selB.appendChild(new Option(name, name));
    });
    selB.value = employees[1];

    const modal = document.getElementById("swapEmployeesModal");
    modal.dataset.historyIndex = String(index);
    modal.classList.remove("hidden");
};

window.closeSwapEmployeesModal = function () {
    const modal = document.getElementById("swapEmployeesModal");
    if (modal) modal.classList.add("hidden");
};

window.confirmSwapEmployees = async function () {
    const modal = document.getElementById("swapEmployeesModal");
    const index = parseInt(modal.dataset.historyIndex, 10);

    const empA = document.getElementById("swapEmpA").value;
    const empB = document.getElementById("swapEmpB").value;

    if (!empA || !empB || empA === empB) {
        setStatusMessage("Seleccioná dos empleados distintos.", "error");
        return;
    }

    const entry = historyEntriesCache[index];
    if (!entry) return;

    try {
        const nextEntry = cloneHistoryEntry(entry);

        const schedA = nextEntry.schedule[empA];
        const schedB = nextEntry.schedule[empB];
        nextEntry.schedule[empA] = schedB;
        nextEntry.schedule[empB] = schedA;

        if (nextEntry.daily_tasks) {
            const tasksA = nextEntry.daily_tasks[empA];
            const tasksB = nextEntry.daily_tasks[empB];
            nextEntry.daily_tasks[empA] = tasksB ?? {};
            nextEntry.daily_tasks[empB] = tasksA ?? {};
        }

        closeSwapEmployeesModal();

        await persistHistoryEntry(index, nextEntry);
        renderHistoryEntryTable(index);
        setStatusMessage(`Horarios de ${empA} y ${empB} intercambiados.`, "success");
    } catch (err) {
        console.error(err);
        setStatusMessage("Error al intercambiar horarios.", "error");
        alert(err.message || "No se pudo guardar el intercambio.");
    }
};

// EDIT HISTORY SHIFT
async function editHistoryShift(empName, day, histIndex) {
    try {
        const entry = historyEntriesCache[histIndex];
        if (!entry) return;

        const currentShift = entry.schedule?.[empName]?.[day] || "OFF";
        const newShift = await promptHistoryShiftValue(empName, [day], currentShift);
        if (!newShift) return;

        const nextEntry = cloneHistoryEntry(entry);
        nextEntry.schedule[empName] = nextEntry.schedule[empName] || {};
        nextEntry.daily_tasks = nextEntry.daily_tasks || {};
        nextEntry.daily_tasks[empName] = nextEntry.daily_tasks[empName] || {};
        nextEntry.schedule[empName][day] = newShift;
        nextEntry.daily_tasks[empName][day] = null;

        await persistHistoryEntry(histIndex, nextEntry);
        renderHistoryEntryTable(histIndex);
        setStatusMessage(`Historial actualizado para ${empName}.`, "success");
    } catch (err) {
        console.error(err);
        alert(err.message || "Error al guardar el historial");
    } finally {
        clearHistorySelectionStyles();
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

function getAutofillWeekNumber(date) {
    const labelDate = new Date(date.getTime());
    labelDate.setDate(labelDate.getDate() + 3);
    return getISOWeekNumber(labelDate);
}

function autoCalcWeekEnd() {
    const startInput = document.getElementById("weekStartDate");
    const endInput = document.getElementById("weekEndDate");
    const preview = document.getElementById("weekNamePreview");
    if (!startInput || !startInput.value) {
        weekSpecialDays = createDefaultSpecialDays();
        if (endInput) endInput.value = "";
        if (preview) preview.style.display = "none";
        renderWeekSpecialDays();
        return;
    }

    const start = new Date(startInput.value + "T00:00:00");
    // End = start + 6 days (Viernes→Jueves)
    const end = new Date(start);
    end.setDate(end.getDate() + 6);
    endInput.value = end.toISOString().split("T")[0];

    // Show preview of week name
    const weekNum = getAutofillWeekNumber(start);
    preview.textContent = `Semana ${weekNum}`;
    preview.style.display = "block";

    weekSpecialDays = createDefaultSpecialDays();
    renderWeekSpecialDays();
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
        const weekNum = getAutofillWeekNumber(start);
        nameInput.value = `Semana ${weekNum}`;
    } else {
        nameInput.value = "";
    }
}
function closeSaveModal() { document.getElementById("saveModal").classList.add("hidden"); }
async function confirmSaveSchedule(event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();

    const name = document.getElementById("scheduleNameInput").value;
    if (!name) return;

    const weekDates = getWeekDatesMap();
    const specialDays = currentMetadata?.special_days || getSpecialDaysPayload();
    const payload = {
        name,
        schedule: currentGeneratedSchedule,
        daily_tasks: currentDailyTasks,
        metadata: currentMetadata || {},
        next_sunday_cycle_index: currentMetadata?.next_sunday_cycle_index,
        next_sunday_rotation_queue: currentMetadata?.next_sunday_rotation_queue,
        week_dates: weekDates,
        special_days: specialDays
    };

    try {
        const res = await fetch('/api/save-history-with-folder-check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            let detail = "No se pudo guardar el historial.";
            try {
                const err = await res.json();
                detail = err.detail || detail;
            } catch (_) { }
            throw new Error(detail);
        }

        historyEntriesCache.push({
            ...cloneHistoryEntry(payload),
            timestamp: new Date().toISOString(),
        });
        closeSaveModal();
        setStatusMessage("Semana guardada.", "success");

        if (!document.getElementById("overlay-history")?.classList.contains("hidden")) {
            renderHistoryList();
        }
    } catch (err) {
        console.error(err);
        alert(err.message || "No se pudo guardar el historial");
    }
}

// UTILS
function populateShiftSelects() {
    document.querySelectorAll(".shift-select, .ppt-shift-select").forEach(sel => {
        if (sel.options && sel.options.length > 1) return;
        sel.innerHTML = "";
        SHIFT_OPTIONS.forEach(o => {
            if (o.code === "D4_13-22" && sel.getAttribute("data-day") !== "Dom") {
                return;
            }
            const opt = document.createElement("option");
            opt.value = o.code; opt.textContent = o.label;
            sel.appendChild(opt);
        });
    });
}

function switchTab(id) {
    document.querySelectorAll(".m-tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".m-tab-content").forEach(c => c.classList.remove("active"));
    const pane = document.getElementById(id);
    if (pane) pane.classList.add("active");
    if (id === "tab-schedule") window.__pillEditorMode = "employee";
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
    if (window.__pillEditorMode === "plantilla") return;
    // If a dropdown says "VAC", check the box
    const selects = document.querySelectorAll("#planillaEmpModal .shift-select");
    selects.forEach(sel => {
        const d = sel.getAttribute("data-day");
        const isVac = sel.value === "VAC";
        const cb = document.querySelector(`#vacationCheckboxes input[data-day='${d}']`);
        if (cb) cb.checked = isVac;
    });
}

function toggleVacation(day, isChecked) {
    const sel = document.querySelector(`#planillaEmpModal .shift-select[data-day='${day}']`);
    if (sel) {
        if (isChecked) sel.value = "VAC";
        else sel.value = "AUTO"; // Revert to auto if unchecked
    }
}

function _taskBaseAndSuffix(t) {
    // Separa el sufijo "↑AM" / "↓PM" del nombre base de la tarea.
    const m = t.match(/^(.+?)\s*([↑↓]\s*(?:AM|PM))\s*$/i);
    if (m) return { base: m[1].trim(), suffix: m[2].trim() };
    return { base: t.trim(), suffix: "" };
}

function _taskColorClass(base) {
    if (base === "Baños") return "task-banos";
    if (base === "Tanques") return "task-tanques";
    if (base.includes("Oficina")) return "task-oficina";
    if (base === "Calibración") return "task-calibracion";
    if (base === "Caños" || base === "Caños GLP") return "task-canos";
    return "task-default";
}

function getTaskLabelHTML(tasks, name, d) {
    if (!tasks || !tasks[name] || !tasks[name][d]) return "";
    const t = tasks[name][d];
    const { base, suffix } = _taskBaseAndSuffix(t);
    const colorClass = _taskColorClass(base);

    let label;
    if (base === "Baños") {
        label = `Baños`;
    } else if (base === "Tanques") {
        label = `Tanques`;
    } else if (base.includes("Oficina")) {
        let extra = base.replace("Oficina + Basureros + Baños", "").trim();
        if (extra.startsWith("+")) extra = extra.substring(1).trim();
        label = `Oficina +<br>Basureros + Baños`;
        if (extra) label += `<br><span class="task-extra">+ ${extra}</span>`;
    } else if (base === "Calibración") {
        label = "Calibración";
    } else if (base === "Caños") {
        label = "Caños";
    } else if (base === "Caños GLP") {
        label = "Caños<br>GLP";
    } else {
        label = base;
    }

    if (suffix) label += `<br><span class="task-suffix">${suffix}</span>`;

    const isHistory = tasks && tasks._is_history;
    const editableClass = isHistory ? " history-task-editable" : "";
    const onclick = isHistory ? `onclick="event.stopPropagation(); editHistoryTask('${escapeHtmlAttr(name)}', '${escapeHtmlAttr(d)}', ${tasks._history_index})"` : "";

    return `<span class="shift-task-label ${colorClass}${editableClass}" ${onclick}>${label}</span>`;
}

async function editHistoryTask(empName, day, historyIndex) {
    const entry = historyEntriesCache[historyIndex];
    if (!entry) return;

    const currentTasks = entry.daily_tasks || {};
    const currentTask = (currentTasks[empName] || {})[day];

    const options = [
        { id: "Tanques", label: "Tanques", icon: "fa-faucet", color: "task-tanques" },
        { id: "Baños", label: "Baños", icon: "fa-restroom", color: "task-banos" },
        { id: "Oficina + Basureros + Baños", label: "Oficina + Basureros + Baños", icon: "fa-broom", color: "task-oficina" },
        { id: "Calibración", label: "Calibración", icon: "fa-sliders", color: "task-calibracion" },
        { id: "Caños", label: "Caños", icon: "fa-wrench", color: "task-canos" },
        { id: "Caños GLP", label: "Caños GLP", icon: "fa-fire", color: "task-canos" },
        { id: "None", label: "Quitar Tarea", icon: "fa-xmark", color: "" }
    ];

    const selection = await showTaskSelectorModal(empName, day, currentTask, options);
    if (selection === undefined) return;

    const taskVal = selection === "None" ? null : selection;

    try {
        const res = await fetch(`/api/history/entry/${entry.db_id}/task?employee_name=${encodeURIComponent(empName)}&day=${encodeURIComponent(day)}&task=${encodeURIComponent(taskVal || "")}`, {
            method: 'PATCH'
        });
        if (!res.ok) throw new Error("Error al guardar");

        // Update local cache
        if (!entry.daily_tasks) entry.daily_tasks = {};
        if (!entry.daily_tasks[empName]) entry.daily_tasks[empName] = {};
        entry.daily_tasks[empName][day] = taskVal;

        // Refresh table
        renderHistoryEntryTable(historyIndex);
        setStatusMessage("Tarea actualizada correctamente", "success");
    } catch (e) {
        console.error(e);
        setStatusMessage("Error al actualizar tarea", "error");
    }
}

function showTaskSelectorModal(empName, day, currentTask, options) {
    return new Promise((resolve) => {
        const modal = document.getElementById("textEditModal");
        const title = document.getElementById("textEditTitle");
        const body = document.querySelector("#textEditModal .modal-body-scroll");
        const footer = document.querySelector("#textEditModal .modal-actions-footer");

        const originalBodyContent = body.innerHTML;
        const originalFooterContent = footer.innerHTML;

        title.textContent = `Asignar Tarea: ${empName} (${day})`;
        body.innerHTML = `
            <div style="display: flex; flex-direction: column; gap: 8px;">
                ${options.map(opt => `
                    <div class="task-option-item ${currentTask === opt.id ? 'selected' : ''}" onclick="window._resolveTaskSelection('${opt.id}')">
                        <div class="task-option-icon ${opt.color}">
                            <i class="fa-solid ${opt.icon}"></i>
                        </div>
                        <div style="flex: 1;">
                            <div style="font-weight: 700;">${opt.label}</div>
                        </div>
                        ${currentTask === opt.id ? '<i class="fa-solid fa-check" style="color: var(--primary);"></i>' : ''}
                    </div>
                `).join('')}
            </div>
        `;
        
        footer.innerHTML = `<button class="btn-text" onclick="window._resolveTaskSelection(undefined)">Cancelar</button>`;

        window._resolveTaskSelection = (val) => {
            body.innerHTML = originalBodyContent;
            footer.innerHTML = originalFooterContent;
            modal.classList.add("hidden");
            resolve(val);
        };

        modal.classList.remove("hidden");
    });
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
    .task-calibracion { color: #6b21a8; background: rgba(107, 33, 168, 0.1); border: 1px solid rgba(107, 33, 168, 0.2); }
    .task-canos { color: #065f46; background: rgba(6, 95, 70, 0.1); border: 1px solid rgba(6, 95, 70, 0.2); }
    .dark-mode .task-banos { color: #fbbf24; background: rgba(251, 191, 36, 0.15); }
    .dark-mode .task-tanques { color: #60a5fa; background: rgba(96, 165, 250, 0.15); }
    .dark-mode .task-oficina { color: #f472b6; background: rgba(244, 114, 182, 0.15); }
    .dark-mode .task-calibracion { color: #c084fc; background: rgba(192, 132, 252, 0.15); }
    .dark-mode .task-canos { color: #34d399; background: rgba(52, 211, 153, 0.15); }
    .task-extra {
        color: #be185d;
        font-weight: 800;
        font-size: 0.7rem;
    }
    .dark-mode .task-extra { color: #f472b6; }
    .task-suffix {
        font-size: 0.62rem;
        opacity: 0.75;
        font-weight: 600;
        letter-spacing: 0.3px;
    }
    .history-task-editable {
        cursor: pointer;
        transition: transform 0.15s ease, filter 0.15s ease;
    }
    .history-task-editable:hover {
        transform: scale(1.05);
        filter: brightness(1.1);
    }
    .history-task-empty {
        width: 20px;
        height: 6px;
        background: rgba(0,0,0,0.05);
        border-radius: 3px;
        margin: 4px auto 0;
        cursor: pointer;
        transition: background 0.2s;
        opacity: 0;
    }
    .history-item.expanded td:hover .history-task-empty {
        opacity: 1;
    }
    .history-task-empty:hover {
        background: var(--primary-light);
        opacity: 1 !important;
    }
    .dark-mode .history-task-empty {
        background: rgba(255,255,255,0.1);
    }
    .task-option-item {
        padding: 12px;
        border-radius: 8px;
        border: 1px solid var(--border);
        margin-bottom: 8px;
        cursor: pointer;
        display: flex;
        align-items: center;
        gap: 12px;
        transition: background 0.2s, border-color 0.2s;
    }
    .task-option-item:hover {
        background: var(--bg-hover);
        border-color: var(--primary);
    }
    .task-option-item.selected {
        background: rgba(99, 102, 241, 0.1);
        border-color: var(--primary);
    }
    .task-option-icon {
        width: 32px;
        height: 32px;
        border-radius: 6px;
        display: flex;
        align-items: center;
        justify-content: justify-center;
        font-size: 1rem;
    }
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
        background: #fff1f2;
        color: #881337;
        font-weight: 800;
        border: 1px solid #fda4af;
    }
    .dark-mode .cov-deficit {
        background: #450a0a;
        color: #fecdd3;
        border-color: #f43f5e;
    }
`;
document.head.appendChild(styleCoverage);

// Event Listener for Sorting on main schedule (DOMContentLoaded fallback — also handled inline)
document.addEventListener('DOMContentLoaded', () => {
    const th = document.getElementById('th-collaborator');
    if (th) {
        th.addEventListener('click', () => {
            currentSortMode = (currentSortMode === 'time') ? 'alpha' : 'time';
            if (currentGeneratedSchedule) {
                renderSchedule(currentGeneratedSchedule, "#scheduleTable", currentDailyTasks);
            }
            // Icon is updated inside renderSchedule via the header rebuild
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

// Funciones para el modal Acerca de
function openAcercaDeModal() {
    const modal = document.getElementById("acercaDeModal");
    if (modal) {
        modal.classList.remove("hidden");
        document.body.style.overflow = "hidden"; // Prevent background scrolling
    }
}

function closeAcercaDeModal(event) {
    // Close if clicking overlay or close button
    if (!event || event.target === event.currentTarget || event.target.closest('button[onclick*="closeAcercaDeModal"]')) {
        const modal = document.getElementById("acercaDeModal");
        if (modal) {
            modal.classList.add("hidden");
            document.body.style.overflow = ""; // Restore scrolling
        }
    }
}

// Close modal on Escape key
document.addEventListener("keydown", function(e) {
    if (e.key === "Escape") {
        const modal = document.getElementById("acercaDeModal");
        if (modal && !modal.classList.contains("hidden")) {
            closeAcercaDeModal(e);
        }
    }
});

// =============================================================================
// MÓDULO: GENERADOR DE HORARIO PARCIAL
// Permite regenerar días específicos de una semana existente en el historial
// ante bajas o ausencias imprevistas, respetando la cobertura y las reglas
// del motor (ShiftScheduler) sin modificar scheduler_engine.py.
// =============================================================================

const PartialGenerator = {
    /** Entrada del historial seleccionada como base ({ db_id, name, schedule, week_dates, ... }) */
    baseEntry: null,

    /**
     * Días pasados (bloqueados). Clave = nombre de día ("Vie", "Lun", etc.)
     * Estado: true = bloqueado (día pasado), false = activo (a regenerar).
     * El objeto preserva el orden canónico de DAYS.
     */
    dayLocked: {},

    /** [{name: str, last_working_day: str}] — empleados dados de baja */
    departed: [],

    /**
     * [{employee: str, day: str, fixed: bool}]
     * Clasificación de OFFs detectados en los días activos del horario base.
     */
    offClassifications: [],

    /** Último resultado del solver (<partial_result>) — usado para el guardado */
    lastResult: null,

    /** Caché interna de resultados de búsqueda actuales — evita JSON en onclick inline */
    _searchCache: [],

    // ─────────────────────────────────────────────────────────────────────────
    // PASO 1 — Búsqueda de historial
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * Busca en el historial por nombre y muestra un dropdown de resultados.
     * Se llama desde oninput / onfocus del input de búsqueda.
     */
    async searchHistory(query) {
        const resultsEl = document.getElementById("partialSearchResults");
        if (!resultsEl) return;

        try {
            const history = await fetch("/api/history").then(r => r.json());
            this._searchCache = history
                .filter(h => (h.name || "").toLowerCase().includes((query || "").toLowerCase()))
                .slice(0, 12);

            if (this._searchCache.length === 0) {
                resultsEl.innerHTML = '<p style="padding:0.75rem 1rem; font-size:0.82rem; color:var(--text-muted); margin:0;">Sin resultados.</p>';
                resultsEl.style.display = "block";
                return;
            }

            resultsEl.innerHTML = this._searchCache.map((h, idx) => {
                const weekDates = h.week_dates || {};
                const range = (weekDates["Vie"] && weekDates["Jue"])
                    ? `Vie ${weekDates["Vie"]} – Jue ${weekDates["Jue"]}`
                    : (h.timestamp ? h.timestamp.slice(0, 10) : "");
                const isPartial = (h.name || "").includes("(parcial)");
                // IMPORTANTE: usamos el índice en la caché en lugar de serializar el
                // objeto completo dentro del atributo onclick — evita problemas con
                // caracteres especiales y comillas en los valores del JSON.
                return `
                    <div
                        class="partial-search-item"
                        onclick="PartialGenerator._selectFromCache(${idx})"
                        style="
                            padding: 0.65rem 1rem;
                            cursor: pointer;
                            border-bottom: 1px solid var(--border-color);
                            transition: background 0.15s;
                        "
                        onmouseenter="this.style.background='var(--surface-2)'; this.style.borderLeft='3px solid #f97316'; this.style.paddingLeft='calc(1rem - 3px)';"
                        onmouseleave="this.style.background=''; this.style.borderLeft=''; this.style.paddingLeft='1rem';"
                    >
                        <div style="display:flex; align-items:center; gap:0.5rem;">
                            <i class="fa-solid fa-calendar-week" style="color:#f97316; font-size:0.8rem;"></i>
                            <span style="font-weight:600; font-size:0.88rem; color:var(--text-main);">${h.name || "(sin nombre)"}</span>
                            ${isPartial ? '<span style="background:rgba(249,115,22,0.12);color:#f97316;font-size:0.67rem;padding:1px 5px;border-radius:4px;border:1px solid rgba(249,115,22,0.25);">PARCIAL</span>' : ""}
                        </div>
                        <div style="font-size:0.72rem; color:var(--text-muted); margin-top:2px;">${range}</div>
                    </div>
                `;
            }).join("");

            resultsEl.style.display = "block";
        } catch (e) {
            console.error("[PartialGenerator] searchHistory error:", e);
            resultsEl.innerHTML = '<p style="padding:0.75rem 1rem; font-size:0.82rem; color:#ef4444; margin:0;">Error al cargar el historial.</p>';
            resultsEl.style.display = "block";
        }
    },

    /**
     * Selecciona una entrada de la búsqueda por índice en _searchCache.
     * Llamado desde los onclick inline del dropdown.
     */
    _selectFromCache(idx) {
        const entry = this._searchCache[idx];
        if (!entry) {
            console.error("[PartialGenerator] _selectFromCache: idx", idx, "no encontrado en caché");
            return;
        }
        this.selectBase(entry);
    },

    /**
     * Selecciona un horario base.
     * Acepta el objeto entry directamente (desde _selectFromCache).
     */
    selectBase(entry) {
        if (!entry || typeof entry !== "object") {
            console.error("[PartialGenerator] selectBase: entry inválido", entry);
            return;
        }
        this.baseEntry = entry;

        // Cerrar dropdown y limpiar input
        const resultsEl = document.getElementById("partialSearchResults");
        if (resultsEl) resultsEl.style.display = "none";
        const input = document.getElementById("partialSearchInput");
        if (input) input.value = this.baseEntry.name || "";

        // Mostrar chip del seleccionado
        const selectedEl = document.getElementById("partialSelectedBase");
        const nameEl = document.getElementById("partialBaseName");
        const rangeEl = document.getElementById("partialBaseRange");
        if (selectedEl) selectedEl.style.display = "flex";
        if (nameEl) nameEl.textContent = this.baseEntry.name || "(sin nombre)";
        const wd = this.baseEntry.week_dates || {};
        if (rangeEl) rangeEl.textContent = (wd["Vie"] && wd["Jue"])
            ? `Vie ${wd["Vie"]} – Jue ${wd["Jue"]}`
            : "Sin fechas";

        // Auto-detectar días pasados
        this._detectLockedDays();

        // Resetear bajas y clasificaciones, luego re-render
        this.departed = [];
        this._renderDepartedList();
        this._buildOffClassifications();
        this._renderOffTable();
        this._updateStatusBadge();
    },

    /** Limpia la selección del horario base y resetea todo. */
    clearBase() {
        this.baseEntry = null;
        this.dayLocked = {};
        this.departed = [];
        this.offClassifications = [];
        this.lastResult = null;

        const input = document.getElementById("partialSearchInput");
        if (input) input.value = "";
        const selectedEl = document.getElementById("partialSelectedBase");
        if (selectedEl) selectedEl.style.display = "none";
        const resultsEl = document.getElementById("partialSearchResults");
        if (resultsEl) resultsEl.style.display = "none";

        document.getElementById("partialDaySelector").innerHTML =
            '<p class="helper-text-sm" style="color:var(--text-muted);">Seleccioná un horario base primero.</p>';
        document.getElementById("partialOffTable").innerHTML =
            '<p class="helper-text-sm" style="color:var(--text-muted);">Los libres aparecerán al seleccionar el horario base y configurar los días activos.</p>';
        document.getElementById("partialPreviewZone").style.display = "none";
        this._updateStatusBadge();
    },

    // ─────────────────────────────────────────────────────────────────────────
    // PASO 2 — Detección y selección de días bloqueados
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * Auto-detecta los días pasados comparando week_dates[day] contra hoy.
     * Construye this.dayLocked y llama a _renderDaySelector().
     */
    _detectLockedDays() {
        const weekDates = (this.baseEntry || {}).week_dates || {};
        const today = new Date();
        today.setHours(0, 0, 0, 0);

        this.dayLocked = {};
        DAYS.forEach(day => {
            const dateStr = weekDates[day];
            if (!dateStr) {
                // Sin fecha: marcar como activo por defecto
                this.dayLocked[day] = false;
                return;
            }
            // week_dates puede venir como "YYYY-MM-DD" o "DD/MM/YYYY"
            let dayDate;
            if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
                dayDate = new Date(dateStr + "T00:00:00");
            } else {
                const parts = dateStr.split("/");
                if (parts.length === 3) {
                    dayDate = new Date(`${parts[2]}-${parts[1].padStart(2,"0")}-${parts[0].padStart(2,"0")}T00:00:00`);
                } else {
                    this.dayLocked[day] = false;
                    return;
                }
            }
            this.dayLocked[day] = dayDate < today;
        });

        this._renderDaySelector();
    },

    /** Renderiza los chips de días con toggle bloqueado/activo. */
    _renderDaySelector() {
        const container = document.getElementById("partialDaySelector");
        if (!container) return;

        const weekDates = (this.baseEntry || {}).week_dates || {};

        container.innerHTML = DAYS.map(day => {
            const locked = this.dayLocked[day];
            const dateStr = weekDates[day] || "";
            // Formatear fecha corta DD/MM
            let shortDate = "";
            if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
                const parts = dateStr.split("-");
                shortDate = `${parts[2]}/${parts[1]}`;
            } else if (/^\d{2}\/\d{2}\/\d{4}$/.test(dateStr)) {
                shortDate = dateStr.slice(0, 5);
            }

            const bg = locked
                ? "rgba(100,116,139,0.12)"
                : "rgba(16,185,129,0.1)";
            const border = locked
                ? "1px solid rgba(100,116,139,0.25)"
                : "1px solid rgba(16,185,129,0.3)";
            const color = locked ? "var(--text-muted)" : "#10b981";
            const icon = locked ? "fa-lock" : "fa-unlock";
            const label = locked ? "Pasado" : "Activo";

            return `
                <div
                    onclick="PartialGenerator.toggleDayLock('${day}')"
                    title="${locked ? 'Click para marcar como activo (regenerar)' : 'Click para marcar como pasado (bloquear)'}"
                    style="
                        padding: 0.55rem 0.85rem;
                        border-radius: 10px;
                        background: ${bg};
                        border: ${border};
                        cursor: pointer;
                        display: flex;
                        flex-direction: column;
                        align-items: center;
                        gap: 0.2rem;
                        min-width: 68px;
                        transition: all 0.2s;
                    "
                >
                    <span style="font-weight:700; font-size:0.9rem; color:${color};">${day}</span>
                    ${shortDate ? `<span style="font-size:0.68rem; color:var(--text-muted);">${shortDate}</span>` : ""}
                    <span style="font-size:0.65rem; color:${color}; display:flex; align-items:center; gap:2px;">
                        <i class="fa-solid ${icon}" style="font-size:0.6rem;"></i> ${label}
                    </span>
                </div>
            `;
        }).join("");
    },

    /** Alterna el estado bloqueado/activo de un día. */
    toggleDayLock(day) {
        this.dayLocked[day] = !this.dayLocked[day];
        this._renderDaySelector();
        // Recalcular OFFs porque cambió el rango activo
        this._buildOffClassifications();
        this._renderOffTable();
    },

    // ─────────────────────────────────────────────────────────────────────────
    // PASO 3 — Gestión de empleados dados de baja
    // ─────────────────────────────────────────────────────────────────────────

    /** Agrega una fila de baja vacía para que el usuario complete. */
    addDeparted() {
        // Obtener lista de empleados del horario base
        const empNames = this.baseEntry
            ? Object.keys(this.baseEntry.schedule || {})
            : employees.map(e => e.name);

        // Evitar duplicados: eliminar los ya seleccionados
        const usedNames = new Set(this.departed.map(d => d.name));
        const available = empNames.filter(n => !usedNames.has(n));

        if (available.length === 0) {
            setStatusMessage("Todos los empleados del horario ya están en la lista", "info");
            return;
        }

        // Predeterminar al primero disponible y al último día activo disponible
        const activeDays = DAYS.filter(d => !this.dayLocked[d]);
        this.departed.push({
            name: available[0],
            last_working_day: activeDays.length > 0 ? activeDays[activeDays.length - 1] : DAYS[DAYS.length - 1],
        });

        this._renderDepartedList();
        // Reconstruir clasificaciones porque los días del despedido ya no cuentan
        this._buildOffClassifications();
        this._renderOffTable();
    },

    /** Actualiza un campo de un elemento de la lista de bajas. */
    updateDeparted(index, field, value) {
        if (this.departed[index]) {
            this.departed[index][field] = value;
            this._buildOffClassifications();
            this._renderOffTable();
        }
    },

    /** Elimina un elemento de la lista de bajas. */
    removeDeparted(index) {
        this.departed.splice(index, 1);
        this._renderDepartedList();
        this._buildOffClassifications();
        this._renderOffTable();
    },

    /** Renderiza la lista de bajas configuradas. */
    _renderDepartedList() {
        const container = document.getElementById("partialDepartedList");
        const emptyMsg = document.getElementById("partialDepartedEmpty");
        if (!container) return;

        const empNames = this.baseEntry
            ? Object.keys(this.baseEntry.schedule || {})
            : employees.map(e => e.name);

        if (this.departed.length === 0) {
            if (emptyMsg) emptyMsg.style.display = "";
            // Limpiar las filas si las hay
            container.querySelectorAll(".partial-departed-row").forEach(el => el.remove());
            return;
        }
        if (emptyMsg) emptyMsg.style.display = "none";

        // Reconstruir filas
        container.querySelectorAll(".partial-departed-row").forEach(el => el.remove());
        this.departed.forEach((dep, idx) => {
            const row = document.createElement("div");
            row.className = "partial-departed-row";
            row.style.cssText = "display:flex; align-items:center; gap:0.5rem; padding:0.6rem 0.75rem; background:rgba(239,68,68,0.06); border:1px solid rgba(239,68,68,0.2); border-radius:10px;";

            const empOptions = empNames.map(n =>
                `<option value="${n}" ${n === dep.name ? "selected" : ""}>${n}</option>`
            ).join("");
            const dayOptions = DAYS.map(d =>
                `<option value="${d}" ${d === dep.last_working_day ? "selected" : ""}>${d}</option>`
            ).join("");

            row.innerHTML = `
                <i class="fa-solid fa-user-slash" style="color:#ef4444; font-size:0.85rem; flex-shrink:0;"></i>
                <select
                    onchange="PartialGenerator.updateDeparted(${idx},'name',this.value)"
                    style="flex:1; padding:0.4rem 0.6rem; border-radius:8px; border:1px solid var(--border-color); background:var(--surface-2); color:var(--text-main); font-size:0.85rem;"
                >${empOptions}</select>
                <span style="font-size:0.78rem; color:var(--text-muted); flex-shrink:0; white-space:nowrap;">Último día:</span>
                <select
                    onchange="PartialGenerator.updateDeparted(${idx},'last_working_day',this.value)"
                    style="padding:0.4rem 0.6rem; border-radius:8px; border:1px solid var(--border-color); background:var(--surface-2); color:var(--text-main); font-size:0.85rem;"
                >${dayOptions}</select>
                <button
                    onclick="PartialGenerator.removeDeparted(${idx})"
                    style="background:none; border:none; color:#ef4444; cursor:pointer; padding:0.3rem; font-size:0.85rem;"
                    title="Quitar"
                ><i class="fa-solid fa-xmark"></i></button>
            `;
            container.appendChild(row);
        });
    },

    // ─────────────────────────────────────────────────────────────────────────
    // PASO 4 — Clasificación de OFFs
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * Extrae todos los OFFs (OFF, VAC, PERM) del horario base en los días activos,
     * excluyendo los días de los empleados despedidos.
     * Los inicializa como flexibles (fixed: false).
     */
    _buildOffClassifications() {
        if (!this.baseEntry) {
            this.offClassifications = [];
            return;
        }

        const schedule = this.baseEntry.schedule || {};
        const activeDays = DAYS.filter(d => !this.dayLocked[d]);
        const departedNames = new Set(this.departed.map(d => d.name));

        // Preservar clasificaciones existentes para no resetear decisiones del usuario
        const existingMap = new Map(
            this.offClassifications.map(c => [`${c.employee}|${c.day}`, c.fixed])
        );

        this.offClassifications = [];
        for (const [emp, days] of Object.entries(schedule)) {
            if (departedNames.has(emp)) continue; // El despedido no aplica
            for (const day of activeDays) {
                const shift = days[day];
                if (shift === "OFF" || shift === "VAC" || shift === "PERM") {
                    const key = `${emp}|${day}`;
                    this.offClassifications.push({
                        employee: emp,
                        day,
                        fixed: existingMap.has(key) ? existingMap.get(key) : false,
                    });
                }
            }
        }
    },

    /** Alterna la clasificación fixed/flexible de una entrada de OFF. */
    toggleOff(index) {
        if (this.offClassifications[index]) {
            this.offClassifications[index].fixed = !this.offClassifications[index].fixed;
            this._renderOffTable();
        }
    },

    /** Renderiza la tabla de clasificación de OFFs. */
    _renderOffTable() {
        const container = document.getElementById("partialOffTable");
        if (!container) return;

        if (this.offClassifications.length === 0) {
            container.innerHTML = '<p class="helper-text-sm" style="color:var(--text-muted); margin:0;">Sin libres en los días activos del horario base.</p>';
            return;
        }

        const rows = this.offClassifications.map((clf, idx) => {
            const isFixed = clf.fixed;
            const shiftLabel = (this.baseEntry?.schedule?.[clf.employee]?.[clf.day]) || "OFF";
            return `
                <tr>
                    <td style="padding:0.5rem 0.75rem; font-weight:500; color:var(--text-main); font-size:0.85rem;">${clf.employee}</td>
                    <td style="padding:0.5rem 0.75rem; font-size:0.85rem; color:var(--text-muted);">${clf.day}</td>
                    <td style="padding:0.5rem 0.75rem;">
                        <span style="background:rgba(100,116,139,0.1); color:var(--text-muted); font-size:0.75rem; padding:2px 8px; border-radius:6px; font-weight:600;">${shiftLabel}</span>
                    </td>
                    <td style="padding:0.5rem 0.75rem;">
                        <div style="display:flex; gap:0.4rem;">
                            <button
                                onclick="PartialGenerator.toggleOff(${idx})"
                                style="
                                    padding: 0.3rem 0.65rem;
                                    font-size: 0.75rem;
                                    border-radius: 7px;
                                    border: 1px solid ${isFixed ? "rgba(239,68,68,0.4)" : "var(--border-color)"};
                                    background: ${isFixed ? "rgba(239,68,68,0.08)" : "transparent"};
                                    color: ${isFixed ? "#ef4444" : "var(--text-muted)"};
                                    cursor: pointer;
                                    font-weight: 600;
                                    display: flex;
                                    align-items: center;
                                    gap: 0.3rem;
                                "
                                title="${isFixed ? "Clic para marcar como flexible" : "Clic para fijar este libre"}"
                            >
                                <i class="fa-solid ${isFixed ? "fa-lock" : "fa-unlock"}" style="font-size:0.65rem;"></i>
                                ${isFixed ? "Fijo" : "Flexible"}
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join("");

        container.innerHTML = `
            <table style="width:100%; border-collapse:collapse;">
                <thead>
                    <tr style="border-bottom:1px solid var(--border-color);">
                        <th style="padding:0.4rem 0.75rem; text-align:left; font-size:0.78rem; color:var(--text-muted); font-weight:600;">Colaborador</th>
                        <th style="padding:0.4rem 0.75rem; text-align:left; font-size:0.78rem; color:var(--text-muted); font-weight:600;">Día</th>
                        <th style="padding:0.4rem 0.75rem; text-align:left; font-size:0.78rem; color:var(--text-muted); font-weight:600;">Tipo</th>
                        <th style="padding:0.4rem 0.75rem; text-align:left; font-size:0.78rem; color:var(--text-muted); font-weight:600;">Clasificación</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        `;
    },

    // ─────────────────────────────────────────────────────────────────────────
    // GENERACIÓN
    // ─────────────────────────────────────────────────────────────────────────

    /** Arma el payload y llama a POST /api/solve-partial. */
    async generate() {
        if (!this.baseEntry) {
            setStatusMessage("Seleccioná un horario base primero", "error");
            return;
        }

        const lockedDays = DAYS.filter(d => this.dayLocked[d]);
        const activeDays = DAYS.filter(d => !this.dayLocked[d]);

        if (activeDays.length === 0) {
            setStatusMessage("No hay días activos — desbloqueá al menos uno", "error");
            return;
        }

        // Obtener week_start (Viernes de esa semana en ISO)
        const weekDates = this.baseEntry.week_dates || {};
        let targetWeekStart = null;
        const vieDate = weekDates["Vie"];
        if (vieDate) {
            if (/^\d{4}-\d{2}-\d{2}$/.test(vieDate)) {
                targetWeekStart = vieDate;
            } else if (/^\d{2}\/\d{2}\/\d{4}$/.test(vieDate)) {
                const parts = vieDate.split("/");
                targetWeekStart = `${parts[2]}-${parts[1].padStart(2,"0")}-${parts[0].padStart(2,"0")}`;
            }
        }

        const payload = {
            base_history_db_id: this.baseEntry.db_id,
            config: getCurrentConfig(),
            target_week_start: targetWeekStart,
            special_days: {},
            locked_days: lockedDays,
            departed_employees: this.departed,
            off_classifications: this.offClassifications,
        };

        const btn = document.getElementById("btnGeneratePartial");
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Generando...'; }

        try {
            const result = await fetch("/api/solve-partial", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            }).then(r => r.json());

            if (result.status !== "Success") {
                const detail = result.status || result.detail || "Error desconocido";
                setStatusMessage(`Error: ${detail}`, "error", 5000);
                return;
            }

            this.lastResult = result;
            this._renderPreview(result);
            setStatusMessage("Horario parcial generado ✓", "success");

        } catch (e) {
            console.error("[PartialGenerator] generate error:", e);
            setStatusMessage("Error al conectar con el servidor", "error");
        } finally {
            if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> <span>Generar Horario Parcial</span>'; }
        }
    },

    // ─────────────────────────────────────────────────────────────────────────
    // PREVIEW
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * Renderiza la tabla de preview con tres tipos de celdas:
     *  - 🔒 Locked (día pasado): gris, candado
     *  - ✂️ Vacant (empleado despedido, día activo sin asignación): rayado diagonal
     *  - ✅ Regenerado (día activo, empleado activo): verde suave
     */
    _renderPreview(result) {
        const previewZone = document.getElementById("partialPreviewZone");
        const tbody = document.getElementById("partialScheduleTbody");
        if (!previewZone || !tbody) return;

        const schedule = result.schedule || {};
        const meta = result.metadata || {};
        const lockedDays = new Set(meta.locked_days || []);
        const departedNames = new Set((meta.departed_employees || []).map(d => d.name));

        // Actualizar cabeceras con fechas
        const weekDates = meta.week_dates || {};
        DAYS.forEach(day => {
            const th = document.getElementById(`partial-th-${day}`);
            if (!th) return;
            const dateStr = weekDates[day] || "";
            let shortDate = "";
            if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
                const p = dateStr.split("-"); shortDate = `${p[2]}/${p[1]}`;
            } else if (/^\d{2}\/\d{2}\/\d{4}$/.test(dateStr)) {
                shortDate = dateStr.slice(0, 5);
            }
            th.innerHTML = `${day}${shortDate ? `<br><small style="font-weight:400;color:var(--text-muted);font-size:0.68rem;">${shortDate}</small>` : ""}`;
            // Colorear cabecera según estado
            if (lockedDays.has(day)) {
                th.style.background = "rgba(100,116,139,0.08)";
                th.style.color = "var(--text-muted)";
            } else {
                th.style.background = "rgba(16,185,129,0.06)";
                th.style.color = "#10b981";
            }
        });

        // Construir filas
        const empNames = Object.keys(schedule);
        tbody.innerHTML = empNames.map(emp => {
            const isDeparted = departedNames.has(emp);
            const empSchedule = schedule[emp] || {};

            const cells = DAYS.map(day => {
                const shift = empSchedule[day]; // undefined = celda vacía
                const isLocked = lockedDays.has(day);

                if (isLocked) {
                    // Día pasado: gris con candado
                    const displayShift = shift || "—";
                    return `
                        <td style="
                            padding: 0.5rem 0.4rem;
                            text-align: center;
                            background: rgba(100,116,139,0.07);
                            color: var(--text-muted);
                            font-size: 0.78rem;
                        ">
                            <span style="display:flex; align-items:center; justify-content:center; gap:3px;">
                                <i class="fa-solid fa-lock" style="font-size:0.55rem; opacity:0.5;"></i>
                                ${displayShift}
                            </span>
                        </td>
                    `;
                }

                if (isDeparted && shift === undefined) {
                    // Empleado despedido en día activo: celda vacía con rayado diagonal
                    return `
                        <td style="
                            padding: 0.5rem 0.4rem;
                            text-align: center;
                            background: repeating-linear-gradient(
                                45deg,
                                rgba(239,68,68,0.04) 0px, rgba(239,68,68,0.04) 3px,
                                transparent 3px, transparent 9px
                            );
                            border: 1px solid rgba(239,68,68,0.15);
                        ">
                            <span style="font-size:0.7rem; color: rgba(239,68,68,0.4);">—</span>
                        </td>
                    `;
                }

                // Empleado activo en día activo: mostrar turno regenerado
                const displayShift = shift || "—";
                const isOff = shift === "OFF" || shift === "VAC" || shift === "PERM";
                return `
                    <td style="
                        padding: 0.5rem 0.4rem;
                        text-align: center;
                        background: rgba(16,185,129,0.05);
                        font-size: 0.8rem;
                        font-weight: ${isOff ? "400" : "600"};
                        color: ${isOff ? "var(--text-muted)" : "var(--text-main)"};
                    ">
                        ${displayShift}
                    </td>
                `;
            }).join("");

            const empRowStyle = isDeparted
                ? "background: rgba(239,68,68,0.03);"
                : "";

            return `
                <tr style="${empRowStyle}">
                    <td style="padding:0.5rem 0.75rem; font-weight:${isDeparted ? "400" : "600"}; color:${isDeparted ? "var(--text-muted)" : "var(--text-main)"}; font-size:0.85rem; white-space:nowrap;">
                        ${isDeparted ? '<i class="fa-solid fa-user-slash" style="font-size:0.7rem; color:#ef4444; margin-right:4px;"></i>' : ""}
                        ${emp}
                    </td>
                    ${cells}
                </tr>
            `;
        }).join("");

        // Mostrar contexto del historial
        const ctxLabel = document.getElementById("partialHistoryContextLabel");
        if (ctxLabel) ctxLabel.textContent = meta.history_context_label || "";

        previewZone.style.display = "block";
        previewZone.scrollIntoView({ behavior: "smooth", block: "start" });
    },

    // ─────────────────────────────────────────────────────────────────────────
    // GUARDADO
    // ─────────────────────────────────────────────────────────────────────────

    /** Guarda el resultado parcial como nueva entrada en el historial con sufijo "(parcial)". */
    async save() {
        if (!this.lastResult) {
            setStatusMessage("Primero generá el horario parcial", "error");
            return;
        }

        const baseName = (this.lastResult.metadata?.base_name || this.baseEntry?.name || "Semana").trim();
        const name = baseName.endsWith("(parcial)") ? baseName : `${baseName} (parcial)`;

        const entry = {
            name,
            schedule: this.lastResult.schedule || {},
            daily_tasks: this.lastResult.daily_tasks || {},
            week_dates: this.lastResult.metadata?.week_dates || {},
            special_days: this.lastResult.metadata?.special_days || {},
            timestamp: new Date().toISOString(),
        };

        try {
            const res = await fetch("/api/history", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(entry),
            });

            if (res.ok) {
                setStatusMessage(`"${name}" guardado en el historial ✓`, "success");
            } else {
                setStatusMessage("Error al guardar en el historial", "error");
            }
        } catch (e) {
            console.error("[PartialGenerator] save error:", e);
            setStatusMessage("Error al conectar con el servidor", "error");
        }
    },

    // ─────────────────────────────────────────────────────────────────────────
    // UTILIDADES
    // ─────────────────────────────────────────────────────────────────────────

    _updateStatusBadge() {
        const badge = document.getElementById("partialStatusBadge");
        if (!badge) return;

        if (!this.baseEntry) {
            badge.textContent = "Sin configurar";
            badge.style.color = "#f97316";
            return;
        }

        const activeDays = DAYS.filter(d => !this.dayLocked[d]);
        badge.textContent = `${this.baseEntry.name} — ${activeDays.length} días activos`;
        badge.style.color = "#10b981";
    },
};

// ─── Funciones globales (llamadas desde HTML inline) ──────────────────────────

function partialSearchHistory(query) {
    PartialGenerator.searchHistory(query).catch(console.error);
}

function partialClearBase() {
    PartialGenerator.clearBase();
}

function partialAddDeparted() {
    PartialGenerator.addDeparted();
}

async function generatePartialSchedule() {
    await PartialGenerator.generate();
}

async function savePartialSchedule() {
    await PartialGenerator.save();
}

// Click handler para matrix 6×7 del jefe de pista
document.addEventListener('click', function(e) {
    const cell = e.target.closest('.jefe-cell');
    if (!cell) return;
    const valueSpan = cell.querySelector('.jefe-cell-value');
    if (!valueSpan) return;
    const isJefe = cell.classList.contains('jefe-cell-active');
    cell.classList.toggle('jefe-cell-active', !isJefe);
    valueSpan.textContent = isJefe ? '—' : 'Jefe';
    updateConfig();
});

// Cerrar el dropdown de búsqueda al hacer click fuera
document.addEventListener("click", function(e) {
    const input = document.getElementById("partialSearchInput");
    const results = document.getElementById("partialSearchResults");
    if (results && input && !input.contains(e.target) && !results.contains(e.target)) {
        results.style.display = "none";
    }
});

// ===================================================================
// INDIVIDUAL HISTORY — Per-employee 6-week history view
// ===================================================================

async function fetchIndividualHistory(name, weeks = 6) {
    const resp = await fetch(`${API_URL}/history/individual/${encodeURIComponent(name)}?weeks=${weeks}`);
    if (!resp.ok) throw new Error(`Failed to fetch history for ${name}`);
    return resp.json();
}

function renderHistoryIndividual(name) {
    fetchIndividualHistory(name, 6).then(data => {
        const weeks = data.weeks || [];
        if (weeks.length === 0) {
            alert(`No hay historial para ${name}`);
            return;
        }

        const typeLabels = {
            matutino: "AM",
            vespertino: "PM",
            nocturno: "Noche",
            libre: "Libre"
        };
        const typeClasses = {
            matutino: "cell-dominant-am",
            vespertino: "cell-dominant-pm",
            nocturno: "cell-dominant-n",
            libre: "cell-dominant-off"
        };

        let html = `<div class="modal-overlay" onclick="closeIndividualHistory(event)">
            <div class="modal-content hist-individual-modal" onclick="event.stopPropagation()">
                <div class="modal-header">
                    <h3>Historial Individual: ${escapeHtml(name)}</h3>
                    <button class="modal-close" onclick="closeIndividualHistory()">&times;</button>
                </div>
                <div class="modal-body">
                    <table class="hist-individual-table">
                        <thead>
                            <tr>
                                <th>Semana</th>
                                <th>Tipo Dominante</th>
                                <th>AM</th>
                                <th>PM</th>
                                <th>Noche</th>
                                <th>Libre</th>
                            </tr>
                        </thead>
                        <tbody>`;

        weeks.forEach(w => {
            const cls = typeClasses[w.dominant_type] || "";
            const label = typeLabels[w.dominant_type] || w.dominant_type;
            html += `<tr>
                <td>${escapeHtml(w.week_label)}</td>
                <td class="${cls}">${label}</td>
                <td>${w.counts?.matutino || 0}</td>
                <td>${w.counts?.vespertino || 0}</td>
                <td>${w.counts?.nocturno || 0}</td>
                <td>${w.counts?.libre || 0}</td>
            </tr>`;
        });

        html += `</tbody></table></div></div></div>`;

        const container = document.createElement("div");
        container.id = "individual-history-modal";
        container.innerHTML = html;
        document.body.appendChild(container);
    }).catch(err => {
        console.error("Error fetching individual history:", err);
        alert(`Error al cargar historial: ${err.message}`);
    });
}

function closeIndividualHistory(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.getElementById("individual-history-modal");
    if (modal) modal.remove();
}

/* ─── Historial Matriz: todos los empleados × semanas ─── */
async function openHistoryMatrix() {
    const existing = document.getElementById("history-matrix-modal");
    if (existing) { existing.remove(); return; }

    try {
        const resp = await fetch(`${API_URL}/history`);
        if (!resp.ok) throw new Error(`Error ${resp.status}`);
        const history = await resp.json();

        // Últimas 8 semanas (alineado con ROTATION_HISTORY_WINDOW)
        // La API devuelve ordenado DESC (más reciente primero), así que
        // tomamos las primeras 8 (más recientes) y las invertimos a cronológico.
        const weeks = (history || []).slice(0, 8).reverse();

        if (weeks.length === 0) {
            alert("No hay historial disponible.");
            return;
        }

        // Empleados únicos (solo activos)
        const empSet = new Set();
        weeks.forEach(entry => {
            const sched = entry.schedule || {};
            Object.keys(sched).forEach(name => {
                const emp = window.employees ? window.employees.find(e => e.name === name) : null;
                if (!emp || emp.activo !== false && emp.activo !== 0) {
                    empSet.add(name);
                }
            });
        });
        const empList = Array.from(empSet).sort();

        // Clasificación de turnos
        function classifyShift(shift) {
            if (!shift || shift === "OFF") return "off";        // día libre normal → NO se cuenta
            if (shift === "VAC") return "vac";
            if (shift === "PERM") return "perm";
            if (shift === "N_22-05") return "nocturno";
            const hourMatch = shift.match(/[_](\d+)/);
            if (hourMatch) {
                const h = parseInt(hourMatch[1], 10);
                return h < 12 ? "matutino" : "vespertino";
            }
            return "off";
        }

        // ── Config de tipos visibles ──
        // `cls` se usa para el nombre de clase CSS del pill (type-pill-{cls})
        const TYPE_CFG = {
            matutino:    { fill: '#3b82f6', label: 'AM', name: 'Matutino',    short: 'AM',  cls: 'am' },
            vespertino:  { fill: '#f97316', label: 'PM', name: 'Vespertino',  short: 'PM',  cls: 'pm' },
            nocturno:    { fill: '#8b5cf6', label: 'N',  name: 'Nocturno',    short: 'N',   cls: 'n'  },
            vac:         { fill: '#f59e0b', label: 'V',  name: 'Vacaciones',  short: 'VAC', cls: 'vac'},
            perm:        { fill: '#ef4444', label: 'P',  name: 'Permiso',     short: 'PERM',cls: 'perm'},
        };
        const VISIBLE_TYPES = ["matutino","vespertino","nocturno","vac","perm"];

        function countDayTypes(days) {
            const counts = { matutino: 0, vespertino: 0, nocturno: 0, vac: 0, perm: 0, off: 0 };
            Object.values(days).forEach(s => {
                const t = classifyShift(s);
                counts[t] = (counts[t] || 0) + 1;
            });
            return counts;
        }

        function isConsistentWeek(counts) {
            const active = VISIBLE_TYPES.filter(t => (counts[t] || 0) > 0);
            return active.length === 1;
        }

        /** Barra: opacidad 0.45 para colores más vívidos */
        function buildBarData(days) {
            const counts = countDayTypes(days);
            const total = VISIBLE_TYPES.reduce((s, t) => s + (counts[t] || 0), 0) || 1;
            let segments = '';
            const parts = [];
            VISIBLE_TYPES.forEach(t => {
                const c = counts[t] || 0;
                if (c === 0) return;
                const pct = (c / total) * 100;
                const cfg = TYPE_CFG[t];
                segments += `<span style="width:${pct}%;background:${cfg.fill};opacity:0.45;"></span>`;
                parts.push(`${c} ${cfg.label}`);
            });
            if (!segments) {
                segments = `<span style="width:100%;background:var(--border);opacity:0.2;"></span>`;
                parts.push('Sin datos');
            }
            return { segments, breakdown: parts.join(' · ') };
        }

        /** Pill si semana 100% consistente, mini bar si mixto */
        function renderCellContent(days) {
            const counts = countDayTypes(days);
            if (isConsistentWeek(counts)) {
                const type = VISIBLE_TYPES.find(t => counts[t] > 0) || 'off';
                if (type === 'off') return `<span class="type-pill type-pill-off">—</span>`;
                const cfg = TYPE_CFG[type];
                return `<span class="type-pill type-pill-${cfg.cls}">${cfg.short}</span>`;
            }
            const { segments, breakdown } = buildBarData(days);
            return `<div class="hist-bar" title="${breakdown}">${segments}</div>`;
        }

        /** Persona de libres: badge + hover reveal */
        function renderLibresCell(days) {
            const { segments, breakdown } = buildBarData(days);
            return `<div class="hist-libres-wrap">
                <span class="hist-libres-badge">LIBRES</span>
                <div class="hist-libres-hover">
                    <div class="hist-bar">${segments}</div>
                    <div class="hist-bar-legend">${breakdown}</div>
                </div>
            </div>`;
        }

        

        // ── Detectar persona de libres por semana ──
        // Orden: 1) metadata.libres_person (solver) → 2) schedule N_22-05 (historiales viejos)
        function findLibresForWeek(entry) {
            const meta = entry.metadata || {};
            if (meta.libres_person) return meta.libres_person;
            // Fallback para historiales viejos: buscar N_22-05 en schedule
            const sched = entry.schedule || {};
            let best = null, bestCount = 0;
            for (const [ename, days] of Object.entries(sched)) {
                if (!days || typeof days !== 'object') continue;
                let n = 0;
                for (const shift of Object.values(days)) {
                    if (shift === 'N_22-05') n++;
                }
                if (n > 0 && n <= 4 && n > bestCount) { bestCount = n; best = ename; }
            }
            return best;
        }
        const empCache = window.employees || [];
        const libresByWeek = [];
        weeks.forEach((entry, wi) => {
            const person = findLibresForWeek(entry);
            if (person) {
                libresByWeek.push({ weekIdx: wi, label: entry.name || entry.nombre || `Semana`, person });
            }
        });
        const libresPersonMap = {};
        libresByWeek.forEach(lb => { libresPersonMap[lb.weekIdx] = lb.person; });

        // ── Detectar empleados con horario fijo (no mostrar pill/barra) ──
        function isFixedScheduleEmployee(name) {
            if (name === 'Refuerzo') return true;
            const emp = empCache.find(e => e.name === name);
            if (!emp || !emp.fixed_shifts) return false;
            const working = Object.values(emp.fixed_shifts).filter(s => s && s !== 'OFF' && s !== 'VAC' && s !== 'PERM');
            return working.length >= 5;
        }

        // ── Modal HTML ──
        let html = `<div class="modal-backdrop" id="history-matrix-backdrop">
            <div class="modal-dialog large" style="max-width: 900px;">
                <div class="modal-header-simple">
                    <h3><i class="fa-solid fa-clock-rotate-left" style="color:var(--primary);"></i> Historial de Turnos</h3>
                    <button class="close-icon" onclick="closeHistoryMatrix()"><i class="fa-solid fa-xmark"></i></button>
                </div>
                <div class="modal-body-scroll" style="padding: 1.25rem 1.5rem;">`;

        // ── Sección: Persona de Libres ──
        if (libresByWeek.length > 0) {
            html += `<div style="background: var(--primary-subtle); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 0.85rem 1rem; margin-bottom: 1.25rem; display: flex; flex-wrap: wrap; align-items: center; gap: 0.75rem;">
                <span style="font-weight: 700; font-size: var(--fs-sm); color: var(--primary); white-space: nowrap;">
                    <i class="fa-solid fa-people-arrows"></i> Persona de Libres:
                </span>`;
            libresByWeek.forEach(lb => {
                html += `<span style="background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 0.3rem 0.65rem; font-size: var(--fs-sm); white-space: nowrap;">
                    <strong>${escapeHtml(lb.person)}</strong>
                    <span style="color: var(--text-muted); margin-left: 0.3rem;">(${escapeHtml(lb.label)})</span>
                </span>`;
            });
            html += `</div>`;
        }

        // ── Tabla Matriz ──
        html += `<div style="overflow-x: auto; border: 1px solid var(--border); border-radius: var(--radius-md);">
            <table class="hist-matrix-table" style="width: 100%; border-collapse: collapse; font-size: var(--fs-sm);">
                <thead>
                    <tr>
                        <th class="sticky-emp" style="position: sticky; left: 0; z-index: 2; background: var(--bg-panel); padding: 0.6rem 0.75rem; text-align: left; font-weight: 700; color: var(--text-main); border-bottom: 2px solid var(--border); min-width: 130px;">Empleado</th>`;

        weeks.forEach(w => {
            const label = w.name || w.nombre || `Semana`;
            html += `<th class="week-col" style="padding: 0.6rem 0.5rem; text-align: center; font-weight: 600; color: var(--text-muted); border-bottom: 2px solid var(--border); font-size: var(--fs-xs); white-space: nowrap;">${escapeHtml(label)}</th>`;
        });

        html += `</tr></thead><tbody>`;

        empList.forEach(name => {
            const skipCell = isFixedScheduleEmployee(name);
            html += `<tr>
                <td class="sticky-emp" style="position: sticky; left: 0; z-index: 1; background: var(--bg-panel); padding: 0.5rem 0.75rem; font-weight: 600; color: var(--text-main); border-bottom: 1px solid var(--border);">
                    <span>${escapeHtml(name)}</span>
                </td>`;
            weeks.forEach((entry, wi) => {
                if (skipCell) {
                    html += `<td style="padding: 0.3rem 0.4rem; border-bottom: 1px solid var(--border);"></td>`;
                    return;
                }
                const sched = entry.schedule || {};
                const days = sched[name] || {};
                const weekLibres = libresPersonMap[wi];
                if (weekLibres === name) {
                    html += `<td style="padding: 0.3rem 0.4rem; border-bottom: 1px solid var(--border); vertical-align: middle; background: var(--success-subtle);">${renderLibresCell(days)}</td>`;
                    return;
                }
                html += `<td style="padding: 0.3rem 0.4rem; border-bottom: 1px solid var(--border); vertical-align: middle;">${renderCellContent(days)}</td>`;
            });
            html += `</tr>`;
        });

        html += `</tbody></table></div>`;

        // ── Leyenda ──
        html += `<div style="display: flex; flex-wrap: wrap; gap: 1rem; margin-top: 1rem; padding: 0.75rem 1rem; background: var(--bg-app); border-radius: var(--radius-md); border: 1px solid var(--border); align-items: center;">
            <span style="font-size: var(--fs-xs); font-weight: 600; color: var(--text-muted); margin-right: 0.25rem;">Leyenda:</span>
            <span style="display: inline-flex; align-items: center; gap: 0.35rem; font-size: var(--fs-xs); color: var(--text-muted);">
                <span style="width: 18px; height: 6px; border-radius: 3px; background: #3b82f6; opacity: 0.35;"></span> AM
            </span>
            <span style="display: inline-flex; align-items: center; gap: 0.35rem; font-size: var(--fs-xs); color: var(--text-muted);">
                <span style="width: 18px; height: 6px; border-radius: 3px; background: #f97316; opacity: 0.35;"></span> PM
            </span>
            <span style="display: inline-flex; align-items: center; gap: 0.35rem; font-size: var(--fs-xs); color: var(--text-muted);">
                <span style="width: 18px; height: 6px; border-radius: 3px; background: #8b5cf6; opacity: 0.35;"></span> N
            </span>
            <span style="display: inline-flex; align-items: center; gap: 0.35rem; font-size: var(--fs-xs); color: var(--text-muted);">
                <span style="width: 18px; height: 6px; border-radius: 3px; background: #f59e0b; opacity: 0.35;"></span> VAC
            </span>
            <span style="display: inline-flex; align-items: center; gap: 0.35rem; font-size: var(--fs-xs); color: var(--text-muted);">
                <span style="width: 18px; height: 6px; border-radius: 3px; background: #ef4444; opacity: 0.35;"></span> PERM
            </span>
            <span style="display: inline-flex; align-items: center; gap: 0.35rem; font-size: var(--fs-xs); color: var(--text-muted); margin-left: 0.5rem;">
                <span style="display: inline-block; background: var(--success-subtle); color: var(--success); font-weight: 700; font-size: 0.55rem; padding: 1px 6px; border-radius: 4px; text-transform: uppercase;">Libres</span> Persona de Libres
            </span>
        </div>`;

        // ── Helper text ──
        html += `<p style="font-size: var(--fs-xs); color: var(--text-muted); text-align: center; margin-top: 0.75rem; margin-bottom: 0;">
                    <i class="fa-solid fa-info-circle"></i>
                    Los <strong>pills</strong> (AM / PM / N) indican semanas consistentes.
                    La <strong>barra</strong> muestra la distribución cuando hay tipos mixtos (excluye días libres).
                    Pasá el mouse sobre <strong>LIBRES</strong> para ver su distribución real.
                </p>
                </div>
            </div>
        </div>`;

        const container = document.createElement("div");
        container.id = "history-matrix-modal";
        container.innerHTML = html;
        document.body.appendChild(container);

    } catch (err) {
        console.error("Error loading history matrix:", err);
        alert("Error al cargar historial: " + err.message);
    }
}

function closeHistoryMatrix(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.getElementById("history-matrix-modal");
    if (modal) modal.remove();
}

// ═══════════════════════════════════════════════
// FOLDERS — carpetas por año
// ═══════════════════════════════════════════════

let foldersCache = [];

function toggleFoldersSection() {
    const body = document.getElementById("foldersBody");
    const arrow = document.getElementById("foldersArrow");
    if (!body || !arrow) return;
    body.classList.toggle("hidden");
    arrow.classList.toggle("rotated");
}

function toggleFolderCreate() {
    const input = document.getElementById("folderNameInput");
    const btn = document.getElementById("btnToggleFolderCreate");
    if (!input || !btn) return;
    const isHidden = input.style.display === "none" || !input.style.display;
    input.style.display = isHidden ? "inline-block" : "none";
    if (isHidden) { input.focus(); btn.innerHTML = '<i class="fa-solid fa-times"></i> Cancelar'; }
    else { btn.innerHTML = '<i class="fa-solid fa-folder-plus"></i> Nueva'; }
}

async function createFolder() {
    const input = document.getElementById("folderNameInput");
    if (!input) return;
    const name = input.value.trim();
    if (!name) { alert("Ingresá un nombre para la carpeta (ej: 2026)."); return; }
    try {
        const res = await fetch('/api/folders', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        if (!res.ok) throw new Error(await res.text());
        input.value = "";
        input.style.display = "none";
        document.getElementById("btnToggleFolderCreate").innerHTML = '<i class="fa-solid fa-folder-plus"></i> Nueva';
        await loadFolders();
        setStatusMessage(`Carpeta "${name}" creada.`, "success");
    } catch (e) {
        alert("Error al crear carpeta: " + e.message);
    }
}

async function loadFolders() {
    const container = document.getElementById("foldersList");
    if (!container) return;
    try {
        const res = await fetch('/api/folders');
        const folders = await res.json();
        foldersCache = folders;
        if (!folders.length) {
            container.innerHTML = '<div class="empty-msg" style="padding:1rem;text-align:center;color:var(--text-muted);font-size:0.85rem;"><i class="fa-solid fa-folder-open"></i> Sin carpetas aún. Creá una para agrupar horarios del año.</div>';
            return;
        }
        container.innerHTML = folders.map(f => `
            <div class="folder-card">
                <div class="folder-card-info" onclick="openFolderDetail(${f.id})" style="cursor:pointer;flex:1;">
                    <div class="folder-card-icon"><i class="fa-solid fa-folder"></i></div>
                    <div>
                        <div class="folder-card-name">${escapeHtml(f.name)}</div>
                        <div class="folder-card-count">${f.entry_count} horario${f.entry_count !== 1 ? 's' : ''}</div>
                    </div>
                </div>
                <div class="folder-card-actions">
                    <button class="btn-icon" onclick="event.stopPropagation();deleteFolder(${f.id})" title="Eliminar carpeta">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </div>
            </div>
        `).join('');
    } catch (e) {
        console.error("Error loading folders:", e);
        container.innerHTML = '<div class="error-msg">Error al cargar carpetas</div>';
    }
}

async function deleteFolder(folderId) {
    const folder = foldersCache.find(f => f.id === folderId);
    const hasEntries = folder && folder.entry_count > 0;
    let msg = `¿Eliminar la carpeta "${folder?.name || ''}"?`;
    if (hasEntries) {
        msg = `¡ATENCIÓN! La carpeta "${folder?.name || ''}" contiene ${folder.entry_count} horario(s).\n\n`;
        msg += `Al eliminarla, TODOS los horarios se irán a la papelera por 7 días.\n\n`;
        msg += `¿Estás ABSOLUTAMENTE seguro? (3 clics necesarios)`;
    }
    if (hasEntries) {
        if (!confirm(msg)) return;
        if (!confirm(`⚠️ CONFIRMACIÓN 2/3: ¿Seguro que querés eliminar "${folder?.name || ''}" con TODOS sus horarios?`)) return;
        if (!confirm(`🚨 CONFIRMACIÓN 3/3: Esta acción es irreversible. ¿Eliminar definitivamente?`)) return;
    } else {
        if (!confirm(msg)) return;
    }
    try {
        const res = await fetch(`/api/folders/${folderId}?purge=${hasEntries ? 'false' : 'false'}`, { method: 'DELETE' });
        if (!res.ok) throw new Error(await res.text());
        await loadFolders();
        setStatusMessage(hasEntries ? `Carpeta enviada a papelera.` : "Carpeta eliminada.", "success");
    } catch (e) {
        alert("Error: " + e.message);
    }
}

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
        modal.innerHTML = `
            <div class="modal-dialog large" style="max-width: 600px;">
                <div class="modal-header-simple">
                    <h3><i class="fa-solid fa-folder-open" style="color:var(--primary);"></i> ${escapeHtml(folder.name)}</h3>
                    <button class="close-icon" onclick="document.getElementById('folderDetailModal').remove()"><i class="fa-solid fa-xmark"></i></button>
                </div>
                <div class="modal-body-scroll">
                    ${entries.length === 0 ? '<p style="text-align:center;color:var(--text-muted);padding:2rem 0;">La carpeta está vacía.</p>' : ''}
                    ${entries.map(e => `
                        <div class="folder-detail-entry">
                            <div>
                                <span class="folder-detail-entry-name">${escapeHtml(e.name)}</span>
                                <span class="folder-detail-entry-date">${e.timestamp ? new Date(e.timestamp).toLocaleDateString() : ''}</span>
                            </div>
                            <div style="display:flex;gap:0.4rem;">
                                <button class="btn-icon" onclick="exportHistoryExcelByDbId(${e.db_id})" title="Exportar Excel">
                                    <i class="fa-solid fa-file-excel"></i>
                                </button>
                                <button class="btn-icon" onclick="removeFromFolder(${folderId}, ${e.db_id})" title="Quitar de carpeta">
                                    <i class="fa-solid fa-xmark" style="color:var(--danger);"></i>
                                </button>
                            </div>
                        </div>
                    `).join('')}
                </div>
                ${entries.length > 0 ? `
                <div class="modal-actions-footer" style="justify-content:space-between;">
                    <span style="font-size:0.8rem;color:var(--text-muted);">${entries.length} horario${entries.length !== 1 ? 's' : ''}</span>
                    <button class="btn-action primary" onclick="exportFolderExcel(${folderId})">
                        <i class="fa-solid fa-file-excel"></i> Exportar todo como Excel
                    </button>
                </div>` : ''}
            </div>
        `;
        document.body.appendChild(modal);
        modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
    } catch (e) {
        alert("Error: " + e.message);
    }
}

function addHistoryToFolder(i, event) {
    event.stopPropagation();
    const entry = historyEntriesCache[i];
    if (!entry || !entry.db_id) {
        alert("No se pudo identificar este historial.");
        return;
    }
    if (!foldersCache || !foldersCache.length) {
        alert("No hay carpetas creadas aún. Creá una carpeta primero.");
        return;
    }

    // Remove existing modal if any
    const existing = document.getElementById("addToFolderModal");
    if (existing) existing.remove();

    const modal = document.createElement("div");
    modal.id = "addToFolderModal";
    modal.className = "modal-backdrop";
    modal.innerHTML = `
        <div class="modal-dialog" style="max-width: 360px;">
            <div class="modal-header-simple">
                <h3>Agregar a carpeta</h3>
                <button class="close-icon" onclick="document.getElementById('addToFolderModal').remove()"><i class="fa-solid fa-xmark"></i></button>
            </div>
            <div class="modal-body-scroll" style="max-height: 60vh;">
                ${foldersCache.map(f => `
                    <div class="folder-select-item" onclick="addToFolder(${f.id}, ${entry.db_id}); document.getElementById('addToFolderModal').remove();" style="cursor:pointer;padding:0.6rem 0.8rem;display:flex;align-items:center;gap:0.5rem;border-bottom:1px solid var(--border);transition:background 0.15s;" onmouseover="this.style.background='var(--bg-hover)'" onmouseout="this.style.background='transparent'">
                        <i class="fa-solid fa-folder" style="color:var(--primary);"></i>
                        <span>${escapeHtml(f.name)}</span>
                        <span style="margin-left:auto;font-size:0.75rem;color:var(--text-muted);">${f.entry_count} horario${f.entry_count !== 1 ? 's' : ''}</span>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });
}

async function addToFolder(folderId, entryDbId) {
    try {
        const res = await fetch(`/api/folders/${folderId}/entries`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ entry_ids: [entryDbId] })
        });
        if (!res.ok) throw new Error(await res.text());
        setStatusMessage("Horario agregado a carpeta.", "success");
        await loadFolders();
    } catch (e) {
        alert("Error: " + e.message);
    }
}

async function removeFromFolder(folderId, entryDbId) {
    try {
        const res = await fetch(`/api/folders/${folderId}/entries/${entryDbId}`, { method: 'DELETE' });
        if (!res.ok) throw new Error(await res.text());
        openFolderDetail(folderId); // Refresh
        await loadFolders();
    } catch (e) {
        alert("Error: " + e.message);
    }
}

async function exportFolderExcel(folderId) {
    try {
        const res = await fetch(`/api/folders/${folderId}/export-excel`);
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Error al exportar");
        }
        const data = await res.json();
        showExportConfirmationModal(data.filename, 'excel');
    } catch (e) {
        alert(e.message);
    }
}

async function exportHistoryExcelByDbId(dbId) {
    // Reuse the existing export flow via the /api/export_excel endpoint
    window.open(`/api/export_excel?history_db_id=${dbId}`, '_blank');
}

