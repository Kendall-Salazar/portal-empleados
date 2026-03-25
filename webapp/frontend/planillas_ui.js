/**
// ─── Toast Notification Utility ──────────────────────────────────────────────
/**
 * showToast(message, type)
 * type: 'success' | 'error' | 'warning' | 'info'
 * Renders a polished, auto-dismissing toast aligned with the design system.
 */
function showToast(message, type = 'success') {
    // Remove any existing toast of same type to avoid stacking
    document.querySelectorAll('.chronos-toast').forEach(t => {
        if (t.dataset.type === type) t.remove();
    });

    const icons = {
        success: 'fa-circle-check',
        error: 'fa-circle-xmark',
        warning: 'fa-triangle-exclamation',
        info: 'fa-circle-info',
    };
    const colors = {
        success: { bg: '#10b981', shadow: 'rgba(16,185,129,0.35)' },
        error: { bg: '#ef4444', shadow: 'rgba(239,68,68,0.35)' },
        warning: { bg: '#f59e0b', shadow: 'rgba(245,158,11,0.35)' },
        info: { bg: '#3b82f6', shadow: 'rgba(59,130,246,0.35)' },
    };
    const c = colors[type] || colors.success;

    const el = document.createElement('div');
    el.className = 'chronos-toast';
    el.dataset.type = type;
    el.innerHTML = `<i class="fa-solid ${icons[type] || icons.success}"></i><span>${message}</span>`;
    Object.assign(el.style, {
        position: 'fixed',
        bottom: '1.5rem',
        right: '1.5rem',
        background: c.bg,
        color: '#fff',
        padding: '0.65rem 1.1rem',
        borderRadius: '10px',
        fontSize: '0.85rem',
        fontWeight: '600',
        zIndex: '9999',
        boxShadow: `0 6px 24px ${c.shadow}`,
        display: 'flex',
        alignItems: 'center',
        gap: '0.55rem',
        animation: 'toastSlideIn 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275) both',
        maxWidth: '360px',
        lineHeight: '1.3',
    });

    // Inject keyframes once
    if (!document.getElementById('chronos-toast-keyframes')) {
        const style = document.createElement('style');
        style.id = 'chronos-toast-keyframes';
        style.textContent = `
            @keyframes toastSlideIn {
                from { transform: translateY(20px) scale(0.95); opacity: 0; }
                to   { transform: translateY(0) scale(1); opacity: 1; }
            }
            @keyframes toastSlideOut {
                from { transform: translateY(0) scale(1); opacity: 1; }
                to   { transform: translateY(16px) scale(0.95); opacity: 0; }
            }
        `;
        document.head.appendChild(style);
    }

    document.body.appendChild(el);

    // Auto-dismiss
    const dur = type === 'error' ? 4500 : 3000;
    setTimeout(() => {
        el.style.animation = 'toastSlideOut 0.25s ease both';
        setTimeout(() => el.remove(), 260);
    }, dur);
}

//Portal de Empleados-- Logica Frontend Unificada
//Maneja: Mi Equipo, Vacaciones, Aguinaldo


// =============================================================================
// NAVIGATION
// =============================================================================
function switchMainTab(tabId) {
    document.querySelectorAll('[data-main-tab]').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.section-overlay').forEach(el => el.classList.add('hidden'));

    document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
    if (event && event.currentTarget) event.currentTarget.classList.add('active');
    else document.getElementById(`nav-${tabId === 'schedule' ? 'schedule' : tabId}`)?.classList.add('active');

    if (tabId === 'schedule') {
        document.getElementById('tab-schedule-main')?.classList.remove('hidden');
    } else {
        document.getElementById(`tab-${tabId}`)?.classList.remove('hidden');
    }

    if (tabId === 'gestion') loadGestionPersonalTab();
    if (tabId === 'planilla-mensual') loadPlanillaMensualTab();
    if (tabId === 'aguinaldo') loadAguinaldoTab();
    if (tabId === 'utilidades') loadUtilidadesTab();
    if (tabId === 'inventario') loadInventarioTab();

    const scheduleConfig = document.getElementById('scheduleConfigSidebar');
    const weekDateConfig = document.getElementById('weekDateConfig');
    const btnGenerate = document.querySelector('.btn-generate');
    if (scheduleConfig) scheduleConfig.style.display = (tabId === 'schedule') ? 'block' : 'none';
    if (weekDateConfig) weekDateConfig.style.display = (tabId === 'schedule') ? 'block' : 'none';
    if (btnGenerate) btnGenerate.style.display = (tabId === 'schedule') ? 'flex' : 'none';
}

const originalCloseAllOverlays = window.closeAllOverlays;
window.closeAllOverlays = function () {
    if (originalCloseAllOverlays) originalCloseAllOverlays();
    document.querySelectorAll('.section-overlay').forEach(el => el.classList.add('hidden'));
};

// =============================================================================
// HELPERS
// =============================================================================
const _GRADIENTS = [
    ['#6366f1', '#8b5cf6'], ['#3b82f6', '#06b6d4'],
    ['#10b981', '#14b8a6'], ['#f59e0b', '#ef4444'],
    ['#ec4899', '#8b5cf6'], ['#14b8a6', '#0ea5e9'],
];
function _grad(id) { const g = _GRADIENTS[id % _GRADIENTS.length]; return `linear-gradient(135deg, ${g[0]}, ${g[1]})`; }
function _initials(name) { return name.split(' ').map(w => w[0]).join('').substring(0, 2).toUpperCase(); }
function _esc(s) { return s.replace(/'/g, "&#39;"); }
function _money(n) { return n.toLocaleString('en-US', { minimumFractionDigits: 2 }); }

// =============================================================================
// SUB-TAB: MI EQUIPO
// =============================================================================
async function loadVacSubEquipo() {
    const content = document.getElementById('vacSubTabContent');
    content.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1.5rem;">
            <div>
                <h3 style="color:var(--text-main); margin:0;"><i class="fa-solid fa-users" style="color:var(--primary); margin-right:8px;"></i> Nómina de Colaboradores</h3>
                <p style="color:var(--text-muted); font-size:0.85rem; margin-top:4px;">Directorio y gestión del equipo</p>
            </div>
            <div style="display:flex; gap:10px; align-items:center;">
                <div class="portal-stat-chip" id="equipoCountChip">
                    <i class="fa-solid fa-user-group"></i> <span>--</span>
                </div>
                <button class="portal-btn-primary" onclick="openUnifiedEmpModal()">
                    <i class="fa-solid fa-plus"></i> Nuevo Colaborador
                </button>
            </div>
        </div>
        <div id="equipoGrid" class="equipo-grid">
            <div class="portal-loading"><div class="portal-spinner"></div><span>Cargando equipo...</span></div>
        </div>`;

    try {
        const res = await fetch('/api/planillas/empleados');
        const emps = await res.json();
        const grid = document.getElementById('equipoGrid');
        document.querySelector('#equipoCountChip span').textContent = `${emps.length} colaboradores`;
        grid.innerHTML = '';

        if (emps.length === 0) {
            grid.innerHTML = '<div class="portal-empty"><i class="fa-solid fa-user-group"></i><p>No hay colaboradores registrados.</p><button class="portal-btn-primary" onclick="openUnifiedEmpModal()"><i class="fa-solid fa-plus"></i> Agregar primero</button></div>';
            return;
        }

        emps.forEach((emp, idx) => {
            const initials = _initials(emp.nombre);
            const gradient = _grad(emp.id);
            const gI = emp.genero === 'F' ? 'fa-venus' : 'fa-mars';
            const gC = emp.genero === 'F' ? '#ec4899' : '#3b82f6';

            const chips = [];
            if (emp.cedula) chips.push(`<span class="ecard-chip"><i class="fa-solid fa-id-card"></i>${emp.cedula}</span>`);
            if (emp.telefono) chips.push(`<span class="ecard-chip"><i class="fa-solid fa-phone"></i>${emp.telefono}</span>`);
            if (emp.correo) chips.push(`<span class="ecard-chip"><i class="fa-solid fa-envelope"></i>${emp.correo}</span>`);
            if (emp.fecha_inicio) chips.push(`<span class="ecard-chip"><i class="fa-solid fa-calendar-check"></i>${emp.fecha_inicio}</span>`);
            if (emp.salario_fijo) chips.push(`<span class="ecard-chip ecard-chip-fijo"><i class="fa-solid fa-coins"></i>₡${_money(emp.salario_fijo)}/mes</span>`);

            // Badge de tipo de pago con icono y color según tipo
            const tipoBadgeMap = {
                tarjeta: { icon: 'fa-credit-card', color: '#1d4ed8', bg: 'rgba(29,78,216,0.12)', label: 'Tarjeta' },
                efectivo: { icon: 'fa-money-bill-wave', color: '#059669', bg: 'rgba(5,150,105,0.12)', label: 'Efectivo' },
                fijo: { icon: 'fa-calendar-week', color: '#7c3aed', bg: 'rgba(124,58,237,0.12)', label: 'Salario Fijo' },
            };
            const tb = tipoBadgeMap[emp.tipo_pago] || { icon: 'fa-circle-question', color: '#6b7280', bg: 'rgba(107,114,128,0.1)', label: emp.tipo_pago || '--' };
            const tipoBadgeHtml = `<span class="ecard-tipo-badge" style="color:${tb.color};background:${tb.bg};"><i class="fa-solid ${tb.icon}"></i>${tb.label}</span>`;

            const statusBadge = ''; // Only actives here

            const card = document.createElement('div');
            card.className = 'ecard';
            card.style.animationDelay = `${idx * 0.04}s`;
            card.innerHTML = `
                <div class="ecard-top">
                    <div class="ecard-avatar" style="background:${gradient};">${initials}</div>
                    <div class="ecard-id-col">
                        <h4 class="ecard-name" style="display: flex; align-items: center;">${emp.nombre}</h4>
                        <div class="ecard-meta">
                            <i class="fa-solid ${gI}" style="color:${gC};"></i>
                            ${tipoBadgeHtml}
                        </div>
                    </div>
                    <div class="ecard-actions">
                        <button class="ecard-btn" onclick='openUnifiedEmpModal(${_esc(JSON.stringify(emp))})' title="Editar"><i class="fa-solid fa-pen-to-square"></i></button>
                    </div>
                </div>
                <div class="ecard-divider"></div>
                <div class="ecard-bottom">
                    <div class="ecard-badges">
                        ${emp.aplica_seguro
                    ? '<span class="ebadge ebadge-ok"><i class="fa-solid fa-shield-halved"></i>Seguro</span>'
                    : '<span class="ebadge ebadge-warn"><i class="fa-solid fa-shield-xmark"></i>Sin Seguro</span>'}
                        ${emp.puede_nocturno ? '<span class="ebadge ebadge-night"><i class="fa-solid fa-moon"></i>Nocturno</span>' : ''}
                    </div>
                    ${chips.length > 0 ? `<div class="ecard-chips">${chips.join('')}</div>` : ''}
                </div>`;
            grid.appendChild(card);
        });

    } catch (e) {
        document.getElementById('equipoGrid').innerHTML = `<div class="portal-error"><i class="fa-solid fa-circle-exclamation"></i> ${e.message}</div>`;
    }
}

async function loadVacSubInactivos() {
    const content = document.getElementById('vacSubTabContent');
    content.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1.5rem;">
            <div>
                <h3 style="color:var(--text-main); margin:0;"><i class="fa-solid fa-user-slash" style="color:#ef4444; margin-right:8px;"></i> Papelera de Inactivos</h3>
                <p style="color:var(--text-muted); font-size:0.85rem; margin-top:4px;">Colaboradores desactivados y opción de eliminación total</p>
            </div>
            <div style="display:flex; gap:10px; align-items:center;">
                <div class="portal-stat-chip" id="equipoCountChip">
                    <i class="fa-solid fa-ban" style="color: #ef4444;"></i> <span>--</span>
                </div>
            </div>
        </div>
        <div id="equipoGrid" class="equipo-grid">
            <div class="portal-loading"><div class="portal-spinner"></div><span>Cargando inactivos...</span></div>
        </div>`;

    try {
        const res = await fetch('/api/planillas/empleados?solo_activos=false');
        const allEmps = await res.json();
        const emps = allEmps.filter(e => e.activo === 0 || e.activo === false);
        const grid = document.getElementById('equipoGrid');
        document.querySelector('#equipoCountChip span').textContent = `${emps.length} inactivos`;
        grid.innerHTML = '';

        if (emps.length === 0) {
            grid.innerHTML = '<div class="portal-empty"><i class="fa-solid fa-user-slash"></i><p>No hay colaboradores inactivos en la papelera.</p></div>';
            return;
        }

        emps.forEach((emp, idx) => {
            const initials = _initials(emp.nombre);
            const gradient = _grad(emp.id);
            const gI = emp.genero === 'F' ? 'fa-venus' : 'fa-mars';
            const gC = emp.genero === 'F' ? '#ec4899' : '#3b82f6';
            const statusBadge = '<span style="color: #ef4444; font-size: 0.75rem; border: 1px solid #ef4444; background: rgba(239, 68, 68, 0.1); padding: 2px 6px; border-radius: 4px; margin-left: 8px; vertical-align: middle;">Inactivo</span>';

            const card = document.createElement('div');
            card.className = 'ecard';
            card.style.animationDelay = `${idx * 0.04}s`;
            card.style.opacity = '0.6';
            card.style.border = '1px solid rgba(239, 68, 68, 0.3)';
            
            card.innerHTML = `
                <div class="ecard-top">
                    <div class="ecard-avatar" style="background:${gradient}; filter: grayscale(100%);">${initials}</div>
                    <div class="ecard-id-col">
                        <h4 class="ecard-name" style="display: flex; align-items: center; color: #9ca3af;">${emp.nombre} ${statusBadge}</h4>
                        <div class="ecard-meta" style="filter: grayscale(100%);">
                            <i class="fa-solid ${gI}" style="color:${gC};"></i>
                        </div>
                    </div>
                    <div class="ecard-actions">
                        <button class="ecard-btn" onclick='openUnifiedEmpModal(${_esc(JSON.stringify(emp))})' title="Reactivar / Editar"><i class="fa-solid fa-rotate-left"></i></button>
                        <button class="ecard-btn ecard-btn-danger" style="background: rgba(239, 68, 68, 0.15);" onclick="deletePlanillaEmp(${emp.id})" title="Borrado Permanente"><i class="fa-solid fa-trash-can"></i></button>
                    </div>
                </div>
                <div class="ecard-divider"></div>
                <div class="ecard-bottom" style="filter: grayscale(100%); opacity: 0.8;">
                    <span style="font-size: 0.8rem; color: #9ca3af;"><i class="fa-solid fa-triangle-exclamation"></i> Borrar aquí elimina todo su historial para siempre</span>
                </div>`;
            grid.appendChild(card);
        });

    } catch (e) {
        document.getElementById('equipoGrid').innerHTML = `<div class="portal-error"><i class="fa-solid fa-circle-exclamation"></i> ${e.message}</div>`;
    }
}

// =============================================================================
// UNIFIED EMPLOYEE MODAL
// =============================================================================
function openUnifiedEmpModal(emp = null) {
    const isEdit = !!emp;
    document.getElementById('planEmpModalTitle').textContent = isEdit ? 'Editar Colaborador' : 'Nuevo Colaborador';
    document.getElementById('planEmpId').value = isEdit ? emp.id : '';
    document.getElementById('planEmpNombre').value = isEdit ? (emp.nombre || '') : '';
    document.getElementById('planEmpCedula').value = isEdit ? (emp.cedula || '') : '';
    document.getElementById('planEmpTelefono').value = isEdit ? (emp.telefono || '') : '';
    document.getElementById('planEmpCorreo').value = isEdit ? (emp.correo || '') : '';
    document.getElementById('planEmpTipoPago').value = isEdit ? (emp.tipo_pago || 'tarjeta') : 'tarjeta';
    document.getElementById('planEmpFechaInicio').value = isEdit ? (emp.fecha_inicio || '') : '';
    document.getElementById('planEmpSalarioFijo').value = isEdit ? (emp.salario_fijo || '') : '';
    document.getElementById('planEmpSeguro').checked = isEdit ? !!emp.aplica_seguro : true;
    document.getElementById('planEmpNocturno').checked = isEdit ? !!emp.puede_nocturno : true;
    
    // Activo mapping
    const activeCb = document.getElementById('empActiveStatus');
    if (activeCb) activeCb.checked = isEdit ? !!(emp.activo !== 0 && emp.activo !== false) : true;

    const genderVal = isEdit ? (emp.genero || 'M') : 'M';
    document.getElementById('planEmpGenero').value = genderVal;
    document.querySelectorAll('.modal-gender-pill').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.gender === genderVal);
    });

    // --- Schedule Preferences ---
    document.getElementById('empForcedLibres').checked = isEdit ? !!emp.forced_libres : false;
    document.getElementById('empForcedQuebrado').checked = isEdit ? !!emp.forced_quebrado : false;
    document.getElementById('empNoRest').checked = isEdit ? !!emp.allow_no_rest : false;
    document.getElementById('empJefePista').checked = isEdit ? !!emp.es_jefe_pista : false;
    document.getElementById('empStrictPreferences').checked = isEdit ? !!emp.strict_preferences : false;

    // Fixed Shifts & Vaccations need their specific UI rendering functions
    // Note: ensure window.renderVacationCheckboxes and window.renderDayCards exist and are called if we switch to the tab!
    // We will call them globally or assume they hook up correctly. For safety, let's call init if they exist from app.js.
    if (typeof window.toggleJefeShiftSelect === 'function') window.toggleJefeShiftSelect();

    // We need to parse turnos_fijos for the grid and jefe
    const fixedShifts = isEdit ? (typeof emp.turnos_fijos === 'string' ? JSON.parse(emp.turnos_fijos || '{}') : (emp.turnos_fijos || {})) : {};

    // If it's jefe de pista, pre-load the main J_ role
    if (emp && emp.es_jefe_pista && fixedShifts['Lun']) {
        document.getElementById('jefeShiftSelect').value = fixedShifts['Lun'];
    }

    // Load shifts into hidden selects so the old app.js script picks them up for the UI
    document.querySelectorAll('.shift-select').forEach(sel => {
        const d = sel.dataset.day;
        sel.value = fixedShifts[d] || 'AUTO';
    });

    // Render the visual cards with the new values
    if (typeof window.buildDayCards === 'function') {
        window.buildDayCards();
    }
    if (typeof window.syncVacationCheckboxesFromDropdowns === 'function') {
        window.syncVacationCheckboxesFromDropdowns();
    }

    toggleSalarioFijoInput();
    document.getElementById('planillaEmpModal').classList.remove('hidden');
}

function closePlanillaEmpModal() {
    document.getElementById('planillaEmpModal').classList.add('hidden');
}

function setModalGender(gender, btn) {
    document.getElementById('planEmpGenero').value = gender;
    document.querySelectorAll('.modal-gender-pill').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
}

function toggleSalarioFijoInput() {
    const tipo = document.getElementById('planEmpTipoPago').value;
    document.getElementById('containerSalarioFijo').style.display = (tipo === 'fijo') ? 'block' : 'none';
}

document.addEventListener('DOMContentLoaded', () => {
    const sel = document.getElementById('planEmpTipoPago');
    if (sel) sel.addEventListener('change', toggleSalarioFijoInput);
});

