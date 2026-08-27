import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch


class TestRunNgrok(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.env_file = Path(self.temp_dir.name) / ".env"
        self.env_file.write_text("WEBAPP_URL=http://localhost:8080\nNGROK_AUTHTOKEN=token123\n", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_update_env_webapp_url_existing(self):
        from scripts.run_ngrok import update_env_webapp_url

        with patch("scripts.run_ngrok.ENV_PATH", self.env_file):
            update_env_webapp_url("https://test.ngrok-free.dev")

        content = self.env_file.read_text(encoding="utf-8")
        self.assertIn("WEBAPP_URL=https://test.ngrok-free.dev", content)
        self.assertIn("NGROK_AUTHTOKEN=token123", content)

    def test_update_env_webapp_url_new_key(self):
        from scripts.run_ngrok import update_env_webapp_url

        self.env_file.write_text("OTHER_KEY=123\n", encoding="utf-8")
        with patch("scripts.run_ngrok.ENV_PATH", self.env_file):
            update_env_webapp_url("https://new.ngrok-free.dev")

        content = self.env_file.read_text(encoding="utf-8")
        self.assertIn("WEBAPP_URL=https://new.ngrok-free.dev", content)
        self.assertIn("OTHER_KEY=123", content)

    def test_start_ngrok_tunnel(self):
        mock_ngrok = MagicMock()
        mock_tunnel = MagicMock()
        mock_tunnel.public_url = "http://auto.ngrok-free.dev"
        mock_ngrok.connect.return_value = mock_tunnel

        mock_modules = {"pyngrok": MagicMock(ngrok=mock_ngrok), "pyngrok.ngrok": mock_ngrok}

        with patch.dict("sys.modules", mock_modules):
            from scripts.run_ngrok import start_ngrok_tunnel

            with patch("scripts.run_ngrok.ENV_PATH", self.env_file):
                tunnel = start_ngrok_tunnel(8080, "mytoken", domain="my-domain.ngrok-free.dev")

        mock_ngrok.set_auth_token.assert_called_with("mytoken")
        mock_ngrok.connect.assert_called_with(8080, "http", domain="my-domain.ngrok-free.dev")
        self.assertEqual(tunnel, mock_tunnel)

    def test_start_ngrok_tunnel_fallback_retry(self):
        mock_ngrok = MagicMock()
        mock_tunnel = MagicMock()
        mock_tunnel.public_url = "http://fallback.ngrok-free.dev"

        def connect_side_effect(port, proto, **kwargs):
            if "domain" in kwargs:
                raise Exception("Domain error")
            return mock_tunnel

        mock_ngrok.connect.side_effect = connect_side_effect

        mock_modules = {"pyngrok": MagicMock(ngrok=mock_ngrok), "pyngrok.ngrok": mock_ngrok}

        with patch.dict("sys.modules", mock_modules):
            from scripts.run_ngrok import start_ngrok_tunnel

            with patch("scripts.run_ngrok.ENV_PATH", self.env_file):
                tunnel = start_ngrok_tunnel(8080, "mytoken", domain="my-domain.ngrok-free.dev")

        self.assertEqual(tunnel, mock_tunnel)

    def test_stop_ngrok_tunnel(self):
        mock_ngrok = MagicMock()
        mock_tunnel = MagicMock()
        mock_tunnel.public_url = "https://auto.ngrok-free.dev"

        mock_modules = {"pyngrok": MagicMock(ngrok=mock_ngrok), "pyngrok.ngrok": mock_ngrok}

        with patch.dict("sys.modules", mock_modules):
            from scripts.run_ngrok import stop_ngrok_tunnel

            stop_ngrok_tunnel(mock_tunnel)

        mock_ngrok.disconnect.assert_called_with("https://auto.ngrok-free.dev")
        mock_ngrok.kill.assert_called_once()


if __name__ == "__main__":
    unittest.main()
