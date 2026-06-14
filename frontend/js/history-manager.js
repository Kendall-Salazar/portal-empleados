// ========================================================================
// Chronos — History Manager
// Historial, papelera, carpetas, selección, export, modales
// ========================================================================

/* ── History List & Table ── */
function renderHistoryEntryTable(index) {
    const entry = historyEntriesCache[index];
    if (!entry) return;
    const metadataHolidayDays = entry.metadata?.holiday_days || null;
    renderSchedule(entry.schedule, `#hist-table-${index}`, entry.daily_tasks || {}, entry.special_days || {}, metadataHolidayDays, entry.week_dates || null);
    applyHistoryHoursVisibility(index);
}
window.renderHistoryEntryTable = renderHistoryEntryTable;

function applyHistoryHoursVisibility(index) {
    const table = document.getElementById(`hist-table-${index}`);
    if (!table) return;
    table.querySelectorAll(".col-hours").forEach(el => { el.classList.toggle("hidden-col", hiddenHistoryHours.has(index)); });
}

function renderHistoryList() {
    const listContainer = document.getElementById('historyList');
    if (!listContainer) return;
    listContainer.innerHTML = "";
    if (!historyEntriesCache.length) { listContainer.innerHTML = '<div class="empty-msg">No hay historiales guardados</div>'; return; }
    historyEntriesCache.forEach((h, i) => {
        const item = document.createElement("div");
        item.className = "history-item";
        item.dataset.historyIndex = String(i);
        if (expandedHistoryItems.has(i)) item.classList.add("expanded");
        const dateValue = h.timestamp ? new Date(h.timestamp) : new Date();
        const dateStr = dateValue.toLocaleDateString() + ' ' + dateValue.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        item.innerHTML = `<div class="history-header" onclick="toggleHistory(this)"><div class="h-info"><i class="fa-solid fa-calendar-week"></i><span class="h-name">${h.name}</span><button type="button" class="btn-icon" onclick="renameHistory(${i}, event)" title="Renombrar" style="padding: 2px 6px;"><i class="fa-solid fa-pen" style="font-size: 0.75rem;"></i></button><span class="h-date">${dateStr}</span></div><div class="h-actions"><i class="fa-solid fa-chevron-down arrow"></i><button type="button" class="btn-icon delete" onclick="deleteHistory(${i}, event)"><i class="fa-solid fa-trash"></i></button></div></div><div class="history-body"><div class="history-body-toolbar"><button type="button" class="btn-icon history-action-button" onclick="validateHistory(${i}, event)" title="Validar Historial"><i class="fa-solid fa-shield-check"></i><span>Validar</span></button><button type="button" class="btn-icon history-action-button" onclick="reassignHistoryTasks(${i}, event)" title="Recalcular Limpieza"><i class="fa-solid fa-broom"></i><span>Limpieza</span></button><button type="button" class="btn-icon history-action-button${hiddenHistoryHours.has(i) ? "" : " is-active"}" data-history-hours-button="${i}" onclick="toggleHistoryHours(${i}, event)" title="Mostrar u ocultar horas" aria-pressed="${hiddenHistoryHours.has(i) ? "false" : "true"}"><i class="fa-solid fa-clock"></i><span>Horas</span></button><button type="button" class="btn-icon" onclick="exportHistoryImage(${i}, event)" title="Exportar Foto"><i class="fa-solid fa-camera"></i></button><button type="button" class="btn-icon" onclick="exportHistoryExcel(${i}, event)" title="Exportar Excel"><i class="fa-solid fa-file-excel"></i></button><button type="button" class="btn-icon history-action-button" onclick="swapHistoryEmployees(${i}, event)" title="Intercambiar horarios de dos empleados"><i class="fa-solid fa-right-left"></i><span>Intercambiar</span></button><button type="button" class="btn-icon history-action-button" onclick="addHistoryToFolder(${i}, event)" title="Agregar a carpeta"><i class="fa-solid fa-folder-plus"></i><span>Carpeta</span></button></div><div class="history-table-wrapper"><table class="clean-table" id="hist-table-${i}"><thead><tr><th>Empleado</th><th>Vie</th><th>Sáb</th><th>Dom</th><th>Lun</th><th>Mar</th><th>Mié</th><th>Jue</th><th class="col-hours">Horas</th></tr></thead><tbody></tbody></table></div></div>`;
        listContainer.appendChild(item);
        renderHistoryEntryTable(i);
    });
}
window.renderHistoryList = renderHistoryList;

function toggleHistory(header) {
    const item = header.closest('.history-item');
    if (!item) return;
    const index = Number(item.dataset.historyIndex);
    const isExpanding = !item.classList.contains('expanded');
    const allItems = document.querySelectorAll('.history-item');
    if (isExpanding) {
        allItems.forEach(i => { if (i !== item && i.classList.contains('expanded')) { i.classList.remove('expanded'); i.classList.add('hidden-by-expand'); } });
        setTimeout(() => {
            allItems.forEach(i => { if (i !== item) { i.style.display = 'none'; i.classList.remove('hidden-by-expand'); } });
            item.classList.add('expanded'); expandedHistoryItems.add(index);
        }, 50);
    } else {
        item.classList.remove('expanded'); expandedHistoryItems.delete(index);
        setTimeout(() => { allItems.forEach(i => { i.style.display = ''; }); }, 100);
    }
}
window.toggleHistory = toggleHistory;

window.toggleHistoryHours = function (index, event) {
    if (event) { event.preventDefault(); event.stopPropagation(); }
    if (hiddenHistoryHours.has(index)) hiddenHistoryHours.delete(index); else hiddenHistoryHours.add(index);
    applyHistoryHoursVisibility(index);
    const button = document.querySelector(`[data-history-hours-button="${index}"]`);
    if (button) { const isVisible = !hiddenHistoryHours.has(index); button.classList.toggle("is-active", isVisible); button.setAttribute("aria-pressed", isVisible ? "true" : "false"); }
};

/* ── History CRUD ── */
async function deleteHistory(i, event) {
    if (event) { event.preventDefault(); event.stopPropagation(); }
    const entry = historyEntriesCache[i]; if (!entry) return;
    if (!confirm(`¿Mover "${entry.name}" a la papelera?\nPodrás restaurarla dentro de 7 días.`)) return;
    const delUrl = entry.db_id != null ? `/api/history/entry/${entry.db_id}` : `/api/history/${i}`;
    const res = await fetch(delUrl, { method: 'DELETE' });
    if (!res.ok) { alert("No se pudo mover a la papelera."); return; }
    historyEntriesCache.splice(i, 1);
    expandedHistoryItems = new Set([...expandedHistoryItems].filter(index => index !== i).map(index => (index > i ? index - 1 : index)));
    hiddenHistoryHours = new Set([...hiddenHistoryHours].filter(index => index !== i).map(index => (index > i ? index - 1 : index)));
    await loadTrash(); renderHistoryList();
    setStatusMessage(`"${entry.name}" movido a la papelera.`, "success");
}
window.deleteHistory = deleteHistory;

async function renameHistory(i, event) {
    if (event) { event.preventDefault(); event.stopPropagation(); }
    const entry = historyEntriesCache[i]; if (!entry) return;
    const newName = prompt("Nuevo nombre:", entry.name);
    if (!newName || newName.trim() === "") return;
    const nextEntry = cloneHistoryEntry(entry); nextEntry.name = newName.trim();
    try {
        await persistHistoryEntry(i, nextEntry);
        setStatusMessage(`Renombrado a "${nextEntry.name}".`, "success");
        renderHistoryList();
    } catch (err) { console.error(err); setStatusMessage("Error al renombrar: " + err.message, "error"); }
}
window.renameHistory = renameHistory;

async function persistHistoryEntry(index, nextEntry) {
    const payload = { name: nextEntry.name, schedule: nextEntry.schedule || {}, daily_tasks: nextEntry.daily_tasks || {}, next_sunday_cycle_index: nextEntry.next_sunday_cycle_index ?? null, next_sunday_rotation_queue: nextEntry.next_sunday_rotation_queue ?? null, week_dates: nextEntry.week_dates ?? null, special_days: nextEntry.special_days || {}, timestamp: nextEntry.timestamp || "", metadata: nextEntry.metadata || {} };
    const entry = historyEntriesCache[index];
    const patchUrl = entry && entry.db_id != null ? `/api/history/entry/${entry.db_id}` : `/api/history/${index}`;
    const res = await fetch(patchUrl, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    if (!res.ok) { let detail = "No se pudo guardar el historial."; try { const err = await res.json(); detail = err.detail || detail; } catch (_) { } throw new Error(detail); }
    historyEntriesCache[index] = nextEntry;
}
window.persistHistoryEntry = persistHistoryEntry;

/* ── Save Modal ── */
function openSaveModal() { document.getElementById("saveModal").classList.remove("hidden"); }
window.openSaveModal = openSaveModal;

function closeSaveModal() { document.getElementById("saveModal").classList.add("hidden"); }
window.closeSaveModal = closeSaveModal;

async function confirmSaveSchedule(event) {
    if (event) event.preventDefault();
    const name = document.getElementById("scheduleNameInput")?.value?.trim();
    if (!name) { setStatusMessage("Ingresá un nombre para el horario.", "error"); return; }
    if (!currentGeneratedSchedule) { setStatusMessage("No hay horario generado para guardar.", "error"); return; }
    setStatusMessage("Guardando...", "info", 0);
    try {
        const entry = { name, schedule: currentGeneratedSchedule, daily_tasks: currentDailyTasks || {}, week_dates: getWeekDatesMap(), special_days: getSpecialDaysPayload(), metadata: currentMetadata || {}, timestamp: new Date().toISOString() };
        const res = await fetch('/api/history', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(entry) });
        if (!res.ok) throw new Error("Error al guardar");
        closeSaveModal();
        setStatusMessage(`"${name}" guardado en el historial.`, "success");
        await fetchHistoryEntries(true);
    } catch (e) { console.error(e); setStatusMessage("Error: " + e.message, "error"); }
}
window.confirmSaveSchedule = confirmSaveSchedule;

/* ── Sunday Rotation ── */
function openSundayRotationModal() { const modal = document.getElementById('sundayRotationModal'); if (modal) modal.classList.remove('hidden'); loadSundayRotation(); }
window.openSundayRotationModal = openSundayRotationModal;

function closeSundayRotationModal() { const modal = document.getElementById('sundayRotationModal'); if (modal) modal.classList.add('hidden'); }
window.closeSundayRotationModal = closeSundayRotationModal;

