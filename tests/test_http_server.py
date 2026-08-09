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

if __name__ == "__main__":
    unittest.main()
