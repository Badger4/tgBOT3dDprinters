/**
 * 3D Farm Manager - Cockpit & Classic Printer Card Renderers
 */

import { escapeHtml, formatCockpitHexColor, formatRemainingTime, cleanSubtaskName, triggerHaptic } from "./utils.js";
import { state } from "./state.js";
import { controlPrinterApi, fetchPrintersApi } from "./api.js";

export function renderClassicPrinterCard(p, statusInfo, modelName, isPrinting, progress, timeStr, layerStr, filamentDisplay, hasPhysicalSpool, slotGrams, printerModelVal, serialVal, fullSearchText) {
    const rawSt = String(p.state || "IDLE").toUpperCase();
    return `
        <div class="printer-card" data-id="${p.id}" data-name="${escapeHtml(p.name)}" data-model="${escapeHtml(modelName)}" data-pmodel="${escapeHtml(printerModelVal)}" data-ip="${escapeHtml(p.ip || '')}" data-sn="${escapeHtml(serialVal)}" data-search="${escapeHtml(fullSearchText)}" data-state="${statusInfo.code}">
            <div class="printer-card-header">
                <div class="printer-name-group">
                    <h3>${escapeHtml(p.name)}</h3>
                    <div class="printer-model-sub"><i class="fa-solid fa-file-code"></i> ${escapeHtml(modelName)}</div>
                </div>
                <div class="d-flex align-items-center">
                    <span class="status-pill ${statusInfo.badgeClass}">${statusInfo.label}</span>
                    <button type="button" class="btn-card-gear" data-id="${p.id}" title="Налаштування принтера"><i class="fa-solid fa-gear"></i></button>
                </div>
            </div>

            <div class="progress-container">
                <div class="progress-header">
                    <span>Прогрес: ${progress}%</span>
                    <span>${timeStr}</span>
                </div>
                <div class="progress-bar-wrap">
                    <div class="progress-bar ${rawSt === 'PAUSE' || rawSt === 'PAUSED' ? 'amber' : rawSt === 'FAILED' ? 'red' : ''}" style="width: ${progress}%;"></div>
                </div>
            </div>

            <div class="printer-stats-row">
                <span><i class="fa-solid fa-temperature-high color-red"></i> ${p.nozzle_temp || 0}°C <small style="opacity:0.75;">(${p.nozzle_diameter || '0.4'}мм)</small></span>
                <span><i class="fa-solid fa-hot-tub-person color-orange"></i> ${p.bed_temp || 0}°C</span>
                <span><i class="fa-solid fa-layer-group color-blue"></i> ${layerStr}</span>
                <span><i class="fa-solid fa-spool ${hasPhysicalSpool ? 'color-purple' : 'text-muted'}" style="${hasPhysicalSpool ? '' : 'opacity:0.4;'}"></i> ${filamentDisplay}</span>
            </div>
        </div>`;
}