async function guardarPlanillaEmp() {
    const id = document.getElementById('planEmpId').value;
    const data = {
        nombre: document.getElementById('planEmpNombre').value,
        cedula: document.getElementById('planEmpCedula').value,
        telefono: document.getElementById('planEmpTelefono').value,
        correo: document.getElementById('planEmpCorreo').value,
        tipo_pago: document.getElementById('planEmpTipoPago').value,
        fecha_inicio: document.getElementById('planEmpFechaInicio').value,
        salario_fijo: document.getElementById('planEmpTipoPago').value === 'fijo' ? parseFloat(document.getElementById('planEmpSalarioFijo').value) || null : null,
        aplica_seguro: document.getElementById('planEmpSeguro').checked ? 1 : 0,
        puede_nocturno: document.getElementById('planEmpNocturno').checked ? 1 : 0,
        genero: document.getElementById('planEmpGenero').value,
        forced_libres: document.getElementById('empForcedLibres').checked ? 1 : 0,
        forced_quebrado: document.getElementById('empForcedQuebrado').checked ? 1 : 0,
        allow_no_rest: document.getElementById('empNoRest').checked ? 1 : 0,
        es_jefe_pista: document.getElementById('empJefePista').checked ? 1 : 0,
        strict_preferences: document.getElementById('empStrictPreferences').checked ? 1 : 0,
        activo: document.getElementById('empActiveStatus') ? (document.getElementById('empActiveStatus').checked ? 1 : 0) : 1,
        turnos_fijos: '{}'
    };

    // Construct turnos fijos JSON
    const shifts = {};
    const isJefe = data.es_jefe_pista;
    const jefeVal = document.getElementById('jefeShiftSelect').value;

    const vacCheckboxes = document.querySelectorAll('.vacation-checkbox');
    const checkedVacDays = Array.from(vacCheckboxes).filter(cb => cb.checked).map(cb => cb.value);

    // Old hidden selects maintained by app.js pill selector
    document.querySelectorAll('.shift-select').forEach(sel => {
        const d = sel.dataset.day;
        if (checkedVacDays.includes(d)) {
            shifts[d] = 'VAC';
        } else if (isJefe) {
            // If they are Jefe, we override their week with the selected J_ shift, except weekend logic
            // Assuming weekend is Saturday T1 / Sunday OFF based on previous logic, but we can respect the UI:
            if (sel.value === 'OFF') shifts[d] = 'OFF';
            else if (sel.value === 'VAC') shifts[d] = 'VAC';
            else if (sel.value.startsWith('J_') || ['Lun', 'Mar', 'Mié', 'Jue', 'Vie'].includes(d)) shifts[d] = jefeVal;
            else if (sel.value !== 'AUTO') shifts[d] = sel.value;
        } else {
            if (sel.value !== 'AUTO') {
                shifts[d] = sel.value;
            }
        }
    });

    data.turnos_fijos = JSON.stringify(shifts);

    if (!data.nombre) { alert('El nombre es requerido.'); return; }

    try {
        let url = '/api/planillas/empleados';
        let method = 'POST';
        if (id) { url += `/${id}`; method = 'PUT'; }

        const res = await fetch(url, {
            method, headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Error al guardar');
        }
        closePlanillaEmpModal();
        loadVacSubEquipo();
    } catch (e) { alert(e.message); }
}

async function deletePlanillaEmp(id) {
    if (!confirm('¡ATENCIÓN! La eliminación borrará permanentemente a este empleado, su historial de horarios, vacaciones y préstamos. ¿Estás absolutamente seguro de que deseas eliminarlo del sistema?')) return;
    try {
        const res = await fetch(`/api/planillas/empleados/${id}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Error al eliminar');
        // Because they are in the inactivos tab to be deleted:
        loadVacSubInactivos();
    } catch (e) { alert(e.message); }
}

// =============================================================================
// TAB: VACACIONES
// =============================================================================

function _formatDateEs(dateStr) {
    if (!dateStr) return '—';
    try {
        const d = new Date(dateStr + 'T00:00:00');
        return d.toLocaleDateString('es-CR', { day: '2-digit', month: 'short', year: 'numeric' });
    } catch { return dateStr; }
}

async function loadGestionPersonalTab() {
    const tab = document.getElementById('tab-gestion');
    tab.innerHTML = `
        <div class="portal-view">
            <div class="portal-header">
                <div class="portal-header-left">
                    <div class="portal-title-row">
                        <div class="portal-icon-wrap" style="--accent: #6366f1;">
                            <i class="fa-solid fa-users-gear"></i>
                        </div>
                        <div>
                            <h2 class="portal-title">Gestión de Personal</h2>
                            <p class="portal-subtitle">Directorio de equipo, vacaciones, permisos y préstamos</p>
                        </div>
                    </div>
                </div>
            </div>
            <!-- SUB-TABS -->
            <div style="display:flex; gap:0; margin-bottom:1.5rem; border-bottom: 2px solid var(--border);">
                <button id="vst-equipo" class="vac-subtab active" onclick="switchVacSubTab('equipo')">
                    <i class="fa-solid fa-users"></i> Mi Equipo
                </button>
                <button id="vst-vacaciones" class="vac-subtab" onclick="switchVacSubTab('vacaciones')">
                    <i class="fa-solid fa-umbrella-beach"></i> Vacaciones
                </button>
                <button id="vst-permisos" class="vac-subtab" onclick="switchVacSubTab('permisos')">
                    <i class="fa-solid fa-hand"></i> Permisos
                </button>
                <button id="vst-prestamos" class="vac-subtab" onclick="switchVacSubTab('prestamos')">
                    <i class="fa-solid fa-hand-holding-dollar"></i> Préstamos
                </button>
                <button id="vst-inactivos" class="vac-subtab" onclick="switchVacSubTab('inactivos')" style="margin-left: auto;">
                    <i class="fa-solid fa-user-slash"></i> Inactivos
                </button>
            </div>
            <div id="vacSubTabContent">
                <div class="portal-loading"><div class="portal-spinner"></div><span>Cargando datos...</span></div>
            </div>
        </div>`;

    // Load the default sub-tab
    await loadVacSubEquipo();
}

function switchVacSubTab(tab) {
    document.querySelectorAll('.vac-subtab').forEach(b => b.classList.remove('active'));
    document.getElementById(`vst-${tab}`)?.classList.add('active');
    if (tab === 'equipo') loadVacSubEquipo();
    else if (tab === 'vacaciones') loadVacSubVacaciones();
    else if (tab === 'permisos') loadVacSubPermisos();
    else if (tab === 'prestamos') loadVacSubPrestamos();
    else if (tab === 'inactivos') loadVacSubInactivos();
}

// ── SUB-TAB: VACACIONES ──
async function loadVacSubVacaciones() {
    const content = document.getElementById('vacSubTabContent');
    content.innerHTML = '<div class="portal-loading"><div class="portal-spinner"></div><span>Cargando...</span></div>';

    try {
        const res = await fetch('/api/planillas/empleados');
        const emps = await res.json();
        if (emps.length === 0) {
            content.innerHTML = '<div class="portal-empty"><i class="fa-solid fa-umbrella-beach"></i><p>No hay empleados registrados.</p></div>';
            return;
        }

        const vacRows = [];
        for (const emp of emps) {
            const vacRes = await fetch(`/api/planillas/vacaciones/${emp.id}`);
            const vacData = await vacRes.json();
            let antiguedad = "--", mesesTotales = 0;
            if (emp.fecha_inicio) {
                const start = new Date(emp.fecha_inicio);
                const hoy = new Date();
                mesesTotales = (hoy.getFullYear() - start.getFullYear()) * 12 - start.getMonth() + hoy.getMonth();
                antiguedad = mesesTotales >= 12 ? `${Math.floor(mesesTotales / 12)}a ${mesesTotales % 12}m` : `${mesesTotales}m`;
            }
            const acum = vacData.acumulados || 0, tom = vacData.tomados || 0, disp = vacData.disponibles || 0;
            vacRows.push({ emp, vacData, antiguedad, acum, tom, disp });
        }

        let html = '<div class="vac-cards-grid">';
        vacRows.forEach(({ emp, vacData, antiguedad, acum, tom, disp }, _vIdx) => {
            const pctUsed = acum > 0 ? Math.min(100, Math.round((tom / acum) * 100)) : 0;
            const dispColor = disp > 0 ? '#10b981' : (disp < 0 ? '#ef4444' : '#94a3b8');
            const barColor = disp > 0 ? '#10b981' : '#ef4444';
            const eName = emp.nombre.replace(/'/g, "\\'");

            html += `
            <div class="vac-emp-card" style="animation: slideDown 0.35s ease both; animation-delay: ${_vIdx * 0.06}s;">
                <div class="vac-emp-card-top">
                    <div class="vac-emp-avatar" style="background:${_grad(emp.id)};">${_initials(emp.nombre)}</div>
                    <div class="vac-emp-info">
                        <span class="vac-emp-name">${emp.nombre}</span>
                        <span class="vac-emp-meta"><i class="fa-solid fa-calendar-day"></i> ${emp.fecha_inicio || '—'} · <span class="vac-emp-antig">${antiguedad}</span></span>
                    </div>
                </div>
                <div class="vac-emp-hero-num">
                    <span class="vac-emp-hero-val" style="color:${dispColor};">${disp}</span>
                    <span class="vac-emp-hero-label">días disponibles</span>
                </div>
                <div class="vac-emp-bar-wrap">
                    <div class="vac-emp-bar-bg">
                        <div class="vac-emp-bar-fill" style="width:${pctUsed}%; background:${barColor};"></div>
                    </div>
                    <div class="vac-emp-bar-legend">
                        <span><span class="vac-emp-dot" style="background:#3b82f6;"></span> Acum: ${acum}</span>
                        <span><span class="vac-emp-dot" style="background:#f59e0b;"></span> Usados: ${tom}</span>
                    </div>
                </div>
                <div class="vac-emp-actions">
                    <button class="vac-btn vac-btn-primary" onclick="openRegistrarVacacion(${emp.id}, '${eName}')">
                        <i class="fa-solid fa-plus"></i> Registrar
                    </button>
                    <button class="vac-btn vac-btn-ghost" onclick="openVacHistorial(${emp.id}, '${eName}')">
                        <i class="fa-solid fa-clock-rotate-left"></i> Historial
                    </button>
                    <button class="vac-btn vac-btn-accent" onclick="goToVacacionesConstancia(${emp.id})" title="Generar carta de goce de vacaciones">
                        <i class="fa-solid fa-file-lines"></i> Carta
                    </button>
                </div>
            </div>`;
        });
        html += '</div>';
        content.innerHTML = html;

    } catch (e) {
        content.innerHTML = `<div class="portal-error"><i class="fa-solid fa-circle-exclamation"></i> ${e.message}</div>`;
    }
}

// ── SUB-TAB: PERMISOS ──
async function loadVacSubPermisos() {
    const content = document.getElementById('vacSubTabContent');
    content.innerHTML = '<div class="portal-loading"><div class="portal-spinner"></div><span>Cargando...</span></div>';

    try {
        const res = await fetch('/api/planillas/empleados');
        const emps = await res.json();
        const anio = new Date().getFullYear();

        let html = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
            <h3 style="color:var(--text-main); margin:0;"><i class="fa-solid fa-hand" style="color:#f59e0b;"></i> Permisos ${anio}</h3>
        </div>`;

        html += '<div class="vac-cards-grid">';
        for (const emp of emps) {
            const permRes = await fetch(`/api/planillas/permisos/${emp.id}?anio=${anio}`);
            const permData = await permRes.json();
            const conteo = permData.conteo || { total: 0, descontados: 0, pendientes: 0 };
            const permisos = permData.permisos || [];
            const eName = emp.nombre.replace(/'/g, "\\'");

            html += `
            <div class="perm-card" style="animation: slideUpFadeIn 0.4s ease backwards; animation-delay: ${Math.min((emp.id || 0) * 0.05, 0.5)}s;">
                <div class="perm-card-top">
                    <div class="vac-emp-avatar" style="background:${_grad(emp.id)};">${_initials(emp.nombre)}</div>
                    <div class="vac-emp-info">
                        <span class="vac-emp-name">${emp.nombre}</span>
                        <span class="vac-emp-meta">
                            <i class="fa-solid fa-id-card"></i> ${emp.cedula || 'Sin registro'}
                        </span>
                    </div>
                </div>

                <div class="perm-stats-grid">
                    <div class="perm-stat-item">
                        <span class="perm-stat-label">Total</span>
                        <span class="perm-stat-val perm-val-total">${conteo.total}</span>
                    </div>
                    <div class="perm-stat-item">
                        <span class="perm-stat-label">Descontados</span>
                        <span class="perm-stat-val perm-val-desc">${conteo.descontados}</span>
                    </div>
                    <div class="perm-stat-item">
                        <span class="perm-stat-label">Pendientes</span>
                        <span class="perm-stat-val perm-val-pend">${conteo.pendientes}</span>
                    </div>
                </div>

                <div class="perm-actions">
                    <button class="perm-btn perm-btn-primary" onclick="openRegistrarPermiso(${emp.id}, '${eName}')" title="Registrar permiso">
                        <i class="fa-solid fa-plus"></i> Registrar
                    </button>
                    ${permisos.length > 0 ? `
                    <button class="perm-btn perm-btn-ghost" onclick="openPermHistorial(${emp.id}, '${eName}', ${anio})" title="Ver historial">
                        <i class="fa-solid fa-clock-rotate-left"></i> Historial
                    </button>
                    ` : ''}
                    ${conteo.pendientes > 0 ? `
                    <button class="perm-btn perm-btn-accent" onclick="descontarPermisos(${emp.id}, '${eName}', ${conteo.pendientes}, ${anio})" title="Descontar de vacaciones">
                        <i class="fa-solid fa-check-to-slot"></i> Descontar (${conteo.pendientes})
                    </button>` : ''}
                </div>
            </div>`;
        }
        html += '</div>';
        content.innerHTML = html;

    } catch (e) {
        content.innerHTML = `<div class="portal-error"><i class="fa-solid fa-circle-exclamation"></i> ${e.message}</div>`;
    }
}

// ── SUB-TAB: PRÉSTAMOS ──
async function loadVacSubPrestamos() {
    const content = document.getElementById('vacSubTabContent');
    content.innerHTML = '<div class="portal-loading"><div class="portal-spinner"></div><span>Cargando...</span></div>';

    try {
        const empsRes = await fetch('/api/planillas/empleados');
        const emps = await empsRes.json();

        let html = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:1rem;">
            <h3 style="color:var(--text-main); margin:0;"><i class="fa-solid fa-hand-holding-dollar" style="color:#8b5cf6;"></i> Préstamos Activos</h3>
            <button class="vac-btn vac-btn-primary" onclick="openNuevoPrestamo()">
                <i class="fa-solid fa-plus"></i> Nuevo Préstamo
            </button>
        </div>`;

        html += '<div class="vac-cards-grid">';
        for (const emp of emps) {
            const prestRes = await fetch(`/api/planillas/prestamos/${emp.id}`);
            const prestamos = await prestRes.json();
            if (prestamos.length === 0) continue;

            const eName = emp.nombre.replace(/'/g, "\\'");

            for (const p of prestamos) {
                const progreso = p.monto_total > 0 ? Math.round(((p.monto_total - p.saldo) / p.monto_total) * 100) : 0;
                const isLiquidado = p.estado === 'liquidado';
                const statusColor = isLiquidado ? '#10b981' : '#8b5cf6';
                const statusText = isLiquidado ? 'Liquidado' : 'Activo';
                const statusBg = isLiquidado ? 'rgba(16,185,129,0.15)' : 'rgba(139,92,246,0.15)';

                html += `
                <div class="vac-emp-card" style="animation: slideDown 0.3s ease both; border-left: 3px solid ${statusColor};">
                    <div class="vac-emp-card-top">
                        <div class="vac-emp-avatar" style="background:${_grad(emp.id)};">${_initials(emp.nombre)}</div>
                        <div class="vac-emp-info">
                            <span class="vac-emp-name">${emp.nombre}</span>
                            <span class="vac-emp-meta">
                                <span style="background:${statusBg}; color:${statusColor}; padding:1px 8px; border-radius:6px; font-size:0.7rem; font-weight:700;">${statusText}</span>
                                <span style="color:var(--text-muted); font-size:0.7rem;">desde ${_formatDateEs(p.fecha_inicio)}</span>
                            </span>
                        </div>
                    </div>
                    <!-- Montos -->
                    <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:0.5rem; margin-top:0.7rem;">
                        <div style="text-align:center;">
                            <div style="font-size:0.65rem; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px;">Total</div>
                            <div style="font-size:1rem; font-weight:800; color:var(--text-main);">₡${_fmtMoney(p.monto_total)}</div>
                        </div>
                        <div style="text-align:center;">
                            <div style="font-size:0.65rem; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px;">Semanal</div>
                            <div style="font-size:1rem; font-weight:800; color:#f59e0b;">₡${_fmtMoney(p.pago_semanal)}</div>
                        </div>
                        <div style="text-align:center;">
                            <div style="font-size:0.65rem; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.5px;">Saldo</div>
                            <div style="font-size:1rem; font-weight:800; color:${isLiquidado ? '#10b981' : '#ef4444'};">₡${_fmtMoney(p.saldo)}</div>
                        </div>
                    </div>
                    <!-- Progress bar -->
                    <div style="margin-top:0.6rem;">
                        <div style="display:flex; justify-content:space-between; font-size:0.7rem; color:var(--text-muted); margin-bottom:3px;">
                            <span>Progreso</span><span>${progreso}%</span>
                        </div>
                        <div style="height:6px; background:rgba(255,255,255,0.08); border-radius:4px; overflow:hidden;">
                            <div style="height:100%; width:${progreso}%; background: linear-gradient(90deg, #8b5cf6, #10b981); border-radius:4px; transition: width 0.5s ease;"></div>
                        </div>
                    </div>
                    ${p.notas ? `<p style="font-size:0.75rem; color:var(--text-muted); margin-top:0.5rem; font-style:italic;">${p.notas}</p>` : ''}
                    <!-- Actions -->
                    <div style="display:flex; gap:0.5rem; margin-top:0.7rem; flex-wrap:wrap;">
                        <button class="vac-btn vac-btn-ghost" style="font-size:0.78rem;" onclick="verAbonosPrestamo(${p.id}, '${eName}')">
                            <i class="fa-solid fa-list"></i> Historial
                        </button>
                        ${!isLiquidado ? `
                        <button class="vac-btn vac-btn-primary" style="font-size:0.78rem; background:#8b5cf6;" onclick="registrarAbono(${p.id}, ${p.pago_semanal}, '${eName}', 'planilla')">
                            <i class="fa-solid fa-money-bill-transfer"></i> Abono Planilla
                        </button>
                        <button class="vac-btn vac-btn-ghost" style="font-size:0.78rem; color:#f59e0b; border-color:rgba(245,158,11,0.3);" onclick="registrarAbono(${p.id}, 0, '${eName}', 'extraordinario')">
                            <i class="fa-solid fa-star"></i> Extraordinario
                        </button>` : ''}
                        <button class="vac-btn vac-btn-ghost" style="font-size:0.75rem; color:#ef4444; border-color:rgba(239,68,68,0.2);" onclick="eliminarPrestamo(${p.id}, '${eName}')">
                            <i class="fa-solid fa-trash-can"></i>
                        </button>
                    </div>
                </div>`;
            }
        }
        html += '</div>';

        // If no loans exist at all
        if (!html.includes('vac-emp-card')) {
            html += `
            <div class="portal-empty-box" style="padding:40px 20px; text-align:center;">
                <i class="fa-solid fa-hand-holding-dollar" style="font-size:2.5rem; color:var(--text-muted); opacity:0.3; margin-bottom:15px;"></i>
                <h3 style="color:var(--text-main); font-size:1rem; margin-bottom:8px;">Sin préstamos activos</h3>
                <p style="color:var(--text-muted); font-size:0.85rem;">Registra un nuevo préstamo para comenzar el seguimiento.</p>
            </div>`;
        }

        content.innerHTML = html;

    } catch (e) {
        content.innerHTML = `<div class="portal-error"><i class="fa-solid fa-circle-exclamation"></i> ${e.message}</div>`;
    }
}

function _fmtMoney(n) {
    return Number(n || 0).toLocaleString('es-CR', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

// Quick link to Constancia de Vacaciones in Utilidades
function goToVacacionesConstancia(empId) {
    // Switch to Utilidades tab and open vacaciones form
    switchMainTab('utilidades');
    setTimeout(() => {
        showUtilForm('vacaciones');
        const sel = document.getElementById('utilVacacionesEmp');
        if (sel) { sel.value = empId; checkVacDisponibles(); }
    }, 500);
}

// =============================================================================
// VACACIONES MODAL — History with Timeline Cards
// =============================================================================
async function openVacHistorial(empId, empName) {
    document.getElementById('vacHistName').textContent = empName;
    document.getElementById('vacHistorialModal').classList.remove('hidden');
    const content = document.getElementById('vacHistContent');
    content.innerHTML = '<div class="portal-loading"><div class="portal-spinner"></div><span>Cargando historial...</span></div>';

    try {
        const res = await fetch(`/api/planillas/vacaciones/${empId}`);
        const data = await res.json();
        const registros = data.registros || [];
        const acum = data.acumulados || 0;
        const tom = data.tomados || 0;
        const disp = data.disponibles || 0;
        const dispColor = disp > 0 ? '#10b981' : (disp < 0 ? '#ef4444' : '#94a3b8');

        // ── Hero Stats ──
        let html = `
        <div class="vhist-hero">
            <div class="vhist-hero-card vhist-hero-main" style="--accent:${dispColor};">
                <i class="fa-solid fa-calendar-check"></i>
                <span class="vhist-hero-val">${disp}</span>
                <span class="vhist-hero-lbl">Disponibles</span>
            </div>
            <div class="vhist-hero-card" style="--accent:#3b82f6;">
                <i class="fa-solid fa-calendar-plus"></i>
                <span class="vhist-hero-val">${acum}</span>
                <span class="vhist-hero-lbl">Acumulados</span>
            </div>
            <div class="vhist-hero-card" style="--accent:#f59e0b;">
                <i class="fa-solid fa-plane-departure"></i>
                <span class="vhist-hero-val">${tom}</span>
                <span class="vhist-hero-lbl">Disfrutados</span>
            </div>
        </div>`;

        // ── Empty State ──
        if (registros.length === 0) {
            html += `
            <div class="vhist-empty">
                <i class="fa-solid fa-sun" style="font-size:3rem;color:#f59e0b;opacity:0.3;"></i>
                <p>Este colaborador aún no tiene registros de vacaciones.</p>
                <button class="vac-btn vac-btn-primary" onclick="closeVacHistorial(); openRegistrarVacacion(${empId}, '${empName.replace(/'/g, "\\'")}')">
                    <i class="fa-solid fa-plus"></i> Registrar Primer Período
                </button>
            </div>`;
            content.innerHTML = html;
            return;
        }

        // ── Timeline ──
        html += '<div class="vhist-timeline">';
        for (const r of registros) {
            const escapedName = empName.replace(/'/g, "\\'");
            const notasEscaped = (r.notas || '').replace(/"/g, '&quot;').replace(/'/g, "\\'");
            html += `
            <div class="vhist-card" id="vhist-card-${r.id}">
                <div class="vhist-card-dot"></div>
                <div class="vhist-card-body">
                    <div class="vhist-card-header">
                        <div class="vhist-card-dates">
                            <span class="vhist-date-range">
                                <i class="fa-regular fa-calendar"></i>
                                ${_formatDateEs(r.fecha_inicio)} → ${_formatDateEs(r.fecha_fin)}
                            </span>
                            <span class="vhist-days-pill">${r.dias} día${r.dias !== 1 ? 's' : ''}</span>
                        </div>
                        <div class="vhist-card-menu">
                            <button class="vhist-btn-icon" onclick="editVacRecord(${r.id}, ${empId}, '${escapedName}')" title="Editar">
                                <i class="fa-solid fa-pen-to-square"></i>
                            </button>
                            <button class="vhist-btn-icon vhist-btn-danger" onclick="deleteVacRecord(${r.id}, ${empId}, '${escapedName}')" title="Eliminar">
                                <i class="fa-solid fa-trash-can"></i>
                            </button>
                        </div>
                    </div>
                    ${r.fecha_reingreso ? `<div class="vhist-reingreso"><i class="fa-solid fa-right-to-bracket"></i> Reingreso: ${_formatDateEs(r.fecha_reingreso)}</div>` : ''}
                    ${r.notas ? `<div class="vhist-notas"><i class="fa-solid fa-comment-dots"></i> ${r.notas}</div>` : ''}
                </div>
            </div>`;
        }
        html += '</div>';
        content.innerHTML = html;
    } catch (e) {
        content.innerHTML = `<div class="portal-error"><i class="fa-solid fa-circle-exclamation"></i> ${e.message}</div>`;
    }
}

function closeVacHistorial() {
    document.getElementById('vacHistorialModal').classList.add('hidden');
}

async function deleteVacRecord(vacId, empId, empName) {
    if (!confirm('¿Estás seguro de eliminar este registro de vacaciones?')) return;
    try {
        const res = await fetch(`/api/planillas/vacaciones/${vacId}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Error al eliminar');
        openVacHistorial(empId, empName);
        loadVacacionesTab();
    } catch (e) { alert(e.message); }
}

async function editVacRecord(vacId, empId, empName) {
    const card = document.getElementById(`vhist-card-${vacId}`);
    if (!card) return;
    const body = card.querySelector('.vhist-card-body');

    // Extract current data from the card
    const dateRange = card.querySelector('.vhist-date-range');
    const daysPill = card.querySelector('.vhist-days-pill');
    const reingreso = card.querySelector('.vhist-reingreso');
    const notas = card.querySelector('.vhist-notas');

    // We need to get the raw data, so let's fetch it
    try {
        const res = await fetch(`/api/planillas/vacaciones/${empId}`);
        const data = await res.json();
        const rec = (data.registros || []).find(r => r.id === vacId);
        if (!rec) return;

        const escapedName = empName.replace(/'/g, "\\'");
        body.innerHTML = `
            <div class="vhist-edit-form">
                <div class="vhist-edit-grid">
                    <div class="vhist-edit-field">
                        <label>Fecha Inicio</label>
                        <input type="date" id="editVacInicio-${vacId}" value="${rec.fecha_inicio || ''}">
                    </div>
                    <div class="vhist-edit-field">
                        <label>Fecha Fin</label>
                        <input type="date" id="editVacFin-${vacId}" value="${rec.fecha_fin || ''}">
                    </div>
                    <div class="vhist-edit-field">
                        <label>Días</label>
                        <input type="number" step="0.5" id="editVacDias-${vacId}" value="${rec.dias || 0}">
                    </div>
                    <div class="vhist-edit-field">
                        <label>Fecha Reingreso</label>
                        <input type="date" id="editVacReingreso-${vacId}" value="${rec.fecha_reingreso || ''}">
                    </div>
                </div>
                <div class="vhist-edit-field" style="margin-top:0.5rem;">
                    <label>Observaciones</label>
                    <textarea id="editVacNotas-${vacId}" rows="3" placeholder="Notas adicionales...">${rec.notas || ''}</textarea>
                </div>
                <div class="vhist-edit-actions">
                    <button class="vac-btn vac-btn-primary" onclick="saveVacEdit(${vacId}, ${empId}, '${escapedName}')">
                        <i class="fa-solid fa-check"></i> Guardar
                    </button>
                    <button class="vac-btn vac-btn-ghost" onclick="openVacHistorial(${empId}, '${escapedName}')">
                        <i class="fa-solid fa-xmark"></i> Cancelar
                    </button>
                </div>
            </div>`;
    } catch (e) { alert(e.message); }
}

async function saveVacEdit(vacId, empId, empName) {
    const data = {
        empleado_id: empId,
        fecha_inicio: document.getElementById(`editVacInicio-${vacId}`).value,
        fecha_fin: document.getElementById(`editVacFin-${vacId}`).value,
        dias: parseFloat(document.getElementById(`editVacDias-${vacId}`).value) || 0,
        fecha_reingreso: document.getElementById(`editVacReingreso-${vacId}`).value,
        notas: document.getElementById(`editVacNotas-${vacId}`).value
    };
    try {
        const res = await fetch(`/api/planillas/vacaciones/${vacId}`, {
            method: 'PUT', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) throw new Error('Error al actualizar');
        openVacHistorial(empId, empName);
        loadVacacionesTab();
    } catch (e) { alert(e.message); }
}

// ── Registro de Vacaciones (Modal) ──
function openRegistrarVacacion(empId, empName) {
    document.getElementById('vacEmpId').value = empId;
    document.getElementById('vacEmpName').textContent = empName;
    document.getElementById('vacFechaInicio').value = '';
    document.getElementById('vacFechaFin').value = '';
    document.getElementById('vacDias').value = '';
    document.getElementById('vacFechaReingreso').value = '';
    document.getElementById('vacNotas').value = '';
    document.getElementById('vacacionModal').classList.remove('hidden');
}

function closeRegistrarVacacion() {
    document.getElementById('vacacionModal').classList.add('hidden');
}

async function guardarVacacion() {
    const empId = document.getElementById('vacEmpId').value;
    const data = {
        empleado_id: parseInt(empId),
        fecha_inicio: document.getElementById('vacFechaInicio').value,
        fecha_fin: document.getElementById('vacFechaFin').value,
        dias: parseFloat(document.getElementById('vacDias').value) || 0,
        fecha_reingreso: document.getElementById('vacFechaReingreso').value,
        notas: document.getElementById('vacNotas').value
    };

    if (!data.fecha_inicio || !data.fecha_fin || data.dias <= 0) {
        alert('Por favor complete las fechas y asegúrese de que los días sean mayores a 0.');
        return;
    }

    try {
        const res = await fetch('/api/planillas/vacaciones', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Error al guardar');
        }
        closeRegistrarVacacion();
        loadVacacionesTab();
        alert('Vacación registrada exitosamente.');
    } catch (e) {
        alert(e.message);
    }
}

function autoCalcVacDias() {
    const inicio = document.getElementById('vacFechaInicio').value;
    const fin = document.getElementById('vacFechaFin').value;
    if (!inicio || !fin) return;

    const d1 = new Date(inicio);
    const d2 = new Date(fin);
    if (d2 < d1) return;

    // Calcular dias naturales totales
    let diff = Math.floor((d2 - d1) / (1000 * 60 * 60 * 24)) + 1;
    document.getElementById('vacDias').value = diff;

    // Calcular reingreso (dia despues del fin)
    const reingreso = new Date(d2);
    reingreso.setDate(reingreso.getDate() + 1);
    document.getElementById('vacFechaReingreso').value = reingreso.toISOString().split('T')[0];
}


// =============================================================================
// PERMISOS FUNCTIONS
// =============================================================================

async function openPermHistorial(empId, empName, anio) {
    document.getElementById('permHistEmpId').value = empId;
    document.getElementById('permHistEmpName').textContent = empName;
    const content = document.getElementById('permHistContent');
    content.innerHTML = '<div class="portal-loading"><div class="portal-spinner"></div><span>Cargando historial...</span></div>';
    document.getElementById('permHistorialModal').classList.remove('hidden');

    try {
        const res = await fetch(`/api/planillas/permisos/${empId}?anio=${anio}`);
        const data = await res.json();
        const permisos = data.permisos || [];

        if (permisos.length === 0) {
            content.innerHTML = '<div class="portal-empty"><i class="fa-solid fa-hand"></i><p>No hay permisos registrados en este año.</p></div>';
            return;
        }

        let html = '<div class="vhist-timeline">';
        
        permisos.forEach(p => {
            const isDescontado = p.descontado_de_vacaciones;
            const estadoColor = isDescontado ? '#10b981' : '#f59e0b';
            const estadoBg = isDescontado ? 'rgba(16, 185, 129, 0.15)' : 'rgba(245, 158, 11, 0.15)';
            const estadoLabel = isDescontado ? 'Descontado' : 'Pendiente';
            const estadoIcon = isDescontado ? 'fa-check-to-slot' : 'fa-hourglass-start';

            html += `
            <div class="vhist-card" id="perm-card-${p.id}">
                <div class="vhist-card-dot" style="background:${estadoColor}; box-shadow: 0 0 0 3px ${estadoBg}; border-color:var(--bg-panel);"></div>
                <div class="vhist-card-body">
                    <div class="vhist-card-header">
                        <div class="vhist-card-dates">
                            <span class="vhist-date-range">
                                <i class="fa-regular fa-calendar" style="color:${estadoColor};"></i>
                                ${_formatDateEs(p.fecha)}
                            </span>
                            <span class="vhist-days-pill" style="color:${estadoColor}; background:${estadoBg};">
                                <i class="fa-solid ${estadoIcon}"></i> ${estadoLabel}
                            </span>
                        </div>
                        <div class="vhist-card-menu">
                            <button class="vhist-btn-icon vhist-btn-danger" onclick="deletePermiso(${p.id}, ${isDescontado})" title="${isDescontado ? 'Eliminar y opcionalmente restaurar vacaciones' : 'Eliminar permiso'}">
                                <i class="fa-solid fa-trash-can"></i>
                            </button>
                        </div>
                    </div>
                    
                    <div style="margin-top:0.6rem;">
                        <span style="font-size:0.85rem; font-weight:600; color:var(--text-main);">
                            <i class="fa-solid fa-tag" style="color:var(--text-muted); font-size:0.75rem; margin-right:4px;"></i> 
                            ${p.motivo || 'Motivo no especificado'}
                        </span>
                    </div>

                    ${p.notas ? `
                    <div class="vhist-notas" style="margin-top:8px;">
                        <i class="fa-solid fa-comment-dots" style="color:#6366f1;"></i> 
                        <span style="white-space:pre-wrap;">${p.notas}</span>
                    </div>` : ''}
                </div>
            </div>`;
        });
        
        html += '</div>';
        content.innerHTML = html;
    } catch (e) {
        content.innerHTML = `<div class="portal-error"><i class="fa-solid fa-circle-exclamation"></i> Error al cargar historial: ${e.message}</div>`;
    }
}

function closePermHistorial() {
    document.getElementById('permHistorialModal').classList.add('hidden');
}

function openRegistrarPermiso(empId, empName) {
    document.getElementById('permEmpId').value = empId;
    document.getElementById('permEmpName').textContent = empName;
    document.getElementById('permFecha').value = '';
    document.getElementById('permMotivo').value = 'Personal';
    document.getElementById('permNotas').value = '';
    document.getElementById('permisoModal').classList.remove('hidden');
}

function closeRegistrarPermiso() {
    document.getElementById('permisoModal').classList.add('hidden');
}

async function guardarPermiso() {
    const empId = document.getElementById('permEmpId').value;
    const data = {
        empleado_id: parseInt(empId),
        fecha: document.getElementById('permFecha').value,
        motivo: document.getElementById('permMotivo').value,
        notas: document.getElementById('permNotas').value
    };

    if (!data.fecha) {
        alert('Por favor seleccione una fecha para el permiso.');
        return;
    }

    try {
        const res = await fetch('/api/planillas/permisos', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Error al guardar');
        }
        closeRegistrarPermiso();
        loadVacSubPermisos();
        if (typeof showToast === 'function') showToast('Permiso registrado', 'success');
        else alert('Permiso registrado exitosamente.');
    } catch (e) {
        alert(e.message);
    }
}

async function deletePermiso(permisoId, isDescontado) {
    if (!confirm('¿Está seguro de que desea eliminar este permiso del historial?')) return;
    
    let restaurar = false;
    if (isDescontado) {
        restaurar = confirm('Este permiso fue descontado de vacaciones.\n\n¿Desea RESTAURAR los días al saldo de vacaciones del empleado?\n[Aceptar] = Sí, restaurar\n[Cancelar] = No restaurar');
    }

    try {
        const res = await fetch(`/api/planillas/permisos/${permisoId}?restaurar=${restaurar}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Error al eliminar');
        loadVacSubPermisos();
        
        // Refresh modal if it's currently open
        const modal = document.getElementById('permHistorialModal');
        if (modal && !modal.classList.contains('hidden')) {
            const empId = document.getElementById('permHistEmpId').value;
            const empName = document.getElementById('permHistEmpName').textContent;
            openPermHistorial(empId, empName, new Date().getFullYear());
        }

        if (typeof showToast === 'function') showToast('Permiso eliminado (vacaciones restauradas si aplicaba)', 'success');
    } catch (e) { alert(e.message); }
}

async function descontarPermisos(empId, empName, pendientes, anio) {
    const cantidad = prompt(
        `${empName}: Tiene ${pendientes} permiso(s) pendiente(s) en ${anio}.\n` +
        `Estos dias se restaran de sus vacaciones.\n\n` +
        `Cuantos permisos desea descontar? (max ${pendientes})`,
        pendientes
    );
    if (cantidad === null) return;
    const cant = parseInt(cantidad);
    if (isNaN(cant) || cant <= 0 || cant > pendientes) {
        alert('Cantidad invalida.');
        return;
    }

    if (!confirm(`Confirmar: Descontar ${cant} dia(s) de permiso de las vacaciones de ${empName}?`)) return;

    try {
        const res = await fetch('/api/planillas/permisos/descontar-vacaciones', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ empleado_id: empId, cantidad: cant, anio })
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Error al descontar');
        }
        loadVacSubPermisos();
        if (typeof showToast === 'function') showToast(`${cant} permiso(s) descontados de vacaciones`, 'success');
        else alert(`${cant} permiso(s) descontados de vacaciones de ${empName}.`);
    } catch (e) { alert(e.message); }
}

// =============================================================================
// PRÉSTAMOS FUNCTIONS
// =============================================================================

async function openNuevoPrestamo() {
    // Build employee select
    const res = await fetch('/api/planillas/empleados');
    const emps = await res.json();
    const opts = emps.map(e => `<option value="${e.id}">${e.nombre}</option>`).join('');

    const content = document.getElementById('vacSubTabContent');
    content.innerHTML = `
    <div style="max-width:500px; margin:0 auto;">
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:1.5rem;">
            <button class="vac-btn vac-btn-ghost" onclick="loadVacSubPrestamos()" style="padding:6px 10px;">
                <i class="fa-solid fa-arrow-left"></i>
            </button>
            <h3 style="color:var(--text-main); margin:0;"><i class="fa-solid fa-hand-holding-dollar" style="color:#8b5cf6;"></i> Nuevo Préstamo</h3>
        </div>
        <div class="vac-emp-card" style="padding:1.5rem;">
            <div class="input-group" style="margin-bottom:1rem;">
                <label style="font-size:0.8rem; color:var(--text-muted); margin-bottom:4px; display:block;">Empleado</label>
                <select id="npEmpId" style="width:100%; padding:0.7rem; background:var(--bg-app); border:1px solid var(--border); color:var(--text-main); border-radius:8px;">
                    ${opts}
                </select>
            </div>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:1rem; margin-bottom:1rem;">
                <div class="input-group">
                    <label style="font-size:0.8rem; color:var(--text-muted); margin-bottom:4px; display:block;">Monto Total (₡)</label>
                    <input type="number" id="npMontoTotal" placeholder="Ej: 100000" oninput="calcNuevoPrestamo()"
                        style="width:100%; padding:0.7rem; background:var(--bg-app); border:1px solid var(--border); color:var(--text-main); border-radius:8px;">
                </div>
                <div class="input-group">
                    <label style="font-size:0.8rem; color:var(--text-muted); margin-bottom:4px; display:block;">Pago Semanal (₡)</label>
                    <input type="number" id="npPagoSemanal" placeholder="Ej: 10000" oninput="calcNuevoPrestamo()"
                        style="width:100%; padding:0.7rem; background:var(--bg-app); border:1px solid var(--border); color:var(--text-main); border-radius:8px;">
                </div>
            </div>
            <div id="npCalcPreview" style="display:none; background:rgba(139,92,246,0.08); border-radius:8px; padding:0.8rem; margin-bottom:1rem;">
            </div>
            <div class="input-group" style="margin-bottom:1rem;">
                <label style="font-size:0.8rem; color:var(--text-muted); margin-bottom:4px; display:block;">Notas (opcional)</label>
                <textarea id="npNotas" rows="2" placeholder="Observaciones..."
                    style="width:100%; padding:0.7rem; background:var(--bg-app); border:1px solid var(--border); color:var(--text-main); border-radius:8px; resize:vertical;"></textarea>
            </div>
            <div style="display:flex; gap:0.5rem;">
                <button class="vac-btn vac-btn-primary" style="flex:1; background:#8b5cf6;" onclick="guardarNuevoPrestamo()">
                    <i class="fa-solid fa-check"></i> Registrar Préstamo
                </button>
                <button class="vac-btn vac-btn-ghost" onclick="loadVacSubPrestamos()">Cancelar</button>
            </div>
        </div>
    </div>`;
}

function calcNuevoPrestamo() {
    const monto = parseFloat(document.getElementById('npMontoTotal').value) || 0;
    const pago = parseFloat(document.getElementById('npPagoSemanal').value) || 0;
    const box = document.getElementById('npCalcPreview');
    if (monto > 0 && pago > 0) {
        const semanas = Math.ceil(monto / pago);
        box.innerHTML = `
            <div style="display:flex; justify-content:space-between; font-size:0.85rem; color:var(--text-main);">
                <span><i class="fa-solid fa-calendar-week" style="color:#8b5cf6; margin-right:4px;"></i> Semanas estimadas</span>
                <strong>${semanas}</strong>
            </div>`;
        box.style.display = 'block';
    } else {
        box.style.display = 'none';
    }
}

async function guardarNuevoPrestamo() {
    const data = {
        empleado_id: parseInt(document.getElementById('npEmpId').value),
        monto_total: parseFloat(document.getElementById('npMontoTotal').value) || 0,
        pago_semanal: parseFloat(document.getElementById('npPagoSemanal').value) || 0,
        notas: document.getElementById('npNotas').value || null
    };
    if (!data.monto_total || !data.pago_semanal) return alert('Complete el monto total y pago semanal.');

    try {
        const res = await fetch('/api/planillas/prestamos', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) throw new Error('Error al registrar');
        loadVacSubPrestamos();
        if (typeof showToast === 'function') showToast('Préstamo registrado', 'success');
    } catch (e) { alert(e.message); }
}

async function registrarAbono(prestamoId, montoSugerido, empName, tipo) {
    let monto;
    if (tipo === 'extraordinario') {
        monto = prompt(`Abono extraordinario para ${empName}.\nIngrese el monto del abono:`);
        if (monto === null) return;
        monto = parseFloat(monto);
        if (isNaN(monto) || monto <= 0) return alert('Monto inválido.');
    } else {
        // planilla — confirmación manual con monto pre-llenado
        const confirmar = confirm(
            `¿Confirmar abono de planilla para ${empName}?\n\n` +
            `Monto: ₡${_fmtMoney(montoSugerido)}\n\n` +
            `Este abono se registrará como rebajo de planilla.`
        );
        if (!confirmar) return;
        monto = montoSugerido;
    }

    const notas = tipo === 'extraordinario' ? prompt('Nota para el abono extraordinario (opcional):') : null;

    try {
        const res = await fetch(`/api/planillas/prestamos/${prestamoId}/abono`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ monto, tipo, notas })
        });
        if (!res.ok) throw new Error('Error al registrar abono');
        const result = await res.json();
        loadVacSubPrestamos();
        if (typeof showToast === 'function') {
            showToast(`Abono ₡${_fmtMoney(monto)} registrado. Saldo: ₡${_fmtMoney(result.nuevo_saldo)}`, 'success');
        }
        if (result.estado === 'liquidado') {
            alert(`¡Préstamo de ${empName} LIQUIDADO! 🎉`);
        }
    } catch (e) { alert(e.message); }
}

async function verAbonosPrestamo(prestamoId, empName) {
    try {
        const res = await fetch(`/api/planillas/prestamos/${prestamoId}/abonos`);
        const data = await res.json();
        const abonos = data.abonos || [];
        const prest = data.prestamo;

        const content = document.getElementById('vacSubTabContent');
        let html = `
        <div style="max-width:600px; margin:0 auto;">
            <div style="display:flex; align-items:center; gap:10px; margin-bottom:1.5rem;">
                <button class="vac-btn vac-btn-ghost" onclick="loadVacSubPrestamos()" style="padding:6px 10px;">
                    <i class="fa-solid fa-arrow-left"></i>
                </button>
                <h3 style="color:var(--text-main); margin:0;">
                    <i class="fa-solid fa-list" style="color:#8b5cf6;"></i> Historial de Abonos — ${empName}
                </h3>
            </div>
            <div class="vac-emp-card" style="margin-bottom:1rem;">
                <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:0.5rem;">
                    <div style="text-align:center;">
                        <div style="font-size:0.65rem; color:var(--text-muted); text-transform:uppercase;">Total</div>
                        <div style="font-size:1.1rem; font-weight:800; color:var(--text-main);">₡${_fmtMoney(prest.monto_total)}</div>
                    </div>
                    <div style="text-align:center;">
                        <div style="font-size:0.65rem; color:var(--text-muted); text-transform:uppercase;">Abonado</div>
                        <div style="font-size:1.1rem; font-weight:800; color:#10b981;">₡${_fmtMoney(prest.monto_total - prest.saldo)}</div>
                    </div>
                    <div style="text-align:center;">
                        <div style="font-size:0.65rem; color:var(--text-muted); text-transform:uppercase;">Saldo</div>
                        <div style="font-size:1.1rem; font-weight:800; color:#ef4444;">₡${_fmtMoney(prest.saldo)}</div>
                    </div>
                </div>
            </div>`;

        if (abonos.length === 0) {
            html += '<p style="text-align:center; color:var(--text-muted); padding:2rem;">No hay abonos registrados aún.</p>';
        } else {
            html += `
            <div class="vac-emp-card" style="padding:0; overflow:hidden;">
                <table style="width:100%; font-size:0.82rem; border-collapse:collapse;">
                    <thead><tr style="background:rgba(255,255,255,0.03); color:var(--text-muted); font-size:0.7rem; text-transform:uppercase; letter-spacing:0.5px;">
                        <th style="text-align:left; padding:10px 12px;">Fecha</th>
                        <th style="text-align:right; padding:10px 12px;">Monto</th>
                        <th style="text-align:center; padding:10px 12px;">Tipo</th>
                        <th style="text-align:left; padding:10px 12px;">Notas</th>
                    </tr></thead>
                    <tbody>
                    ${abonos.map(a => `
                    <tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
                        <td style="padding:8px 12px; color:var(--text-main);">${_formatDateEs(a.fecha)}</td>
                        <td style="padding:8px 12px; text-align:right; font-weight:700; color:#10b981;">₡${_fmtMoney(a.monto)}</td>
                        <td style="padding:8px 12px; text-align:center;">
                            ${a.tipo === 'planilla' ? 
                                '<span style="background:rgba(139,92,246,0.15); color:#8b5cf6; padding:2px 8px; border-radius:5px; font-size:0.68rem; font-weight:600;">Planilla</span>' :
                                '<span style="background:rgba(245,158,11,0.15); color:#f59e0b; padding:2px 8px; border-radius:5px; font-size:0.68rem; font-weight:600;">Extraordinario</span>'
                            }
                        </td>
                        <td style="padding:8px 12px; color:var(--text-muted); font-size:0.75rem;">${a.notas || '—'}</td>
                    </tr>`).join('')}
                    </tbody>
                </table>
            </div>`;
        }

        html += '</div>';
        content.innerHTML = html;

    } catch (e) { alert(e.message); }
}

async function eliminarPrestamo(prestamoId, empName) {
    if (!confirm(`¿Eliminar el préstamo de ${empName}? Se eliminarán todos los abonos registrados.`)) return;
    try {
        const res = await fetch(`/api/planillas/prestamos/${prestamoId}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Error al eliminar');
        loadVacSubPrestamos();
        if (typeof showToast === 'function') showToast('Préstamo eliminado', 'success');
    } catch (e) { alert(e.message); }
}

// =============================================================================
// TAB: AGUINALDO
// =============================================================================
async function loadAguinaldoTab() {
    const tab = document.getElementById('tab-aguinaldo');
    const anioActual = new Date().getFullYear();
    let opts = '';
    for (let i = anioActual - 3; i <= anioActual + 1; i++) {
        opts += `<option value="${i}" ${i === anioActual ? 'selected' : ''}>${i}</option>`;
    }

    tab.innerHTML = `
        <div class="portal-view">
            <div class="portal-header">
                <div class="portal-header-left">
                    <div class="portal-title-row">
                        <div class="portal-icon-wrap" style="--accent: #f59e0b;">
                            <i class="fa-solid fa-gift"></i>
                        </div>
                        <div>
                            <h2 class="portal-title">Calculo de Aguinaldo</h2>
                            <p class="portal-subtitle">Proyeccion basada en planillas Excel</p>
                        </div>
                    </div>
                </div>
                <div class="portal-header-right" style="gap: 10px;">
                    <div class="portal-select-wrap">
                        <label>Ano</label>
                        <select id="aguiAnioSelect">${opts}</select>
                    </div>
                    <button class="portal-btn-ghost" id="btnSincronizarAguinaldo" onclick="sincronizarAguinaldo()" title="Sincronizar salarios desde el Excel actual">
                        <i class="fa-solid fa-rotate"></i> Sincronizar
                    </button>
                    <button class="portal-btn-primary" onclick="procesarAguinaldo()">
                        <i class="fa-solid fa-calculator"></i> Calcular
                    </button>
                </div>
            </div>
            <div id="aguinaldoResults">
                <div class="portal-empty-box">
                    <i class="fa-solid fa-gift"></i>
                    <p>Seleccione un ano y presione <strong>Calcular</strong></p>
                </div>
            </div>
        </div>`;
}

async function procesarAguinaldo() {
    const anio = document.getElementById('aguiAnioSelect').value;
    const resDiv = document.getElementById('aguinaldoResults');
    resDiv.innerHTML = '<div class="portal-loading"><div class="portal-spinner"></div><span>Calculando ' + anio + '...</span></div>';

    try {
        const res = await fetch(`/api/planillas/aguinaldo/${anio}`);
        const data = await res.json();

        if (data.status === 'error' || !data.data || data.data.length === 0) {
            resDiv.innerHTML = `<div class="portal-empty-box" style="border-color: rgba(239,68,68,0.3);"><i class="fa-solid fa-triangle-exclamation" style="color:#f87171;"></i><p>${data.message || 'No se encontraron registros para ' + anio}.</p></div>`;
            return;
        }

        let html = `
            <div class="agui-summary">
                <div class="agui-summary-left">
                    <div class="agui-summary-label">Resumen ${anio}</div>
                    <div class="agui-summary-sub">${data.meses_evaluados} meses evaluados · Salario Bruto</div>
                </div>
                <div class="agui-summary-right">
                    <div class="agui-summary-label">Total Aguinaldo Proyectado</div>
                    <div class="agui-total">₡${_money(data.total_aguinaldo)}</div>
                </div>
            </div>
            <div class="portal-table-wrap">
                <table class="ptable agui-table">
                    <thead><tr>
                        <th class="ptable-left">Colaborador</th>
                        <th>Cédula</th>
                        <th class="ptable-right">Sal. Bruto Anual</th>
                        <th class="ptable-right">Aguinaldo</th>
                        <th style="width:40px;"></th>
                    </tr></thead>
                    <tbody>`;

        data.data.forEach((row, idx) => {
            const op = row.aguinaldo > 0 ? ` style="animation:slideDown 0.3s ease both;animation-delay:${idx * 0.05}s;"` : ` style="opacity:0.45;animation:slideDown 0.3s ease both;animation-delay:${idx * 0.05}s;"`;
            const hasDesglose = row.desglose_mensual && row.desglose_mensual.length > 0;
            html += `<tr${op} class="agui-row-main" onclick="toggleAguiDesglose(${idx})">
                <td class="ptable-left">
                    <div class="ptable-person">
                        <div class="ptable-avatar" style="background:${_grad(row.id)};">${_initials(row.nombre)}</div>
                        <span class="ptable-name">${row.nombre}</span>
                    </div>
                </td>
                <td><span class="ptable-muted">${row.cedula || '--'}</span></td>
                <td class="ptable-right"><span class="ptable-mono">₡${_money(row.salario_anual)}</span></td>
                <td class="ptable-right"><span class="ptable-mono ptable-num-ok">₡${_money(row.aguinaldo)}</span></td>
                <td style="text-align:center;">
                    ${hasDesglose ? '<i class="fa-solid fa-chevron-down agui-chevron" id="agui-chev-' + idx + '" style="transition:transform 0.2s;font-size:0.7rem;color:var(--text-muted);"></i>' : ''}
                </td>
            </tr>`;

            // Expandable monthly breakdown row
            if (hasDesglose) {
                html += `<tr id="agui-detail-${idx}" class="agui-detail-row" style="display:none;">
                    <td colspan="5" style="padding:0;">
                        <div class="agui-desglose">
                            <div class="agui-desglose-title"><i class="fa-solid fa-chart-bar"></i> Desglose Mensual — Salario Bruto</div>
                            <div class="agui-desglose-grid">`;
                row.desglose_mensual.forEach(m => {
                    html += `<div class="agui-mes-item">
                        <span class="agui-mes-label">${m.mes}</span>
                        <span class="agui-mes-val">₡${_money(m.bruto)}</span>
                    </div>`;
                });
                html += `
                            </div>
                            <div class="agui-desglose-calc">
                                <span>Cálculo: ₡${_money(row.salario_anual)} ÷ 12 = <strong style="color:#10b981;">₡${_money(row.aguinaldo)}</strong></span>
                            </div>
                        </div>
                    </td>
                </tr>`;
            }
        });

        html += '</tbody></table></div>';
        resDiv.innerHTML = html;
    } catch (e) {
        resDiv.innerHTML = `<div class="portal-error"><i class="fa-solid fa-circle-exclamation"></i> ${e.message}</div>`;
    }
}

async function sincronizarAguinaldo() {
    const anio = document.getElementById('aguiAnioSelect').value;
    if (!confirm(`¿Sincronizar los salarios del año ${anio} desde el Excel actual?\nEsto buscará todas las hojas de semana y guardará los sueldos brutos en la base de datos.`)) return;

    const btn = document.getElementById('btnSincronizarAguinaldo');
    const originalHTML = btn ? btn.innerHTML : null;
    if (btn) {
        btn.classList.add('syncing');
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-rotate"></i> Sincronizando...';
    }

    try {
        const res = await fetch(`/api/planillas/sincronizar-aguinaldo/${anio}`, { method: 'POST' });
        const data = await res.json();
        if (data.status === 'success') {
            showToast(data.message || `Salarios ${anio} sincronizados`, 'success');
            procesarAguinaldo();
        } else {
            showToast('Error: ' + data.message, 'error');
        }
    } catch (e) {
        showToast(e.message, 'error');
    } finally {
        if (btn) {
            btn.classList.remove('syncing');
            btn.disabled = false;
            btn.innerHTML = originalHTML;
        }
    }
}

function toggleAguiDesglose(idx) {
    const row = document.getElementById(`agui-detail-${idx}`);
    const chev = document.getElementById(`agui-chev-${idx}`);
    if (!row) return;
    if (row.style.display === 'none') {
        row.style.display = '';
        if (chev) chev.style.transform = 'rotate(180deg)';
    } else {
        row.style.display = 'none';
        if (chev) chev.style.transform = '';
    }
}


// =============================================================================
// TAB: PLANILLA MENSUAL
// =============================================================================
async function loadPlanillaMensualTab() {
    const tab = document.getElementById('tab-planilla-mensual');
    tab.innerHTML = `
        <div class="portal-view">
            <div class="portal-header">
                <div class="portal-header-left">
                    <div class="portal-title-row">
                        <div class="portal-icon-wrap" style="--accent: #10b981;">
                            <i class="fa-solid fa-file-invoice-dollar"></i>
                        </div>
                        <div>
                            <h2 class="portal-title">Gestión de Planilla</h2>
                            <p class="portal-subtitle" id="pmensualSubtitle">Cargando mes activo...</p>
                        </div>
                    </div>
                </div>
                <div class="portal-header-right" id="pmensualActions" style="gap: 10px;">
                    <!-- Actions will be injected here -->
                </div>
            </div>
            <div id="pmensualContent">
                <div class="portal-loading"><div class="portal-spinner"></div><span>Cargando datos...</span></div>
            </div>
        </div>`;

    try {
        const res = await fetch('/api/planillas/meses/activo');
        const data = await res.json();

        const content = document.getElementById('pmensualContent');
        const actions = document.getElementById('pmensualActions');
        const subtitle = document.getElementById('pmensualSubtitle');

        // Always show the Tarifas and Historial buttons
        let actionsHtml = `
            <button class="btn-action" onclick="abrirPlanillasHistorial()"><i class="fa-solid fa-clock-rotate-left"></i> Historial</button>
            <button class="btn-action" onclick="abrirConfigTarifas()"><i class="fa-solid fa-cog"></i> Tarifas</button>
        `;

        if (!data.mes) {
            subtitle.textContent = "Ningún mes activo";
            actionsHtml += `<button class="btn-action primary" onclick="abrirNuevoMes()"><i class="fa-solid fa-plus"></i> Iniciar Mes</button>`;
            actions.innerHTML = actionsHtml;
            content.innerHTML = `
                <div class="portal-empty-box" style="margin-top: 40px; padding: 60px 20px;">
                    <i class="fa-solid fa-folder-open" style="font-size: 3rem; color: var(--text-muted); opacity:0.3; margin-bottom: 20px;"></i>
                    <h3 style="color: var(--text-main); font-size: 1.2rem; margin-bottom: 10px;">No hay una planilla activa</h3>
                    <p style="color: var(--text-muted); max-width: 400px; margin: 0 auto;">Inicia un nuevo mes para generar el archivo maestro de Excel y comenzar a agregar semanas.</p>
                    <button class="btn-action primary" style="margin-top: 25px;" onclick="abrirNuevoMes()"><i class="fa-solid fa-file-excel"></i> Crear Planilla</button>
                </div>`;
            return;
        }

        const mes = data.mes;
        const semanas = data.semanas || [];

        // Month is active
        const meses_nombres = {
            1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
            5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
            9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
        };
        const mName = meses_nombres[mes.mes] || mes.mes;
        subtitle.textContent = `Archivo activo: Planilla_${mName}_${mes.anio}.xlsx`;

        // Action Buttons
        actionsHtml += `
            <button class="btn-action" onclick="abrirBoletas(${mes.id})"><i class="fa-solid fa-image"></i> Boletas (WA)</button>
            <button class="btn-action" style="color: #10b981; border-color: rgba(16,185,129,0.3);" onclick="abrirExcel()"><i class="fa-solid fa-file-excel"></i> Ver Excel</button>
            <button class="btn-action primary" onclick="abrirNuevaSemana()"><i class="fa-solid fa-plus"></i> Añadir Semana</button>
        `;
        actions.innerHTML = actionsHtml;

        let html = `
            <div class="portal-table-wrap" style="margin-bottom: 30px;">
                <table class="ptable">
                    <thead><tr>
                        <th class="ptable-left">Semana</th>
                        <th>Fecha Inicial (Viernes)</th>
                        <th>Registro</th>
                        <th>Acción</th>
                    </tr></thead>
                    <tbody>`;

        if (semanas.length === 0) {
            html += `<tr><td colspan="4" style="text-align:center; padding: 30px; color: var(--text-muted);">No se han agregado semanas a este mes.</td></tr>`;
        } else {
            // Save weeks for the global reference
            window.activeSemanas = semanas;

            semanas.forEach(s => {
                html += `
                    <tr style="animation:slideDown 0.3s ease both;animation-delay:${semanas.indexOf(s) * 0.07}s;">
                        <td class="ptable-left"><strong>Semana ${s.num_semana}</strong></td>
                        <td><span class="ptable-pill" style="background: rgba(59,130,246,0.1); color: #3b82f6;">${s.viernes}</span></td>
                        <td><span class="ptable-muted">${new Date(s.fecha_agregada).toLocaleDateString()}</span></td>
                        <td>
                            <button class="btn-action" class="btn-sm-blue" style="margin-right:5px;" onclick="abrirImportarHorarioModal(${s.id}, ${s.num_semana})">
                                <i class="fa-solid fa-download"></i> Importar
                            </button>
                            <button class="btn-action" class="btn-sm-red" onclick="eliminarSemana(${s.id}, ${s.num_semana})">
                                <i class="fa-solid fa-trash"></i> Eliminar
                            </button>
                        </td>
                    </tr>`;
            });
        }

        html += `</tbody></table></div>`;

        // Month Summary & Close
        html += `
            <div class="agui-summary" style="background: var(--bg-panel); border: 1px solid var(--border);">
                <div class="agui-summary-left">
                    <div class="agui-summary-label" style="color: var(--text-main);">Mes Actual: ${mName} ${mes.anio}</div>
                    <div class="agui-summary-sub">Semanas registradas: ${semanas.length}</div>
                </div>
                <div class="agui-summary-right" style="display:flex; gap: 10px; align-items:center;">
                    <span style="font-size:0.8rem; color: var(--text-muted); text-align:right;">Al cerrar el mes se considerará<br>listo para el Aguinaldo.</span>
                    <button class="btn-action primary" style="background: #ef4444;" onclick="cerrarMes(${mes.id}, '${mName} ${mes.anio}')">
                        <i class="fa-solid fa-lock"></i> Cerrar Mes
                    </button>
                </div>
            </div>`;

        content.innerHTML = html;

    } catch (e) {
        document.getElementById('pmensualContent').innerHTML = `<div class="portal-error"><i class="fa-solid fa-circle-exclamation"></i> ${e.message}</div>`;
    }
}

// ---------------------------
// TARIFAS
// ---------------------------
async function abrirConfigTarifas() {
    try {
        const res = await fetch('/api/planillas/tarifas');
        const t = await res.json();
        document.getElementById('cfgTarifaDiurna').value = t.tarifa_diurna;
        document.getElementById('cfgTarifaMixta').value = t.tarifa_mixta;
        document.getElementById('cfgTarifaNocturna').value = t.tarifa_nocturna;
        document.getElementById('cfgTarifaSeguro').value = t.seguro;
        document.getElementById('planillaConfigModal').classList.remove('hidden');
    } catch (e) { alert("Error al cargar tarifas."); }
}

function closeTarifasModal() {
    document.getElementById('planillaConfigModal').classList.add('hidden');
}

async function guardarTarifas() {
    const data = {
        tarifa_diurna: parseFloat(document.getElementById('cfgTarifaDiurna').value),
        tarifa_mixta: parseFloat(document.getElementById('cfgTarifaMixta').value),
        tarifa_nocturna: parseFloat(document.getElementById('cfgTarifaNocturna').value),
        seguro: parseFloat(document.getElementById('cfgTarifaSeguro').value)
    };
    try {
        const res = await fetch('/api/planillas/tarifas', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) throw new Error("Error guardando tarifas");
        closeTarifasModal();
    } catch (e) { alert(e.message); }
}

// ---------------------------
// MESES
// ---------------------------
function abrirNuevoMes() {
    const date = new Date();
    document.getElementById('nuevoMesAnio').value = date.getFullYear();
    document.getElementById('nuevoMesSel').value = date.getMonth() + 1;
    document.getElementById('nuevoMesModal').classList.remove('hidden');
}

function closeNuevoMesModal() {
    document.getElementById('nuevoMesModal').classList.add('hidden');
}

async function crearNuevoMes() {
    const data = {
        anio: parseInt(document.getElementById('nuevoMesAnio').value),
        mes: parseInt(document.getElementById('nuevoMesSel').value)
    };
    try {
        const res = await fetch('/api/planillas/meses', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail);
        }
        closeNuevoMesModal();
        loadPlanillaMensualTab();
    } catch (e) { alert(e.message); }
}

async function cerrarMes(id, nombre) {
    if (!confirm(`¿Estás seguro que deseas cerrar el mes de ${nombre}? Ya no podrás agregar más semanas.`)) return;
    try {
        const res = await fetch(`/api/planillas/meses/${id}/cerrar`, { method: 'POST' });
        if (!res.ok) throw new Error("Error al cerrar");
        loadPlanillaMensualTab();
    } catch (e) { alert(e.message); }
}

async function abrirExcel() {
    try {
        const res = await fetch('/api/planillas/excel/abrir');
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail);
        }
    } catch (e) { alert(e.message); }
}

// ---------------------------
// SEMANAS
// ---------------------------
function abrirNuevaSemana() {
    document.getElementById('nuevaSemanaFecha').value = "";
    document.getElementById('nuevaSemanaModal').classList.remove('hidden');
}

function closeNuevaSemanaModal() {
    document.getElementById('nuevaSemanaModal').classList.add('hidden');
}

async function guardarNuevaSemana() {
    const v = document.getElementById('nuevaSemanaFecha').value;
    if (!v) return alert('Debes seleccionar la fecha del Viernes');

    // We get the mes_id by re-fetching or implicitly saving it (which we omitted for brevity, lets fetch from api)
    try {
        const actRes = await fetch('/api/planillas/meses/activo');
        const actData = await actRes.json();
        if (!actData.mes) throw new Error("No hay mes activo");

        const data = { mes_id: actData.mes.id, viernes: v };

        // Show loading state implicitly by disabling button
        const btn = document.querySelector('#nuevaSemanaModal .btn-action.primary');
        let prevText = "";
        if (btn) {
            prevText = btn.innerHTML;
            btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Generando...`;
            btn.disabled = true;
        }

        const res = await fetch('/api/planillas/semanas', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (btn) {
            btn.innerHTML = prevText;
            btn.disabled = false;
        }

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail);
        }

        closeNuevaSemanaModal();
        loadPlanillaMensualTab();
    } catch (e) { alert(e.message); }
}

async function eliminarSemana(id, num) {
    if (!confirm(`¿Eliminar la Semana ${num}? Se borrará del Excel también.`)) return;
    try {
        const res = await fetch(`/api/planillas/semanas/${id}`, { method: 'DELETE' });
        if (!res.ok) throw new Error("Error al eliminar");
        loadPlanillaMensualTab();
    } catch (e) { alert(e.message); }
}

// ---------------------------
// BOLETAS JPEGS
// ---------------------------
function abrirBoletas() {
    const semanas = window.activeSemanas || [];
    if (semanas.length === 0) return alert("No hay semanas en este mes para generar boletas.");

    const sel = document.getElementById('boletaSemanaSel');
    sel.innerHTML = semanas.map(s => `<option value="Semana ${s.num_semana}">Semana ${s.num_semana} (${s.viernes})</option>`).join('');

    document.getElementById('boletasModal').classList.remove('hidden');
}

function closeBoletasModal() {
    document.getElementById('boletasModal').classList.add('hidden');
}

async function ejecutarBoletas() {
    const semName = document.getElementById('boletaSemanaSel').value;

    const btn = document.querySelector('#boletasModal .btn-action.primary');
    let prevText = "";
    if (btn) {
        prevText = btn.innerHTML;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Procesando...`;
        btn.disabled = true;
    }

    try {
        const res = await fetch('/api/planillas/boletas/generar', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ semana_nombre: semName })
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail);
        }

        const data = await res.json();
        alert(data.message);
        closeBoletasModal();
    } catch (e) {
        alert(e.message);
    } finally {
        if (btn) {
            btn.innerHTML = prevText;
            btn.disabled = false;
        }
    }
}

