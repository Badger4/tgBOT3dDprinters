/**
 * 3D Farm Manager - Core Utilities & UI Formatters
 */

export function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

export function formatTimeMins(mins) {
    if (!mins || mins <= 0) return "—";
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    if (h > 0 && m > 0) return `${h} год ${m} хв`;
    if (h > 0) return `${h} год`;
    return `${m} хв`;
}

export function formatRemainingTime(mins, nowMs = Date.now()) {
    if (!mins || mins <= 0) return "";
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    const durStr = h > 0 ? `${h}г ${m}хв` : `${m} хв`;
    const finishDate = new Date(nowMs + mins * 60000);
    const hh = String(finishDate.getHours()).padStart(2, "0");
    const mm = String(finishDate.getMinutes()).padStart(2, "0");
    return `${durStr} (до ${hh}:${mm})`;
}

export function getPrinterStatusInfo(rawState) {
    const st = String(rawState || "ONLINE").toUpperCase();
    if (st === "OFFLINE" || st === "OFF" || st === "DISCONNECTED" || st === "UNKNOWN") {
        return { code: "OFFLINE", label: "Офлайн 🔴", badgeClass: "status-OFFLINE" };
    }
    if (st === "RUNNING" || st === "PRINTING") {
        return { code: "RUNNING", label: "Друк 🟢", badgeClass: "status-RUNNING" };
    }
    if (st === "PAUSE" || st === "PAUSED") {
        return { code: "PAUSE", label: "Пауза 🟡", badgeClass: "status-PAUSE" };
    }
    if (st === "PREPARE" || st === "PREPARING") {
        return { code: "PREPARE", label: "Підготовка 🟡", badgeClass: "status-PREPARE" };
    }
    if (st === "FINISH" || st === "FINISHED" || st === "SUCCESS") {
        return { code: "FINISH", label: "Завершено 🟣", badgeClass: "status-FINISH" };
    }
    if (st === "FAILED" || st === "ERROR") {
        return { code: "FAILED", label: "Помилка 🔴", badgeClass: "status-FAILED" };
    }
    return { code: "ONLINE", label: "Вільний ⚪", badgeClass: "status-ONLINE" };
}

export function formatCockpitHexColor(raw) {
    if (!raw) return "#3b82f6";
    let s = String(raw).trim();
    if (s.startsWith("#")) {
        return s.length === 7 || s.length === 9 ? s.slice(0, 7) : s;
    }
    if (/^[0-9A-Fa-f]{3,8}$/.test(s)) {
        return "#" + s.slice(0, 6);
    }
    return "#3b82f6";
}

export function getBambuModelCode(nameStr) {
    if (!nameStr) return "UNKNOWN";
    const s = String(nameStr).toLowerCase().replace(/[\-_]/g, " ").trim();

    if (s.includes("a1 mini") || s.includes("a1mini") || s.includes("a1m") || s.includes("@bbl a1m") || s.includes("n2s") || s.includes("n2")) {
        return "@BBL A1M";
    }
    if (s.includes("a1") || s.includes("@bbl a1") || s.includes("n1")) {
        return "@BBL A1";
    }
    if (s.includes("a2l") || s.includes("@bbl a2l")) {
        return "@BBL A2L";
    }
    if (s.includes("h2d pro") || s.includes("h2dpro") || s.includes("h2dp") || s.includes("@bbl h2dp")) {
        return "@BBL H2DP";
    }
    if (s.includes("h2c") || s.includes("@bbl h2c")) {
        return "@BBL H2C";
    }
    if (s.includes("h2d") || s.includes("@bbl h2d")) {
        return "@BBL H2D";
    }
    if (s.includes("h2s") || s.includes("@bbl h2s")) {
        return "@BBL H2S";
    }
    if (s.includes("p1p") || s.includes("@bbl p1p")) {
        return "@BBL P1P";
    }
    if (s.includes("p1s") || s.includes("@bbl p1s") || s.includes("c12")) {
        return "@BBL P1S";
    }
    if (s.includes("p2s") || s.includes("@bbl p2s")) {
        return "@BBL P2S";
    }
    if (s.includes("x2d") || s.includes("@bbl x2d")) {
        return "@BBL X2D";
    }
    if (s.includes("x1e") || s.includes("@bbl x1e")) {
        return "@BBL X1E";
    }
    if (s.includes("x1 carbon") || s.includes("x1c") || s.includes("x1") || s.includes("@bbl x1c") || s.includes("c10")) {
        return "@BBL X1C";
    }
    return "UNKNOWN";
}

export function normalizeFilamentName(rawName) {
    if (!rawName || String(rawName).trim().toLowerCase() === "unknown" || String(rawName).trim().toLowerCase() === "невизначено" || !String(rawName).trim()) {
        return "";
    }
    const s = String(rawName).trim().toUpperCase();
    const hardcodedTypes = [
        "ASA-AERO", "PETG-CF", "PLA-AERO", "PPA-CF", "PPA-GF", "TPU-AMS", "ABS-GF", "ASA-CF",
        "PA6-CF", "PLA-CF", "PET-CF", "PA-GF", "PP-CF", "PP-GF", "PE-CF", "PCTG", "BVOH",
        "CoPE", "HIPS", "PA6", "PETG", "PLA", "ABS", "TPU", "ASA", "PVA", "SBS", "EVA",
        "PHA", "PP", "PE", "PC", "PA"
    ];
    for (const t of hardcodedTypes) {
        const regex = new RegExp("(?:^|[^A-Z0-9\\-])" + t + "(?:$|[^A-Z0-9\\-])", "i");
        if (regex.test(s)) {
            return t;
        }
    }
    return s;
}

