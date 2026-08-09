"""
Unit tests for bot router initialization.
"""
import unittest
from aiogram import Router
from bot.handlers import setup_routers

class TestBotRouters(unittest.TestCase):
    def test_setup_routers(self):
        router = setup_routers()
        self.assertIsInstance(router, Router)
        # Check subrouters count (11 subrouters registered)
        self.assertEqual(len(router.sub_routers), 11)

if __name__ == "__main__":
    unittest.main()