export function renderCockpitPrinterCard(p, statusInfo, modelName, isPrinting, progress, timeStr, layerStr, filamentDisplay, hasPhysicalSpool, slotGrams, printerModelVal, serialVal, fullSearchText, assignedSpools) {
    const lightIsOn = (p.chamber_light_state === "on");
    const spdLvl = parseInt(p.spd_lvl || 2);
    const speedMeta = {
        1: { icon: "🐢", pct: "50%", name: "Тихий" },
        2: { icon: "⚡", pct: "100%", name: "Стандарт" },
        3: { icon: "🚀", pct: "124%", name: "Спорт" },
        4: { icon: "🏎️", pct: "166%", name: "Турбо" }
    };
    const curSpd = speedMeta[spdLvl] || speedMeta[2];

    const validPct = Math.min(100, Math.max(0, Number(progress) || 0));
    const dashOffset = (219.91 * (1 - (validPct / 100))).toFixed(1);

    let ringClass = "ring-idle";
    if (isPrinting) ringClass = "ring-running";
    else if (statusInfo.code === "PAUSE") ringClass = "ring-pause";
    else if (statusInfo.code === "FAILED") ringClass = "ring-failed";
    else if (statusInfo.code === "OFFLINE") ringClass = "ring-offline";

    let centerPctText = isPrinting || statusInfo.code === "PAUSE" ? `${validPct}%` : (statusInfo.code === "IDLE" ? "Вільний" : "—");
    let centerLayerText = isPrinting || statusInfo.code === "PAUSE" ? `Шар ${p.current_layer || 0}/${p.total_layers || 0}` : (statusInfo.code === "IDLE" ? "Готовий" : statusInfo.label);

    const hasAms = Boolean(p.has_ams);
    let amsPanelHtml = "";

    if (hasAms) {
        const slotKeys = ["0", "1", "2", "3"];
        const slotLabels = { "0": "A1", "1": "A2", "2": "A3", "3": "A4" };
        const activeKey = String(p.active_slot_key || p.active_ams_tray || "255");

        const slotsHtml = slotKeys.map(k => {
            const isActive = (k === activeKey || String(p.active_ams_tray) === k);
            const trayInfo = (p.ams_trays_info || {})[k] || {};
            const assigned = (assignedSpools || []).find(s => String(s.assigned_slot_key) === k);
            const hasTray = Boolean(!trayInfo.empty && trayInfo.type);
            const hasAssigned = Boolean(assigned && (assigned.remaining_grams > 0 || assigned.name));
            const isLoaded = hasTray || hasAssigned;

            if (!isLoaded) {
                return `
                    <div class="cockpit-ams-slot empty ${isActive ? 'active' : ''}">
                        <div class="cockpit-ams-head">
                            <span>${slotLabels[k]}${isActive ? ' ⚡' : ''}</span>
                            <i class="fa-solid fa-ban" style="font-size: 8px; opacity: 0.35;"></i>
                        </div>
                        <div class="cockpit-ams-info">
                            <span class="cockpit-ams-type text-muted">—</span>
                            <span class="cockpit-ams-grams text-muted">Порожньо</span>
                        </div>
                        <div class="cockpit-ams-fill-bar">
                            <div class="cockpit-ams-fill-inner" style="width: 0%;"></div>
                        </div>
                    </div>`;
            }

            let spoolColor = "#3b82f6";
            let spoolType = "PLA";
            let displayGrams = 0;
            let pct = 0;

            if (assigned) {
                spoolColor = formatCockpitHexColor(assigned.color);
                spoolType = assigned.type || "PLA";
                displayGrams = assigned.remaining_grams !== undefined ? assigned.remaining_grams : 0;
                const maxCap = assigned.initial_grams || assigned.total_grams || 1000;
                pct = Math.min(100, Math.max(0, Math.round((displayGrams / maxCap) * 100)));
            } else if (hasTray) {
                spoolColor = formatCockpitHexColor(trayInfo.color);
                spoolType = trayInfo.type || "PLA";
                displayGrams = (p.ams_slots && p.ams_slots[k] !== undefined) ? p.ams_slots[k] : 0;
                if (trayInfo.remain !== undefined && trayInfo.remain >= 0) {
                    pct = trayInfo.remain;
                } else {
                    pct = Math.min(100, Math.max(0, Math.round((displayGrams / 1000) * 100)));
                }
            }

            const gramsText = displayGrams > 0 ? `${Math.round(displayGrams)}g` : `${pct}%`;

            return `
                <div class="cockpit-ams-slot ${isActive ? 'active' : ''}" title="${slotLabels[k]}: ${escapeHtml(spoolType)} (${gramsText})">
                    <div class="cockpit-ams-head">
                        <span>${slotLabels[k]}${isActive ? ' ⚡' : ''}</span>
                        <div class="cockpit-ams-color-pill" style="background-color: ${spoolColor};"></div>
                    </div>
                    <div class="cockpit-ams-info">
                        <span class="cockpit-ams-type">${escapeHtml(spoolType)}</span>
                        <span class="cockpit-ams-grams">${gramsText}</span>
                    </div>
                    <div class="cockpit-ams-fill-bar">
                        <div class="cockpit-ams-fill-inner" style="width: ${pct}%; background-color: ${spoolColor};"></div>
                    </div>
                </div>`;
        }).join("");

        const humIdx = parseInt(p.ams_humidity_idx || 0);
        let humBadgeHtml = "";
        if (humIdx >= 1) {
            let humClass = "hum-dry";
            let humIcon = '<i class="fa-solid fa-droplet color-cyan"></i>';
            let humTitle = "Вологість в нормі";
            if (humIdx === 3) {
                humClass = "hum-ok";
                humIcon = '<i class="fa-solid fa-droplet color-green"></i>';
                humTitle = "Вологість помірна";
            } else if (humIdx === 4) {
                humClass = "hum-warn";
                humIcon = '<i class="fa-solid fa-triangle-exclamation color-amber"></i>';
                humTitle = "Підвищена вологість! Осушувач насичується";
            } else if (humIdx >= 5) {
                humClass = "hum-danger";
                humIcon = '<i class="fa-solid fa-circle-exclamation color-red"></i>';
                humTitle = "Критична вологість! Замініть осушувач";
            }
            humBadgeHtml = `<span class="badge-ams-humidity ${humClass}" title="${humTitle}">${humIcon} ${humIdx}/5</span>`;
        }

        amsPanelHtml = `
            <div class="cockpit-ams-header">
                <span><i class="fa-solid fa-box-archive"></i> AMS</span>
                ${humBadgeHtml}
            </div>
            <div class="cockpit-ams-strip">${slotsHtml}</div>`;
    } else {
        const activeKey = String(p.active_slot_key || "254");
        const isExternalActive = (activeKey === "254" || activeKey === "255");
        const assigned = (assignedSpools || []).find(s => ["254", "255"].includes(String(s.assigned_slot_key)));
        const spoolColor = formatCockpitHexColor(assigned?.color || (isExternalActive && isPrinting ? "#10b981" : "#3b82f6"));

        amsPanelHtml = `
            <div class="cockpit-single-spool ${isExternalActive ? 'active' : ''}">
                <div class="d-flex align-items-center gap-2" style="min-width: 0;">
                    <span class="badge" style="background: rgba(255,255,255,0.08); font-size: 10px; font-weight: 700; padding: 2px 6px;">VT${isExternalActive ? ' ⚡' : ''}</span>
                    <div class="cockpit-ams-color-pill" style="background-color: ${spoolColor};"></div>
                    <span class="text-truncate" style="font-size: 11px; font-weight: 600;">${filamentDisplay || 'Зовнішня котушка'}</span>
                </div>
                <span style="font-size: 11px; color: var(--text-muted); flex-shrink: 0;">${hasPhysicalSpool ? `${Math.round(slotGrams)}g` : 'Порожньо'}</span>
            </div>`;
    }

    const isPaused = statusInfo.code === "PAUSE";
    const canPauseResume = isPrinting || isPaused;
    const isPeekOpen = state.openCamPeekIds.has(String(p.id));
    const tg = window.Telegram?.WebApp;
    const initDataParam = tg?.initData ? `?initData=${encodeURIComponent(tg.initData)}` : "";
    const peekSrc = isPeekOpen ? `/api/printers/${p.id}/snapshot${initDataParam}${initDataParam ? '&' : '?'}t=${Date.now()}` : "";

    return `
        <div class="printer-card cockpit-card" data-id="${p.id}" data-name="${escapeHtml(p.name)}" data-model="${escapeHtml(modelName)}" data-pmodel="${escapeHtml(printerModelVal)}" data-ip="${escapeHtml(p.ip || '')}" data-sn="${escapeHtml(serialVal)}" data-search="${escapeHtml(fullSearchText)}" data-state="${statusInfo.code}">
            <!-- Header -->
            <div class="cockpit-header">
                <div class="cockpit-title-group">
                    <div class="cockpit-title-row">
                        <h3 class="cockpit-printer-name">${escapeHtml(p.name)}</h3>
                        <span class="status-pill ${statusInfo.badgeClass}">${statusInfo.label}</span>
                    </div>
                    <div class="cockpit-file-name" title="${escapeHtml(modelName)}">
                        <i class="fa-solid fa-file-code"></i>
                        <span>${escapeHtml(modelName)}</span>
                    </div>
                </div>
                <div class="cockpit-quick-actions">
                    ${canPauseResume ? `
                    <button type="button" class="btn-cockpit-quick btn-cockpit-pause-resume ${isPaused ? 'state-pause' : 'state-running'}" data-id="${p.id}" data-state="${statusInfo.code}" title="${isPaused ? 'Відновити друк' : 'Поставити на паузу'}">
                        <i class="fa-solid ${isPaused ? 'fa-play' : 'fa-pause'}"></i>
                    </button>` : ''}
                    <button type="button" class="btn-cockpit-quick btn-cockpit-cam-peek ${isPeekOpen ? 'active' : ''}" data-id="${p.id}" title="Швидкий огляд камери">
                        <i class="fa-solid fa-camera"></i>
                    </button>
                    <button type="button" class="btn-cockpit-quick btn-cockpit-light ${lightIsOn ? 'active' : ''}" data-id="${p.id}" title="Підсвітка камери: ${lightIsOn ? 'Увімкнено' : 'Вимкнено'}">
                        <i class="fa-solid fa-lightbulb"></i>
                    </button>
                    <button type="button" class="btn-cockpit-quick btn-cockpit-speed" data-id="${p.id}" data-lvl="${spdLvl}" title="Швидкість: ${curSpd.name} (${curSpd.pct})">
                        <span class="cockpit-spd-icon">${curSpd.icon}</span>
                        <span class="cockpit-spd-val">${curSpd.pct}</span>
                    </button>
                    <button type="button" class="btn-card-gear" data-id="${p.id}" title="Налаштування принтера">
                        <i class="fa-solid fa-gear"></i>
                    </button>
                </div>
            </div>

            <!-- Quick Inline Camera Peek Box -->
            <div class="cockpit-cam-peek-box ${isPeekOpen ? 'active' : ''}" id="cockpit-peek-${p.id}">
                ${isPeekOpen ? `<img src="${peekSrc}" alt="Камера ${escapeHtml(p.name)}" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" /><div style="display:none; color:var(--text-muted); font-size:12px; align-items:center; gap:6px;"><i class="fa-solid fa-video-slash"></i> Камера недоступна</div>` : ''}
            </div>

            <!-- Cockpit Body: Circular SVG Progress & Telemetry -->
            <div class="cockpit-body">
                <div class="cockpit-ring-container">
                    <svg class="cockpit-ring-svg" viewBox="0 0 84 84">
                        <circle class="cockpit-ring-bg" cx="42" cy="42" r="35"></circle>
                        <circle class="cockpit-ring-fill ${ringClass}" cx="42" cy="42" r="35"
                                style="stroke-dasharray: 219.91; stroke-dashoffset: ${dashOffset};"></circle>
                    </svg>
                    <div class="cockpit-ring-text">
                        <span class="cockpit-ring-pct">${centerPctText}</span>
                        <span class="cockpit-ring-layer">${centerLayerText}</span>
                    </div>
                </div>

                <div class="cockpit-telemetry-grid">
                    <div class="cockpit-tele-box">
                        <span class="cockpit-tele-lbl"><i class="fa-regular fa-clock color-cyan"></i> Залишилось</span>
                        <span class="cockpit-tele-val">${timeStr}</span>
                    </div>
                    <div class="cockpit-tele-box">
                        <span class="cockpit-tele-lbl"><i class="fa-solid fa-layer-group color-blue"></i> Шари</span>
                        <span class="cockpit-tele-val">${layerStr}</span>
                    </div>
                    <div class="cockpit-tele-box">
                        <span class="cockpit-tele-lbl"><i class="fa-solid fa-temperature-high color-red"></i> Сопло</span>
                        <span class="cockpit-tele-val">${p.nozzle_temp !== undefined ? p.nozzle_temp : 0}°C <small style="font-size:10px; opacity:0.75; font-weight:normal;">(${p.nozzle_diameter || '0.4'}мм)</small></span>
                    </div>
                    <div class="cockpit-tele-box">
                        <span class="cockpit-tele-lbl"><i class="fa-solid fa-hot-tub-person color-orange"></i> Стіл</span>
                        <span class="cockpit-tele-val">${p.bed_temp !== undefined ? p.bed_temp : 0}°C</span>
                    </div>
                </div>
            </div>

            <!-- Cockpit AMS Mini-Slots / External Spool -->
            ${amsPanelHtml}
        </div>`;
}

export async function handleQuickPauseResume(pId, btnEl, e) {
    if (e) e.stopPropagation();
    triggerHaptic("medium");
    const curState = btnEl.getAttribute("data-state") || "RUNNING";
    const action = curState === "PAUSE" ? "resume" : "pause";
    btnEl.disabled = true;
    try {
        const data = await controlPrinterApi(pId, action);
        if (data.status === "ok") {
            triggerHaptic("success");
            const printers = await fetchPrintersApi();
            state.printers = printers;
        } else {
            triggerHaptic("error");
            alert(`⚠️ Не вдалося змінити стан друку: ${data.error || ""}`);
        }
    } catch (err) {
        triggerHaptic("error");
        console.error("Quick pause/resume error:", err);
    } finally {
        btnEl.disabled = false;
    }
}

export function handleQuickCamPeek(pId, btnEl, e) {
    if (e) e.stopPropagation();
    triggerHaptic("light");
    const key = String(pId);
    const box = document.getElementById(`cockpit-peek-${pId}`);
    if (!box) return;

    if (state.openCamPeekIds.has(key)) {
        state.openCamPeekIds.delete(key);
        btnEl.classList.remove("active");
        box.classList.remove("active");
        box.innerHTML = "";
    } else {
        state.openCamPeekIds.add(key);
        btnEl.classList.add("active");
        box.classList.add("active");
        const tg = window.Telegram?.WebApp;
        const initDataParam = tg?.initData ? `?initData=${encodeURIComponent(tg.initData)}` : "";
        const src = `/api/printers/${pId}/snapshot${initDataParam}${initDataParam ? '&' : '?'}t=${Date.now()}`;
        box.innerHTML = `<img src="${src}" alt="Камера" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" /><div style="display:none; color:var(--text-muted); font-size:12px; align-items:center; gap:6px;"><i class="fa-solid fa-video-slash"></i> Камера недоступна</div>`;
    }
}

