/**
 * 3D Farm Manager - API Client Module
 * Provides unified HTTP client with automatic auth headers (Telegram initData & Web session tokens).
 */

export function getSessionToken() {
    return localStorage.getItem("3d_farm_session") || "";
}

export function getTelegramInitData() {
    return window.Telegram?.WebApp?.initData || "";
}

export async function apiFetch(url, options = {}) {
    const opts = { ...options };
    opts.headers = { ...(opts.headers || {}) };

    const token = getSessionToken();
    if (token && !opts.headers["X-Session-Token"] && !opts.headers["Authorization"]) {
        opts.headers["X-Session-Token"] = token;
    }

    const initData = getTelegramInitData();
    if (initData && !opts.headers["X-Telegram-Init-Data"]) {
        opts.headers["X-Telegram-Init-Data"] = initData;
    }

    // Bypass localtunnel reminder screen
    opts.headers["Bypass-Tunnel-Reminder"] = "true";

    const res = await fetch(url, opts);
    if (res.status === 401) {
        if (!window.Telegram?.WebApp?.initData) {
            window.location.href = "/login";
        }
    }
    return res;
}

export function initSseStream(onEvent, onError) {
    const initData = getTelegramInitData();
    const token = getSessionToken();
    let url = "/api/events";
    const params = [];
    if (initData) params.push(`initData=${encodeURIComponent(initData)}`);
    if (token) params.push(`token=${encodeURIComponent(token)}`);
    if (params.length > 0) {
        url += "?" + params.join("&");
    }

    const evtSource = new EventSource(url);
    evtSource.onmessage = (e) => {
        try {
            const data = JSON.parse(e.data);
            if (onEvent) onEvent(data);
        } catch (err) {
            console.error("SSE parse error:", err);
        }
    };
    evtSource.onerror = (err) => {
        if (onError) onError(err);
    };
    return evtSource;
}
