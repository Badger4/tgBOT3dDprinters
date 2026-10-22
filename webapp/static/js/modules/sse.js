/**
 * 3D Farm Manager - SSE Real-Time Telemetry Stream & Tab Lifecycle
 */

import { getTelegramInitData, getSessionToken } from "./api.js";

let evtSource = null;
let sseRetryCount = 0;

export function initSSEStream({ onPrinters, onFinish, onOpen, onError }) {
    if (!window.EventSource) return null;
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
            if (onOpen) onOpen();
        };

        evtSource.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                if (Array.isArray(data) && data.length > 0) {
                    if (onPrinters) onPrinters(data);
                    if (data.some(p => String(p.state || "").toUpperCase() === "FINISH")) {
                        if (onFinish) onFinish();
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
            if (onError) onError(err);
            const delay = Math.min(30000, 1000 * Math.pow(1.5, sseRetryCount++));
            setTimeout(() => {
                if (!evtSource && document.visibilityState !== "hidden") {
                    initSSEStream({ onPrinters, onFinish, onOpen, onError });
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
    if (evtSource) {
        try { evtSource.close(); } catch (_) {}
        evtSource = null;
    }
}

export function setupVisibilityHandler({ onVisible, onHidden }) {
    const BLANK_PIXEL = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";
    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            closeSSEStream();
            const cImg = document.getElementById("camera-snapshot-img");
            const fsImg = document.getElementById("fullscreen-camera-img");
            if (cImg) cImg.src = BLANK_PIXEL;
            if (fsImg) fsImg.src = BLANK_PIXEL;
            if (onHidden) onHidden();
        } else {
            if (onVisible) onVisible();
        }
    });
}
