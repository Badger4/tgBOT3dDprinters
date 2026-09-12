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

    def test_bambu_raw_gcode_parsing(self):
        gcode = """; model label id: 54,105,127,149
; printing object Куб id:0 copy 0
; start printing object, unique label id: 54
M624 CAAAAAAAAAA=
G1 X100 Y100 E1
; stop printing object, unique label id: 54
; printing object Куб id:65537 copy 0
; start printing object, unique label id: 105
M624 CBBBBBBBBBB=
G1 X120 Y100 E1
; stop printing object, unique label id: 105
; total filament used [g] = 15.4
"""
        meta = parse_3mf_file(gcode.encode("utf-8"), "model.gcode")
        assert len(meta["objects"]) == 4
        ids = [o["id"] for o in meta["objects"]]
        assert "54" in ids
        assert "105" in ids
        assert "127" in ids
        assert "149" in ids
        obj_54 = next(o for o in meta["objects"] if o["id"] == "54")
        assert "Куб" in obj_54["name"]

    def test_bambu_plate_json_mesh_ids_do_not_purge_firmware_ids(self):
        import io, zipfile, json
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            plate_json = json.dumps({
                "bbox_objects": [
                    {"id": 437, "name": "Куб", "bbox": [100.0, 70.0, 140.0, 120.0]},
                    {"id": 256, "name": "Куб", "bbox": [110.0, 50.0, 130.0, 70.0]},
                ]
            })
            zf.writestr("Metadata/plate_1.json", plate_json)
            slice_info = """<?xml version="1.0" encoding="UTF-8"?>
<config>
  <plate>
    <metadata key="index" value="1"/>
    <object identify_id="422" name="Куб" skipped="false" />
    <object identify_id="241" name="Куб" skipped="false" />
  </plate>
</config>"""
            zf.writestr("Metadata/slice_info.config", slice_info)

        meta = parse_3mf_file(buf.getvalue(), "plate.3mf")
        assert len(meta["objects"]) == 2
        ids = [o["id"] for o in meta["objects"]]
        assert "422" in ids
        assert "241" in ids
        # Check bboxes were mapped and not purged
        assert "bbox" in meta["objects"][0]
        assert "bbox" in meta["objects"][1]

    @pytest.mark.asyncio
    async def test_cumulative_skip_objects_async(self):
        import json
        printer = BambuPrinter({"id": "p1", "name": "P1S", "serialNumber": "01P00A1234"}, storage=MagicMock())
        printer._client = MagicMock()
        printer._client.is_connected.return_value = True

        mock_result = MagicMock()
        mock_result.rc = 0
        printer._client.publish.return_value = mock_result

        # First skip
        ok1, _ = await printer.skip_objects_async([54])
        assert ok1 is True
        assert printer.skipped_objects == [54]
        call1 = json.loads(printer._client.publish.call_args[0][1])
        assert call1["print"]["obj_list"] == [54]

        # Second skip must be cumulative
        ok2, _ = await printer.skip_objects_async([105])
        assert ok2 is True
        assert printer.skipped_objects == [54, 105]
        call2 = json.loads(printer._client.publish.call_args[0][1])
        assert call2["print"]["obj_list"] == [54, 105]

