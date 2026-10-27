/**
 * Automated Unit Tests for WebApp Frontend Logic
 * Executable via Node.js native test runner: node --test tests/test_webapp_unit.test.js
 */

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

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
