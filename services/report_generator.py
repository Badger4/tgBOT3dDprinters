"""
Service for generating professional PDF and CSV exports and reports for farm print history and warehouses.
"""

import csv
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


def _encode_csv_with_bom(output_stringio: io.StringIO) -> bytes:
    """Encodes StringIO content to UTF-8 and ensures UTF-8 BOM (0xEF 0xBB 0xBF) is present for Excel & Mobile."""
    text = output_stringio.getvalue()
    if text.startswith("\ufeff"):
        text = text[1:]
    return b"\xef\xbb\xbf" + text.encode("utf-8")


def generate_csv_report(history: list[dict[str, Any]]) -> bytes:
    """
    Generates a UTF-8-BOM encoded CSV file from print history list.
    BOM ensures Microsoft Excel opens Ukrainian text without character corruption.
    """
    output = io.StringIO()
    output.write("\ufeff")

    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(
        [
            "№",
            "Дата та час",
            "Принтер",
            "Назва моделі / 3MF",
            "Тип пластику",
            "Витрачено пластику (г)",
            "Примітка",
        ]
    )

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
        p_name = item.get("printer_name", "Принтер")
        subtask = item.get("subtask_name", "Модель")
        filament = item.get("filament_type", "PLA")
        weight_g = item.get("weight_g", 0.0)
        note = item.get("note", "Успішно виконано")

        writer.writerow([idx, dt_str, p_name, subtask, filament, f"{weight_g:.1f}", note])

    return _encode_csv_with_bom(output)


def generate_spools_csv_report(spools: dict[str, Any]) -> bytes:
    """
    Generates CSV export for Filament Spools warehouse.
    Columns: ID, Назва котушки, Тип, Колір, Початкова вага (г), Залишок ваги (г), Ціна (грн/кг), Кількість (шт), Статус / Слот.
    """
    output = io.StringIO()
    # Write UTF-8 BOM header explicitly
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)

    writer.writerow(
        [
            "ID",
            "Назва котушки",
            "Тип",
            "Колір",
            "Початкова вага (г)",
            "Залишок ваги (г)",
            "Ціна (грн/кг)",
            "Кількість (шт)",
            "Статус / Слот",
        ]
    )

    total_initial_g = 0.0
    total_remaining_g = 0.0
    total_value_uah = 0.0
    total_qty = 0

    if spools:
        for s_id, s in spools.items():
            if isinstance(s, dict):
                spool_id = s.get("id", s_id)
                name = s.get("name", "Котушка")
                fil_type = s.get("type", "PLA")
                color = str(s.get("color") or "-")
                initial_g = float(s.get("initial_grams") or s.get("total_grams") or 1000.0)
                remaining_g = float(s.get("remaining_grams") or 1000.0)
                price_per_kg = float(s.get("price_per_kg") or 650.0)
                qty = max(1, int(s.get("quantity", 1)))
                slot_info = s.get("assigned_slot_key")
                status = f"Прив'язаний: Слот {slot_info}" if slot_info else "На складі"

                val_uah = (remaining_g / 1000.0) * price_per_kg * qty
                total_initial_g += initial_g * qty
                total_remaining_g += remaining_g * qty
                total_value_uah += val_uah
                total_qty += qty

                writer.writerow([
                    spool_id,
                    name,
                    fil_type,
                    color,
                    f"{initial_g:.1f}",
                    f"{remaining_g:.1f}",
                    f"{price_per_kg:.2f}",
                    qty,
                    status,
                ])
            elif hasattr(s, "__dict__"):
                spool_id = getattr(s, "id", s_id)
                name = getattr(s, "name", "Котушка")
                fil_type = getattr(s, "type", "PLA")
                color = getattr(s, "color", "-")
                initial_g = float(getattr(s, "initial_grams", getattr(s, "total_grams", 1000.0)))
                remaining_g = float(getattr(s, "remaining_grams", 1000.0))
                price_per_kg = float(getattr(s, "price_per_kg", 650.0))
                qty = max(1, int(getattr(s, "quantity", 1)))
                slot_info = getattr(s, "assigned_slot_key", None)
                status = f"Прив'язаний: Слот {slot_info}" if slot_info else "На складі"

                val_uah = (remaining_g / 1000.0) * price_per_kg * qty
                total_initial_g += initial_g * qty
                total_remaining_g += remaining_g * qty
                total_value_uah += val_uah
                total_qty += qty

                writer.writerow([
                    spool_id,
                    name,
                    fil_type,
                    color,
                    f"{initial_g:.1f}",
                    f"{remaining_g:.1f}",
                    f"{price_per_kg:.2f}",
                    qty,
                    status,
                ])

        # Financial Summary Row
        writer.writerow([])
        writer.writerow([
            "ВАРТІСТЬ СКЛАДУ",
            "ЗАГАЛОМ ПО ВСІХ КОТУШКАХ",
            "-",
            "-",
            f"{total_initial_g:.1f} г",
            f"{total_remaining_g:.1f} г",
            "-",
            total_qty,
            f"Загальна вартість: {total_value_uah:.2f} грн",
        ])

    return _encode_csv_with_bom(output)