// =============================================================================
// IMPORTAR HORARIO
// =============================================================================
async function abrirImportarHorarioModal(semanaId, numSemana) {
    document.getElementById('importSemanaId').value = semanaId;
    const nombreSemana = `Semana ${numSemana}`;
    document.getElementById('importSemanaTxt').value = nombreSemana;
    document.getElementById('importSemanaNombreLbl').textContent = nombreSemana;
    document.getElementById('importSyncEmps').checked = true;

    try {
        const res = await fetch('/api/planillas/horarios-disponibles');
        if (!res.ok) throw new Error("No se pudo cargar los horarios");
        const data = await res.json();

        const sel = document.getElementById('importHorarioSel');
        sel.innerHTML = '';
        if (data.horarios && data.horarios.length > 0) {
            data.horarios.forEach(h => {
                const opt = document.createElement('option');
                opt.value = h.id;
                opt.textContent = `${h.nombre}  (${h.timestamp.substring(0, 10)})`;
                sel.appendChild(opt);
            });
            document.getElementById('importarHorarioModal').classList.remove('hidden');
        } else {
            alert("No hay horarios generados disponibles para importar.");
        }
    } catch (e) {
        alert(e.message);
    }
}

function closeImportarHorarioModal() {
    document.getElementById('importarHorarioModal').classList.add('hidden');
}

