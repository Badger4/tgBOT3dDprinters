"""
Async unit tests for StorageManager persistence.
"""

import tempfile
import unittest
from pathlib import Path

from storage.manager import StorageManager


class TestStorageManager(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.storage = StorageManager(Path(self.temp_dir.name))

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    async def test_load_and_save_user(self):
        user_id = "12345678"
        user = await self.storage.load_user(user_id)
        self.assertEqual(user["user_id"], user_id)
        self.assertFalse(user["is_approved"])

        user["is_approved"] = True
        user["notify"]["min_time_to_end"] = 10
        await self.storage.save_user(user)

        loaded_user = await self.storage.load_user(user_id)
        self.assertTrue(loaded_user["is_approved"])
        self.assertEqual(loaded_user["notify"]["min_time_to_end"], 10)

    async def test_spools_storage(self):
        spools = await self.storage.load_spools()
        self.assertIn("spool_1", spools)

        spools["spool_1"]["remaining_grams"] = 850.0
        await self.storage.save_spools(spools)

        reloaded = await self.storage.load_spools()
        self.assertEqual(reloaded["spool_1"]["remaining_grams"], 850.0)

    async def test_spool_auto_delete_on_zero_weight(self):
        spools = await self.storage.load_spools()
        self.assertIn("spool_1", spools)

        spools["spool_1"]["remaining_grams"] = 0.0
        await self.storage.save_spools(spools)

        reloaded = await self.storage.load_spools()
        self.assertNotIn("spool_1", reloaded)

    async def test_history_storage(self):
        entry = {
            "timestamp": 1234567890.0,
            "printer_name": "Test P1S",
            "subtask_name": "Test Model",
            "weight_g": 50.0,
            "cost_uah": 35.0,
        }
        await self.storage.add_history_entry(entry)
        history = await self.storage.load_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["subtask_name"], "Test Model")

    async def test_history_deduplication(self):
        entry = {
            "timestamp": 1234567890.0,
            "printer_name": "Test P1S",
            "subtask_name": "Test Model",
            "weight_g": 50.0,
        }
        await self.storage.add_history_entry(entry)

        entry_dup = dict(entry)
        entry_dup["timestamp"] = 1234567900.0
        await self.storage.add_history_entry(entry_dup)

        history = await self.storage.load_history()
        self.assertEqual(len(history), 1)


if __name__ == "__main__":
    unittest.main()
