"""
Domain model and calculation engine for Commercial Pricing Presets.
"""
from typing import Dict, Any, Tuple

def parse_val_or_percent(val_str: str, base_amount: float, hours: float = 1.0) -> Tuple[float, bool]:
    """
    Parses a string input that can be either a fixed UAH value ("50", "10.5") or a percentage ("50%", "15.5%").
    Returns (calculated_uah_amount, is_percentage).
    """
    s = str(val_str).strip()
    if s.endswith("%"):
        try:
            pct = float(s[:-1].strip())
            return round(base_amount * (pct / 100.0), 2), True
        except ValueError:
            return 0.0, True
    else:
        try:
            val = float(s)
            # If fixed UAH, scale hourly expenses by time hours if hours > 0
            return round(val * hours, 2), False
        except ValueError:
            return 0.0, False

def calculate_commercial_price(preset: Dict[str, Any], weight_g: float, time_mins: int) -> Dict[str, Any]:
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
    profit_cost, profit_is_pct = parse_val_or_percent(profit_str, cost_before_profit, hours=1.0) # Fixed UAH profit is not per hour

    total_price = round(cost_before_profit + profit_cost, 2)

    return {
        "preset_name": preset.get("name", "Стандарт"),
        "weight_g": weight_g,
        "time_mins": time_mins,
        "filament_cost": filament_cost,
        "electricity_cost": electricity_cost,
        "direct_cost": direct_cost,
        "depreciation_cost": depr_cost,
        "depreciation_str": depr_str,
        "consumables_cost": cons_cost,
        "consumables_str": cons_str,
        "cost_before_profit": cost_before_profit,
        "profit_cost": profit_cost,
        "profit_str": profit_str,
        "total_price": total_price
    }