export function normalizeAmsSlots(printer, assignedSpools = []) {
    const rawTrays = printer.ams_trays || {};
    const activeTrayId = printer.active_tray_id;
    const isExternalOnly = (printer.ams_exist === false && !printer.has_ams) ||
        (Array.isArray(printer.ams_list) && printer.ams_list.length === 0 && !Object.keys(rawTrays).length);

    if (isExternalOnly) {
        const extKeys = ["254", "255", "vt", "external"];
        let extAssigned = null;
        for (const k of extKeys) {
            const found = assignedSpools.find(s => String(s.assigned_slot || "").toLowerCase() === k);
            if (found) { extAssigned = found; break; }
        }
        let extTray = rawTrays["254"] || rawTrays["255"] || rawTrays["vt"] || null;
        const isLoaded = !!(extAssigned || extTray);
        const color = extAssigned ? formatCockpitHexColor(extAssigned.color) : (extTray ? formatCockpitHexColor(extTray.color) : "#64748b");
        const type = extAssigned ? (extAssigned.type || "PLA") : (extTray?.type || "PLA");
        const name = extAssigned ? (extAssigned.name || "Зовнішня котушка") : (extTray?.sub_brands ? `Bambu ${type} ${extTray.sub_brands}` : `Зовнішній ${type}`);
        const grams = extAssigned ? (extAssigned.remaining_grams || 0) : (printer.vt_tray?.remain || 0);
        const pct = extAssigned ? Math.min(100, Math.max(0, Math.round((grams / (extAssigned.initial_grams || 1000)) * 100))) : (extTray?.remain !== undefined && extTray.remain >= 0 ? extTray.remain : 100);

        return [{
            slotKey: "254",
            label: "VT",
            isActive: activeTrayId === 254 || activeTrayId === 255,
            isLoaded,
            color,
            filamentType: type,
            spoolName: isLoaded ? name : "Порожньо",
            remainingGrams: Math.round(grams),
            percentage: pct,
            gramsText: isLoaded ? (grams > 0 ? `${Math.round(grams)}g` : `${pct}%`) : "Порожньо",
            source: extAssigned ? "warehouse" : (extTray ? "ams_tray" : "empty")
        }];
    }

    const slotLabels = { "0": "A1", "1": "A2", "2": "A3", "3": "A4" };
    return ["0", "1", "2", "3"].map((k, idx) => {
        const trayInfo = rawTrays[k] || rawTrays[String(idx)];
        const assigned = assignedSpools.find(s => String(s.assigned_slot) === k || String(s.assigned_slot) === String(idx));
        const isActive = activeTrayId === idx || String(activeTrayId) === k;
        const hasTray = trayInfo && (trayInfo.color || trayInfo.type || (trayInfo.state !== undefined && trayInfo.state !== 0));

        if (!assigned && !hasTray) {
            return {
                slotKey: k,
                label: slotLabels[k] || k,
                isActive,
                isLoaded: false,
                color: null,
                filamentType: "—",
                spoolName: "Порожньо",
                remainingGrams: 0,
                percentage: 0,
                gramsText: "Порожньо",
                source: "empty"
            };
        }

        let spoolColor = "#3b82f6";
        let spoolType = "PLA";
        let spoolName = "";
        let displayGrams = 0;
        let pct = 0;
        let source = "unknown";

        if (assigned) {
            source = "warehouse";
            spoolColor = formatCockpitHexColor(assigned.color);
            spoolType = assigned.type || "PLA";
            spoolName = assigned.name || "Складська котушка";
            displayGrams = assigned.remaining_grams !== undefined ? assigned.remaining_grams : 0;
            const maxCap = assigned.initial_grams || assigned.total_grams || 1000;
            pct = Math.min(100, Math.max(0, Math.round((displayGrams / maxCap) * 100)));
        } else if (hasTray) {
            source = "ams_tray";
            spoolColor = formatCockpitHexColor(trayInfo.color);
            spoolType = trayInfo.type || "PLA";
            spoolName = trayInfo.sub_brands ? `Bambu ${spoolType} ${trayInfo.sub_brands}` : `Bambu ${spoolType}`;
            displayGrams = (printer.ams_slots && printer.ams_slots[k] !== undefined) ? printer.ams_slots[k] : 0;
            if (trayInfo.remain !== undefined && trayInfo.remain >= 0) {
                pct = trayInfo.remain;
            } else {
                pct = Math.min(100, Math.max(0, Math.round((displayGrams / 1000) * 100)));
            }
        }

        const gramsText = displayGrams > 0 ? `${Math.round(displayGrams)}g` : `${pct}%`;

        return {
            slotKey: k,
            label: slotLabels[k] || k,
            isActive,
            isLoaded: true,
            color: spoolColor,
            filamentType: spoolType,
            spoolName,
            remainingGrams: Math.round(displayGrams),
            percentage: pct,
            gramsText,
            source
        };
    });
}