def generate_parts_csv_report(parts: dict[str, Any]) -> bytes:
    """
    Generates CSV export for Printed 3D Parts warehouse.
    Columns: ID, Назва деталі, Модель принтера, Тип пластику, Вага 1 шт (г), Ціна за 1 шт (грн), Кількість (шт), Загальна вартість (грн).
    """
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)

    writer.writerow(
        [
            "ID",
            "Назва деталі",
            "Модель принтера",
            "Тип пластику",
            "Вага 1 шт (г)",
            "Ціна за 1 шт (грн)",
            "Кількість (шт)",
            "Загальна вартість (грн)",
        ]
    )

    total_qty = 0
    total_val = 0.0

    if parts and isinstance(parts, dict):
        for p_id, p in parts.items():
            if isinstance(p, dict):
                part_id = p.get("id", p_id)
                p_name = p.get("name", "Деталь")
                p_model = p.get("printer_model", "-")
                p_fil = p.get("filament_type", "PLA")
                p_weight = float(p.get("weight_g", 0.0) or p.get("weight", 0.0) or 0.0)
                p_price = float(p.get("price", 0.0) or p.get("cost", 0.0) or 0.0)
                p_qty = max(1, int(p.get("count", 1) or p.get("quantity", 1) or 1))
                row_val = p_price * p_qty
                total_qty += p_qty
                total_val += row_val

                writer.writerow([
                    part_id,
                    p_name,
                    p_model,
                    p_fil,
                    f"{p_weight:.1f}",
                    f"{p_price:.2f}",
                    p_qty,
                    f"{row_val:.2f}",
                ])

    writer.writerow([])
    writer.writerow(["ВАРТІСТЬ СКЛАДУ ДЕТАЛЕЙ", "ЗАГАЛОМ ПО ВСІХ ДЕТАЛЯХ", "-", "-", "-", "-", total_qty, f"{total_val:.2f} грн"])

    return _encode_csv_with_bom(output)


