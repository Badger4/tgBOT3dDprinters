"""
Unit tests for REST API & Healthcheck HTTP server.
"""
import unittest
import asyncio
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop
from services.http_server import create_http_app

class DummyApp:
    def __init__(self):
        self.printers = {}

class TestHTTPServer(AioHTTPTestCase):
    async def get_application(self):
        self.dummy_app = DummyApp()
        return create_http_app(self.dummy_app)

    @unittest_run_loop
    async def test_health_endpoint(self):
        resp = await self.client.request("GET", "/health")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("uptime_seconds", data)
        self.assertIn("total_printers", data)

    @unittest_run_loop
    async def test_get_printers_empty(self):
        resp = await self.client.request("GET", "/api/printers")
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertEqual(data, [])
        self.assertIn("X-RateLimit-Limit", resp.headers)
        self.assertIn("X-RateLimit-Remaining", resp.headers)
        self.assertIn("Access-Control-Allow-Origin", resp.headers)

    @unittest_run_loop
    async def test_options_cors_preflight(self):
        # 1. Test allowed Telegram WebApp origin
        headers = {"Origin": "https://web.telegram.org"}
        resp = await self.client.request("OPTIONS", "/api/printers", headers=headers)
        self.assertEqual(resp.status, 204)
        self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "https://web.telegram.org")
        self.assertIn("Access-Control-Allow-Methods", resp.headers)
        self.assertIn("Access-Control-Allow-Headers", resp.headers)

        # 2. Test disallowed origin returns "null"
        bad_headers = {"Origin": "https://malicious-hacker-site.com"}
        bad_resp = await self.client.request("OPTIONS", "/api/printers", headers=bad_headers)
        self.assertEqual(bad_resp.status, 204)
        self.assertEqual(bad_resp.headers.get("Access-Control-Allow-Origin"), "null")

if __name__ == "__main__":
    unittest.main()


