/**
 * Panel de Parámetros del Generador — matriz densa + detalle (API /api/generator/employee-params).
 */
(function () {
    const FLAG_KEYS = ["forced_libres", "forced_quebrado", "allow_no_rest", "strict_preferences", "is_jefe_pista"];
    const DAY_ORDER = ["Vie", "Sáb", "Dom", "Lun", "Mar", "Mié", "Jue"];

    let genPanelSnapshot = null;
    let genPanelRows = {};
    let genPanelActiveId = null;

    function shiftLabel(code) {
        if (typeof window.formatGeneratorShiftLabel === "function") {
            return window.formatGeneratorShiftLabel(code);
        }
        return code || "—";
    }

    function _fridayOf(d) {
        const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
        while (x.getDay() !== 5) x.setDate(x.getDate() - 1);
        return x;
    }

    function _iso(d) {
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, "0");
        const day = String(d.getDate()).padStart(2, "0");
        return `${y}-${m}-${day}`;
    }

    function initGenPanelWeekInput() {
        const el = document.getElementById("genPanelWeekStart");
        if (!el || el.dataset.genInit) return;
        el.dataset.genInit = "1";
        const fri = _fridayOf(new Date());
        el.value = _iso(fri);
    }

    function summarizeShifts(prefs) {
        if (!prefs) return "—";
        const parts = [];
        for (const d of DAY_ORDER) {
            const v = prefs[d];
            if (v && v !== "AUTO") parts.push(`${d}: ${shiftLabel(v)}`);
        }
        if (parts.length === 0) return "—";
        const s = parts.slice(0, 3).join(" · ");
        return parts.length > 3 ? s + "…" : s;
    }

    function rowFromApi(entry) {
        return {
            employee_id: entry.employee_id,
            nombre: entry.nombre,
            flags: { ...entry.flags },
            preference_source: entry.preference_source,
            pref_plantilla_id: entry.pref_plantilla_id,
            pref_plantilla_nombre: entry.pref_plantilla_nombre,
            shift_preferences: { ...entry.shift_preferences },
            absences: Array.isArray(entry.absences) ? entry.absences.slice() : [],
            hr_absence_hints: Array.isArray(entry.hr_absence_hints) ? entry.hr_absence_hints.slice() : [],
        };
    }

    function genPanelOptionsForDay(day) {
        const out = [];
        const seen = new Set();
        function add(code, label) {
            if (!code || seen.has(code)) return;
            seen.add(code);
            out.push({ code, label: label != null ? label : shiftLabel(code) });
        }
        add("AUTO", shiftLabel("AUTO"));
        const bg = typeof window.buildPillGroupsForDay === "function" ? window.buildPillGroupsForDay(day) : null;
        if (bg) {
            const order = ["special", "morning", "afternoon", "extended", "jefe"];
            for (const key of order) {
                for (const x of bg[key] || []) {
                    if (x.code === "AUTO") continue;
                    add(x.code, shiftLabel(x.code));
                }
            }
        } else {
            ["OFF", "VAC", "PERM", "N_22-05", "T1_05-13", "T2_06-14", "T3_07-15", "T4_08-16", "PM", "J_06-16"].forEach(
                (c) => add(c, shiftLabel(c))
            );
        }
        return out;
    }

    window.refreshGeneratorParamsPanel = async function () {
        initGenPanelWeekInput();
        const weekEl = document.getElementById("genPanelWeekStart");
        const weekStart = weekEl && weekEl.value ? weekEl.value : "";
        const tbody = document.getElementById("genPanelTbody");
        const empty = document.getElementById("genPanelEmpty");
        if (!tbody) return;
        tbody.innerHTML = "";
        try {
            const q = weekStart ? `?week_start=${encodeURIComponent(weekStart)}` : "";
            const res = await fetch(`/api/generator/employee-params${q}`);
            if (!res.ok) throw new Error(await res.text());
            genPanelSnapshot = await res.json();
            genPanelRows = {};
            const emps = genPanelSnapshot.employees || {};
            const ids = Object.keys(emps).sort((a, b) =>
                (emps[a].nombre || "").localeCompare(emps[b].nombre || "", "es")
            );
            if (ids.length === 0) {
                if (empty) empty.classList.remove("hidden");
                window._renderGenPanelDetail();
                return;
            }
            if (empty) empty.classList.add("hidden");
            for (const id of ids) {
                const e = emps[id];
                genPanelRows[id] = rowFromApi(e);
                tbody.appendChild(window._buildGenPanelRow(id, genPanelRows[id]));
            }
            window._renderGenPanelDetail();
        } catch (err) {
            console.error(err);
            if (empty) {
                empty.classList.remove("hidden");
                empty.textContent = "Error al cargar el panel: " + (err.message || err);
            }
        }
    };

    window._buildGenPanelRow = function (id, row) {
        const tr = document.createElement("tr");
        tr.dataset.empId = id;
        if (String(genPanelActiveId) === String(id)) tr.classList.add("gen-row-active");

        const tdName = document.createElement("td");
        tdName.className = "gen-col-name";
        const nb = document.createElement("button");
        nb.type = "button";
        nb.className = "gen-param-name-btn";
        nb.textContent = row.nombre || "—";
        nb.addEventListener("click", () => {
            genPanelActiveId = Number(id);
            document.querySelectorAll("#genPanelTbody tr").forEach((r) => r.classList.remove("gen-row-active"));
            tr.classList.add("gen-row-active");
            window._renderGenPanelDetail();
        });
        tdName.appendChild(nb);
        tr.appendChild(tdName);

        for (const fk of FLAG_KEYS) {
            const td = document.createElement("td");
            td.className = "gen-col-toggle";
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "gen-param-toggle";
            btn.setAttribute("role", "switch");
            const on = !!row.flags[fk];
            btn.setAttribute("aria-checked", on ? "true" : "false");
            btn.addEventListener("click", () => {
                row.flags[fk] = !row.flags[fk];
                btn.setAttribute("aria-checked", row.flags[fk] ? "true" : "false");
            });
            td.appendChild(btn);
            tr.appendChild(td);
        }

        const tdSh = document.createElement("td");
        tdSh.className = "gen-col-shift gen-param-shift-cell";
        tdSh.textContent = summarizeShifts(row.shift_preferences);
        tdSh.title = "Resumen de turnos fijos — editá por día en el panel lateral";
        tr.appendChild(tdSh);

        const tdAb = document.createElement("td");
        tdAb.className = "gen-col-abs";
        const ab = document.createElement("button");
        ab.type = "button";
        ab.className = "gen-param-abs-btn";
        const na = (row.absences || []).length;
        const nh = (row.hr_absence_hints || []).length;
        ab.textContent = na ? String(na) : nh ? "!" : "0";
        ab.title = na ? "Ausencias en turnos (semana)" : nh ? "Revisar avisos RR.HH." : "Sin ausencias";
        ab.addEventListener("click", () => {
            genPanelActiveId = Number(id);
            document.querySelectorAll("#genPanelTbody tr").forEach((r) => r.classList.remove("gen-row-active"));
            tr.classList.add("gen-row-active");
            window._renderGenPanelDetail();
        });
        tdAb.appendChild(ab);
        tr.appendChild(tdAb);

        return tr;
    };

    window._renderGenPanelDetail = function () {
        const ph = document.getElementById("genPanelDetailPlaceholder");
        const box = document.getElementById("genPanelDetailContent");
        if (!ph || !box) return;
        if (genPanelActiveId == null || !genPanelRows[String(genPanelActiveId)]) {
            ph.classList.remove("hidden");
            box.classList.add("hidden");
            box.innerHTML = "";
            return;
        }
        ph.classList.add("hidden");
        box.classList.remove("hidden");
        const row = genPanelRows[String(genPanelActiveId)];
        const parts = [];
        parts.push(`<p style="margin:0 0 0.5rem 0;font-weight:600;font-size:0.85rem;">${escapeHtml(row.nombre)}</p>`);

        parts.push(`<p class="gen-detail-shifts-title">Turnos fijos (semana tipo)</p>`);
        parts.push(`<div class="gen-detail-days-grid" id="genPanelDayShiftsGrid">`);
        for (const d of DAY_ORDER) {
            const opts = genPanelOptionsForDay(d);
            let val = row.shift_preferences[d];
            if (val == null || val === "") val = "AUTO";
            parts.push(
                `<div class="gen-detail-day-row"><label for="genDaySel_${d}_${row.employee_id}">${escapeHtml(
                    d
                )}</label><select id="genDaySel_${d}_${row.employee_id}" class="gen-detail-day-shift" data-day="${escapeHtml(
                    d
                )}" aria-label="Turno fijo ${escapeHtml(d)}">`
            );
            for (const o of opts) {
                const sel = o.code === val ? " selected" : "";
                parts.push(`<option value="${escapeHtml(o.code)}"${sel}>${escapeHtml(o.label)}</option>`);
            }
            parts.push(`</select></div>`);
        }
        parts.push(`</div>`);
        parts.push(
            `<button type="button" class="btn-action" style="margin-top:0.5rem;font-size:0.78rem;padding:0.4rem 0.75rem;" onclick="genPanelResetWeekAuto(${row.employee_id})">Resetear semana a Auto</button>`
        );

        parts.push(`<p style="font-size:0.72rem;color:var(--text-muted);margin:0.75rem 0 0.35rem 0;">Ausencias efectivas (turnos fijos / semana)</p>`);
        parts.push("<ul class='gen-detail-list'>");
        if (!row.absences || row.absences.length === 0) parts.push("<li>Ninguna en esta semana</li>");
        else
            row.absences.forEach((a) => {
                parts.push(
                    `<li>${escapeHtml(a.type)} ${escapeHtml(a.date || "")} ${a.note ? "<small>(" + escapeHtml(a.note) + ")</small>" : ""}</li>`
                );
            });
        parts.push("</ul>");
        if (row.hr_absence_hints && row.hr_absence_hints.length) {
            parts.push(`<p style="font-size:0.72rem;color:var(--text-muted);margin:0.75rem 0 0.35rem 0;">Avisos RR.HH. (no aplicados al motor si no están en turnos)</p>`);
            parts.push("<ul class='gen-detail-list'>");
            row.hr_absence_hints.forEach((h) => {
                parts.push(`<li>${escapeHtml(h.type)} ${escapeHtml(h.date || "")} — ${escapeHtml(h.note || "")}</li>`);
            });
            parts.push("</ul>");
        }
        parts.push(
            `<p class="gen-detail-hint">Guardá con «Guardar todo» arriba para persistir turnos en la base. El perfil laboral del colaborador está en Gestión de Personal.</p>`
        );
        parts.push(
            `<button type="button" class="btn-action" style="margin-top:0.5rem;font-size:0.78rem;padding:0.4rem 0.75rem;" onclick="genPanelOpenEmpModal(${row.employee_id})">Abrir ficha del colaborador (perfil)</button>`
        );
        box.innerHTML = parts.join("");

        box.querySelectorAll(".gen-detail-day-shift").forEach((sel) => {
            sel.addEventListener("change", () => {
                const day = sel.getAttribute("data-day");
                const v = sel.value;
                const r = genPanelRows[String(genPanelActiveId)];
                if (!r || !day) return;
                r.shift_preferences[day] = v;
                window._genPanelReplaceRowTr(String(r.employee_id));
            });
        });
    };

    window.genPanelResetWeekAuto = function (empId) {
        const row = genPanelRows[String(empId)];
        if (!row) return;
        DAY_ORDER.forEach((d) => {
            row.shift_preferences[d] = "AUTO";
        });
        window._genPanelReplaceRowTr(String(empId));
        if (genPanelActiveId === Number(empId)) window._renderGenPanelDetail();
    };

    window.genPanelApplyJefeBaseFromConfig = function () {
        const jsel = document.getElementById("jefeBaseShiftSelect");
        const code = (jsel && jsel.value) ? jsel.value : "J_06-16";
        const weekdays = ["Lun", "Mar", "Mié", "Jue", "Vie"];
        let jefeId = null;
        for (const id of Object.keys(genPanelRows)) {
            if (genPanelRows[id].flags && genPanelRows[id].flags.is_jefe_pista) {
                jefeId = id;
                break;
            }
        }
        if (!jefeId) {
            alert(
                "No hay colaborador marcado como jefe de pista en la matriz. Activá el toggle «Jefe» en una fila y guardá si hace falta."
            );
            return;
        }
        const row = genPanelRows[jefeId];
        weekdays.forEach((d) => {
            row.shift_preferences[d] = code;
        });
        const sPref = row.shift_preferences["Sáb"];
        const dPref = row.shift_preferences["Dom"];
        if (!sPref || sPref === "AUTO") row.shift_preferences["Sáb"] = "T1_05-13";
        if (!dPref || dPref === "AUTO") row.shift_preferences["Dom"] = "OFF";
        genPanelActiveId = Number(jefeId);
        document.querySelectorAll("#genPanelTbody tr").forEach((r) => r.classList.remove("gen-row-active"));
        const tr = document.querySelector(`#genPanelTbody tr[data-emp-id="${jefeId}"]`);
        if (tr) tr.classList.add("gen-row-active");
        window._genPanelReplaceRowTr(String(jefeId));
        window._renderGenPanelDetail();
    };

    window._genPanelReplaceRowTr = function (idStr) {
        const tbody = document.getElementById("genPanelTbody");
        if (!tbody) return;
        const old = tbody.querySelector(`tr[data-emp-id="${idStr}"]`);
        const row = genPanelRows[idStr];
        if (!old || !row) return;
        const nu = window._buildGenPanelRow(idStr, row);
        old.replaceWith(nu);
    };

    function escapeHtml(s) {
        if (s == null) return "";
        return String(s)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    window.genPanelOpenEmpModal = async function (empId) {
        try {
            const res = await fetch("/api/planillas/empleados");
            if (!res.ok) return;
            const list = await res.json();
            const emp = list.find((e) => e.id === empId);
            if (emp && typeof openUnifiedEmpModal === "function") openUnifiedEmpModal(emp);
            else if (typeof switchMainTab === "function") switchMainTab("planillas");
        } catch (e) {
            console.error(e);
        }
    };

    window.genPanelBatchForcedQuebrado = function (value) {
        for (const id of Object.keys(genPanelRows)) {
            genPanelRows[id].flags.forced_quebrado = !!value;
        }
        window._genPanelSyncDomFromState();
    };

    window._genPanelSyncDomFromState = function () {
        const tbody = document.getElementById("genPanelTbody");
        if (!tbody) return;
        tbody.querySelectorAll("tr").forEach((tr) => {
            const id = tr.dataset.empId;
            const row = genPanelRows[id];
            if (!row) return;
            const toggles = tr.querySelectorAll(".gen-param-toggle");
            FLAG_KEYS.forEach((fk, i) => {
                const b = toggles[i];
                if (b) b.setAttribute("aria-checked", row.flags[fk] ? "true" : "false");
            });
            const sh = tr.querySelector(".gen-param-shift-cell");
            if (sh) sh.textContent = summarizeShifts(row.shift_preferences);
        });
        window._renderGenPanelDetail();
    };

    window.saveGeneratorParamsPanel = async function () {
        const weekEl = document.getElementById("genPanelWeekStart");
        const updates = Object.keys(genPanelRows).map((id) => {
            const r = genPanelRows[id];
            return {
                employee_id: r.employee_id,
                flags: { ...r.flags },
                shift_preferences: { ...r.shift_preferences },
            };
        });
        try {
            const res = await fetch("/api/generator/employee-params", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    week_start: weekEl && weekEl.value ? weekEl.value : null,
                    updates,
                }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || JSON.stringify(data));
            const warns = (data.results || []).filter((x) => (x.warnings || []).length);
            let msg = "Guardado correctamente.";
            if (warns.length) msg += " Revisá la consola por avisos.";
            console.log("generator save", data);
            alert(msg);
            await window.refreshGeneratorParamsPanel();
        } catch (e) {
            console.error(e);
            alert("Error al guardar: " + (e.message || e));
        }
    };

    window.genPanelSyncRrhh = async function () {
        const weekEl = document.getElementById("genPanelWeekStart");
        const ws = weekEl && weekEl.value ? weekEl.value : "";
        if (!ws) {
            alert("Elegí la fecha del viernes de la semana.");
            return;
        }
        if (!confirm("¿Sincronizar vacaciones y permisos de RR.HH. hacia turnos fijos de todos los colaboradores para esta semana?")) return;
        try {
            const res = await fetch("/api/generator/sync-rrhh-to-shifts", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ week_start: ws }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Error");
            alert(`Sincronizado: ${data.empleados || 0} colaboradores.`);
            await window.refreshGeneratorParamsPanel();
        } catch (e) {
            alert("Error: " + (e.message || e));
        }
    };

    document.addEventListener("DOMContentLoaded", () => {
        initGenPanelWeekInput();
    });
})();
