/**
 * 3D Farm Manager - UI Utilities & Formatters
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

export function formatCockpitHexColor(raw) {
    if (!raw) return "#3b82f6";
    let s = String(raw).trim();
    if (s.startsWith("#")) {
        return s;
    }
    if (/^[0-9A-Fa-f]{3,8}$/.test(s)) {
        return "#" + s;
    }
    return "#3b82f6";
}

export function getBambuModelCode(nameStr) {
    const s = String(nameStr).toLowerCase().replace(/[\-_]/g, " ").trim();
    if (s.includes("p1s")) return "p1s";
    if (s.includes("p1p")) return "p1p";
    if (s.includes("x1c") || s.includes("x1 carbon")) return "x1c";
    if (s.includes("x1e")) return "x1e";
    if (s.includes("x1")) return "x1";
    if (s.includes("a1 mini")) return "a1_mini";
    if (s.includes("a1")) return "a1";
    return "p1s";
}

export function normalizeFilamentName(rawName) {
    if (!rawName) return "Unknown";
    const s = String(rawName).trim().toUpperCase();
    const hardcodedTypes = ["PLA-CF", "PETG-CF", "ABS-GF", "PET-CF", "PA-CF", "PLA", "PETG", "ABS", "ASA", "TPU", "PC", "PA"];
    for (const t of hardcodedTypes) {
        if (s.includes(t)) return t;
    }
    return rawName;
}
