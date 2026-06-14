/* Plantillas de preferencias de horario (Parámetros + asignación en colaborador) */

async function refreshPrefPlantillasList() {
    const host = document.getElementById("prefPlantillasList");
    if (!host) return;
    host.innerHTML = '<p class="helper-text-sm" style="margin:0;">Cargando…</p>';
    try {
        const res = await fetch("/api/planillas/pref-plantillas");
        if (!res.ok) throw new Error("No se pudieron cargar las plantillas");
        const rows = await res.json();
        if (!rows.length) {
            host.innerHTML = '<p class="helper-text-sm" style="margin:0; color:var(--text-muted);">No hay plantillas. Creá una con «Nueva plantilla».</p>';
            return;
        }
        let html = '<div style="display:flex; flex-direction:column; gap:0.5rem;">';
        rows.forEach((p) => {
            const act = p.activa ? "" : " <span style=\"opacity:0.6\">(inactiva)</span>";
            html += `<div style="display:flex; align-items:center; justify-content:space-between; gap:0.75rem; padding:0.6rem 0.75rem; background:var(--surface-2); border-radius:8px; border:1px solid var(--border-color);">
                <div><strong style="font-size:0.9rem;">${escapeHtml(p.nombre)}</strong>${act}<br><span class="helper-text-sm" style="margin:0;">ID ${p.id}</span></div>
                <button type="button" class="btn-action" style="font-size:0.8rem; padding:0.35rem 0.65rem; border-radius:6px;" onclick="openPrefPlantillaModal(${p.id})"><i class="fa-solid fa-pen"></i> Editar</button>
            </div>`;
        });
        html += "</div>";
        host.innerHTML = html;
    } catch (e) {
        host.innerHTML = `<p class="helper-text-sm" style="margin:0; color:var(--danger);">${escapeHtml(e.message || "Error")}</p>`;
    }
}

