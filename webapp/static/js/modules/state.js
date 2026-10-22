/**
 * 3D Farm Manager - Centralized Application State
 */

export const state = {
    printers: [],
    selectedPrinterId: null,
    spools: {},
    editingSpoolId: null,
    selectedSpoolForAssign: null,
    parts: {},
    editingPartId: null,
    presets: {},
    editingPresetId: null,
    history: [],
    activeScrapTarget: null,
    openCamPeekIds: new Set(),
    currentLanguage: localStorage.getItem("app_lang") || "uk",
    pollInterval: null,
    allMovementsCache: [],
    movementsFiltersBound: false,
    uploadedFileData: null,
    activeFilters: {
        printerStatus: "all",
        printerQuery: "",
        spoolType: "all",
        spoolQuery: "",
        historyQuery: ""
    }
};

export function initLegacyStateBridges() {
    if (!window._openCamPeekIds) {
        window._openCamPeekIds = state.openCamPeekIds;
    }
    Object.defineProperty(window, "latestSpools", {
        get() { return state.spools; },
        set(val) { state.spools = val || {}; },
        configurable: true
    });
    Object.defineProperty(window, "spoolsData", {
        get() { return state.spools; },
        set(val) { state.spools = val || {}; },
        configurable: true
    });
    Object.defineProperty(window, "_cachedSpoolsMap", {
        get() { return state.spools; },
        set(val) { state.spools = val || {}; },
        configurable: true
    });
    Object.defineProperty(window, "_partsCache", {
        get() { return state.parts; },
        set(val) { state.parts = val || {}; },
        configurable: true
    });
    Object.defineProperty(window, "_cachedPrintersForSpools", {
        get() { return state.printers; },
        set(val) { state.printers = val || []; },
        configurable: true
    });
}
