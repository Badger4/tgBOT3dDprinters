"""
Repository for 3D printed parts catalog and 3MF files.
"""

from __future__ import annotations

from typing import Any

from storage.base import BaseStorage


class PartRepository(BaseStorage):
    """Handles async persistence for finished printed parts inventory."""

    async def load_parts(self) -> dict[str, dict[str, Any]]:
        data = await self.load_json(self.parts_file, {})
        if isinstance(data, list):
            return {p["id"]: p for p in data if isinstance(p, dict) and "id" in p}
        if isinstance(data, dict):
            return data
        return {}

    async def save_parts(self, parts: dict[str, dict[str, Any]]) -> bool:
        return await self.save_json(self.parts_file, parts)