async function ejecutarImportarHorario() {
    const semName = document.getElementById('importSemanaTxt').value;
    const horarioId = document.getElementById('importHorarioSel').value;
    const syncEmps = document.getElementById('importSyncEmps').checked;

    if (!horarioId) return alert("Selecciona un horario válido.");

    const btn = document.querySelector('#importarHorarioModal .btn-action.primary');
    let prevText = "";
    if (btn) {
        prevText = btn.innerHTML;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Importando...`;
        btn.disabled = true;
    }

    try {
        const res = await fetch('/api/planillas/semanas/importar', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                horario_id: parseInt(horarioId),
                semana_nombre: semName,
                sync_empleados: syncEmps
            })
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail);
        }

        const data = await res.json();
        alert(data.message);
        closeImportarHorarioModal();
    } catch (e) {
        alert(e.message);
    } finally {
        if (btn) {
            btn.innerHTML = prevText;
            btn.disabled = false;
        }
    }
}

// =============================================================================
// TAB: UTILIDADES — GENERADOR DE DOCUMENTOS WORD
// =============================================================================
let _utilEmpleados = [];

async function loadUtilidadesTab() {
    const tab = document.getElementById('tab-utilidades');
    try {
        const res = await fetch('/api/planillas/empleados');
        _utilEmpleados = await res.json();
    } catch (e) { _utilEmpleados = []; }

    const empOptions = _utilEmpleados.map(e => `<option value="${e.id}">${_esc(e.nombre)} ${e.cedula ? '(' + _esc(e.cedula) + ')' : ''}</option>`).join('');

    tab.innerHTML = `
        <div class="portal-view">
            <div class="portal-header">
                <div class="portal-header-left">
                    <div class="portal-title-row">
                        <div class="portal-icon-wrap" style="--accent: #f59e0b;">
                            <i class="fa-solid fa-toolbox"></i>
                        </div>
                        <div>
                            <h2 class="portal-title">Utilidades</h2>
                            <p class="portal-subtitle">Genera documentos Word de acciones de empleado</p>
                        </div>
                    </div>
                </div>
            </div>

            <div class="util-cards-grid">
                <!-- Card 1: Préstamo -->
                <div class="util-card" onclick="showUtilForm('prestamo')">
                    <div class="util-card-icon" style="background: linear-gradient(135deg, #6366f1, #8b5cf6);">
                        <i class="fa-solid fa-hand-holding-dollar"></i>
                    </div>
                    <h3>Contrato de Préstamo</h3>
                    <p>Genera un contrato con monto, pago semanal y fecha de liquidación</p>
                </div>

                <!-- Card 2: Amonestación -->
                <div class="util-card" onclick="showUtilForm('amonestacion')">
                    <div class="util-card-icon" style="background: linear-gradient(135deg, #ef4444, #f97316);">
                        <i class="fa-solid fa-triangle-exclamation"></i>
                    </div>
                    <h3>Carta de Amonestación</h3>
                    <p>Detalla faltantes con fecha y monto en una carta formal</p>
                </div>

                <!-- Card 3: Vacaciones -->
                <div class="util-card" onclick="showUtilForm('vacaciones')">
                    <div class="util-card-icon" style="background: linear-gradient(135deg, #10b981, #14b8a6);">
                        <i class="fa-solid fa-umbrella-beach"></i>
                    </div>
                    <h3>Constancia de Vacaciones</h3>
                    <p>Genera una constancia con fechas, tipo y cálculo automático de días</p>
                </div>

                <!-- Card 4: Carta de Despido -->
                <div class="util-card" onclick="showUtilForm('despido')">
                    <div class="util-card-icon" style="background: linear-gradient(135deg, #3b82f6, #2563eb);">
                        <i class="fa-solid fa-user-xmark"></i>
                    </div>
                    <h3>Carta de Despido</h3>
                    <p>Genera la carta de despido con el cálculo de liquidación (aguinaldo y vacaciones)</p>
                </div>

                <!-- Card 5: Carta de Renuncia -->
                <div class="util-card" onclick="showUtilForm('renuncia')">
                    <div class="util-card-icon" style="background: linear-gradient(135deg, #8b5cf6, #d946ef);">
                        <i class="fa-solid fa-file-signature"></i>
                    </div>
                    <h3>Aceptación de Renuncia</h3>
                    <p>Documenta la renuncia voluntaria con los rubros a cancelar al colaborador</p>
                </div>

                <!-- Card 6: Carta de Recomendación -->
                <div class="util-card" onclick="showUtilForm('recomendacion')">
                    <div class="util-card-icon" style="background: linear-gradient(135deg, #06b6d4, #0ea5e9);">
                        <i class="fa-solid fa-award"></i>
                    </div>
                    <h3>Carta de Recomendación</h3>
                    <p>Genera una carta de recomendación genérica para el colaborador seleccionado</p>
                </div>
            </div>

            <!-- ========== FORMS (hidden by default) ========== -->


            <!-- PRÉSTAMO FORM -->
            <div id="util-form-prestamo" class="util-form-panel hidden">
                <div class="util-form-header">
                    <h3><i class="fa-solid fa-hand-holding-dollar" style="color:#8b5cf6;"></i> Contrato de Préstamo</h3>
                    <button class="util-form-close" onclick="hideUtilForm('prestamo')">&times;</button>
                </div>
                <div class="util-form-body">
                    <div class="input-group">
                        <label>Empleado</label>
                        <select id="utilPrestamoEmp">${empOptions}</select>
                    </div>
                    <div class="input-row">
                        <div class="input-group">
                            <label>Monto Total (₡)</label>
                            <input type="number" id="utilPrestamoMonto" placeholder="Ej: 50000" oninput="calcPrestamo()">
                        </div>
                        <div class="input-group">
                            <label>Pago Semanal (₡)</label>
                            <input type="number" id="utilPrestamoPago" placeholder="Ej: 5000" oninput="calcPrestamo()">
                        </div>
                    </div>
                    <div id="utilPrestamoCalc" class="util-calc-box" style="display:none;"></div>
                    <button class="btn-action primary" onclick="generarPrestamo()" style="margin-top: 1rem; width: 100%;">
                        <i class="fa-solid fa-file-word"></i> Generar Documento
                    </button>
                </div>
            </div>

            <!-- AMONESTACIÓN FORM -->
            <div id="util-form-amonestacion" class="util-form-panel hidden">
                <div class="util-form-header">
                    <h3><i class="fa-solid fa-triangle-exclamation" style="color:#ef4444;"></i> Carta de Amonestación</h3>
                    <button class="util-form-close" onclick="hideUtilForm('amonestacion')">&times;</button>
                </div>
                <div class="util-form-body">
                    <div class="input-row">
                        <div class="input-group" style="flex:2;">
                            <label>Empleado</label>
                            <select id="utilAmonestacionEmp">${empOptions}</select>
                        </div>
                        <div class="input-group" style="flex:1;">
                            <label>Tipo de Amonestación</label>
                            <select id="utilAmonestacionTipo" onchange="toggleAmonestacionCampos()">
                                <option value="faltantes">Por Faltantes</option>
                                <option value="tardanzas">Llegadas Tardías</option>
                                <option value="conductas">Conductas Inapropiadas</option>
                            </select>
                        </div>
                    </div>
                    
                    <div id="utilAmonestacionDynamic">
                        <label style="font-weight:600; margin-top: 1rem; display:block;" id="amoDynamicLabel">Faltantes</label>
                        <div id="faltantesRows"></div>
                        <button class="btn-action" onclick="addFaltanteRow()" style="margin-top: 0.5rem;" id="amoDynamicBtn">
                            <i class="fa-solid fa-plus"></i> Agregar Registro
                        </button>
                    </div>

                    <button class="btn-action primary" onclick="generarAmonestacion()" style="margin-top: 1rem; width: 100%;">
                        <i class="fa-solid fa-file-word"></i> Generar Documento
                    </button>
                </div>
            </div>

            <!-- VACACIONES FORM -->
            <div id="util-form-vacaciones" class="util-form-panel hidden">
                <div class="util-form-header">
                    <h3><i class="fa-solid fa-umbrella-beach" style="color:#10b981;"></i> Constancia de Vacaciones</h3>
                    <button class="util-form-close" onclick="hideUtilForm('vacaciones')">&times;</button>
                </div>
                <div class="util-form-body">
                    <div class="input-group">
                        <label>Empleado</label>
                        <select id="utilVacacionesEmp" onchange="checkVacDisponibles()">${empOptions}</select>
                    </div>
                    <div id="utilVacDispWarn" style="display:none;padding:0.5rem;margin-top:0.5rem;border-radius:6px;background:rgba(239,68,68,0.15);color:#f87171;font-size:0.85rem;"></div>
                    <div class="input-group" style="margin-top:0.8rem;">
                        <label>Tipo de Vacaciones</label>
                        <select id="utilVacTipo">
                            <option value="total">Goce Total</option>
                            <option value="parcial">Goce Parcial</option>
                        </select>
                    </div>
                    <div class="input-row">
                        <div class="input-group">
                            <label>Fecha de Inicio</label>
                            <input type="date" id="utilVacInicio" onchange="calcVacDias()">
                        </div>
                        <div class="input-group">
                            <label>Fecha de Reingreso</label>
                            <input type="date" id="utilVacReingreso" onchange="calcVacDias()">
                        </div>
                    </div>
                    <div id="utilVacCalc" class="util-calc-box" style="display:none;"></div>
                    <button class="btn-action primary" onclick="generarVacaciones()" style="margin-top: 1rem; width: 100%;">
                        <i class="fa-solid fa-file-word"></i> Generar Documento
                    </button>
                </div>
            </div>

            <!-- DESPIDO FORM -->
            <div id="util-form-despido" class="util-form-panel hidden">
                <div class="util-form-header">
                    <h3><i class="fa-solid fa-user-xmark" style="color:#3b82f6;"></i> Carta de Despido</h3>
                    <button class="util-form-close" onclick="hideUtilForm('despido')">&times;</button>
                </div>
                <div class="util-form-body">
                    <div class="input-group">
                        <label>Empleado</label>
                        <select id="utilDespidoEmp" onchange="autoFillLiquidacion('despido')">${empOptions}</select>
                    </div>
                    <div id="utilDespidoInfo" class="util-calc-box" style="display:none;margin-top:0.5rem;"></div>
                    
                    <div class="input-row" style="margin-top:1rem;">
                        <div class="input-group">
                            <label>Días Vacaciones a Pagar</label>
                            <input type="number" step="0.5" id="utilDespidoVacDias" placeholder="Ej: 5" oninput="calcLiquidacion('despido')">
                        </div>
                        <div class="input-group">
                            <label>Monto Vacaciones (₡)</label>
                            <input type="number" id="utilDespidoVacMonto" placeholder="Ej: 35000" oninput="calcLiquidacion('despido')">
                        </div>
                    </div>
                    
                    <div class="input-row">
                        <div class="input-group">
                            <label>Monto Aguinaldo (₡)</label>
                            <input type="number" id="utilDespidoAguinaldo" placeholder="Ej: 150000" oninput="calcLiquidacion('despido')">
                        </div>
                        <div class="input-group">
                            <label>Auxilio Cesantía (₡)</label>
                            <input type="number" id="utilDespidoCesantia" placeholder="Auto-calc" oninput="calcLiquidacion('despido')">
                        </div>
                    </div>
                    
                    <div class="input-row">
                        <div class="input-group">
                            <label>Preaviso (₡)</label>
                            <input type="number" id="utilDespidoPreaviso" placeholder="Auto-calc" oninput="calcLiquidacion('despido')">
                        </div>
                        <div class="input-group">
                            <label>Modo de Pago</label>
                            <select id="utilDespidoModo">
                                <option value="Pago Total">Pago Total Inmediato</option>
                                <option value="Abonos Parciales">Acuerdo de Abonos</option>
                            </select>
                        </div>
                    </div>

                    <div id="utilDespidoCalc" class="util-calc-box" style="display:block;">
                        <div class="util-calc-row"><span>Total a Liquidar</span><strong style="color:red;font-size:1.1rem" id="utilDespidoTotal">₡0.00</strong></div>
                    </div>

                    <button class="btn-action primary" onclick="generarLiquidacion('despido')" style="margin-top: 1rem; width: 100%;">
                        <i class="fa-solid fa-file-word"></i> Generar Carta Despido
                    </button>
                </div>
            </div>

            <!-- RENUNCIA FORM -->
            <div id="util-form-renuncia" class="util-form-panel hidden">
                <div class="util-form-header">
                    <h3><i class="fa-solid fa-file-signature" style="color:#8b5cf6;"></i> Aceptación de Renuncia</h3>
                    <button class="util-form-close" onclick="hideUtilForm('renuncia')">&times;</button>
                </div>
                <div class="util-form-body">
                    <div class="input-group">
                        <label>Empleado</label>
                        <select id="utilRenunciaEmp" onchange="autoFillLiquidacion('renuncia')">${empOptions}</select>
                    </div>
                    <div id="utilRenunciaInfo" class="util-calc-box" style="display:none;margin-top:0.5rem;"></div>
                    
                    <div class="input-row" style="margin-top:1rem;">
                        <div class="input-group">
                            <label>Días Vacaciones a Pagar</label>
                            <input type="number" step="0.5" id="utilRenunciaVacDias" placeholder="Ej: 5" oninput="calcLiquidacion('renuncia')">
                        </div>
                        <div class="input-group">
                            <label>Monto Vacaciones (₡)</label>
                            <input type="number" id="utilRenunciaVacMonto" placeholder="Ej: 35000" oninput="calcLiquidacion('renuncia')">
                        </div>
                    </div>
                    
                    <div class="input-row">
                        <div class="input-group">
                            <label>Monto Aguinaldo (₡)</label>
                            <input type="number" id="utilRenunciaAguinaldo" placeholder="Ej: 150000" oninput="calcLiquidacion('renuncia')">
                        </div>
                        <div class="input-group">
                            <label>Modo de Pago</label>
                            <select id="utilRenunciaModo">
                                <option value="Pago Total">Pago Total Inmediato</option>
                                <option value="Abonos Parciales">Acuerdo de Abonos</option>
                            </select>
                        </div>
                    </div>

                    <div id="utilRenunciaCalc" class="util-calc-box" style="display:block;">
                        <div class="util-calc-row"><span>Total a Liquidar</span><strong style="color:red;font-size:1.1rem" id="utilRenunciaTotal">₡0.00</strong></div>
                    </div>

                    <button class="btn-action primary" onclick="generarLiquidacion('renuncia')" style="margin-top: 1rem; width: 100%;">
                        <i class="fa-solid fa-file-word"></i> Generar Aceptación
                    </button>
                </div>
            </div>

            <!-- RECOMENDACIÓN FORM -->
            <div id="util-form-recomendacion" class="util-form-panel hidden">
                <div class="util-form-header">
                    <h3><i class="fa-solid fa-award" style="color:#06b6d4;"></i> Carta de Recomendación</h3>
                    <button class="util-form-close" onclick="hideUtilForm('recomendacion')">&times;</button>
                </div>
                <div class="util-form-body">
                    <div class="input-group">
                        <label>Empleado</label>
                        <select id="utilRecomendacionEmp">${empOptions}</select>
                    </div>
                    <div class="input-group" style="margin-top:0.8rem;">
                        <label>Puesto / Cargo</label>
                        <input type="text" id="utilRecomendacionPuesto" placeholder="Ej: Despachador de combustible">
                    </div>
                    <div class="input-group" style="margin-top:0.8rem;">
                        <label>Texto adicional (opcional)</label>
                        <textarea id="utilRecomendacionTexto" rows="3" placeholder="Texto personalizado que se incluirá en la carta..." style="width:100%;padding:8px;background:var(--bg-app);color:var(--text-main);border:1px solid var(--border);border-radius:8px;resize:vertical;"></textarea>
                    </div>
                    <button class="btn-action primary" onclick="generarRecomendacion()" style="margin-top: 1rem; width: 100%;">
                        <i class="fa-solid fa-file-word"></i> Generar Carta
                    </button>
                </div>
            </div>

        </div>
    `;
    // Init amonestacion with one empty row
    addAmonestacionRow();
}

function showUtilForm(type) {
    // Hide all form panels first
    document.querySelectorAll('.util-form-panel').forEach(p => p.classList.add('hidden'));
    const panel = document.getElementById(`util-form-${type}`);
    if (panel) {
        panel.classList.remove('hidden');
        panel.style.animation = 'none';
        panel.offsetHeight; // trigger reflow
        panel.style.animation = 'slideDown 0.3s ease-out';

        // Ensure the panel is visible in viewport without locking scroll
        setTimeout(() => {
            panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }, 50);
    }
}

function hideUtilForm(type) {
    document.getElementById(`util-form-${type}`)?.classList.add('hidden');
}

// ── Préstamo Calc ──
function calcPrestamo() {
    const monto = parseFloat(document.getElementById('utilPrestamoMonto').value) || 0;
    const pago = parseFloat(document.getElementById('utilPrestamoPago').value) || 0;
    const box = document.getElementById('utilPrestamoCalc');
    if (monto > 0 && pago > 0) {
        const semanas = Math.ceil(monto / pago);
        const fecha = new Date();
        fecha.setDate(fecha.getDate() + semanas * 7);
        box.innerHTML = `
            <div class="util-calc-row"><span>Semanas estimadas</span><strong>${semanas}</strong></div>
            <div class="util-calc-row"><span>Fecha de liquidación</span><strong>${fecha.toLocaleDateString('es-CR')}</strong></div>
        `;
        box.style.display = 'block';
    } else {
        box.style.display = 'none';
    }
}

async function generarPrestamo() {
    const data = {
        emp_id: parseInt(document.getElementById('utilPrestamoEmp').value),
        monto_total: parseFloat(document.getElementById('utilPrestamoMonto').value) || 0,
        pago_semanal: parseFloat(document.getElementById('utilPrestamoPago').value) || 0,
    };
    if (!data.monto_total || !data.pago_semanal) return alert('Completa los campos de monto.');
    try {
        const res = await fetch('/api/utilidades/prestamo', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data)
        });
        if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
        alert('✅ Documento de Préstamo generado exitosamente.');
    } catch (e) { alert('Error: ' + e.message); }
}

// ── Amonestación ──
let _amoCount = 0;

function toggleAmonestacionCampos() {
    const tipo = document.getElementById('utilAmonestacionTipo').value;
    const dynamicDiv = document.getElementById('utilAmonestacionDynamic');
    const label = document.getElementById('amoDynamicLabel');
    const container = document.getElementById('faltantesRows');
    const btn = document.getElementById('amoDynamicBtn');

    // Clear current rows
    container.innerHTML = '';
    _amoCount = 0;

    if (tipo === 'faltantes') {
        dynamicDiv.style.display = 'block';
        label.innerText = 'Faltantes Registrados';
        btn.innerHTML = '<i class="fa-solid fa-plus"></i> Agregar Faltante';
        addAmonestacionRow();
    } else if (tipo === 'tardanzas') {
        dynamicDiv.style.display = 'block';
        label.innerText = 'Llegadas Tardías';
        btn.innerHTML = '<i class="fa-solid fa-plus"></i> Agregar Tardanza';
        addAmonestacionRow();
    } else if (tipo === 'conductas') {
        // Conductas does not require any dynamic rows
        dynamicDiv.style.display = 'none';
    }
}

function addAmonestacionRow() {
    const container = document.getElementById('faltantesRows');
    const tipo = document.getElementById('utilAmonestacionTipo').value;
    if (!container) return;
    _amoCount++;
    const row = document.createElement('div');
    row.className = 'faltante-row';
    row.id = `amo-row-${_amoCount}`;

    if (tipo === 'faltantes') {
        row.innerHTML = `
            <div class="input-row" style="align-items:flex-end; gap: 8px;">
                <div class="input-group" style="flex:1;">
                    <label>Fecha</label>
                    <input type="date" class="amo-fecha">
                </div>
                <div class="input-group" style="flex:1;">
                    <label>Monto (₡)</label>
                    <input type="number" class="amo-val" placeholder="Ej: 15000">
                </div>
                <button class="btn-action danger" style="height:42px; min-width:42px; padding: 0 10px;" onclick="this.closest('.faltante-row').remove()">
                    <i class="fa-solid fa-trash"></i>
                </button>
            </div>
        `;
    } else if (tipo === 'tardanzas') {
        row.innerHTML = `
            <div class="input-row" style="align-items:flex-end; gap: 8px;">
                <div class="input-group" style="flex:1;">
                    <label>Fecha</label>
                    <input type="date" class="amo-fecha">
                </div>
                <div class="input-group" style="flex:1;">
                    <label>Minutos Tarde</label>
                    <input type="number" class="amo-val" placeholder="Ej: 15">
                </div>
                <button class="btn-action danger" style="height:42px; min-width:42px; padding: 0 10px;" onclick="this.closest('.faltante-row').remove()">
                    <i class="fa-solid fa-trash"></i>
                </button>
            </div>
        `;
    }
    container.appendChild(row);
}

async function generarAmonestacion() {
    const empId = parseInt(document.getElementById('utilAmonestacionEmp').value);
    const tipo = document.getElementById('utilAmonestacionTipo').value;
    const datos = [];

    if (tipo !== 'conductas') {
        const rows = document.querySelectorAll('.faltante-row');
        rows.forEach(r => {
            const fecha = r.querySelector('.amo-fecha').value;
            const val = parseFloat(r.querySelector('.amo-val').value) || 0;
            if (fecha && val > 0) {
                if (tipo === 'faltantes') {
                    datos.push({ fecha, monto: val });
                } else if (tipo === 'tardanzas') {
                    datos.push({ fecha, minutos: val });
                }
            }
        });
        if (datos.length === 0) return alert('Agrega al menos un registro válido para esta amonestación.');
    }

    try {
        const res = await fetch('/api/utilidades/amonestacion', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ emp_id: empId, tipo: tipo, datos: datos })
        });
        if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
        alert('✅ Carta de Amonestación generada exitosamente.');
    } catch (e) { alert('Error: ' + e.message); }
}

// ── Liquidación (Despido / Renuncia) ──
function _cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

function calcLiquidacion(formType) {
    const p = `util${_cap(formType)}`;
    const vMonto = parseFloat(document.getElementById(`${p}VacMonto`).value) || 0;
    const aMonto = parseFloat(document.getElementById(`${p}Aguinaldo`).value) || 0;
    let total = vMonto + aMonto;

    // Despido includes cesantía + preaviso
    if (formType === 'despido') {
        const cMonto = parseFloat(document.getElementById(`${p}Cesantia`).value) || 0;
        const pMonto = parseFloat(document.getElementById(`${p}Preaviso`).value) || 0;
        total += cMonto + pMonto;
    }

    const label = document.getElementById(`${p}Total`);
    if (label) {
        label.innerText = `₡${total.toLocaleString('es-CR', { minimumFractionDigits: 2 })}`;
    }
}

async function autoFillLiquidacion(formType) {
    const p = `util${_cap(formType)}`;
    const empId = parseInt(document.getElementById(`${p}Emp`).value);
    if (!empId) return;

    const infoBox = document.getElementById(`${p}Info`);
    if (infoBox) {
        infoBox.style.display = 'block';
        infoBox.innerHTML = '<span style="color:var(--text-dim);font-size:0.85rem;">⏳ Calculando liquidación...</span>';
    }

    try {
        const res = await fetch(`/api/planillas/liquidacion/${empId}`);
        const d = await res.json();

        // Fill form fields
        document.getElementById(`${p}VacDias`).value = d.vacaciones_dias || 0;
        document.getElementById(`${p}VacMonto`).value = d.vacaciones_monto || 0;
        document.getElementById(`${p}Aguinaldo`).value = d.aguinaldo_monto || 0;

        if (formType === 'despido') {
            document.getElementById(`${p}Cesantia`).value = d.cesantia_monto || 0;
            document.getElementById(`${p}Preaviso`).value = d.preaviso_monto || 0;
        }

        // Info box
        if (infoBox) {
            infoBox.innerHTML = `
                <div class="util-calc-row"><span>Antigüedad</span><strong>${d.antiguedad_anios || 0} años</strong></div>
                <div class="util-calc-row"><span>Sal. Promedio Mensual</span><strong>₡${(d.salario_promedio_mensual || 0).toLocaleString('es-CR', { minimumFractionDigits: 2 })}</strong></div>
                <div class="util-calc-row"><span>Tarifa Diurna/h</span><strong>₡${(d.tarifa_diurna || 0).toLocaleString('es-CR', { minimumFractionDigits: 2 })}</strong></div>
            `;
        }

        calcLiquidacion(formType);
    } catch (e) {
        if (infoBox) infoBox.innerHTML = '<span style="color:#f87171;">Error al calcular</span>';
    }
}

async function generarLiquidacion(formType) {
    const p = `util${_cap(formType)}`;
    const empId = parseInt(document.getElementById(`${p}Emp`).value);
    const vDias = parseFloat(document.getElementById(`${p}VacDias`).value) || 0;
    const vMonto = parseFloat(document.getElementById(`${p}VacMonto`).value) || 0;
    const aMonto = parseFloat(document.getElementById(`${p}Aguinaldo`).value) || 0;
    const modo = document.getElementById(`${p}Modo`).value;

    let cMonto = 0, pMonto = 0;
    if (formType === 'despido') {
        cMonto = parseFloat(document.getElementById(`${p}Cesantia`).value) || 0;
        pMonto = parseFloat(document.getElementById(`${p}Preaviso`).value) || 0;
    }

    const total = vMonto + aMonto + cMonto + pMonto;

    if (total <= 0) {
        if (!confirm('El total a pagar es ₡0. ¿Estás seguro de continuar con la generación del documento?')) return;
    }

    const data = {
        emp_id: empId,
        vacaciones_dias: vDias,
        vacaciones_monto: vMonto,
        aguinaldo_monto: aMonto,
        cesantia_monto: cMonto,
        preaviso_monto: pMonto,
        total_pagar: total,
        modo_pago: modo
    };

    try {
        const res = await fetch(`/api/utilidades/${formType}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data)
        });
        if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
        alert(`✅ Documento de ${_cap(formType)} generado exitosamente.`);
    } catch (e) { alert('Error: ' + e.message); }
}

