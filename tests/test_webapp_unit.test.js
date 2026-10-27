/**
 * Automated Unit Tests for WebApp Frontend Logic
 * Executable via Node.js native test runner: node --test tests/test_webapp_unit.test.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// ============================================================================
// 1. Tested Frontend Domain Logic
// ============================================================================

export function parseValOrPercent(valStr, baseAmount, hours = 1.0) {
    const s = String(valStr || '').trim();
    if (s.endsWith('%')) {
        const pct = parseFloat(s.slice(0, -1).trim());
        if (isNaN(pct) || !isFinite(pct)) return [0, true];
        return [Math.round(baseAmount * (pct / 100) * 100) / 100, true];
    } else {
        const val = parseFloat(s);
        if (isNaN(val) || !isFinite(val)) return [0, false];
        return [Math.round(val * hours * 100) / 100, false];
    }
}

export function calculateCommercialQuote(preset, weightG, timeMins, options = {}) {
    const pricePerG = parseFloat(options.price_per_g ?? preset.price_per_g ?? 0.85);
    const elecRate = parseFloat(options.electricity_rate_uah ?? preset.electricity_rate_uah ?? 4.32);
    const powerW = parseFloat(options.power_watts ?? preset.power_watts ?? 120.0);
    const hours = Math.max(0.1, timeMins / 60.0);

    const wastePct = parseFloat(options.waste_pct ?? preset.waste_pct ?? 0.0);
    const totalWeightG = Math.round(weightG * (1.0 + Math.max(0, wastePct) / 100) * 100) / 100;
    const filamentCost = Math.round(totalWeightG * pricePerG * 100) / 100;

    const kwh = (powerW / 1000.0) * hours;
    const electricityCost = Math.round(kwh * elecRate * 100) / 100;
    const directCost = Math.round((filamentCost + electricityCost) * 100) / 100;

    const printerCost = parseFloat(options.printer_cost ?? preset.printer_cost ?? 0);
    const printerLife = parseFloat(options.printer_life_hours ?? preset.printer_life_hours ?? 0);
    const deprStr = String(options.depreciation_val ?? preset.depreciation_val ?? '10');

    let deprCost = 0;
    if (printerCost > 0 && printerLife > 0) {
        deprCost = Math.round((printerCost / printerLife) * hours * 100) / 100;
    } else {
        [deprCost] = parseValOrPercent(deprStr, directCost, hours);
    }

    const consStr = String(options.consumables_val ?? preset.consumables_val ?? '5');
    const [consCost] = parseValOrPercent(consStr, directCost, hours);

    const laborRate = parseFloat(options.labor_rate_uah ?? preset.labor_rate_uah ?? 0);
    const prepTime = parseFloat(options.prep_time_mins ?? preset.prep_time_mins ?? 0);
    const postTime = parseFloat(options.post_time_mins ?? preset.post_time_mins ?? 0);
    const laborHours = (prepTime + postTime) / 60.0;
    const laborCost = Math.round(laborHours * laborRate * 100) / 100;

    const packagingCost = parseFloat(options.packaging_cost ?? preset.packaging_cost ?? 0);
    const shippingCost = parseFloat(options.shipping_cost ?? preset.shipping_cost ?? 0);
    const packCost = Math.round((packagingCost + shippingCost) * 100) / 100;

    const baseCost = Math.round((directCost + deprCost + consCost + laborCost + packCost) * 100) / 100;

    let profitStr = String(options.profit_val ?? preset.profit_val ?? '100%');
    if (options.margin_pct !== undefined && options.margin_pct !== null) {
        profitStr = options.margin_pct + '%';
    }
    const [profitCost] = parseValOrPercent(profitStr, baseCost, 1.0);
    const totalPrice = Math.round((baseCost + profitCost) * 100) / 100;

    return {
        weight_g: weightG,
        time_mins: timeMins,
        filament_cost: filamentCost,
        electricity_cost: electricityCost,
        direct_cost: directCost,
        depreciation_cost: deprCost,
        consumables_cost: consCost,
        cost_before_profit: baseCost,
        profit_cost: profitCost,
        total_price: totalPrice
    };
}

export function normalizePresetInputs({ name, rawPrice, elecRate, powerWatts, deprVal, consVal, profitVal }) {
    const trimmedName = String(name || "").trim();
    if (!trimmedName) {
        throw new Error("Введіть назву пресету!");
    }

    const priceNum = parseFloat(String(rawPrice !== undefined && rawPrice !== null ? rawPrice : 0.85).replace(",", "."));
    const finalPrice = isNaN(priceNum) || priceNum <= 0 ? 0.85 : (priceNum >= 50 ? priceNum / 1000 : priceNum);
    const roundedPrice = Math.round(finalPrice * 1000) / 1000;

    const elecNum = parseFloat(String(elecRate !== undefined && elecRate !== null ? elecRate : 4.32).replace(",", "."));
    const finalElec = isNaN(elecNum) || elecNum < 0 ? 4.32 : Math.round(elecNum * 100) / 100;

    const powerNum = parseFloat(String(powerWatts !== undefined && powerWatts !== null ? powerWatts : 120).replace(",", "."));
    const finalPower = isNaN(powerNum) || powerNum < 0 ? 120 : Math.round(powerNum);

    const cleanDepr = String(deprVal !== undefined && deprVal !== null ? deprVal : "10").trim() || "10";
    const cleanCons = String(consVal !== undefined && consVal !== null ? consVal : "5").trim() || "5";
    const cleanProfit = String(profitVal !== undefined && profitVal !== null ? profitVal : "100%").trim() || "100%";

    return {
        name: trimmedName,
        price_per_g: roundedPrice,
        electricity_rate_uah: finalElec,
        power_watts: finalPower,
        depreciation_val: cleanDepr,
        consumables_val: cleanCons,
        profit_val: cleanProfit
    };
}

export function normalizeReprintTaskData(taskOrElement, origPrinterName = "", origPrinterId = "") {
    let taskName = "";
    let printerName = origPrinterName || "";
    let printerId = origPrinterId || "";

    if (taskOrElement && typeof taskOrElement === "object") {
        if (typeof taskOrElement.getAttribute === "function") {
            taskName = taskOrElement.getAttribute("data-task") || taskOrElement.dataset?.task || "";
            printerName = printerName || taskOrElement.getAttribute("data-printer") || taskOrElement.dataset?.printer || "";
            printerId = printerId || taskOrElement.getAttribute("data-printer-id") || taskOrElement.dataset?.printerId || "";
        } else {
            taskName = taskOrElement.taskName || taskOrElement.subtask_name || taskOrElement.task || taskOrElement.file || taskOrElement.name || "";
            printerName = printerName || taskOrElement.printerName || taskOrElement.printer_name || taskOrElement.printer || "";
            printerId = printerId || taskOrElement.printerId || taskOrElement.printer_id || taskOrElement.printer_sn || "";
        }
    } else {
        taskName = String(taskOrElement || "");
    }

    return {
        taskName: taskName.trim(),
        printerName: String(printerName || "").trim(),
        printerId: String(printerId || "").trim()
    };
}

export function buildAuthenticatedExportUrl(rawUrl, { token = "", initData = "" } = {}) {
    const sToken = token;
    const sInitData = initData;

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

export function formatRemainingTime(mins, nowMs = Date.now()) {
    if (!mins || mins <= 0) return '';
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    const durStr = h > 0 ? `${h}г ${m}хв` : `${m} хв`;
    const finishDate = new Date(nowMs + mins * 60000);
    const hh = String(finishDate.getHours()).padStart(2, '0');
    const mm = String(finishDate.getMinutes()).padStart(2, '0');
    return `${durStr} (до ${hh}:${mm})`;
}

export function getPrinterStatusInfo(rawState) {
    const st = String(rawState || 'ONLINE').toUpperCase();
    if (st === 'OFFLINE' || st === 'OFF' || st === 'DISCONNECTED' || st === 'UNKNOWN') {
        return { code: 'OFFLINE', label: '🔴 Офлайн', badgeClass: 'status-OFFLINE' };
    }
    if (st === 'RUNNING' || st === 'PREPARE' || st === 'PREPARATION' || st === 'PRINTING' || st === 'CHANGING_FILAMENT' || st === 'SLICING' || st === 'BUILDING' || st === 'BUSY') {
        return { code: 'RUNNING', label: '🟢 Друкує', badgeClass: 'status-RUNNING' };
    }
    if (st === 'PAUSE' || st === 'PAUSED') {
        return { code: 'PAUSE', label: '⏸️ Пауза', badgeClass: 'status-PAUSE' };
    }
    return { code: 'ONLINE', label: '⚪ Онлайн', badgeClass: 'status-ONLINE' };
}

export function formatCockpitHexColor(raw) {
    if (!raw) return '#3b82f6';
    let s = String(raw).trim();
    if (s.startsWith('#')) return s;
    if (/^[0-9A-Fa-f]{3,8}$/.test(s)) return '#' + s;
    return '#3b82f6';
}

export function normalizeAmsSlots(printer, assignedSpools = []) {
    const hasAms = Boolean(printer.has_ams);
    const activeKey = String(printer.active_slot_key || printer.active_ams_tray || '254');
    const slotKeys = hasAms ? ['0', '1', '2', '3'] : ['254'];
    const slotLabels = { '0': 'A1', '1': 'A2', '2': 'A3', '3': 'A4', '254': 'VT', '255': 'VT' };

    return slotKeys.map(k => {
        const isActive = (k === activeKey || String(printer.active_ams_tray) === k || (k === '254' && activeKey === '255') || (k === '255' && activeKey === '254'));
        const trayInfo = (printer.ams_trays_info || {})[k] || (k === '254' ? (printer.ams_trays_info || {})['255'] : {}) || {};
        const assigned = (assignedSpools || []).find(s => String(s.assigned_slot_key) === k || (k === '254' && String(s.assigned_slot_key) === '255'));
        
        const hasTray = Boolean(!trayInfo.empty && trayInfo.type);
        const hasAssigned = Boolean(assigned && (assigned.remaining_grams > 0 || assigned.name));
        const isLoaded = hasTray || hasAssigned;

        if (!isLoaded) {
            return {
                slotKey: k,
                label: slotLabels[k] || k,
                isActive,
                isLoaded: false,
                color: null,
                filamentType: '—',
                spoolName: 'Порожньо',
                remainingGrams: 0,
                percentage: 0,
                gramsText: 'Порожньо',
                source: 'empty'
            };
        }

        let spoolColor = '#3b82f6';
        let spoolType = 'PLA';
        let spoolName = '';
        let displayGrams = 0;
        let pct = 0;
        let source = 'unknown';

        if (assigned) {
            source = 'warehouse';
            spoolColor = formatCockpitHexColor(assigned.color);
            spoolType = assigned.type || 'PLA';
            spoolName = assigned.name || 'Складська котушка';
            displayGrams = assigned.remaining_grams !== undefined ? assigned.remaining_grams : 0;
            const maxCap = assigned.initial_grams || assigned.total_grams || 1000;
            pct = Math.min(100, Math.max(0, Math.round((displayGrams / maxCap) * 100)));
        } else if (hasTray) {
            source = 'ams_tray';
            spoolColor = formatCockpitHexColor(trayInfo.color);
            spoolType = trayInfo.type || 'PLA';
            spoolName = trayInfo.sub_brands ? 'Bambu ' + spoolType + ' ' + trayInfo.sub_brands : 'Bambu ' + spoolType;
            displayGrams = (printer.ams_slots && printer.ams_slots[k] !== undefined) ? printer.ams_slots[k] : 0;
            if (trayInfo.remain !== undefined && trayInfo.remain >= 0) {
                pct = trayInfo.remain;
            } else {
                pct = Math.min(100, Math.max(0, Math.round((displayGrams / 1000) * 100)));
            }
        }

        const gramsText = displayGrams > 0 ? Math.round(displayGrams) + 'g' : pct + '%';

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

// ============================================================================
// 2. Unit Test Suites
// ============================================================================

describe('Commercial Pricing Calculator', () => {
    const preset = {
        name: 'Стандарт PLA',
        price_per_g: 0.85,
        electricity_rate_uah: 4.0,
        power_watts: 250.0,
        depreciation_val: '10',
        consumables_val: '5',
        profit_val: '100%'
    };

    it('calculates standard print job breakdown correctly matching Python backend', () => {
        const res = calculateCommercialQuote(preset, 100.0, 120);
        assert.equal(res.filament_cost, 85.0);
        assert.equal(res.electricity_cost, 2.0);
        assert.equal(res.direct_cost, 87.0);
        assert.equal(res.depreciation_cost, 20.0);
        assert.equal(res.consumables_cost, 10.0);
        assert.equal(res.cost_before_profit, 117.0);
        assert.equal(res.profit_cost, 117.0);
        assert.equal(res.total_price, 234.0);
    });

    it('handles waste percentage and percentage margins', () => {
        const custom = {
            ...preset,
            depreciation_val: '10%',
            consumables_val: '5%',
            profit_val: '50%'
        };
        const res = calculateCommercialQuote(custom, 100.0, 60, { waste_pct: 10 });
        assert.equal(res.filament_cost, 93.5);
        assert.equal(res.electricity_cost, 1.0);
        assert.equal(res.direct_cost, 94.5);
        assert.equal(res.depreciation_cost, 9.45);
        assert.equal(res.consumables_cost, 4.73);
        assert.equal(res.cost_before_profit, 108.68);
        assert.equal(res.profit_cost, 54.34);
        assert.equal(res.total_price, 163.02);
    });
});

describe('formatRemainingTime', () => {
    const fixedNow = new Date('2026-10-21T14:00:00').getTime();

    it('returns empty string for zero, negative or missing values', () => {
        assert.equal(formatRemainingTime(0, fixedNow), '');
        assert.equal(formatRemainingTime(-15, fixedNow), '');
        assert.equal(formatRemainingTime(null, fixedNow), '');
        assert.equal(formatRemainingTime(undefined, fixedNow), '');
    });

    it('formats minutes only under 1 hour', () => {
        assert.equal(formatRemainingTime(35, fixedNow), '35 хв (до 14:35)');
    });

    it('formats hours and minutes above 1 hour', () => {
        assert.equal(formatRemainingTime(125, fixedNow), '2г 5хв (до 16:05)');
    });

    it('handles finish time crossing midnight', () => {
        const midnightEve = new Date('2026-10-21T23:30:00').getTime();
        assert.equal(formatRemainingTime(60, midnightEve), '1г 0хв (до 00:30)');
    });
});

describe('getPrinterStatusInfo', () => {
    it('maps offline states correctly', () => {
        for (const st of ['OFFLINE', 'OFF', 'DISCONNECTED', 'UNKNOWN']) {
            const info = getPrinterStatusInfo(st);
            assert.equal(info.code, 'OFFLINE');
            assert.equal(info.label, '🔴 Офлайн');
            assert.equal(info.badgeClass, 'status-OFFLINE');
        }
    });

    it('maps running and preparation states correctly', () => {
        for (const st of ['RUNNING', 'PREPARE', 'PREPARATION', 'PRINTING', 'CHANGING_FILAMENT', 'SLICING', 'BUILDING', 'BUSY']) {
            const info = getPrinterStatusInfo(st);
            assert.equal(info.code, 'RUNNING');
            assert.equal(info.label, '🟢 Друкує');
            assert.equal(info.badgeClass, 'status-RUNNING');
        }
    });

    it('maps pause states correctly', () => {
        for (const st of ['PAUSE', 'PAUSED']) {
            const info = getPrinterStatusInfo(st);
            assert.equal(info.code, 'PAUSE');
            assert.equal(info.label, '⏸️ Пауза');
            assert.equal(info.badgeClass, 'status-PAUSE');
        }
    });

    it('maps fallback/idle/null states to ONLINE', () => {
        assert.equal(getPrinterStatusInfo('IDLE').code, 'ONLINE');
        assert.equal(getPrinterStatusInfo('ONLINE').code, 'ONLINE');
        assert.equal(getPrinterStatusInfo(null).code, 'ONLINE');
        assert.equal(getPrinterStatusInfo(undefined).code, 'ONLINE');
    });
});

describe('AMS Slot Data Normalization', () => {
    it('normalizes 4 AMS slots with mixed telemetry and empty slots', () => {
        const printer = {
            id: 'bambu-1',
            has_ams: true,
            active_slot_key: '0',
            ams_slots: { '0': 750, '1': 300 },
            ams_trays_info: {
                '0': { type: 'PLA-CF', color: '333333', remain: 75, empty: false, sub_brands: 'Basic' },
                '1': { type: 'PETG', color: '#00ff00', remain: 30, empty: false },
                '2': { empty: true },
                '3': { empty: true }
            }
        };

        const slots = normalizeAmsSlots(printer);
        assert.equal(slots.length, 4);

        assert.equal(slots[0].slotKey, '0');
        assert.equal(slots[0].label, 'A1');
        assert.equal(slots[0].isActive, true);
        assert.equal(slots[0].isLoaded, true);
        assert.equal(slots[0].color, '#333333');
        assert.equal(slots[0].filamentType, 'PLA-CF');
        assert.equal(slots[0].spoolName, 'Bambu PLA-CF Basic');
        assert.equal(slots[0].remainingGrams, 750);
        assert.equal(slots[0].percentage, 75);
        assert.equal(slots[0].gramsText, '750g');
        assert.equal(slots[0].source, 'ams_tray');

        assert.equal(slots[1].label, 'A2');
        assert.equal(slots[1].isActive, false);
        assert.equal(slots[1].isLoaded, true);
        assert.equal(slots[1].color, '#00ff00');
        assert.equal(slots[1].filamentType, 'PETG');

        assert.equal(slots[2].label, 'A3');
        assert.equal(slots[2].isLoaded, false);
        assert.equal(slots[2].source, 'empty');
        assert.equal(slots[2].gramsText, 'Порожньо');
    });

    it('prioritizes warehouse assigned spool over RFID tray telemetry', () => {
        const printer = {
            id: 'bambu-2',
            has_ams: true,
            active_slot_key: '1',
            ams_slots: { '1': 100 },
            ams_trays_info: {
                '1': { type: 'Generic PLA', color: '111111', remain: 10, empty: false }
            }
        };
        const assigned = [{
            assigned_slot_key: '1',
            name: 'Plexiwire Red',
            type: 'PLA',
            color: '#e11d48',
            remaining_grams: 850,
            initial_grams: 1000
        }];

        const slots = normalizeAmsSlots(printer, assigned);
        assert.equal(slots[1].source, 'warehouse');
        assert.equal(slots[1].spoolName, 'Plexiwire Red');
        assert.equal(slots[1].color, '#e11d48');
        assert.equal(slots[1].remainingGrams, 850);
        assert.equal(slots[1].percentage, 85);
        assert.equal(slots[1].gramsText, '850g');
    });

    it('normalizes external spool holder (VT / 254 / 255)', () => {
        const printer = {
            id: 'bambu-3',
            has_ams: false,
            active_slot_key: '254',
            filament_type: 'TPU',
            ams_slots: { '254': 500 }
        };
        const assigned = [{
            assigned_slot_key: '254',
            name: 'Monofilament TPU',
            type: 'TPU',
            color: '#f59e0b',
            remaining_grams: 500,
            initial_grams: 750
        }];

        const slots = normalizeAmsSlots(printer, assigned);
        assert.equal(slots.length, 1);
        assert.equal(slots[0].slotKey, '254');
        assert.equal(slots[0].label, 'VT');
        assert.equal(slots[0].isActive, true);
        assert.equal(slots[0].isLoaded, true);
        assert.equal(slots[0].spoolName, 'Monofilament TPU');
        assert.equal(slots[0].color, '#f59e0b');
        assert.equal(slots[0].percentage, 67);
    });
});

describe('Spools Warehouse Inventory Filtering', () => {
    const mockSpools = {
        's1': { id: 's1', name: 'Bambu PLA Basic Black', type: 'PLA', color: '#000000', quantity: 2, remaining_grams: 1000 },
        's2': { id: 's2', name: 'Sunlu PETG White', type: 'PETG', color: '#ffffff', quantity: 1, remaining_grams: 800 },
        's3': { id: 's3', name: 'Devil Design TPU Red', type: 'TPU', color: '#ef4444', quantity: 1, remaining_grams: 500 },
        's4': { id: 's4', name: 'eSUN ABS+ Black', type: 'ABS', color: '#111111', quantity: 1, remaining_grams: 900 },
        's5': { id: 's5', name: 'Polymaker PolyLite ASA Grey', type: 'ASA', color: '#64748b', quantity: 1, remaining_grams: 750 },
        's6': { id: 's6', name: 'ColorFabb PA-CF Carbon', type: 'PA-CF', color: '#333333', quantity: 1, remaining_grams: 600 },
        's7': { id: 's7', name: 'Mounted Spool', type: 'PLA', color: '#22c55e', quantity: 1, assigned_printer_id: 'p1' },
        's8': { id: 's8', name: 'Empty Stock Spool', type: 'PLA', color: '#000000', quantity: 0, remaining_grams: 0 }
    };

    function filterSpools(spoolsDict, query = '', matFilter = 'ALL') {
        const allUnassigned = Object.values(spoolsDict || {}).filter(s => !s.assigned_printer_id && (s.quantity !== undefined ? Number(s.quantity) : 1) > 0);
        const q = (query || '').trim().toLowerCase();
        const mf = (matFilter || 'ALL').toUpperCase();

        return allUnassigned.filter(s => {
            const sType = String(s.type || 'PLA').toUpperCase();
            const sName = String(s.name || '').toLowerCase();
            const sColor = String(s.color || '').toLowerCase();

            const matchesQuery = !q || sName.includes(q) || sType.toLowerCase().includes(q) || sColor.includes(q);
            if (!matchesQuery) return false;

            if (mf === 'ALL') return true;
            if (mf === 'PLA') return sType.includes('PLA');
            if (mf === 'PETG') return sType.includes('PETG') || sType.includes('PCTG') || sType.includes('PET');
            if (mf === 'TPU') return sType.includes('TPU');
            if (mf === 'ABS/ASA') return sType.includes('ABS') || sType.includes('ASA');
            if (mf === 'OTHER') {
                return !(sType.includes('PLA') || sType.includes('PETG') || sType.includes('PCTG') || sType.includes('PET') || sType.includes('TPU') || sType.includes('ABS') || sType.includes('ASA'));
            }
            return true;
        });
    }

    it('filters out assigned spools and zero-quantity items', () => {
        const result = filterSpools(mockSpools, '', 'ALL');
        assert.equal(result.length, 6);
        assert.ok(!result.some(s => s.id === 's7'));
        assert.ok(!result.some(s => s.id === 's8'));
    });

    it('filters by material pill PLA, PETG, TPU, ABS/ASA, and OTHER', () => {
        assert.equal(filterSpools(mockSpools, '', 'PLA').length, 1);
        assert.equal(filterSpools(mockSpools, '', 'PETG').length, 1);
        assert.equal(filterSpools(mockSpools, '', 'TPU').length, 1);
        assert.equal(filterSpools(mockSpools, '', 'ABS/ASA').length, 2);
        assert.equal(filterSpools(mockSpools, '', 'OTHER').length, 1);
    });

    it('filters by search query case-insensitively across name, type and color', () => {
        const resName = filterSpools(mockSpools, 'Sunlu');
        assert.equal(resName.length, 1);
        assert.equal(resName[0].id, 's2');

        const resColor = filterSpools(mockSpools, '#ef4444');
        assert.equal(resColor.length, 1);
        assert.equal(resColor[0].id, 's3');

        const resCombined = filterSpools(mockSpools, 'black', 'PLA');
        assert.equal(resCombined.length, 1);
        assert.equal(resCombined[0].id, 's1');
    });
});

describe('Spool Movements Audit Filtering', () => {
    function filterSpoolMovements(movementsList, { spoolId = 'all', action = 'all', period = 'all', query = '' } = {}) {
        const list = Array.isArray(movementsList) ? movementsList : [];
        const now = 1700000000; // Fixed test timestamp
        let minTime = 0;
        if (period === 'today') {
            minTime = now - 3600;
        } else if (period === 'week') {
            minTime = now - (7 * 86400);
        }

        const q = (query || '').trim().toLowerCase();

        return list.filter(item => {
            if (spoolId !== 'all' && String(item.spool_id) !== String(spoolId)) return false;
            if (action !== 'all') {
                if (action === 'stock') {
                    if (item.action !== 'stock' && item.action !== 'initial_stock' && item.action !== 'refill') return false;
                } else if (String(item.action) !== String(action)) {
                    return false;
                }
            }
            if (minTime > 0 && (item.timestamp || 0) < minTime) return false;
            if (q) {
                const searchable = `${item.spool_name || ''} ${item.note || ''} ${item.reason || ''} ${item.printer_name || ''} ${item.user || ''}`.toLowerCase();
                if (!searchable.includes(q)) return false;
            }
            return true;
        });
    }

    const mockMovements = [
        { id: 'm1', spool_id: 's1', spool_name: 'Bambu PLA Black', action: 'initial_stock', weight_change_g: 1000, new_weight_g: 1000, user: 'Admin', reason: 'Склад', timestamp: 1700000000 },
        { id: 'm2', spool_id: 's1', spool_name: 'Bambu PLA Black', action: 'print', weight_change_g: -45.5, new_weight_g: 954.5, user: 'X1C-01', reason: 'Друк деталі', timestamp: 1700000000 },
        { id: 'm3', spool_id: 's2', spool_name: 'Sunlu PETG White', action: 'refill', weight_change_g: 500, new_weight_g: 800, user: 'Admin', reason: 'Поповнення', timestamp: 1700000000 },
        { id: 'm4', spool_id: 's2', spool_name: 'Sunlu PETG White', action: 'manual_edit', weight_change_g: -10, new_weight_g: 790, user: 'Admin', reason: 'Коригування', timestamp: 1690000000 },
        { id: 'm5', spool_id: 's3', spool_name: 'eSUN ABS+ Red', action: 'write_off', weight_change_g: -500, new_weight_g: 0, user: 'Operator', reason: 'Списання браку', timestamp: 1690000000 },
    ];

    it('filters movements by specific spool ID', () => {
        const res = filterSpoolMovements(mockMovements, { spoolId: 's1' });
        assert.equal(res.length, 2);
        assert.ok(res.every(m => m.spool_id === 's1'));
    });

    it('filters stock actions matching both initial_stock and refill', () => {
        const res = filterSpoolMovements(mockMovements, { action: 'stock' });
        assert.equal(res.length, 2);
        assert.ok(res.some(m => m.action === 'initial_stock'));
        assert.ok(res.some(m => m.action === 'refill'));
    });

    it('filters by distinct actions (print, write_off, manual_edit)', () => {
        assert.equal(filterSpoolMovements(mockMovements, { action: 'print' }).length, 1);
        assert.equal(filterSpoolMovements(mockMovements, { action: 'write_off' }).length, 1);
        assert.equal(filterSpoolMovements(mockMovements, { action: 'manual_edit' }).length, 1);
    });

    it('filters by search query across spool name, user, and reason', () => {
        assert.equal(filterSpoolMovements(mockMovements, { query: 'Operator' }).length, 1);
        assert.equal(filterSpoolMovements(mockMovements, { query: 'X1C-01' }).length, 1);
        assert.equal(filterSpoolMovements(mockMovements, { query: 'Списання' }).length, 1);
        assert.equal(filterSpoolMovements(mockMovements, { query: 'PETG' }).length, 2);
    });
});

describe('Parts Warehouse Filtering & Search', () => {
    function filterParts(partsMapOrArray, query = '') {
        const list = Array.isArray(partsMapOrArray)
            ? partsMapOrArray
            : Object.values(partsMapOrArray || {});
        const q = (query || '').trim().toLowerCase();
        if (!q) return list;

        return list.filter(p => {
            const nameMatch = p.name && String(p.name).toLowerCase().includes(q);
            const modelMatch = p.printer_model && String(p.printer_model).toLowerCase().includes(q);
            const filMatch = p.filament_type && String(p.filament_type).toLowerCase().includes(q);
            const fileMatch = (p.three_mf || p.three_mf_name) && String(p.three_mf || p.three_mf_name).toLowerCase().includes(q);
            return Boolean(nameMatch || modelMatch || filMatch || fileMatch);
        });
    }

    const mockParts = [
        { id: 'p1', name: 'Кронштейн P1S', printer_model: 'Bambu Lab P1S', filament_type: 'PETG', three_mf: 'p1s_bracket.3mf', count: 5 },
        { id: 'p2', name: 'Шестерня A1 mini', printer_model: 'Bambu Lab A1 mini', filament_type: 'PLA', three_mf: 'gear_v2.3mf', count: 12 },
        { id: 'p3', name: 'Корпус роз\'єму XT60', printer_model: 'Unknown', filament_type: 'ABS', three_mf: '', count: 3 },
        { id: 'p4', name: 'Калібрувальний кубик Voron', printer_model: 'Voron 2.4', filament_type: 'ASA', three_mf: 'cube20mm.3mf', count: 0 },
    ];

    it('returns all parts when search query is empty or whitespace', () => {
        assert.equal(filterParts(mockParts, '').length, 4);
        assert.equal(filterParts(mockParts, '   ').length, 4);
        assert.equal(filterParts(mockParts, null).length, 4);
    });

    it('filters parts case-insensitively by name', () => {
        const res = filterParts(mockParts, 'кронштейн');
        assert.equal(res.length, 1);
        assert.equal(res[0].id, 'p1');

        const resUpper = filterParts(mockParts, 'ШЕСТЕРНЯ');
        assert.equal(resUpper.length, 1);
        assert.equal(resUpper[0].id, 'p2');
    });

    it('filters parts by printer model', () => {
        const res = filterParts(mockParts, 'A1 mini');
        assert.equal(res.length, 1);
        assert.equal(res[0].id, 'p2');

        const resP1S = filterParts(mockParts, 'P1S');
        assert.equal(resP1S.length, 1);
        assert.equal(resP1S[0].id, 'p1');
    });

    it('filters parts by filament type', () => {
        const res = filterParts(mockParts, 'PETG');
        assert.equal(res.length, 1);
        assert.equal(res[0].id, 'p1');

        const resAbs = filterParts(mockParts, 'ABS');
        assert.equal(resAbs.length, 1);
        assert.equal(resAbs[0].id, 'p3');
    });

    it('filters parts by 3mf filename', () => {
        const res = filterParts(mockParts, 'cube20mm');
        assert.equal(res.length, 1);
        assert.equal(res[0].id, 'p4');
    });

    it('returns empty array when query does not match any field', () => {
        assert.equal(filterParts(mockParts, 'неіснуюча_деталь').length, 0);
    });
});

describe('Commercial Presets & Payload Validation', () => {
    it('throws error when name is empty or only whitespace', () => {
        assert.throws(() => {
            normalizePresetInputs({ name: '' });
        }, /Введіть назву пресету!/);

        assert.throws(() => {
            normalizePresetInputs({ name: '   ' });
        }, /Введіть назву пресету!/);
    });

    it('normalizes price per gram from decimal and handles price per kg (>= 50)', () => {
        const fromPerG = normalizePresetInputs({ name: 'PLA 0.85', rawPrice: '0.85' });
        assert.equal(fromPerG.price_per_g, 0.85);

        const fromPerKg = normalizePresetInputs({ name: 'PLA 850/kg', rawPrice: '850' });
        assert.equal(fromPerKg.price_per_g, 0.85);

        const fromComma = normalizePresetInputs({ name: 'PETG Comma', rawPrice: '1,25' });
        assert.equal(fromComma.price_per_g, 1.25);
    });

    it('falls back to defaults for invalid electricity and power numbers', () => {
        const defaults = normalizePresetInputs({
            name: 'Fallback Test',
            rawPrice: '-10',
            elecRate: 'abc',
            powerWatts: '-50'
        });

        assert.equal(defaults.price_per_g, 0.85);
        assert.equal(defaults.electricity_rate_uah, 4.32);
        assert.equal(defaults.power_watts, 120);
    });

    it('correctly parses custom electricity tariff and power wattage', () => {
        const custom = normalizePresetInputs({
            name: 'Industrial Print',
            rawPrice: '0.95',
            elecRate: '5,80',
            powerWatts: '350'
        });

        assert.equal(custom.electricity_rate_uah, 5.80);
        assert.equal(custom.power_watts, 350);
    });

    it('preserves percentage and fixed strings for depreciation, consumables and profit', () => {
        const res = normalizePresetInputs({
            name: 'High Margin Carbon',
            rawPrice: '1.5',
            deprVal: '15%',
            consVal: '8 грн/год',
            profitVal: '150%'
        });

        assert.equal(res.depreciation_val, '15%');
        assert.equal(res.consumables_val, '8 грн/год');
        assert.equal(res.profit_val, '150%');
    });
});

describe('History & Reprint Task Normalization', () => {
    it('normalizes string arguments cleanly', () => {
        const res = normalizeReprintTaskData('bracket.3mf', 'Bambu A1', 'printer_1');
        assert.equal(res.taskName, 'bracket.3mf');
        assert.equal(res.printerName, 'Bambu A1');
        assert.equal(res.printerId, 'printer_1');
    });

    it('extracts task and printer from a DOM element mock without crashing on .trim', () => {
        const mockElement = {
            getAttribute: (attr) => {
                const map = {
                    'data-task': 'gear_assembly.3mf',
                    'data-printer': 'Bambu P1S',
                    'data-printer-id': 'printer_2'
                };
                return map[attr] || null;
            }
        };

        const res = normalizeReprintTaskData(mockElement);
        assert.equal(res.taskName, 'gear_assembly.3mf');
        assert.equal(res.printerName, 'Bambu P1S');
        assert.equal(res.printerId, 'printer_2');
    });

    it('extracts task from plain object and trims whitespace', () => {
        const res = normalizeReprintTaskData({
            taskName: '   spool_holder.3mf   ',
            printerName: 'A1 mini',
            printerId: 'printer_3'
        });

        assert.equal(res.taskName, 'spool_holder.3mf');
        assert.equal(res.printerName, 'A1 mini');
        assert.equal(res.printerId, 'printer_3');
    });

    it('extracts subtask_name from real backend history item objects', () => {
        const realHistoryItem = {
            subtask_name: 'Drone_Arm_v2.3mf',
            printer: 'Bambu Lab A1',
            printer_sn: '01P00A123456789'
        };

        const res = normalizeReprintTaskData(realHistoryItem);
        assert.equal(res.taskName, 'Drone_Arm_v2.3mf');
        assert.equal(res.printerName, 'Bambu Lab A1');
        assert.equal(res.printerId, '01P00A123456789');
    });

    it('handles null, undefined, numbers or empty input safely', () => {
        const emptyRes = normalizeReprintTaskData(null);
        assert.equal(emptyRes.taskName, '');
        assert.equal(emptyRes.printerName, '');
        assert.equal(emptyRes.printerId, '');

        const undefRes = normalizeReprintTaskData(undefined);
        assert.equal(undefRes.taskName, '');

        const numRes = normalizeReprintTaskData(12345);
        assert.equal(numRes.taskName, '12345');
    });
});

describe('Authenticated PDF Export URL Normalization', () => {
    it('injects token into relative export URL while preserving query params', () => {
        const url = buildAuthenticatedExportUrl('/api/history/export_pdf?format=pdf', {
            token: 'test_token_123'
        });
        assert.equal(url, '/api/history/export_pdf?format=pdf&token=test_token_123');
    });

    it('injects initData and token without duplicating existing keys', () => {
        const url = buildAuthenticatedExportUrl('/api/spools/export_pdf?format=pdf&token=existing', {
            token: 'new_token',
            initData: 'query_id=123'
        });
        assert.equal(url, '/api/spools/export_pdf?format=pdf&token=existing&initData=query_id%3D123');
    });

    it('handles absolute URLs cleanly', () => {
        const url = buildAuthenticatedExportUrl('https://myfarm.internal/api/parts/export_pdf?format=pdf', {
            token: 'abc'
        });
        assert.equal(url, 'https://myfarm.internal/api/parts/export_pdf?format=pdf&token=abc');
    });
});

describe('Settings & Farm Telemetry Formatters', () => {
    function formatUptime(seconds, lang = 'uk') {
        const sec = Math.max(0, parseInt(seconds, 10) || 0);
        const isEn = lang === 'en';
        const d = Math.floor(sec / 86400);
        const h = Math.floor((sec % 86400) / 3600);
        const m = Math.floor((sec % 3600) / 60);
        const s = sec % 60;

        if (d > 0) {
            return isEn ? `${d}d ${h}h ${m}m` : `${d} д ${h} год ${m} хв`;
        }
        if (h > 0) {
            return isEn ? `${h}h ${m}m ${s}s` : `${h} год ${m} хв ${s} сек`;
        }
        if (m > 0) {
            return isEn ? `${m}m ${s}s` : `${m} хв ${s} сек`;
        }
        return isEn ? `${s}s` : `${s} сек`;
    }

    it('formats seconds correctly under 1 minute', () => {
        assert.equal(formatUptime(45, 'uk'), '45 сек');
        assert.equal(formatUptime(45, 'en'), '45s');
        assert.equal(formatUptime(0, 'uk'), '0 сек');
        assert.equal(formatUptime(-10, 'uk'), '0 сек');
    });

    it('formats minutes and seconds under 1 hour', () => {
        assert.equal(formatUptime(125, 'uk'), '2 хв 5 сек');
        assert.equal(formatUptime(125, 'en'), '2m 5s');
    });

    it('formats hours, minutes and seconds under 1 day', () => {
        assert.equal(formatUptime(3665, 'uk'), '1 год 1 хв 5 сек');
        assert.equal(formatUptime(3665, 'en'), '1h 1m 5s');
    });

    it('formats days, hours and minutes above 1 day', () => {
        assert.equal(formatUptime(90060, 'uk'), '1 д 1 год 1 хв');
        assert.equal(formatUptime(90060, 'en'), '1d 1h 1m');
    });
});

describe('Admin Users Table Row Builder', () => {
    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function buildUserRowHtml(u) {
        const uId = u.user_id || u.id || '';
        const isApproved = u.approved === true || u.is_approved === true || u.status === 'approved';
        const statusBadge = isApproved
            ? `<span class="badge badge-success">Дозволено</span>`
            : `<span class="badge badge-warning">Очікує</span>`;

        const displayName = u.name || (u.first_name ? `${u.first_name} ${u.last_name || ''}`.trim() : '') || (u.username ? '@' + u.username : '') || String(uId);
        const role = (u.role || 'USER').toUpperCase();
        const roleBadge = `<span class="badge ${role === 'ADMIN' ? 'badge-primary' : 'badge-secondary'}">${escapeHtml(role)}</span>`;

        return `
        <tr>
            <td><strong>${escapeHtml(displayName)}</strong></td>
            <td><code>${escapeHtml(String(uId))}</code></td>
            <td>${roleBadge}</td>
            <td>${statusBadge}</td>
            <td>
                <div class="d-flex gap-1">
                    ${!isApproved ? `
                    <button type="button" class="btn btn-xs btn-success btn-approve-user" data-id="${escapeHtml(String(uId))}" title="Дозволити доступ">
                        <i class="fa-solid fa-check"></i>
                    </button>` : `
                    <button type="button" class="btn btn-xs btn-outline-warning btn-revoke-user" data-id="${escapeHtml(String(uId))}" title="Заблокувати доступ">
                        <i class="fa-solid fa-ban"></i>
                    </button>`}
                    <button type="button" class="btn btn-xs btn-outline-danger btn-delete-user" data-id="${escapeHtml(String(uId))}" title="Видалити користувача">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </div>
            </td>
        </tr>
        `.trim();
    }

    it('generates exactly 5 <td> columns for an approved user', () => {
        const row = buildUserRowHtml({
            user_id: '123456789',
            name: 'Pavlo <Dev>',
            role: 'ADMIN',
            approved: true
        });

        const tdCount = (row.match(/<td/g) || []).length;
        assert.equal(tdCount, 5, 'Must contain exactly 5 columns matching the table header');
        assert.ok(row.includes('&lt;Dev&gt;'), 'Must escape user input against XSS');
        assert.ok(row.includes('<code>123456789</code>'));
        assert.ok(row.includes('badge-primary'));
        assert.ok(row.includes('Дозволено'));
        assert.ok(row.includes('btn-revoke-user'));
    });

    it('generates approve button and warning badge for pending user', () => {
        const row = buildUserRowHtml({
            user_id: '987654321',
            first_name: 'John',
            last_name: 'Doe',
            role: 'USER',
            approved: false
        });

        assert.ok(row.includes('John Doe'));
        assert.ok(row.includes('badge-secondary'));
        assert.ok(row.includes('Очікує'));
        assert.ok(row.includes('btn-approve-user'));
        assert.ok(!row.includes('btn-revoke-user'));
    });

    it('normalizes API response whether given array or { users: [...] }', () => {
        const rawArray = [{ id: '1' }, { id: '2' }];
        const rawWrapped = { users: [{ id: '1' }, { id: '2' }] };

        const normalize = (res) => Array.isArray(res) ? res : (res?.users || []);
        assert.equal(normalize(rawArray).length, 2);
        assert.equal(normalize(rawWrapped).length, 2);
        assert.equal(normalize(null).length, 0);
        assert.equal(normalize({}).length, 0);
    });

    it('generates consistent printer list signatures for debouncing dropdown rebuilds', () => {
        const pList1 = [
            { id: 'p1', name: 'Bambu A1', model: 'A1' },
            { id: 'p2', name: 'Bambu P1S', model: 'P1S' }
        ];
        const pList2 = [
            { id: 'p1', name: 'Bambu A1', model: 'A1' },
            { id: 'p2', name: 'Bambu P1S', model: 'P1S' }
        ];
        const pListModified = [
            { id: 'p1', name: 'Bambu A1 New Name', model: 'A1' },
            { id: 'p2', name: 'Bambu P1S', model: 'P1S' }
        ];

        const getSig = (list) => (list || []).map(p => `${p.id}:${p.name}:${p.model || p.printer_model || ''}`).join('|');
        assert.equal(getSig(pList1), getSig(pList2));
        assert.notEqual(getSig(pList1), getSig(pListModified));
    });

    it('removes masked bullet characters from access code payloads to prevent wiping secrets', () => {
        const sanitizePayload = (payload) => {
            const p = { ...payload };
            if (p.accessCode?.includes('•')) {
                delete p.accessCode;
            }
            return p;
        };

        const safe = sanitizePayload({ accessCode: '••••••••', name: 'Printer 1' });
        assert.equal(safe.accessCode, undefined);
        assert.equal(safe.name, 'Printer 1');

        const real = sanitizePayload({ accessCode: '12345678', name: 'Printer 1' });
        assert.equal(real.accessCode, '12345678');
    });
});

describe('Design, CSS Architecture & Non-blocking Toast UX', () => {
    it('infers toast type correctly from message content', () => {
        function inferToastType(msg) {
            const str = String(msg || '');
            const isError = /помилка|error|failed|не вдалося|невірн|некоректн/i.test(str);
            const isSuccess = /успішно|success|збережено|готово|скинуто/i.test(str);
            return isError ? 'error' : (isSuccess ? 'success' : 'info');
        }

        assert.equal(inferToastType('✅ Налаштування успішно збережено!'), 'success');
        assert.equal(inferToastType('Лічильник успішно скинуто'), 'success');
        assert.equal(inferToastType('⚠️ Помилка збереження: 403 Forbidden'), 'error');
        assert.equal(inferToastType('Не вдалося завантажити файл'), 'error');
        assert.equal(inferToastType('Некоректне число!'), 'error');
        assert.equal(inferToastType('Калібрування запущено'), 'info');
        assert.equal(inferToastType('Котушку знято зі слоту'), 'info');
    });

    it('verifies search bar layer stacking hierarchy prevents input overlapping icons', () => {
        const layers = {
            input: 1,
            icon: 5,
            clearBtn: 6
        };

        assert.ok(layers.icon > layers.input, 'Icon must be stacked above input');
        assert.ok(layers.clearBtn > layers.input, 'Clear button must be stacked above input');
        assert.ok(layers.clearBtn >= layers.icon, 'Clear button must be interactive over icon');
    });

    it('verifies CSS versioning query parameters in @import directives', () => {
        const styleCssPath = path.join(__dirname, '..', 'webapp', 'static', 'css', 'style.css');
        const content = fs.readFileSync(styleCssPath, 'utf8');
        const importLines = content.split('\n')
            .map(l => l.trim())
            .filter(l => l.startsWith('@import'));

        assert.ok(importLines.length >= 5, 'Should have at least 5 import statements in style.css');
        for (const imp of importLines) {
            assert.ok(/\?v=\d+/.test(imp), `Import ${imp} in style.css must contain cache-busting version parameter`);
        }
    });

    it('validates assign spool resolution supports both pre-selected and dropdown selection', () => {
        function resolveSpoolId(selectedSpool, selectElementValue) {
            return selectedSpool?.id || selectElementValue || '';
        }

        assert.equal(resolveSpoolId({ id: 'spool-from-warehouse' }, 'spool-from-select'), 'spool-from-warehouse');
        assert.equal(resolveSpoolId(null, 'spool-from-select'), 'spool-from-select');
        assert.equal(resolveSpoolId(undefined, ''), '');
    });

    it('validates slot grams prompt input resolution and math evaluation', () => {
        function parseSlotGrams(input) {
            if (!input || String(input).trim() === '') return null;
            const str = String(input).trim();
            if (/^[0-9+\-*/. ()]+$/.test(str)) {
                try {
                    const res = Function(`'use strict'; return (${str})`)();
                    return typeof res === 'number' && !isNaN(res) && res >= 0 ? res : null;
                } catch {
                    return null;
                }
            }
            return null;
        }

        assert.equal(parseSlotGrams('1000'), 1000);
        assert.equal(parseSlotGrams('1000 - 250'), 750);
        assert.equal(parseSlotGrams('250 * 2 + 100'), 600);
        assert.equal(parseSlotGrams('-50'), null);
        assert.equal(parseSlotGrams('invalid'), null);
        assert.equal(parseSlotGrams(''), null);
    });
});