async function loadSundayRotation() {
    const container = document.getElementById('sundayRotationContent');
    if (!container) return;
    container.innerHTML = '<div style="text-align: center; padding: 2rem; color: var(--text-muted);"><i class="fa-solid fa-circle-notch fa-spin"></i> Cargando...</div>';
    try {
        const res = await fetch(`${API_URL}/rotacion-domingos`);
        const data = await res.json();
        if (!data || data.length === 0) { container.innerHTML = '<div style="padding: 1rem; text-align: center; color: var(--text-muted);">No hay historial o empleados elegibles.</div>'; return; }
        container.innerHTML = '';
        data.forEach((emp, index) => {
            let colorCls = "var(--text-main)", bgCls = "var(--bg-panel)", icon = "fa-user";
            if (index === 0) { colorCls = "#10b981"; bgCls = "rgba(16, 185, 129, 0.1)"; icon = "fa-star"; }
            else if (index < 3) { colorCls = "#3b82f6"; bgCls = "rgba(59, 130, 246, 0.1)"; icon = "fa-arrow-up"; }
            else { colorCls = "#ef4444"; bgCls = "rgba(239, 68, 68, 0.05)"; icon = "fa-briefcase"; }
            const row = document.createElement('div');
            row.style.cssText = `display: flex; justify-content: space-between; align-items: center; padding: 0.75rem; background: ${bgCls}; border-radius: 6px; border: 1px solid rgba(255,255,255,0.05);`;
            row.className = "hover-glow";
            const names = emp.name.split(' ');
            const initials = names.length > 1 ? names[0][0] + names[names.length - 1][0] : names[0].substring(0, 2);
            row.innerHTML = `<div style="display: flex; align-items: center; gap: 12px;"><div style="width: 28px; height: 28px; border-radius: 50%; background: ${colorCls}; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 0.75rem; font-weight: bold;">${index + 1}</div><div><div style="font-weight: 600; font-size: 0.95rem; color: var(--text-main); margin-bottom: 2px;">${emp.name}</div><div style="font-size: 0.7rem; color: var(--text-muted);"><i class="fa-solid ${icon}" style="color:${colorCls};"></i> ${emp.priority}</div></div></div><div style="text-align: right;"><span style="font-size: 0.75rem; font-weight: 600; color: ${colorCls}; background: var(--bg-app); padding: 4px 8px; border-radius: 12px; border: 1px solid var(--border);"><i class="fa-solid fa-clock-rotate-left"></i> ${emp.last_off}</span></div>`;
            container.appendChild(row);
        });
    } catch (e) { console.error(e); container.innerHTML = '<div style="padding: 1rem; text-align: center; color: #ef4444;"><i class="fa-solid fa-triangle-exclamation"></i> Error cargando rotación.</div>'; }
}
window.loadSundayRotation = loadSundayRotation;

/* ── History Selection ── */
function clearHistorySelectionStyles() { document.querySelectorAll('.history-shift-pill.history-pill-selected').forEach(el => { el.classList.remove('history-pill-selected'); }); }

function getHistorySelectionRange(startDay, endDay) {
    const startIndex = DAY_INDEX[startDay]; const endIndex = DAY_INDEX[endDay];
    if (startIndex === undefined || endIndex === undefined) return startDay ? [startDay] : [];
    const from = Math.min(startIndex, endIndex); const to = Math.max(startIndex, endIndex);
    return DAYS.slice(from, to + 1);
}

function applyHistorySelectionStyles() {
    clearHistorySelectionStyles();
    if (historySelectionState.histIndex === null || !historySelectionState.empName || !historySelectionState.days.length) return;
    document.querySelectorAll('.history-shift-pill').forEach(el => {
        if (Number(el.dataset.historyIndex) === historySelectionState.histIndex && el.dataset.employeeName === historySelectionState.empName && historySelectionState.days.includes(el.dataset.day)) { el.classList.add('history-pill-selected'); }
    });
}

