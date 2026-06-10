// ========================================================================
// Chronos — Manual Schedule Editor
// Editor manual de horarios con tabla interactiva
// ========================================================================

const _manualSchedState = {
    weekDates: {},
    specialDays: {},
    holidayDays: {},
    holidayMode: false,
    hoursVisible: true,
};

function _manualSchedSetStatus(text, kind = "info") {
    const el = document.getElementById("manualSchedStatus");
    if (!el) return;
    const icons = { info: "fa-circle-info", success: "fa-check", error: "fa-circle-xmark", warn: "fa-triangle-exclamation" };
    const icon = icons[kind] || icons.info;
    el.innerHTML = `<i class="fa-solid ${icon}"></i> ${text}`;
    el.className = `manual-sched-status ${kind}`;
}

function _manualSchedDefaultFridayIso() {
    const d = new Date();
    const diff = (5 - d.getDay() + 7) % 7;
    d.setDate(d.getDate() + diff);
    const y = d.getFullYear(); const m = String(d.getMonth() + 1).padStart(2, "0"); const dd = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${dd}`;
}

function _manualSchedRefreshHeader() {
    const fridayIso = document.getElementById("manualSchedFriday")?.value || "";
    if (fridayIso) { _manualSchedState.weekDates = _fridayToWeekDates(fridayIso); } else { _manualSchedState.weekDates = {}; }
    const headerRow = document.getElementById("manualSchedHeaderRow"); if (!headerRow) return;
    headerRow.innerHTML = `<th style="width:140px;">Empleado</th>`;
    DAYS.forEach(day => {
        const th = document.createElement("th");
        const dateLabel = _manualSchedState.weekDates[day] || "";
        const isClosed = _manualSchedState.specialDays[day] === "closed";
        const holiday = _manualSchedState.holidayDays[day];
        th.innerHTML = `<div>${day}${dateLabel ? `<br><small style="font-weight:400;color:var(--text-muted);font-size:0.68rem;">${dateLabel}</small>` : ""}</div>${isClosed ? '<div style="font-size:0.6rem;color:var(--error);">CERRADO</div>' : ''}${holiday ? `<div style="font-size:0.6rem;color:#f59e0b;">★ ${escapeHtmlAttr(holiday.name)}</div>` : ''}`;
        th.classList.toggle("manual-sched-day-clickable", _manualSchedState.holidayMode);
        if (_manualSchedState.holidayMode) { th.onclick = () => _manualSchedToggleDayState(day); }
        headerRow.appendChild(th);
    });
    const hoursTh = document.createElement("th"); hoursTh.className = "ms-col-hours"; hoursTh.textContent = "Horas"; headerRow.appendChild(hoursTh);
}

function manualSchedRefreshHeaderDates() { _manualSchedRefreshHeader(); }
window.manualSchedRefreshHeaderDates = manualSchedRefreshHeaderDates;

function _manualSchedToggleDayState(day) {
    const isClosed = _manualSchedState.specialDays[day] === "closed";
    const holiday = _manualSchedState.holidayDays[day];
    if (!isClosed && !holiday) { _manualSchedState.specialDays[day] = "closed"; }
    else if (isClosed) { delete _manualSchedState.specialDays[day]; _manualSchedState.holidayDays[day] = { name: "Feriado" }; }
    else { delete _manualSchedState.specialDays[day]; delete _manualSchedState.holidayDays[day]; }
    _manualSchedRefreshHeader();
}

function manualSchedToggleHolidayMode() {
    _manualSchedState.holidayMode = !_manualSchedState.holidayMode;
    const btn = document.getElementById("manualSchedHolidayBtn");
    if (btn) btn.classList.toggle("is-active", _manualSchedState.holidayMode);
    _manualSchedRefreshHeader();
    _manualSchedSetStatus(_manualSchedState.holidayMode ? "Modo feriado: clic en día para marcar." : "Modo feriado desactivado.", "info");
}
window.manualSchedToggleHolidayMode = manualSchedToggleHolidayMode;

function manualSchedToggleHours() {
    _manualSchedState.hoursVisible = !_manualSchedState.hoursVisible;
    document.querySelectorAll("#manualSchedTable .col-hours, #manualSchedTable .ms-col-hours").forEach(el => { el.classList.toggle("hidden-col", !_manualSchedState.hoursVisible); });
    const btn = document.getElementById("manualSchedHoursBtn"); if (btn) btn.classList.toggle("is-active", _manualSchedState.hoursVisible);
}
window.manualSchedToggleHours = manualSchedToggleHours;

function _manualSchedAvatarInitials(name) {
    if (!name) return "??";
    const parts = name.trim().split(/\s+/);
    return parts.length > 1 ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase() : name.substring(0, 2).toUpperCase();
}

function _manualSchedUpdateRowsCount() {
    const tbody = document.getElementById("manualSchedTbody"); const chip = document.getElementById("manualSchedStatRows");
    if (!chip) return; const count = tbody ? tbody.querySelectorAll("tr").length : 0; chip.textContent = `${count} fila${count !== 1 ? 's' : ''}`;
}

function _manualSchedBuildRow(name, isEditable) {
    const tr = document.createElement("tr");
    const nameTd = document.createElement("td");
    if (isEditable) {
        const inp = document.createElement("input"); inp.type = "text"; inp.placeholder = "Nombre"; inp.className = "manual-sched-name-input";
        inp.value = name || ""; inp.style.cssText = "width:100%;padding:4px 8px;border:1px solid var(--border);border-radius:6px;background:var(--surface-2);color:var(--text-main);font-size:0.82rem;";
        nameTd.appendChild(inp);
    } else {
        const avatar = document.createElement("span"); avatar.className = "ms-avatar"; avatar.textContent = _manualSchedAvatarInitials(name);
        avatar.style.cssText = "display:inline-flex;width:28px;height:28px;border-radius:50%;background:var(--primary);color:#fff;align-items:center;justify-content:center;font-size:0.7rem;font-weight:700;margin-right:6px;";
        nameTd.innerHTML = ""; nameTd.appendChild(avatar); nameTd.appendChild(document.createTextNode(name));
        nameTd.style.cssText = "font-weight:600;font-size:0.85rem;display:flex;align-items:center;";
    }
    tr.appendChild(nameTd);
    DAYS.forEach(day => {
        const td = document.createElement("td");
        const isClosed = _manualSchedState.specialDays[day] === "closed";
        const holiday = _manualSchedState.holidayDays[day];
        if (isClosed) { td.innerHTML = `<div style="text-align:center;color:var(--error);font-size:0.75rem;">Cerrado</div>`; }
        else if (holiday) { td.innerHTML = `<div style="text-align:center;color:#f59e0b;font-size:0.75rem;">★ Feriado</div>`; }
        else {
            const sel = document.createElement("select"); sel.className = "manual-sched-shift-sel"; sel.dataset.day = day;
            sel.style.cssText = "width:100%;padding:4px 6px;border:1px solid var(--border);border-radius:6px;background:var(--surface-2);color:var(--text-main);font-size:0.75rem;";
            const opts = [{ code: "OFF", label: "Libre" }, { code: "VAC", label: "Vacaciones" }, { code: "PERM", label: "Permiso" }];
            if (SHIFT_OPTIONS && SHIFT_OPTIONS.length) opts.push(...SHIFT_OPTIONS);
            opts.forEach(o => { const opt = document.createElement("option"); opt.value = o.code; opt.textContent = o.label; if (o.code === "OFF") opt.selected = true; sel.appendChild(opt); });
            td.appendChild(sel);
        }
        tr.appendChild(td);
    });
    const hoursTd = document.createElement("td"); hoursTd.className = "ms-col-hours"; hoursTd.textContent = "—"; hoursTd.style.cssText = "text-align:center;font-size:0.8rem;color:var(--text-muted);";
    if (!_manualSchedState.hoursVisible) hoursTd.classList.add("hidden-col");
    tr.appendChild(hoursTd);
    const delTd = document.createElement("td");
    const delBtn = document.createElement("button"); delBtn.type = "button"; delBtn.innerHTML = '<i class="fa-solid fa-xmark"></i>'; delBtn.title = "Eliminar fila";
    delBtn.style.cssText = "background:none;border:none;color:var(--error);cursor:pointer;font-size:0.85rem;padding:2px 6px;border-radius:4px;";
    delBtn.addEventListener("click", () => { tr.remove(); _manualSchedUpdateRowsCount(); });
    delTd.appendChild(delBtn); tr.appendChild(delTd);
    _manualSchedUpdateRowsCount();
    return tr;
}

async function _manualSchedFetchActiveEmployees() {
    try {
        const res = await fetch(`${API_URL}/employees`);
        if (!res.ok) return [];
        const emps = await res.json();
        return emps.filter(e => e.activo !== false && e.activo !== 0 && e.incluir_en_horario !== false).map(e => e.name);
    } catch (e) { console.error("Error fetching employees:", e); return []; }
}

window.manualSchedReloadEmployees = async function () {
    const tbody = document.getElementById("manualSchedTbody"); if (!tbody) return; tbody.innerHTML = "";
    const names = await _manualSchedFetchActiveEmployees();
    if (!names.length) { _manualSchedAddRow(); _manualSchedSetStatus("No hay empleados activos incluidos en horario. Se agregó una fila vacía.", "warn"); _manualSchedUpdateRowsCount(); return; }
    names.forEach(n => tbody.appendChild(_manualSchedBuildRow(n, false)));
    _manualSchedSetStatus(`${names.length} empleados cargados.`, "info"); _manualSchedUpdateRowsCount();
};

function _manualSchedAddRow() {
    const tbody = document.getElementById("manualSchedTbody"); if (!tbody) return;
    const tr = _manualSchedBuildRow("", true); tbody.appendChild(tr); _manualSchedUpdateRowsCount();
}
window.manualSchedAddRow = _manualSchedAddRow;

window.openManualScheduleOverlay = async function () {
    const overlay = document.getElementById("manualScheduleOverlay"); if (overlay) overlay.classList.remove("hidden");
    const fridayInput = document.getElementById('manualSchedFriday');
    if (fridayInput) fridayInput.value = _manualSchedDefaultFridayIso();
    const nameInput = document.getElementById('manualSchedName'); if (nameInput) nameInput.value = "";
    _manualSchedState.specialDays = {}; _manualSchedState.holidayDays = {}; _manualSchedState.holidayMode = false;
    _manualSchedRefreshHeader(); await window.manualSchedReloadEmployees();
};

function _manualSchedReadSchedule() {
    const schedule = {}; const dailyTasks = {};
    const tbody = document.getElementById("manualSchedTbody"); if (!tbody) return { schedule, dailyTasks };
    tbody.querySelectorAll("tr").forEach(tr => {
        const nameInp = tr.querySelector(".manual-sched-name-input");
        let name = nameInp ? nameInp.value.trim() : tr.querySelector("td")?.textContent?.trim() || "";
        if (!name) return;
        schedule[name] = {}; dailyTasks[name] = {};
        tr.querySelectorAll(".manual-sched-shift-sel").forEach(sel => {
            const day = sel.dataset.day; schedule[name][day] = sel.value;
        });
    });
    return { schedule, dailyTasks };
}

window.manualSchedValidate = async function () {
    const { schedule } = _manualSchedReadSchedule();
    if (Object.keys(schedule).length === 0) { _manualSchedSetStatus("Agregá al menos una fila con turnos para validar.", "warn"); return; }
    try {
        validationRules = await fetchValidationRules({ ...(_manualSchedState.specialDays || {}) });
        _manualSchedSetStatus("Validación corrida. Mirá el panel emergente para detalles.", "success");
    } catch (err) { _manualSchedSetStatus("Error al validar: " + (err.message || err), "error"); }
};

window.manualSchedSave = async function () {
    const name = (document.getElementById('manualSchedName')?.value || "").trim();
    const fridayIso = document.getElementById('manualSchedFriday')?.value || "";
    if (!name) { _manualSchedSetStatus("Ingresá un nombre para la semana.", "error"); return; }
    if (!fridayIso) { _manualSchedSetStatus("Seleccioná la fecha del viernes.", "error"); return; }
    const { schedule, dailyTasks } = _manualSchedReadSchedule();
    if (Object.keys(schedule).length === 0) { _manualSchedSetStatus("Agregá al menos una fila con un nombre antes de guardar.", "error"); return; }
    const weekDates = _fridayToWeekDates(fridayIso);
    const entry = { name, schedule, daily_tasks: dailyTasks, week_dates: weekDates, special_days: { ..._manualSchedState.specialDays }, holiday_days: { ..._manualSchedState.holidayDays }, timestamp: new Date().toISOString() };
    _manualSchedSetStatus("Guardando...", "info");
    try {
        const res = await fetch('/api/history', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(entry) });
        if (!res.ok) throw new Error("Error al guardar");
        _manualSchedSetStatus(`Guardado al historial: "${name}".`, "success");
        if (typeof loadHistory === "function") await loadHistory(true);
    } catch (err) { _manualSchedSetStatus("Error al guardar: " + (err.message || err), "error"); }
};
