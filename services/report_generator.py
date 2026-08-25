"""
Service for generating CSV exports and reports for farm print history.
"""

import csv
import io
import time
from typing import Any


def generate_csv_report(history: list[dict[str, Any]]) -> bytes:
    """
    Generates a UTF-8-BOM encoded CSV file from print history list.
    BOM ensures Microsoft Excel opens Ukrainian text without character corruption.
    """
    output = io.StringIO()
    # Write UTF-8 BOM header explicitly
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

    sorted_history = sorted(history, key=lambda x: x.get("timestamp", 0), reverse=True)
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

    return output.getvalue().encode("utf-8")


def generate_warehouse_csv_report(spools: dict[str, Any], parts: dict[str, Any]) -> bytes:
    """
    Generates a structured CSV report for the Warehouse (Склад).
    Contains separate blocks and rows for Spools (Котушки) and Parts (Деталі) with columns:
    Назва (Name), Ціна (Price), Вага (Weight), Кількість (Quantity).
    Uses semicolon ';' delimiter and UTF-8 BOM for 100% compatibility with Excel / Sheets.
    """
    output = io.StringIO()
    # Write UTF-8 BOM header explicitly
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)

    # Header section
    writer.writerow(["=== ЗВІТ СКЛАДУ (ПЛАСТИК ТА ДЕТАЛІ) ==="])
    writer.writerow([])

    # Block 1: Filament Spools
    writer.writerow(["БЛОК 1: СКЛАД ПЛАСТИКУ (КОТУШКИ)"])
    writer.writerow(["Назва", "Ціна (грн/кг)", "Залишок ваги (г)", "Кількість (шт)", "Тип / Слот", "Орієнтовна вартість (грн)"])

    total_spool_grams = 0.0
    total_spool_cost = 0.0
    spool_count = 0

    if spools:
        for s_id, s in spools.items():
            if isinstance(s, dict):
                name = s.get("name", "Котушка")
                price_per_kg = float(s.get("price_per_kg", 650.0))
                remaining_g = float(s.get("remaining_grams", 1000.0))
                qty = max(1, int(s.get("quantity", 1)))
                fil_type = s.get("type", "PLA")
                slot_info = s.get("assigned_slot_key", "Не призначено")

                item_cost = (remaining_g / 1000.0) * price_per_kg * qty
                total_spool_grams += remaining_g * qty
                total_spool_cost += item_cost
                spool_count += qty

                writer.writerow([
                    name,
                    f"{price_per_kg:.2f}",
                    f"{remaining_g:.1f}",
                    qty,
                    f"{fil_type} (Слот {slot_info})",
                    f"{item_cost:.2f}"
                ])
    else:
        writer.writerow(["Немає котушок на складі", "-", "-", "-", "-", "-"])

    writer.writerow(["УСЬОГО ПО КОТУШКАХ:", f"{total_spool_cost:.2f} грн", f"{total_spool_grams:.1f} г", spool_count, "-", f"{total_spool_cost:.2f} грн"])
    writer.writerow([])
    writer.writerow([])

    # Block 2: Printed Parts Warehouse
    writer.writerow(["БЛОК 2: СКЛАД ГОТОВИХ ДЕТАЛЕЙ"])
    writer.writerow(["Назва", "Ціна за 1 шт (грн)", "Вага 1 шт (г)", "Кількість (шт)", "Модель / Пластик", "Загальна вартість (грн)"])

    total_parts_g = 0.0
    total_parts_cost = 0.0
    total_parts_qty = 0

    if parts:
        for p_id, p in parts.items():
            if isinstance(p, dict):
                p_name = p.get("name", "Деталь")
                p_price = float(p.get("price", 0.0) or p.get("cost", 0.0) or 0.0)
                p_weight = float(p.get("weight_g", 0.0) or p.get("weight", 0.0) or 0.0)
                p_qty = max(1, int(p.get("count", 1) or p.get("quantity", 1) or 1))
                p_model = p.get("printer_model", "Unknown")
                p_fil = p.get("filament_type", "PLA")

                item_total_price = p_price * p_qty
                total_parts_g += p_weight * p_qty
                total_parts_cost += item_total_price
                total_parts_qty += p_qty

                writer.writerow([
                    p_name,
                    f"{p_price:.2f}",
                    f"{p_weight:.1f}",
                    p_qty,
                    f"{p_model} ({p_fil})",
                    f"{item_total_price:.2f}"
                ])
    else:
        writer.writerow(["Немає деталей на складі", "-", "-", "-", "-", "-"])

    writer.writerow(["УСЬОГО ПО ДЕТАЛЯХ:", f"{total_parts_cost:.2f} грн", f"{total_parts_g:.1f} г", total_parts_qty, "-", f"{total_parts_cost:.2f} грн"])
    writer.writerow([])
    writer.writerow(["ЗАГАЛЬНИЙ ПІДСУМОК СКЛАДУ:", f"{total_spool_cost + total_parts_cost:.2f} грн", f"{total_spool_grams + total_parts_g:.1f} г", spool_count + total_parts_qty, "-", f"{total_spool_cost + total_parts_cost:.2f} грн"])

    return output.getvalue().encode("utf-8")
