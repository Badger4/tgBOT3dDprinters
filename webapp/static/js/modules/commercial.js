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
                            <i class="fa-solid fa-pen btn-edit-preset" data-id="${escapeHtml(String(p.id))}" title="Редагувати"></i>
                            <i class="fa-solid fa-trash btn-delete-preset text-danger" data-id="${escapeHtml(String(p.id))}" title="Видалити"></i>
                        </div>
                    `;
                    chip.addEventListener("click", (e) => {
                        if (!e.target.classList.contains("fa-pen") && !e.target.classList.contains("fa-trash") && !e.target.closest(".btn-edit-preset") && !e.target.closest(".btn-delete-preset")) {
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

/**
 * Pure helper to validate and normalize preset form inputs.
 * Ensures numbers are parsed, percentage strings are preserved, and defaults applied.
 */
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

export function openPresetModal(preset = null) {
    const modal = document.getElementById("preset-modal");
    if (!modal) return;
    state.editingPresetId = preset ? preset.id : null;
    const titleEl = document.getElementById("preset-modal-title");
    if (titleEl) {
        titleEl.textContent = preset ? "✏️ Редагувати пресет ціноутворення" : "➕ Створити пресет ціноутворення";
    }

    const nameEl = document.getElementById("preset-name");
    const filPriceEl = document.getElementById("preset-price-g") || document.getElementById("preset-filament-price");
    const elecEl = document.getElementById("preset-elec-rate");
    const powerEl = document.getElementById("preset-power");
    const deprEl = document.getElementById("preset-depreciation") || document.getElementById("preset-depr-val");
    const consEl = document.getElementById("preset-consumables") || document.getElementById("preset-cons-val");
    const profitEl = document.getElementById("preset-profit") || document.getElementById("preset-profit-val");

    if (nameEl) nameEl.value = preset?.name || "";
    if (filPriceEl) {
        filPriceEl.value = preset?.price_per_g !== undefined ? preset.price_per_g : 0.85;
    }
    if (elecEl) {
        elecEl.value = preset?.electricity_rate_uah !== undefined ? preset.electricity_rate_uah : 4.32;
    }
    if (powerEl) {
        powerEl.value = preset?.power_watts !== undefined ? preset.power_watts : 120;
    }
    if (deprEl) {
        deprEl.value = preset?.depreciation_val || "10";
    }
    if (consEl) {
        consEl.value = preset?.consumables_val || "5";
    }
    if (profitEl) {
        profitEl.value = preset?.profit_val || "100%";
    }

    triggerHaptic("light");
    modal.classList.add("active");
    if (nameEl) {
        setTimeout(() => nameEl.focus(), 50);
    }
}

export function closePresetModal() {
    const modal = document.getElementById("preset-modal");
    if (modal) modal.classList.remove("active");
    state.editingPresetId = null;
}

export async function submitSavePreset() {
    const saveBtn = document.getElementById("save-preset-submit");
    if (saveBtn && saveBtn.disabled) return;

    const nameInput = document.getElementById("preset-name");
    const name = (nameInput?.value || "").trim();
    if (!name) {
        alert("Введіть назву пресету!");
        if (nameInput) nameInput.focus();
        return;
    }

    const priceEl = document.getElementById("preset-price-g") || document.getElementById("preset-filament-price");
    const elecEl = document.getElementById("preset-elec-rate");
    const powerEl = document.getElementById("preset-power");
    const deprEl = document.getElementById("preset-depreciation") || document.getElementById("preset-depr-val");
    const consEl = document.getElementById("preset-consumables") || document.getElementById("preset-cons-val");
    const profitEl = document.getElementById("preset-profit") || document.getElementById("preset-profit-val");

    let payload;
    try {
        const normalized = normalizePresetInputs({
            name,
            rawPrice: priceEl?.value,
            elecRate: elecEl?.value,
            powerWatts: powerEl?.value,
            deprVal: deprEl?.value,
            consVal: consEl?.value,
            profitVal: profitEl?.value
        });
        payload = {
            id: state.editingPresetId || undefined,
            ...normalized
        };
    } catch (valErr) {
        alert(valErr.message || "Помилка валідації полів пресету");
        return;
    }

    let originalHtml = "";
    if (saveBtn) {
        originalHtml = saveBtn.innerHTML;
        saveBtn.disabled = true;
        saveBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Збереження...';
    }

    try {
        const res = await saveCommercialPresetApi(payload);
        if (!res || res.error || (res.status !== "ok" && !res.preset)) {
            throw new Error(res?.error || "Помилка збереження на сервері");
        }
        triggerHaptic("success");
        closePresetModal();
        await loadCommercialPresets();
    } catch (e) {
        console.error("Save preset error:", e);
        triggerHaptic("error");
        alert("Не вдалося зберегти пресет: " + (e.message || e));
    } finally {
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.innerHTML = originalHtml;
        }
    }
}

export async function deletePreset(presetId) {
    if (!presetId) return;
    const p = state.presets ? state.presets[presetId] : null;
    const pName = p ? ` "${p.name}"` : "";
    if (!confirm(`Видалити цей пресет ціноутворення${pName}?`)) return;

    try {
        triggerHaptic("medium");
        const res = await deleteCommercialPresetApi(presetId);
        if (res && res.error) {
            throw new Error(res.error);
        }
        await loadCommercialPresets();
        triggerHaptic("success");
    } catch (e) {
        console.error("Delete preset error:", e);
        triggerHaptic("error");
        alert("Помилка видалення пресету: " + (e.message || e));
    }
}

export async function exportCommercialPdf() {
    const exportBtn = document.getElementById("btn-export-calc-pdf");
    if (exportBtn && exportBtn.disabled) return;

    let originalHtml = "";
    if (exportBtn) {
        originalHtml = exportBtn.innerHTML;
        exportBtn.disabled = true;
        exportBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Створення PDF...';
    }

    try {
        triggerHaptic("light");
        const weight_g = parseFloat(document.getElementById("calc-weight-g")?.value) || 100;
        const time_mins = parseInt(document.getElementById("calc-time-mins")?.value) || 60;
        const preset_id = document.getElementById("calc-preset-select")?.value;
        const client_order = (document.getElementById("calc-client-order")?.value || "").trim();
        const electricity_rate_uah = parseFloat(document.getElementById("calc-elec-rate")?.value) || 4.32;
        const power_watts = parseFloat(document.getElementById("calc-power-watts")?.value) || 120;

        const preset = (state.presets && preset_id) ? state.presets[preset_id] : null;
        const presetName = preset?.name || (document.getElementById("calc-preset-select")?.selectedOptions?.[0]?.text) || "Стандартний";

        const totalPrice = document.getElementById("res-total-price")?.textContent || "0.00 ₴";
        const filamentCost = document.getElementById("res-filament-cost")?.textContent || "0.00 ₴";
        const elecCost = document.getElementById("res-elec-cost")?.textContent || "0.00 ₴";
        const deprCost = document.getElementById("res-depr-cost")?.textContent || "0.00 ₴";
        const consCost = document.getElementById("res-cons-cost")?.textContent || "0.00 ₴";
        const directCost = document.getElementById("res-direct-cost")?.textContent || "0.00 ₴";
        const profitCost = document.getElementById("res-profit-cost")?.textContent || "0.00 ₴";

        const hours = Math.floor(time_mins / 60);
        const mins = time_mins % 60;
        const timeFormatted = hours > 0 ? `${hours} год ${mins} хв (${time_mins} хв)` : `${time_mins} хв`;
        const now = new Date();
        const dateFormatted = now.toLocaleString("uk-UA", { dateStyle: "medium", timeStyle: "short" });

        // 1. Prefer client-side html2pdf export if library is available
        if (typeof window.html2pdf === "function") {
            const reportEl = document.createElement("div");
            reportEl.id = "commercial-pdf-report-container";
            reportEl.style.cssText = `
                width: 700px;
                padding: 32px;
                background: #ffffff;
                color: #1a1a1a;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                font-size: 14px;
                line-height: 1.5;
                box-sizing: border-box;
            `;

            reportEl.innerHTML = `
                <div style="border-bottom: 2px solid #2563eb; padding-bottom: 16px; margin-bottom: 24px; display: flex; justify-content: space-between; align-items: flex-start;">
                    <div>
                        <h1 style="margin: 0 0 6px 0; font-size: 24px; color: #1e3a8a; font-weight: 700;">КОМЕРЦІЙНА ПРОПОЗИЦІЯ</h1>
                        <div style="font-size: 13px; color: #4b5563;">3D Farm Manager • Розрахунок вартості послуг 3D-друку</div>
                    </div>
                    <div style="text-align: right; font-size: 12px; color: #6b7280;">
                        <div><strong>Дата:</strong> ${escapeHtml(dateFormatted)}</div>
                        ${client_order ? `<div style="margin-top: 4px; font-size: 13px; color: #1f2937;"><strong>Замовлення:</strong> ${escapeHtml(client_order)}</div>` : ""}
                    </div>
                </div>

                <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 18px; margin-bottom: 24px;">
                    <div style="font-size: 14px; font-weight: 600; color: #334155; margin-bottom: 10px;">Параметри виготовлення</div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 13px;">
                        <div><span style="color: #64748b;">Пресет ціноутворення:</span> <strong>${escapeHtml(presetName)}</strong></div>
                        <div><span style="color: #64748b;">Вага моделі (пластик):</span> <strong>${weight_g} г</strong></div>
                        <div><span style="color: #64748b;">Час друку:</span> <strong>${escapeHtml(timeFormatted)}</strong></div>
                        <div><span style="color: #64748b;">Тариф електроенергії:</span> <strong>${electricity_rate_uah} грн/кВт·год</strong></div>
                    </div>
                </div>

                <table style="width: 100%; border-collapse: collapse; margin-bottom: 24px; font-size: 13px;">
                    <thead>
                        <tr style="background: #f1f5f9; border-bottom: 2px solid #cbd5e1; text-align: left;">
                            <th style="padding: 10px 12px; font-weight: 600; color: #334155;">Стаття витрат</th>
                            <th style="padding: 10px 12px; text-align: right; font-weight: 600; color: #334155;">Вартість</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr style="border-bottom: 1px solid #e2e8f0;">
                            <td style="padding: 10px 12px; color: #334155;">Основний матеріал (філамент)</td>
                            <td style="padding: 10px 12px; text-align: right; font-weight: 500;">${escapeHtml(filamentCost)}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #e2e8f0;">
                            <td style="padding: 10px 12px; color: #334155;">Електроенергія (${power_watts} Вт)</td>
                            <td style="padding: 10px 12px; text-align: right; font-weight: 500;">${escapeHtml(elecCost)}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #e2e8f0;">
                            <td style="padding: 10px 12px; color: #334155;">Амортизація обладнання</td>
                            <td style="padding: 10px 12px; text-align: right; font-weight: 500;">${escapeHtml(deprCost)}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #e2e8f0;">
                            <td style="padding: 10px 12px; color: #334155;">Витратні матеріали (сопла, адгезиви, ТО)</td>
                            <td style="padding: 10px 12px; text-align: right; font-weight: 500;">${escapeHtml(consCost)}</td>
                        </tr>
                        <tr style="border-bottom: 1px solid #94a3b8; background: #f8fafc;">
                            <td style="padding: 10px 12px; font-weight: 600; color: #1e293b;">Собівартість виробництва (прямі витрати)</td>
                            <td style="padding: 10px 12px; text-align: right; font-weight: 600; color: #1e293b;">${escapeHtml(directCost)}</td>
                        </tr>
                        <tr style="border-bottom: 2px solid #cbd5e1; background: #f8fafc;">
                            <td style="padding: 10px 12px; font-weight: 600; color: #166534;">Прибуток / Робота майстерні (маржа)</td>
                            <td style="padding: 10px 12px; text-align: right; font-weight: 600; color: #166534;">${escapeHtml(profitCost)}</td>
                        </tr>
                    </tbody>
                </table>

                <div style="background: #eff6ff; border: 2px solid #bfdbfe; border-radius: 8px; padding: 16px 20px; display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <div style="font-size: 13px; color: #1e40af; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">Разом до сплати</div>
                        <div style="font-size: 12px; color: #60a5fa;">Всі витрати та матеріали враховано</div>
                    </div>
                    <div style="font-size: 26px; font-weight: 800; color: #1d4ed8;">${escapeHtml(totalPrice)}</div>
                </div>

                <div style="margin-top: 36px; padding-top: 16px; border-top: 1px solid #e2e8f0; display: flex; justify-content: space-between; font-size: 11px; color: #94a3b8;">
                    <div>Документ сформовано автоматично сервісом 3D Farm Manager</div>
                    <div>Дякуємо за співпрацю!</div>
                </div>
            `;

            reportEl.style.position = "fixed";
            reportEl.style.left = "-9999px";
            reportEl.style.top = "0";
            document.body.appendChild(reportEl);

            try {
                const opt = {
                    margin: [10, 10, 10, 10],
                    filename: `commercial_quote_${Date.now()}.pdf`,
                    image: { type: "jpeg", quality: 0.98 },
                    html2canvas: { scale: 2, useCORS: true, logging: false },
                    jsPDF: { unit: "mm", format: "a4", orientation: "portrait" }
                };

                await window.html2pdf().set(opt).from(reportEl).save();
                triggerHaptic("success");
                return;
            } finally {
                if (reportEl.parentNode) {
                    reportEl.parentNode.removeChild(reportEl);
                }
            }
        }

        // 2. Fallback to backend ReportLab PDF generation if html2pdf is unavailable
        const params = new URLSearchParams({
            weight_g: String(weight_g),
            time_mins: String(time_mins),
            electricity_rate_uah: String(electricity_rate_uah),
            power_watts: String(power_watts),
            format: "pdf"
        });
        if (preset_id) params.set("preset_id", preset_id);
        if (client_order) params.set("client_order", client_order);

        const res = await fetch(`/api/commercial/export_pdf?${params.toString()}`);
        if (!res.ok) {
            throw new Error(`Помилка генерації PDF сервером: ${res.statusText}`);
        }
        const blob = await res.blob();
        const blobUrl = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = blobUrl;
        a.download = `commercial_quote_${Date.now()}.pdf`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(blobUrl);
        triggerHaptic("success");
    } catch (err) {
        console.error("Commercial PDF export failed:", err);
        triggerHaptic("error");
        alert("Не вдалося сформувати звіт PDF: " + (err.message || err));
    } finally {
        if (exportBtn) {
            exportBtn.disabled = false;
            exportBtn.innerHTML = originalHtml;
        }
    }
}

export function initCommercialEventListeners() {
    if (state.commercialModuleBound) return;
    state.commercialModuleBound = true;

    document.getElementById("calc-preset-select")?.addEventListener("change", (e) => {
        syncPresetToInputs(e.target.value);
        recalculateCommercial();
    });
    document.getElementById("calc-weight-g")?.addEventListener("input", recalculateCommercial);
    document.getElementById("calc-time-mins")?.addEventListener("input", recalculateCommercial);
    document.getElementById("calc-elec-rate")?.addEventListener("input", recalculateCommercial);
    document.getElementById("calc-power-watts")?.addEventListener("input", recalculateCommercial);
    document.getElementById("calc-client-order")?.addEventListener("input", recalculateCommercial);

    document.getElementById("btn-export-calc-pdf")?.addEventListener("click", exportCommercialPdf);

    document.getElementById("add-preset-btn")?.addEventListener("click", () => openPresetModal());
    document.getElementById("save-preset-submit")?.addEventListener("click", submitSavePreset);
    document.getElementById("cancel-preset-submit")?.addEventListener("click", closePresetModal);
    document.getElementById("close-preset-modal")?.addEventListener("click", closePresetModal);
}

export const initCommercialCalculator = initCommercialEventListeners;
