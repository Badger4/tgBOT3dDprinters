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
            m.setattr("services.http.routes_control.is_admin_request", AsyncMock(return_value=True))
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

    @pytest.mark.asyncio
    async def test_effective_job_grams_and_skip_refund(self):
        printer = BambuPrinter({"id": "p1", "name": "P1S", "serialNumber": "01P00A1234"}, storage=MagicMock())
        printer._client = MagicMock()
        printer._client.is_connected.return_value = True
        printer._client.publish.return_value = MagicMock(rc=0)

        printer.current_job_objects = [
            {"id": "1", "name": "Part 1"},
            {"id": "2", "name": "Part 2"},
            {"id": "3", "name": "Part 3"},
            {"id": "4", "name": "Part 4"},
        ]
        printer.mc_percent = 20
        await printer.skip_objects_async([1, 2])

        eff, saved = printer.calculate_effective_job_grams(100.0)
        # 2 of 4 parts skipped at 20% -> each saved 80% of 25g = 20g -> total saved 40g, effective 60g
        assert saved == 40.0
        assert eff == 60.0
        assert printer.is_all_objects_skipped() is False

        await printer.skip_objects_async([3, 4])
        assert printer.is_all_objects_skipped() is True

    def test_mqtt_s_obj_invalidates_plate_gif_cache(self):
        printer = BambuPrinter({"id": "p1", "name": "P1S", "serialNumber": "01P00A1234"}, storage=MagicMock())
        printer._plate_gif_cache = b"cached_gif_bytes"
        printer.mc_percent = 15

        payload = b'{"print":{"s_obj":[422],"gcode_state":"RUNNING","mc_percent":15}}'
        printer._process_message(payload)

        assert printer.skipped_objects == [422]
        assert printer._plate_gif_cache is None
        assert printer._skipped_at_progress.get(422) == 15

    @pytest.mark.asyncio
    async def test_bot_skip_objects_rbac_and_two_step_confirm(self):
        from bot.handlers.callbacks import handle_callback_query
        from bot.keyboards import build_skip_objects_keyboard

        printer = BambuPrinter({"id": "p1", "name": "P1S", "serialNumber": "01P00A1234"}, storage=MagicMock())
        printer._client = MagicMock()
        printer._client.is_connected.return_value = True
        printer._client.publish.return_value = MagicMock(rc=0)
        printer.current_job_objects = [{"id": "206", "name": "Bracket_Left"}]

        app = MagicMock()
        app.printers = {"p1": printer}
        app.storage = MagicMock()
        app.is_user_admin = AsyncMock(return_value=False)

        # 1. Unapproved user blocked
        app.storage.load_user = AsyncMock(return_value={"is_approved": False})
        cb_unauth = MagicMock()
        cb_unauth.data = "skip_obj_act:p1:206"
        cb_unauth.from_user = MagicMock(id=999)
        cb_unauth.answer = AsyncMock()
        await handle_callback_query(cb_unauth, app)
        assert not printer._client.publish.called
        assert "Доступ заборонено" in cb_unauth.answer.call_args[0][0]

        # 2. Approved user triggers two-step confirmation on skip_obj_act
        app.storage.load_user = AsyncMock(return_value={"is_approved": True})
        cb_act = MagicMock()
        cb_act.data = "skip_obj_act:p1:206"
        cb_act.from_user = MagicMock(id=111)
        cb_act.answer = AsyncMock()
        cb_act.message = MagicMock()
        cb_act.message.edit_reply_markup = AsyncMock()
        await handle_callback_query(cb_act, app)
        assert not printer._client.publish.called
        assert cb_act.message.edit_reply_markup.called

        # 3. Approved user confirms on skip_obj_cfm -> MQTT sent
        cb_cfm = MagicMock()
        cb_cfm.data = "skip_obj_cfm:p1:206"
        cb_cfm.from_user = MagicMock(id=111)
        cb_cfm.answer = AsyncMock()
        cb_cfm.message = MagicMock()
        cb_cfm.message.edit_reply_markup = AsyncMock()
        cb_cfm.message.answer = AsyncMock()
        await handle_callback_query(cb_cfm, app)
        assert printer._client.publish.called
        assert 206 in printer.skipped_objects

        # 4. Keyboard includes stop button when all objects skipped
        kb = build_skip_objects_keyboard(printer)
        all_cb_data = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "skip_obj_stop:p1" in all_cb_data
        assert "skip_obj_ref:p1" in all_cb_data
        assert "skip_obj_cls:p1" in all_cb_data

        # 5. Executing skip_obj_stop calls stop_print() without AttributeError
        cb_stop = MagicMock()
        cb_stop.data = "skip_obj_stop:p1"
        cb_stop.from_user = MagicMock(id=111)
        cb_stop.answer = AsyncMock()
        cb_stop.message = MagicMock()
        cb_stop.message.answer = AsyncMock()
        await handle_callback_query(cb_stop, app)
        cb_stop.answer.assert_called_with("🛑 Друк зупинено!", show_alert=True)

        # 6. Synthetic objects do not trigger false-positive "Stop Print (all skipped)"
        printer.current_job_objects = [{"id": "65537", "name": "Об'єкт #65537", "_synthetic": True}]
        printer.skipped_objects = [65537]
        assert not printer.is_all_objects_skipped()
        kb_syn = build_skip_objects_keyboard(printer)
        syn_cb_data = [btn.callback_data for row in kb_syn.inline_keyboard for btn in row]
        assert "skip_obj_stop:p1" not in syn_cb_data

    def test_render_plate_gif_binary_search(self):
        from utils.image_utils import render_plate_gif
        objs = [
            {"id": "1", "name": "Gear #1", "bbox": [20, 20, 80, 80]},
            {"id": "2", "name": "Bracket #2", "bbox": [120, 120, 180, 180]},
        ]
        gif_bytes = render_plate_gif(objs, bed_size_mm=(256, 256), skipped_ids=[1])
        assert isinstance(gif_bytes, bytes)
        assert len(gif_bytes) > 100
        assert gif_bytes[:6] in (b"GIF87a", b"GIF89a")

    def test_webapp_js_no_1_to_maxid_dom_freeze(self):
        from pathlib import Path
        js_path = Path(__file__).resolve().parent.parent / "webapp" / "static" / "js" / "modules" / "printers.js"
        js_code = js_path.read_text(encoding="utf-8")
        assert "i <= maxId" not in js_code
        assert ".slice(0, 50)" in js_code
        assert ".slice(0, 60)" in js_code
        assert "urlVer" in js_code



