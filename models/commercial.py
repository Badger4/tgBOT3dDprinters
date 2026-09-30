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


def calculate_commercial_price(
    preset: dict[str, Any],
    weight_g: float,
    time_mins: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Calculates detailed commercial price breakdown for a print job based on a preset and advanced parameters.
    Supports Drugarnya-style advanced features:
    - Production modes: 'single', 'serial', 'test'
    - Pricing modes: 'margin' (percentage), 'ppg' (price per gram)
    - Technological waste/support allowance (waste_pct)
    - Additional hardware & components list (hardware_items)
    - Dual-tariff electricity (Day/Night rates)
    - Machine depreciation (hourly or machine cost / life hours)
    - Operator labor (prep + post processing time)
    - Packaging & logistics
    - Serial batch scaling, plate sharing, and savings analysis
    - Profitability verdict & dominant cost identification
    """
    # 1. Base parameters with fallback to preset or kwargs
    price_per_g = float(kwargs.get("price_per_g") or preset.get("price_per_g", 0.85))
    elec_rate = float(kwargs.get("electricity_rate_uah") or preset.get("electricity_rate_uah", 4.32))
    power_w = float(kwargs.get("power_watts") or preset.get("power_watts", 120.0))
    hours = max(0.1, time_mins / 60.0)

    mode = str(kwargs.get("mode") or preset.get("mode") or "single").lower()
    if mode not in ("single", "serial", "test"):
        mode = "single"

    pricing_mode = str(kwargs.get("pricing_mode") or preset.get("pricing_mode") or "margin").lower()
    if pricing_mode not in ("margin", "ppg"):
        pricing_mode = "margin"

    # Material & Waste
    waste_pct = float(kwargs.get("waste_pct") or preset.get("waste_pct") or 0.0)
    total_weight_g = round(weight_g * (1.0 + max(0.0, waste_pct) / 100.0), 2)
    filament_cost = round(total_weight_g * price_per_g, 2)

    # Electricity (Single or Day/Night tariff)
    tariff_mode = str(kwargs.get("tariff_mode") or preset.get("tariff_mode") or "single").lower()
    if tariff_mode == "daynight":
        elec_day_rate = float(kwargs.get("elec_day_rate", 4.32))
        elec_night_rate = float(kwargs.get("elec_night_rate", 2.16))
        elec_day_hours = float(kwargs.get("elec_day_hours", 0.0))
        elec_night_hours = float(kwargs.get("elec_night_hours", 0.0))

        day_h = min(elec_day_hours, hours)
        night_h = min(elec_night_hours, hours)
        rest_h = max(0.0, hours - day_h - night_h)
        avg_rate = (elec_day_rate + elec_night_rate) / 2.0 if rest_h > 0 else elec_day_rate

        kwh_per_h = power_w / 1000.0
        electricity_cost = round(
            kwh_per_h * (day_h * elec_day_rate + night_h * elec_night_rate + rest_h * avg_rate), 2
        )
    else:
        kwh = (power_w / 1000.0) * hours
        electricity_cost = round(kwh * elec_rate, 2)

    direct_cost = round(filament_cost + electricity_cost, 2)

    # Depreciation
    printer_cost = float(kwargs.get("printer_cost") or preset.get("printer_cost") or 0.0)
    printer_life = float(kwargs.get("printer_life_hours") or preset.get("printer_life_hours") or 0.0)
    depr_str = str(kwargs.get("depreciation_val") or preset.get("depreciation_val", "10"))

    if printer_cost > 0 and printer_life > 0:
        depr_cost = round((printer_cost / printer_life) * hours, 2)
        depr_is_pct = False
        depr_str = f"{printer_cost / printer_life:.2f} грн/год"
    else:
        depr_cost, depr_is_pct = parse_val_or_percent(depr_str, direct_cost, hours)

    # Consumables
    cons_str = str(kwargs.get("consumables_val") or preset.get("consumables_val", "5"))
    cons_cost, cons_is_pct = parse_val_or_percent(cons_str, direct_cost, hours)

    # Hardware & Components (метизи, вплавні гайки, підшипники тощо)
    raw_hw = kwargs.get("hardware_items") or preset.get("hardware_items") or []
    hardware_items: list[dict[str, Any]] = []
    hardware_cost = 0.0
    if isinstance(raw_hw, list):
        for item in raw_hw:
            if isinstance(item, dict):
                h_name = str(item.get("name") or "").strip()
                try:
                    h_price = float(item.get("price") or 0.0)
                    h_qty = float(item.get("qty") or 1.0)
                except (ValueError, TypeError):
                    h_price, h_qty = 0.0, 1.0
                if h_name or h_price > 0:
                    h_total = round(h_price * h_qty, 2)
                    hardware_cost += h_total
                    hardware_items.append({
                        "name": h_name or "Метиз/компонент",
                        "price": h_price,
                        "qty": h_qty,
                        "total": h_total,
                    })
    hardware_cost = round(hardware_cost, 2)

    # Labor (Operator rate, preparation, post-processing)
    labor_rate = float(kwargs.get("labor_rate_uah") or preset.get("labor_rate_uah") or 0.0)
    prep_time = float(kwargs.get("prep_time_mins") or preset.get("prep_time_mins") or 0.0)
    post_time = float(kwargs.get("post_time_mins") or preset.get("post_time_mins") or 0.0)
    labor_hours = (prep_time + post_time) / 60.0
    labor_cost = round(labor_hours * labor_rate, 2)

    # Packaging & Shipping
    packaging_cost = float(kwargs.get("packaging_cost") or preset.get("packaging_cost") or 0.0)
    shipping_cost = float(kwargs.get("shipping_cost") or preset.get("shipping_cost") or 0.0)
    pack_cost = round(packaging_cost + shipping_cost, 2)

    # Base single unit production cost before profit
    base_cost = round(
        direct_cost + depr_cost + cons_cost + hardware_cost + labor_cost + pack_cost, 2
    )

    # Production Mode adjustments:
    cost_per_unit = base_cost
    labor_display = labor_cost
    serial_saving = 0.0
    serial_qty = 1
    serial_per_plate = 1
    test_extra_labor = 0.0

    if mode == "serial":
        serial_qty = max(2, int(kwargs.get("serial_qty") or 10))
        serial_per_plate = max(1, int(kwargs.get("serial_per_plate") or 1))
        serial_post_mins = float(kwargs.get("serial_post_mins") or post_time)
        serial_pack_cost = float(kwargs.get("serial_pack_cost") or packaging_cost)

        # In serial mode:
        # 1. Prep labor is done ONCE for the entire batch and divided by total quantity
        # 2. Post-processing is done per each unit
        prep_h = prep_time / 60.0
        post_h = serial_post_mins / 60.0
        labor_s = round((prep_h / serial_qty + post_h) * labor_rate, 2)

        # 3. Machine time costs (electricity, depreciation, consumables) on the plate are divided among parts on that plate
        elec_per = electricity_cost / serial_per_plate
        depr_per = depr_cost / serial_per_plate
        cons_per = cons_cost / serial_per_plate

        material_per = filament_cost + hardware_cost
        machine_per = elec_per + depr_per + cons_per

        cost_per_unit = round(material_per + machine_per + labor_s + serial_pack_cost, 2)
        labor_display = labor_s

        # Savings compared to separate 1-by-1 prints
        serial_saving = round(max(0.0, (base_cost - cost_per_unit) * serial_qty), 2)

    elif mode == "test":
        # Test prototype carries 50% extra labor for slicing tuning, support adjustments, risk
        test_extra_labor = round(labor_cost * 0.5, 2)
        cost_per_unit = round(base_cost + test_extra_labor, 2)
        labor_display = round(labor_cost + test_extra_labor, 2)

    # Cost before profit is the per-unit production cost
    cost_before_profit = cost_per_unit

    # Pricing & Profit Margin
    price_per_gram = float(kwargs.get("price_per_gram") or 0.0)
    profit_str = str(kwargs.get("profit_val") or preset.get("profit_val", "100%"))

    if pricing_mode == "ppg" and price_per_gram > 0:
        sale_price_per_unit = round(weight_g * price_per_gram, 2)
        profit_cost = round(sale_price_per_unit - cost_per_unit, 2)
        effective_margin_pct = (
            round((profit_cost / cost_per_unit * 100.0), 1) if cost_per_unit > 0 else 0.0
        )
        profit_str = f"{price_per_gram:.2f} грн/г ({effective_margin_pct:.0f}%)"
        profit_is_pct = True
    else:
        # Check if margin_pct override provided in kwargs
        if "margin_pct" in kwargs and kwargs["margin_pct"] is not None:
            try:
                m_pct = float(kwargs["margin_pct"])
                profit_str = f"{m_pct:g}%"
            except (ValueError, TypeError):
                pass

        profit_cost, profit_is_pct = parse_val_or_percent(profit_str, cost_before_profit, hours=1.0)
        sale_price_per_unit = round(cost_before_profit + profit_cost, 2)
        effective_margin_pct = (
            round((profit_cost / cost_before_profit * 100.0), 1) if cost_before_profit > 0 else 0.0
        )

    total_price = sale_price_per_unit

    # Batch totals
    effective_qty = serial_qty if mode == "serial" else 1
    total_batch_cost = round(cost_per_unit * effective_qty, 2)
    total_batch_price = round(sale_price_per_unit * effective_qty, 2)
    total_batch_profit = round(total_batch_price - total_batch_cost, 2)

    # Profitability Verdict & Dominant Expense Driver (Drugarnya Intelligence)
    expenses = [
        ("Матеріал (філамент)", filament_cost),
        ("Електроенергія", electricity_cost),
        ("Амортизація обладнання", depr_cost),
        ("Витратні матеріали", cons_cost),
        ("Фурнітура та метизи", hardware_cost),
        ("Праця оператора", labor_display),
        ("Пакування та логістика", pack_cost),
    ]
    expenses.sort(key=lambda x: x[1], reverse=True)
    biggest_name, biggest_amt = expenses[0]
    biggest_pct = round((biggest_amt / cost_per_unit * 100.0), 1) if cost_per_unit > 0 else 0.0

    if profit_cost < 0:
        verdict_status = "danger"
        verdict_main = f"Збиток {abs(profit_cost):.2f} ₴ з деталі"
        verdict_detail = (
            f"Ціна продажу ({sale_price_per_unit:.2f} ₴) нижча за собівартість ({cost_per_unit:.2f} ₴). "
            f"Найбільша стаття витрат — «{biggest_name}» ({biggest_pct}%). "
            f"Рекомендовано підняти ціну або зменшити витрати."
        )
    elif effective_margin_pct < 15:
        verdict_status = "warning"
        verdict_main = f"Прибуток {profit_cost:.2f} ₴/шт · маржа {effective_margin_pct:.0f}%"
        verdict_detail = (
            f"Маржа ризиковано низька (<15%). Найбільше забирає «{biggest_name}» ({biggest_pct}%). "
            f"За партію чистий заробіток: {total_batch_profit:.2f} ₴."
        )
    else:
        verdict_status = "success"
        verdict_main = f"Прибуток {profit_cost:.2f} ₴/шт · маржа {effective_margin_pct:.0f}%"
        verdict_detail = (
            f"Здорова прибутковість. Найбільша частка витрат — «{biggest_name}» ({biggest_pct}%). "
            f"Чистий прибуток замовлення: {total_batch_profit:.2f} ₴."
        )

    test_min_price = round(cost_per_unit * 1.1, 2) if mode == "test" else sale_price_per_unit

    return {
        "preset_name": preset.get("name", "Стандарт"),
        "mode": mode,
        "pricing_mode": pricing_mode,
        "weight_g": weight_g,
        "waste_pct": waste_pct,
        "total_weight_g": total_weight_g,
        "time_mins": time_mins,
        "time_hours": round(hours, 2),
        "price_per_g": price_per_g,
        "price_per_gram": price_per_gram,
        "electricity_rate_uah": elec_rate,
        "power_watts": power_w,
        "tariff_mode": tariff_mode,
        "filament_cost": filament_cost,
        "electricity_cost": electricity_cost,
        "direct_cost": direct_cost,
        "depreciation_cost": depr_cost,
        "depreciation_str": depr_str,
        "depr_is_pct": depr_is_pct,
        "consumables_cost": cons_cost,
        "consumables_str": cons_str,
        "cons_is_pct": cons_is_pct,
        "hardware_cost": hardware_cost,
        "hardware_items": hardware_items,
        "labor_rate_uah": labor_rate,
        "prep_time_mins": prep_time,
        "post_time_mins": post_time,
        "labor_cost": labor_display,
        "packaging_cost": packaging_cost,
        "shipping_cost": shipping_cost,
        "pack_cost": pack_cost,
        "base_cost": base_cost,
        "cost_per_unit": cost_per_unit,
        "cost_before_profit": cost_before_profit,
        "profit_cost": profit_cost,
        "profit_str": profit_str,
        "profit_is_pct": profit_is_pct,
        "profit_amount": profit_cost,
        "effective_margin_pct": effective_margin_pct,
        "total_price": total_price,
        "sale_price_per_unit": sale_price_per_unit,
        "total_batch_cost": total_batch_cost,
        "total_batch_price": total_batch_price,
        "total_batch_profit": total_batch_profit,
        "serial_qty": serial_qty,
        "serial_per_plate": serial_per_plate,
        "serial_saving": serial_saving,
        "test_extra_labor": test_extra_labor,
        "test_min_price": test_min_price,
        "verdict_status": verdict_status,
        "verdict_main": verdict_main,
        "verdict_detail": verdict_detail,
        "biggest_expense_name": biggest_name,
        "biggest_expense_pct": biggest_pct,
    }

