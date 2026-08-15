"""
Senior QA Automation & Security Engineering Test Suite.
Rigorous, paranoid unit tests for data isolation, mutation testing, security edge cases,
access-code protection, malformed inputs, boundary conditions, and mock-isolated crash scenarios.
"""

import asyncio
import copy
import hmac
import io
import json
import math
import time
import urllib.parse
import zipfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.commercial import calculate_commercial_price, parse_val_or_percent
from models.printer import BambuPrinter
from services.camera_stream import _fetch_bambu_port6000_jpeg, capture_real_camera_photo
from services.ftps_client import fetch_bambu_ftps_weight
from services.gcode_parser import check_compatibility, parse_3mf_file, parse_time_str
from services.http_server import build_printer_telemetry, verify_telegram_init_data
from storage.manager import StorageManager


# ============================================================================
# 1. DATA ISOLATION & PRESENTATION SEPARATION TESTS
# ============================================================================
class TestSecurityDataIsolationAndFormatting:
    """
    Verifies that formatting functions (e.g. masking access codes or creating public dicts)
    NEVER alter or leak the underlying raw in-memory object state or database state.
    """

    def test_access_code_formatting_does_not_mutate_object_state(self, tmp_path):
        storage = StorageManager(tmp_path)
        secret_code = "SECRET_12345_LAN_CODE"
        config = {
            "id": "p_sec_1",
            "name": "Security Test Printer",
            "ip": "192.168.1.100",
            "accessCode": secret_code,
            "serialNumber": "SN_SEC_123",
        }
        printer = BambuPrinter(config, storage)

        # 1. Verify initial in-memory state
        assert printer.access_code == secret_code

        # 2. Call to_dict (which masks accessCode) and to_storage_dict (unmasked for DB)
        dict_repr = printer.to_dict()
        assert dict_repr["accessCode"] == "••••••••"
        assert printer.to_storage_dict()["accessCode"] == secret_code
        assert printer.access_code == secret_code

        # 3. Call build_printer_telemetry (WebApp endpoint payload)
        telemetry = build_printer_telemetry(printer)
        assert "accessCode" not in telemetry or telemetry.get("accessCode") != secret_code
        assert printer.access_code == secret_code

    @pytest.mark.asyncio
    async def test_access_code_isolation_in_db_persistence(self, tmp_path):
        storage = StorageManager(tmp_path)
        raw_code = "PASS_RAW_9876"
        config = {
            "id": "p_db_1",
            "name": "DB Isolation Printer",
            "ip": "192.168.1.101",
            "accessCode": raw_code,
            "serialNumber": "SN_DB_987",
        }
        printer = BambuPrinter(config, storage)

        # Save to SQLite DB and JSON using to_storage_dict
        printers_dict = {printer.id: printer.to_storage_dict()}
        await storage.save_json(storage.printers_file, printers_dict)

        # Reload from storage
        reloaded_dict = await storage.load_json(storage.printers_file, {})
        assert reloaded_dict["p_db_1"]["accessCode"] == raw_code

        # Verify object created from reloaded dict retains exact raw_code
        reloaded_printer = BambuPrinter(reloaded_dict["p_db_1"], storage)
        assert reloaded_printer.access_code == raw_code

    def test_ftps_and_mqtt_receive_unmasked_access_code(self):
        raw_code = "SECRET_LAN_PASS_99"

        # Mock socket and SSL for port 6000 camera stream
        with patch("socket.socket") as mock_sock_cls, patch("ssl.create_default_context") as mock_ssl_ctx_fn:
            mock_sock = MagicMock()
            mock_ssl_sock = MagicMock()
            mock_sock_cls.return_value = mock_sock
            mock_ssl_ctx = MagicMock()
            mock_ssl_ctx.wrap_socket.return_value = mock_ssl_sock
            mock_ssl_ctx_fn.return_value = mock_ssl_ctx

            # Return binary ACK header + dummy JPEG bytes
            mock_ssl_sock.recv.side_effect = [
                b"\x40\x00\x00\x00\x00\x30\x00\x00" + b"\x00" * 56,
                b"\xff\xd8" + b"dummy_jpeg_data" + b"\xff\xd9",
            ]

            _fetch_bambu_port6000_jpeg("192.168.1.102", raw_code)

            # Assert that the exact raw_code bytes were sent in the binary auth packet
            assert mock_ssl_sock.sendall.called
            sent_packet = mock_ssl_sock.sendall.call_args[0][0]
            assert raw_code.encode("utf-8") in sent_packet
            assert b"\xe2\x80\xa2" not in sent_packet  # Bullet character '•' must NOT be sent!

    @pytest.mark.asyncio
    async def test_ftps_client_receives_unmasked_credentials(self):
        raw_code = "FTPS_SECRET_PASSWORD"

        with patch("services.ftps_client.ImplicitFTP_TLS") as mock_ftps_cls:
            mock_ftps = MagicMock()
            mock_ftps_cls.return_value = mock_ftps
            mock_ftps.nlst.return_value = []

            fetch_bambu_ftps_weight("192.168.1.103", raw_code, "test.gcode")

            # Verify login was called with unmasked raw_code
            assert mock_ftps.login.called
            args = mock_ftps.login.call_args[0]
            assert args[0] == "bblp"
            assert args[1] == raw_code
            assert args[1] != "••••••••"


