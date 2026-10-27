/**
 * 3D Farm Manager - API Client Module
 * Provides unified HTTP client with automatic auth headers & centralized backend route callers.
 */

import { triggerHaptic } from "./utils.js";

export function getSessionToken() {
    return localStorage.getItem("3d_farm_session") || localStorage.getItem("web_session_token") || "";
}

export const getWebSessionToken = getSessionToken;

export function getTelegramInitData() {
    return window.Telegram?.WebApp?.initData || "";
}

export function setupFetchInterceptor() {
    const originalFetch = window.fetch;
    window.fetch = function(url, options = {}) {
        options = options || {};
        let h = options.headers;
        if (!h) {
            h = new Headers();
        } else if (!(h instanceof Headers)) {
            h = new Headers(h);
        }
        h.set("Bypass-Tunnel-Reminder", "true");
        const initData = getTelegramInitData();
        if (initData) {
            h.set("X-Telegram-Init-Data", initData);
        }
        const token = getSessionToken();
        if (token) {
            if (!h.has("Authorization")) h.set("Authorization", `Bearer ${token}`);
            if (!h.has("X-Session-Token")) h.set("X-Session-Token", token);
        }
        options.headers = h;
        return originalFetch(url, options);
    };
}

export async function apiFetch(url, options = {}) {
    const res = await window.fetch(url, options);
    if (res.status === 401 || res.status === 403) {
        if (!window.Telegram?.WebApp?.initData) {
            const currentPath = window.location.pathname;
            if (currentPath !== "/login" && !currentPath.startsWith("/login")) {
                window.location.href = "/login";
            }
        }
    }
    return res;
}

/**
 * Injects session token or telegram initData into query parameters of an export URL
 * so that both fetch and native browser downloads carry valid authorization.
 */
export function buildAuthenticatedExportUrl(rawUrl, { token = "", initData = "" } = {}) {
    const sToken = token || getSessionToken();
    const sInitData = initData || getTelegramInitData();

    try {
        const dummyBase = "http://localhost";
        const isRelative = !rawUrl.startsWith("http://") && !rawUrl.startsWith("https://");
        const parsed = new URL(rawUrl, dummyBase);

        if (sToken && !parsed.searchParams.has("token")) {
            parsed.searchParams.set("token", sToken);
        }
        if (sInitData && !parsed.searchParams.has("initData")) {
            parsed.searchParams.set("initData", sInitData);
        }

        if (isRelative) {
            return parsed.pathname + parsed.search + parsed.hash;
        }
        return parsed.toString();
    } catch (_) {
        return rawUrl;
    }
}

/**
 * Safely downloads a protected PDF report using fetch with auth headers
 * and automatic fallback to authenticated blob object URL.
 */
export async function downloadAuthenticatedPdf(url, defaultFilename = "document.pdf", btnElement = null) {
    if (!url) return;

    let originalHtml = "";
    if (btnElement) {
        if (btnElement.getAttribute("data-busy") === "true") return;
        btnElement.setAttribute("data-busy", "true");
        originalHtml = btnElement.innerHTML;
        btnElement.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> PDF...';
        btnElement.style.pointerEvents = "none";
    }

    try {
        triggerHaptic("light");
        const authenticatedUrl = buildAuthenticatedExportUrl(url);

        const res = await window.fetch(authenticatedUrl);
        if (!res.ok) {
            let errMsg = `Помилка сервера: HTTP ${res.status}`;
            try {
                const j = await res.json();
                if (j && j.error) errMsg = j.error;
            } catch (_) {}
            throw new Error(errMsg);
        }

        const blob = await res.blob();
        let filename = defaultFilename;
        const disposition = res.headers.get("Content-Disposition");
        if (disposition && disposition.includes("filename=")) {
            const match = disposition.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
            if (match && match[1]) filename = decodeURIComponent(match[1].trim());
        }

        const blobUrl = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = blobUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => window.URL.revokeObjectURL(blobUrl), 2000);
        triggerHaptic("success");
    } catch (err) {
        console.error("Authenticated PDF download failed:", err);
        triggerHaptic("error");
        alert("Не вдалося завантажити PDF: " + (err.message || err));
    } finally {
        if (btnElement) {
            btnElement.removeAttribute("data-busy");
            btnElement.innerHTML = originalHtml;
            btnElement.style.pointerEvents = "";
        }
    }
}

