"""
Hardcore unit tests for ftps_client service: weight extraction and FTPS upload routines.
"""

import io
import unittest
import zipfile
from unittest.mock import MagicMock, patch

from services.ftps_client import (
    bambu_storbinary,
    extract_model_weight,
    parse_weight_from_3mf_bytes,
    parse_weight_from_gcode_text,
    upload_3mf_to_bambu,
)


class TestFTPSClient(unittest.TestCase):
    def test_extract_model_weight_dict(self):
        self.assertEqual(extract_model_weight({"filament_weight": 125.4}), 125.4)
        self.assertEqual(extract_model_weight({"nested": {"used_g": 88.2}}), 88.2)
        self.assertEqual(extract_model_weight({"subtask_name": "box_45.5g.3mf"}), 45.5)

    def test_parse_weight_from_gcode_text(self):
        gcode1 = "; total filament used [g] = 134.56\n; header end"
        self.assertEqual(parse_weight_from_gcode_text(gcode1), 134.56)

        gcode2 = "; filament_used_g = 62.1\n"
        self.assertEqual(parse_weight_from_gcode_text(gcode2), 62.1)

    def test_parse_weight_from_3mf_bytes(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("Metadata/slice_info.config", "filament used [g] = 99.8\n")

        weight = parse_weight_from_3mf_bytes(buf.getvalue())
        self.assertEqual(weight, 99.8)

    def test_bambu_storbinary_custom_no_unwrap(self):
        """Ensures custom bambu_storbinary sends TYPE I, transfers data, closes conn without unwrap, and returns voidresp."""
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
        """Ensures fallback to root / occurs on a fresh connection if /cache fails."""
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


if __name__ == "__main__":
    unittest.main()
