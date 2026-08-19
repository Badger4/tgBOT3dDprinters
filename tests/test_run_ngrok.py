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

    @patch("pyngrok.ngrok.connect")
    @patch("pyngrok.ngrok.set_auth_token")
    def test_start_ngrok_tunnel(self, mock_set_auth, mock_connect):
        from scripts.run_ngrok import start_ngrok_tunnel

        mock_tunnel = patch("pyngrok.ngrok.NgrokTunnel").start()
        mock_tunnel.public_url = "http://auto.ngrok-free.dev"
        mock_connect.return_value = mock_tunnel

        with patch("scripts.run_ngrok.ENV_PATH", self.env_file):
            tunnel = start_ngrok_tunnel(8080, "mytoken", domain="my-domain.ngrok-free.dev")

        mock_set_auth.assert_called_with("mytoken")
        mock_connect.assert_called_with(8080, "http", domain="my-domain.ngrok-free.dev")
        self.assertEqual(tunnel, mock_tunnel)

    @patch("pyngrok.ngrok.kill")
    @patch("pyngrok.ngrok.disconnect")
    def test_stop_ngrok_tunnel(self, mock_disconnect, mock_kill):
        from scripts.run_ngrok import stop_ngrok_tunnel

        mock_tunnel = patch("pyngrok.ngrok.NgrokTunnel").start()
        mock_tunnel.public_url = "https://auto.ngrok-free.dev"

        stop_ngrok_tunnel(mock_tunnel)

        mock_disconnect.assert_called_with("https://auto.ngrok-free.dev")
        mock_kill.assert_called_once()


if __name__ == "__main__":
    unittest.main()