export async function handleQuickLightToggle(pId, btnEl, e) {
    if (e) e.stopPropagation();
    triggerHaptic("medium");
    const wasActive = btnEl.classList.contains("active");
    btnEl.classList.toggle("active");
    btnEl.setAttribute("title", `Підсвітка камери: ${!wasActive ? 'Увімкнено' : 'Вимкнено'}`);

    try {
        const data = await controlPrinterApi(pId, "light_toggle");
        if (data.status === "ok") {
            const p = state.printers.find(x => x.id === pId);
            if (p) p.chamber_light_state = data.light_state || (!wasActive ? "on" : "off");
        } else {
            btnEl.classList.toggle("active");
        }
    } catch (err) {
        console.error("Quick light error:", err);
        btnEl.classList.toggle("active");
    }
}

export async function handleQuickSpeedCycle(pId, btnEl, e) {
    if (e) e.stopPropagation();
    triggerHaptic("medium");
    const curLvl = parseInt(btnEl.getAttribute("data-lvl") || "2");
    const nextLvl = (curLvl % 4) + 1;

    const speedMeta = {
        1: { icon: "🐢", pct: "50%", name: "Тихий" },
        2: { icon: "⚡", pct: "100%", name: "Стандарт" },
        3: { icon: "🚀", pct: "124%", name: "Спорт" },
        4: { icon: "🏎️", pct: "166%", name: "Турбо" }
    };

    btnEl.setAttribute("data-lvl", nextLvl);
    btnEl.setAttribute("title", `Швидкість: ${speedMeta[nextLvl].name} (${speedMeta[nextLvl].pct})`);
    const iconEl = btnEl.querySelector(".cockpit-spd-icon");
    const valEl = btnEl.querySelector(".cockpit-spd-val");
    if (iconEl) iconEl.textContent = speedMeta[nextLvl].icon;
    if (valEl) valEl.textContent = speedMeta[nextLvl].pct;

    try {
        const data = await controlPrinterApi(pId, "set_speed", { level: nextLvl });
        if (data.status === "ok") {
            const p = state.printers.find(x => x.id === pId);
            if (p) p.spd_lvl = nextLvl;
        } else {
            btnEl.setAttribute("data-lvl", curLvl);
            if (iconEl) iconEl.textContent = speedMeta[curLvl].icon;
            if (valEl) valEl.textContent = speedMeta[curLvl].pct;
        }
    } catch (err) {
        console.error("Quick speed error:", err);
        btnEl.setAttribute("data-lvl", curLvl);
        if (iconEl) iconEl.textContent = speedMeta[curLvl].icon;
        if (valEl) valEl.textContent = speedMeta[curLvl].pct;
    }
}
