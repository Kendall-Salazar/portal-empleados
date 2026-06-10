// ========================================================================
// Chronos — Schedule Renderer
// Renderizado de tabla de horarios, export, validación UI
// ========================================================================

/* ── Shift Info & Time Parsing ── */
function getShiftInfo(s) {
    const effectiveShift = normalizeFlexibleShiftInput(s) || s;
    if (!effectiveShift || effectiveShift === "OFF") return { class: "pill-off", icon: "fa-mug-hot", text: "LIBRE" };
    if (effectiveShift === "Q3_05-11+17-22") return { class: "pill-night", icon: "fa-bolt", text: "05-11 / 17-22" };
    let typeClass = "pill-morning";
    let icon = "fa-sun";
    if (effectiveShift === "VAC") return { class: "pill-vac", icon: "fa-plane", text: "VAC" };
    if (effectiveShift === "PERM") return { class: "pill-perm", icon: "fa-file-signature", text: "PERM" };
    const match = typeof effectiveShift === "string" ? effectiveShift.match(/_(\d{1,2})/) : null;
    let startHour = 8;
    if (match) startHour = parseInt(match[1]);
    if (effectiveShift.includes("N_") || startHour >= 20 || startHour <= 4) { typeClass = "pill-night"; icon = "fa-moon"; }
    else if (startHour >= 12) { typeClass = "pill-afternoon"; icon = "fa-cloud-sun"; }
    let rangePart = effectiveShift.split('_').slice(1).join('_');
    if (!rangePart && effectiveShift.includes("-")) rangePart = effectiveShift;
    let timeText = formatTimeRange(rangePart);
    if (!timeText) timeText = s;
    return { class: typeClass, icon, text: timeText };
}
window.getShiftInfo = getShiftInfo;

function formatTimeRange(rangeStr) {
    if (!rangeStr) return "";
    if (rangeStr.includes("+")) return rangeStr.split("+").map(formatTimeRange).join(" / ");
    const parts = rangeStr.split("-");
    if (parts.length !== 2) return rangeStr;
    const start = parseInt(parts[0]); const end = parseInt(parts[1]);
    const formatH = (h) => {
        let period = h >= 12 && h < 24 ? "PM" : "AM";
        if (h >= 24) period = "AM";
        let hour = h % 12; if (hour === 0) hour = 12;
        return `${hour.toString().padStart(2, '0')}:00 ${period}`;
    };
    return `${formatH(start)} - ${formatH(end)}`;
}

function parseFlexibleTimeToken(token) {
    if (!token) return null;
    const compact = token.toString().trim().toLowerCase().replace(/\./g, "").replace(/\s+/g, "");
    if (!compact) return null;
    let match = compact.match(/^(\d{1,2})(?::(\d{2}))?(am|pm)$/);
    if (match) {
        let hour = parseInt(match[1], 10); const minutes = match[2] ? parseInt(match[2], 10) : 0;
        const suffix = match[3];
        if (Number.isNaN(hour) || Number.isNaN(minutes) || minutes !== 0 || hour < 1 || hour > 12) return null;
        if (suffix === "am") { if (hour === 12) hour = 0; } else if (hour !== 12) { hour += 12; }
        return hour;
    }
    match = compact.match(/^(\d{1,2})(?::(\d{2}))?$/);
    if (!match) return null;
    const hour = parseInt(match[1], 10); const minutes = match[2] ? parseInt(match[2], 10) : 0;
    if (Number.isNaN(hour) || Number.isNaN(minutes) || minutes !== 0 || hour < 0 || hour > 29) return null;
    return hour;
}

function splitFlexibleRangeSegment(segment) {
    const cleaned = (segment || "").trim().replace(/[–—]/g, "-");
    if (!cleaned) return null;
    let parts = cleaned.split(/\s*-\s*/); if (parts.length === 2) return parts;
    parts = cleaned.split(/\s+a\s+/i); if (parts.length === 2) return parts;
    parts = cleaned.split(/\s+to\s+/i); if (parts.length === 2) return parts;
    return null;
}

function normalizeFlexibleShiftInput(value) {
    if (value === null || value === undefined) return null;
    const raw = value.toString().trim(); if (!raw) return null;
    const upper = raw.toUpperCase();
    if (["OFF", "LIBRE", "DESCANSO"].includes(upper)) return "OFF";
    if (["VAC", "VACACIONES"].includes(upper)) return "VAC";
    if (["PERM", "PERMISO"].includes(upper)) return "PERM";
    if (upper === "AUTO") return "AUTO";
    if (SHIFT_HOURS[upper] !== undefined) return upper;
    let candidate = raw;
    if (upper.startsWith(MANUAL_SHIFT_PREFIX)) candidate = raw.slice(MANUAL_SHIFT_PREFIX.length);
    const segments = candidate.split(/\s*(?:\+|\/|,)\s*/).filter(Boolean);
    if (!segments.length) return null;
    const normalizedSegments = [];
    for (const segment of segments) {
        const split = splitFlexibleRangeSegment(segment);
        if (!split) return null;
        const start = parseFlexibleTimeToken(split[0]); const end = parseFlexibleTimeToken(split[1]);
        if (start === null || end === null) return null;
        normalizedSegments.push(`${String(start).padStart(2, "0")}-${String(end).padStart(2, "0")}`);
    }
    return `${MANUAL_SHIFT_PREFIX}${normalizedSegments.join("+")}`;
}
window.normalizeFlexibleShiftInput = normalizeFlexibleShiftInput;

