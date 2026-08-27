"""
Unit tests for SensitiveDataFilter log sanitization.
"""

import logging
import unittest

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
            exc_info=None,
        )
        self.assertTrue(self.filter.filter(record))
        self.assertNotIn("9876543210:", record.msg)
        self.assertIn("[TELEGRAM_BOT_TOKEN_MASKED]", record.msg)

    def test_query_param_sanitization(self):
        raw_msg = (
            "GET /api/login?access_code=SECRET_12345&token=9876543210:AAEEFFGGHHIIJJKKLLMMNNOOPPQQRRSSTTU HTTP/1.1"
        )
        sanitized = self.filter._sanitize(raw_msg)
        self.assertNotIn("SECRET_12345", sanitized)
        self.assertNotIn("9876543210:AAEEFFGGHHIIJJKKLLMMNNOOPPQQRRSSTTU", sanitized)
        self.assertIn("••••••••", sanitized)

    def test_numeric_args_formatting(self):
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Process ID: %d, time: %.2f",
            args=(1234, 1.25),
            exc_info=None,
        )
        self.assertTrue(self.filter.filter(record))
        self.assertEqual(record.args, (1234, 1.25))
        self.assertEqual(record.getMessage(), "Process ID: 1234, time: 1.25")

    def test_dict_args_formatting(self):
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="User %(name)s ID %(id)d",
            args={"name": "Alice", "id": 42},
            exc_info=None,
        )
        self.assertTrue(self.filter.filter(record))
        self.assertEqual(record.args, {"name": "Alice", "id": 42})
        self.assertEqual(record.getMessage(), "User Alice ID 42")

    def test_mixed_tuple_sanitization(self):
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Token %s failed with code %d",
            args=("1234567890:ABCdefGHIjklMNOpqrsTUVwxyz123456789", 401),
            exc_info=None,
        )
        self.assertTrue(self.filter.filter(record))
        self.assertEqual(record.args, ("[TELEGRAM_BOT_TOKEN_MASKED]", 401))
        self.assertEqual(record.getMessage(), "Token [TELEGRAM_BOT_TOKEN_MASKED] failed with code 401")


if __name__ == "__main__":
    unittest.main()
