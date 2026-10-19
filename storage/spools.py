"""
Repository for filament spools and warehouse audit movements.
"""

from __future__ import annotations

import time
from typing import Any

from config import logger
from storage.base import BaseStorage


class SpoolRepository(BaseStorage):
    """Handles async persistence for filament spools and weight audit logs."""

    async def load_spools(self) -> dict[str, dict[str, Any]]:
        default_spools = {
            "spool_1": {
                "id": "spool_1",
                "name": "Sunlu PLA Black",
                "brand": "Sunlu",
                "type": "PLA",
                "color": "Black",
                "remaining_grams": 1000.0,
                "total_grams": 1000.0,
                "price_uah": 650.0,
            },
            "spool_2": {
                "id": "spool_2",
                "name": "eSUN PETG Grey",
                "brand": "eSUN",
                "type": "PETG",
                "color": "Grey",
                "remaining_grams": 1000.0,
                "total_grams": 1000.0,
                "price_uah": 700.0,
            },
        }
        data = await self.load_json(self.spools_file, default_spools)
        raw_dict = {}
        if isinstance(data, list):
            raw_dict = {s["id"]: s for s in data if isinstance(s, dict) and "id" in s}
        elif isinstance(data, dict):
            raw_dict = data
        else:
            raw_dict = default_spools

        # Filter out depleted spools (remaining_grams <= 0.0)
        filtered = {}
        for s_id, s in raw_dict.items():
            if isinstance(s, dict):
                try:
                    rem_val: Any = s.get("remaining_grams", 1000.0)
                    rem_g = float(rem_val)
                except (ValueError, TypeError):
                    rem_g = 1000.0
                if rem_g > 0.0:
                    filtered[s_id] = s
        return filtered

    async def save_spools(self, spools: dict[str, dict[str, Any]]) -> bool:
        filtered = {}
        for s_id, s in spools.items():
            if isinstance(s, dict):
                try:
                    rem_g = float(s.get("remaining_grams", 1000.0))
                except (ValueError, TypeError):
                    rem_g = 1000.0
                if rem_g > 0.0:
                    filtered[s_id] = s
        return await self.save_json(self.spools_file, filtered)

    async def load_spool_movements(self) -> list[dict[str, Any]]:
        """Loads warehouse movement audit history."""
        return await self.load_json(self.movements_file, [])

    async def record_spool_movement(
        self,
        spool_id: str,
        spool_name: str,
        action: str,
        weight_change_g: float,
        prev_weight_g: float,
        new_weight_g: float,
        reason: str = "",
        user: str = "System",
    ) -> dict[str, Any]:
        """Records a spool weight movement / audit log entry."""
        now = time.time()
        entry = {
            "id": f"mov_{int(now * 1000)}",
            "timestamp": now,
            "datetime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
            "spool_id": spool_id,
            "spool_name": spool_name,
            "action": action,  # "print", "refill", "manual_edit", "write_off"
            "weight_change_g": round(float(weight_change_g), 2),
            "prev_weight_g": round(float(prev_weight_g), 2),
            "new_weight_g": round(float(new_weight_g), 2),
            "reason": reason or action,
            "user": user,
        }
        async with self.transaction_lock("movements"):
            movements = await self.load_spool_movements()
            movements.append(entry)
            if len(movements) > 1000:
                movements = movements[-1000:]
            await self.save_json(self.movements_file, movements)
        logger.info(
            f"📦 Audit Log [{action}] for '{spool_name}' ({spool_id}): "
            f"{weight_change_g:+.1f}g -> new: {new_weight_g:.1f}g ({reason})"
        )
        return entry