function beginHistorySelection(event, element) {
    if (event.button !== 0) return; event.preventDefault(); event.stopPropagation();
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
window.beginHistorySelection = beginHistorySelection;

function extendHistorySelection(event, element) {
    if (!historySelectionState.active) return;
    if ((event.buttons & 1) !== 1) return;
    const histIndex = Number(element.dataset.historyIndex);
    const empName = element.dataset.employeeName || "";
    const day = element.dataset.day || null;
    if (histIndex !== historySelectionState.histIndex || empName !== historySelectionState.empName || !day) return;
    if (day !== historySelectionState.currentDay) {
        historySelectionState.dragged = true;
        historySelectionState.currentDay = day;
        historySelectionState.days = getHistorySelectionRange(historySelectionState.anchorDay, day);
        applyHistorySelectionStyles();
    }
}
window.extendHistorySelection = extendHistorySelection;

function finishHistorySelection() {
    if (!historySelectionState.active) return;
    const selection = { histIndex: historySelectionState.histIndex, empName: historySelectionState.empName, days: [...historySelectionState.days], dragged: historySelectionState.dragged };
    historySelectionState.active = false;
    if (selection.dragged && selection.days.length > 1) {
        historySelectionState.suppressClick = true;
        window.setTimeout(() => { editHistoryShiftBatch(selection.empName, selection.days, selection.histIndex); }, 0);
        return;
    }
    clearHistorySelectionStyles();
    historySelectionState.anchorDay = null; historySelectionState.currentDay = null; historySelectionState.days = [];
}

function handleHistoryCellClick(event, element) {
    event.preventDefault(); event.stopPropagation();
    if (historySelectionState.suppressClick) { historySelectionState.suppressClick = false; clearHistorySelectionStyles(); return; }
    openShiftTaskModal(element.dataset.employeeName, element.dataset.day, Number(element.dataset.historyIndex));
}
window.handleHistoryCellClick = handleHistoryCellClick;

/* ── Shift Task Modal ── */
let shiftTaskModalData = { empName: null, day: null, histIndex: null, currentShift: null, currentTask: null };

function _populateShiftTaskLegend() {
    const el = document.getElementById('shiftTaskLegend'); if (!el) return;
    const rows = [];
    const codes = Object.keys(SHIFT_HOURS || {}).filter(c => c && !["OFF", "VAC", "PERM"].includes(c)).sort((a, b) => ((SHIFT_HOURS[a] && SHIFT_HOURS[a].start) || 0) - ((SHIFT_HOURS[b] && SHIFT_HOURS[b].start) || 0));
    const friendly = (code) => { const info = (typeof getShiftInfo === "function") ? getShiftInfo(code) : null; return info && info.text ? info.text : code; };
    rows.push(`<div style="margin-bottom:0.4rem;"><b>Códigos rápidos</b></div>`);
    if (codes.length) { const items = codes.map(c => `<code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">${escapeHtmlAttr(c)}</code> = <span style="color:var(--text-muted);">${escapeHtmlAttr(friendly(c))}</span>`).join('<br/>'); rows.push(`<div style="margin-bottom:0.6rem;">${items}</div>`); }
    rows.push(`<div style="margin-bottom:0.4rem;"><b>Horarios manuales</b></div>`);
    rows.push(`<div style="margin-bottom:0.6rem; color:var(--text-muted);">Escribí el rango directamente, ejemplos:<br/><code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">13-22</code> · <code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">1pm-10pm</code> · <code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">5am-11am + 5pm-8pm</code></div>`);
    rows.push(`<div style="margin-bottom:0.4rem;"><b>Códigos especiales</b></div>`);
    rows.push(`<div style="color:var(--text-muted);"><code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">OFF</code> = Libre &nbsp;·&nbsp;<code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">VAC</code> = Vacaciones &nbsp;·&nbsp;<code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">PERM</code> = Permiso</div>`);
    el.innerHTML = rows.join("");
}

window.openShiftTaskModal = function(empName, day, histIndex) {
    const entry = historyEntriesCache[histIndex]; if (!entry) return;
    const currentShift = entry.schedule?.[empName]?.[day] || "OFF";
    const currentTasks = entry.daily_tasks || {};
    const currentTask = (currentTasks[empName] || {})[day] || "";
    _populateShiftTaskLegend();
    shiftTaskModalData = { empName, day, histIndex, currentShift, currentTask };
    document.getElementById('shiftTaskTitle').textContent = `Editar: ${empName} (${day})`;
    const shiftInput = document.getElementById('shiftTaskShiftInput');
    shiftInput.value = currentShift.startsWith("MANUAL_") ? currentShift.slice(7) : currentShift;
    const taskSelect = document.getElementById('shiftTaskSelect');
    const { base } = _taskBaseAndSuffix(currentTask);
    taskSelect.value = base || "";
    const hintEl = document.getElementById('shiftTaskAmPmHint'); const hintText = document.getElementById('shiftTaskAmPmText');
    const startHour = getShiftStartHour(currentShift);
    if (currentShift && currentShift !== "OFF" && currentShift !== "VAC" && currentShift !== "PERM") {
        hintEl.style.display = 'block';
        hintText.innerHTML = startHour >= 12 ? `Turno PM (empieza a las ${startHour}:00). La tarea se marcará con <b>↓PM</b>.` : `Turno AM (empieza a las ${startHour}:00). La tarea se marcará con <b>↑AM</b>.`;
    } else { hintEl.style.display = 'none'; }
    document.getElementById('shiftTaskModal').classList.remove('hidden'); shiftInput.focus();
};

window.closeShiftTaskModal = function() { document.getElementById('shiftTaskModal').classList.add('hidden'); };

window.confirmShiftTaskEdit = async function() {
    const { empName, day, histIndex } = shiftTaskModalData;
    const entry = historyEntriesCache[histIndex]; if (!entry) return;
    const newShiftInput = document.getElementById('shiftTaskShiftInput').value.trim();
    const taskSelect = document.getElementById('shiftTaskSelect'); const taskBase = taskSelect.value;
    let newShift = null;
    if (newShiftInput && newShiftInput !== "") { const normalized = normalizeFlexibleShiftInput(newShiftInput); if (normalized && normalized !== "AUTO") newShift = normalized; }
    if (!newShift || newShift === "OFF") newShift = "OFF";
    let newTask = null;
    if (taskBase) {
        const startHour = getShiftStartHour(newShift); let suffix = "";
        if (newShift !== "OFF" && newShift !== "VAC" && newShift !== "PERM") { suffix = startHour >= 12 ? "↓PM" : "↑AM"; }
        newTask = taskBase + (suffix ? " " + suffix : "");
    }
    const nextEntry = cloneHistoryEntry(entry);
    nextEntry.schedule = nextEntry.schedule || {}; nextEntry.schedule[empName] = nextEntry.schedule[empName] || {};
    nextEntry.daily_tasks = nextEntry.daily_tasks || {}; nextEntry.daily_tasks[empName] = nextEntry.daily_tasks[empName] || {};
    nextEntry.schedule[empName][day] = newShift; nextEntry.daily_tasks[empName][day] = newTask;
    try { await persistHistoryEntry(histIndex, nextEntry); closeShiftTaskModal(); renderHistoryEntryTable(histIndex); setStatusMessage(`Actualizado: ${empName} - ${day}`, "success"); }
    catch (err) { console.error(err); setStatusMessage("Error al guardar: " + err.message, "error"); }
};

/* ── History Edit Shift ── */
async function editHistoryShift(empName, day, histIndex) {
    const entry = historyEntriesCache[histIndex]; if (!entry) return;
    const currentShift = entry.schedule?.[empName]?.[day] || "OFF";
    const newValue = await promptHistoryShiftValue(empName, [day], currentShift);
    if (newValue === null) return;
    const nextEntry = cloneHistoryEntry(entry);
    nextEntry.schedule = nextEntry.schedule || {}; nextEntry.schedule[empName] = nextEntry.schedule[empName] || {};
    nextEntry.schedule[empName][day] = newValue;
    try { await persistHistoryEntry(histIndex, nextEntry); renderHistoryEntryTable(histIndex); setStatusMessage(`${empName} (${day}) → ${newValue}`, "success"); }
    catch (err) { console.error(err); setStatusMessage("Error al guardar: " + err.message, "error"); }
}
window.editHistoryShift = editHistoryShift;

async function editHistoryShiftBatch(empName, days, histIndex) {
    const entry = historyEntriesCache[histIndex]; if (!entry) return;
    const currentShift = entry.schedule?.[empName]?.[days[0]] || "OFF";
    const newValue = await promptHistoryShiftValue(empName, days, currentShift);
    if (newValue === null) return;
    const nextEntry = cloneHistoryEntry(entry);
    nextEntry.schedule = nextEntry.schedule || {}; nextEntry.schedule[empName] = nextEntry.schedule[empName] || {};
    days.forEach(d => { nextEntry.schedule[empName][d] = newValue; });
    try { await persistHistoryEntry(histIndex, nextEntry); renderHistoryEntryTable(histIndex); setStatusMessage(`${empName} (${days.join(", ")}) → ${newValue}`, "success"); }
    catch (err) { console.error(err); setStatusMessage("Error al guardar: " + err.message, "error"); }
}
window.editHistoryShiftBatch = editHistoryShiftBatch;

function buildHistoryShiftPromptMessage(empName, days) { const dayLabel = days.length === 1 ? days[0] : days.join(", "); return `Cambiar turno de ${empName} (${dayLabel})`; }

function getHistoryPromptDefaultValue(shiftCode) { if (!shiftCode) return ""; return shiftCode.startsWith(MANUAL_SHIFT_PREFIX) ? shiftCode.slice(MANUAL_SHIFT_PREFIX.length) : shiftCode; }

let shiftPromptCallback = null;

function promptHistoryShiftValue(empName, days, currentValue = "") {
    return new Promise((resolve) => {
        const message = buildHistoryShiftPromptMessage(empName, days);
        const defaultVal = getHistoryPromptDefaultValue(currentValue);
        document.getElementById('textEditTitle').textContent = message;
        document.getElementById('textEditLabel').textContent = 'Turno';
        document.getElementById('textEditInput').value = defaultVal;
        document.getElementById('textEditInput').placeholder = "Ej: 5am-1pm, 13-22, OFF";
        const legendWrap = document.getElementById('textEditLegendWrap'); const legendBody = document.getElementById('textEditLegend');
        if (legendWrap && legendBody) {
            legendWrap.style.display = 'block';
            const codes = Object.keys(SHIFT_HOURS || {}).filter(c => c && !["OFF", "VAC", "PERM"].includes(c)).sort((a, b) => ((SHIFT_HOURS[a] && SHIFT_HOURS[a].start) || 0) - ((SHIFT_HOURS[b] && SHIFT_HOURS[b].start) || 0));
            const friendly = (code) => { const info = (typeof getShiftInfo === "function") ? getShiftInfo(code) : null; return info && info.text ? info.text : code; };
            const fastItems = codes.map(c => `<code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">${escapeHtmlAttr(c)}</code> = <span style="color:var(--text-muted);">${escapeHtmlAttr(friendly(c))}</span>`).join('<br/>');
            legendBody.innerHTML = `<div style="margin-bottom:0.4rem;"><b>Códigos rápidos</b></div><div style="margin-bottom:0.6rem;">${fastItems}</div><div style="margin-bottom:0.4rem;"><b>Horario manual</b></div><div style="margin-bottom:0.6rem; color:var(--text-muted);">Escribí el rango directamente:<br/><code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">13-22</code> · <code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">1pm-10pm</code> · <code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">5am-11am + 5pm-8pm</code></div><div style="margin-bottom:0.4rem;"><b>Códigos especiales</b></div><div style="color:var(--text-muted);"><code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">OFF</code> Libre &nbsp;·&nbsp;<code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">VAC</code> Vacaciones &nbsp;·&nbsp;<code style="background:var(--bg-app); padding:1px 5px; border-radius:4px; font-size:0.75rem;">PERM</code> Permiso</div>`;
        }
        shiftPromptCallback = (input) => {
            if (!input || input.trim() === "") { resolve(null); return; }
            const trimmed = input.trim(); const normalized = normalizeFlexibleShiftInput(trimmed);
            if (!normalized || normalized === "AUTO") { document.getElementById('textEditInput').style.borderColor = 'var(--error)'; setTimeout(() => { document.getElementById('textEditInput').style.borderColor = ''; }, 2000); return; }
            resolve(normalized);
        };
        document.getElementById('textEditModal').classList.remove('hidden'); document.getElementById('textEditInput').focus();
    });
}

/* ── History Validate / Reassign / Swap ── */
window.validateHistory = async function (index, event) {
    if (event) event.stopPropagation();
    try {
        await fetchHistoryEntries(); const entry = historyEntriesCache[index]; if (!entry) return;
        const oldSchedule = currentGeneratedSchedule; const oldRules = validationRules; const oldMeta = currentMetadata;
        currentGeneratedSchedule = entry.schedule;
        currentMetadata = oldMeta && typeof oldMeta === "object" ? { ...oldMeta } : {};
        delete currentMetadata.rest_between_shifts; delete currentMetadata.min_rest_hours_applied; delete currentMetadata.min_rest_hours_target;
        if (entry.rest_between_shifts) currentMetadata.rest_between_shifts = entry.rest_between_shifts;
        if (entry.min_rest_hours_applied != null) currentMetadata.min_rest_hours_applied = entry.min_rest_hours_applied;
        if (entry.min_rest_hours_target != null) currentMetadata.min_rest_hours_target = entry.min_rest_hours_target;
        validationRules = await fetchValidationRules(entry.special_days || {});
        isValidationOn = true; applyValidationUI();
        currentGeneratedSchedule = oldSchedule; validationRules = oldRules || baseValidationRules; currentMetadata = oldMeta;
        setStatusMessage("Validación del historial aplicada.", "success");
    } catch (err) { console.error(err); setStatusMessage("Error al validar historial.", "error"); }
};

window.reassignHistoryTasks = async function (index, event) {
    if (event) { event.preventDefault(); event.stopPropagation(); }
    try {
        setStatusMessage("Recalculando limpieza...", "info", 0);
        await fetchHistoryEntries(); const entry = historyEntriesCache[index]; if (!entry) return;
        const reassignUrl = entry && entry.db_id != null ? `/api/history/entry/${entry.db_id}/reassign_tasks` : `/api/history/${index}/reassign_tasks`;
        const res = await fetch(reassignUrl, { method: "POST" });
        const payload = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(payload.detail || `API returned ${res.status}`);
        entry.daily_tasks = payload.daily_tasks || {}; entry.special_days = payload.special_days || entry.special_days || {};
        renderHistoryEntryTable(index); setStatusMessage("Limpieza recalculada para esta semana.", "success");
    } catch (err) { console.error(err); setStatusMessage("No se pudo recalcular la limpieza.", "error"); alert(err.message || "Error al recalcular limpieza"); }
};

window.swapHistoryEmployees = async function (index, event) {
    if (event) { event.preventDefault(); event.stopPropagation(); }
    const entry = historyEntriesCache[index]; if (!entry) return;
    const employees = Object.keys(entry.schedule || {});
    if (employees.length < 2) { alert("Se necesitan al menos 2 empleados para intercambiar."); return; }
    const emp1 = prompt("Empleado 1:", employees[0]); if (!emp1 || !employees.includes(emp1)) return;
    const emp2 = prompt("Empleado 2:", employees[1]); if (!emp2 || !employees.includes(emp2) || emp2 === emp1) return;
    const nextEntry = cloneHistoryEntry(entry);
    DAYS.forEach(d => {
        const tmp = nextEntry.schedule[emp1][d]; nextEntry.schedule[emp1][d] = nextEntry.schedule[emp2][d]; nextEntry.schedule[emp2][d] = tmp;
        const tmpT = (nextEntry.daily_tasks[emp1] || {})[d];
        if (!nextEntry.daily_tasks[emp1]) nextEntry.daily_tasks[emp1] = {};
        if (!nextEntry.daily_tasks[emp2]) nextEntry.daily_tasks[emp2] = {};
        nextEntry.daily_tasks[emp1][d] = (nextEntry.daily_tasks[emp2] || {})[d] || null;
        nextEntry.daily_tasks[emp2][d] = tmpT || null;
    });
    try { await persistHistoryEntry(index, nextEntry); renderHistoryEntryTable(index); setStatusMessage(`Intercambiados: ${emp1} ↔ ${emp2}`, "success"); }
    catch (err) { console.error(err); setStatusMessage("Error al intercambiar.", "error"); }
};

/* ── History Export Image ── */
async function exportHistoryImage(index, event) {
    if (event) { event.preventDefault(); event.stopPropagation(); }
    const table = document.getElementById(`hist-table-${index}`);
    if (!table) return;
    try {
        const canvas = await renderScheduleCaptureCanvas(table.closest('.history-table-wrapper') || table);
        const name = getHistoryExportBaseName(index);
        const filename = `${name}_historial.png`;
        const imgData = canvas.toDataURL("image/png");
        const link = document.createElement('a'); link.download = filename; link.href = imgData; link.click();
        showExportConfirmationModal(filename, 'image');
    } catch (err) { console.error(err); alert("Error al exportar imagen del historial: " + err.message); }
}
window.exportHistoryImage = exportHistoryImage;

/* ── Trash ── */
async function restoreHistory(i, event) {
    if (event) { event.preventDefault(); event.stopPropagation(); }
    const entry = trashCache[i]; if (!entry) return;
    const restoreUrl = entry.db_id != null ? `/api/history/trash/restore/${entry.db_id}` : `/api/history/${i}/restore`;
    const res = await fetch(restoreUrl, { method: 'POST' });
    if (!res.ok) { alert("No se pudo restaurar la semana."); return; }
    trashCache.splice(i, 1);
    await fetchHistoryEntries(true); renderHistoryList(); renderTrashList();
    setStatusMessage(`"${entry.name}" restaurada del historial.`, "success");
}
window.restoreHistory = restoreHistory;

async function permanentDeleteTrash(i, event) {
    if (event) { event.preventDefault(); event.stopPropagation(); }
    const entry = trashCache[i]; if (!entry) return;
    if (!confirm(`¿Eliminar "${entry.name}" PERMANENTEMENTE?\nEsta acción no se puede deshacer.`)) return;
    const delUrl = entry.db_id != null ? `/api/history/trash/entry/${entry.db_id}` : `/api/history/trash/${i}`;
    const res = await fetch(delUrl, { method: 'DELETE' });
    if (!res.ok) { alert("No se pudo eliminar permanentemente."); return; }
    trashCache.splice(i, 1); renderTrashList();
    setStatusMessage(`"${entry.name}" eliminada permanentemente.`, "success");
}
window.permanentDeleteTrash = permanentDeleteTrash;

async function purgeTrash(event) {
    if (event) { event.preventDefault(); event.stopPropagation(); }
    if (!confirm('¿Eliminar permanentemente todas las entradas con más de 7 días en la papelera?')) return;
    const res = await fetch('/api/history/trash/purge', { method: 'POST' });
    if (!res.ok) { alert("No se pudo purgar la papelera."); return; }
    await loadTrash(); renderTrashList(); setStatusMessage("Papelera purgada.", "success");
}
window.purgeTrash = purgeTrash;

function toggleTrashSection() { const body = document.getElementById('trashBody'); const arrow = document.getElementById('trashArrow'); if (!body) return; body.classList.toggle('hidden'); if (arrow) arrow.classList.toggle('rotated'); }
window.toggleTrashSection = toggleTrashSection;

/* ── History Import Excel ── */
let importHorarioExcelHistorialFile = null;
let importHorarioExcelHistorialDrafts = [];

function closeImportHorarioExcelHistorialModal() { const m = document.getElementById("importHorarioExcelHistorialModal"); if (m) m.classList.add("hidden"); }
window.closeImportHorarioExcelHistorialModal = closeImportHorarioExcelHistorialModal;

function openImportHorarioExcelHistorialModal() {
    importHorarioExcelHistorialFile = null; importHorarioExcelHistorialDrafts = [];
    const inp = document.getElementById("importHorarioExcelFileInput"); if (inp) inp.value = "";
    const sl = document.getElementById("importHorarioExcelSheetList"); if (sl) sl.innerHTML = "";
    const pv = document.getElementById("importHorarioExcelPreview"); if (pv) pv.innerHTML = "";
    const st = document.getElementById("importHorarioExcelStatus"); if (st) st.textContent = "";
    const iw = document.getElementById("importHorarioExcelInverseWarnings"); if (iw) iw.textContent = "";
    const btn = document.getElementById("importHorarioExcelConfirmBtn"); if (btn) btn.disabled = true;
    const m = document.getElementById("importHorarioExcelHistorialModal"); if (m) m.classList.remove("hidden");
}
window.openImportHorarioExcelHistorialModal = openImportHorarioExcelHistorialModal;

function _importHorarioExcelApiErrorMessage(data, fallback) {
    const d = data && data.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return d.map((x) => (x && (x.msg || x.message)) || JSON.stringify(x)).join("; ");
    if (d && typeof d === "object") return JSON.stringify(d);
    return fallback || "Error";
}

async function onImportHorarioExcelHistorialFileChange(ev) {
    const f = ev.target.files && ev.target.files[0];
    const sl = document.getElementById("importHorarioExcelSheetList"); const st = document.getElementById("importHorarioExcelStatus");
    if (!f) return;
    importHorarioExcelHistorialFile = f; importHorarioExcelHistorialDrafts = [];
    if (sl) sl.innerHTML = ""; const pv = document.getElementById("importHorarioExcelPreview"); if (pv) pv.innerHTML = "";
    const btn = document.getElementById("importHorarioExcelConfirmBtn"); if (btn) btn.disabled = true;
    if (st) st.textContent = "Leyendo pestañas…";
    const fd = new FormData(); fd.append("file", f); fd.append("sheets", "[]");
    try {
        const res = await fetch("/api/history/import-horario-excel/preview", { method: "POST", body: fd });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(_importHorarioExcelApiErrorMessage(data, res.statusText));
        if (st) st.textContent = `Archivo: ${f.name} — elija pestañas y pulse Vista previa.`;
        (data.sheetnames || []).forEach((name) => {
            const n = String(name).trim(); const isDefault = /^(10|11|12|13)$/.test(n);
            const safeId = `import-excel-sheet-${String(name).replace(/\W/g, "_")}`;
            const cb = document.createElement("input"); cb.type = "checkbox"; cb.value = name; cb.id = safeId; cb.checked = isDefault; cb.style.display = "none";
            const chip = document.createElement("label"); chip.htmlFor = safeId; chip.className = "excel-sheet-chip" + (isDefault ? " selected" : ""); chip.textContent = n || name; chip.title = name;
            cb.addEventListener("change", () => { chip.classList.toggle("selected", cb.checked); });
            sl.appendChild(cb); sl.appendChild(chip);
        });
    } catch (e) { console.error(e); if (st) st.textContent = e.message || String(e); }
}
window.onImportHorarioExcelHistorialFileChange = onImportHorarioExcelHistorialFileChange;

async function runImportHorarioExcelHistorialPreview() {
    const st = document.getElementById("importHorarioExcelStatus"); const iw = document.getElementById("importHorarioExcelInverseWarnings");
    const btn = document.getElementById("importHorarioExcelConfirmBtn");
    if (!importHorarioExcelHistorialFile) { if (st) st.textContent = "Seleccione un archivo Excel."; return; }
    const checks = [...document.querySelectorAll("#importHorarioExcelSheetList input[type=checkbox]:checked")];
    const sheets = checks.map((c) => c.value);
    if (!sheets.length) { if (st) st.textContent = "Marque al menos una hoja."; return; }
    if (st) st.textContent = "Generando vista previa…"; if (iw) iw.textContent = ""; btn.disabled = true;
    const fd = new FormData(); fd.append("file", importHorarioExcelHistorialFile); fd.append("sheets", JSON.stringify(sheets));
    try {
        const res = await fetch("/api/history/import-horario-excel/preview", { method: "POST", body: fd });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(_importHorarioExcelApiErrorMessage(data, res.statusText));
        importHorarioExcelHistorialDrafts = data.drafts || [];
        if (Array.isArray(data.inverse_map_warnings) && data.inverse_map_warnings.length) iw.textContent = "Avisos catálogo turnos (colisiones texto→código): " + data.inverse_map_warnings.slice(0, 6).join("; ");
        renderImportHorarioExcelHistorialPreview(importHorarioExcelHistorialDrafts);
        const anyOk = importHorarioExcelHistorialDrafts.some((d) => (!d.errors || !d.errors.length) && d.week_dates && Object.keys(d.week_dates).length >= 7);
        btn.disabled = !anyOk;
        if (st) st.textContent = anyOk ? "Revise la vista previa y pulse Aceptar (solo se guardan las hojas sin errores)." : "Ninguna hoja es importable: corrija el Excel o elija otras pestañas.";
    } catch (e) { console.error(e); if (st) st.textContent = e.message || String(e); }
}
window.runImportHorarioExcelHistorialPreview = runImportHorarioExcelHistorialPreview;

function renderImportHorarioExcelHistorialPreview(drafts) {
    const pv = document.getElementById("importHorarioExcelPreview"); if (!pv) return; pv.innerHTML = "";
    drafts.forEach((d, i) => {
        const card = document.createElement("div"); card.className = "import-excel-draft-card"; card.dataset.draftIndex = String(i);
        card.style.cssText = "margin-bottom: 1.25rem; padding: 12px; border: 1px solid var(--border, #e2e8f0); border-radius: 10px;";
        const h = document.createElement("h4"); h.style.margin = "0 0 8px"; h.textContent = `Hoja: ${d.sheet || ""}`; card.appendChild(h);
        const errBox = document.createElement("div");
        if (d.errors && d.errors.length) { errBox.style.color = "var(--danger, #dc2626)"; errBox.style.fontSize = "0.85rem"; errBox.style.marginBottom = "8px"; errBox.textContent = "Errores: " + d.errors.join(" · "); }
        card.appendChild(errBox);
        const warnBox = document.createElement("div");
        if (d.warnings && d.warnings.length) { warnBox.style.color = "var(--warning, #d97706)"; warnBox.style.fontSize = "0.85rem"; warnBox.style.marginBottom = "8px"; warnBox.textContent = "Avisos: " + d.warnings.slice(0, 14).join(" · "); }
        card.appendChild(warnBox);
        const nameL = document.createElement("label"); nameL.textContent = "Nombre en historial"; nameL.style.display = "block"; nameL.style.fontSize = "0.85rem"; nameL.style.marginBottom = "4px";
        const nameInp = document.createElement("input"); nameInp.type = "text"; nameInp.className = "import-draft-name form-input"; nameInp.style.width = "100%"; nameInp.style.marginBottom = "10px"; nameInp.value = (d.name_sugerido || "").trim(); nameInp.placeholder = "Ej. Semana 10";
        card.appendChild(nameL); card.appendChild(nameInp);
        const wrap = document.createElement("div"); wrap.className = "history-table-wrapper"; wrap.style.overflowX = "auto";
        const table = document.createElement("table"); table.className = "clean-table"; table.id = `import-hist-prev-${i}`;
        table.innerHTML = `<thead><tr><th>Empleado</th><th>Vie</th><th>Sáb</th><th>Dom</th><th>Lun</th><th>Mar</th><th>Mié</th><th>Jue</th><th class="col-hours">Horas</th></tr></thead><tbody></tbody>`;
        wrap.appendChild(table); card.appendChild(wrap); pv.appendChild(card);
        renderSchedule(d.schedule || {}, `#import-hist-prev-${i}`, d.daily_tasks || {}, {}, null, d.week_dates || null);
        const tasks = d.daily_tasks || {}; const DAYS_PREVIEW = ["Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue"];
        const taskEntries = Object.entries(tasks).filter(([, days]) => DAYS_PREVIEW.some((day) => days[day]));
        if (taskEntries.length) {
            const tasksWrap = document.createElement("div"); tasksWrap.className = "import-tasks-preview";
            const tasksTitle = document.createElement("div"); tasksTitle.className = "import-tasks-title"; tasksTitle.innerHTML = `<i class="fa-solid fa-broom"></i> Tareas de Limpieza Detectadas`; tasksWrap.appendChild(tasksTitle);
            const tasksGrid = document.createElement("div"); tasksGrid.className = "import-tasks-grid";
            for (const [emp, days] of taskEntries) {
                const empRow = document.createElement("div"); empRow.className = "import-tasks-row";
                const empName = document.createElement("span"); empName.className = "import-tasks-emp"; empName.textContent = emp; empRow.appendChild(empName);
                for (const day of DAYS_PREVIEW) {
                    const task = days[day]; const cell = document.createElement("span");
                    let taskColorCls = "";
                    if (task) { const { base } = _taskBaseAndSuffix(task); taskColorCls = " itc-" + _taskColorClass(base).replace("task-", ""); }
                    cell.className = "import-tasks-cell" + (task ? " has-task" + taskColorCls : "");
                    cell.textContent = task ? _taskBaseAndSuffix(task).base : "–"; cell.title = task ? `${day}: ${task}` : "";
                    empRow.appendChild(cell);
                }
                tasksGrid.appendChild(empRow);
            }
            tasksWrap.appendChild(tasksGrid); card.appendChild(tasksWrap);
        }
    });
}
window.renderImportHorarioExcelHistorialPreview = renderImportHorarioExcelHistorialPreview;

async function confirmImportHorarioExcelHistorial() {
    const st = document.getElementById("importHorarioExcelStatus");
    const cards = [...document.querySelectorAll("#importHorarioExcelPreview .import-excel-draft-card")];
    const items = []; const days = ["Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue"];
    for (const card of cards) {
        const i = Number(card.dataset.draftIndex); const d = importHorarioExcelHistorialDrafts[i]; if (!d) continue;
        if (d.errors && d.errors.length) continue;
        if (!d.week_dates || days.some((day) => !(day in d.week_dates))) continue;
        const nameInp = card.querySelector(".import-draft-name");
        const name = (nameInp && nameInp.value.trim()) || (d.name_sugerido || "").trim();
        if (!name) { if (st) st.textContent = "Indique un nombre en historial para cada semana válida."; return; }
        items.push({ name, schedule: d.schedule || {}, week_dates: d.week_dates, daily_tasks: d.daily_tasks || {} });
    }
    if (!items.length) { if (st) st.textContent = "No hay borradores válidos para guardar."; return; }
    if (st) st.textContent = "Guardando…";
    try {
        const res = await fetch("/api/history/import-horario-excel/confirm", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ items }) });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(_importHorarioExcelApiErrorMessage(data, res.statusText));
        closeImportHorarioExcelHistorialModal(); await loadHistory(true);
    } catch (e) { console.error(e); if (st) st.textContent = e.message || String(e); }
}
window.confirmImportHorarioExcelHistorial = confirmImportHorarioExcelHistorial;

