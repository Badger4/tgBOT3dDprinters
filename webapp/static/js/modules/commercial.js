/**
 * 3D Farm Manager - Commercial Pricing Calculator & Preset Management
 */

import { escapeHtml, triggerHaptic } from "./utils.js";
import { state } from "./state.js";
import {
    fetchCommercialPresetsApi,
    saveCommercialPresetApi,
    deleteCommercialPresetApi,
    calculateCommercialApi
} from "./api.js";

export function parseValOrPercent(valStr, baseAmount, hours = 1.0) {
    const s = String(valStr || "").trim();
    if (s.endsWith("%")) {
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
    const deprStr = String(options.depreciation_val ?? preset.depreciation_val ?? "10");

    let deprCost = 0;
    if (printerCost > 0 && printerLife > 0) {
        deprCost = Math.round((printerCost / printerLife) * hours * 100) / 100;
    } else {
        [deprCost] = parseValOrPercent(deprStr, directCost, hours);
    }

    const consStr = String(options.consumables_val ?? preset.consumables_val ?? "5");
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

    let profitStr = String(options.profit_val ?? preset.profit_val ?? "100%");
    if (options.margin_pct !== undefined && options.margin_pct !== null) {
        profitStr = options.margin_pct + "%";
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

export async function loadCommercialPresets() {
    try {
        const presets = await fetchCommercialPresetsApi();
        state.presets = presets || {};

        const presetSelect = document.getElementById("calc-preset-select");
        if (presetSelect) {
            presetSelect.innerHTML = '<option value="">⚙️ Стандартний розрахунок</option>';
            Object.values(state.presets).forEach(p => {
                const opt = document.createElement("option");
                opt.value = p.id;
                opt.textContent = p.name;
                presetSelect.appendChild(opt);
            });
        }

        const presetsContainer = document.getElementById("presets-list");
        if (presetsContainer) {
            presetsContainer.innerHTML = "";
            const presetValues = Object.values(state.presets);
            if (presetValues.length === 0) {
                presetsContainer.innerHTML = '<p class="text-muted" style="font-size: 13px;">Немає збережених пресетів.</p>';
            } else {
                presetValues.forEach(p => {
                    const chip = document.createElement("div");
                    chip.className = "preset-chip";
                    chip.innerHTML = `
                        <span>${escapeHtml(p.name)}</span>
                        <div class="d-flex gap-2">
                            <i class="fa-solid fa-pen btn-edit-preset" data-id="${p.id}" title="Редагувати"></i>
                            <i class="fa-solid fa-trash btn-delete-preset text-danger" data-id="${p.id}" title="Видалити"></i>
                        </div>
                    `;
                    chip.addEventListener("click", (e) => {
                        if (!e.target.classList.contains("fa-pen") && !e.target.classList.contains("fa-trash")) {
                            if (presetSelect) {
                                presetSelect.value = p.id;
                                syncPresetToInputs(p.id);
                                recalculateCommercial();
                            }
                        }
                    });
                    presetsContainer.appendChild(chip);
                });
            }
        }
        await recalculateCommercial();
    } catch (e) {
        console.error("Failed loading commercial presets:", e);
    }
}

export function syncPresetToInputs(presetId) {
    if (!presetId || !state.presets[presetId]) return;
    const p = state.presets[presetId];
    const elecEl = document.getElementById("calc-elec-rate");
    const powerEl = document.getElementById("calc-power-watts");
    if (elecEl && p.electricity_rate_uah !== undefined) elecEl.value = p.electricity_rate_uah;
    if (powerEl && p.power_watts !== undefined) powerEl.value = p.power_watts;
}

export async function recalculateCommercial() {
    const weight_g = parseFloat(document.getElementById("calc-weight-g")?.value) || 100;
    const time_mins = parseInt(document.getElementById("calc-time-mins")?.value) || 60;
    const preset_id = document.getElementById("calc-preset-select")?.value;
    const client_order = (document.getElementById("calc-client-order")?.value || "").trim();
    const electricity_rate_uah = parseFloat(document.getElementById("calc-elec-rate")?.value) || 4.32;
    const power_watts = parseFloat(document.getElementById("calc-power-watts")?.value) || 120;

    try {
        const data = await calculateCommercialApi({
            weight_g, time_mins, preset_id, client_order, electricity_rate_uah, power_watts
        });
        if (data.status === "ok" && data.calculation) {
            const c = data.calculation;
            const totalEl = document.getElementById("res-total-price");
            if (totalEl) totalEl.textContent = `${c.total_price.toFixed(2)} ₴`;
            const filEl = document.getElementById("res-filament-cost");
            if (filEl) filEl.textContent = `${c.filament_cost.toFixed(2)} ₴`;
            const elecEl = document.getElementById("res-elec-cost");
            if (elecEl) elecEl.textContent = `${c.electricity_cost.toFixed(2)} ₴`;
            const deprEl = document.getElementById("res-depr-cost");
            if (deprEl) deprEl.textContent = `${c.depreciation_cost.toFixed(2)} ₴ (${c.depreciation_str || ""})`;
            const consEl = document.getElementById("res-cons-cost");
            if (consEl) consEl.textContent = `${c.consumables_cost.toFixed(2)} ₴ (${c.consumables_str || ""})`;
            const dirEl = document.getElementById("res-direct-cost");
            if (dirEl) dirEl.textContent = `${c.direct_cost.toFixed(2)} ₴`;
            const profEl = document.getElementById("res-profit-cost");
            if (profEl) profEl.textContent = `${c.profit_cost.toFixed(2)} ₴ (${c.profit_str || ""})`;

            // Mobile floating bar update
            const mobVal = document.querySelector(".calc-mob-val");
            if (mobVal) mobVal.textContent = `${c.total_price.toFixed(2)} ₴`;
        }
    } catch (e) {
        console.error("Failed calculating commercial price:", e);
    }
}

export function openPresetModal(preset = null) {
    const modal = document.getElementById("preset-modal");
    if (!modal) return;
    state.editingPresetId = preset ? preset.id : null;
    const titleEl = document.getElementById("preset-modal-title");
    if (titleEl) titleEl.textContent = preset ? "✏️ Редагувати пресет" : "➕ Новий пресет";

    const nameEl = document.getElementById("preset-name");
    const filPriceEl = document.getElementById("preset-filament-price");
    const deprEl = document.getElementById("preset-depr-val");
    const consEl = document.getElementById("preset-cons-val");
    const profitEl = document.getElementById("preset-profit-val");

    if (nameEl) nameEl.value = preset?.name || "";
    if (filPriceEl) filPriceEl.value = preset?.price_per_g ? Math.round(preset.price_per_g * 1000) : 850;
    if (deprEl) deprEl.value = preset?.depreciation_val || "10%";
    if (consEl) consEl.value = preset?.consumables_val || "5%";
    if (profitEl) profitEl.value = preset?.profit_val || "100%";

    triggerHaptic("light");
    modal.classList.add("active");
}

export function closePresetModal() {
    const modal = document.getElementById("preset-modal");
    if (modal) modal.classList.remove("active");
    state.editingPresetId = null;
}

export async function submitSavePreset() {
    const name = document.getElementById("preset-name")?.value.trim();
    if (!name) {
        alert("Введіть назву пресету!");
        return;
    }
    const filKg = parseFloat(document.getElementById("preset-filament-price")?.value) || 850;
    const payload = {
        id: state.editingPresetId || undefined,
        name,
        price_per_g: Math.round((filKg / 1000) * 100) / 100,
        depreciation_val: document.getElementById("preset-depr-val")?.value.trim() || "10%",
        consumables_val: document.getElementById("preset-cons-val")?.value.trim() || "5%",
        profit_val: document.getElementById("preset-profit-val")?.value.trim() || "100%"
    };
    try {
        await saveCommercialPresetApi(payload);
        closePresetModal();
        await loadCommercialPresets();
    } catch (e) {
        console.error("Save preset error:", e);
        alert("Не вдалося зберегти пресет.");
    }
}

export async function deletePreset(presetId) {
    if (!presetId) return;
    if (confirm("Видалити цей пресет?")) {
        try {
            await deleteCommercialPresetApi(presetId);
            await loadCommercialPresets();
        } catch (e) {
            console.error("Delete preset error:", e);
        }
    }
}

export function initCommercialEventListeners() {
    document.getElementById("calc-preset-select")?.addEventListener("change", (e) => {
        syncPresetToInputs(e.target.value);
        recalculateCommercial();
    });
    document.getElementById("calc-weight-g")?.addEventListener("input", recalculateCommercial);
    document.getElementById("calc-time-mins")?.addEventListener("input", recalculateCommercial);
    document.getElementById("calc-elec-rate")?.addEventListener("input", recalculateCommercial);
    document.getElementById("calc-power-watts")?.addEventListener("input", recalculateCommercial);
    document.getElementById("calc-client-order")?.addEventListener("input", recalculateCommercial);

    document.getElementById("add-preset-btn")?.addEventListener("click", () => openPresetModal());
    document.getElementById("save-preset-submit")?.addEventListener("click", submitSavePreset);
    document.getElementById("cancel-preset-submit")?.addEventListener("click", closePresetModal);
    document.getElementById("close-preset-modal")?.addEventListener("click", closePresetModal);
}

export const initCommercialCalculator = initCommercialEventListeners;
