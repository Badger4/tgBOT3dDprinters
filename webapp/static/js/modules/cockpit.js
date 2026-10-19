/**
 * 3D Farm Manager - Cockpit UI Card Renderer
 */

import { escapeHtml, formatCockpitHexColor } from "./utils.js";

export function renderCockpitCard(printer, onOpenModal) {
    const card = document.createElement("div");
    card.className = "glass-card printer-cockpit-card";
    card.dataset.printerId = printer.id;

    const isPrinting = printer.state === "RUNNING" || printer.state === "PRINTING";
    const statusBadgeClass = isPrinting ? "badge-success" : (printer.state === "OFFLINE" ? "badge-danger" : "badge-warning");
    const progress = Math.min(100, Math.max(0, printer.progress || 0));

    card.innerHTML = `
        <div class="card-header d-flex justify-content-between align-items-center">
            <div class="printer-identity">
                <span class="printer-name">${escapeHtml(printer.name)}</span>
                <span class="printer-model-badge">${escapeHtml(printer.model || "Bambu")}</span>
            </div>
            <span class="badge ${statusBadgeClass}">${escapeHtml(printer.status_text || printer.state)}</span>
        </div>
        <div class="card-body">
            <div class="cockpit-progress-wrap ${isPrinting ? '' : 'd-none'}">
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill" style="width: ${progress}%;"></div>
                </div>
                <div class="progress-labels d-flex justify-content-between">
                    <span>${progress}%</span>
                    <span>${escapeHtml(printer.time_remaining_str || "")}</span>
                </div>
            </div>
            <div class="cockpit-telemetry d-flex justify-content-around mt-2">
                <div class="telemetry-pill">
                    <i class="fa-solid fa-temperature-half text-danger"></i>
                    <span>${printer.nozzle_temp || 0}°C</span>
                </div>
                <div class="telemetry-pill">
                    <i class="fa-solid fa-bed text-warning"></i>
                    <span>${printer.bed_temp || 0}°C</span>
                </div>
            </div>
        </div>
    `;

    card.addEventListener("click", () => {
        if (onOpenModal) onOpenModal(printer.id);
    });

    return card;
}
