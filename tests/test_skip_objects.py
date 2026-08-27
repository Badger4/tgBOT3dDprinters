"""
Unit tests for 3MF object parsing, skip_objects_async MQTT command, REST API, and telemetry parsing.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from aiohttp import web

from services.gcode_parser import parse_3mf_file
from services.mqtt_message_parser import parse_mqtt_payload
from models.printer import BambuPrinter
from services.http.routes_control import handle_printer_control


class TestSkipObjects:
    def test_3mf_object_parsing(self):
        # Create minimal 3MF zip with Metadata/slice_info.config
        import io, zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            xml_data = """<?xml version="1.0" encoding="UTF-8"?>
<config>
  <plate>
    <metadata key="index" value="1"/>
    <object id="206" name="Bracket_Left.stl" skipped="false"/>
    <object id="207" name="Bracket_Right.stl" skipped="false"/>
  </plate>
</config>"""
            zf.writestr("Metadata/slice_info.config", xml_data)

        meta = parse_3mf_file(buf.getvalue(), "test_plate.3mf")
        assert len(meta["objects"]) == 2
        assert meta["objects"][0]["id"] == "206"
        assert meta["objects"][0]["name"] == "Bracket_Left.stl"
        assert meta["objects"][1]["id"] == "207"

    def test_mqtt_telemetry_skipped_objects_parsing(self):
        payload = b'{"print":{"s_obj":[206, 207],"gcode_state":"RUNNING"}}'
        parsed = parse_mqtt_payload(payload)
        assert parsed["skipped_objects"] == [206, 207]

    @pytest.mark.asyncio
    async def test_printer_skip_objects_async(self):
        printer = BambuPrinter({"id": "p1", "name": "P1S", "serialNumber": "01P00A1234"}, storage=MagicMock())
        printer._client = MagicMock()
        printer._client.is_connected.return_value = True

        mock_result = MagicMock()
        mock_result.rc = 0
        printer._client.publish.return_value = mock_result

        ok, msg = await printer.skip_objects_async([206])
        assert ok is True
        assert 206 in printer.skipped_objects
        printer._client.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_http_routes_control_skip_objects(self):
        printer = MagicMock()
        printer.id = "p1"
        printer.skip_objects_async = AsyncMock(return_value=(True, "Об'єкт 206 пропущено"))
        printer.skipped_objects = [206]

        req = MagicMock(spec=web.Request)
        req.app = {"app_obj": MagicMock(printers={"p1": printer})}
        req.match_info = {"id": "p1"}
        async def mock_json():
            return {"action": "skip_objects", "obj_ids": [206]}
        req.json = mock_json

        with pytest.MonkeyPatch.context() as m:
            m.setattr("services.http.routes_control.check_auth", AsyncMock(return_value=True))
            res = await handle_printer_control(req)
            assert res.status == 200
