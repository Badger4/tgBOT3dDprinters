"""
Filament spools, parts, movements, and combined warehouse PDF report generator.
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
from reportlab.platypus import HRFlowable, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from services.reports.base import (
    NumberedCanvas,
    _format_slot_name,
    _resolve_printer_name,
    _setup_reportlab_fonts,
)

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
            Paragraph("Фото / ID", header_cell_style),
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

                import config
                img_col = None
                img_url = str(p.get("image", "")).strip()
                if img_url.startswith("/uploads/"):
                    uploads_dir = (config.STORAGE_DIR / "uploads").resolve()
                    local_filename = Path(img_url.replace("/uploads/", "")).name
                    cand = (uploads_dir / local_filename).resolve()
                    if cand.is_relative_to(uploads_dir) and cand.is_file() and cand.exists():
                        try:
                            img_col = Image(str(cand), width=50, height=50, kind='proportional')
                        except Exception:
                            pass
                
                first_col = img_col if img_col else Paragraph(part_id, cell_style)

                table_data.append(
                    [
                        first_col,
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
            Paragraph("Фото / ID", header_cell_style),
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

                import config
                img_col = None
                img_url = str(p.get("image", "")).strip()
                if img_url.startswith("/uploads/"):
                    uploads_dir = (config.STORAGE_DIR / "uploads").resolve()
                    local_filename = Path(img_url.replace("/uploads/", "")).name
                    cand = (uploads_dir / local_filename).resolve()
                    if cand.is_relative_to(uploads_dir) and cand.is_file() and cand.exists():
                        try:
                            img_col = Image(str(cand), width=50, height=50, kind='proportional')
                        except Exception:
                            pass
                
                first_col = img_col if img_col else Paragraph(part_id, cell_style)

                part_table_data.append(
                    [
                        first_col,
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


