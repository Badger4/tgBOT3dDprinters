"""
Repository for 3D printer fleet persistence.
"""

from __future__ import annotations

from typing import Any

from storage.base import BaseStorage


class PrinterRepository(BaseStorage):
    """Handles async persistence for 3D printer credentials and telemetry."""

    async def load_printers(self) -> dict[str, Any]:
        """Loads all registered 3D printers from storage."""
        data = await self.load_json(self.printers_file, {})
        if isinstance(data, list):
            return {p["id"]: p for p in data if isinstance(p, dict) and "id" in p}
        if isinstance(data, dict):
            return data
        return {}

    async def save_printers(self, printers: dict[str, Any] | list[dict[str, Any]]) -> bool:
        """Saves registered 3D printers configuration to storage."""
        if isinstance(printers, dict):
            printers = list(printers.values())
        return await self.save_json(self.printers_file, printers)
