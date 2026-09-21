"""
Domain model and calculation engine for Commercial Pricing Presets.
"""

import math
from typing import Any


def parse_val_or_percent(val_str: str, base_amount: float, hours: float = 1.0) -> tuple[float, bool]:
    """
    Parses a string input that can be either a fixed UAH value ("50", "10.5") or a percentage ("50%", "15.5%").
    Returns (calculated_uah_amount, is_percentage).
    """
    s = str(val_str).strip()
    if s.endswith("%"):
        try:
            pct = float(s[:-1].strip())
            if math.isnan(pct) or math.isinf(pct):
                return 0.0, True
            return round(base_amount * (pct / 100.0), 2), True
        except ValueError:
            return 0.0, True
    else:
        try:
            val = float(s)
            if math.isnan(val) or math.isinf(val):
                return 0.0, False
            return round(val * hours, 2), False
        except ValueError:
            return 0.0, False


def validate_val_or_percent(raw_text: str) -> tuple[bool, str]:
    """
    Validates that raw_text is a valid non-negative number or percentage.
    Accepts: '10', '10.5', '10,5', '15%', '15.5%', '+100%', '10 грн', '10 грн/год', '0'.
    Rejects text containing random letters, multiple signs, negative numbers, etc.
    Returns (is_valid, cleaned_string_or_error_msg).
    """
    s = str(raw_text or "").strip()
    if not s:
        return False, "⚠️ Поле не може бути порожнім."

    is_pct = False
    clean_s = s
    if clean_s.startswith("+"):
        clean_s = clean_s[1:].strip()

    if clean_s.endswith("%"):
        num_part = clean_s[:-1].strip()
        is_pct = True
    else:
        for suffix in ["грн/год", "грн/г", "грн", "uah/h", "uah", "₴/год", "₴"]:
            if clean_s.lower().endswith(suffix):
                clean_s = clean_s[: -len(suffix)].strip()
                break
        num_part = clean_s.strip()

    num_part = num_part.replace(",", ".")
    try:
        val = float(num_part)
        if math.isnan(val) or math.isinf(val):
            return False, "⚠️ Введіть коректне числове значення."
        if val < 0:
            return False, "⚠️ Значення не може бути від'ємним."

        val_str = f"{val:g}"
        if is_pct:
            return True, f"{val_str}%"
        return True, val_str
    except ValueError:
        return False, "⚠️ Введіть тільки число (наприклад <code>10</code>) або відсоток (наприклад <code>15%</code>) без зайвих букв."


def calculate_commercial_price(preset: dict[str, Any], weight_g: float, time_mins: int) -> dict[str, Any]:
    """
    Calculates detailed commercial price breakdown for a print job based on a preset.
    """
    price_per_g = float(preset.get("price_per_g", 0.85))
    elec_rate = float(preset.get("electricity_rate_uah", 4.32))
    power_w = float(preset.get("power_watts", 120.0))
    hours = max(0.1, time_mins / 60.0)

    filament_cost = round(weight_g * price_per_g, 2)
    kwh = (power_w / 1000.0) * hours
    electricity_cost = round(kwh * elec_rate, 2)
    direct_cost = round(filament_cost + electricity_cost, 2)

    depr_str = str(preset.get("depreciation_val", "10"))
    depr_cost, depr_is_pct = parse_val_or_percent(depr_str, direct_cost, hours)

    cons_str = str(preset.get("consumables_val", "5"))
    cons_cost, cons_is_pct = parse_val_or_percent(cons_str, direct_cost, hours)

    cost_before_profit = round(direct_cost + depr_cost + cons_cost, 2)

    profit_str = str(preset.get("profit_val", "100%"))
    profit_cost, profit_is_pct = parse_val_or_percent(
        profit_str, cost_before_profit, hours=1.0
    )  # Fixed UAH profit is not per hour

    total_price = round(cost_before_profit + profit_cost, 2)

    return {
        "preset_name": preset.get("name", "Стандарт"),
        "weight_g": weight_g,
        "time_mins": time_mins,
        "time_hours": round(hours, 2),
        "price_per_g": price_per_g,
        "electricity_rate_uah": elec_rate,
        "power_watts": power_w,
        "filament_cost": filament_cost,
        "electricity_cost": electricity_cost,
        "direct_cost": direct_cost,
        "depreciation_cost": depr_cost,
        "depreciation_str": depr_str,
        "depr_is_pct": depr_is_pct,
        "consumables_cost": cons_cost,
        "consumables_str": cons_str,
        "cons_is_pct": cons_is_pct,
        "cost_before_profit": cost_before_profit,
        "profit_cost": profit_cost,
        "profit_str": profit_str,
        "profit_is_pct": profit_is_pct,
        "profit_amount": profit_cost,
        "total_price": total_price,
    }