/* ── Manual Week Entry ── */
const MANUAL_DAYS = ["Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue"];
const MANUAL_CLEANING_TASKS = ["", "Baños", "Tanques", "Oficina + Basureros + Baños"];
const MANUAL_SHIFTS_OPTIONS = [
    { code: "OFF", label: "Libre" }, { code: "VAC", label: "Vacaciones" }, { code: "PERM", label: "Permiso" },
    { code: "T1_05-13", label: "T1 5am-1pm" }, { code: "T2_06-14", label: "T2 6am-2pm" }, { code: "T3_07-15", label: "T3 7am-3pm" },
    { code: "T4_08-16", label: "T4 8am-4pm" }, { code: "PM_13-22", label: "PM 1pm-10pm" }, { code: "J_06-16", label: "J 6am-4pm" }, { code: "N_22-05", label: "N 10pm-5am" },
];

function toggleManualWeekForm() {
    const form = document.getElementById("importManualWeekForm"); const btn = document.getElementById("toggleManualWeekBtn");
    if (!form) return; const isHidden = form.classList.toggle("hidden");
    btn.innerHTML = isHidden ? '<i class="fa-solid fa-plus"></i> Agregar semana manualmente' : '<i class="fa-solid fa-minus"></i> Ocultar entrada manual';
    if (!isHidden) _buildManualWeekTable();
}
window.toggleManualWeekForm = toggleManualWeekForm;

