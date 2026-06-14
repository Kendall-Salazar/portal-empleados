// ========================================================================
// Chronos — Partial Generator
// Generador de horario parcial para semanas existentes
// ========================================================================

const PartialGenerator = {
    baseEntry: null,
    dayLocked: {},
    departed: [],
    offClassifications: [],
    lastResult: null,
    _searchCache: [],

    async searchHistory(query) {
        const resultsEl = document.getElementById("partialSearchResults"); if (!resultsEl) return;
        try {
            const history = await fetch("/api/history").then(r => r.json());
            this._searchCache = history.filter(h => (h.name || "").toLowerCase().includes((query || "").toLowerCase())).slice(0, 12);
            if (this._searchCache.length === 0) { resultsEl.innerHTML = '<p style="padding:0.75rem 1rem; font-size:0.82rem; color:var(--text-muted); margin:0;">Sin resultados.</p>'; resultsEl.style.display = "block"; return; }
            resultsEl.innerHTML = this._searchCache.map((h, idx) => {
                const weekDates = h.week_dates || {};
                const range = (weekDates["Vie"] && weekDates["Jue"]) ? `Vie ${weekDates["Vie"]} – Jue ${weekDates["Jue"]}` : (h.timestamp ? h.timestamp.slice(0, 10) : "");
                const isPartial = (h.name || "").includes("(parcial)");
                return `<div class="partial-search-item" onclick="PartialGenerator._selectFromCache(${idx})" style="padding: 0.65rem 1rem; cursor: pointer; border-bottom: 1px solid var(--border-color); transition: background 0.15s;" onmouseenter="this.style.background='var(--surface-2)'; this.style.borderLeft='3px solid #f97316'; this.style.paddingLeft='calc(1rem - 3px)';" onmouseleave="this.style.background=''; this.style.borderLeft=''; this.style.paddingLeft='1rem';"><div style="display:flex; align-items:center; gap:0.5rem;"><i class="fa-solid fa-calendar-week" style="color:#f97316; font-size:0.8rem;"></i><span style="font-weight:600; font-size:0.88rem; color:var(--text-main);">${h.name || "(sin nombre)"}</span>${isPartial ? '<span style="background:rgba(249,115,22,0.12);color:#f97316;font-size:0.67rem;padding:1px 5px;border-radius:4px;border:1px solid rgba(249,115,22,0.25);">PARCIAL</span>' : ""}</div><div style="font-size:0.72rem; color:var(--text-muted); margin-top:2px;">${range}</div></div>`;
            }).join("");
            resultsEl.style.display = "block";
        } catch (e) { console.error("[PartialGenerator] searchHistory error:", e); resultsEl.innerHTML = '<p style="padding:0.75rem 1rem; font-size:0.82rem; color:#ef4444; margin:0;">Error al cargar el historial.</p>'; resultsEl.style.display = "block"; }
    },

    _selectFromCache(idx) {
        const entry = this._searchCache[idx];
        if (!entry) { console.error("[PartialGenerator] _selectFromCache: idx", idx, "no encontrado en caché"); return; }
        this.selectBase(entry);
    },

    selectBase(entry) {
        if (!entry || typeof entry !== "object") { console.error("[PartialGenerator] selectBase: entry inválido", entry); return; }
        this.baseEntry = entry;
        const resultsEl = document.getElementById("partialSearchResults"); if (resultsEl) resultsEl.style.display = "none";
        const input = document.getElementById("partialSearchInput"); if (input) input.value = this.baseEntry.name || "";
        const selectedEl = document.getElementById("partialSelectedBase"); if (selectedEl) selectedEl.style.display = "flex";
        const nameEl = document.getElementById("partialBaseName"); if (nameEl) nameEl.textContent = this.baseEntry.name || "(sin nombre)";
        const wd = this.baseEntry.week_dates || {};
        const rangeEl = document.getElementById("partialBaseRange"); if (rangeEl) rangeEl.textContent = (wd["Vie"] && wd["Jue"]) ? `Vie ${wd["Vie"]} – Jue ${wd["Jue"]}` : "Sin fechas";
        this._detectLockedDays();
        this.departed = []; this._renderDepartedList(); this._buildOffClassifications(); this._renderOffTable(); this._updateStatusBadge();
    },

    clearBase() {
        this.baseEntry = null; this.dayLocked = {}; this.departed = []; this.offClassifications = []; this.lastResult = null;
        const input = document.getElementById("partialSearchInput"); if (input) input.value = "";
        const selectedEl = document.getElementById("partialSelectedBase"); if (selectedEl) selectedEl.style.display = "none";
        const resultsEl = document.getElementById("partialSearchResults"); if (resultsEl) resultsEl.style.display = "none";
        document.getElementById("partialDaySelector").innerHTML = '<p class="helper-text-sm" style="color:var(--text-muted);">Seleccioná un horario base primero.</p>';
        document.getElementById("partialOffTable").innerHTML = '<p class="helper-text-sm" style="color:var(--text-muted);">Los libres aparecerán al seleccionar el horario base y configurar los días activos.</p>';
        document.getElementById("partialPreviewZone").style.display = "none"; this._updateStatusBadge();
    },

    _detectLockedDays() {
        const weekDates = (this.baseEntry || {}).week_dates || {};
        const today = new Date(); today.setHours(0, 0, 0, 0);
        this.dayLocked = {};
        DAYS.forEach(day => {
            const dateStr = weekDates[day];
            if (!dateStr) { this.dayLocked[day] = false; return; }
            let dayDate;
            if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) { dayDate = new Date(dateStr + "T00:00:00"); }
            else {
                const parts = dateStr.split("/");
                if (parts.length === 3) { dayDate = new Date(`${parts[2]}-${parts[1].padStart(2,"0")}-${parts[0].padStart(2,"0")}T00:00:00`); }
                else { this.dayLocked[day] = false; return; }
            }
            this.dayLocked[day] = dayDate < today;
        });
        this._renderDaySelector();
    },

    _renderDaySelector() {
        const container = document.getElementById("partialDaySelector"); if (!container) return;
        const weekDates = (this.baseEntry || {}).week_dates || {};
        container.innerHTML = DAYS.map(day => {
            const locked = this.dayLocked[day]; const dateStr = weekDates[day] || "";
            let shortDate = "";
            if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) { const parts = dateStr.split("-"); shortDate = `${parts[2]}/${parts[1]}`; }
            else if (/^\d{2}\/\d{2}\/\d{4}$/.test(dateStr)) { shortDate = dateStr.slice(0, 5); }
            const bg = locked ? "rgba(100,116,139,0.12)" : "rgba(16,185,129,0.1)";
            const border = locked ? "1px solid rgba(100,116,139,0.25)" : "1px solid rgba(16,185,129,0.3)";
            const color = locked ? "var(--text-muted)" : "#10b981";
            const icon = locked ? "fa-lock" : "fa-unlock"; const label = locked ? "Pasado" : "Activo";
            return `<div onclick="PartialGenerator.toggleDayLock('${day}')" title="${locked ? 'Click para marcar como activo (regenerar)' : 'Click para marcar como pasado (bloquear)'}" style="padding: 0.55rem 0.85rem; border-radius: 10px; background: ${bg}; border: ${border}; cursor: pointer; display: flex; flex-direction: column; align-items: center; gap: 0.2rem; min-width: 68px; transition: all 0.2s;"><span style="font-weight:700; font-size:0.9rem; color:${color};">${day}</span>${shortDate ? `<span style="font-size:0.68rem; color:var(--text-muted);">${shortDate}</span>` : ""}<span style="font-size:0.65rem; color:${color}; display:flex; align-items:center; gap:2px;"><i class="fa-solid ${icon}" style="font-size:0.6rem;"></i> ${label}</span></div>`;
        }).join("");
    },

    toggleDayLock(day) { this.dayLocked[day] = !this.dayLocked[day]; this._renderDaySelector(); this._buildOffClassifications(); this._renderOffTable(); },

    addDeparted() {
        const empNames = this.baseEntry ? Object.keys(this.baseEntry.schedule || {}) : employees.map(e => e.name);
        const usedNames = new Set(this.departed.map(d => d.name));
        const available = empNames.filter(n => !usedNames.has(n));
        if (available.length === 0) { setStatusMessage("Todos los empleados del horario ya están en la lista", "info"); return; }
        const activeDays = DAYS.filter(d => !this.dayLocked[d]);
        this.departed.push({ name: available[0], last_working_day: activeDays.length > 0 ? activeDays[activeDays.length - 1] : DAYS[DAYS.length - 1] });
        this._renderDepartedList(); this._buildOffClassifications(); this._renderOffTable();
    },

    updateDeparted(index, field, value) { if (this.departed[index]) { this.departed[index][field] = value; this._buildOffClassifications(); this._renderOffTable(); } },

    removeDeparted(index) { this.departed.splice(index, 1); this._renderDepartedList(); this._buildOffClassifications(); this._renderOffTable(); },

    _renderDepartedList() {
        const container = document.getElementById("partialDepartedList"); const emptyMsg = document.getElementById("partialDepartedEmpty");
        if (!container) return;
        const empNames = this.baseEntry ? Object.keys(this.baseEntry.schedule || {}) : employees.map(e => e.name);
        if (this.departed.length === 0) { if (emptyMsg) emptyMsg.style.display = ""; container.querySelectorAll(".partial-departed-row").forEach(el => el.remove()); return; }
        if (emptyMsg) emptyMsg.style.display = "none";
        container.querySelectorAll(".partial-departed-row").forEach(el => el.remove());
        this.departed.forEach((dep, idx) => {
            const row = document.createElement("div"); row.className = "partial-departed-row";
            row.style.cssText = "display:flex; align-items:center; gap:0.5rem; padding:0.6rem 0.75rem; background:rgba(239,68,68,0.06); border:1px solid rgba(239,68,68,0.2); border-radius:10px;";
            const empOptions = empNames.map(n => `<option value="${n}" ${n === dep.name ? "selected" : ""}>${n}</option>`).join("");
            const dayOptions = DAYS.map(d => `<option value="${d}" ${d === dep.last_working_day ? "selected" : ""}>${d}</option>`).join("");
            row.innerHTML = `<i class="fa-solid fa-user-slash" style="color:#ef4444; font-size:0.85rem; flex-shrink:0;"></i><select onchange="PartialGenerator.updateDeparted(${idx},'name',this.value)" style="flex:1; padding:0.4rem 0.6rem; border-radius:8px; border:1px solid var(--border-color); background:var(--surface-2); color:var(--text-main); font-size:0.85rem;">${empOptions}</select><span style="font-size:0.78rem; color:var(--text-muted); flex-shrink:0; white-space:nowrap;">Último día:</span><select onchange="PartialGenerator.updateDeparted(${idx},'last_working_day',this.value)" style="padding:0.4rem 0.6rem; border-radius:8px; border:1px solid var(--border-color); background:var(--surface-2); color:var(--text-main); font-size:0.85rem;">${dayOptions}</select><button onclick="PartialGenerator.removeDeparted(${idx})" style="background:none; border:none; color:#ef4444; cursor:pointer; padding:0.3rem; font-size:0.85rem;" title="Quitar"><i class="fa-solid fa-xmark"></i></button>`;
            container.appendChild(row);
        });
    },

    _buildOffClassifications() {
        if (!this.baseEntry) { this.offClassifications = []; return; }
        const schedule = this.baseEntry.schedule || {};
        const activeDays = DAYS.filter(d => !this.dayLocked[d]);
        const departedNames = new Set(this.departed.map(d => d.name));
        const existingMap = new Map(this.offClassifications.map(c => [`${c.employee}|${c.day}`, c.fixed]));
        this.offClassifications = [];
        for (const [emp, days] of Object.entries(schedule)) {
            if (departedNames.has(emp)) continue;
            for (const day of activeDays) {
                const shift = days[day];
                if (shift === "OFF" || shift === "VAC" || shift === "PERM") {
                    const key = `${emp}|${day}`;
                    this.offClassifications.push({ employee: emp, day, fixed: existingMap.has(key) ? existingMap.get(key) : false });
                }
            }
        }
    },

    toggleOff(index) { if (this.offClassifications[index]) { this.offClassifications[index].fixed = !this.offClassifications[index].fixed; this._renderOffTable(); } },

    _renderOffTable() {
        const container = document.getElementById("partialOffTable"); if (!container) return;
        if (this.offClassifications.length === 0) { container.innerHTML = '<p class="helper-text-sm" style="color:var(--text-muted); margin:0;">Sin libres en los días activos del horario base.</p>'; return; }
        const rows = this.offClassifications.map((clf, idx) => {
            const isFixed = clf.fixed; const shiftLabel = (this.baseEntry?.schedule?.[clf.employee]?.[clf.day]) || "OFF";
            return `<tr><td style="padding:0.5rem 0.75rem; font-weight:500; color:var(--text-main); font-size:0.85rem;">${clf.employee}</td><td style="padding:0.5rem 0.75rem; font-size:0.85rem; color:var(--text-muted);">${clf.day}</td><td style="padding:0.5rem 0.75rem;"><span style="background:rgba(100,116,139,0.1); color:var(--text-muted); font-size:0.75rem; padding:2px 8px; border-radius:6px; font-weight:600;">${shiftLabel}</span></td><td style="padding:0.5rem 0.75rem;"><div style="display:flex; gap:0.4rem;"><button onclick="PartialGenerator.toggleOff(${idx})" style="padding: 0.3rem 0.65rem; font-size: 0.75rem; border-radius: 7px; border: 1px solid ${isFixed ? "rgba(239,68,68,0.4)" : "var(--border-color)"}; background: ${isFixed ? "rgba(239,68,68,0.08)" : "transparent"}; color: ${isFixed ? "#ef4444" : "var(--text-muted)"}; cursor: pointer; font-weight: 600; display: flex; align-items: center; gap: 0.3rem;" title="${isFixed ? "Clic para marcar como flexible" : "Clic para fijar este libre"}"><i class="fa-solid ${isFixed ? "fa-lock" : "fa-unlock"}" style="font-size:0.65rem;"></i>${isFixed ? "Fijo" : "Flexible"}</button></div></td></tr>`;
        }).join("");
        container.innerHTML = `<table style="width:100%; border-collapse:collapse;"><thead><tr style="border-bottom:1px solid var(--border-color);"><th style="padding:0.4rem 0.75rem; text-align:left; font-size:0.78rem; color:var(--text-muted); font-weight:600;">Colaborador</th><th style="padding:0.4rem 0.75rem; text-align:left; font-size:0.78rem; color:var(--text-muted); font-weight:600;">Día</th><th style="padding:0.4rem 0.75rem; text-align:left; font-size:0.78rem; color:var(--text-muted); font-weight:600;">Tipo</th><th style="padding:0.4rem 0.75rem; text-align:left; font-size:0.78rem; color:var(--text-muted); font-weight:600;">Clasificación</th></tr></thead><tbody>${rows}</tbody></table>`;
    },

    async generate() {
        if (!this.baseEntry) { setStatusMessage("Seleccioná un horario base primero", "error"); return; }
        const lockedDays = DAYS.filter(d => this.dayLocked[d]); const activeDays = DAYS.filter(d => !this.dayLocked[d]);
        if (activeDays.length === 0) { setStatusMessage("No hay días activos — desbloqueá al menos uno", "error"); return; }
        const weekDates = this.baseEntry.week_dates || {};
        let targetWeekStart = null;
        const vieDate = weekDates["Vie"];
        if (vieDate) {
            if (/^\d{4}-\d{2}-\d{2}$/.test(vieDate)) { targetWeekStart = vieDate; }
            else if (/^\d{2}\/\d{2}\/\d{4}$/.test(vieDate)) { const parts = vieDate.split("/"); targetWeekStart = `${parts[2]}-${parts[1].padStart(2,"0")}-${parts[0].padStart(2,"0")}`; }
        }
        const payload = { base_history_db_id: this.baseEntry.db_id, config: getCurrentConfig(), target_week_start: targetWeekStart, special_days: {}, locked_days: lockedDays, departed_employees: this.departed, off_classifications: this.offClassifications };
        const btn = document.getElementById("btnGeneratePartial");
        if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Generando...'; }
        try {
            const result = await fetch("/api/solve-partial", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }).then(r => r.json());
            if (result.status !== "Success") { const detail = result.status || result.detail || "Error desconocido"; setStatusMessage(`Error: ${detail}`, "error", 5000); return; }
            this.lastResult = result; this._renderPreview(result); setStatusMessage("Horario parcial generado ✓", "success");
        } catch (e) { console.error("[PartialGenerator] generate error:", e); setStatusMessage("Error al conectar con el servidor", "error"); }
        finally { if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> <span>Generar Horario Parcial</span>'; } }
    },

    _renderPreview(result) {
        const previewZone = document.getElementById("partialPreviewZone"); const tbody = document.getElementById("partialScheduleTbody");
        if (!previewZone || !tbody) return;
        const schedule = result.schedule || {}; const meta = result.metadata || {};
        const lockedDays = new Set(meta.locked_days || []);
        const departedNames = new Set((meta.departed_employees || []).map(d => d.name));
        const weekDates = meta.week_dates || {};
        DAYS.forEach(day => {
            const th = document.getElementById(`partial-th-${day}`); if (!th) return;
            const dateStr = weekDates[day] || ""; let shortDate = "";
            if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) { const p = dateStr.split("-"); shortDate = `${p[2]}/${p[1]}`; }
            else if (/^\d{2}\/\d{2}\/\d{4}$/.test(dateStr)) { shortDate = dateStr.slice(0, 5); }
            th.innerHTML = `${day}${shortDate ? `<br><small style="font-weight:400;color:var(--text-muted);font-size:0.68rem;">${shortDate}</small>` : ""}`;
            if (lockedDays.has(day)) { th.style.background = "rgba(100,116,139,0.08)"; th.style.color = "var(--text-muted)"; }
            else { th.style.background = "rgba(16,185,129,0.06)"; th.style.color = "#10b981"; }
        });
        const empNames = Object.keys(schedule);
        tbody.innerHTML = empNames.map(emp => {
            const isDeparted = departedNames.has(emp); const empSchedule = schedule[emp] || {};
            const cells = DAYS.map(day => {
                const shift = empSchedule[day]; const isLocked = lockedDays.has(day);
                if (isLocked) { const displayShift = shift || "—"; return `<td style="padding: 0.5rem 0.4rem; text-align: center; background: rgba(100,116,139,0.07); color: var(--text-muted); font-size: 0.78rem;"><span style="display:flex; align-items:center; justify-content:center; gap:3px;"><i class="fa-solid fa-lock" style="font-size:0.55rem; opacity:0.5;"></i>${displayShift}</span></td>`; }
                if (isDeparted && shift === undefined) { return `<td style="padding: 0.5rem 0.4rem; text-align: center; background: repeating-linear-gradient(45deg, rgba(239,68,68,0.04) 0px, rgba(239,68,68,0.04) 3px, transparent 3px, transparent 9px); border: 1px solid rgba(239,68,68,0.15);"><span style="font-size:0.7rem; color: rgba(239,68,68,0.4);">—</span></td>`; }
                const displayShift = shift || "—"; const isOff = shift === "OFF" || shift === "VAC" || shift === "PERM";
                return `<td style="padding: 0.5rem 0.4rem; text-align: center; background: rgba(16,185,129,0.05); font-size: 0.8rem; font-weight: ${isOff ? "400" : "600"}; color: ${isOff ? "var(--text-muted)" : "var(--text-main)"};">${displayShift}</td>`;
            }).join("");
            const empRowStyle = isDeparted ? "background: rgba(239,68,68,0.03);" : "";
            return `<tr style="${empRowStyle}"><td style="padding:0.5rem 0.75rem; font-weight:${isDeparted ? "400" : "600"}; color:${isDeparted ? "var(--text-muted)" : "var(--text-main)"}; font-size:0.85rem; white-space:nowrap;">${isDeparted ? '<i class="fa-solid fa-user-slash" style="font-size:0.7rem; color:#ef4444; margin-right:4px;"></i>' : ""}${emp}</td>${cells}</tr>`;
        }).join("");
        const ctxLabel = document.getElementById("partialHistoryContextLabel"); if (ctxLabel) ctxLabel.textContent = meta.history_context_label || "";
        previewZone.style.display = "block"; previewZone.scrollIntoView({ behavior: "smooth", block: "start" });
    },

    async save() {
        if (!this.lastResult) { setStatusMessage("Primero generá el horario parcial", "error"); return; }
        const baseName = (this.lastResult.metadata?.base_name || this.baseEntry?.name || "Semana").trim();
        const name = baseName.endsWith("(parcial)") ? baseName : `${baseName} (parcial)`;
        const entry = { name, schedule: this.lastResult.schedule || {}, daily_tasks: this.lastResult.daily_tasks || {}, week_dates: this.lastResult.metadata?.week_dates || {}, special_days: this.lastResult.metadata?.special_days || {}, timestamp: new Date().toISOString() };
        try {
            const res = await fetch("/api/history", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(entry) });
            if (res.ok) setStatusMessage(`"${name}" guardado en el historial ✓`, "success");
            else setStatusMessage("Error al guardar en el historial", "error");
        } catch (e) { console.error("[PartialGenerator] save error:", e); setStatusMessage("Error al conectar con el servidor", "error"); }
    },

    _updateStatusBadge() {
        const badge = document.getElementById("partialStatusBadge"); if (!badge) return;
        if (!this.baseEntry) { badge.textContent = "Sin configurar"; badge.style.color = "#f97316"; return; }
        const activeDays = DAYS.filter(d => !this.dayLocked[d]);
        badge.textContent = `${this.baseEntry.name} — ${activeDays.length} días activos`; badge.style.color = "#10b981";
    },
};

/* ── Funciones globales (llamadas desde HTML inline) ── */
function partialSearchHistory(query) { PartialGenerator.searchHistory(query).catch(console.error); }
window.partialSearchHistory = partialSearchHistory;

function partialClearBase() { PartialGenerator.clearBase(); }
window.partialClearBase = partialClearBase;

function partialAddDeparted() { PartialGenerator.addDeparted(); }
window.partialAddDeparted = partialAddDeparted;

async function generatePartialSchedule() { await PartialGenerator.generate(); }
window.generatePartialSchedule = generatePartialSchedule;

async function savePartialSchedule() { await PartialGenerator.save(); }
window.savePartialSchedule = savePartialSchedule;

/* ── Click handlers ── */
document.addEventListener("click", function(e) {
    const input = document.getElementById("partialSearchInput");
    const results = document.getElementById("partialSearchResults");
    if (results && input && !input.contains(e.target) && !results.contains(e.target)) { results.style.display = "none"; }
});
