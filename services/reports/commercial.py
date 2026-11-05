"""
Commercial pricing presets and calculation PDF report generator.
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
from reportlab.platypus import HRFlowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from services.reports.base import NumberedCanvas, _setup_reportlab_fonts

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
    story.append(Spacer(1, 8))

    client_order = str(calc.get("client_order") or "").strip()
    if client_order:
        order_lbl = "Замовник / Номер замовлення:" if not is_en else "Client / Order Reference:"
        story.append(
            Paragraph(
                f"👤 {order_lbl} <b>{html.escape(client_order)}</b>",
                ParagraphStyle(
                    "CalcClientRef",
                    fontName=font_bold,
                    fontSize=9,
                    leading=12,
                    textColor=colors.HexColor("#0284c7"),
                ),
            )
        )
        story.append(Spacer(1, 6))
    else:
        story.append(Spacer(1, 4))

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

    # Hardware row if present
    hw_cost = float(calc.get("hardware_cost", 0.0) or 0.0)
    hw_items = calc.get("hardware_items", [])
    if hw_cost > 0:
        hw_desc = f"{len(hw_items)} найм." if not is_en else f"{len(hw_items)} items"
        table_data.insert(2, [
            Paragraph("🔩 Фурнітура та метизи" if not is_en else "🔩 Hardware Components", cell_style),
            Paragraph(hw_desc, cell_style),
            Paragraph("-", cell_style),
            Paragraph(f"{hw_cost:.2f} грн" if not is_en else f"{hw_cost:.2f} UAH", bold_cell_style),
        ])

    # Operator labor row if present
    labor_cost = float(calc.get("labor_cost", 0.0) or 0.0)
    labor_rate = float(calc.get("labor_rate_uah", 0.0) or 0.0)
    prep_time = float(calc.get("prep_time_mins", 0.0) or 0.0)
    post_time = float(calc.get("post_time_mins", 0.0) or 0.0)
    if labor_cost > 0:
        lab_model = f"Підг.+пост: {prep_time+post_time:.0f} хв" if not is_en else f"Prep+post: {prep_time+post_time:.0f} min"
        lab_preset = f"Ставка: {labor_rate:.0f} грн/год" if not is_en else f"Rate: {labor_rate:.0f} UAH/h"
        table_data.insert(-2, [
            Paragraph("👷 Праця оператора" if not is_en else "👷 Operator Labor", cell_style),
            Paragraph(lab_model, cell_style),
            Paragraph(lab_preset, cell_style),
            Paragraph(f"{labor_cost:.2f} грн" if not is_en else f"{labor_cost:.2f} UAH", bold_cell_style),
        ])

    # Packaging & Shipping row if present
    pack_cost = float(calc.get("pack_cost", 0.0) or 0.0)
    if pack_cost > 0:
        table_data.insert(-2, [
            Paragraph("📦 Пакування & Доставка" if not is_en else "📦 Packaging & Shipping", cell_style),
            Paragraph(f"Пакування: {calc.get('packaging_cost', 0):.2f} грн" if not is_en else f"Pack: {calc.get('packaging_cost', 0):.2f} UAH", cell_style),
            Paragraph(f"Доставка: {calc.get('shipping_cost', 0):.2f} грн" if not is_en else f"Shipping: {calc.get('shipping_cost', 0):.2f} UAH", cell_style),
            Paragraph(f"{pack_cost:.2f} грн" if not is_en else f"{pack_cost:.2f} UAH", bold_cell_style),
        ])

    # Adjust last row if serial mode
    if calc.get("mode") == "serial":
        sqty = calc.get("serial_qty", 10)
        tot_batch = calc.get("total_batch_price", total_price * sqty)
        table_data[-1] = [
            Paragraph("<b>🏷️ РАЗОМ ЗА 1 ШТ</b>" if not is_en else "<b>🏷️ PRICE PER 1 PC</b>", header_cell_style),
            Paragraph(f"<b>Партія: {sqty} шт</b>" if not is_en else f"<b>Batch: {sqty} pcs</b>", header_cell_style),
            Paragraph(f"<b>Вся партія: {tot_batch:.2f} грн</b>" if not is_en else f"<b>Total batch: {tot_batch:.2f} UAH</b>", header_cell_style),
            Paragraph(f"<b>{total_price:.2f} грн</b>" if not is_en else f"<b>{total_price:.2f} UAH</b>", header_cell_style),
        ]

    # Re-create table with dynamic rows
    story.pop()
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

    # Verdict callout card
    if calc.get("verdict_main"):
        story.append(Spacer(1, 10))
        v_status = calc.get("verdict_status", "success")
        v_main = str(calc.get("verdict_main", ""))
        v_desc = str(calc.get("verdict_detail", ""))
        v_color = "#15803d" if v_status == "success" else "#b45309" if v_status == "warning" else "#b91c1c"
        v_bg = "#ecfdf5" if v_status == "success" else "#fef3c7" if v_status == "warning" else "#fef2f2"
        v_border = "#10b981" if v_status == "success" else "#f59e0b" if v_status == "warning" else "#ef4444"

        v_card_data = [
            [Paragraph(f"<font color='{v_color}'><b>📊 Оцінка рентабельності: {html.escape(v_main)}</b></font>", bold_cell_style)],
            [Paragraph(f"<font color='{v_color}' size='8'>{html.escape(v_desc)}</font>", cell_style)],
        ]
        v_card = Table(v_card_data, colWidths=[545])
        v_card.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(v_bg)),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor(v_border)),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(v_card)

    doc.build(story, canvasmaker=NumberedCanvas)
    return buf.getvalue()