function _getManualShiftOptsHTML() {
    const base = (SHIFT_OPTIONS && SHIFT_OPTIONS.length) ? SHIFT_OPTIONS.map(o => `<option value="${o.code}">${o.label}</option>`).join("") : MANUAL_SHIFTS_OPTIONS.map(o => `<option value="${o.code}">${o.label}</option>`).join("");
    return base + `<option value="__OTRO__">⌨ Horario manual…</option>`;
}

function _getManualTaskOptsHTML() { return MANUAL_CLEANING_TASKS.map(t => `<option value="${t}">${t || "—"}</option>`).join(""); }

function _buildManualWeekRow(empName, isEditable) {
    const shiftOptsHTML = _getManualShiftOptsHTML(); const taskOptsHTML = _getManualTaskOptsHTML();
    const tr = document.createElement("tr");
    const nameTd = document.createElement("td"); nameTd.style.padding = "4px 5px";
    if (isEditable) {
        const inp = document.createElement("input"); inp.type = "text"; inp.placeholder = "Nombre colaborador"; inp.className = "form-input manual-emp-name-input";
        inp.style.cssText = "width:100%;font-size:0.78rem;padding:3px 6px;border-radius:6px;"; inp.dataset.empName = "";
        inp.addEventListener("input", () => { inp.dataset.empName = inp.value.trim(); nameTd.dataset.empName = inp.value.trim(); });
        nameTd.appendChild(inp);
    } else { nameTd.textContent = empName; nameTd.dataset.empName = empName; nameTd.style.fontWeight = "500"; nameTd.style.fontSize = "0.82rem"; }
    tr.appendChild(nameTd);
    for (const day of MANUAL_DAYS) {
        const td = document.createElement("td"); td.style.padding = "3px 2px";
        const shiftSel = document.createElement("select"); shiftSel.className = "manual-shift-sel"; shiftSel.dataset.emp = empName; shiftSel.dataset.day = day;
        shiftSel.innerHTML = shiftOptsHTML; shiftSel.style.cssText = "width:100%;min-width:82px;font-size:0.7rem;padding:2px 3px;border-radius:6px;background:var(--bg-app);border:1px solid var(--border);color:var(--text-main);display:block;";
        const customInp = document.createElement("input"); customInp.type = "text"; customInp.placeholder = "Ej: 8:00-16:00"; customInp.className = "manual-custom-time hidden";
        customInp.style.cssText = "width:100%;font-size:0.68rem;padding:2px 4px;margin-top:2px;border-radius:5px;background:var(--bg-app);border:1px solid var(--primary,#6366f1);color:var(--text-main);display:none;";
        shiftSel.addEventListener("change", () => { const isOtro = shiftSel.value === "__OTRO__"; customInp.style.display = isOtro ? "block" : "none"; });
        const taskSel = document.createElement("select"); taskSel.className = "manual-task-sel"; taskSel.dataset.emp = empName; taskSel.dataset.day = day;
        taskSel.innerHTML = taskOptsHTML; taskSel.style.cssText = "width:100%;font-size:0.67rem;padding:1px 3px;margin-top:2px;border-radius:5px;background:var(--surface-2);border:1px solid var(--border);color:var(--text-muted);display:block;";
        td.appendChild(shiftSel); td.appendChild(customInp); td.appendChild(taskSel); tr.appendChild(td);
    }
    const delTd = document.createElement("td"); delTd.style.padding = "4px 3px";
    const delBtn = document.createElement("button"); delBtn.type = "button"; delBtn.innerHTML = `<i class="fa-solid fa-xmark"></i>`; delBtn.title = "Eliminar esta fila";
    delBtn.style.cssText = "background:none;border:none;color:var(--danger,#dc2626);cursor:pointer;font-size:0.9rem;padding:2px 5px;border-radius:4px;";
    delBtn.addEventListener("click", () => tr.remove()); delTd.appendChild(delBtn); tr.appendChild(delTd);
    return tr;
}

function _buildManualWeekTable() {
    const tbody = document.getElementById("manualWeekTableBody"); if (!tbody) return; tbody.innerHTML = "";
    const activeEmps = employees.filter(e => e.activo !== false && e.activo !== 0);
    for (const emp of activeEmps) tbody.appendChild(_buildManualWeekRow(emp.name || "", false));
    if (!activeEmps.length) _addManualEmptyRow();
}

function _addManualEmptyRow() {
    const tbody = document.getElementById("manualWeekTableBody"); if (!tbody) return;
    const tr = _buildManualWeekRow("", true); tbody.appendChild(tr);
    const inp = tr.querySelector(".manual-emp-name-input"); if (inp) setTimeout(() => inp.focus(), 50);
}

function onManualWeekDateChange() { /* noop */ }
window.onManualWeekDateChange = onManualWeekDateChange;

function addManualWeekToPreview() {
    const nameVal = (document.getElementById("manualWeekName")?.value || "").trim();
    const fridayVal = document.getElementById("manualWeekFridayDate")?.value || "";
    const statusEl = document.getElementById("manualWeekStatus");
    if (!nameVal) { if (statusEl) statusEl.textContent = "Ingresá un nombre para la semana."; return; }
    if (!fridayVal) { if (statusEl) statusEl.textContent = "Seleccioná la fecha del Viernes."; return; }
    const weekDates = _fridayToWeekDates(fridayVal);
    const schedule = {}; const dailyTasks = {};
    document.querySelectorAll("#manualWeekTableBody tr").forEach(tr => {
        const nameTd = tr.querySelector("td[data-emp-name]"); const nameInp = tr.querySelector(".manual-emp-name-input");
        const empName = (nameTd?.dataset?.empName || nameInp?.value || "").trim(); if (!empName) return;
        schedule[empName] = {}; dailyTasks[empName] = {};
        MANUAL_DAYS.forEach(day => {
            const shiftSel = tr.querySelector(`.manual-shift-sel[data-day="${day}"]`);
            const taskSel = tr.querySelector(`.manual-task-sel[data-day="${day}"]`);
            let shiftVal = shiftSel?.value || "OFF";
            if (shiftVal === "__OTRO__") {
                const td = shiftSel?.closest("td"); const timeInp = td?.querySelector(".manual-custom-time");
                const raw = timeInp?.value?.trim() || "";
                shiftVal = typeof normalizeFlexibleShiftInput === 'function' ? normalizeFlexibleShiftInput(raw) || "OFF" : (raw ? (raw.startsWith("MANUAL_") ? raw : "MANUAL_" + raw) : "OFF");
            }
            schedule[empName][day] = shiftVal;
            const tv = taskSel?.value || ""; dailyTasks[empName][day] = tv || null;
        });
    });
    if (Object.keys(schedule).length === 0) { if (statusEl) statusEl.textContent = "Agregá al menos un empleado con turnos."; return; }
    const previewContainer = document.getElementById("manualWeekPreview");
    if (previewContainer) {
        previewContainer.innerHTML = `<div class="history-table-wrapper"><table class="clean-table" id="manual-week-preview-table"><thead><tr><th>Empleado</th>${MANUAL_DAYS.map(d => `<th>${d}</th>`).join('')}<th class="col-hours">Horas</th></tr></thead><tbody></tbody></table></div>`;
        renderSchedule(schedule, "#manual-week-preview-table", dailyTasks, {}, null, weekDates);
        if (statusEl) statusEl.textContent = `Preview: "${nameVal}" — ${Object.keys(schedule).length} empleados.`;
    }
    const saveBtn = document.getElementById("manualWeekSaveBtn");
    if (saveBtn) {
        saveBtn.disabled = false;
        saveBtn.onclick = async () => {
            if (statusEl) statusEl.textContent = "Guardando...";
            try {
                const entry = { name: nameVal, schedule, daily_tasks: dailyTasks, week_dates: weekDates, timestamp: new Date().toISOString() };
                const res = await fetch('/api/history', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(entry) });
                if (!res.ok) throw new Error("Error al guardar");
                if (statusEl) statusEl.textContent = `"${nameVal}" guardado exitosamente.`;
                await loadHistory(true);
            } catch (e) { console.error(e); if (statusEl) statusEl.textContent = "Error: " + e.message; }
        };
    }
}
window.addManualWeekToPreview = addManualWeekToPreview;