def generate_combined_warehouse_csv_report(spools: dict[str, Any], parts: dict[str, Any]) -> bytes:
    """
    Generates a combined CSV report containing both Spools Warehouse and Parts Warehouse.
    """
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)

    # Section 1: Spools Warehouse
    writer.writerow(["СКЛАД КОТУШОК ПЛАСТИКУ"])
    writer.writerow([
        "ID",
        "Назва котушки",
        "Тип",
        "Колір",
        "Початкова вага (г)",
        "Залишок ваги (г)",
        "Ціна (грн/кг)",
        "Кількість (шт)",
        "Статус / Слот",
    ])
    total_spools_val = 0.0
    if spools and isinstance(spools, dict):
        for s_id, s in spools.items():
            if isinstance(s, dict):
                spool_id = s.get("id", s_id)
                name = s.get("name", "Котушка")
                fil_type = s.get("type", "PLA")
                color = str(s.get("color") or "-")
                initial_g = float(s.get("initial_grams") or s.get("total_grams") or 1000.0)
                remaining_g = float(s.get("remaining_grams") or 1000.0)
                price_per_kg = float(s.get("price_per_kg") or 650.0)
                qty = max(1, int(s.get("quantity", 1)))
                slot_info = s.get("assigned_slot_key")
                status = f"Слот {slot_info}" if slot_info else "На складі"
                val_uah = (remaining_g / 1000.0) * price_per_kg * qty
                total_spools_val += val_uah

                writer.writerow([
                    spool_id,
                    name,
                    fil_type,
                    color,
                    f"{initial_g:.1f}",
                    f"{remaining_g:.1f}",
                    f"{price_per_kg:.2f}",
                    qty,
                    status,
                ])

    writer.writerow([])
    writer.writerow(["СКЛАД ГОТОВИХ ДЕТАЛЕЙ"])
    writer.writerow([
        "ID",
        "Назва деталі",
        "Модель принтера",
        "Тип пластику",
        "Вага 1 шт (г)",
        "Ціна за 1 шт (грн)",
        "Кількість (шт)",
        "Загальна вартість (грн)",
    ])
    total_parts_val = 0.0
    if parts and isinstance(parts, dict):
        for p_id, p in parts.items():
            if isinstance(p, dict):
                part_id = p.get("id", p_id)
                p_name = p.get("name", "Деталь")
                p_model = p.get("printer_model", "-")
                p_fil = p.get("filament_type", "PLA")
                p_weight = float(p.get("weight_g", 0.0) or p.get("weight", 0.0) or 0.0)
                p_price = float(p.get("price", 0.0) or p.get("cost", 0.0) or 0.0)
                p_qty = max(1, int(p.get("count", 1) or p.get("quantity", 1) or 1))
                t_val = p_price * p_qty
                total_parts_val += t_val

                writer.writerow([
                    part_id,
                    p_name,
                    p_model,
                    p_fil,
                    f"{p_weight:.1f}",
                    f"{p_price:.2f}",
                    p_qty,
                    f"{t_val:.2f}",
                ])

    writer.writerow([])
    writer.writerow(["ЗАГАЛЬНА ВАРТІСТЬ СКЛАДУ (КОТУШКИ + ДЕТАЛІ)", f"{total_spools_val + total_parts_val:.2f} грн"])

    return _encode_csv_with_bom(output)


def generate_warehouse_csv_report(spools: dict[str, Any], parts: dict[str, Any] | None = None, report_type: str = "all") -> bytes:
    """Delegates to spools, parts or combined report generator based on report_type."""
    if report_type == "parts" and parts:
        return generate_parts_csv_report(parts)
    if report_type == "spools":
        return generate_spools_csv_report(spools)
    if parts:
        return generate_combined_warehouse_csv_report(spools, parts)
    return generate_spools_csv_report(spools)


def generate_movements_csv_report(movements: list[dict[str, Any]]) -> bytes:
    """
    Generates CSV export for Warehouse Audit Movements log.
    Columns: ID, Дата та час, ID Котушки, Назва котушки, Дія, Зміна ваги (г), Попередня вага (г), Нова вага (г), Причина / Деталі, Користувач.
    """
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)

    writer.writerow([
        "ID",
        "Дата та час",
        "ID Котушки",
        "Назва котушки",
        "Дія",
        "Зміна ваги (г)",
        "Попередня вага (г)",
        "Нова вага (г)",
        "Причина / Деталі",
        "Користувач",
    ])

    sorted_movs = sorted(movements, key=lambda x: x.get("timestamp", 0), reverse=True)
    for m in sorted_movs:
        writer.writerow([
            m.get("id", "-"),
            m.get("datetime", "-"),
            m.get("spool_id", "-"),
            m.get("spool_name", "-"),
            m.get("action", "-"),
            f"{m.get('weight_change_g', 0.0):+.1f}",
            f"{m.get('prev_weight_g', 0.0):.1f}",
            f"{m.get('new_weight_g', 0.0):.1f}",
            m.get("reason", "-"),
            m.get("user", "System"),
        ])

    return _encode_csv_with_bom(output)


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
        note = html.escape(str(item.get("note", "Успішно")))

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