// ── Carta de Recomendación ──
async function generarRecomendacion() {
    const empId = parseInt(document.getElementById('utilRecomendacionEmp').value);
    const puesto = document.getElementById('utilRecomendacionPuesto').value.trim();
    const textoAdicional = document.getElementById('utilRecomendacionTexto').value.trim();

    if (!puesto) {
        alert('Por favor ingresa el puesto o cargo del colaborador.');
        return;
    }

    try {
        const res = await fetch('/api/utilidades/recomendacion', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ emp_id: empId, puesto, texto_adicional: textoAdicional })
        });
        if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
        alert('✅ Carta de Recomendación generada exitosamente.');
    } catch (e) { alert('Error: ' + e.message); }
}

// ── Constancia Vacaciones: validar disponibles ──
async function checkVacDisponibles() {
    const empId = parseInt(document.getElementById('utilVacacionesEmp').value);
    const warn = document.getElementById('utilVacDispWarn');
    const btn = document.querySelector('#util-form-vacaciones .btn-action.primary');
    if (!empId) return;
    try {
        const res = await fetch(`/api/planillas/vacaciones/${empId}`);
        const data = await res.json();
        const disp = data.disponibles || 0;
        if (disp <= 0) {
            warn.style.display = 'block';
            warn.innerHTML = `<i class="fa-solid fa-triangle-exclamation"></i> Este empleado tiene <strong>0 días disponibles</strong>. No se puede generar constancia.`;
            if (btn) btn.disabled = true;
        } else {
            warn.style.display = 'block';
            warn.innerHTML = `<i class="fa-solid fa-check-circle" style="color:#10b981;"></i> Días disponibles: <strong style="color:#10b981;">${disp}</strong>`;
            if (btn) btn.disabled = false;
        }
    } catch (e) {
        warn.style.display = 'none';
        if (btn) btn.disabled = false;
    }
}