/* ── Text Edit Modal (generic) ── */
let textEditCallback = null;

function openTextEditModal(title, label, defaultValue, callback) {
    document.getElementById('textEditTitle').textContent = title;
    document.getElementById('textEditLabel').textContent = label;
    document.getElementById('textEditInput').value = defaultValue || "";
    textEditCallback = callback;
    document.getElementById('textEditModal').classList.remove('hidden');
    document.getElementById('textEditInput').focus();
}
window.openTextEditModal = openTextEditModal;

function closeTextEditModal() {
    document.getElementById('textEditModal').classList.add('hidden');
    textEditCallback = null; shiftPromptCallback = null;
    const legendWrap = document.getElementById('textEditLegendWrap'); if (legendWrap) legendWrap.style.display = 'none';
}
window.closeTextEditModal = closeTextEditModal;

function confirmTextEdit() {
    const value = document.getElementById('textEditInput').value;
    if (shiftPromptCallback) { shiftPromptCallback(value); shiftPromptCallback = null; }
    else if (textEditCallback) { textEditCallback(value); }
    closeTextEditModal();
}
window.confirmTextEdit = confirmTextEdit;

/* ── Holiday Modal ── */
let holidayModalData = { histIndex: null };

window.toggleDayAsHoliday = function(index, event) {
    if (event) { event.preventDefault(); event.stopPropagation(); }
    const entry = historyEntriesCache[index]; if (!entry) return;
    holidayModalData = { histIndex: index };
    const existingHolidays = entry.metadata?.holiday_days || {};
    const modalHtml = `<div id="holidayModal" class="modal-backdrop"><div class="modal-dialog" style="max-width: 400px;"><div class="modal-content"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; border-bottom: 1px solid var(--border-color); padding-bottom: 0.75rem;"><h3 style="margin: 0; font-size: 1.1rem;">Marcar Día como Feriado</h3><button type="button" onclick="closeHolidayModal()" style="background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 1.25rem;"><i class="fa-solid fa-xmark"></i></button></div><p class="helper-text" style="margin-bottom: 1rem;"><i class="fa-solid fa-info-circle"></i> Seleccioná el día de la semana para marcarlo como feriado.</p><div id="holidayDaysContainer" style="display: flex; flex-direction: column; gap: 0.5rem;">${DAYS.map(d => { const isChecked = !!existingHolidays[d]; const holidayName = existingHolidays[d] || ""; return `<label style="display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem; background: var(--surface-2); border-radius: 8px; cursor: pointer; border: 1px solid ${isChecked ? 'var(--primary)' : 'var(--border-color)'};"><input type="checkbox" class="holiday-day-checkbox" data-day="${d}" ${isChecked ? 'checked' : ''} style="width: 18px; height: 18px; accent-color: var(--primary);" onchange="toggleHolidayDayInput('${d}', this.checked)"><span style="font-weight: 600; min-width: 50px;">${d}</span><input type="text" id="holidayName_${d}" class="custom-input" placeholder="Nombre del feriado" value="${holidayName}" style="flex: 1; padding: 0.4rem; font-size: 0.85rem; ${isChecked ? '' : 'display: none;'}" ${isChecked ? '' : 'disabled'}></label>`; }).join('')}</div><div class="modal-actions" style="margin-top: 1rem;"><button type="button" class="btn-text" onclick="closeHolidayModal()">Cancelar</button><button type="button" class="btn-action primary" onclick="saveHolidayDays()">Guardar</button></div></div></div></div>`;
    const existing = document.getElementById('holidayModal'); if (existing) existing.remove();
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    document.getElementById('holidayModal').classList.remove('hidden');
};

window.toggleHolidayDayInput = function(day, checked) {
    const input = document.getElementById(`holidayName_${day}`);
    if (input) { input.style.display = checked ? 'block' : 'none'; input.disabled = !checked; if (!checked) input.value = ''; }
};

window.closeHolidayModal = function() { const modal = document.getElementById('holidayModal'); if (modal) modal.remove(); };

window.openHolidayDayModal = function(day, histIndex) {
    if (histIndex < 0) return;
    const entry = historyEntriesCache[histIndex]; if (!entry) return;
    holidayModalData = { histIndex, day };
    const existingHolidays = entry.metadata?.holiday_days || {};
    const isChecked = !!existingHolidays[day]; const holidayName = existingHolidays[day] || "";
    const modalHtml = `<div id="holidayModal" class="modal-backdrop"><div class="modal-dialog" style="max-width: 350px;"><div class="modal-content"><div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; border-bottom: 1px solid var(--border-color); padding-bottom: 0.75rem;"><h3 style="margin: 0; font-size: 1.1rem;">Marcar ${day} como Feriado</h3><button type="button" onclick="closeHolidayModal()" style="background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 1.25rem;"><i class="fa-solid fa-xmark"></i></button></div><p class="helper-text" style="margin-bottom: 1rem;"><i class="fa-solid fa-info-circle"></i> Esto agregará la fila de feriados en la planilla para este día.</p><div style="margin-bottom: 1rem;"><label class="option-card hover-glow holiday-modal-toggle-row" style="padding: 12px 16px; display: flex; align-items: center; gap: 12px; cursor: pointer;"><div class="toggle-container" style="flex-shrink: 0;"><input type="checkbox" id="holidayDayCheckbox" ${isChecked ? 'checked' : ''} class="toggle-checkbox" onchange="syncHolidayDayModalNameField()"><div class="toggle-slider"></div></div><div class="opt-content" style="flex: 1;"><div class="opt-icon" style="background: rgba(245, 158, 11, 0.1); color: #f59e0b;"><i class="fa-solid fa-star"></i></div><div class="opt-text"><strong style="font-size: 0.9rem;">Marcar como feriado</strong></div></div></label><input type="text" id="holidayNameInput" class="custom-input holiday-modal-name-input" placeholder="Nombre (vacío = Feriado (${day}))" value="${escapeHtmlAttr(holidayName)}" style="width: 100%; margin-top: 0.75rem; padding: 0.6rem 0.8rem; ${isChecked ? '' : 'display: none;'}" ${isChecked ? '' : 'disabled'}></div><div class="modal-actions" style="margin-top: 1rem;"><button type="button" class="btn-text" onclick="closeHolidayModal()">Cancelar</button><button type="button" class="btn-action primary" onclick="saveSingleHolidayDay()">Guardar</button></div></div></div></div>`;
    const existing = document.getElementById('holidayModal'); if (existing) existing.remove();
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    document.getElementById('holidayModal').classList.remove('hidden'); syncHolidayDayModalNameField();
};

function syncHolidayDayModalNameField() {
    const cb = document.getElementById("holidayDayCheckbox"); const inp = document.getElementById("holidayNameInput");
    if (!cb || !inp) return; const on = cb.checked; inp.disabled = !on; inp.style.display = on ? "block" : "none";
    if (on) requestAnimationFrame(() => { void inp.offsetHeight; inp.focus(); });
}
window.syncHolidayDayModalNameField = syncHolidayDayModalNameField;

window.saveSingleHolidayDay = async function() {
    const { histIndex, day } = holidayModalData;
    const entry = historyEntriesCache[histIndex]; if (!entry) { console.error("No entry found for histIndex:", histIndex); return; }
    const checkbox = document.getElementById('holidayDayCheckbox'); const nameInput = document.getElementById('holidayNameInput');
    const holidayDays = { ...(entry.metadata?.holiday_days || {}) };
    if (checkbox && checkbox.checked && nameInput) { const raw = nameInput.value.trim(); holidayDays[day] = raw || `Feriado (${day})`; }
    else { delete holidayDays[day]; }
    const nextEntry = cloneHistoryEntry(entry); nextEntry.metadata = nextEntry.metadata || {}; nextEntry.metadata.holiday_days = holidayDays;
    const savedDbId = nextEntry.db_id ?? historyEntriesCache[histIndex]?.db_id;
    try {
        await persistHistoryEntry(histIndex, nextEntry); await fetchHistoryEntries(true);
        let renderIdx = histIndex;
        if (savedDbId != null) { const found = historyEntriesCache.findIndex((e) => e.db_id === savedDbId); if (found >= 0) renderIdx = found; }
        closeHolidayModal(); renderHistoryEntryTable(renderIdx);
        setStatusMessage(checkbox && checkbox.checked ? `${day} marcado como feriado.` : `${day}: feriado quitado.`, "success");
    } catch (err) { console.error("Error saving holiday:", err); setStatusMessage("Error al guardar: " + err.message, "error"); }
};

window.saveHolidayDays = async function() {
    const { histIndex } = holidayModalData;
    const entry = historyEntriesCache[histIndex]; if (!entry) return;
    const holidayDays = {};
    DAYS.forEach(d => {
        const checkbox = document.querySelector(`.holiday-day-checkbox[data-day="${d}"]`);
        const nameInput = document.getElementById(`holidayName_${d}`);
        if (checkbox && checkbox.checked && nameInput) { const name = nameInput.value.trim(); holidayDays[d] = name || `Feriado (${d})`; }
    });
    const nextEntry = cloneHistoryEntry(entry); nextEntry.metadata = nextEntry.metadata || {}; nextEntry.metadata.holiday_days = holidayDays;
    try { await persistHistoryEntry(histIndex, nextEntry); await fetchHistoryEntries(true); closeHolidayModal(); renderHistoryList(); setStatusMessage("Días feriados actualizados.", "success"); }
    catch (err) { console.error(err); setStatusMessage("Error al guardar: " + err.message, "error"); }
};

/* ── History Name Modal ── */
let _historyNameModalState = { histIndex: null, canonical: null, suggestions: [], selectedCanonical: null };

async function _loadHistoryNameSuggestions() {
    try {
        const res = await fetch('/api/planillas/empleados'); if (!res.ok) return [];
        const all = await res.json();
        return all.filter(e => (e.activo === 1 || e.activo === true) && (e.incluir_en_horario === 1 || e.incluir_en_horario === true || e.incluir_en_horario == null)).map(e => ({ id: e.id, nombre: e.nombre || "" })).filter(e => e.nombre).sort((a, b) => a.nombre.localeCompare(b.nombre, 'es', { sensitivity: 'base' }));
    } catch (err) { console.error("No se pudieron cargar las sugerencias:", err); return []; }
}