def generate_spools_pdf_report(spools: dict[str, Any]) -> bytes:
    """Generates Landscape A4 PDF export for Filament Spools warehouse."""
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
    story.append(Paragraph("🧵 Звіт складу котушок пластику", title_style))
    story.append(
        Paragraph(
            f"Згенеровано: <b>{now_str}</b> | Загальна кількість позицій: <b>{len(spools)}</b>",
            subtitle_style,
        )
    )
    story.append(Spacer(1, 10))

    col_widths = [45, 145, 60, 60, 65, 65, 75, 45, 120, 120]
    table_data = [
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

    total_initial_g = 0.0
    total_remaining_g = 0.0
    total_value_uah = 0.0
    total_qty = 0

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
                status = f"Слот {slot_info}" if slot_info else "На складі"

                val_uah = (remaining_g / 1000.0) * price_per_kg * qty
                total_initial_g += initial_g * qty
                total_remaining_g += remaining_g * qty
                total_value_uah += val_uah
                total_qty += qty

                table_data.append(
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

    # Summary Row
    table_data.append(
        [
            Paragraph("Всього", header_cell_style),
            Paragraph(f"{len(spools)} позицій", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph(f"{total_initial_g/1000.0:.2f} кг", header_cell_style),
            Paragraph(f"{total_remaining_g/1000.0:.2f} кг", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph(f"{total_qty} шт", header_cell_style),
            Paragraph("Загальна вартість:", header_cell_style),
            Paragraph(f"{total_value_uah:.2f} грн", header_cell_style),
        ]
    )

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
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
    story.append(t)

    doc.build(story, canvasmaker=NumberedCanvas)
    return buf.getvalue()


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

    col_widths = [60, 180, 120, 80, 75, 75, 60, 150]
    table_data = [
        [
            Paragraph("ID", header_cell_style),
            Paragraph("Назва деталі", header_cell_style),
            Paragraph("Модель принтера", header_cell_style),
            Paragraph("Тип пластику", header_cell_style),
            Paragraph("Вага 1 шт (г)", header_cell_style),
            Paragraph("Ціна 1 шт (грн)", header_cell_style),
            Paragraph("К-сть (шт)", header_cell_style),
            Paragraph("Загальна сума (грн)", header_cell_style),
        ]
    ]

    total_qty = 0
    total_val = 0.0

    if parts and isinstance(parts, dict):
        for p_id, p in parts.items():
            if isinstance(p, dict):
                part_id = html.escape(str(p.get("id", p_id)))
                p_name = html.escape(str(p.get("name", "Деталь")))
                p_model = html.escape(str(p.get("printer_model", "-")))
                p_fil = html.escape(str(p.get("filament_type", "PLA")))
                p_weight = float(p.get("weight_g", 0.0) or p.get("weight", 0.0) or 0.0)
                p_price = float(p.get("price", 0.0) or p.get("cost", 0.0) or 0.0)
                p_qty = max(1, int(p.get("count", 1) or p.get("quantity", 1) or 1))
                row_val = p_price * p_qty
                total_qty += p_qty
                total_val += row_val

                table_data.append(
                    [
                        Paragraph(part_id, cell_style),
                        Paragraph(p_name, cell_style),
                        Paragraph(p_model, cell_style),
                        Paragraph(p_fil, cell_style),
                        Paragraph(f"{p_weight:.1f}", cell_style),
                        Paragraph(f"{p_price:.2f}", cell_style),
                        Paragraph(str(p_qty), cell_style),
                        Paragraph(f"{row_val:.2f} грн", bold_cell_style),
                    ]
                )

    # Summary Row
    table_data.append(
        [
            Paragraph("Всього", header_cell_style),
            Paragraph(f"{len(parts)} найменувань", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph(f"{total_qty} шт", header_cell_style),
            Paragraph(f"{total_val:.2f} грн", header_cell_style),
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


def generate_combined_warehouse_pdf_report(spools: dict[str, Any], parts: dict[str, Any]) -> bytes:
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
                status = f"Слот {slot_info}" if slot_info else "На складі"

                val_uah = (remaining_g / 1000.0) * price_per_kg * qty
                total_spool_val += val_uah
                total_spool_weight_g += remaining_g * qty

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
            Paragraph("-", header_cell_style),
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

    part_widths = [60, 180, 120, 80, 75, 75, 60, 150]
    part_table_data = [
        [
            Paragraph("ID", header_cell_style),
            Paragraph("Назва деталі", header_cell_style),
            Paragraph("Модель принтера", header_cell_style),
            Paragraph("Тип пластику", header_cell_style),
            Paragraph("Вага 1 шт (г)", header_cell_style),
            Paragraph("Ціна 1 шт (грн)", header_cell_style),
            Paragraph("К-сть (шт)", header_cell_style),
            Paragraph("Загальна сума (грн)", header_cell_style),
        ]
    ]

    total_part_val = 0.0
    total_part_qty = 0

    if parts and isinstance(parts, dict):
        for p_id, p in parts.items():
            if isinstance(p, dict):
                part_id = html.escape(str(p.get("id", p_id)))
                p_name = html.escape(str(p.get("name", "Деталь")))
                p_model = html.escape(str(p.get("printer_model", "-")))
                p_fil = html.escape(str(p.get("filament_type", "PLA")))
                p_weight = float(p.get("weight_g", 0.0) or p.get("weight", 0.0) or 0.0)
                p_price = float(p.get("price", 0.0) or p.get("cost", 0.0) or 0.0)
                p_qty = max(1, int(p.get("count", 1) or p.get("quantity", 1) or 1))
                row_val = p_price * p_qty
                total_part_qty += p_qty
                total_part_val += row_val

                part_table_data.append(
                    [
                        Paragraph(part_id, cell_style),
                        Paragraph(p_name, cell_style),
                        Paragraph(p_model, cell_style),
                        Paragraph(p_fil, cell_style),
                        Paragraph(f"{p_weight:.1f}", cell_style),
                        Paragraph(f"{p_price:.2f}", cell_style),
                        Paragraph(str(p_qty), cell_style),
                        Paragraph(f"{row_val:.2f} грн", bold_cell_style),
                    ]
                )

    part_table_data.append(
        [
            Paragraph("Разом деталі", header_cell_style),
            Paragraph(f"{len(parts)} найменувань", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph("-", header_cell_style),
            Paragraph(f"{total_part_qty} шт", header_cell_style),
            Paragraph(f"{total_part_val:.2f} грн", header_cell_style),
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
    grand_total = total_spool_val + total_part_val
    grand_summary_data = [
        [
            Paragraph("💰 ЗАГАЛЬНА ВАРТІСТЬ ВСЬОГО СКЛАДУ (КОТУШКИ + ДЕТАЛІ):", bold_cell_style),
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


def generate_movements_pdf_report(movements: list[dict[str, Any]]) -> bytes:
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
    story.append(
        Paragraph(
            f"Згенеровано: <b>{now_str}</b> | Всього подій: <b>{len(movements)}</b>",
            subtitle_style,
        )
    )
    story.append(Spacer(1, 10))

    col_widths = [40, 105, 125, 75, 65, 65, 65, 175, 85]
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

    sorted_movs = sorted(movements, key=lambda x: x.get("timestamp", 0), reverse=True)
    for m in sorted_movs:
        table_data.append(
            [
                Paragraph(html.escape(str(m.get("id", "-"))), cell_style),
                Paragraph(html.escape(str(m.get("datetime", "-"))), cell_style),
                Paragraph(html.escape(str(m.get("spool_name", "-"))), cell_style),
                Paragraph(html.escape(str(m.get("action", "-"))), cell_style),
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
) -> bytes:
    """Delegates to spools, parts or combined PDF report generator based on report_type."""
    if report_type == "parts" and parts:
        return generate_parts_pdf_report(parts)
    if report_type == "spools":
        return generate_spools_pdf_report(spools)
    if parts:
        return generate_combined_warehouse_pdf_report(spools, parts)
    return generate_spools_pdf_report(spools)

