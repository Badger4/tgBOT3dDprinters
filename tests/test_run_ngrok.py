import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.run_ngrok import update_env_webapp_url


class TestRunNgrok(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.env_file = Path(self.temp_dir.name) / ".env"
        self.env_file.write_text("WEBAPP_URL=http://localhost:8080\nNGROK_AUTHTOKEN=token123\n", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_update_env_webapp_url_existing(self):
        with patch("scripts.run_ngrok.ENV_PATH", self.env_file):
            update_env_webapp_url("https://test.ngrok-free.dev")

        content = self.env_file.read_text(encoding="utf-8")
        self.assertIn("WEBAPP_URL=https://test.ngrok-free.dev", content)
        self.assertIn("NGROK_AUTHTOKEN=token123", content)

    def test_update_env_webapp_url_new_key(self):
        self.env_file.write_text("OTHER_KEY=123\n", encoding="utf-8")
        with patch("scripts.run_ngrok.ENV_PATH", self.env_file):
            update_env_webapp_url("https://new.ngrok-free.dev")

        content = self.env_file.read_text(encoding="utf-8")
        self.assertIn("WEBAPP_URL=https://new.ngrok-free.dev", content)
        self.assertIn("OTHER_KEY=123", content)


if __name__ == "__main__":
    unittest.main()