/**
 * Global click interceptor for all PDF export links to prevent 401/403 navigation errors.
 */
export function initPdfExportDelegation() {
    if (window._pdfExportDelegated) return;
    window._pdfExportDelegated = true;

    document.addEventListener("click", (e) => {
        const link = e.target.closest('a[href*="/export_pdf"], button[data-export-pdf], a[data-export-pdf]');
        if (link) {
            e.preventDefault();
            e.stopPropagation();
            const href = link.getAttribute("href") || link.getAttribute("data-export-pdf") || "";
            if (!href || href === "#") return;

            let defaultName = link.dataset?.filename || link.getAttribute("data-filename") || "";
            if (!defaultName) {
                if (href.includes("/history/")) defaultName = "print_history.pdf";
                else if (href.includes("/spools/movements/")) defaultName = "spool_movements.pdf";
                else if (href.includes("/spools/")) defaultName = "spools_inventory.pdf";
                else if (href.includes("/parts/")) defaultName = "parts_inventory.pdf";
                else if (href.includes("/commercial/")) defaultName = "commercial_quote.pdf";
                else defaultName = "report.pdf";
            }

            downloadAuthenticatedPdf(href, defaultName, link);
        }
    });
}

// Printers API
export async function fetchPrintersApi() {
    const res = await apiFetch("/api/printers");
    if (!res.ok) {
        const err = new Error(`HTTP error ${res.status}`);
        err.status = res.status;
        throw err;
    }
    return res.json();
}

export async function createPrinterApi(printerData) {
    const res = await apiFetch("/api/printers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(printerData)
    });
    return res.json();
}

export async function controlPrinterApi(printerId, action, params = {}) {
    const res = await apiFetch(`/api/printers/${printerId}/control`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, ...params })
    });
    return res.json();
}

export async function fetchPrinterSettingsApi(printerId) {
    const res = await apiFetch(`/api/printers/${printerId}/settings`);
    return res.json();
}

