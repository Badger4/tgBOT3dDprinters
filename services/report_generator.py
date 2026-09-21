"""
Service for generating professional PDF exports and reports for farm print history and warehouses.
"""

import html
import io
import os
import time
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_FONTS_INITIALIZED = False
_FONT_REGULAR = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"


def _setup_reportlab_fonts() -> tuple[str, str]:
    """Registers TrueType font supporting Cyrillic/Ukrainian characters if available."""
    global _FONTS_INITIALIZED, _FONT_REGULAR, _FONT_BOLD
    if _FONTS_INITIALIZED:
        return _FONT_REGULAR, _FONT_BOLD

    candidates = [
        # Linux / Raspberry Pi standard system paths
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ),
        (
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ),
        (
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        ),
        # Windows system paths
        ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
        ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
    ]

    for reg_path, bold_path in candidates:
        if os.path.exists(reg_path):
            try:
                pdfmetrics.registerFont(TTFont("ReportCyrillic", reg_path))
                _FONT_REGULAR = "ReportCyrillic"
                if os.path.exists(bold_path):
                    pdfmetrics.registerFont(TTFont("ReportCyrillicBold", bold_path))
                    _FONT_BOLD = "ReportCyrillicBold"
                else:
                    _FONT_BOLD = "ReportCyrillic"
                break
            except Exception:
                pass

    _FONTS_INITIALIZED = True
    return _FONT_REGULAR, _FONT_BOLD


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to dynamically calculate total pages and render uniform footers."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_decorations(self, page_count: int) -> None:
        self.saveState()
        font_reg, _ = _setup_reportlab_fonts()
        self.setFont(font_reg, 8)
        self.setFillColor(colors.HexColor("#64748b"))

        # Footer divider line
        w, _ = self._pagesize
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(20, 25, w - 20, 25)

        # Footer text
        self.drawString(20, 14, "3D Farm Bot Management System • Автоматичний звіт")
        page_str = f"Сторінка {self._pageNumber} з {page_count}"
        self.drawRightString(w - 20, 14, page_str)
        self.restoreState()


