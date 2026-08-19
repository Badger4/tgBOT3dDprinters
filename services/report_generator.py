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