function getShiftHoursList(shiftCode) {
    const normalized = normalizeFlexibleShiftInput(shiftCode) || shiftCode;
    const rules = validationRules || baseValidationRules;
    const knownHours = rules?.shift_sets?.[normalized];
    if (knownHours && knownHours.length) return [...knownHours];
    if (!normalized || typeof normalized !== "string" || !normalized.startsWith(MANUAL_SHIFT_PREFIX)) return [];
    const rangePart = normalized.slice(MANUAL_SHIFT_PREFIX.length);
    const hours = new Set();
    rangePart.split("+").forEach(segment => {
        const [startRaw, endRaw] = segment.split("-");
        const start = parseInt(startRaw, 10); let end = parseInt(endRaw, 10);
        if (Number.isNaN(start) || Number.isNaN(end)) return;
        if (end <= start) end += 24;
        for (let h = start; h < end; h++) hours.add(h);
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

function getShiftEndExclusiveHour(shiftCode) {
    const hours = getShiftHoursList(shiftCode);
    if (!hours.length) return null;
    return Math.max(...hours) + 1;
}

function restHoursBetweenShiftsClient(s1, s2) {
    const non = ["OFF", "VAC", "PERM"];
    if (!s1 || !s2 || non.includes(s1) || non.includes(s2)) return null;
    const end1 = getShiftEndExclusiveHour(s1); const start2 = getShiftStartHour(s2);
    if (end1 == null || start2 == null) return null;
    return (start2 + 24) - end1;
}

function buildRestReportClient(schedule, targetHours = 12) {
    const per = {};
    const names = Object.keys(schedule || {});
    names.forEach((e) => {
        const gaps = []; let minG = null;
        for (let i = 0; i < DAYS.length - 1; i++) {
            const d1 = DAYS[i]; const d2 = DAYS[i + 1];
            const a = schedule[e]?.[d1]; const b = schedule[e]?.[d2];
            const h = restHoursBetweenShiftsClient(a, b);
            if (h == null) continue;
            gaps.push({ from: d1, to: d2, hours: h, meets_target: h >= targetHours, meets_applied: h >= targetHours });
            minG = minG === null ? h : Math.min(minG, h);
        }
        per[e] = { min_gap_hours: minG, gaps, meets_target: minG === null || minG >= targetHours, meets_applied: minG === null || minG >= targetHours };
    });
    return { per_employee: per, target_hours: targetHours, applied_hours: targetHours, client_only: true };
}

let currentSortMode = 'time';
const historySortModes = new Map();

function getAverageStartHour(name, schedule) {
    const days = ["Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue"];
    let sum = 0; let count = 0;
    if (!schedule[name]) return 24;
    days.forEach(d => {
        const s = schedule[name][d];
        if (!s || s === "OFF" || s === "VAC") { sum += 24; count++; return; }
        sum += getShiftStartHour(s); count++;
    });
    return count === 0 ? 24 : sum / count;
}

/* ── View Toggles ── */
let isVerticalView = false;
function toggleVerticalView() {
    isVerticalView = !isVerticalView;
    const btn = document.getElementById("btnToggleVertical");
    if (btn) {
        if (isVerticalView) { btn.classList.add("primary"); btn.innerHTML = `<i class="fa-solid fa-table"></i> Vista Horizontal`; }
        else { btn.classList.remove("primary"); btn.innerHTML = `<i class="fa-solid fa-bars-staggered"></i> Vista Vertical`; }
    }
    if (currentGeneratedSchedule) {
        renderSchedule(currentGeneratedSchedule, "#scheduleTable", currentDailyTasks || {});
        if (isValidationOn && typeof applyValidationUI === "function") applyValidationUI();
    }
}
window.toggleVerticalView = toggleVerticalView;

function toggleHoursColumn() {
    document.querySelectorAll(".col-hours").forEach(el => el.classList.toggle("hidden-col"));
}
window.toggleHoursColumn = toggleHoursColumn;

/* ── Schedule Actions Menu ── */
window.toggleScheduleActionsMenu = function (event) {
    if (event) event.stopPropagation();
    const dropdown = document.getElementById("scheduleActionsDropdown");
    const trigger = document.getElementById("btnScheduleActionsMenu");
    if (!dropdown) return;
    const isOpen = !dropdown.classList.contains("hidden");
    if (isOpen) { dropdown.classList.add("hidden"); if (trigger) trigger.setAttribute("aria-expanded", "false"); }
    else {
        dropdown.classList.remove("hidden"); if (trigger) trigger.setAttribute("aria-expanded", "true");
        setTimeout(() => {
            const handler = (e) => {
                if (!dropdown.contains(e.target) && e.target !== trigger && !trigger?.contains(e.target)) {
                    dropdown.classList.add("hidden"); if (trigger) trigger.setAttribute("aria-expanded", "false");
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

/* ── Main Schedule Render ── */
function renderSchedule(schedule, tableSelector, tasks = {}, specialDaysOverride = null, metadataHolidayDays = null, weekDatesOverride = null) {
    const tableEl = document.querySelector(tableSelector);
    const thead = document.querySelector(`${tableSelector} thead tr`);
    const tbody = document.querySelector(`${tableSelector} tbody`);
    if (!tbody || !thead || !tableEl) return;
    tbody.innerHTML = ""; thead.innerHTML = "";
    let keys = Object.keys(schedule);
    let isHistory = tableSelector.includes("hist");
    let historyIndex = isHistory ? parseInt(tableSelector.split("-").pop()) : null;
    const effectiveSortMode = isHistory ? (historySortModes.get(historyIndex) || 'time') : currentSortMode;
    if (effectiveSortMode === 'time') { keys.sort((a, b) => { const avgA = getAverageStartHour(a, schedule); const avgB = getAverageStartHour(b, schedule); if (Math.abs(avgA - avgB) < 0.01) return a.localeCompare(b); return avgA - avgB; }); }
    else { keys.sort((a, b) => a.localeCompare(b, 'es', { sensitivity: 'base' })); }
    const verticalAliases = isHistory ? (historyEntriesCache[historyIndex]?.metadata?.display_aliases || {}) : {};

    if (isVerticalView) {
        tableEl.classList.add("vertical-table");
        const weekDatesMapV = weekDatesOverride != null ? weekDatesOverride : getWeekDatesMap();
        const specialDaysV = specialDaysOverride ?? currentMetadata?.special_days ?? {};
        thead.innerHTML = `<th class="th-horario-col" style="width:120px; text-align:center;">Horario</th>`;
        DAYS.forEach(d => {
            const holiday = getHolidayForDay(d, weekDatesMapV, metadataHolidayDays);
            const isClosedV = specialDaysV[d] === 'closed';
            const closedBadgeV = isClosedV ? `<span class="th-day-head-badge-closed">CERRADO</span>` : '';
            const holidayIcon = holiday ? `<i class="fa-solid fa-star th-day-head-star" title="${escapeHtmlAttr(holiday.name)}"></i>` : '';
            const clickAction = isHistory ? `onclick="openHolidayDayModal('${d}', ${historyIndex})" style="cursor:pointer;"` : '';
            thead.innerHTML += `<th class="th-day-col${isClosedV ? ' th-closed' : ''}${holiday ? ' th-holiday' : ''}" ${clickAction}><div class="th-day-col-inner" style="font-size:1.1rem; font-weight:800; color:var(--text-main);"><span class="th-day-name">${d}</span>${closedBadgeV}${holidayIcon}</div></th>`;
        });
        let uniqueShifts = new Set();
        keys.forEach(name => { DAYS.forEach(d => { const s = schedule[name][d]; if (s && s !== "OFF" && s !== "VAC" && s !== "PERM") uniqueShifts.add(s); }); });
        let shiftArray = Array.from(uniqueShifts).sort((a, b) => getAverageStartHour("dummy", { "dummy": { "Vie": a } }) - getAverageStartHour("dummy", { "dummy": { "Vie": b } }));
        shiftArray.push("OFF_GROUP");
        shiftArray.forEach(shiftCode => {
            const row = document.createElement("tr");
            if (shiftCode === "OFF_GROUP") { row.innerHTML = `<td style="font-weight:700; color:var(--text-muted); text-align:center; font-size:0.9rem; background:var(--bg-app);"><i class="fa-solid fa-bed"></i> Descanso / Ausentes</td>`; }
            else { const info = getShiftInfo(shiftCode); row.innerHTML = `<td style="font-weight:700; color:var(--text-main); text-align:center; font-size:0.9rem;"><div style="margin-bottom:4px;"><i class="fa-solid ${info.icon}" style="color:var(--text-muted);"></i></div>${info.text}</td>`; }
            DAYS.forEach(d => {
                const holidayTd = getHolidayForDay(d, weekDatesMapV, metadataHolidayDays);
                const isClosedTd = specialDaysV[d] === "closed";
                let cellHtml = `<td class="${isClosedTd ? 'closed-col' : ''}${holidayTd ? ' holiday-col' : ''}" style="vertical-align: top;"><div style="display:flex; flex-direction:column; gap:0.5rem; min-height:60px;">`;
                keys.forEach(name => {
                    const s = schedule[name][d] || "OFF";
                    let belongsInRow = shiftCode === "OFF_GROUP" ? (s === "OFF" || s === "VAC" || s === "PERM") : (s === shiftCode);
                    if (belongsInRow) {
                        const emp = employees.find(e => e.name === name);
                        const role = name === "Refuerzo" ? "REF" : (emp && sqlIntFlagOn(emp.is_jefe_pista) ? "JEFE" : (emp && emp.is_practicante ? "PRACT" : ""));
                        const nightBadge = emp && emp.can_do_night ? '<i class="fa-solid fa-moon" style="font-size:0.7em;"></i> ' : '';
                        let info = getShiftInfo(s);
                        const closedOffCard = isHistory && isClosedTd && s === "OFF";
                        let tagHtml = role ? `<div style="font-size:0.6rem; opacity:0.8; margin-top:2px;">${role}</div>` : "";
                        let taskData = { ...(tasks || {}) };
                        if (isHistory) { taskData._is_history = true; taskData._history_index = historyIndex; }
                        let taskHtml = getTaskLabelHTML(taskData, name, d);
                        let historyAttrs = "", cursorStyle = "";
                        if (isHistory) {
                            historyAttrs = `data-history-index="${historyIndex}" data-employee-name="${escapeHtmlAttr(name)}" data-day="${escapeHtmlAttr(d)}" onmousedown="beginHistorySelection(event, this)" onmouseenter="extendHistorySelection(event, this)" onclick="handleHistoryCellClick(event, this)"`;
                            cursorStyle = "cursor:pointer; user-select:none;";
                        }
                        const pillClass = closedOffCard ? `shift-pill pill-closed-establishment${isHistory ? " history-shift-pill" : ""}` : `shift-pill ${info.class}${isHistory ? " history-shift-pill" : ""}`;
                        const verticalDisplayName = isHistory && verticalAliases[name] ? verticalAliases[name] : name;
                        cellHtml += `<div class="${pillClass}" ${historyAttrs} style="min-height:auto; padding:0.4rem; flex-direction:row; justify-content:space-between; ${cursorStyle}"><div style="display:flex; flex-direction:column; align-items:flex-start; text-align:left;"><span style="font-weight:700; font-size:0.9rem;">${nightBadge}${verticalDisplayName}</span>${closedOffCard ? '<span class="pill-closed-inline-label">Cerrado</span>' : ""}${tagHtml}</div><div style="display:flex; align-items:center;">${taskHtml}</div></div>`;
                    }
                });
                cellHtml += `</div></td>`; row.innerHTML += cellHtml;
            });
            tbody.appendChild(row);
        });
    } else {
        tableEl.classList.remove("vertical-table");
        const activeSortMode = isHistory ? (historySortModes.get(historyIndex) || 'time') : currentSortMode;
        const sortIconClass = activeSortMode === 'time' ? 'fa-solid fa-clock sort-active-time' : 'fa-solid fa-sort-alpha-down sort-active-alpha';
        const sortTitle = activeSortMode === 'time' ? 'Ordenado por hora — click para ordenar A-Z' : 'Ordenado A-Z — click para ordenar por hora';
        const weekDatesMap = weekDatesOverride != null ? weekDatesOverride : getWeekDatesMap();
        const specialDays = specialDaysOverride ?? currentMetadata?.special_days ?? {};
        thead.innerHTML = `<th id="${isHistory ? `th-collaborator-hist-${historyIndex}` : 'th-collaborator'}" style="cursor:pointer; min-width:160px; user-select:none;" title="${sortTitle}">Empleado <i class="${sortIconClass}" style="font-size:0.75rem; margin-left:4px;"></i></th>${DAYS.map(d => {
            const holiday = getHolidayForDay(d, weekDatesMap, metadataHolidayDays);
            const isClosed = specialDays[d] === 'closed';
            const closedBadge = isClosed ? `<span class="th-day-head-badge-closed">CERRADO</span>` : '';
            const holidayIcon = holiday ? `<i class="fa-solid fa-star th-day-head-star" title="${escapeHtmlAttr(holiday.name)}"></i>` : '';
            const clickAction = isHistory ? `onclick="openHolidayDayModal('${d}', ${historyIndex})" style="cursor:pointer;"` : '';
            return `<th class="th-day-col${isClosed ? ' th-closed' : ''}${holiday ? ' th-holiday' : ''}" ${clickAction}><div class="th-day-col-inner"><span class="th-day-name">${d}</span>${closedBadge}${holidayIcon}</div></th>`;
        }).join('')}<th class="col-hours">Horas</th>`;
        const thCollab = thead.querySelector(`#${isHistory ? `th-collaborator-hist-${historyIndex}` : 'th-collaborator'}`);
        if (thCollab) {
            thCollab.addEventListener('click', () => {
                if (isHistory) { const prev = historySortModes.get(historyIndex) || 'time'; historySortModes.set(historyIndex, prev === 'time' ? 'alpha' : 'time'); renderHistoryEntryTable(historyIndex); }
                else { currentSortMode = currentSortMode === 'time' ? 'alpha' : 'time'; if (currentGeneratedSchedule) renderSchedule(currentGeneratedSchedule, '#scheduleTable', currentDailyTasks); }
            });
        }
        const historyAliases = isHistory ? (historyEntriesCache[historyIndex]?.metadata?.display_aliases || {}) : {};
        keys.forEach(name => {
            const row = document.createElement("tr");
            const displayName = isHistory && historyAliases[name] ? historyAliases[name] : name;
            const aliasIndicator = isHistory && historyAliases[name] && historyAliases[name] !== name ? `<i class="fa-solid fa-link" style="font-size:0.65em; margin-left:4px; color:var(--text-muted);" title="Vinculado a ${escapeHtmlAttr(name)}"></i>` : '';
            const initials = name === "Refuerzo" ? "RF" : (displayName || name).substring(0, 2).toUpperCase();
            const emp = employees.find(e => e.name === name);
            const nightBadge = emp && emp.can_do_night ? '<i class="fa-solid fa-moon" style="font-size:0.7em; margin-left:4px; color:#6366f1;" title="Turno Noche"></i>' : '';
            const noRestBadge = emp && emp.allow_no_rest ? '<i class="fa-solid fa-battery-empty" style="font-size:0.7em; margin-left:4px; color:#ef4444;" title="Sin Descanso"></i>' : '';
            const forcedLibresBadge = emp && emp.forced_libres ? '<i class="fa-solid fa-thumbtack forced-libres-icon" title="Rol Libres Forzado"></i>' : '';
            const forcedQuebradoBadge = emp && emp.forced_quebrado ? '<i class="fa-solid fa-bolt" style="font-size:0.7em; margin-left:4px; color:#7c3aed;" title="Forzar Quebrado"></i>' : '';
            const refBadge = name === "Refuerzo" ? '<span class="tag night" style="font-size:0.6em; margin-left:4px;">REF</span>' : '';
            const libresPerson = currentMetadata?.libres_person || "";
            const libresWeekBadge = name === libresPerson ? '<span class="libres-week-badge" title="Persona de Libres esta semana">★ LIBRES</span>' : '';
            const nameJsLiteral = JSON.stringify(name).replace(/"/g, "&quot;");
            const nameClickAttrs = isHistory ? `class="emp-name hist-name-edit" onclick="openHistoryNameModal(${historyIndex}, ${nameJsLiteral})" title="Click para renombrar o vincular" style="cursor:pointer; text-decoration: underline dotted; text-underline-offset: 2px;"` : `class="emp-name"`;
            row.innerHTML = `<td><div class="emp-cell-content"><div class="emp-avatar" style="${name === "Refuerzo" ? 'background: var(--accent-color);' : ''}">${initials}</div><div class="emp-details"><span ${nameClickAttrs}>${displayName}${aliasIndicator} ${nightBadge} ${noRestBadge} ${forcedLibresBadge} ${forcedQuebradoBadge} ${libresWeekBadge} ${refBadge}</span><span class="emp-role">${name === "Refuerzo" ? 'Apoyo Extra' : (emp && sqlIntFlagOn(emp.is_jefe_pista) ? 'Jefe de Pista' : (emp && emp.is_practicante ? 'Practicante' : 'Colaborador'))}</span></div></div></td>`;
            let totalHours = 0;
            DAYS.forEach(d => {
                const s = schedule[name][d] || "OFF"; const info = getShiftInfo(s);
                totalHours += getShiftHoursCount(s);
                let fixedClass = ""; if (emp && emp.fixed_shifts && emp.fixed_shifts[d]) fixedClass = "pill-fixed";
                const holiday = getHolidayForDay(d, weekDatesMap, metadataHolidayDays);
                const isClosedDay = specialDays[d] === 'closed';
                const cellClass = (isClosedDay ? 'closed-col' : '') + (holiday ? ' holiday-col' : '');
                let historyAttrs = "", cursorStyle = "";
                if (isHistory) {
                    historyAttrs = `data-history-index="${historyIndex}" data-employee-name="${escapeHtmlAttr(name)}" data-day="${escapeHtmlAttr(d)}" onmousedown="beginHistorySelection(event, this)" onmouseenter="extendHistorySelection(event, this)" onclick="handleHistoryCellClick(event, this)"`;
                    cursorStyle = "cursor:pointer; user-select:none;";
                }
                const showClosedEstablishmentPill = isClosedDay && s === "OFF";
                if (isClosedDay && !isHistory) { row.innerHTML += `<td class="${cellClass}"><div class="shift-pill pill-closed-establishment" style="cursor:default;"><i class="fa-solid fa-store-slash pill-icon"></i><span class="pill-time">Cerrado</span><span class="pill-closed-hint">Sin servicio</span></div></td>`; }
                else if (showClosedEstablishmentPill && isHistory) { row.innerHTML += `<td class="${cellClass}"><div class="shift-pill pill-closed-establishment ${fixedClass} history-shift-pill" ${historyAttrs} style="${cursorStyle}"><i class="fa-solid fa-store-slash pill-icon"></i><span class="pill-time">Cerrado</span><span class="pill-closed-hint">Sin servicio</span>${getTaskLabelHTML(tasks, name, d)}</div></td>`; }
                else { row.innerHTML += `<td class="${cellClass}"><div class="shift-pill ${info.class} ${fixedClass}${isHistory ? " history-shift-pill" : ""}" ${historyAttrs} style="${cursorStyle}"><i class="fa-solid ${info.icon} pill-icon"></i><span class="pill-time">${info.text}</span>${getTaskLabelHTML(tasks, name, d)}</div></td>`; }
            });
            row.innerHTML += `<td class="col-hours"><div class="hours-cell"><strong>${totalHours}</strong> hrs</div></td>`;
            tbody.appendChild(row);
        });
    }
}
window.renderSchedule = renderSchedule;

/* ── Export ── */
async function renderScheduleCaptureCanvas(captureElement) {
    if (!captureElement) throw new Error("No se encontro el contenedor para exportar.");
    const rect = captureElement.getBoundingClientRect();
    const captureWidth = Math.ceil(Math.max(captureElement.scrollWidth || 0, rect.width || 0));
    const captureHeight = Math.ceil(Math.max(captureElement.scrollHeight || 0, rect.height || 0));
    const exportToken = `export-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const bodyBg = getComputedStyle(document.body).backgroundColor || (document.body.classList.contains("dark-mode") ? "#0f172a" : "#ffffff");
    captureElement.dataset.exportCaptureId = exportToken;
    try {
        return await html2canvas(captureElement, {
            scale: 2, useCORS: true, backgroundColor: bodyBg, width: captureWidth, height: captureHeight,
            windowWidth: Math.max(window.innerWidth, captureWidth), windowHeight: Math.max(window.innerHeight, captureHeight),
            onclone: (clonedDocument) => {
                const clone = clonedDocument.querySelector(`[data-export-capture-id="${exportToken}"]`);
                if (!clone) return;
                clone.style.overflow = "visible"; clone.style.width = `${captureWidth}px`; clone.style.minWidth = `${captureWidth}px`;
                clone.style.maxWidth = "none"; clone.style.height = "auto"; clone.style.maxHeight = "none";
                clone.style.margin = "0"; clone.style.transform = "none"; clone.style.contain = "none";
                clone.querySelectorAll(".shift-pill").forEach((el) => { el.style.boxShadow = "none"; el.style.filter = "none"; el.style.transform = "none"; el.style.transition = "none"; el.style.outline = "none"; el.style.willChange = "auto"; el.style.boxSizing = "border-box"; });
                clone.querySelectorAll(".history-shift-pill.history-pill-selected").forEach((el) => { el.style.outline = "none"; el.style.boxShadow = "none"; el.style.transform = "none"; });
                clone.querySelectorAll("*").forEach((el) => { const computed = clonedDocument.defaultView.getComputedStyle(el); if (computed.position === "sticky") { el.style.position = "static"; el.style.top = "auto"; el.style.left = "auto"; el.style.zIndex = "auto"; } });
            },
        });
    } finally { delete captureElement.dataset.exportCaptureId; }
}

async function exportToImage() {
    const captureElement = document.getElementById("scheduleCapture");
    if (!captureElement) return;
    try {
        const canvas = await renderScheduleCaptureCanvas(captureElement);
        const filename = 'horario_completo.png';
        const imgData = canvas.toDataURL("image/png");
        const link = document.createElement('a'); link.download = filename; link.href = imgData; link.click();
        const saveRes = await fetch(`${API_URL}/export_image`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ image_data: imgData, filename }) });
        if (!saveRes.ok) { let detail = "No se pudo guardar la imagen en export_horarios."; try { const err = await saveRes.json(); detail = err.detail || detail; } catch (_) {} throw new Error(detail); }
        showExportConfirmationModal(filename, 'image');
    } catch (err) { console.error("Capture failed:", err); alert(err.message || "Error al exportar imagen"); }
}
window.exportToImage = exportToImage;

function exportToExcel() { downloadExcel("/api/export_excel"); }
window.exportToExcel = exportToExcel;

/* ── Validation UI ── */
async function toggleValidation() {
    isValidationOn = !isValidationOn;
    const btn = document.getElementById("btnToggleValidation");
    if (isValidationOn) {
        btn.classList.add("primary"); btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Cargando...`;
        try { await refreshScheduleValidationRules(currentMetadata?.special_days || getSpecialDaysPayload()); btn.innerHTML = `<i class="fa-solid fa-check"></i> Validación activa`; }
        catch (err) { console.error("Error fetching validation rules:", err); alert("Error al obtener reglas de validación del servidor."); btn.innerHTML = `<i class="fa-solid fa-check-double"></i> Validación`; btn.classList.remove("primary"); isValidationOn = false; return; }
        try { if (typeof applyValidationUI === "function") applyValidationUI(); } catch (uiErr) { console.error("Error en applyValidationUI:", uiErr); }
    } else {
        btn.classList.remove("primary"); btn.innerHTML = `<i class="fa-solid fa-check-double"></i> Validación`;
        document.querySelectorAll(".col-valid, .col-invalid, .th-invalid, .td-invalid").forEach(el => { el.classList.remove("col-valid", "col-invalid", "th-invalid", "td-invalid"); });
        const summaryPanel = document.getElementById("validationSummaryPanel"); if (summaryPanel) summaryPanel.style.display = "none";
        const coveragePanel = document.getElementById("coverageInfoPanel"); if (coveragePanel) coveragePanel.style.display = "none";
        const restPanel = document.getElementById("restBetweenShiftsPanel"); if (restPanel) restPanel.style.display = "none";
        const validatorOverlay = document.getElementById("validatorOverlay");
        if (validatorOverlay && !validatorOverlay.classList.contains("val-overlay-hidden")) {
            try { if (typeof closeValidatorOverlay === "function") closeValidatorOverlay(); } catch (err) { console.error("Error al apagar validación desde el overlay:", err); }
        }
        const stale = document.getElementById("validatorReopenBtn"); if (stale) stale.remove();
    }
}
window.toggleValidation = toggleValidation;

function applyValidationUI() {
    if (!validationRules || !currentGeneratedSchedule) return;
    document.querySelectorAll(".col-valid, .col-invalid, .th-invalid, .td-invalid").forEach(el => { el.classList.remove("col-valid", "col-invalid", "th-invalid", "td-invalid"); });
    const schedule = currentGeneratedSchedule;
    const days = ["Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue"];
    const coverage = validationRules.coverage || {};
    const coverageTable = document.getElementById("coverageInfoPanel");
    if (coverageTable) {
        let html = '<table class="coverage-table"><thead><tr><th>Hora</th>';
        days.forEach(d => { html += `<th>${d}</th>`; });
        html += '</tr></thead><tbody>';
        for (let h = 5; h <= 22; h++) {
            html += `<tr><td class="coverage-hour">${h}:00</td>`;
            days.forEach(d => {
                const req = coverage[d]?.[h] || 0;
                let count = 0;
                Object.values(schedule).forEach(emp => { const s = emp[d]; const hours = getShiftHoursList(s); if (hours.includes(h)) count++; });
                const ok = count >= req;
                html += `<td class="${ok ? 'cov-ok' : 'cov-deficit'}">${count}/${req}</td>`;
            });
            html += '</tr>';
        }
        html += '</tbody></table>';
        coverageTable.innerHTML = html; coverageTable.style.display = "block";
    }
    const restReport = currentMetadata?.rest_between_shifts || buildRestReportClient(schedule);
    const restPanel = document.getElementById("restBetweenShiftsPanel");
    if (restPanel && restReport && restReport.per_employee) {
        let html = '<table class="coverage-table"><thead><tr><th>Empleado</th>';
        for (let i = 0; i < days.length - 1; i++) { html += `<th>${days[i]} → ${days[i + 1]}</th>`; }
        html += '</tr></thead><tbody>';
        Object.entries(restReport.per_employee).forEach(([name, data]) => {
            html += `<tr><td class="coverage-hour">${name}</td>`;
            const applied = restReport.applied_hours || restReport.target_hours || 12;
            (data.gaps || []).forEach(g => { html += `<td class="${g.meets_applied ? 'cov-ok' : 'cov-deficit'}">${g.hours}h</td>`; });
            html += '</tr>';
        });
        html += '</tbody></table>';
        restPanel.innerHTML = html; restPanel.style.display = "block";
    }
    const summaryPanel = document.getElementById("validationSummaryPanel");
    if (summaryPanel) {
        let issues = [];
        Object.entries(coverage).forEach(([day, hours]) => {
            Object.entries(hours).forEach(([h, req]) => {
                let count = 0;
                Object.values(schedule).forEach(emp => { const s = emp[day]; const hrs = getShiftHoursList(s); if (hrs.includes(parseInt(h))) count++; });
                if (count < req) issues.push(`${day} ${h}:00 — ${count}/${req}`);
            });
        });
        if (issues.length) { summaryPanel.innerHTML = `<div class="coverage-badge coverage-badge-error">${issues.length} déficit(s) de cobertura</div><ul style="margin:8px 0 0;padding-left:1.2rem;font-size:0.8rem;">${issues.map(i => `<li>${i}</li>`).join('')}</ul>`; summaryPanel.style.display = "block"; }
        else { summaryPanel.innerHTML = '<div class="coverage-badge coverage-badge-ok">Cobertura OK</div>'; summaryPanel.style.display = "block"; }
    }
}
window.applyValidationUI = applyValidationUI;

function closeValidatorOverlay() {
    const overlay = document.getElementById("validatorOverlay");
    if (overlay) { overlay.classList.add("val-overlay-hidden"); overlay.classList.remove("val-overlay-visible"); }
    isValidationOn = false;
    const btn = document.getElementById("btnToggleValidation");
    if (btn) { btn.classList.remove("primary"); btn.innerHTML = `<i class="fa-solid fa-check-double"></i> Validación`; }
    document.querySelectorAll(".col-valid, .col-invalid, .th-invalid, .td-invalid").forEach(el => { el.classList.remove("col-valid", "col-invalid", "th-invalid", "td-invalid"); });
    const summaryPanel = document.getElementById("validationSummaryPanel"); if (summaryPanel) summaryPanel.style.display = "none";
    const coveragePanel = document.getElementById("coverageInfoPanel"); if (coveragePanel) coveragePanel.style.display = "none";
    const restPanel = document.getElementById("restBetweenShiftsPanel"); if (restPanel) restPanel.style.display = "none";
    const stale = document.getElementById("validatorReopenBtn"); if (stale) stale.remove();
}
window.closeValidatorOverlay = closeValidatorOverlay;

function reopenValidatorOverlay() {
    const overlay = document.getElementById("validatorOverlay");
    if (overlay) { overlay.classList.remove("val-overlay-hidden"); overlay.classList.add("val-overlay-visible"); }
}
window.reopenValidatorOverlay = reopenValidatorOverlay;

/* ── Export helpers ── */
function _escapeHtml(text) {
    const div = document.createElement("div"); div.textContent = text; return div.innerHTML;
}
window._escapeHtml = _escapeHtml;

function escapeHtml(text) { return _escapeHtml(text); }
window.escapeHtml = escapeHtml;

async function downloadExcel(url) {
    const status = document.getElementById("statusMessage");
    const previousStatus = status ? status.innerHTML : "";
    if (status) status.innerHTML = '<i class="fa-solid fa-file-excel"></i> Exportando Excel...';
    try {
        const res = await fetch(url);
        if (!res.ok) { let detail = "No se pudo exportar el horario."; try { const err = await res.json(); detail = err.detail || detail; } catch (_) { } throw new Error(detail); }
        const blob = await res.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        const contentDisposition = res.headers.get("content-disposition") || "";
        const match = contentDisposition.match(/filename="?([^";]+)"?/i);
        const exportedFilename = match ? match[1] : "horario.xlsx";
        link.href = downloadUrl; link.download = exportedFilename; document.body.appendChild(link); link.click(); link.remove();
        window.URL.revokeObjectURL(downloadUrl);
        showExportConfirmationModal(exportedFilename);
        if (status) status.innerHTML = '<i class="fa-solid fa-check"></i> Exportación completada';
    } catch (e) {
        if (status) status.innerHTML = `<span class="error"><i class="fa-solid fa-circle-xmark"></i> ${e.message}</span>`;
        else alert(e.message);
    } finally {
        if (status) setTimeout(() => { status.innerHTML = previousStatus; }, 4000);
    }
}
window.downloadExcel = downloadExcel;

function showExportConfirmationModal(filename, type = 'excel') {
    let existing = document.getElementById("exportConfirmModal"); if (existing) existing.remove();
    const titles = { excel: { icon: 'fa-file-excel', color: '#10b981', msg: 'Excel exportado exitosamente' }, image: { icon: 'fa-image', color: '#3b82f6', msg: 'Imagen exportada exitosamente' } };
    const cfg = titles[type] || titles.excel;
    const modal = document.createElement("div");
    modal.id = "exportConfirmModal"; modal.className = "modal-backdrop";
    modal.innerHTML = `<div class="modal-dialog" style="max-width: 440px; animation: modalSpringUp 0.35s cubic-bezier(0.175, 0.885, 0.32, 1.2) both;"><div class="modal-content" style="text-align: center; padding: 2rem;"><div style="margin-bottom: 1.25rem;"><div style="width: 64px; height: 64px; border-radius: 50%; background: linear-gradient(135deg, ${cfg.color}, ${cfg.color}dd); display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem;"><i class="fa-solid fa-check" style="font-size: 1.75rem; color: white;"></i></div><h3 style="margin: 0 0 0.5rem; font-size: 1.2rem; color: var(--text-main);">${cfg.msg}</h3><p style="margin: 0; color: var(--text-muted); font-size: 0.9rem;"><i class="fa-solid ${cfg.icon}" style="color: ${cfg.color}; margin-right: 4px;"></i>${_escapeHtml(filename)}</p></div><div style="display: flex; gap: 0.75rem; justify-content: center; flex-wrap: wrap;"><button type="button" onclick="openExportFolder(); closeExportConfirmModal();" class="action-btn" style="background: linear-gradient(135deg, #3b82f6, #2563eb); color: white; border: none; padding: 0.6rem 1.25rem; border-radius: 8px; cursor: pointer; font-size: 0.9rem; display: inline-flex; align-items: center; gap: 6px;"><i class="fa-solid fa-folder-open"></i> Abrir carpeta</button><button type="button" onclick="closeExportConfirmModal();" class="action-btn" style="background: var(--bg-card); color: var(--text-main); border: 1px solid var(--border-color); padding: 0.6rem 1.25rem; border-radius: 8px; cursor: pointer; font-size: 0.9rem;">Cerrar</button></div></div></div>`;
    document.body.appendChild(modal);
    modal.addEventListener("click", (e) => { if (e.target === modal) closeExportConfirmModal(); });
}
window.showExportConfirmationModal = showExportConfirmationModal;

function closeExportConfirmModal() { const modal = document.getElementById("exportConfirmModal"); if (modal) modal.remove(); }
window.closeExportConfirmModal = closeExportConfirmModal;

async function openExportFolder() { try { await fetch("/api/open_export_folder", { method: "POST" }); } catch (e) { console.error("Error opening export folder:", e); } }
window.openExportFolder = openExportFolder;

function exportHistoryExcel(index, event) {
    if (event) { event.preventDefault(); event.stopPropagation(); }
    const entry = historyEntriesCache[index];
    const param = (entry && entry.db_id != null) ? `history_db_id=${entry.db_id}` : `history_index=${index}`;
    downloadExcel(`/api/export_excel?${param}`);
}
window.exportHistoryExcel = exportHistoryExcel;