// ── Vacaciones ──
function calcVacDias() {
    const inicio = document.getElementById('utilVacInicio').value;
    const reingreso = document.getElementById('utilVacReingreso').value;
    const box = document.getElementById('utilVacCalc');
    if (inicio && reingreso) {
        const dias = Math.round((new Date(reingreso) - new Date(inicio)) / (1000 * 60 * 60 * 24));
        box.innerHTML = `<div class="util-calc-row"><span>Días totales</span><strong>${dias}</strong></div>`;
        box.style.display = 'block';
    } else {
        box.style.display = 'none';
    }
}

async function generarVacaciones() {
    const data = {
        emp_id: parseInt(document.getElementById('utilVacacionesEmp').value),
        tipo: document.getElementById('utilVacTipo').value,
        fecha_inicio: document.getElementById('utilVacInicio').value,
        fecha_reingreso: document.getElementById('utilVacReingreso').value,
    };
    if (!data.fecha_inicio || !data.fecha_reingreso) return alert('Selecciona ambas fechas.');
    try {
        const res = await fetch('/api/utilidades/vacaciones', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data)
        });
        if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
        alert('✅ Constancia de Vacaciones generada exitosamente.');
    } catch (e) { alert('Error: ' + e.message); }
}

// =============================================================================
// DEFAULT TAB ON LOAD
// =============================================================================
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(() => switchMainTab('gestion'), 100);
});