function _renderHistoryNameSuggestions(filterText) {
    const container = document.getElementById('histNameSuggestions'); if (!container) return;
    const ft = (filterText || "").trim().toLowerCase();
    const list = _historyNameModalState.suggestions.filter(s => !ft || s.nombre.toLowerCase().includes(ft));
    if (!list.length) { container.innerHTML = `<div style="padding: 0.5rem; font-size: 0.8rem; color: var(--text-muted);">Sin coincidencias.</div>`; return; }
    container.innerHTML = list.slice(0, 20).map(s => `<div class="hist-name-option" data-name="${escapeHtmlAttr(s.nombre)}" style="padding: 0.45rem 0.6rem; border-radius: 6px; cursor: pointer; font-size: 0.85rem; display: flex; align-items: center; gap: 0.5rem;"><i class="fa-solid fa-user" style="color: var(--text-muted); font-size: 0.75rem;"></i><span>${escapeHtmlAttr(s.nombre)}</span></div>`).join("");
    container.querySelectorAll('.hist-name-option').forEach(el => {
        el.addEventListener('mouseenter', () => { el.style.background = 'var(--surface-3, rgba(99,102,241,0.12))'; });
        el.addEventListener('mouseleave', () => { el.style.background = 'transparent'; });
        el.addEventListener('click', () => { const picked = el.dataset.name; const input = document.getElementById('histNameInput'); if (input) input.value = picked; _historyNameModalState.selectedCanonical = picked; _updateHistoryNameLinkBadge(); });
    });
}

function _updateHistoryNameLinkBadge() {
    const badge = document.getElementById('histNameLinkBadge'); if (!badge) return;
    const input = document.getElementById('histNameInput'); const val = input ? input.value.trim() : "";
    const picked = _historyNameModalState.selectedCanonical;
    if (picked && val === picked) { badge.textContent = picked; badge.style.display = ''; }
    else { badge.style.display = 'none'; }
}

/* ── History Matrix ── */
async function openHistoryMatrix() {
    const existing = document.getElementById("history-matrix-modal"); if (existing) { existing.remove(); return; }
    try {
        const resp = await fetch(`${API_URL}/history`); if (!resp.ok) throw new Error(`Error ${resp.status}`);
        const history = await resp.json();
        const weeks = (history || []).slice(0, 8).reverse();
        if (weeks.length === 0) { alert("No hay historial disponible."); return; }
        const empSet = new Set();
        weeks.forEach(entry => {
            const sched = entry.schedule || {};
            Object.keys(sched).forEach(name => {
                const emp = window.employees ? window.employees.find(e => e.name === name) : null;
                if (!emp || emp.activo !== false && emp.activo !== 0) empSet.add(name);
            });
        });
        const empList = Array.from(empSet).sort();
        function classifyShift(shift) {
            if (!shift || shift === "OFF") return "off"; if (shift === "VAC") return "vac"; if (shift === "PERM") return "perm";
            if (shift === "N_22-05") return "nocturno";
            const hourMatch = shift.match(/[_](\d+)/); if (hourMatch) { const h = parseInt(hourMatch[1], 10); return h < 12 ? "matutino" : "vespertino"; }
            return "off";
        }
        const TYPE_CFG = { matutino: { fill: '#3b82f6', label: 'AM', name: 'Matutino', short: 'AM', cls: 'am' }, vespertino: { fill: '#f97316', label: 'PM', name: 'Vespertino', short: 'PM', cls: 'pm' }, nocturno: { fill: '#8b5cf6', label: 'N', name: 'Nocturno', short: 'N', cls: 'n' }, vac: { fill: '#f59e0b', label: 'V', name: 'Vacaciones', short: 'VAC', cls: 'vac' }, perm: { fill: '#ef4444', label: 'P', name: 'Permiso', short: 'PERM', cls: 'perm' } };
        const VISIBLE_TYPES = ["matutino", "vespertino", "nocturno", "vac", "perm"];
        function countDayTypes(days) { const counts = { matutino: 0, vespertino: 0, nocturno: 0, vac: 0, perm: 0, off: 0 }; Object.values(days).forEach(s => { const t = classifyShift(s); counts[t] = (counts[t] || 0) + 1; }); return counts; }
        function isConsistentWeek(counts) { const active = VISIBLE_TYPES.filter(t => (counts[t] || 0) > 0); return active.length === 1; }
        function buildBarData(days) { const counts = countDayTypes(days); const total = VISIBLE_TYPES.reduce((s, t) => s + (counts[t] || 0), 0) || 1; let segments = ''; const parts = []; VISIBLE_TYPES.forEach(t => { const c = counts[t] || 0; if (c === 0) return; const pct = (c / total) * 100; const cfg = TYPE_CFG[t]; segments += `<span style="width:${pct}%;background:${cfg.fill};opacity:0.45;"></span>`; parts.push(`${c} ${cfg.label}`); }); if (!segments) { segments = `<span style="width:100%;background:var(--border);opacity:0.2;"></span>`; parts.push('Sin datos'); } return { segments, breakdown: parts.join(' · ') }; }
        function renderCellContent(days) { const counts = countDayTypes(days); if (isConsistentWeek(counts)) { const type = VISIBLE_TYPES.find(t => counts[t] > 0) || 'off'; if (type === 'off') return `<span class="type-pill type-pill-off">—</span>`; const cfg = TYPE_CFG[type]; return `<span class="type-pill type-pill-${cfg.cls}">${cfg.short}</span>`; } const { segments, breakdown } = buildBarData(days); return `<div class="hist-bar" title="${breakdown}">${segments}</div>`; }
        function renderLibresCell(days) { const { segments, breakdown } = buildBarData(days); return `<div class="hist-libres-wrap"><span class="hist-libres-badge">LIBRES</span><div class="hist-libres-hover"><div class="hist-bar">${segments}</div><div class="hist-bar-legend">${breakdown}</div></div></div>`; }
        function findLibresForWeek(entry) { const meta = entry.metadata || {}; if (meta.libres_person) return meta.libres_person; const sched = entry.schedule || {}; let best = null, bestCount = 0; for (const [ename, days] of Object.entries(sched)) { if (!days || typeof days !== 'object') continue; let n = 0; for (const shift of Object.values(days)) { if (shift === 'N_22-05') n++; } if (n > 0 && n <= 4 && n > bestCount) { bestCount = n; best = ename; } } return best; }
        const libresByWeek = []; weeks.forEach((entry, wi) => { const person = findLibresForWeek(entry); if (person) libresByWeek.push({ weekIdx: wi, label: entry.name || entry.nombre || `Semana`, person }); });
        const libresPersonMap = {}; libresByWeek.forEach(lb => { libresPersonMap[lb.weekIdx] = lb.person; });
        const empCache = window.employees || [];
        function isFixedScheduleEmployee(name) { if (name === 'Refuerzo') return true; const emp = empCache.find(e => e.name === name); if (!emp || !emp.fixed_shifts) return false; const working = Object.values(emp.fixed_shifts).filter(s => s && s !== 'OFF' && s !== 'VAC' && s !== 'PERM'); return working.length >= 5; }
        let html = `<div class="modal-backdrop" id="history-matrix-backdrop"><div class="modal-dialog large" style="max-width: 900px;"><div class="modal-header-simple"><h3><i class="fa-solid fa-clock-rotate-left" style="color:var(--primary);"></i> Historial de Turnos</h3><button class="close-icon" onclick="closeHistoryMatrix()"><i class="fa-solid fa-xmark"></i></button></div><div class="modal-body-scroll" style="padding: 1.25rem 1.5rem;">`;
        if (libresByWeek.length > 0) { html += `<div style="background: var(--primary-subtle); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 0.85rem 1rem; margin-bottom: 1.25rem; display: flex; flex-wrap: wrap; align-items: center; gap: 0.75rem;"><span style="font-weight: 700; font-size: var(--fs-sm); color: var(--primary); white-space: nowrap;"><i class="fa-solid fa-people-arrows"></i> Persona de Libres:</span>`; libresByWeek.forEach(lb => { html += `<span style="background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 0.3rem 0.65rem; font-size: var(--fs-sm); white-space: nowrap;"><strong>${escapeHtml(lb.person)}</strong><span style="color: var(--text-muted); margin-left: 0.3rem;">(${escapeHtml(lb.label)})</span></span>`; }); html += `</div>`; }
        html += `<div style="overflow-x: auto; border: 1px solid var(--border); border-radius: var(--radius-md);"><table class="hist-matrix-table" style="width: 100%; border-collapse: collapse; font-size: var(--fs-sm);"><thead><tr><th class="sticky-emp" style="position: sticky; left: 0; z-index: 2; background: var(--bg-panel); padding: 0.6rem 0.75rem; text-align: left; font-weight: 700; color: var(--text-main); border-bottom: 2px solid var(--border); min-width: 130px;">Empleado</th>`;
        weeks.forEach(w => { const label = w.name || w.nombre || `Semana`; html += `<th class="week-col" style="padding: 0.6rem 0.5rem; text-align: center; font-weight: 600; color: var(--text-muted); border-bottom: 2px solid var(--border); font-size: var(--fs-xs); white-space: nowrap;">${escapeHtml(label)}</th>`; });
        html += `</tr></thead><tbody>`;
        empList.forEach(name => {
            const skipCell = isFixedScheduleEmployee(name);
            html += `<tr><td class="sticky-emp" style="position: sticky; left: 0; z-index: 1; background: var(--bg-panel); padding: 0.5rem 0.75rem; font-weight: 600; color: var(--text-main); border-bottom: 1px solid var(--border);"><span>${escapeHtml(name)}</span></td>`;
            weeks.forEach((entry, wi) => {
                if (skipCell) { html += `<td style="padding: 0.3rem 0.4rem; border-bottom: 1px solid var(--border);"></td>`; return; }
                const sched = entry.schedule || {}; const days = sched[name] || {}; const weekLibres = libresPersonMap[wi];
                if (weekLibres === name) { html += `<td style="padding: 0.3rem 0.4rem; border-bottom: 1px solid var(--border); vertical-align: middle; background: var(--success-subtle);">${renderLibresCell(days)}</td>`; return; }
                html += `<td style="padding: 0.3rem 0.4rem; border-bottom: 1px solid var(--border); vertical-align: middle;">${renderCellContent(days)}</td>`;
            });
            html += `</tr>`;
        });
        html += `</tbody></table></div>`;
        html += `<div style="display: flex; flex-wrap: wrap; gap: 1rem; margin-top: 1rem; padding: 0.75rem 1rem; background: var(--bg-app); border-radius: var(--radius-md); border: 1px solid var(--border); align-items: center;"><span style="font-size: var(--fs-xs); font-weight: 600; color: var(--text-muted); margin-right: 0.25rem;">Leyenda:</span><span style="display: inline-flex; align-items: center; gap: 0.35rem; font-size: var(--fs-xs); color: var(--text-muted);"><span style="width: 18px; height: 6px; border-radius: 3px; background: #3b82f6; opacity: 0.35;"></span> AM</span><span style="display: inline-flex; align-items: center; gap: 0.35rem; font-size: var(--fs-xs); color: var(--text-muted);"><span style="width: 18px; height: 6px; border-radius: 3px; background: #f97316; opacity: 0.35;"></span> PM</span><span style="display: inline-flex; align-items: center; gap: 0.35rem; font-size: var(--fs-xs); color: var(--text-muted);"><span style="width: 18px; height: 6px; border-radius: 3px; background: #8b5cf6; opacity: 0.35;"></span> N</span><span style="display: inline-flex; align-items: center; gap: 0.35rem; font-size: var(--fs-xs); color: var(--text-muted);"><span style="width: 18px; height: 6px; border-radius: 3px; background: #f59e0b; opacity: 0.35;"></span> VAC</span><span style="display: inline-flex; align-items: center; gap: 0.35rem; font-size: var(--fs-xs); color: var(--text-muted);"><span style="width: 18px; height: 6px; border-radius: 3px; background: #ef4444; opacity: 0.35;"></span> PERM</span><span style="display: inline-flex; align-items: center; gap: 0.35rem; font-size: var(--fs-xs); color: var(--text-muted); margin-left: 0.5rem;"><span style="display: inline-block; background: var(--success-subtle); color: var(--success); font-weight: 700; font-size: 0.55rem; padding: 1px 6px; border-radius: 4px; text-transform: uppercase;">Libres</span> Persona de Libres</span></div>`;
        html += `<p style="font-size: var(--fs-xs); color: var(--text-muted); text-align: center; margin-top: 0.75rem; margin-bottom: 0;"><i class="fa-solid fa-info-circle"></i> Los <strong>pills</strong> (AM / PM / N) indican semanas consistentes. La <strong>barra</strong> muestra la distribución cuando hay tipos mixtos.</p></div></div></div>`;
        const container = document.createElement("div"); container.id = "history-matrix-modal"; container.innerHTML = html; document.body.appendChild(container);
    } catch (err) { console.error("Error loading history matrix:", err); alert("Error al cargar historial: " + err.message); }
}
window.openHistoryMatrix = openHistoryMatrix;