# =========================================================================
# Professional Landscape A4 PDF Report Generators
# =========================================================================


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
        fontName=font_reg,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#64748b"),
    )
    header_cell_style = ParagraphStyle(
        "HistHeaderCell",
        fontName=font_bold,
        fontSize=8,
        leading=10,
        textColor=colors.white,
    )
    cell_style = ParagraphStyle(
        "HistCell",
        fontName=font_reg,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1e293b"),
    )
    bold_cell_style = ParagraphStyle(
        "HistBoldCell",
        fontName=font_bold,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#0f172a"),
    )

    story: list[Any] = []

    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    story.append(Paragraph("📊 Звіт історії друку 3D Ферми", title_style))
    story.append(
        Paragraph(
            f"Згенеровано: <b>{now_str}</b> | Всього записів: <b>{len(history)}</b>",
            subtitle_style,
        )
    )
    story.append(Spacer(1, 10))

    col_widths = [30, 110, 110, 245, 75, 75, 155]
    table_data = [
        [
            Paragraph("№", header_cell_style),
            Paragraph("Дата та час", header_cell_style),
            Paragraph("Принтер", header_cell_style),
            Paragraph("Назва моделі / 3MF", header_cell_style),
            Paragraph("Тип пластику", header_cell_style),
            Paragraph("Витрата (г)", header_cell_style),
            Paragraph("Примітка", header_cell_style),
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
        subtask = html.escape(str(item.get("subtask_name", "Модель")))
        filament = html.escape(str(item.get("filament_type", "PLA")))
        weight_g = float(item.get("weight_g", 0.0) or 0.0)
        total_weight += weight_g
        raw_note = str(item.get("note", "Завершено") or "Завершено").strip()
        if not raw_note or raw_note.lower() in ("успішно", "успішно виконано", "завершено", "success", "finish", "completed", "ok") or "успіш" in raw_note.lower() or "заверш" in raw_note.lower() or raw_note.startswith("?"):
            note_str = "Завершено"
        else:
            note_str = raw_note
        note = html.escape(note_str)

        table_data.append(
            [
                Paragraph(str(idx), cell_style),
                Paragraph(dt_str, cell_style),
                Paragraph(p_name, cell_style),
                Paragraph(subtask, cell_style),
                Paragraph(filament, cell_style),
                Paragraph(f"{weight_g:.1f}", bold_cell_style),
                Paragraph(note, cell_style),
            ]
        )

    # Summary Row
    table_data.append(
        [
            Paragraph("Всього", header_cell_style),
            Paragraph(f"{len(sorted_history)} робіт", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph(f"{total_weight:.1f} г ({total_weight/1000.0:.2f} кг)", header_cell_style),
            Paragraph("-", header_cell_style),
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


def _resolve_printer_name(printer_id: str | None, printers: Any = None) -> str:
    """Resolves human-readable printer name from id and optional printers collection."""
    if not printer_id:
        return "Невідомий принтер"
    p_id_str = str(printer_id).strip()
    if printers:
        if isinstance(printers, dict):
            p = printers.get(p_id_str)
            if p:
                if isinstance(p, dict):
                    return str(p.get("name") or p_id_str)
                return str(getattr(p, "name", None) or p_id_str)
            for item in printers.values():
                pid = item.get("id") if isinstance(item, dict) else getattr(item, "id", None)
                if pid and str(pid).strip() == p_id_str:
                    if isinstance(item, dict):
                        return str(item.get("name") or p_id_str)
                    return str(getattr(item, "name", None) or p_id_str)
        elif isinstance(printers, (list, tuple)):
            for item in printers:
                pid = item.get("id") if isinstance(item, dict) else getattr(item, "id", None)
                if pid and str(pid).strip() == p_id_str:
                    if isinstance(item, dict):
                        return str(item.get("name") or p_id_str)
                    return str(getattr(item, "name", None) or p_id_str)
    try:
        from pathlib import Path
        import json
        for cand in [Path("printers_storage/printers.json"), Path("printers.json")]:
            if cand.exists():
                with open(cand, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and str(item.get("id")).strip() == p_id_str:
                                return str(item.get("name") or p_id_str)
                    elif isinstance(data, dict):
                        item = data.get(p_id_str)
                        if isinstance(item, dict):
                            return str(item.get("name") or p_id_str)
    except Exception:
        pass
    return f"Принтер {p_id_str}"


def _format_slot_name(slot_key: Any) -> str:
    """Formats slot key into human-friendly Ukrainian slot description."""
    if slot_key is None:
        return "Невідомий слот"
    slot_str = str(slot_key).strip()
    slot_map = {
        "0": "Слот A1 (AMS)",
        "1": "Слот A2 (AMS)",
        "2": "Слот A3 (AMS)",
        "3": "Слот A4 (AMS)",
        "254": "Слот VT (Зовнішній)",
        "255": "Слот VT (Зовнішній)",
    }
    if slot_str in slot_map:
        return slot_map[slot_str]
    return f"Слот {slot_str}"


def generate_spools_pdf_report(
    spools: dict[str, Any],
    printers: dict[str, Any] | None = None,
) -> bytes:
    """Generates Landscape A4 PDF export for Filament Spools warehouse and active printers."""
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
        "SpoolTitle",
        parent=styles["Heading1"],
        fontName=font_bold,
        fontSize=15,
        leading=18,
        textColor=colors.HexColor("#0f172a"),
    )
    section_style = ParagraphStyle(
        "SpoolSectionTitle",
        parent=styles["Heading2"],
        fontName=font_bold,
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#0f172a"),
    )
    subtitle_style = ParagraphStyle(
        "SpoolSubtitle",
        fontName=font_reg,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#64748b"),
    )
    header_cell_style = ParagraphStyle(
        "SpoolHeaderCell",
        fontName=font_bold,
        fontSize=8,
        leading=10,
        textColor=colors.white,
    )
    cell_style = ParagraphStyle(
        "SpoolCell",
        fontName=font_reg,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1e293b"),
    )
    bold_cell_style = ParagraphStyle(
        "SpoolBoldCell",
        fontName=font_bold,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#0f172a"),
    )

    story: list[Any] = []
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    total_registered_qty = sum(max(1, int(s.get("quantity", 1) or 1)) for s in spools.values() if isinstance(s, dict)) if spools else 0
    total_pos = len(spools) if spools else 0
    reg_summary = f"{total_registered_qty} шт. ({total_pos} поз.)" if total_registered_qty != total_pos else f"{total_registered_qty} шт."

    story.append(Paragraph("🧵 Інвентаризаційний звіт пластику 3D ферми", title_style))
    story.append(
        Paragraph(
            f"Згенеровано: <b>{now_str}</b> | Загальна кількість зареєстрованих котушок: <b>{reg_summary}</b>",
            subtitle_style,
        )
    )
    story.append(Spacer(1, 10))

    # Separate warehouse stock vs active mounted spools
    warehouse_spools: list[tuple[str, dict[str, Any]]] = []
    mounted_spools: list[tuple[str, dict[str, Any]]] = []

    if spools and isinstance(spools, dict):
        for s_id, s in spools.items():
            if isinstance(s, dict):
                if s.get("assigned_printer_id") or s.get("assigned_slot_key"):
                    mounted_spools.append((s_id, s))
                else:
                    warehouse_spools.append((s_id, s))

    # ==========================================
    # SECTION 1: 📦 На складі (вільні залишки)
    # ==========================================
    wh_total_qty_pre = sum(max(1, int(s.get("quantity", 1) or 1)) for _, s in warehouse_spools)
    wh_summary_pre = f"<b>{wh_total_qty_pre}</b> шт. ({len(warehouse_spools)} поз.)" if wh_total_qty_pre != len(warehouse_spools) else f"<b>{len(warehouse_spools)}</b> поз."
    story.append(Paragraph("📦 1. Залишки на складі (вільні котушки)", section_style))
    story.append(
        Paragraph(
            f"Котушки на полицях складу (готові до використання): {wh_summary_pre}",
            subtitle_style,
        )
    )
    story.append(Spacer(1, 4))

    wh_widths = [45, 155, 60, 60, 65, 65, 75, 45, 110, 120]
    wh_table_data = [
        [
            Paragraph("ID", header_cell_style),
            Paragraph("Назва котушки", header_cell_style),
            Paragraph("Тип", header_cell_style),
            Paragraph("Колір", header_cell_style),
            Paragraph("Поч. вага", header_cell_style),
            Paragraph("Залишок", header_cell_style),
            Paragraph("Ціна (грн/кг)", header_cell_style),
            Paragraph("К-сть", header_cell_style),
            Paragraph("Розташування", header_cell_style),
            Paragraph("Сума (грн)", header_cell_style),
        ]
    ]

    wh_initial_g = 0.0
    wh_remaining_g = 0.0
    wh_value_uah = 0.0
    wh_qty = 0

    if warehouse_spools:
        for s_id, s in warehouse_spools:
            spool_id = html.escape(str(s.get("id", s_id)))
            name = html.escape(str(s.get("name", "Котушка")))
            fil_type = html.escape(str(s.get("type", "PLA")))
            color = html.escape(str(s.get("color") or "-"))
            initial_g = float(s.get("initial_grams") or s.get("total_grams") or 1000.0)
            remaining_g = float(s.get("remaining_grams") or 1000.0)
            price_per_kg = float(s.get("price_per_kg") or 650.0)
            qty = max(1, int(s.get("quantity", 1)))
            val_uah = (remaining_g / 1000.0) * price_per_kg * qty

            wh_initial_g += initial_g * qty
            wh_remaining_g += remaining_g * qty
            wh_value_uah += val_uah
            wh_qty += qty

            wh_table_data.append(
                [
                    Paragraph(spool_id, cell_style),
                    Paragraph(name, cell_style),
                    Paragraph(fil_type, cell_style),
                    Paragraph(color, cell_style),
                    Paragraph(f"{initial_g:.1f} г", cell_style),
                    Paragraph(f"{remaining_g:.1f} г", bold_cell_style),
                    Paragraph(f"{price_per_kg:.2f}", cell_style),
                    Paragraph(str(qty), cell_style),
                    Paragraph("На складі", cell_style),
                    Paragraph(f"{val_uah:.2f} грн", bold_cell_style),
                ]
            )
    else:
        wh_table_data.append(
            [
                Paragraph("-", cell_style),
                Paragraph("<i>Вільних котушок на складі немає</i>", cell_style),
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
                Paragraph("0", cell_style),
                Paragraph("-", cell_style),
                Paragraph("0.00 грн", cell_style),
            ]
        )

    # Subtotal Section 1
    wh_table_data.append(
        [
            Paragraph("Разом на складі", header_cell_style),
            Paragraph(f"{len(warehouse_spools)} позицій", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph(f"{wh_initial_g/1000.0:.2f} кг", header_cell_style),
            Paragraph(f"{wh_remaining_g/1000.0:.2f} кг", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph(f"{wh_qty} шт", header_cell_style),
            Paragraph("Сума на складі:", header_cell_style),
            Paragraph(f"{wh_value_uah:.2f} грн", header_cell_style),
        ]
    )

    t_wh = Table(wh_table_data, colWidths=wh_widths, repeatRows=1)
    t_wh.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0284c7")),
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
    story.append(t_wh)
    story.append(Spacer(1, 14))

    # ==========================================
    # SECTION 2: 🖨️ Встановлені на принтерах (у роботі)
    # ==========================================
    story.append(Paragraph("🖨️ 2. Встановлені на принтерах (у роботі)", section_style))
    story.append(
        Paragraph(
            f"Котушки в слотах AMS або на зовнішніх тримачах: <b>{len(mounted_spools)}</b> поз.",
            subtitle_style,
        )
    )
    story.append(Spacer(1, 4))

    mounted_widths = [45, 145, 55, 55, 60, 65, 65, 115, 90, 105]
    mounted_table_data = [
        [
            Paragraph("ID", header_cell_style),
            Paragraph("Назва котушки", header_cell_style),
            Paragraph("Тип", header_cell_style),
            Paragraph("Колір", header_cell_style),
            Paragraph("Поч. вага", header_cell_style),
            Paragraph("Залишок", header_cell_style),
            Paragraph("Ціна (грн/кг)", header_cell_style),
            Paragraph("Принтер", header_cell_style),
            Paragraph("Слот", header_cell_style),
            Paragraph("Сума (грн)", header_cell_style),
        ]
    ]

    m_initial_g = 0.0
    m_remaining_g = 0.0
    m_value_uah = 0.0
    m_qty = 0

    if mounted_spools:
        for s_id, s in mounted_spools:
            spool_id = html.escape(str(s.get("id", s_id)))
            name = html.escape(str(s.get("name", "Котушка")))
            fil_type = html.escape(str(s.get("type", "PLA")))
            color = html.escape(str(s.get("color") or "-"))
            initial_g = float(s.get("initial_grams") or s.get("total_grams") or 1000.0)
            remaining_g = float(s.get("remaining_grams") or 1000.0)
            price_per_kg = float(s.get("price_per_kg") or 650.0)
            qty = max(1, int(s.get("quantity", 1)))
            val_uah = (remaining_g / 1000.0) * price_per_kg * qty

            p_id = s.get("assigned_printer_id")
            printer_name = html.escape(_resolve_printer_name(p_id, printers))
            slot_name = html.escape(_format_slot_name(s.get("assigned_slot_key")))

            m_initial_g += initial_g * qty
            m_remaining_g += remaining_g * qty
            m_value_uah += val_uah
            m_qty += qty

            mounted_table_data.append(
                [
                    Paragraph(spool_id, cell_style),
                    Paragraph(name, cell_style),
                    Paragraph(fil_type, cell_style),
                    Paragraph(color, cell_style),
                    Paragraph(f"{initial_g:.1f} г", cell_style),
                    Paragraph(f"{remaining_g:.1f} г", bold_cell_style),
                    Paragraph(f"{price_per_kg:.2f}", cell_style),
                    Paragraph(printer_name, cell_style),
                    Paragraph(slot_name, cell_style),
                    Paragraph(f"{val_uah:.2f} грн", bold_cell_style),
                ]
            )
    else:
        mounted_table_data.append(
            [
                Paragraph("-", cell_style),
                Paragraph("<i>Встановлених на принтерах котушок немає</i>", cell_style),
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
                Paragraph("-", cell_style),
                Paragraph("0.00 грн", cell_style),
            ]
        )

    # Subtotal Section 2
    mounted_table_data.append(
        [
            Paragraph("Разом в роботі", header_cell_style),
            Paragraph(f"{len(mounted_spools)} позицій", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph(f"{m_initial_g/1000.0:.2f} кг", header_cell_style),
            Paragraph(f"{m_remaining_g/1000.0:.2f} кг", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph("Сума в роботі:", header_cell_style),
            Paragraph(f"{m_value_uah:.2f} грн", header_cell_style),
        ]
    )

    t_mounted = Table(mounted_table_data, colWidths=mounted_widths, repeatRows=1)
    t_mounted.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f46e5")),
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
    story.append(t_mounted)
    story.append(Spacer(1, 14))

    # ==========================================
    # SECTION 3: 📊 Підсумковий баланс
    # ==========================================
    story.append(Paragraph("📊 3. Підсумковий баланс пластику 3D ферми", section_style))
    story.append(Spacer(1, 4))

    grand_total_pos = len(warehouse_spools) + len(mounted_spools)
    grand_total_qty = wh_qty + m_qty
    grand_initial_kg = (wh_initial_g + m_initial_g) / 1000.0
    grand_remaining_kg = (wh_remaining_g + m_remaining_g) / 1000.0
    grand_value_uah = wh_value_uah + m_value_uah

    summary_widths = [200, 100, 110, 120, 130, 140]
    summary_data = [
        [
            Paragraph("Категорія обліку", header_cell_style),
            Paragraph("Позицій", header_cell_style),
            Paragraph("К-сть котушок", header_cell_style),
            Paragraph("Початкова вага", header_cell_style),
            Paragraph("Залишок ваги", header_cell_style),
            Paragraph("Вартість залишку", header_cell_style),
        ],
        [
            Paragraph("📦 Вільні залишки на складі", cell_style),
            Paragraph(f"{len(warehouse_spools)} поз.", cell_style),
            Paragraph(f"{wh_qty} шт", cell_style),
            Paragraph(f"{wh_initial_g/1000.0:.2f} кг", cell_style),
            Paragraph(f"{wh_remaining_g/1000.0:.2f} кг", bold_cell_style),
            Paragraph(f"{wh_value_uah:,.2f} грн", bold_cell_style),
        ],
        [
            Paragraph("🖨️ Встановлені на принтерах", cell_style),
            Paragraph(f"{len(mounted_spools)} поз.", cell_style),
            Paragraph(f"{m_qty} шт", cell_style),
            Paragraph(f"{m_initial_g/1000.0:.2f} кг", cell_style),
            Paragraph(f"{m_remaining_g/1000.0:.2f} кг", bold_cell_style),
            Paragraph(f"{m_value_uah:,.2f} грн", bold_cell_style),
        ],
        [
            Paragraph("<b>🏆 ЗАГАЛЬНИЙ БАЛАНС ФЕРМИ</b>", bold_cell_style),
            Paragraph(f"<b>{grand_total_pos} поз.</b>", bold_cell_style),
            Paragraph(f"<b>{grand_total_qty} шт</b>", bold_cell_style),
            Paragraph(f"<b>{grand_initial_kg:.2f} кг</b>", bold_cell_style),
            Paragraph(f"<b>{grand_remaining_kg:.2f} кг</b>", bold_cell_style),
            Paragraph(f"<b>{grand_value_uah:,.2f} грн</b>", bold_cell_style),
        ],
    ]

    t_summary = Table(summary_data, colWidths=summary_widths)
    t_summary.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("BACKGROUND", (0, 1), (-1, 1), colors.white),
                ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#f8fafc")),
                ("BACKGROUND", (0, 3), (-1, 3), colors.HexColor("#ecfdf5")),
                ("BOX", (0, 3), (-1, 3), 1.5, colors.HexColor("#10b981")),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(KeepTogether([t_summary]))

    doc.build(story, canvasmaker=NumberedCanvas)
    return buf.getvalue()


def _resolve_part_report_fields(p: dict[str, Any]) -> tuple[float, str, str]:
    """Resolves (weight_g, printer_model, filament_type) for a part with fallback to 3MF on disk."""
    p_weight = 0.0
    for k in ["weight_g", "weight", "filament_weight", "part_weight"]:
        try:
            val = float(p.get(k, 0.0) or 0.0)
            if val > 0.0:
                p_weight = val
                break
        except (ValueError, TypeError):
            pass

    p_model = str(p.get("printer_model", "-") or "-")
    p_fil = str(p.get("filament_type", "PLA") or "PLA")

    if p_weight <= 0.0 or p_model in ["-", "Unknown", ""]:
        three_mf = p.get("three_mf")
        three_mf_name = p.get("three_mf_name")
        for fname in [three_mf, three_mf_name]:
            if not fname:
                continue
            import config
            for d in [config.STORAGE_DIR / "uploads", config.STORAGE_DIR / "parts_files"]:
                p_path = d / fname
                if p_path.exists() and p_path.is_file():
                    try:
                        from services.gcode_parser import parse_3mf_file
                        meta = parse_3mf_file(p_path.read_bytes(), three_mf_name or p_path.name)
                        if p_weight <= 0.0 and meta.get("weight_g"):
                            p_weight = float(meta["weight_g"])
                        if p_model in ["-", "Unknown", ""] and meta.get("printer_model") and meta.get("printer_model") != "Unknown":
                            p_model = str(meta["printer_model"])
                        if (not p_fil or p_fil == "PLA") and meta.get("filament_type"):
                            p_fil = str(meta["filament_type"])
                        break
                    except Exception:
                        pass
            if p_weight > 0.0:
                break

    return p_weight, p_model, p_fil


def generate_parts_pdf_report(parts: dict[str, Any]) -> bytes:
    """Generates Landscape A4 PDF export for Printed 3D Parts warehouse."""
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
        "PartTitle",
        parent=styles["Heading1"],
        fontName=font_bold,
        fontSize=15,
        leading=18,
        textColor=colors.HexColor("#0f172a"),
    )
    subtitle_style = ParagraphStyle(
        "PartSubtitle",
        fontName=font_reg,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#64748b"),
    )
    header_cell_style = ParagraphStyle(
        "PartHeaderCell",
        fontName=font_bold,
        fontSize=8,
        leading=10,
        textColor=colors.white,
    )
    cell_style = ParagraphStyle(
        "PartCell",
        fontName=font_reg,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1e293b"),
    )
    bold_cell_style = ParagraphStyle(
        "PartBoldCell",
        fontName=font_bold,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#0f172a"),
    )

    story: list[Any] = []
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    story.append(Paragraph("🧩 Звіт складу надрукованих 3D деталей", title_style))
    story.append(
        Paragraph(
            f"Згенеровано: <b>{now_str}</b> | Загальна кількість найменувань: <b>{len(parts)}</b>",
            subtitle_style,
        )
    )
    story.append(Spacer(1, 10))

    col_widths = [65, 230, 155, 95, 80, 75, 100]
    table_data = [
        [
            Paragraph("ID", header_cell_style),
            Paragraph("Назва деталі", header_cell_style),
            Paragraph("Модель принтера", header_cell_style),
            Paragraph("Тип пластику", header_cell_style),
            Paragraph("Вага 1 шт (г)", header_cell_style),
            Paragraph("К-сть (шт)", header_cell_style),
            Paragraph("Загальна вага", header_cell_style),
        ]
    ]

    total_qty = 0
    total_single_weight_g = 0.0
    total_weight_g = 0.0

    if parts and isinstance(parts, dict):
        for p_id, p in parts.items():
            if isinstance(p, dict):
                part_id = html.escape(str(p.get("id", p_id)))
                p_name = html.escape(str(p.get("name", "Деталь")))
                p_weight, p_model_val, p_fil_val = _resolve_part_report_fields(p)
                p_model = html.escape(p_model_val)
                p_fil = html.escape(p_fil_val)
                p_qty = max(1, int(p.get("count", 1) or p.get("quantity", 1) or 1))
                item_tot_w = p_weight * p_qty
                total_qty += p_qty
                total_single_weight_g += p_weight
                total_weight_g += item_tot_w

                if item_tot_w >= 1000.0:
                    item_tot_str = f"{item_tot_w/1000.0:.2f} кг"
                elif item_tot_w > 0:
                    item_tot_str = f"{item_tot_w:.1f} г ({item_tot_w/1000.0:.2f} кг)" if p_qty > 1 else f"{item_tot_w:.1f} г"
                else:
                    item_tot_str = "-"

                table_data.append(
                    [
                        Paragraph(part_id, cell_style),
                        Paragraph(p_name, cell_style),
                        Paragraph(p_model, cell_style),
                        Paragraph(p_fil, cell_style),
                        Paragraph(f"{p_weight:.1f} г" if p_weight > 0 else "-", cell_style),
                        Paragraph(f"{p_qty} шт", bold_cell_style),
                        Paragraph(item_tot_str, bold_cell_style),
                    ]
                )

    # Summary Row: under 'Вага 1 шт (г)' show sum of 1 pc; under 'Загальна вага' show total weight
    single_w_str = f"{total_single_weight_g/1000.0:.2f} кг" if total_single_weight_g >= 1000.0 else f"{total_single_weight_g:.1f} г"
    if total_weight_g >= 1000.0:
        tot_w_str = f"{total_weight_g/1000.0:.2f} кг"
    elif total_weight_g > 0:
        tot_w_str = f"{total_weight_g:.1f} г ({total_weight_g/1000.0:.2f} кг)" if total_qty > 1 else f"{total_weight_g:.1f} г"
    else:
        tot_w_str = "-"

    table_data.append(
        [
            Paragraph("Всього", header_cell_style),
            Paragraph(f"{len(parts)} найменувань", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph(single_w_str if total_single_weight_g > 0 else "-", header_cell_style),
            Paragraph(f"{total_qty} шт", header_cell_style),
            Paragraph(tot_w_str, header_cell_style),
        ]
    )

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7c3aed")),
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


def generate_combined_warehouse_pdf_report(
    spools: dict[str, Any],
    parts: dict[str, Any],
    printers: dict[str, Any] | None = None,
) -> bytes:
    """Generates Landscape A4 PDF export combining both Spools Warehouse and Parts Warehouse."""
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
        "MainTitle",
        parent=styles["Heading1"],
        fontName=font_bold,
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#0f172a"),
    )
    section_style = ParagraphStyle(
        "SectionTitle",
        parent=styles["Heading2"],
        fontName=font_bold,
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#1e293b"),
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        fontName=font_reg,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#64748b"),
    )
    header_cell_style = ParagraphStyle(
        "HCell",
        fontName=font_bold,
        fontSize=8,
        leading=10,
        textColor=colors.white,
    )
    cell_style = ParagraphStyle(
        "Cell",
        fontName=font_reg,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1e293b"),
    )
    bold_cell_style = ParagraphStyle(
        "BCell",
        fontName=font_bold,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#0f172a"),
    )

    story: list[Any] = []
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    story.append(Paragraph("🏢 Зведений звіт матеріального складу 3D Ферми", title_style))
    story.append(Paragraph(f"Згенеровано: <b>{now_str}</b>", subtitle_style))
    story.append(Spacer(1, 10))

    # Section 1: Spools
    story.append(Paragraph("🧵 1. Склад котушок пластику", section_style))
    story.append(Spacer(1, 4))

    spool_widths = [45, 145, 60, 60, 65, 65, 75, 45, 120, 120]
    spool_table_data = [
        [
            Paragraph("ID", header_cell_style),
            Paragraph("Назва котушки", header_cell_style),
            Paragraph("Тип", header_cell_style),
            Paragraph("Колір", header_cell_style),
            Paragraph("Поч. вага", header_cell_style),
            Paragraph("Залишок", header_cell_style),
            Paragraph("Ціна (грн/кг)", header_cell_style),
            Paragraph("К-сть", header_cell_style),
            Paragraph("Статус / Слот", header_cell_style),
            Paragraph("Сума (грн)", header_cell_style),
        ]
    ]

    total_spool_val = 0.0
    total_spool_weight_g = 0.0
    total_spool_qty = 0

    if spools and isinstance(spools, dict):
        for s_id, s in spools.items():
            if isinstance(s, dict):
                spool_id = html.escape(str(s.get("id", s_id)))
                name = html.escape(str(s.get("name", "Котушка")))
                fil_type = html.escape(str(s.get("type", "PLA")))
                color = html.escape(str(s.get("color") or "-"))
                initial_g = float(s.get("initial_grams") or s.get("total_grams") or 1000.0)
                remaining_g = float(s.get("remaining_grams") or 1000.0)
                price_per_kg = float(s.get("price_per_kg") or 650.0)
                qty = max(1, int(s.get("quantity", 1)))
                slot_info = s.get("assigned_slot_key")
                p_id = s.get("assigned_printer_id")
                if p_id or slot_info:
                    p_name = _resolve_printer_name(p_id, printers)
                    slot_desc = _format_slot_name(slot_info)
                    status = f"{p_name} ({slot_desc})"
                else:
                    status = "На складі"

                val_uah = (remaining_g / 1000.0) * price_per_kg * qty
                total_spool_val += val_uah
                total_spool_weight_g += remaining_g * qty
                total_spool_qty += qty

                spool_table_data.append(
                    [
                        Paragraph(spool_id, cell_style),
                        Paragraph(name, cell_style),
                        Paragraph(fil_type, cell_style),
                        Paragraph(color, cell_style),
                        Paragraph(f"{initial_g:.1f} г", cell_style),
                        Paragraph(f"{remaining_g:.1f} г", bold_cell_style),
                        Paragraph(f"{price_per_kg:.2f}", cell_style),
                        Paragraph(str(qty), cell_style),
                        Paragraph(status, cell_style),
                        Paragraph(f"{val_uah:.2f} грн", bold_cell_style),
                    ]
                )

    spool_table_data.append(
        [
            Paragraph("Разом котушки", header_cell_style),
            Paragraph(f"{len(spools)} позицій", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph(f"{total_spool_weight_g/1000.0:.2f} кг", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph(f"{total_spool_qty} шт", header_cell_style),
            Paragraph("Сума котушок:", header_cell_style),
            Paragraph(f"{total_spool_val:.2f} грн", header_cell_style),
        ]
    )

    t_spools = Table(spool_table_data, colWidths=spool_widths, repeatRows=1)
    t_spools.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0284c7")),
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
    story.append(t_spools)
    story.append(Spacer(1, 14))

    # Section 2: Parts
    story.append(Paragraph("🧩 2. Склад надрукованих деталей", section_style))
    story.append(Spacer(1, 4))

    part_widths = [65, 230, 155, 95, 80, 75, 100]
    part_table_data = [
        [
            Paragraph("ID", header_cell_style),
            Paragraph("Назва деталі", header_cell_style),
            Paragraph("Модель принтера", header_cell_style),
            Paragraph("Тип пластику", header_cell_style),
            Paragraph("Вага 1 шт (г)", header_cell_style),
            Paragraph("К-сть (шт)", header_cell_style),
            Paragraph("Загальна вага", header_cell_style),
        ]
    ]

    total_part_qty = 0
    total_part_single_weight_g = 0.0
    total_part_weight_g = 0.0

    if parts and isinstance(parts, dict):
        for p_id, p in parts.items():
            if isinstance(p, dict):
                part_id = html.escape(str(p.get("id", p_id)))
                p_name = html.escape(str(p.get("name", "Деталь")))
                p_weight, p_model_val, p_fil_val = _resolve_part_report_fields(p)
                p_model = html.escape(p_model_val)
                p_fil = html.escape(p_fil_val)
                p_qty = max(1, int(p.get("count", 1) or p.get("quantity", 1) or 1))
                item_tot_w = p_weight * p_qty
                total_part_qty += p_qty
                total_part_single_weight_g += p_weight
                total_part_weight_g += item_tot_w

                if item_tot_w >= 1000.0:
                    item_tot_str = f"{item_tot_w/1000.0:.2f} кг"
                elif item_tot_w > 0:
                    item_tot_str = f"{item_tot_w:.1f} г ({item_tot_w/1000.0:.2f} кг)" if p_qty > 1 else f"{item_tot_w:.1f} г"
                else:
                    item_tot_str = "-"

                part_table_data.append(
                    [
                        Paragraph(part_id, cell_style),
                        Paragraph(p_name, cell_style),
                        Paragraph(p_model, cell_style),
                        Paragraph(p_fil, cell_style),
                        Paragraph(f"{p_weight:.1f} г" if p_weight > 0 else "-", cell_style),
                        Paragraph(f"{str(p_qty)} шт", bold_cell_style),
                        Paragraph(item_tot_str, bold_cell_style),
                    ]
                )

    single_part_w_str = f"{total_part_single_weight_g/1000.0:.2f} кг" if total_part_single_weight_g >= 1000.0 else f"{total_part_single_weight_g:.1f} г"
    if total_part_weight_g >= 1000.0:
        tot_part_w_str = f"{total_part_weight_g/1000.0:.2f} кг"
    elif total_part_weight_g > 0:
        tot_part_w_str = f"{total_part_weight_g:.1f} г ({total_part_weight_g/1000.0:.2f} кг)" if total_part_qty > 1 else f"{total_part_weight_g:.1f} г"
    else:
        tot_part_w_str = "-"

    part_table_data.append(
        [
            Paragraph("Разом деталі", header_cell_style),
            Paragraph(f"{len(parts)} найменувань", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph(single_part_w_str if total_part_single_weight_g > 0 else "-", header_cell_style),
            Paragraph(f"{total_part_qty} шт", header_cell_style),
            Paragraph(tot_part_w_str, header_cell_style),
        ]
    )

    t_parts = Table(part_table_data, colWidths=part_widths, repeatRows=1)
    t_parts.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7c3aed")),
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
    story.append(t_parts)
    story.append(Spacer(1, 14))

    # Grand Summary Card
    grand_total = total_spool_val
    grand_summary_data = [
        [
            Paragraph("💰 ЗАГАЛЬНА ВАРТІСТЬ СКЛАДУ КОТУШОК:", bold_cell_style),
            Paragraph(f"<b>{grand_total:,.2f} грн</b>", bold_cell_style),
        ]
    ]
    t_grand = Table(grand_summary_data, colWidths=[550, 250])
    t_grand.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ecfdf5")),
                ("BOX", (0, 0), (-1, -1), 1.5, colors.HexColor("#10b981")),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(KeepTogether([t_grand]))

    doc.build(story, canvasmaker=NumberedCanvas)
    return buf.getvalue()


def generate_movements_pdf_report(
    movements: list[dict[str, Any]],
    filter_subtitle: str | None = None,
) -> bytes:
    """Generates Landscape A4 PDF export for Warehouse Audit Movements log."""
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
        "MovTitle",
        parent=styles["Heading1"],
        fontName=font_bold,
        fontSize=15,
        leading=18,
        textColor=colors.HexColor("#0f172a"),
    )
    subtitle_style = ParagraphStyle(
        "MovSubtitle",
        fontName=font_reg,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#64748b"),
    )
    header_cell_style = ParagraphStyle(
        "MovHeaderCell",
        fontName=font_bold,
        fontSize=8,
        leading=10,
        textColor=colors.white,
    )
    cell_style = ParagraphStyle(
        "MovCell",
        fontName=font_reg,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1e293b"),
    )

    story: list[Any] = []
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    story.append(Paragraph("📋 Журнал аудиту та переміщень складу", title_style))
    
    sub_text = f"Згенеровано: <b>{now_str}</b> | Всього подій: <b>{len(movements)}</b>"
    if filter_subtitle:
        sub_text += f"<br/>🔍 <b>Фільтр:</b> {html.escape(filter_subtitle)}"
    story.append(Paragraph(sub_text, subtitle_style))
    story.append(Spacer(1, 10))

    col_widths = [40, 105, 125, 80, 65, 65, 65, 170, 85]
    table_data = [
        [
            Paragraph("ID", header_cell_style),
            Paragraph("Дата та час", header_cell_style),
            Paragraph("Котушка", header_cell_style),
            Paragraph("Дія", header_cell_style),
            Paragraph("Зміна (г)", header_cell_style),
            Paragraph("Попередня", header_cell_style),
            Paragraph("Нова", header_cell_style),
            Paragraph("Причина / Деталі", header_cell_style),
            Paragraph("Користувач", header_cell_style),
        ]
    ]

    action_labels = {
        "initial_stock": "Внесення",
        "refill": "Поповнення",
        "manual_edit": "Коригування",
        "print": "Друк",
        "write_off": "Списання",
    }

    sorted_movs = sorted(movements, key=lambda x: x.get("timestamp", 0), reverse=True)
    for m in sorted_movs:
        raw_act = str(m.get("action", "-"))
        act_display = action_labels.get(raw_act, raw_act)
        table_data.append(
            [
                Paragraph(html.escape(str(m.get("id", "-"))), cell_style),
                Paragraph(html.escape(str(m.get("datetime", "-"))), cell_style),
                Paragraph(html.escape(str(m.get("spool_name", "-"))), cell_style),
                Paragraph(html.escape(act_display), cell_style),
                Paragraph(f"{m.get('weight_change_g', 0.0):+.1f}", cell_style),
                Paragraph(f"{m.get('prev_weight_g', 0.0):.1f}", cell_style),
                Paragraph(f"{m.get('new_weight_g', 0.0):.1f}", cell_style),
                Paragraph(html.escape(str(m.get("reason", "-"))), cell_style),
                Paragraph(html.escape(str(m.get("user", "System"))), cell_style),
            ]
        )

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#475569")),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
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


def generate_warehouse_pdf_report(
    spools: dict[str, Any],
    parts: dict[str, Any] | None = None,
    report_type: str = "all",
    printers: dict[str, Any] | None = None,
) -> bytes:
    """Delegates to spools, parts or combined PDF report generator based on report_type."""
    if report_type == "parts" and parts:
        return generate_parts_pdf_report(parts)
    if report_type == "spools":
        return generate_spools_pdf_report(spools, printers=printers)
    if parts:
        return generate_combined_warehouse_pdf_report(spools, parts, printers=printers)
    return generate_spools_pdf_report(spools, printers=printers)


def generate_commercial_pdf_report(
    presets: dict[str, Any],
    lang: str = "uk",
) -> bytes:
    """Generates a professional Landscape A4 PDF report for commercial pricing presets."""
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
        "CommTitle",
        parent=styles["Heading1"],
        fontName=font_bold,
        fontSize=15,
        leading=18,
        textColor=colors.HexColor("#0f172a"),
    )
    subtitle_style = ParagraphStyle(
        "CommSubtitle",
        fontName=font_reg,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#64748b"),
    )
    header_cell_style = ParagraphStyle(
        "CommHeaderCell",
        fontName=font_bold,
        fontSize=8,
        leading=10,
        textColor=colors.white,
    )
    cell_style = ParagraphStyle(
        "CommCell",
        fontName=font_reg,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1e293b"),
    )
    bold_cell_style = ParagraphStyle(
        "CommBoldCell",
        fontName=font_bold,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#0f172a"),
    )

    story: list[Any] = []
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    is_en = lang == "en"

    doc_title = "💰 Звіт комерційних пресетів та розрахунку ціни" if not is_en else "💰 Commercial Pricing Presets & Calculation Report"
    gen_str = (
        f"Згенеровано: <b>{now_str}</b> | Загальна кількість пресетів: <b>{len(presets)}</b>"
        if not is_en
        else f"Generated: <b>{now_str}</b> | Total Presets: <b>{len(presets)}</b>"
    )
    story.append(Paragraph(doc_title, title_style))
    story.append(Paragraph(gen_str, subtitle_style))
    story.append(Spacer(1, 10))

    col_widths = [190, 100, 100, 80, 110, 110, 110]
    headers = [
        "Назва пресету" if not is_en else "Preset Name",
        "Ціна пластику" if not is_en else "Filament Rate",
        "Тариф ел." if not is_en else "Power Rate",
        "Потужність" if not is_en else "Wattage",
        "Амортизація" if not is_en else "Depreciation",
        "Витратники" if not is_en else "Consumables",
        "Маржа / Прибуток" if not is_en else "Margin / Profit",
    ]
    table_data = [[Paragraph(h, header_cell_style) for h in headers]]

    if presets and isinstance(presets, dict):
        for pid, p in presets.items():
            if not isinstance(p, dict):
                continue
            name = html.escape(str(p.get("name", pid)))
            pr_g = float(p.get("price_per_g", 0.85))
            pr_kg = pr_g * 1000.0
            elec = float(p.get("electricity_rate_uah", 4.32))
            watts = float(p.get("power_watts", 120.0))
            depr = html.escape(str(p.get("depreciation_val", "10")))
            cons = html.escape(str(p.get("consumables_val", "5")))
            prof = html.escape(str(p.get("profit_val", "100%")))

            fil_str = (
                f"{pr_g:.2f} грн/г ({pr_kg:.0f} грн/кг)"
                if not is_en
                else f"{pr_g:.2f} UAH/g ({pr_kg:.0f} UAH/kg)"
            )
            elec_str = f"{elec:.2f} грн/кВт·год" if not is_en else f"{elec:.2f} UAH/kWh"
            watt_str = f"{watts:.0f} Вт" if not is_en else f"{watts:.0f} W"
            depr_str = f"{depr} грн/год" if "%" not in depr and not depr.endswith("грн") else depr
            cons_str = f"{cons} грн/год" if "%" not in cons and not cons.endswith("грн") else cons
            prof_str = f"+{prof}" if not prof.startswith("+") else prof

            table_data.append(
                [
                    Paragraph(name, bold_cell_style),
                    Paragraph(fil_str, cell_style),
                    Paragraph(elec_str, cell_style),
                    Paragraph(watt_str, cell_style),
                    Paragraph(depr_str, cell_style),
                    Paragraph(cons_str, cell_style),
                    Paragraph(prof_str, bold_cell_style),
                ]
            )

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f766e")),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0fdf4")]),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(t)

    # Info summary card
    story.append(Spacer(1, 14))
    info_header = "ℹ️ Інструкція з комерційного ціноутворення" if not is_en else "ℹ️ Commercial Pricing Guide"
    info_desc = (
        "Собівартість розраховується за формулою: <b>Собівартість = Пластик + Електроенергія + Амортизація + Витратники</b>.<br/>"
        "Підсумкова ціна для клієнта = <b>Собівартість + Націнка/Прибуток</b>."
    ) if not is_en else (
        "Cost price formula: <b>Cost = Filament + Electricity + Depreciation + Consumables</b>.<br/>"
        "Final client price = <b>Cost + Profit Margin</b>."
    )
    card_data = [
        [Paragraph(f"<b>{info_header}</b>", bold_cell_style)],
        [Paragraph(info_desc, cell_style)],
    ]
    card_table = Table(card_data, colWidths=[800])
    card_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(card_table)

    doc.build(story, canvasmaker=NumberedCanvas)
    return buf.getvalue()


def generate_commercial_calc_pdf(
    calc: dict[str, Any],
    filename: str | None = None,
    lang: str = "uk",
) -> bytes:
    """Generates a professional Landscape A4 PDF commercial quotation for a specific calculation."""
    font_reg, font_bold = _setup_reportlab_fonts()
    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=25,
        rightMargin=25,
        topMargin=25,
        bottomMargin=30,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CalcTitle",
        parent=styles["Heading1"],
        fontName=font_bold,
        fontSize=15,
        leading=18,
        textColor=colors.HexColor("#0f172a"),
    )
    subtitle_style = ParagraphStyle(
        "CalcSubtitle",
        fontName=font_reg,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#64748b"),
    )
    header_cell_style = ParagraphStyle(
        "CalcHeaderCell",
        fontName=font_bold,
        fontSize=9,
        leading=11,
        textColor=colors.white,
    )
    cell_style = ParagraphStyle(
        "CalcCell",
        fontName=font_reg,
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#1e293b"),
    )
    bold_cell_style = ParagraphStyle(
        "CalcBoldCell",
        fontName=font_bold,
        fontSize=9,
        leading=11,
        textColor=colors.HexColor("#0f172a"),
    )

    story: list[Any] = []
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    is_en = lang == "en"

    doc_title = (
        "💼 Комерційна пропозиція та розрахунок вартості 3D друку"
        if not is_en
        else "💼 3D Printing Commercial Quotation"
    )
    preset_n = html.escape(str(calc.get("preset_name", "Стандарт")))
    file_info_str = f" | Файл: <b>{html.escape(filename)}</b>" if filename else ""
    gen_str = (
        f"Згенеровано: <b>{now_str}</b>{file_info_str} | Пресет: <b>{preset_n}</b>"
        if not is_en
        else f"Generated: <b>{now_str}</b>{file_info_str} | Preset: <b>{preset_n}</b>"
    )
    story.append(Paragraph(doc_title, title_style))
    story.append(Paragraph(gen_str, subtitle_style))
    story.append(Spacer(1, 12))

    weight_g = float(calc.get("weight_g", 0.0) or 0.0)
    time_mins = int(calc.get("time_mins", 0) or 0)
    time_hours = float(calc.get("time_hours", 0.0) or (time_mins / 60.0))
    filament_cost = float(calc.get("filament_cost", 0.0) or 0.0)
    electricity_cost = float(calc.get("electricity_cost", 0.0) or 0.0)
    direct_cost = float(calc.get("direct_cost", round(filament_cost + electricity_cost, 2)) or 0.0)
    depr_cost = float(calc.get("depreciation_cost", 0.0) or 0.0)
    depr_str = str(calc.get("depreciation_str", "-"))
    cons_cost = float(calc.get("consumables_cost", 0.0) or 0.0)
    cons_str = str(calc.get("consumables_str", "-"))
    cost_before_profit = float(calc.get("cost_before_profit", round(direct_cost + depr_cost + cons_cost, 2)) or 0.0)
    profit_cost = float(calc.get("profit_cost", 0.0) or 0.0)
    profit_str = str(calc.get("profit_str", "-"))
    total_price = float(calc.get("total_price", 0.0) or 0.0)

    # Filament preset rate
    pr_g = calc.get("price_per_g")
    if pr_g is None and weight_g > 0:
        pr_g = round(filament_cost / weight_g, 2)
    elif pr_g is None:
        pr_g = 0.85
    pr_g = float(pr_g)
    pr_kg = pr_g * 1000.0

    # Electricity preset rates
    elec_rate = float(calc.get("electricity_rate_uah", 4.32) or 4.32)
    power_w = float(calc.get("power_watts", 120.0) or 120.0)

    # Column 2 (Model data) and Column 3 (Preset data)
    fil_model = f"Вага: {weight_g:.1f} г" if not is_en else f"Weight: {weight_g:.1f} g"
    fil_preset = f"{pr_g:.2f} грн/г ({pr_kg:.0f} грн/кг)" if not is_en else f"{pr_g:.2f} UAH/g ({pr_kg:.0f} UAH/kg)"

    elec_model = f"Час: ~{time_mins} хв ({time_hours:.2f} год)" if not is_en else f"Time: ~{time_mins} min ({time_hours:.2f} h)"
    elec_preset = f"{power_w:.0f} Вт | {elec_rate:.2f} грн/кВт·год" if not is_en else f"{power_w:.0f} W | {elec_rate:.2f} UAH/kWh"

    if "%" in depr_str:
        depr_model = f"База витрат: {direct_cost:.2f} грн" if not is_en else f"Direct cost: {direct_cost:.2f} UAH"
        depr_preset = f"Ставка: {depr_str}" if not is_en else f"Rate: {depr_str}"
    else:
        depr_model = f"Час друку: {time_hours:.2f} год" if not is_en else f"Print time: {time_hours:.2f} h"
        d_val = f"{depr_str} грн/год" if not depr_str.endswith("грн/год") and not depr_str.endswith("грн") else depr_str
        depr_preset = d_val if not is_en else d_val.replace("грн/год", "UAH/h").replace("грн", "UAH")

    if "%" in cons_str:
        cons_model = f"База витрат: {direct_cost:.2f} грн" if not is_en else f"Direct cost: {direct_cost:.2f} UAH"
        cons_preset = f"Ставка: {cons_str}" if not is_en else f"Rate: {cons_str}"
    else:
        cons_model = f"Час друку: {time_hours:.2f} год" if not is_en else f"Print time: {time_hours:.2f} h"
        c_val = f"{cons_str} грн/год" if not cons_str.endswith("грн/год") and not cons_str.endswith("грн") else cons_str
        cons_preset = c_val if not is_en else c_val.replace("грн/год", "UAH/h").replace("грн", "UAH")

    profit_is_pct = calc.get("profit_is_pct", False)
    if profit_is_pct or "%" in profit_str:
        formatted_profit = f"+{profit_str.lstrip('+')}" if not profit_str.startswith("+") else profit_str
    else:
        try:
            val = float(profit_str)
            formatted_profit = f"{val:.2f} грн" if not is_en else f"{val:.2f} UAH"
        except ValueError:
            formatted_profit = f"{profit_str} грн" if not is_en else f"{profit_str} UAH"

    prof_model = f"Собівартість: {cost_before_profit:.2f} грн" if not is_en else f"Cost base: {cost_before_profit:.2f} UAH"
    prof_preset = f"Націнка: {formatted_profit}" if not is_en else f"Markup: {formatted_profit}"

    col_widths = [165, 125, 135, 120]
    table_data = [
        [
            Paragraph("Стаття витрат" if not is_en else "Cost Item", header_cell_style),
            Paragraph("Дані моделі" if not is_en else "Model Data", header_cell_style),
            Paragraph("Дані пресета" if not is_en else "Preset Data", header_cell_style),
            Paragraph("Сума (грн)" if not is_en else "Amount (UAH)", header_cell_style),
        ],
        [
            Paragraph("🧵 Пластик / Філамент" if not is_en else "🧵 Filament Material", cell_style),
            Paragraph(fil_model, cell_style),
            Paragraph(fil_preset, cell_style),
            Paragraph(f"{filament_cost:.2f} грн" if not is_en else f"{filament_cost:.2f} UAH", bold_cell_style),
        ],
        [
            Paragraph("⚡ Електроенергія" if not is_en else "⚡ Electricity", cell_style),
            Paragraph(elec_model, cell_style),
            Paragraph(elec_preset, cell_style),
            Paragraph(f"{electricity_cost:.2f} грн" if not is_en else f"{electricity_cost:.2f} UAH", bold_cell_style),
        ],
        [
            Paragraph("🔧 Амортизація обладнання" if not is_en else "🔧 Depreciation", cell_style),
            Paragraph(depr_model, cell_style),
            Paragraph(depr_preset, cell_style),
            Paragraph(f"{depr_cost:.2f} грн" if not is_en else f"{depr_cost:.2f} UAH", bold_cell_style),
        ],
        [
            Paragraph(
                "🧼 Витратні матеріали та ТО" if not is_en else "🧼 Consumables & Maintenance",
                cell_style,
            ),
            Paragraph(cons_model, cell_style),
            Paragraph(cons_preset, cell_style),
            Paragraph(f"{cons_cost:.2f} грн" if not is_en else f"{cons_cost:.2f} UAH", bold_cell_style),
        ],
        [
            Paragraph("💼 Маржа / Прибуток" if not is_en else "💼 Profit Margin", bold_cell_style),
            Paragraph(prof_model, cell_style),
            Paragraph(prof_preset, bold_cell_style),
            Paragraph(f"{profit_cost:.2f} грн" if not is_en else f"{profit_cost:.2f} UAH", bold_cell_style),
        ],
        [
            Paragraph("<b>🏷️ РАЗОМ ДЛЯ КЛІЄНТА</b>" if not is_en else "<b>🏷️ TOTAL FOR CLIENT</b>", header_cell_style),
            Paragraph(f"<b>{weight_g:.1f} г | ~{time_mins} хв</b>" if not is_en else f"<b>{weight_g:.1f} g | ~{time_mins} min</b>", header_cell_style),
            Paragraph(f"<b>Пресет: {preset_n}</b>" if not is_en else f"<b>Preset: {preset_n}</b>", header_cell_style),
            Paragraph(f"<b>{total_price:.2f} грн</b>" if not is_en else f"<b>{total_price:.2f} UAH</b>", header_cell_style),
        ],
    ]

    t = Table(table_data, colWidths=col_widths)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#0f766e")),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f8fafc")]),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(t)

    doc.build(story, canvasmaker=NumberedCanvas)
    return buf.getvalue()