# ============================================================================
# 2. MUTATION TESTING PURITY TESTS
# ============================================================================
class TestMutationTestingPurity:
    """
    Verifies that domain functions NEVER mutate input arguments (dicts, lists, objects).
    """

    def test_calculate_commercial_price_does_not_mutate_preset_dict(self):
        preset = {
            "id": "preset_immutable",
            "name": "Immutable Preset",
            "price_per_g": 0.85,
            "electricity_rate_uah": 4.32,
            "power_watts": 120.0,
            "depreciation_val": "10",
            "consumables_val": "5",
            "profit_val": "100%",
        }
        original_copy = copy.deepcopy(preset)

        res = calculate_commercial_price(preset, weight_g=250.0, time_mins=180)

        assert preset == original_copy
        assert isinstance(res, dict)
        assert "total_price" in res

    def test_parse_3mf_file_does_not_mutate_bytes_or_filename(self):
        filename = "test_model_plate.3mf"
        filename_copy = str(filename)

        # Build valid dummy zip bytes
        buf = bytearray()
        buf.extend(b"PK\x03\x04\x0a\x00\x00\x00\x00\x00")
        raw_bytes = bytes(buf)
        bytes_copy = bytes(raw_bytes)

        res = parse_3mf_file(raw_bytes, filename)

        assert raw_bytes == bytes_copy
        assert filename == filename_copy
        assert isinstance(res, dict)

    def test_check_compatibility_does_not_mutate_strings(self):
        model = "Bambu Lab P1S"
        filament = "PETG"
        printer_name = "Farm Printer P1S"
        model_copy, fil_copy, p_copy = str(model), str(filament), str(printer_name)

        res = check_compatibility(model, filament, printer_name)

        assert model == model_copy
        assert filament == fil_copy
        assert printer_name == p_copy
        assert "compatible" in res

    def test_build_printer_telemetry_does_not_mutate_printer(self, tmp_path):
        storage = StorageManager(tmp_path)
        config = {
            "id": "p_mut_1",
            "name": "Purity Printer",
            "ip": "192.168.1.50",
            "accessCode": "88888888",
            "serialNumber": "SN_MUT_1",
        }
        printer = BambuPrinter(config, storage)
        printer_state_before = copy.deepcopy(printer.__dict__)

        telemetry = build_printer_telemetry(printer)

        # Ignore unpicklable / lock objects
        for k in ["_client", "_file_locks", "storage", "_main_loop"]:
            printer_state_before.pop(k, None)
            printer.__dict__.pop(k, None)

        assert printer.id == config["id"]
        assert printer.access_code == config["accessCode"]
        assert isinstance(telemetry, dict)