function closeHistoryMatrix(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.getElementById("history-matrix-modal"); if (modal) modal.remove();
}
window.closeHistoryMatrix = closeHistoryMatrix;

/* ── Individual History ── */
async function fetchIndividualHistory(name, weeks = 6) {
    const resp = await fetch(`${API_URL}/history/individual/${encodeURIComponent(name)}?weeks=${weeks}`);
    if (!resp.ok) throw new Error(`Failed to fetch history for ${name}`);
    return resp.json();
}

function renderHistoryIndividual(name) {
    fetchIndividualHistory(name, 6).then(data => {
        const weeks = data.weeks || [];
        if (weeks.length === 0) { alert(`No hay historial para ${name}`); return; }
        const typeLabels = { matutino: "AM", vespertino: "PM", nocturno: "Noche", libre: "Libre" };
        const typeClasses = { matutino: "cell-dominant-am", vespertino: "cell-dominant-pm", nocturno: "cell-dominant-n", libre: "cell-dominant-off" };
        let html = `<div class="modal-overlay" onclick="closeIndividualHistory(event)"><div class="modal-content hist-individual-modal" onclick="event.stopPropagation()"><div class="modal-header"><h3>Historial Individual: ${escapeHtml(name)}</h3><button class="modal-close" onclick="closeIndividualHistory()">&times;</button></div><div class="modal-body"><table class="hist-individual-table"><thead><tr><th>Semana</th><th>Tipo Dominante</th><th>AM</th><th>PM</th><th>Noche</th><th>Libre</th></tr></thead><tbody>`;
        weeks.forEach(w => { const cls = typeClasses[w.dominant_type] || ""; const label = typeLabels[w.dominant_type] || w.dominant_type; html += `<tr><td>${escapeHtml(w.week_label)}</td><td class="${cls}">${label}</td><td>${w.counts?.matutino || 0}</td><td>${w.counts?.vespertino || 0}</td><td>${w.counts?.nocturno || 0}</td><td>${w.counts?.libre || 0}</td></tr>`; });
        html += `</tbody></table></div></div></div>`;
        const container = document.createElement("div"); container.id = "individual-history-modal"; container.innerHTML = html; document.body.appendChild(container);
    }).catch(err => { console.error("Error fetching individual history:", err); alert(`Error al cargar historial: ${err.message}`); });
}
window.renderHistoryIndividual = renderHistoryIndividual;

function closeIndividualHistory(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.getElementById("individual-history-modal"); if (modal) modal.remove();
}
window.closeIndividualHistory = closeIndividualHistory;

/* ── Task Label Helpers ── */
function _taskBaseAndSuffix(t) { const m = t.match(/^(.+?)\s*([↑↓]\s*(?:AM|PM))\s*$/i); if (m) return { base: m[1].trim(), suffix: m[2].trim() }; return { base: t.trim(), suffix: "" }; }
function _taskColorClass(base) { if (base === "Baños") return "task-banos"; if (base === "Tanques") return "task-tanques"; if (base.includes("Oficina")) return "task-oficina"; if (base === "Calibración") return "task-calibracion"; if (base === "Caños" || base === "Caños GLP") return "task-canos"; return "task-default"; }

function getTaskLabelHTML(tasks, name, d) {
    if (!tasks || !tasks[name] || !tasks[name][d]) return "";
    const t = tasks[name][d]; const { base, suffix } = _taskBaseAndSuffix(t); const colorClass = _taskColorClass(base);
    let label;
    if (base === "Baños") label = `Baños`;
    else if (base === "Tanques") label = `Tanques`;
    else if (base.includes("Oficina")) { let extra = base.replace("Oficina + Basureros + Baños", "").trim(); if (extra.startsWith("+")) extra = extra.substring(1).trim(); label = `Oficina+Basureros+Baños`; if (extra) label += ` <span class="task-extra">+${extra}</span>`; }
    else if (base === "Calibración") label = "Calibración";
    else if (base === "Caños") label = "Caños";
    else if (base === "Caños GLP") label = "Caños GLP";
    else label = base;
    if (suffix) label += ` <span class="task-suffix">${suffix}</span>`;
    const isHistory = tasks && tasks._is_history;
    const editableClass = isHistory ? " history-task-editable" : "";
    const onclick = isHistory ? `onclick="event.stopPropagation(); editHistoryTask('${escapeHtmlAttr(name)}', '${escapeHtmlAttr(d)}', ${tasks._history_index})"` : "";
    return `<span class="shift-task-label ${colorClass}${editableClass}" ${onclick}>${label}</span>`;
}
window.getTaskLabelHTML = getTaskLabelHTML;

async function editHistoryTask(empName, day, historyIndex) {
    const entry = historyEntriesCache[historyIndex]; if (!entry) return;
    const currentTasks = entry.daily_tasks || {}; const currentTask = (currentTasks[empName] || {})[day];
    const options = [
        { id: "Tanques", label: "Tanques", icon: "fa-faucet", color: "task-tanques" }, { id: "Baños", label: "Baños", icon: "fa-restroom", color: "task-banos" },
        { id: "Oficina + Basureros + Baños", label: "Oficina + Basureros + Baños", icon: "fa-broom", color: "task-oficina" }, { id: "Calibración", label: "Calibración", icon: "fa-sliders", color: "task-calibracion" },
        { id: "Caños", label: "Caños", icon: "fa-wrench", color: "task-canos" }, { id: "Caños GLP", label: "Caños GLP", icon: "fa-fire", color: "task-canos" },
        { id: "None", label: "Quitar Tarea", icon: "fa-xmark", color: "" }
    ];
    const selection = await showTaskSelectorModal(empName, day, currentTask, options);
    if (selection === undefined) return;
    const taskVal = selection === "None" ? null : selection;
    try {
        const res = await fetch(`/api/history/entry/${entry.db_id}/task?employee_name=${encodeURIComponent(empName)}&day=${encodeURIComponent(day)}&task=${encodeURIComponent(taskVal || "")}`, { method: 'PATCH' });
        if (!res.ok) throw new Error("Error al guardar");
        if (!entry.daily_tasks) entry.daily_tasks = {}; if (!entry.daily_tasks[empName]) entry.daily_tasks[empName] = {};
        entry.daily_tasks[empName][day] = taskVal;
        renderHistoryEntryTable(historyIndex); setStatusMessage("Tarea actualizada correctamente", "success");
    } catch (e) { console.error(e); setStatusMessage("Error al actualizar tarea", "error"); }
}
window.editHistoryTask = editHistoryTask;

function showTaskSelectorModal(empName, day, currentTask, options) {
    return new Promise((resolve) => {
        const modal = document.getElementById("textEditModal");
        const title = document.getElementById("textEditTitle");
        const body = document.querySelector("#textEditModal .modal-body-scroll");
        const footer = document.querySelector("#textEditModal .modal-actions-footer");
        const originalBodyContent = body.innerHTML; const originalFooterContent = footer.innerHTML;
        title.textContent = `Asignar Tarea: ${empName} (${day})`;
        body.innerHTML = `<div style="display: flex; flex-direction: column; gap: 8px;">${options.map(opt => `<div class="task-option-item ${currentTask === opt.id ? 'selected' : ''}" onclick="window._resolveTaskSelection('${opt.id}')"><div class="task-option-icon ${opt.color}"><i class="fa-solid ${opt.icon}"></i></div><div style="flex: 1;"><div style="font-weight: 700;">${opt.label}</div></div>${currentTask === opt.id ? '<i class="fa-solid fa-check" style="color: var(--primary);"></i>' : ''}</div>`).join('')}</div>`;
        footer.innerHTML = `<button class="btn-text" onclick="window._resolveTaskSelection(undefined)">Cancelar</button>`;
        window._resolveTaskSelection = (val) => { body.innerHTML = originalBodyContent; footer.innerHTML = originalFooterContent; modal.classList.add("hidden"); resolve(val); };
        modal.classList.remove("hidden");
    });
}

/* ── Param Card Toggles ── */
function toggleParamCard(header) { const card = header.parentElement; card.classList.toggle('expanded'); }
window.toggleParamCard = toggleParamCard;

function toggleParamGroup(header) { const group = header.parentElement; group.classList.toggle('collapsed'); }
window.toggleParamGroup = toggleParamGroup;

/* ── Acerca de Modal ── */
function openAcercaDeModal() { const modal = document.getElementById("acercaDeModal"); if (modal) { modal.classList.remove("hidden"); document.body.style.overflow = "hidden"; } }
window.openAcercaDeModal = openAcercaDeModal;

function closeAcercaDeModal(event) {
    if (!event || event.target === event.currentTarget || event.target.closest('button[onclick*="closeAcercaDeModal"]')) {
        const modal = document.getElementById("acercaDeModal"); if (modal) { modal.classList.add("hidden"); document.body.style.overflow = ""; }
    }
}
window.closeAcercaDeModal = closeAcercaDeModal;

document.addEventListener("keydown", function(e) {
    if (e.key === "Escape") { const modal = document.getElementById("acercaDeModal"); if (modal && !modal.classList.contains("hidden")) closeAcercaDeModal(e); }
});
