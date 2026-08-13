"""
Unit tests for SensitiveDataFilter log sanitization.
"""
import unittest
import logging
from config import SensitiveDataFilter

class TestLogSanitization(unittest.TestCase):
    def setUp(self):
        self.filter = SensitiveDataFilter()

    def test_telegram_token_sanitization(self):
        raw_msg = "Connecting with token 1234567890:ABCdefGHIjklMNOpqrsTUVwxyz123456789"
        sanitized = self.filter._sanitize(raw_msg)
        self.assertNotIn("1234567890:ABCdefGHIjklMNOpqrsTUVwxyz123456789", sanitized)
        self.assertIn("[TELEGRAM_BOT_TOKEN_MASKED]", sanitized)

    def test_ngrok_token_sanitization(self):
        raw_msg = "Tunnel auth with token 3HgPFyXRmopOKrpbZJX7Pmj0jG0_2VHEVk9uS3FR9rigGnhkM"
        sanitized = self.filter._sanitize(raw_msg)
        self.assertNotIn("3HgPFyXRmopOKrpbZJX7Pmj0jG0_2VHEVk9uS3FR9rigGnhkM", sanitized)
        self.assertIn("[NGROK_AUTHTOKEN_MASKED]", sanitized)

    def test_access_code_sanitization(self):
        raw_msg = 'Printer MQTT connection access_code="SECRET_PASS_123"'
        sanitized = self.filter._sanitize(raw_msg)
        self.assertNotIn("SECRET_PASS_123", sanitized)
        self.assertIn("••••••••", sanitized)

    def test_log_record_filtering(self):
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="User token 9876543210:AAEEFFGGHHIIJJKKLLMMNNOOPPQQRRSSTTU",
            args=(),
            exc_info=None
        )
        self.assertTrue(self.filter.filter(record))
        self.assertNotIn("9876543210:", record.msg)
        self.assertIn("[TELEGRAM_BOT_TOKEN_MASKED]", record.msg)

if __name__ == "__main__":
    unittest.main()
