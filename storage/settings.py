"""
Repository for global 3D printer farm settings.
"""

from __future__ import annotations

from typing import Any

from storage.base import BaseStorage


class SettingsRepository(BaseStorage):
    """Handles async persistence for farm-wide settings."""

    async def load_settings(self) -> dict[str, Any]:
        """Loads global settings from storage."""
        data = await self.load_json(self.settings_file, {})
        return data if isinstance(data, dict) else {}

    async def save_settings(self, settings: dict[str, Any]) -> bool:
        """Saves global settings to storage."""
        return await self.save_json(self.settings_file, settings)
