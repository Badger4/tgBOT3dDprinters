"""
Professional Landscape A4 PDF Report Generators for 3D Printer Farm.
Unified facade re-exporting modular reporting packages while maintaining 100% backward compatibility.
"""

from __future__ import annotations

import html
import io
import time
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# Re-export base utilities and canvas to maintain 100% backward compatibility
from services.reports.base import (
    NumberedCanvas,
    _format_slot_name,
    _resolve_printer_name,
    _setup_reportlab_fonts,
)

# Re-export inventory reports
from services.reports.inventory import (
    generate_combined_warehouse_pdf_report,
    generate_movements_pdf_report,
    generate_parts_pdf_report,
    generate_spools_pdf_report,
    generate_warehouse_pdf_report,
)

# Re-export commercial reports
from services.reports.commercial import (
    generate_commercial_calc_pdf,
    generate_commercial_pdf_report,
)


def generate_history_pdf_report(history: list[dict[str, Any]]) -> bytes:
    """Generates a professional Landscape A4 PDF report from 3D print history list."""
    font_reg, font_bold = _setup_reportlab_fonts()
    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=20,
        rightMargin=20,
        topMargin=25,
        bottomMargin=35,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "HistTitle",
        parent=styles["Heading1"],
        fontName=font_bold,
        fontSize=15,
        leading=18,
        textColor=colors.HexColor("#0f172a"),
    )
    subtitle_style = ParagraphStyle(
        "HistSubtitle",
        parent=styles["Heading2"],
        fontName=font_reg,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#64748b"),
    )
    header_cell_style = ParagraphStyle(
        "HistHeaderCell",
        parent=styles["Normal"],
        fontName=font_bold,
        fontSize=8,
        leading=10,
        textColor=colors.white,
    )
    cell_style = ParagraphStyle(
        "HistCell",
        parent=styles["Normal"],
        fontName=font_reg,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1e293b"),
    )
    bold_cell_style = ParagraphStyle(
        "HistBoldCell",
        parent=styles["Normal"],
        fontName=font_bold,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#0f172a"),
    )

    story: list[Any] = []

    scrap_jobs = sum(1 for item in history if item.get("is_scrap"))
    scrap_weight = sum(float(item.get("wasted_weight_g", item.get("weight_g", 0.0)) or 0.0) for item in history if item.get("is_scrap"))
    scrap_sub = f" | Брак: <b>{scrap_jobs} робіт ({scrap_weight:.1f} г)</b>" if scrap_jobs > 0 else ""

    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    story.append(Paragraph("📊 Звіт історії друку 3D Ферми", title_style))
    story.append(
        Paragraph(
            f"Згенеровано: <b>{now_str}</b> | Всього робіт: <b>{len(history)}</b>{scrap_sub}",
            subtitle_style,
        )
    )
    story.append(Spacer(1, 10))

    col_widths = [30, 105, 105, 255, 70, 75, 160]
    table_data = [
        [
            Paragraph("№", header_cell_style),
            Paragraph("Дата та час", header_cell_style),
            Paragraph("Принтер", header_cell_style),
            Paragraph("Назва моделі / Замовлення", header_cell_style),
            Paragraph("Тип нитки", header_cell_style),
            Paragraph("Витрата (г)", header_cell_style),
            Paragraph("Статус / Примітка", header_cell_style),
        ]
    ]

    total_weight = 0.0

    def _get_ts(x: dict[str, Any]) -> float:
        ts = x.get("timestamp", 0)
        if isinstance(ts, (int, float)):
            return float(ts)
        return 0.0

    sorted_history = sorted(history, key=_get_ts, reverse=True)
    for idx, item in enumerate(sorted_history, 1):
        ts = item.get("timestamp", time.time())
        if isinstance(ts, (int, float)):
            dt_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
        else:
            dt_str = str(ts)
        p_name = html.escape(str(item.get("printer_name", "Принтер")))
        subtask_raw = html.escape(str(item.get("subtask_name", "Модель")))
        client_order = str(item.get("client_order") or "").strip()
        if client_order:
            subtask_html = f"<b>{subtask_raw}</b><br/><font color='#0284c7'>👤 {html.escape(client_order)}</font>"
        else:
            subtask_html = subtask_raw

        filament = html.escape(str(item.get("filament_type", "PLA")))
        weight_g = float(item.get("weight_g", 0.0) or 0.0)
        total_weight += weight_g

        is_scrap = bool(item.get("is_scrap"))
        wasted_g = float(item.get("wasted_weight_g", weight_g) or weight_g)

        if is_scrap:
            reason = html.escape(str(item.get("scrap_reason", "Брак")))
            note_html = f"<font color='#dc2626'><b>❌ БРАК:</b> {reason}</font>"
            weight_html = f"{weight_g:.1f}<br/><font color='#dc2626' size='7'>Втрата: {wasted_g:.1f}г</font>"
        else:
            raw_note = str(item.get("note", "Завершено") or "Завершено").strip()
            if not raw_note or raw_note.lower() in ("успішно", "успішно виконано", "завершено", "success", "finish", "completed", "ok") or "успіш" in raw_note.lower() or "заверш" in raw_note.lower() or raw_note.startswith("?"):
                note_str = "Завершено"
            else:
                note_str = raw_note
            note_html = html.escape(note_str)
            weight_html = f"{weight_g:.1f}"

        table_data.append(
            [
                Paragraph(str(idx), cell_style),
                Paragraph(dt_str, cell_style),
                Paragraph(p_name, cell_style),
                Paragraph(subtask_html, cell_style),
                Paragraph(filament, cell_style),
                Paragraph(weight_html, bold_cell_style),
                Paragraph(note_html, cell_style),
            ]
        )

    summary_extra = f"<br/><font size='7'>Брак: {scrap_weight:.1f} г</font>" if scrap_jobs > 0 else ""
    table_data.append(
        [
            Paragraph("Всього", header_cell_style),
            Paragraph(f"{len(sorted_history)} робіт", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph(f"{total_weight:.1f} г ({total_weight/1000.0:.2f} кг){summary_extra}", header_cell_style),
            Paragraph(f"Брак: {scrap_jobs} шт" if scrap_jobs > 0 else "Без браку", header_cell_style),
        ]
    )

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e40af")),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#0f172a")),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f8fafc")]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(t)

    doc.build(story, canvasmaker=NumberedCanvas)
    return buf.getvalue()