// =============================================================================
// HISTORIAL DE PLANILLAS
// =============================================================================

function closePlanillasHistorial() {
    document.getElementById('planillaHistorialModal').classList.add('hidden');
}

async function abrirPlanillasHistorial() {
    document.getElementById('planillaHistorialModal').classList.remove('hidden');
    const content = document.getElementById('planillaHistContent');
    content.innerHTML = '<div class="portal-loading"><div class="portal-spinner"></div><span>Cargando historial...</span></div>';

    try {
        const res = await fetch('/api/planillas/meses');
        const meses = await res.json();

        if (!meses || meses.length === 0) {
            content.innerHTML = `
                <div class="portal-empty-box" style="margin-top: 20px;">
                    <i class="fa-solid fa-folder-open" style="font-size: 2rem; color: var(--text-muted); opacity:0.3; margin-bottom: 10px;"></i>
                    <p>No hay planillas registradas en el historial.</p>
                </div>`;
            return;
        }

        const meses_nombres = {
            1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
            5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
            9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
        };

        let html = '<div style="display: flex; flex-direction: column; gap: 1rem;">';

        meses.forEach((m, idx) => {
            const mName = meses_nombres[m.mes] || m.mes;
            const statusColor = m.cerrado ? "#ef4444" : "#10b981";
            const statusText = m.cerrado ? "Cerrado" : "Activa";
            const statusIcon = m.cerrado ? "fa-lock" : "fa-lock-open";
            const cantSemanas = m.semanas ? m.semanas.length : 0;
            const semanasJson = _esc(JSON.stringify(m.semanas || []));

            // Rows for semanas (collapsed by default)
            let semanasHtml = '';
            if (m.semanas && m.semanas.length > 0) {
                m.semanas.forEach(s => {
                    semanasHtml += `
                    <div class="hist-sem-row" id="hist-sem-${s.id}">
                        <span class="hist-sem-num"><i class="fa-solid fa-calendar-week"></i> Semana ${s.num_semana}</span>
                        <span class="ptable-pill" style="background:rgba(59,130,246,0.1);color:#3b82f6;font-size:0.8rem;">${s.viernes}</span>
                        <button class="btn-action" class="btn-sm-green"
                            onclick="abrirImportarHorarioHistorico(${m.id}, 'Semana ${s.num_semana}', '${mName} ${m.anio}')">
                            <i class="fa-solid fa-file-import"></i> Importar
                        </button>
                        <button class="btn-action" class="btn-sm-red"
                            onclick="eliminarSemanaHistorial(${s.id}, ${m.id}, '${mName} ${m.anio}')">
                            <i class="fa-solid fa-trash"></i>
                        </button>
                    </div>`;
                });
            } else {
                semanasHtml = '<p style="color:var(--text-muted);font-size:0.82rem;padding:8px 0;margin:0;">No hay semanas registradas.</p>';
            }

            html += `
            <div class="option-card hover-glow hist-mes-card" style="padding: 0; flex-direction: column; align-items: stretch;">
                <!-- HEADER row (always visible) -->
                <div style="display:flex;align-items:center;gap:12px;padding:1rem;">
                    <div class="opt-icon" style="background: rgba(59, 130, 246, 0.1); color: #3b82f6; width: 44px; height: 44px; font-size: 1.2rem; flex-shrink:0;">
                        <i class="fa-solid fa-file-excel"></i>
                    </div>
                    <div style="flex:1;min-width:0;">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;flex-wrap:wrap;gap:6px;">
                            <strong style="font-size:1.05rem;">${mName} ${m.anio}</strong>
                            <span style="font-size:0.75rem;padding:3px 8px;border-radius:12px;background:${statusColor}15;color:${statusColor};font-weight:600;">
                                <i class="fa-solid ${statusIcon}"></i> ${statusText}
                            </span>
                        </div>
                        <div style="font-size:0.8rem;color:var(--text-muted);">
                            <i class="fa-solid fa-calendar-week"></i> ${cantSemanas} Semana(s)
                        </div>
                    </div>
                    <!-- Action buttons -->
                    <div style="display:flex;flex-direction:column;gap:6px;flex-shrink:0;">
                        <button class="btn-action" class="btn-sm-green" onclick="abrirExcelHistorico(${m.id})">
                            <i class="fa-solid fa-file-excel"></i> Abrir
                        </button>
                        <button class="btn-action hist-toggle-btn"  onclick="toggleHistSemanas(${m.id})">
                            <i class="fa-solid fa-chevron-down" id="hist-chev-${m.id}" style="transition:transform 0.2s;"></i> Editar
                        </button>
                        ${m.cerrado ? `
                        <button class="btn-action" class="btn-sm-red" onclick="eliminarMesHistorial(${m.id}, '${mName} ${m.anio}')">
                            <i class="fa-solid fa-trash-can"></i> Eliminar
                        </button>` : ''}
                    </div>
                </div>

                <!-- EXPANDABLE semanas panel -->
                <div id="hist-semanas-${m.id}" style="display:none;border-top:1px solid var(--border);padding:0.75rem 1rem 1rem;">
                    <div class="hist-sem-list" id="hist-sem-list-${m.id}">
                        ${semanasHtml}
                    </div>
                    <!-- Add semana form -->
                    <div style="display:flex;align-items:center;gap:8px;margin-top:0.75rem;padding-top:0.75rem;border-top:1px solid var(--border);">
                        <label style="font-size:0.82rem;color:var(--text-muted);white-space:nowrap;">Agregar semana:</label>
                        <input type="date" id="hist-nueva-sem-${m.id}"
                            style="flex:1;padding:0.4rem 0.6rem;font-size:0.82rem;background:var(--bg-app);border:1px solid var(--border);color:var(--text-main);border-radius:6px;">
                        <button class="btn-action primary" style="font-size:0.8rem;padding:0.4rem 0.7rem;white-space:nowrap;"
                            onclick="agregarSemanaHistorial(${m.id}, '${mName} ${m.anio}')">
                            <i class="fa-solid fa-plus"></i> Agregar
                        </button>
                    </div>
                </div>
            </div>`;
        });

        html += '</div>';
        content.innerHTML = html;

    } catch (e) {
        content.innerHTML = `<div class="portal-error"><i class="fa-solid fa-circle-exclamation"></i> Error cargando historial: ${e.message}</div>`;
    }
}

function toggleHistSemanas(mesId) {
    const panel = document.getElementById(`hist-semanas-${mesId}`);
    const chev = document.getElementById(`hist-chev-${mesId}`);
    if (!panel) return;
    const isOpen = panel.style.display !== 'none';
    panel.style.display = isOpen ? 'none' : 'block';
    if (chev) chev.style.transform = isOpen ? '' : 'rotate(180deg)';
}

async function eliminarSemanaHistorial(semanaId, mesId, mesNombre) {
    if (!confirm(`¿Eliminar esta semana de la planilla "${mesNombre}"?
Se borrará del Excel también.`)) return;
    try {
        const res = await fetch(`/api/planillas/semanas/${semanaId}`, { method: 'DELETE' });
        if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
        // Refresh just this month's semana list
        const data = await res.json();
        const listEl = document.getElementById(`hist-sem-list-${mesId}`);
        if (listEl) {
            const semanas = data.semanas || [];
            if (semanas.length === 0) {
                listEl.innerHTML = '<p style="color:var(--text-muted);font-size:0.82rem;padding:8px 0;margin:0;">No hay semanas registradas.</p>';
            } else {
                listEl.innerHTML = semanas.map(s => `
                    <div class="hist-sem-row" id="hist-sem-${s.id}">
                        <span class="hist-sem-num"><i class="fa-solid fa-calendar-week"></i> Semana ${s.num_semana}</span>
                        <span class="ptable-pill" style="background:rgba(59,130,246,0.1);color:#3b82f6;font-size:0.8rem;">${s.viernes}</span>
                        <button class="btn-action" class="btn-sm-green"
                            onclick="abrirImportarHorarioHistorico(${mesId}, 'Semana ${s.num_semana}', '${mesNombre}')">
                            <i class="fa-solid fa-file-import"></i> Importar
                        </button>
                        <button class="btn-action" class="btn-sm-red"
                            onclick="eliminarSemanaHistorial(${s.id}, ${mesId}, '${mesNombre}')">
                            <i class="fa-solid fa-trash"></i>
                        </button>
                    </div>`).join('');
            }
        }
        loadPlanillaMensualTab();
    } catch (e) { alert('Error: ' + e.message); }
}

async function agregarSemanaHistorial(mesId, mesNombre) {
    const input = document.getElementById(`hist-nueva-sem-${mesId}`);
    const viernes = input ? input.value : '';
    if (!viernes) return alert('Selecciona la fecha del Viernes.');

    const btn = input ? input.nextElementSibling : null;
    let prevText = '';
    if (btn) { prevText = btn.innerHTML; btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>'; btn.disabled = true; }

    try {
        const res = await fetch(`/api/planillas/meses/${mesId}/semanas`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mes_id: mesId, viernes })
        });
        if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
        const data = await res.json();

        // Refresh semana list in the panel
        const listEl = document.getElementById(`hist-sem-list-${mesId}`);
        if (listEl && data.semanas) {
            listEl.innerHTML = data.semanas.map(s => `
                <div class="hist-sem-row" id="hist-sem-${s.id}">
                    <span class="hist-sem-num"><i class="fa-solid fa-calendar-week"></i> Semana ${s.num_semana}</span>
                    <span class="ptable-pill" style="background:rgba(59,130,246,0.1);color:#3b82f6;font-size:0.8rem;">${s.viernes}</span>
                    <button class="btn-action" class="btn-sm-red"
                        onclick="eliminarSemanaHistorial(${s.id}, ${mesId}, '${mesNombre}')">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </div>`).join('');
        }
        if (input) input.value = '';
        loadPlanillaMensualTab();
    } catch (e) {
        alert('Error: ' + e.message);
    } finally {
        if (btn) { btn.innerHTML = prevText; btn.disabled = false; }
    }
}

async function eliminarMesHistorial(mesId, mesNombre) {
    if (!confirm(`¿Eliminar la planilla "${mesNombre}" y TODAS sus semanas?

Esta acción borrará los registros de la base de datos y el archivo Excel.
Esta operación no se puede deshacer.`)) return;
    try {
        const res = await fetch(`/api/planillas/meses/${mesId}`, { method: 'DELETE' });
        if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
        abrirPlanillasHistorial(); // Reload the historial
        loadPlanillaMensualTab();
    } catch (e) { alert('Error al eliminar: ' + e.message); }
}

// ---------------------------------------------------------------------------
// Importar horario del generador a una semana de planilla histórica
// ---------------------------------------------------------------------------
async function abrirImportarHorarioHistorico(mesId, semanaNombre, mesNombre) {
    // Load available schedules from the generator DB
    let horarios = [];
    try {
        const r = await fetch('/api/planillas/horarios-disponibles');
        const d = await r.json();
        horarios = d.horarios || [];
    } catch (e) {
        alert('Error al cargar horarios: ' + e.message);
        return;
    }

    if (horarios.length === 0) {
        alert('No hay horarios guardados en el generador. Genera y guarda un horario primero.');
        return;
    }

    const options = horarios.map(h =>
        `<option value="${h.id}">${h.name} — ${h.timestamp ? h.timestamp.substring(0, 10) : ''}</option>`
    ).join('');

    // Build a simple inline modal
    const modalId = 'hist-import-modal';
    let existing = document.getElementById(modalId);
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = modalId;
    modal.className = 'modal-backdrop';
    modal.style.zIndex = '3000';
    modal.innerHTML = `
        <div class="modal-dialog">
            <div class="modal-header-simple">
                <h3><i class="fa-solid fa-file-import"></i> Importar Horario</h3>
                <button class="close-icon" onclick="document.getElementById('${modalId}').remove()">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            </div>
            <div class="modal-body-scroll">
                <p class="helper-text-sm" style="margin-bottom:12px;">
                    Importando a <strong>${semanaNombre}</strong> de <strong>${mesNombre}</strong>.
                    Se rellenarán las horas en el Excel de esa planilla.
                </p>
                <div class="input-group">
                    <label>Horario Generado</label>
                    <select id="hist-import-sel" style="width:100%;padding:0.7rem;background:var(--bg-app);border:1px solid var(--border);color:var(--text-main);border-radius:8px;">
                        ${options}
                    </select>
                </div>
                <div class="input-group" style="margin-top:12px;display:flex;align-items:center;gap:10px;">
                    <input type="checkbox" id="hist-import-sync" checked>
                    <label for="hist-import-sync" style="margin:0;cursor:pointer;color:var(--text-muted);font-size:0.9rem;">
                        Sincronizar nuevos empleados a planilla
                    </label>
                </div>
            </div>
            <div class="modal-actions-footer">
                <button class="btn-text" onclick="document.getElementById('${modalId}').remove()">Cancelar</button>
                <button class="btn-action primary" id="hist-import-btn" onclick="ejecutarImportarHorarioHistorico(${mesId}, '${semanaNombre}', '${mesNombre}')">
                    <i class="fa-solid fa-download"></i> Importar Horas
                </button>
            </div>
        </div>`;
    document.body.appendChild(modal);
}

async function ejecutarImportarHorarioHistorico(mesId, semanaNombre, mesNombre) {
    const horarioId = parseInt(document.getElementById('hist-import-sel').value);
    const syncEmps = document.getElementById('hist-import-sync').checked;
    const btn = document.getElementById('hist-import-btn');

    if (!horarioId) { alert('Selecciona un horario.'); return; }

    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Importando...';

    try {
        const url = `/api/planillas/meses/${mesId}/semanas/${encodeURIComponent(semanaNombre)}/importar`;
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ horario_id: horarioId, semana_nombre: semanaNombre, sync_empleados: syncEmps })
        });
        if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
        const data = await res.json();

        document.getElementById('hist-import-modal')?.remove();
        loadPlanillaMensualTab();
        showToast(data.message || 'Horario importado correctamente', 'success');
    } catch (e) {
        alert('Error al importar: ' + e.message);
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-download"></i> Importar Horas';
    }
}
async function abrirExcelHistorico(mesId) {
    try {
        const res = await fetch(`/api/planillas/excel/abrir/${mesId}`);
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Error abriendo archivo");
        }
    } catch (e) {
        alert(e.message);
    }
}


// =============================================================================
// OVERRIDE: buildDayCards — actualiza tarjetas en lugar de destruir/recrear.
// app.js hace grid.innerHTML = "" en cada selectPill(), lo que resetea el scroll.
// Esta versión remplaza solo el contenido interno de cada card existente.
// Como planillas_ui.js carga después de app.js, esta definición toma precedencia.
// =============================================================================
window.buildDayCards = function buildDayCards() {
    const grid = document.getElementById("dayCardsGrid");
    if (!grid) return;

    const existingCards = grid.querySelectorAll(".day-card");

    // Si no hay tarjetas aún, construir desde cero (primera renderización)
    if (existingCards.length === 0) {
        if (typeof DAYS === "undefined" || typeof getDayCardInfo === "undefined") return;
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
        return;
    }

    // Si ya existen, actualizar en lugar de recrear (preserva el scroll)
    existingCards.forEach(card => {
        const d = card.getAttribute("data-day");
        const sel = document.querySelector(`.shift-select[data-day="${d}"]`);
        const code = sel ? sel.value : "AUTO";
        const info = getDayCardInfo(code);

        // Actualizar clase sin remover el elemento del DOM
        card.className = `day-card ${info.cls}`;
        card.innerHTML = `
            <span class="dc-day-label">${d}</span>
            <i class="fa-solid ${info.icon} dc-icon"></i>
            <span class="dc-shift-label">${info.label}</span>
        `;
        // Reattach onclick (se pierde al cambiar innerHTML)
        card.onclick = () => openPillPanel(d, card);
    });
};


// Override switchTab: la versión de app.js nunca activa el botón de la tab,
// solo el contenido. Esta versión también resalta el botón correcto.
window.switchTab = function switchTab(id) {
    document.querySelectorAll(".m-tab-content").forEach(c => c.classList.remove("active"));
    document.querySelectorAll(".m-tab").forEach(btn => {
        const target = btn.getAttribute("onclick")?.match(/switchTab\('([^']+)'\)/)?.[1];
        btn.classList.toggle("active", target === id);
    });
    const content = document.getElementById(id);
    if (content) content.classList.add("active");
};

// =============================================================================
// TAB: INVENTARIO
// =============================================================================
let inventarioBaseState = { articulos: [], config: null };

