"""
Printer maintenance and operational cost calculations mixin.
Provides isolated handling of service intervals, run-hours tracking, and electricity/filament cost estimations.
"""

from __future__ import annotations

import time
from typing import Any

from config import logger


class PrinterMaintenanceMixin:
    """Mixin providing maintenance tracking and job cost calculation for BambuPrinter."""

    total_print_hours: float
    maintenance_hours_counter: float
    maintenance_items: dict[str, dict[str, Any]]
    price_per_kg: float
    power_watts: float
    electricity_rate_uah: float
    name: str

    def _trigger_save(self) -> None:
        pass

    def calculate_job_cost(self, weight_grams: float, print_mins: int = 0) -> dict[str, float]:
        """Calculates cost breakdown: filament cost + electricity cost in UAH."""
        if weight_grams <= 0:
            return {"filament_cost": 0.0, "electricity_cost": 0.0, "total_cost": 0.0}

        filament_cost = (weight_grams / 1000.0) * self.price_per_kg
        effective_mins = print_mins if print_mins > 0 else max(10, int(weight_grams * 2.0))
        electricity_kwh = (self.power_watts / 1000.0) * (effective_mins / 60.0)
        electricity_cost = electricity_kwh * self.electricity_rate_uah

        return {
            "filament_cost": round(filament_cost, 2),
            "electricity_cost": round(electricity_cost, 2),
            "total_cost": round(filament_cost + electricity_cost, 2),
        }

    def record_print_hours(self, hours: float) -> None:
        """Records completed print hours towards total and maintenance counters."""
        if hours <= 0:
            return
        self.total_print_hours = round(self.total_print_hours + hours, 2)
        self.maintenance_hours_counter = round(self.maintenance_hours_counter + hours, 2)
        for k, item in self.maintenance_items.items():
            item["counter_hours"] = round(item.get("counter_hours", 0.0) + hours, 2)
        logger.info(f"⏱️ Updated print hours for [{self.name}]: +{hours:.2f}h (Total: {self.total_print_hours:.1f}h)")
        self._trigger_save()

    def reset_maintenance_counter(self, item_key: str = "rails") -> None:
        """Resets a specific maintenance item's counter after servicing."""
        now_ts = time.time()
        if item_key in ["all", "rails"]:
            self.maintenance_hours_counter = 0.0
            setattr(self, "last_maintenance_timestamp", now_ts)
        if item_key == "all":
            for item in self.maintenance_items.values():
                item["counter_hours"] = 0.0
                item["last_reset"] = now_ts
        elif item_key in self.maintenance_items:
            self.maintenance_items[item_key]["counter_hours"] = 0.0
            self.maintenance_items[item_key]["last_reset"] = now_ts
        logger.info(f"🔧 Reset maintenance counter '{item_key}' for [{self.name}]")
        self._trigger_save()

    def set_maintenance_interval(self, item_key: str, interval_hours: float) -> None:
        """Sets target maintenance interval in hours for a specific item."""
        val = max(1.0, float(interval_hours))
        if item_key in self.maintenance_items:
            self.maintenance_items[item_key]["interval_hours"] = val
        if item_key == "rails":
            setattr(self, "maintenance_interval_hours", int(val))
        logger.info(f"⚙️ Maintenance interval for [{self.name}] ({item_key}) set to {val}h")
        self._trigger_save()
