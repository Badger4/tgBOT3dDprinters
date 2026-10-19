"""
Repository for commercial print presets, print history, and scrap logs.
"""

from __future__ import annotations

import time
from typing import Any

from config import logger
from storage.base import BaseStorage


class CommercialRepository(BaseStorage):
    """Handles async persistence for commercial cost presets and print job history."""

    async def load_presets(self) -> dict[str, dict[str, Any]]:
        data = await self.load_json(self.presets_file, None)
        if data is None or not data:
            legacy_file = self.base_dir / "presets.json"
            legacy_data = await self.load_json(legacy_file, {})
            if legacy_data:
                data = legacy_data
                await self.save_json(self.presets_file, data)
            else:
                data = {}
        if isinstance(data, list):
            return {p["id"]: p for p in data if isinstance(p, dict) and "id" in p}
        if isinstance(data, dict):
            return data
        return {}

    async def save_presets(self, presets: dict[str, dict[str, Any]]) -> bool:
        return await self.save_json(self.presets_file, presets)

    async def load_history(self) -> list[dict[str, Any]]:
        return await self.load_json(self.history_file, [])

    async def add_history_entry(self, entry: dict[str, Any]) -> bool:
        async with self.transaction_lock("history"):
            history = await self.load_history()
            p_name = entry.get("printer_name")
            sub_name = entry.get("subtask_name")
            ts = float(entry.get("timestamp", time.time()))

            for existing in history[-20:]:
                e_p_name = existing.get("printer_name")
                e_sub_name = existing.get("subtask_name")
                e_ts = float(existing.get("timestamp", 0.0))
                if e_p_name == p_name and e_sub_name == sub_name and (abs(ts - e_ts) < 20 or ts == e_ts):
                    logger.info(f"🛡️ Skipped duplicate history entry for [{p_name}] - '{sub_name}'")
                    return True

            history.append(entry)
            if len(history) > 500:
                history = history[-500:]
            return await self.save_json(self.history_file, history)

    async def clear_history(self) -> bool:
        """Clears all print history records."""
        return await self.save_json(self.history_file, [])

    async def delete_history_entry(self, timestamp: float) -> bool:
        """Deletes a single history record matching the given timestamp."""
        async with self.transaction_lock("history"):
            history = await self.load_history()
            filtered = [item for item in history if item.get("timestamp") != timestamp]
            return await self.save_json(self.history_file, filtered)

    async def mark_history_scrap(
        self,
        timestamp: float,
        wasted_weight_g: float,
        reason: str = "Брак",
        refund_grams: float = 0.0,
        printer_id: str | None = None,
        slot_key: str | None = None,
        spool_id: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Marks an existing history record as scrap/failed, updating wasted weight and note.
        Optionally refunds unprinted grams back to the assigned spool.
        """
        target_entry = None
        async with self.transaction_lock("history"):
            history = await self.load_history()
            for item in history:
                try:
                    item_ts = float(item.get("timestamp", 0.0))
                    if abs(item_ts - float(timestamp)) < 0.5:
                        target_entry = item
                        break
                except (ValueError, TypeError):
                    continue

            if not target_entry:
                return None

            target_entry["is_scrap"] = True
            target_entry["scrap_reason"] = reason
            target_entry["wasted_weight_g"] = round(float(wasted_weight_g), 1)
            target_entry["refunded_g"] = round(float(refund_grams), 1)
            target_entry["note"] = f"Брак ❌ ({reason})"

            await self.save_json(self.history_file, history)

        # Handle spool refund if requested
        if refund_grams > 0 and hasattr(self, "load_spools") and hasattr(self, "save_spools"):
            async with self.transaction_lock("spools"):
                spools = await self.load_spools()
                target_spool = None
                if spool_id and spool_id in spools:
                    target_spool = spools[spool_id]
                elif printer_id:
                    for s in spools.values():
                        if s.get("assigned_printer_id") == printer_id:
                            if slot_key is None or str(s.get("assigned_slot_key")) == str(slot_key):
                                target_spool = s
                                break

                if target_spool:
                    prev_w = float(target_spool.get("remaining_grams", 0.0))
                    new_w = round(prev_w + refund_grams, 1)
                    target_spool["remaining_grams"] = new_w
                    await self.save_spools(spools)
                    if hasattr(self, "record_spool_movement"):
                        await self.record_spool_movement(
                            spool_id=target_spool["id"],
                            spool_name=target_spool.get("name", "Spool"),
                            action="scrap_refund",
                            weight_change_g=+refund_grams,
                            prev_weight_g=prev_w,
                            new_weight_g=new_w,
                            reason=f"Повернення невитраченого пластику через брак ({reason})",
                            user="System",
                        )

        return target_entry