export function cleanSubtaskName(subtask, isPrinting = false) {
    if (!subtask) return isPrinting ? "Друк моделі" : "Очікування завдання";
    let s = String(subtask).trim();
    if (s.startsWith("Metadata/")) s = s.replace(/^Metadata\//, "");
    if (s.toLowerCase().endsWith(".gcode")) s = s.slice(0, -6);
    if (s.toLowerCase().endsWith(".3mf")) s = s.slice(0, -4);
    return s || (isPrinting ? "Друк моделі" : "Очікування завдання");
}

export function evaluateMathExpression(rawExpr) {
    if (!rawExpr) return 0;
    const clean = String(rawExpr).replace(/,/g, ".").replace(/\s+/g, "");
    if (!/^[0-9\.\+\-\*\/\(\)]+$/.test(clean)) {
        const val = parseFloat(clean);
        return isNaN(val) ? 0 : val;
    }
    let pos = 0;
    function parseNumber() {
        let start = pos;
        if (clean[pos] === "-" || clean[pos] === "+") pos++;
        while (pos < clean.length && ((clean[pos] >= "0" && clean[pos] <= "9") || clean[pos] === ".")) {
            pos++;
        }
        const token = clean.slice(start, pos);
        const val = parseFloat(token);
        return isNaN(val) ? 0 : val;
    }
    function parseFactor() {
        if (clean[pos] === "(") {
            pos++;
            const val = parseAddSub();
            if (clean[pos] === ")") pos++;
            return val;
        }
        return parseNumber();
    }
    function parseMulDiv() {
        let left = parseFactor();
        while (pos < clean.length && (clean[pos] === "*" || clean[pos] === "/")) {
            const op = clean[pos++];
            const right = parseFactor();
            if (op === "*") left = left * right;
            else if (op === "/") left = right === 0 ? 0 : left / right;
        }
        return left;
    }
    function parseAddSub() {
        let left = parseMulDiv();
        while (pos < clean.length && (clean[pos] === "+" || clean[pos] === "-")) {
            const op = clean[pos++];
            const right = parseMulDiv();
            if (op === "+") left = left + right;
            else if (op === "-") left = left - right;
        }
        return left;
    }
    try {
        const res = parseAddSub();
        return isFinite(res) && !isNaN(res) ? Math.round(res * 100) / 100 : 0;
    } catch (e) {
        return 0;
    }
}

export function triggerHaptic(type = "light") {
    const tg = window.Telegram?.WebApp;
    if (!tg || !tg.HapticFeedback) return;
    try {
        if (type === "success" || type === "error" || type === "warning") {
            tg.HapticFeedback.notificationOccurred(type);
        } else if (type === "selection") {
            tg.HapticFeedback.selectionChanged();
        } else {
            tg.HapticFeedback.impactOccurred(type);
        }
    } catch (e) {}
}

export function renderVisualSpoolSvg(color, grams, total = 1000, size = 64) {
    const hex = formatCockpitHexColor(color);
    const validTotal = Math.max(100, total || 1000);
    const validGrams = Math.max(0, Math.min(validTotal, grams !== undefined ? grams : 0));
    const fillRatio = validGrams / validTotal;

    const rMin = 13;
    const rMax = 25;
    const currentRadius = rMin + (rMax - rMin) * fillRatio;
    const strokeWidth = (currentRadius - rMin) * 2;
    const strokeRadius = rMin + (currentRadius - rMin) / 2;

    const rgb = parseInt(hex.slice(1), 16);
    const r = (rgb >> 16) & 255;
    const g = (rgb >> 8) & 255;
    const b = rgb & 255;
    const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    const isLight = lum > 190;

    return `
    <svg class="visual-spool-svg ${isLight ? 'light-spool' : ''}" width="${size}" height="${size}" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="32" cy="32" r="28" fill="#1e293b" stroke="#334155" stroke-width="2"/>
        <circle cx="32" cy="32" r="26" stroke="#475569" stroke-width="1" stroke-dasharray="3 3"/>
        ${fillRatio > 0.02 ? `
        <circle cx="32" cy="32" r="${strokeRadius}" stroke="${hex}" stroke-width="${strokeWidth}" fill="none"/>
        <circle cx="32" cy="32" r="${strokeRadius}" stroke="rgba(255,255,255,0.2)" stroke-width="${strokeWidth}" stroke-dasharray="2 4" fill="none"/>
        ` : ''}
        <circle cx="32" cy="32" r="13" fill="#0f172a" stroke="#334155" stroke-width="1.5"/>
        <circle cx="32" cy="32" r="6" fill="#090d16" stroke="#475569" stroke-width="1"/>
        <circle cx="32" cy="32" r="27.5" stroke="rgba(255,255,255,0.15)" stroke-width="0.75" fill="none"/>
    </svg>`;
}
