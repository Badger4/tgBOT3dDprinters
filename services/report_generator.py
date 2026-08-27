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

    return output.getvalue().encode("utf-8")


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
                total_val = p_price * p_qty

                writer.writerow([
                    part_id,
                    p_name,
                    p_model,
                    p_fil,
                    f"{p_weight:.1f}",
                    f"{p_price:.2f}",
                    p_qty,
                    f"{total_val:.2f}",
                ])

    return output.getvalue().encode("utf-8")


def generate_warehouse_csv_report(spools: dict[str, Any], parts: dict[str, Any] | None = None, report_type: str = "spools") -> bytes:
    """Delegates to spools or parts report generator based on report_type."""
    if report_type == "parts" and parts:
        return generate_parts_csv_report(parts)
    return generate_spools_csv_report(spools)