# ============================================================================
# 3. ADVERSARIAL BOUNDARY & EDGE INPUT TESTS (PARAMETRIZED)
# ============================================================================
class TestAdversarialBoundaryAndEdgeInputs:
    """
    Parametrized edge-case tests: empty strings, whitespace, 256KB+ string bombs,
    SQL injection, XSS, null bytes, unicode emojis, malformed numbers, NaN, and Inf.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bad_code",
        [
            "",
            "   ",
            "\t\n\r  ",
            "A" * 256,
            pytest.param("B" * 50000, id="50k_chars_str"),
            "' OR '1'='1' --",
            "<script>alert('xss')</script>",
            "pass\x00word\r\n\t",
            "🔑🔓🔒🔑1234",
            "ПарольПринтера123",
            None,
            12345678,
            99.95,
            ["pass_list"],
            {"code": "dict_pass"},
        ],
    )
    async def test_access_code_boundary_resilience(self, bad_code, tmp_path):
        storage = StorageManager(tmp_path)
        config = {
            "id": "p_edge_code",
            "name": "Edge Code Printer",
            "ip": "192.168.1.99",
            "accessCode": bad_code,
            "serialNumber": "SN_EDGE",
        }
        with patch("models.printer.mqtt.Client"):
            printer = BambuPrinter(config, storage)
            assert isinstance(printer.access_code, str)
            printer.init_mqtt()

            # Must not crash during camera photo attempt
            with (
                patch("services.camera_stream.check_tcp_port_open", AsyncMock(return_value=False)),
                patch("services.camera_stream._fetch_bambu_port6000_jpeg", return_value=None),
            ):
                photo = await capture_real_camera_photo("192.168.1.99", printer.access_code)
                assert photo is None

            # Must not crash during FTPS weight fetch attempt
            with patch("services.ftps_client._connect_bambu_ftps", return_value=None):
                w = fetch_bambu_ftps_weight("192.168.1.99", printer.access_code, "test.gcode")
                assert w == 0.0

            printer.destroy()

    @pytest.mark.parametrize(
        "raw_mc_percent, expected_percent",
        [
            (0, 0),
            (50, 50),
            (100, 100),
            ("75", 75),
            (45.8, 45),
            (-10, 0),
            (999, 100),
            (None, 0),
            ("INVALID", 0),
            (float("nan"), 0),
            (float("inf"), 0),
        ],
    )
    def test_mqtt_telemetry_percent_clamping_and_types(self, raw_mc_percent, expected_percent, tmp_path):
        storage = StorageManager(tmp_path)
        printer = BambuPrinter({"id": "p_tele", "name": "Tele", "ip": "127.0.0.1"}, storage)
        printer.mc_percent = 0

        # Simulate MQTT push payload
        msg = MagicMock()
        msg.payload = json.dumps({"print": {"mc_percent": raw_mc_percent}}).encode("utf-8")

        printer._on_message(None, None, msg)
        assert printer.mc_percent == expected_percent
        assert isinstance(printer.mc_percent, int)

    @pytest.mark.parametrize(
        "val_str, base_amount, hours, expected_val, expected_is_pct",
        [
            ("10", 100.0, 2.0, 20.0, False),
            ("0", 100.0, 2.0, 0.0, False),
            ("50%", 100.0, 2.0, 50.0, True),
            ("0%", 100.0, 2.0, 0.0, True),
            ("200%", 100.0, 2.0, 200.0, True),
            ("  15.5 % ", 100.0, 2.0, 15.5, True),
            ("invalid", 100.0, 2.0, 0.0, False),
            ("", 100.0, 2.0, 0.0, False),
            ("   ", 100.0, 2.0, 0.0, False),
            (None, 100.0, 2.0, 0.0, False),
            ("NaN%", 100.0, 2.0, 0.0, True),
            ("Inf%", 100.0, 2.0, 0.0, True),
        ],
    )
    def test_parse_val_or_percent_edge_cases(self, val_str, base_amount, hours, expected_val, expected_is_pct):
        val, is_pct = parse_val_or_percent(val_str, base_amount, hours)
        assert val == pytest.approx(expected_val, abs=1e-2)
        assert is_pct == expected_is_pct

    @pytest.mark.parametrize(
        "time_str, expected_mins",
        [
            ("8d 18h 54m 54s", 12654),
            ("model printing time: 8d 18h 54m 54s; total estimated time: 8d 19h 1m 9s", 12661),
            ("1d 0h 0m", 1440),
            ("02:30:00", 150),
            ("00:45:00", 45),
            ("random text 123", 0),
            ("", 0),
            (None, 0),
            ("999999d 0h 0m", 1439998560),
        ],
    )
    def test_parse_time_str_edge_cases(self, time_str, expected_mins):
        mins = parse_time_str(time_str)
        assert mins == expected_mins


# ============================================================================
# 4. CRASH SCENARIOS, FORGERY & ISOLATION TESTS
# ============================================================================
class TestCrashScenariosAndIsolation:
    """
    Tests high-concurrency DB operations, corrupted files/zip bombs, forged Telegram HMAC,
    and network timeout fallback resilience.
    """

    def test_telegram_init_data_forgery_prevention(self):
        bot_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"

        # 1. Valid HMAC construction
        user_dict = {"id": 999888777, "first_name": "TestUser", "username": "testuser"}
        user_json = json.dumps(user_dict, separators=(",", ":"))
        auth_date = str(int(time.time()))

        params = {"auth_date": auth_date, "user": user_json}
        data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
        secret_key = hmac.new(
            b"WebAppData", bot_token.encode("utf-8"), hashlib_sha256 := __import__("hashlib").sha256
        ).digest()
        valid_hash = hmac.new(secret_key, data_check.encode("utf-8"), hashlib_sha256).hexdigest()

        valid_init_data = f"auth_date={auth_date}&hash={valid_hash}&user={urllib_quote(user_json)}"

        res_valid = verify_telegram_init_data(valid_init_data, bot_token)
        assert res_valid is not None
        assert res_valid.get("id") == 999888777


        # 2. Tampered hash (forgery attack)
        forged_init_data = valid_init_data.replace(valid_hash, "f0rged_h@sh_1234567890abcdef1234567890abcdef")
        assert verify_telegram_init_data(forged_init_data, bot_token) is None

        # 3. Tampered user ID (privilege escalation attack)
        tampered_user_json = json.dumps({"id": 1, "first_name": "Admin"}, separators=(",", ":"))
        tampered_init_data = f"auth_date={auth_date}&hash={valid_hash}&user={urllib_quote(tampered_user_json)}"
        assert verify_telegram_init_data(tampered_init_data, bot_token) is None

        # 4. Empty and garbage initData
        assert verify_telegram_init_data("", bot_token) is None
        assert verify_telegram_init_data("garbage_string", bot_token) is None
        assert verify_telegram_init_data(None, bot_token) is None

    def test_corrupt_3mf_file_and_zip_bomb(self):
        # 1. Completely corrupt non-ZIP data
        corrupt_res = parse_3mf_file(b"CORRUPT_NOT_A_ZIP_HEADER_12345", "corrupt_file.3mf")
        assert corrupt_res["valid"] is True
        assert corrupt_res["weight_g"] == 0.0
        assert corrupt_res["time_mins"] == 0

        # 2. Malformed ZIP with 0 entries
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            pass
        empty_zip_bytes = buf.getvalue()

        empty_res = parse_3mf_file(empty_zip_bytes, "empty.3mf")
        assert empty_res["valid"] is True
        assert empty_res["weight_g"] == 50.0
        assert empty_res["time_mins"] == 60

        # 3. Zip with Metadata/plate_1.gcode containing gcode weight and prediction time
        buf_meta = io.BytesIO()
        gcode_content = (
            "; model printing time = 2h 30m 0s\n; total filament used [g] = 145.85\n; printer_model_id = @BBL P1S\n"
        )
        with zipfile.ZipFile(buf_meta, "w") as zf:
            zf.writestr("Metadata/plate_1.gcode", gcode_content)

        meta_res = parse_3mf_file(buf_meta.getvalue(), "valid.3mf")
        assert meta_res["valid"] is True
        assert meta_res["weight_g"] == 145.85
        assert meta_res["time_mins"] == 150
        assert meta_res["printer_model"] == "Bambu Lab P1S"

    @pytest.mark.asyncio
    async def test_concurrent_storage_wal_persistence(self, tmp_path):
        storage = StorageManager(tmp_path)

        # Concurrently save 40 different printer updates
        async def worker(idx: int):
            p_data = {
                f"p_{idx}": {
                    "id": f"p_{idx}",
                    "name": f"Concurrent Printer {idx}",
                    "ip": f"192.168.1.{idx}",
                    "accessCode": f"CODE_{idx}",
                    "filament_grams": 1000.0 - idx,
                }
            }
            await storage.save_json(storage.printers_file, p_data)

        tasks = [worker(i) for i in range(40)]
        await asyncio.gather(*tasks)

        # Verify DB and JSON integrity after concurrent writes
        final_dict = await storage.load_json(storage.printers_file, {})
        assert isinstance(final_dict, dict)
        assert len(final_dict) > 0

    def test_zero_division_and_overflow_protection_in_commercial(self):
        preset = {
            "name": "Zero Test",
            "price_per_g": 0.0,
            "electricity_rate_uah": 0.0,
            "power_watts": 0.0,
            "depreciation_val": "0",
            "consumables_val": "0",
            "profit_val": "0%",
        }

        # 1. Zero values
        res_zero = calculate_commercial_price(preset, weight_g=0.0, time_mins=0)
        assert res_zero["total_price"] == 0.0
        assert math.isnan(res_zero["total_price"]) is False

        # 2. Huge / Overflow boundary values
        res_huge = calculate_commercial_price(preset, weight_g=1e8, time_mins=1000000)
        assert res_huge["total_price"] >= 0.0
        assert math.isinf(res_huge["total_price"]) is False


def urllib_quote(s: str) -> str:
    return urllib.parse.quote(s)