async function loadInventarioTab() {
    const tab = document.getElementById('tab-inventario');
    tab.innerHTML = `
        <div class="portal-view">
            <div class="portal-header">
                <div class="portal-header-left">
                    <div class="portal-title-row">
                        <div class="portal-icon-wrap" style="--accent: #8b5cf6;">
                            <i class="fa-solid fa-boxes-stacked"></i>
                        </div>
                        <div>
                            <h2 class="portal-title">Control de Inventario</h2>
                            <p class="portal-subtitle">Verificación de la carga contra una base editable</p>
                        </div>
                    </div>
                </div>
                <div class="portal-header-right">
                    <div class="portal-stat-chip" id="invCountChip">
                        <i class="fa-solid fa-box"></i> <span>--</span>
                    </div>
                </div>
            </div>

            <div class="inv-upload-zone" id="invUploadZone">
                <div class="inv-upload-inner">
                    <div class="inv-upload-icon">
                        <i class="fa-solid fa-cloud-arrow-up"></i>
                    </div>
                    <h3>Subir Excel de Inventario</h3>
                    <p>Arrastra tu archivo aquí o haz click para seleccionar</p>
                    <p class="inv-upload-hint">Formato: columnas con Nombre, Precio, Código, Existencias</p>
                    <input type="file" id="invFileInput" accept=".xlsx,.xls,.xlsm" style="display:none;" onchange="handleInventarioFile(this)">
                    <label for="invFileInput" class="portal-btn-primary" style="cursor:pointer;display:inline-flex;align-items:center;gap:6px;">
                        <i class="fa-solid fa-file-excel"></i> Examinar Archivo
                    </label>
                </div>
            </div>

            <div id="invBaseSection"></div>
            <div id="invDashboard"></div>
            <div id="invHistorySection"></div>
        </div>`;

    const zone = document.getElementById('invUploadZone');
    zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('inv-drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('inv-drag-over'));
    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('inv-drag-over');
        const files = e.dataTransfer.files;
        if (files.length > 0) uploadInventarioExcel(files[0]);
    });

    await loadInventarioBaseSection();
    await loadInventarioDashboard();
    await loadInventarioHistory();
}

async function loadInventarioBaseSection() {
    const section = document.getElementById('invBaseSection');
    if (!section) return;

    try {
        const res = await fetch('/api/inventario/base');
        inventarioBaseState = await res.json();
        const arts = inventarioBaseState.articulos || [];
        const sourcePath = inventarioBaseState.config?.source_path || '';

        section.innerHTML = `
            <div class="inv-base-card">
                <div class="inv-base-header">
                    <div>
                        <h3 class="inv-section-title"><i class="fa-solid fa-scale-balanced" style="color:#f59e0b;"></i> Base de Comparación</h3>
                        <p class="inv-base-subtitle">Se usa para validar el Excel subido y puedes ajustarla si cambian productos o cantidades.</p>
                    </div>
                    <div class="inv-base-actions">
                        <button class="portal-btn-primary" onclick="openInventarioBaseEditor()">
                            <i class="fa-solid fa-pen-to-square"></i> Editar Base
                        </button>
                        <button class="portal-btn-secondary inv-btn-soft" onclick="reimportInventarioBaseDefault()">
                            <i class="fa-solid fa-rotate"></i> Recargar Excel Base
                        </button>
                    </div>
                </div>
                <div class="inv-base-meta">
                    <span><i class="fa-solid fa-box"></i> ${arts.length} productos base</span>
                    <span><i class="fa-solid fa-file"></i> ${sourcePath || 'Base almacenada en la app'}</span>
                </div>
                <div class="inv-table-wrapper">
                    <table class="inv-table">
                        <thead>
                            <tr>
                                <th>Hoja</th>
                                <th>Código</th>
                                <th>Producto</th>
                                <th class="inv-th-num">Precio</th>
                                <th class="inv-th-num">Cantidad Base</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${arts.map(a => `
                                <tr>
                                    <td>${a.hoja_origen || 'Manual'}</td>
                                    <td class="inv-td-code">${a.codigo || '—'}</td>
                                    <td class="inv-td-name">${a.nombre}</td>
                                    <td class="inv-td-num">₡${_money(a.precio || 0)}</td>
                                    <td class="inv-td-num">${a.existencias_base ?? 0}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>`;
    } catch (e) {
        section.innerHTML = `<div class="portal-error"><i class="fa-solid fa-circle-exclamation"></i> ${e.message}</div>`;
    }
}

async function loadInventarioDashboard() {
    const dashboard = document.getElementById('invDashboard');
    if (!dashboard) return;

    try {
        const res = await fetch('/api/inventario/diff');
        const data = await res.json();

        if (!data.carga_actual) {
            dashboard.innerHTML = `
                <div class="inv-empty-state">
                    <i class="fa-solid fa-box-open"></i>
                    <p>No hay cargas de inventario aún.</p>
                    <p class="inv-empty-hint">Sube tu primer Excel para comenzar la verificación.</p>
                </div>`;
            document.querySelector('#invCountChip span').textContent = '0 artículos';
            return;
        }

        const r = data.resumen || {};
        const arts = data.articulos || [];
        document.querySelector('#invCountChip span').textContent = `${r.total_cargados || arts.length} artículos`;

        let html = `
            <div class="inv-date-header">
                <div class="inv-date-current">
                    <i class="fa-solid fa-calendar-day"></i>
                    <span>Carga actual: <strong>${_formatDateEs(data.carga_actual.fecha)}</strong></span>
                    <span class="inv-date-file">${data.carga_actual.archivo_nombre || ''}</span>
                </div>
                <div class="inv-date-arrow"><i class="fa-solid fa-arrow-right-arrow-left"></i></div>
                <div class="inv-date-prev">
                    <i class="fa-solid fa-scale-balanced"></i>
                    <span>Base: <strong>${r.total_base || 0} productos</strong></span>
                </div>
            </div>

            <div class="inv-stats-grid">
                <div class="inv-stat-card" style="--stat-color: #8b5cf6;">
                    <div class="inv-stat-icon"><i class="fa-solid fa-boxes-stacked"></i></div>
                    <div class="inv-stat-val">${r.total_cargados || 0}</div>
                    <div class="inv-stat-label">En Carga</div>
                </div>
                <div class="inv-stat-card" style="--stat-color: #10b981;">
                    <div class="inv-stat-icon"><i class="fa-solid fa-check-double"></i></div>
                    <div class="inv-stat-val">${r.coinciden || 0}</div>
                    <div class="inv-stat-label">Coinciden</div>
                </div>
                <div class="inv-stat-card" style="--stat-color: #ef4444;">
                    <div class="inv-stat-icon"><i class="fa-solid fa-triangle-exclamation"></i></div>
                    <div class="inv-stat-val">${r.con_diferencia || 0}</div>
                    <div class="inv-stat-label">Con Diferencia</div>
                </div>
                <div class="inv-stat-card" style="--stat-color: #f59e0b;">
                    <div class="inv-stat-icon"><i class="fa-solid fa-ban"></i></div>
                    <div class="inv-stat-val">${r.faltantes_en_carga || 0}</div>
                    <div class="inv-stat-label">Faltan en Excel</div>
                </div>
            </div>`;

        const topDiffs = arts.filter(a => a.status === 'difference').slice(0, 5);
        if (topDiffs.length) {
            const maxDelta = Math.max(...topDiffs.map(item => Math.abs(item.delta || 0)), 1);
            html += `<div class="inv-top5-section">
                <h3 class="inv-section-title"><i class="fa-solid fa-fire" style="color:#ef4444;"></i> Diferencias Más Grandes</h3>
                <div class="inv-top5-list">
                    ${topDiffs.map((item, idx) => {
                        const pct = Math.min(100, Math.round((Math.abs(item.delta) / maxDelta) * 100));
                        return `
                            <div class="inv-top5-item" style="animation-delay: ${idx * 0.08}s;">
                                <div class="inv-top5-rank">${idx + 1}</div>
                                <div class="inv-top5-info">
                                    <span class="inv-top5-name">${item.nombre}</span>
                                    <div class="inv-top5-bar-bg">
                                        <div class="inv-top5-bar-fill" style="width:${pct}%;"></div>
                                    </div>
                                </div>
                                <div class="inv-top5-delta">${item.delta > 0 ? '+' : ''}${item.delta}</div>
                            </div>`;
                    }).join('')}
                </div>
            </div>`;
        }

        html += `<div class="inv-table-section">
            <h3 class="inv-section-title"><i class="fa-solid fa-table-list" style="color:#6366f1;"></i> Verificación contra Base</h3>
            <div class="inv-table-wrapper">
                <table class="inv-table">
                    <thead>
                        <tr>
                            <th>Estado</th>
                            <th>Hoja</th>
                            <th>Código</th>
                            <th>Artículo</th>
                            <th class="inv-th-num">Precio</th>
                            <th class="inv-th-num">Base</th>
                            <th class="inv-th-num">Actual</th>
                            <th class="inv-th-num">Diferencia</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${arts.map((a, idx) => {
                            let statusLabel = 'Coincide';
                            let deltaClass = 'inv-delta-neutral';
                            let deltaText = a.delta ?? '—';
                            let rowClass = '';

                            if (a.status === 'difference') {
                                statusLabel = 'Diferente';
                                deltaClass = a.delta < 0 ? 'inv-delta-down' : 'inv-delta-up';
                                deltaText = `${a.delta > 0 ? '+' : ''}${a.delta}`;
                                rowClass = a.delta < 0 ? 'inv-row-consumed' : 'inv-row-increased';
                            } else if (a.status === 'missing') {
                                statusLabel = 'Faltante';
                                deltaClass = 'inv-delta-missing';
                                deltaText = 'Falta';
                                rowClass = 'inv-row-missing';
                            } else {
                                deltaText = a.delta === 0 ? '0' : deltaText;
                            }

                            return `
                                <tr class="${rowClass}" style="animation-delay: ${idx * 0.02}s;">
                                    <td><span class="inv-status-pill inv-status-${a.status || 'match'}">${statusLabel}</span></td>
                                    <td>${a.hoja_origen || '—'}</td>
                                    <td class="inv-td-code">${a.codigo || '—'}</td>
                                    <td class="inv-td-name">${a.nombre}</td>
                                    <td class="inv-td-num">₡${_money(a.precio || 0)}</td>
                                    <td class="inv-td-num">${a.existencias_base !== null ? a.existencias_base : '—'}</td>
                                    <td class="inv-td-num inv-td-current">${a.existencias_actual !== null ? a.existencias_actual : '—'}</td>
                                    <td class="inv-td-num ${deltaClass}">${deltaText}</td>
                                </tr>`;
                        }).join('')}
                    </tbody>
                </table>
            </div>
        </div>`;

        dashboard.innerHTML = html;
        requestAnimationFrame(() => {
            document.querySelectorAll('.inv-top5-bar-fill').forEach(bar => {
                bar.style.transition = 'width 0.8s cubic-bezier(0.4, 0, 0.2, 1)';
            });
        });
    } catch (e) {
        dashboard.innerHTML = `<div class="portal-error"><i class="fa-solid fa-circle-exclamation"></i> ${e.message}</div>`;
    }
}

async function loadInventarioHistory() {
    const section = document.getElementById('invHistorySection');
    if (!section) return;

    try {
        const res = await fetch('/api/inventario/history');
        const history = await res.json();

        if (!history || history.length === 0) {
            section.innerHTML = '';
            return;
        }

        let html = `<div class="inv-history-section">
            <h3 class="inv-section-title"><i class="fa-solid fa-clock-rotate-left" style="color:#f59e0b;"></i> Historial de Cargas</h3>
            <div class="inv-history-grid">`;

        history.forEach((c, idx) => {
            html += `
            <div class="inv-history-card" style="animation-delay: ${idx * 0.05}s;">
                <div class="inv-history-card-top">
                    <div class="inv-history-date">
                        <i class="fa-regular fa-calendar"></i> ${_formatDateEs(c.fecha)}
                    </div>
                    <button class="inv-history-delete" onclick="deleteInventarioCarga(${c.id})" title="Eliminar carga">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                </div>
                <div class="inv-history-card-body">
                    <div class="inv-history-file">
                        <i class="fa-solid fa-file-excel" style="color:#10b981;"></i> ${c.archivo_nombre || 'Sin nombre'}
                    </div>
                    <div class="inv-history-count">
                        <i class="fa-solid fa-cubes"></i> ${c.total_articulos} artículos
                    </div>
                </div>
            </div>`;
        });

        html += `</div></div>`;
        section.innerHTML = html;
    } catch (e) {
        section.innerHTML = '';
    }
}

async function handleInventarioFile(input) {
    if (input.files && input.files[0]) {
        await uploadInventarioExcel(input.files[0]);
        input.value = ''; // Reset so same file can be re-uploaded
    }
}

async function uploadInventarioExcel(file) {
    const zone = document.getElementById('invUploadZone');
    const inner = zone.querySelector('.inv-upload-inner');
    const originalHTML = inner.innerHTML;

    // Show loading state
    inner.innerHTML = `
        <div class="inv-upload-loading">
            <div class="portal-spinner"></div>
            <p>Procesando <strong>${file.name}</strong>...</p>
        </div>`;

    try {
        const formData = new FormData();
        formData.append('file', file);

        const res = await fetch('/api/inventario/upload', {
            method: 'POST',
            body: formData
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Error al subir archivo');
        }

        const data = await res.json();
        showToast(data.message || `Se cargaron ${data.total_articulos} artículos`, 'success');

        // Reload dashboard
        inner.innerHTML = originalHTML;
        await loadInventarioBaseSection();
        await loadInventarioDashboard();
        await loadInventarioHistory();

    } catch (e) {
        showToast(e.message, 'error');
        inner.innerHTML = originalHTML;
    }
}

async function deleteInventarioCarga(cargaId) {
    if (!confirm('¿Estás seguro de eliminar esta carga de inventario?')) return;
    try {
        const res = await fetch(`/api/inventario/${cargaId}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Error al eliminar');
        showToast('Carga eliminada', 'success');
        await loadInventarioDashboard();
        await loadInventarioHistory();
    } catch (e) {
        showToast(e.message, 'error');
    }
}

window.openInventarioBaseEditor = async function openInventarioBaseEditor() {
    const current = (inventarioBaseState.articulos || []).map((a, i) => ({
        id: a.id, codigo: a.codigo || '', nombre: a.nombre || '',
        precio: a.precio || 0, existencias_base: a.existencias_base ?? 0,
        hoja_origen: a.hoja_origen || 'Manual', orden: a.orden || (i + 1),
    }));

    // Build modal
    let backdrop = document.getElementById('invBaseEditorModal');
    if (backdrop) backdrop.remove();

    backdrop = document.createElement('div');
    backdrop.id = 'invBaseEditorModal';
    backdrop.className = 'modal-backdrop';
    backdrop.innerHTML = `
        <div class="modal-dialog large" style="max-width:900px;max-height:85vh;display:flex;flex-direction:column;">
            <div class="modal-header-simple">
                <h3><i class="fa-solid fa-pen-to-square" style="color:#f59e0b;"></i> Editar Base de Comparación</h3>
                <button class="close-icon" id="invEditorClose"><i class="fa-solid fa-xmark"></i></button>
            </div>
            <div style="overflow:auto;flex:1;padding:0 1.2rem;">
                <table class="inv-table" style="width:100%;">
                    <thead>
                        <tr>
                            <th style="width:100px;">Código</th>
                            <th>Producto</th>
                            <th style="width:110px;">Precio</th>
                            <th style="width:90px;">Cant. Base</th>
                            <th style="width:100px;">Hoja</th>
                            <th style="width:50px;"></th>
                        </tr>
                    </thead>
                    <tbody id="invEditorBody"></tbody>
                </table>
            </div>
            <div style="padding:1rem 1.2rem;display:flex;justify-content:space-between;align-items:center;border-top:1px solid var(--border);">
                <button id="invEditorAdd">
                    <i class="fa-solid fa-plus"></i> Agregar Producto
                </button>
                <div style="display:flex;gap:8px;">
                    <button class="btn-text" id="invEditorCancel">Cancelar</button>
                    <button class="btn-action primary" id="invEditorSave">
                        <i class="fa-solid fa-floppy-disk"></i> Guardar Cambios
                    </button>
                </div>
            </div>
        </div>`;
    document.body.appendChild(backdrop);

    const tbody = document.getElementById('invEditorBody');
    const inputStyle = 'width:100%;padding:6px 8px;background:var(--bg-app);border:1px solid var(--border);color:var(--text-main);border-radius:6px;font-size:0.85rem;';

    function addRow(item) {
        const tr = document.createElement('tr');
        tr.dataset.itemId = item.id || '';
        tr.innerHTML = `
            <td><input type="text" value="${item.codigo}" data-field="codigo" style="${inputStyle}"></td>
            <td><input type="text" value="${item.nombre}" data-field="nombre" style="${inputStyle}" placeholder="Nombre del producto"></td>
            <td><input type="number" value="${item.precio}" data-field="precio" style="${inputStyle}" min="0" step="0.01"></td>
            <td><input type="number" value="${item.existencias_base}" data-field="existencias_base" style="${inputStyle}" min="0"></td>
            <td><input type="text" value="${item.hoja_origen}" data-field="hoja_origen" style="${inputStyle}"></td>
            <td><button class="inv-editor-del" title="Eliminar" style="background:none;border:none;color:#ef4444;cursor:pointer;font-size:1rem;padding:4px;">
                <i class="fa-solid fa-trash-can"></i>
            </button></td>`;
        tr.querySelector('.inv-editor-del').addEventListener('click', () => tr.remove());
        tbody.appendChild(tr);
    }

    current.forEach(addRow);

    document.getElementById('invEditorAdd').addEventListener('click', () => {
        addRow({ id: '', codigo: '', nombre: '', precio: 0, existencias_base: 0, hoja_origen: 'Manual' });
        tbody.lastElementChild.querySelector('[data-field="nombre"]').focus();
    });

    const close = () => backdrop.remove();
    document.getElementById('invEditorClose').addEventListener('click', close);
    document.getElementById('invEditorCancel').addEventListener('click', close);

    document.getElementById('invEditorSave').addEventListener('click', async () => {
        const rows = [...tbody.querySelectorAll('tr')];
        const items = rows.map((tr, i) => ({
            id: tr.dataset.itemId ? Number(tr.dataset.itemId) : null,
            codigo: tr.querySelector('[data-field="codigo"]').value.trim(),
            nombre: tr.querySelector('[data-field="nombre"]').value.trim(),
            precio: Number(tr.querySelector('[data-field="precio"]').value) || 0,
            existencias_base: Number(tr.querySelector('[data-field="existencias_base"]').value) || 0,
            hoja_origen: tr.querySelector('[data-field="hoja_origen"]').value.trim() || 'Manual',
            orden: i + 1,
        }));

        if (items.some(it => !it.nombre)) {
            showToast('Todos los productos deben tener nombre', 'error');
            return;
        }

        try {
            for (const item of items) {
                const res = await fetch('/api/inventario/base/articulo', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(item),
                });
                if (!res.ok) {
                    const err = await res.json();
                    throw new Error(err.detail || 'Error guardando la base');
                }
            }

            const originalIds = new Set(current.map(a => a.id));
            const keptIds = new Set(items.map(a => a.id).filter(Boolean));
            for (const id of originalIds) {
                if (!keptIds.has(id)) {
                    await fetch(`/api/inventario/base/articulo/${id}`, { method: 'DELETE' });
                }
            }

            showToast('Base actualizada correctamente', 'success');
            close();
            await loadInventarioBaseSection();
            await loadInventarioDashboard();
        } catch (e) {
            showToast(e.message, 'error');
        }
    });
};

window.reimportInventarioBaseDefault = async function reimportInventarioBaseDefault() {
    try {
        const res = await fetch('/api/inventario/base/import-default', { method: 'POST' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'No se pudo recargar la base');
        showToast(`Base recargada: ${data.total_articulos} productos`, 'success');
        await loadInventarioBaseSection();
        await loadInventarioDashboard();
    } catch (e) {
        showToast(e.message, 'error');
    }
};