function escapeHtml(s) {
    if (!s) return "";
    return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

window.openPrefPlantillaModal = async function (id) {
    window.__pillEditorMode = "plantilla";
    if (typeof closePillPanel === "function") closePillPanel();
    const modal = document.getElementById("prefPlantillaModal");
    if (!modal) return;
    modal.classList.remove("hidden");
    document.getElementById("prefPlantillaEditId").value = id || "";
    document.getElementById("btnPrefPlantillaDelete").style.display = id ? "inline-flex" : "none";
    if (typeof populateShiftSelects === "function") populateShiftSelects();
    document.querySelectorAll("#prefPlantillaModal .ppt-shift-select").forEach((s) => {
        s.value = "AUTO";
    });
    document.getElementById("pptForcedLibres").checked = false;
    document.getElementById("pptForcedQuebrado").checked = false;
    document.getElementById("pptNoRest").checked = false;
    document.getElementById("pptStrictPreferences").checked = false;
    document.getElementById("prefPlantillaNombre").value = "";
    document.getElementById("prefPlantillaDesc").value = "";
    document.getElementById("prefPlantillaActiva").checked = true;

    if (id) {
        document.getElementById("prefPlantillaModalTitle").textContent = "Editar plantilla";
        try {
            const res = await fetch(`/api/planillas/pref-plantillas/${id}`);
            if (!res.ok) throw new Error("Plantilla no encontrada");
            const p = await res.json();
            document.getElementById("prefPlantillaNombre").value = p.nombre || "";
            document.getElementById("prefPlantillaDesc").value = p.descripcion || "";
            document.getElementById("prefPlantillaActiva").checked = !!p.activa;
            document.getElementById("pptForcedLibres").checked = !!p.forced_libres;
            document.getElementById("pptForcedQuebrado").checked = !!p.forced_quebrado;
            document.getElementById("pptNoRest").checked = !!p.allow_no_rest;
            document.getElementById("pptStrictPreferences").checked = !!p.strict_preferences;
            let tf = {};
            try {
                tf = JSON.parse(p.turnos_fijos || "{}");
            } catch (_) {}
            DAYS.forEach((d) => {
                const sel = document.querySelector(`#prefPlantillaModal .ppt-shift-select[data-day="${d}"]`);
                if (sel) sel.value = tf[d] || "AUTO";
            });
        } catch (e) {
            alert(e.message || "Error");
            closePrefPlantillaModal();
            return;
        }
    } else {
        document.getElementById("prefPlantillaModalTitle").textContent = "Nueva plantilla";
    }
    if (typeof buildDayCards === "function") buildDayCards();
};

window.closePrefPlantillaModal = function () {
    window.__pillEditorMode = undefined;
    document.getElementById("prefPlantillaModal")?.classList.add("hidden");
    document.getElementById("pptPillSelectorPanel")?.classList.add("hidden");
};

window.savePrefPlantillaFromModal = async function () {
    const nombre = (document.getElementById("prefPlantillaNombre").value || "").trim();
    if (!nombre) return alert("Nombre requerido");
    const shifts = {};
    document.querySelectorAll("#prefPlantillaModal .ppt-shift-select").forEach((sel) => {
        const d = sel.getAttribute("data-day");
        if (sel.value && sel.value !== "AUTO") shifts[d] = sel.value;
    });
    const body = {
        nombre,
        descripcion: (document.getElementById("prefPlantillaDesc").value || "").trim(),
        activa: document.getElementById("prefPlantillaActiva").checked ? 1 : 0,
        turnos_fijos: JSON.stringify(shifts),
        strict_preferences: document.getElementById("pptStrictPreferences").checked ? 1 : 0,
        allow_no_rest: document.getElementById("pptNoRest").checked ? 1 : 0,
        forced_libres: document.getElementById("pptForcedLibres").checked ? 1 : 0,
        forced_quebrado: document.getElementById("pptForcedQuebrado").checked ? 1 : 0,
    };
    const eid = document.getElementById("prefPlantillaEditId").value;
    try {
        let res;
        if (eid) {
            res = await fetch(`/api/planillas/pref-plantillas/${eid}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
        } else {
            res = await fetch("/api/planillas/pref-plantillas", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body),
            });
        }
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || res.statusText);
        }
        closePrefPlantillaModal();
        await refreshPrefPlantillasList();
        if (typeof loadEmpPrefPlantillaOptions === "function") await loadEmpPrefPlantillaOptions();
    } catch (e) {
        alert(e.message || "No se pudo guardar");
    }
};

window.deletePrefPlantillaCurrent = async function () {
    const eid = document.getElementById("prefPlantillaEditId").value;
    if (!eid) return;
    if (!confirm("¿Eliminar esta plantilla? Los colaboradores quedarán sin plantilla (modo legado).")) return;
    try {
        const res = await fetch(`/api/planillas/pref-plantillas/${eid}`, { method: "DELETE" });
        if (!res.ok) throw new Error("No se pudo eliminar");
        closePrefPlantillaModal();
        await refreshPrefPlantillasList();
        if (typeof loadEmpPrefPlantillaOptions === "function") await loadEmpPrefPlantillaOptions();
    } catch (e) {
        alert(e.message || "Error");
    }
};

window.loadEmpPrefPlantillaOptions = async function () {
    const sel = document.getElementById("empPrefPlantillaSelect");
    if (!sel) return;
    const cur = sel.value;
    sel.innerHTML = '<option value="">— Sin plantilla (preferencias en este formulario) —</option>';
    try {
        const res = await fetch("/api/planillas/pref-plantillas?solo_activas=true");
        if (!res.ok) return;
        const rows = await res.json();
        rows.forEach((p) => {
            const o = document.createElement("option");
            o.value = String(p.id);
            o.textContent = p.nombre;
            sel.appendChild(o);
        });
    } catch (_) {}
    if (cur && [...sel.options].some((o) => o.value === cur)) sel.value = cur;
};

window.onEmpPrefPlantillaChange = function () {
    const v = document.getElementById("empPrefPlantillaSelect")?.value;
    const legacy = document.getElementById("scheduleLegacyShiftUI");
    const banner = document.getElementById("empPrefPlantillaBanner");
    if (v) {
        legacy?.classList.add("hidden");
        banner?.classList.remove("hidden");
    } else {
        legacy?.classList.remove("hidden");
        banner?.classList.add("hidden");
    }
};
