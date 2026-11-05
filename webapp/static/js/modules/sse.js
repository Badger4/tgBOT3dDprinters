/**
 * 3D Farm Manager - SSE Real-Time Telemetry Stream & Tab Lifecycle
 */

import { getTelegramInitData, getSessionToken } from "./api.js";

let evtSource = null;
let sseRetryCount = 0;
let reconnectTimer = null;
const lastPrinterStates = new Map();
let visibilityListenerBound = false;
let visibilityCallbacks = {
    onVisible: null,
    onHidden: null
};

let activeCallbacks = {
    onPrinters: null,
    onFinish: null,
    onOpen: null,
    onError: null
};

export function resetSSEStateCache() {
    lastPrinterStates.clear();
}

export function initSSEStream(callbacks = {}) {
    // 1. Always record callbacks first, even if the document is currently hidden or EventSource is unavailable
    if (callbacks) {
        if (typeof callbacks === "function") {
            activeCallbacks.onPrinters = callbacks;
        } else if (typeof callbacks === "object") {
            if (callbacks.onPrinters !== undefined) activeCallbacks.onPrinters = callbacks.onPrinters;
            if (callbacks.onFinish !== undefined) activeCallbacks.onFinish = callbacks.onFinish;
            if (callbacks.onOpen !== undefined) activeCallbacks.onOpen = callbacks.onOpen;
            if (callbacks.onError !== undefined) activeCallbacks.onError = callbacks.onError;
        }
    }

    if (!window.EventSource) return null;
    if (document.visibilityState === "hidden") return null;

    // Cancel pending reconnect timer if any
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }

    // Close any existing connection cleanly
    if (evtSource) {
        try { evtSource.close(); } catch (_) {}
        evtSource = null;
    }

    try {
        const initData = getTelegramInitData();
        const token = getSessionToken();
        const params = [];
        if (initData) params.push(`initData=${encodeURIComponent(initData)}`);
        if (token) params.push(`token=${encodeURIComponent(token)}`);
        const queryStr = params.length > 0 ? "?" + params.join("&") : "";

        evtSource = new EventSource("/api/events" + queryStr);

        evtSource.onopen = function() {
            sseRetryCount = 0;
            if (typeof activeCallbacks.onOpen === "function") {
                activeCallbacks.onOpen();
            }
        };

        evtSource.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                if (Array.isArray(data)) {
                    if (typeof activeCallbacks.onPrinters === "function") {
                        activeCallbacks.onPrinters(data);
                    }
                    let newlyFinished = false;
                    for (const p of data) {
                        if (!p) continue;
                        const pKey = String(p.id ?? p.name ?? "");
                        const currState = String(p.state || "").toUpperCase();
                        const prevState = lastPrinterStates.get(pKey);
                        if (currState === "FINISH" && prevState !== "FINISH") {
                            newlyFinished = true;
                        }
                        if (pKey) {
                            lastPrinterStates.set(pKey, currState);
                        }
                    }
                    if (newlyFinished && typeof activeCallbacks.onFinish === "function") {
                        activeCallbacks.onFinish();
                    }
                }
            } catch (e) {
                console.error("SSE parse error:", e);
            }
        };

        evtSource.onerror = function(err) {
            if (evtSource) {
                try { evtSource.close(); } catch (_) {}
                evtSource = null;
            }
            if (typeof activeCallbacks.onError === "function") {
                activeCallbacks.onError(err);
            }
            const delay = Math.min(30000, 1000 * Math.pow(1.5, sseRetryCount++));
            if (reconnectTimer) clearTimeout(reconnectTimer);
            reconnectTimer = setTimeout(() => {
                reconnectTimer = null;
                if (!evtSource && document.visibilityState !== "hidden") {
                    initSSEStream();
                }
            }, delay);
        };

        return evtSource;
    } catch (e) {
        console.error("SSE initialization failed:", e);
        return null;
    }
}

export function closeSSEStream() {
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
    if (evtSource) {
        try { evtSource.close(); } catch (_) {}
        evtSource = null;
    }
}

export function setupVisibilityHandler(options = {}) {
    const BLANK_PIXEL = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";
    const callbacks = (typeof options === "function") ? { onVisible: options } : (options || {});
    visibilityCallbacks.onVisible = callbacks.onVisible || null;
    visibilityCallbacks.onHidden = callbacks.onHidden || null;

    if (visibilityListenerBound) return;
    visibilityListenerBound = true;

    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            closeSSEStream();
            const cImg = document.getElementById("camera-snapshot-img");
            const fsImg = document.getElementById("fullscreen-camera-img");
            if (cImg) cImg.src = BLANK_PIXEL;
            if (fsImg) fsImg.src = BLANK_PIXEL;
            if (typeof visibilityCallbacks.onHidden === "function") visibilityCallbacks.onHidden();
        } else {
            // Re-open SSE stream using stored activeCallbacks
            initSSEStream();
            if (typeof visibilityCallbacks.onVisible === "function") visibilityCallbacks.onVisible();
        }
    });
}