export async function savePrinterSettingsApi(printerId, settings) {
    const res = await apiFetch(`/api/printers/${printerId}/settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings)
    });
    return res.json();
}

export async function deletePrinterApi(printerId) {
    const res = await apiFetch(`/api/printers/${printerId}`, { method: "DELETE" });
    return res.json();
}

export async function sendFleetLightsApi(action = "on", printerIds = null) {
    const payload = { action };
    if (printerIds && Array.isArray(printerIds)) payload.printer_ids = printerIds;
    const res = await apiFetch("/api/fleet/lights", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });
    return res.json();
}

export async function sendFleetCalibrateApi(printerIds = null) {
    const payload = {};
    if (printerIds && Array.isArray(printerIds)) payload.printer_ids = printerIds;
    const res = await apiFetch("/api/fleet/calibrate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });
    return res.json();
}

// Spools API
export async function fetchSpoolsApi() {
    const res = await apiFetch("/api/spools");
    if (!res.ok) {
        const err = new Error(`HTTP error ${res.status}`);
        err.status = res.status;
        throw err;
    }
    return res.json();
}

export async function saveSpoolApi(spoolData) {
    const res = await apiFetch("/api/spools", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(spoolData)
    });
    return res.json();
}

export async function deleteSpoolApi(spoolId) {
    const res = await apiFetch(`/api/spools/${spoolId}`, { method: "DELETE" });
    return res.json();
}

export async function mountSpoolApi(spoolId, printerId, slotKey = "0") {
    const res = await apiFetch(`/api/spools/${spoolId}/mount`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ printer_id: printerId, slot_key: String(slotKey) })
    });
    return res.json();
}

export async function unmountSpoolApi(spoolId) {
    const res = await apiFetch(`/api/spools/${spoolId}/unmount`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({})
    });
    return res.json();
}

export async function fetchSpoolMovementsApi() {
    const res = await apiFetch("/api/spools/movements");
    return res.json();
}

export function getMovementsPdfExportUrl(filters = {}) {
    const params = new URLSearchParams();
    if (filters.spool_id) params.set("spool_id", filters.spool_id);
    if (filters.action) params.set("action", filters.action);
    if (filters.period) params.set("period", filters.period);
    if (filters.q) params.set("q", filters.q);
    const token = getSessionToken();
    if (token) params.set("token", token);
    const initData = getTelegramInitData();
    if (initData) params.set("initData", initData);
    return `/api/spools/movements/export_pdf?${params.toString()}`;
}

// Parts API
export async function fetchPartsApi() {
    const res = await apiFetch("/api/parts");
    return res.json();
}

export async function savePartApi(partData) {
    const res = await apiFetch("/api/parts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(partData)
    });
    return res.json();
}

export async function deletePartApi(partId) {
    const res = await apiFetch(`/api/parts/${partId}`, { method: "DELETE" });
    return res.json();
}

export async function printPartApi(partId, printerId) {
    const res = await apiFetch(`/api/parts/${partId}/print/${printerId}`, {
        method: "POST"
    });
    return res.json();
}

// Files & Uploads API
export async function uploadFileApi(formData) {
    const res = await apiFetch("/api/files/upload", {
        method: "POST",
        body: formData
    });
    return res.json();
}

export async function uploadImageApi(formData) {
    const res = await apiFetch("/api/files/upload_image", {
        method: "POST",
        body: formData
    });
    return res.json();
}

// History API
export async function fetchHistoryApi() {
    const res = await apiFetch("/api/history");
    return res.json();
}

export async function deleteHistoryItemApi(timestamp) {
    const res = await apiFetch(`/api/history?timestamp=${encodeURIComponent(timestamp)}`, {
        method: "DELETE"
    });
    return res.json();
}

export async function clearAllHistoryApi() {
    const res = await apiFetch("/api/history", { method: "DELETE" });
    return res.json();
}

export async function markScrapApi(scrapData) {
    const res = await apiFetch("/api/history/mark_scrap", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(scrapData)
    });
    return res.json();
}

// Commercial Presets API
export async function fetchCommercialPresetsApi() {
    const res = await apiFetch("/api/commercial/presets");
    return res.json();
}

export async function saveCommercialPresetApi(presetData) {
    const res = await apiFetch("/api/commercial/presets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(presetData)
    });
    return res.json();
}

export async function deleteCommercialPresetApi(presetId) {
    const res = await apiFetch(`/api/commercial/presets/${presetId}`, {
        method: "DELETE"
    });
    return res.json();
}

export async function calculateCommercialApi(params) {
    const res = await apiFetch("/api/commercial/calculate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params)
    });
    return res.json();
}

// User & Settings API
export async function fetchUserSettingsApi() {
    const res = await apiFetch("/api/user/settings");
    return res.json();
}

export async function saveUserSettingsApi(settings) {
    const res = await apiFetch("/api/user/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings)
    });
    return res.json();
}

export async function fetchGlobalSettingsApi() {
    const res = await apiFetch("/api/settings");
    return res.json();
}

export async function saveGlobalSettingsApi(settings) {
    const res = await apiFetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings)
    });
    return res.json();
}

export async function fetchHealthApi() {
    const res = await apiFetch("/health");
    return res.json();
}

export async function fetchUsersApi() {
    const res = await apiFetch("/api/users");
    return res.json();
}

export async function saveUserAccessApi(userData) {
    const res = await apiFetch("/api/users/access", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(userData)
    });
    return res.json();
}

export async function deleteUserApi(userId) {
    const res = await apiFetch("/api/users/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId })
    });
    return res.json();
}

// Files API
export async function fetchFilesApi() {
    try {
        const res = await apiFetch("/api/files");
        if (res.ok) return await res.json();
    } catch (_) {}
    return { files: [] };
}

// Unified API Facade
export const api = {
    getPrinters: fetchPrintersApi,
    getSpools: fetchSpoolsApi,
    sendPrinterAction: (printerId, actionPayload) => controlPrinterApi(printerId, actionPayload?.action || actionPayload, actionPayload),
    addPrinter: createPrinterApi,
    deletePrinter: deletePrinterApi,
    getPrinterSettings: fetchPrinterSettingsApi,
    savePrinterSettings: savePrinterSettingsApi,
    getParts: fetchPartsApi,
    savePart: savePartApi,
    deletePart: deletePartApi,
    printPart: printPartApi,
    getHistory: fetchHistoryApi,
    getCommercialPresets: fetchCommercialPresetsApi,
    saveCommercialPreset: saveCommercialPresetApi,
    deleteCommercialPreset: deleteCommercialPresetApi,
    calculateCommercial: calculateCommercialApi,
    fetchFiles: fetchFilesApi,
    getHealth: fetchHealthApi,
    getGlobalSettings: fetchGlobalSettingsApi,
    saveGlobalSettings: saveGlobalSettingsApi,
};
