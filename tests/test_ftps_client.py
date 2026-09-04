"""
Hardcore unit tests for ftps_client service: weight extraction, FTPS connection, upload, download, and async retries.
"""

import io
import unittest
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from services.ftps_client import (
    _connect_bambu_ftps,
    async_fetch_bambu_ftps_info,
    async_upload_3mf_to_bambu,
    bambu_storbinary,
    extract_model_weight,
    fetch_bambu_ftps_info,
    fetch_bambu_ftps_weight,
    parse_weight_from_3mf_bytes,
    parse_weight_from_gcode_text,
    sanitize_bambu_filename,
    upload_3mf_to_bambu,
    verify_bambu_file_size,
)


class TestFTPSClient(unittest.TestCase):
    def test_extract_model_weight_dict(self):
        self.assertEqual(extract_model_weight({"filament_weight": 125.4}), 125.4)
        self.assertEqual(extract_model_weight({"nested": {"used_g": 88.2}}), 88.2)
        self.assertEqual(extract_model_weight({"subtask_name": "box_45.5g.3mf"}), 45.5)
        self.assertEqual(extract_model_weight({}), 0.0)

    def test_parse_weight_from_gcode_text(self):
        gcode1 = "; total filament used [g] = 134.56\n; header end"
        self.assertEqual(parse_weight_from_gcode_text(gcode1), 134.56)

        gcode2 = "; filament_used_g = 62.1\n"
        self.assertEqual(parse_weight_from_gcode_text(gcode2), 62.1)

        self.assertEqual(parse_weight_from_gcode_text("no weight here"), 0.0)

    def test_parse_weight_from_3mf_bytes(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("Metadata/slice_info.config", "filament used [g] = 99.8\n")

        weight = parse_weight_from_3mf_bytes(buf.getvalue())
        self.assertEqual(weight, 99.8)

        self.assertEqual(parse_weight_from_3mf_bytes(b"invalid zip"), 0.0)

    def test_sanitize_bambu_filename(self):
        self.assertEqual(sanitize_bambu_filename("plate.3mf"), "plate.3mf")
        self.assertEqual(sanitize_bambu_filename("box #1 @home!.gcode"), "box_1_home.gcode")

        # Long filename truncation
        long_name = "extremely_long_filename_for_3d_print_job.3mf"
        sanitized = sanitize_bambu_filename(long_name)
        self.assertTrue(sanitized.startswith("print_"))
        self.assertTrue(sanitized.endswith(".3mf"))

    def test_bambu_storbinary_custom_no_unwrap(self):
        mock_ftps = MagicMock()
        mock_conn = MagicMock()
        mock_ftps.transfercmd.return_value = mock_conn
        mock_ftps.voidresp.return_value = "226 Transfer complete"

        data = b"Hello 3MF World"
        fp = io.BytesIO(data)

        res = bambu_storbinary(mock_ftps, "STOR test.3mf", fp)

        mock_ftps.voidcmd.assert_called_once_with("TYPE I")
        mock_ftps.transfercmd.assert_called_once_with("STOR test.3mf")
        mock_conn.sendall.assert_called_once_with(data)
        mock_conn.close.assert_called_once()
        self.assertEqual(res, "226 Transfer complete")

    @patch("services.ftps_client.ImplicitFTP_TLS")
    def test_connect_bambu_ftps_implicit_success(self, mock_implicit):
        mock_ftps = MagicMock()
        mock_implicit.return_value = mock_ftps

        conn = _connect_bambu_ftps("192.168.1.10", "12345678")
        self.assertEqual(conn, mock_ftps)
        mock_ftps.connect.assert_called_with("192.168.1.10", 990, timeout=10.0)
        mock_ftps.login.assert_called_with("bblp", "12345678")

    @patch("services.ftps_client.BambuFTP_TLS")
    @patch("services.ftps_client.ImplicitFTP_TLS")
    def test_connect_bambu_ftps_explicit_fallback(self, mock_implicit, mock_explicit):
        mock_implicit.side_effect = TimeoutError("Implicit port 990 timed out")
        mock_ftps_bambu = MagicMock()
        mock_explicit.return_value = mock_ftps_bambu

        conn = _connect_bambu_ftps("192.168.1.10", "12345678")
        self.assertEqual(conn, mock_ftps_bambu)
        mock_ftps_bambu.connect.assert_called_with("192.168.1.10", 21, timeout=10.0)

    @patch("services.ftps_client._connect_bambu_ftps")
    def test_upload_3mf_to_bambu_success_cache(self, mock_connect):
        mock_ftps = MagicMock()
        mock_conn = MagicMock()
        mock_ftps.transfercmd.return_value = mock_conn
        mock_ftps.voidresp.return_value = "226 Transfer complete"
        mock_connect.return_value = mock_ftps

        res = upload_3mf_to_bambu("192.168.1.5", "12345678", b"3mf content", "box model.3mf")

        self.assertEqual(res, "cache/box_model.3mf")
        mock_ftps.cwd.assert_called_with("/cache")
        mock_ftps.quit.assert_called_once()

    @patch("services.ftps_client._connect_bambu_ftps")
    def test_upload_3mf_to_bambu_fallback_root(self, mock_connect):
        mock_ftps_cache = MagicMock()
        mock_ftps_cache.cwd.side_effect = Exception("No /cache dir")

        mock_ftps_root = MagicMock()
        mock_conn = MagicMock()
        mock_ftps_root.transfercmd.return_value = mock_conn
        mock_ftps_root.voidresp.return_value = "226 Transfer complete"

        mock_connect.side_effect = [mock_ftps_cache, mock_ftps_root]

        res = upload_3mf_to_bambu("192.168.1.5", "12345678", b"3mf content", "box.3mf")

        self.assertEqual(res, "box.3mf")
        mock_ftps_root.cwd.assert_called_with("/")
        mock_ftps_root.quit.assert_called_once()

    @patch("services.ftps_client._connect_bambu_ftps")
    def test_fetch_bambu_ftps_info_success(self, mock_connect):
        mock_ftps = MagicMock()
        mock_connect.return_value = mock_ftps
        mock_ftps.nlst.side_effect = lambda folder: ["part.3mf"] if folder == "/cache" else []

        # Create valid 3MF zip buffer
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("Metadata/slice_info.config", "<config><printer_model_id>n2s</printer_model_id></config>")
        zip_data = buf.getvalue()

        def retr_side_effect(cmd, callback):
            callback(zip_data)

        mock_ftps.retrbinary.side_effect = retr_side_effect

        info = fetch_bambu_ftps_info("192.168.1.5", "12345678")
        self.assertEqual(info.get("printer_model"), "Bambu Lab A1 mini")

        weight = fetch_bambu_ftps_weight("192.168.1.5", "12345678")
        self.assertIsInstance(weight, float)

    @patch("services.ftps_client._connect_bambu_ftps")
    def test_verify_bambu_file_size(self, mock_connect):
        mock_ftps = MagicMock()
        mock_connect.return_value = mock_ftps
        mock_ftps.size.return_value = 1024

        self.assertTrue(verify_bambu_file_size("192.168.1.5", "12345678", "cache/test.3mf", 1024, max_retries=1))
        self.assertFalse(verify_bambu_file_size("192.168.1.5", "12345678", "cache/test.3mf", 2048, max_retries=1))


@pytest.mark.asyncio
async def test_async_fetch_bambu_ftps_info():
    with patch("services.ftps_client.fetch_bambu_ftps_info") as mock_fetch:
        mock_fetch.return_value = {"printer_model": "Bambu Lab A1"}
        res = await async_fetch_bambu_ftps_info("192.168.1.5", "code123")
        assert res["printer_model"] == "Bambu Lab A1"
        mock_fetch.assert_called_once_with("192.168.1.5", "code123", "")


@pytest.mark.asyncio
async def test_async_upload_3mf_to_bambu():
    with patch("services.ftps_client.upload_3mf_to_bambu") as mock_upload:
        mock_upload.return_value = "cache/part.3mf"
        res = await async_upload_3mf_to_bambu("192.168.1.5", "code123", b"bytes", "part.3mf")
        assert res == "cache/part.3mf"
        mock_upload.assert_called_once_with("192.168.1.5", "code123", b"bytes", "part.3mf")


if __name__ == "__main__":
    unittest.main()
