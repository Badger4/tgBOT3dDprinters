"""
Comprehensive automated tests for Parts Warehouse Telegram Bot workflows:
1. Opening parts warehouse via all buttons and aliases.
2. Viewing parts (issue 4 fix: part_view_{p_id} callback).
3. Adding parts wizard (issue 5 fix: full state machine from name to 3mf).
4. Skipping optional fields and cancelling add part.
5. Editing part properties (part_prop_ callbacks, drafts, save, cancel).
6. Deleting parts (from part info and from selection list).
7. Sending parts to print (compatibility checks, printer selection, execution).
8. Searching parts with matching and non-matching queries.
9. Navigation and back buttons.
10. PDF reports triggers.
"""

from datetime import datetime
import html
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Document, Message, PhotoSize, User as TgUser

from bot.handlers import setup_routers
from bot.states import PartCreatingStates, PartEditingStates
from models.printer import BambuPrinter
from storage.manager import StorageManager


class DummyApp:
    def __init__(self, data_dir: Path):
        self.storage = StorageManager(data_dir)
        self.data_dir = str(data_dir)
        self.printers: dict[str, BambuPrinter] = {}
        self.save_printers_config = AsyncMock()

    async def is_user_approved(self, chat_id: str) -> bool:
        return True

    async def is_user_admin(self, chat_id: str) -> bool:
        return True


class MsgResult:
    def __init__(self, answer, photo, doc):
        self.answer = answer
        self.photo = photo
        self.doc = doc

    @property
    def called(self) -> bool:
        return self.answer.called or self.photo.called or self.doc.called

    def all_text(self) -> str:
        texts = []
        for c in self.answer.call_args_list:
            if c.args:
                texts.append(str(c.args[0]))
        for c in self.photo.call_args_list:
            if "caption" in c.kwargs:
                texts.append(str(c.kwargs["caption"]))
        for c in self.doc.call_args_list:
            if "caption" in c.kwargs:
                texts.append(str(c.kwargs["caption"]))
        return " ".join(texts)


class TestPartsComprehensiveWorkflow(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_dir = Path(self.temp_dir_obj.name)

        import config
        self.orig_storage_dir = config.STORAGE_DIR
        config.STORAGE_DIR = self.temp_dir

        self.app = DummyApp(self.temp_dir)
        self.bot = AsyncMock()
        self.bot.get_file = AsyncMock()
        self.bot.download_file = AsyncMock()
        self.app.bot = self.bot
        self.router = setup_routers()

        self.fsm_storage = MemoryStorage()
        self.storage_key = StorageKey(bot_id=1, chat_id=888, user_id=888)
        self.state = FSMContext(storage=self.fsm_storage, key=self.storage_key)

        # Seed user
        await self.app.storage.save_user({
            "user_id": "888",
            "chat_id": "888",
            "username": "tester",
            "state": "idle",
            "language": "uk",
            "context_data": {},
        })

        # Seed printers
        self.p1 = BambuPrinter(
            {
                "id": "p1",
                "name": "Bambu Lab P1S",
                "ip": "192.168.1.100",
                "accessCode": "12345678",
                "serialNumber": "01P1S000000001",
                "printer_model": "P1S",
            },
            storage=self.app.storage,
        )
        self.p1.start_print_job_async = AsyncMock(return_value=(True, "OK"))
        self.app.printers = {"p1": self.p1}

        # Seed test parts
        uploads_dir = self.temp_dir / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        (uploads_dir / "gear.3mf").write_bytes(b"PK\x03\x04DummyGear3MF")

        await self.app.storage.save_parts({
            "part_101": {
                "id": "part_101",
                "name": "Шестерня P1S",
                "count": 5,
                "quantity": 5,
                "image": "",
                "three_mf": "gear.3mf",
                "three_mf_name": "gear.3mf",
                "printer_model": "P1S",
                "filament_type": "PLA",
                "updated_at": time.time(),
            },
            "part_102": {
                "id": "part_102",
                "name": "Ручка шафи",
                "count": 2,
                "quantity": 2,
                "image": "",
                "three_mf": "",
                "three_mf_name": "",
                "printer_model": "Unknown",
                "filament_type": "PETG",
                "updated_at": time.time(),
            },
        })

    async def asyncTearDown(self):
        import config
        config.STORAGE_DIR = self.orig_storage_dir
        self.temp_dir_obj.cleanup()

    async def _send_msg(self, text: str = "", doc_name: str = None, is_photo: bool = False) -> MsgResult:
        tg_user = TgUser(id=888, is_bot=False, first_name="Tester", username="tester")
        chat = Chat(id=888, type="private")
        msg = Message(
            message_id=int(time.time() * 1000) % 100000,
            date=datetime.now(),
            chat=chat,
            from_user=tg_user,
            text=text if not is_photo and not doc_name else (text or None),
        )

        if doc_name:
            msg.document = Document(
                file_id=f"file_id_{doc_name}",
                file_unique_id=f"uniq_{doc_name}",
                file_name=doc_name,
                mime_type="application/octet-stream" if not doc_name.endswith((".jpg", ".png")) else "image/jpeg",
            )
        if is_photo:
            msg.photo = [PhotoSize(file_id="photo_file_id_999", file_unique_id="uniq_photo", width=100, height=100)]

        mock_answer = AsyncMock()
        mock_answer_photo = AsyncMock()
        mock_answer_doc = AsyncMock()
        object.__setattr__(msg, "answer", mock_answer)
        object.__setattr__(msg, "reply", mock_answer)
        object.__setattr__(msg, "answer_photo", mock_answer_photo)
        object.__setattr__(msg, "answer_document", mock_answer_doc)

        raw_st = await self.state.get_state()
        await self.router.propagate_event(
            update_type="message",
            event=msg,
            app=self.app,
            bot=self.bot,
            state=self.state,
            raw_state=raw_st,
        )
        return MsgResult(mock_answer, mock_answer_photo, mock_answer_doc)

    async def _send_cb(self, data: str) -> tuple[MsgResult, MagicMock]:
        tg_user = TgUser(id=888, is_bot=False, first_name="Tester", username="tester")
        chat = Chat(id=888, type="private")
        parent_msg = Message(
            message_id=int(time.time() * 1000) % 100000,
            date=datetime.now(),
            chat=chat,
            from_user=tg_user,
            text="Menu message",
        )
        mock_answer = AsyncMock()
        mock_answer_doc = AsyncMock()
        mock_answer_photo = AsyncMock()
        object.__setattr__(parent_msg, "answer", mock_answer)
        object.__setattr__(parent_msg, "reply", mock_answer)
        object.__setattr__(parent_msg, "answer_document", mock_answer_doc)
        object.__setattr__(parent_msg, "answer_photo", mock_answer_photo)

        cb = CallbackQuery(
            id="cb_id_123",
            from_user=tg_user,
            chat_instance="ci_123",
            message=parent_msg,
            data=data,
        )
        mock_cb_answer = AsyncMock()
        object.__setattr__(cb, "answer", mock_cb_answer)

        raw_st = await self.state.get_state()
        await self.router.propagate_event(
            update_type="callback_query",
            event=cb,
            app=self.app,
            bot=self.bot,
            state=self.state,
            raw_state=raw_st,
        )
        return MsgResult(mock_answer, mock_answer_photo, mock_answer_doc), mock_cb_answer

    async def test_open_parts_warehouse(self):
        """Test opening parts warehouse via various text triggers."""
        ans = await self._send_msg("🧩 Склад деталей")
        self.assertTrue(ans.called)
        self.assertEqual(await self.state.get_state(), PartEditingStates.in_parts_list)

        ans2 = await self._send_msg("3Д")
        self.assertTrue(ans2.called)
        self.assertEqual(await self.state.get_state(), PartEditingStates.in_parts_list)

    async def test_issue_4_click_part_view_card(self):
        """Fix Issue 4: Clicking on a part in parts warehouse displays part card with info and .3mf."""
        # Click on part_101 (has gear.3mf)
        ans, cb_ans = await self._send_cb("part_view_part_101")
        self.assertTrue(cb_ans.called)
        self.assertTrue(ans.called)

        # Must display part name, count and .3mf
        rendered = ans.all_text()
        self.assertIn("Шестерня P1S", rendered)
        self.assertIn("5 шт", rendered)
        self.assertEqual(await self.state.get_state(), PartEditingStates.in_part_info)
        st_data = await self.state.get_data()
        self.assertEqual(st_data.get("selected_part_id"), "part_101")

        # Non-existent part alert
        ans_err, cb_err = await self._send_cb("part_view_non_existent")
        self.assertTrue(cb_err.called)
        self.assertIn("не знайдено", str(cb_err.call_args[0][0]))

    async def test_issue_5_add_part_full_wizard(self):
        """Fix Issue 5: Full add part wizard from name -> photo/skip -> count -> 3mf/skip -> storage save."""
        # 1. Start add part
        ans1 = await self._send_msg("➕ Добавити")
        self.assertTrue(ans1.called)
        self.assertEqual(await self.state.get_state(), PartCreatingStates.name)

        # 2. Empty name validation (spaces only)
        ans_empty = await self._send_msg("   ")
        self.assertTrue(ans_empty.called)
        self.assertIn("Помилка", ans_empty.all_text())
        self.assertEqual(await self.state.get_state(), PartCreatingStates.name)

        # 3. Enter valid name
        ans_name = await self._send_msg("Корпус термометра")
        self.assertTrue(ans_name.called)
        self.assertEqual(await self.state.get_state(), PartCreatingStates.image)
        st_data = await self.state.get_data()
        self.assertEqual(st_data.get("name"), "Корпус термометра")

        # 4. Skip image with "-"
        ans_img = await self._send_msg("-")
        self.assertTrue(ans_img.called)
        self.assertEqual(await self.state.get_state(), PartCreatingStates.count)

        # 5. Invalid count (non-digit)
        ans_bad_cnt = await self._send_msg("десять")
        self.assertTrue(ans_bad_cnt.called)
        self.assertIn("Помилка", ans_bad_cnt.all_text())
        self.assertEqual(await self.state.get_state(), PartCreatingStates.count)

        # 6. Valid count
        ans_cnt = await self._send_msg("15")
        self.assertTrue(ans_cnt.called)
        self.assertEqual(await self.state.get_state(), PartCreatingStates.three_mf)

        # 7. Invalid 3mf (wrong text)
        ans_bad_3mf = await self._send_msg("якийсь файл.stl")
        self.assertTrue(ans_bad_3mf.called)
        self.assertIn("Помилка", ans_bad_3mf.all_text())
        self.assertEqual(await self.state.get_state(), PartCreatingStates.three_mf)

        # 8. Skip 3mf with "-"
        ans_skip_3mf = await self._send_msg("-")
        self.assertTrue(ans_skip_3mf.called)
        self.assertIn("успішно", ans_skip_3mf.all_text().lower())

        # Verify part created in storage
        parts = await self.app.storage.load_parts()
        created = [p for p in parts.values() if p.get("name") == "Корпус термометра"]
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["count"], 15)
        self.assertEqual(created[0]["image"], "")
        self.assertEqual(created[0]["three_mf"], "")

    async def test_add_part_cancel(self):
        """Test cancelling add part wizard at any step via reply buttons, main menu, and callback."""
        # 1. Cancel at Step: name via "❌ Скасувати"
        await self._send_msg("➕ Добавити")
        self.assertEqual(await self.state.get_state(), PartCreatingStates.name)

        ans_cancel = await self._send_msg("❌ Скасувати")
        self.assertTrue(ans_cancel.called)
        self.assertIn("скасовано", ans_cancel.all_text().lower())
        self.assertEqual(await self.state.get_state(), PartEditingStates.in_parts_list)

        # 2. Cancel at Step: image via "⬅️ Назад"
        await self._send_msg("➕ Добавити")
        await self._send_msg("Деталь X")
        self.assertEqual(await self.state.get_state(), PartCreatingStates.image)

        ans_cancel_img = await self._send_msg("⬅️ Назад")
        self.assertTrue(ans_cancel_img.called)
        self.assertIn("скасовано", ans_cancel_img.all_text().lower())
        self.assertEqual(await self.state.get_state(), PartEditingStates.in_parts_list)

        # 3. Cancel at Step: count via "Головне меню"
        await self._send_msg("➕ Добавити")
        await self._send_msg("Деталь Y")
        await self._send_msg("⏩ Пропустити")
        self.assertEqual(await self.state.get_state(), PartCreatingStates.count)

        ans_cancel_menu = await self._send_msg("Головне меню")
        self.assertTrue(ans_cancel_menu.called)
        self.assertIn("скасовано", ans_cancel_menu.all_text().lower())
        self.assertIsNone(await self.state.get_state())

        # 4. Cancel at Step: three_mf via callback query
        await self._send_msg("🧩 Склад деталей")
        await self._send_msg("➕ Добавити")
        await self._send_msg("Деталь Z")
        await self._send_msg("⏩ Пропустити")
        await self._send_msg("5")
        self.assertEqual(await self.state.get_state(), PartCreatingStates.three_mf)

        ans_cb_cancel, _ = await self._send_cb("cancel_part_creation")
        self.assertTrue(ans_cb_cancel.called)
        self.assertEqual(await self.state.get_state(), PartEditingStates.in_parts_list)


    async def test_edit_part_property_workflow(self):
        """Test editing part properties via part_prop_ callbacks, draft updates, save and cancel."""
        # 1. View part_101
        await self._send_cb("part_view_part_101")
        self.assertEqual(await self.state.get_state(), PartEditingStates.in_part_info)

        # 2. Click edit property: name
        ans_prop, cb_prop = await self._send_cb("part_prop_name")
        self.assertTrue(cb_prop.called)
        self.assertEqual(await self.state.get_state(), PartEditingStates.property_edit)

        # 3. Enter new name
        ans_edit_name = await self._send_msg("Шестерня P1S Посилена")
        self.assertTrue(ans_edit_name.called)
        st_data = await self.state.get_data()
        self.assertEqual(st_data["editing_draft"]["name"], "Шестерня P1S Посилена")

        # 4. Save changes
        ans_save = await self._send_msg("💾 Зберегти")
        self.assertTrue(ans_save.called)
        self.assertIn("збережено", ans_save.all_text().lower())
        self.assertEqual(await self.state.get_state(), PartEditingStates.in_part_info)

        parts = await self.app.storage.load_parts()
        self.assertEqual(parts["part_101"]["name"], "Шестерня P1S Посилена")

        # 5. Click edit property: count and then CANCEL
        await self._send_cb("part_prop_count")
        await self._send_msg("999")
        ans_cancel = await self._send_msg("❌ Скасувати редагування")
        self.assertTrue(ans_cancel.called)

        # Verify count did NOT become 999
        parts2 = await self.app.storage.load_parts()
        self.assertEqual(parts2["part_101"]["count"], 5)

    async def test_delete_part_workflow(self):
        """Test deleting part from part card and from delete selection list."""
        # 1. Delete part_102 directly from part card
        await self._send_cb("part_view_part_102")
        ans_del = await self._send_msg("🗑️ Видалити")
        self.assertTrue(ans_del.called)
        self.assertIn("успішно", ans_del.all_text().lower())

        parts = await self.app.storage.load_parts()
        self.assertNotIn("part_102", parts)

        # 2. Delete via selection list when not in card
        await self.state.set_state(PartEditingStates.in_parts_list)
        ans_del_prompt = await self._send_msg("🗑️ Видалити")
        self.assertTrue(ans_del_prompt.called)
        self.assertEqual(await self.state.get_state(), PartEditingStates.select_part_for_delete)

        # Click on part_101 in delete mode
        ans_del_cb, _ = await self._send_cb("part_view_part_101")
        self.assertTrue(ans_del_cb.called)
        parts_after = await self.app.storage.load_parts()
        self.assertNotIn("part_101", parts_after)

    async def test_part_print_trigger_and_compatibility(self):
        """Test sending part to print: printer selection, compatibility check, and execution."""
        # 1. Click print when no 3mf file attached (part_102)
        _, cb_noprint = await self._send_cb("part_print_select_part_102")
        self.assertTrue(cb_noprint.called)
        self.assertIn("не завантажено", str(cb_noprint.call_args[0][0]).lower())

        # 2. Click print for part_101 (has 3mf and compatible P1S)
        ans_pr_sel, cb_pr_sel = await self._send_cb("part_print_select_part_101")
        self.assertTrue(cb_pr_sel.called)
        self.assertTrue(ans_pr_sel.called)
        self.assertIn("Оберіть принтер", ans_pr_sel.all_text())

        # 3. Execute print on P1S
        with patch("services.gcode_parser.check_compatibility", return_value={"compatible": True}):
            ans_exec, cb_exec = await self._send_cb("part_exec_print:part_101:p1")
            self.assertTrue(cb_exec.called)
            self.assertTrue(ans_exec.called)
            self.assertIn("успішно запущено", ans_exec.all_text().lower())
            self.assertTrue(self.p1.start_print_job_async.called)

        # 4. Incompatible print execution
        with patch("services.gcode_parser.check_compatibility", return_value={"compatible": False, "reason": "Wrong model", "reason_type": "PRINTER"}):
            ans_incomp, cb_incomp = await self._send_cb("part_exec_print:part_101:p1")
            self.assertTrue(cb_incomp.called)
            self.assertIn("БЛОКОВАНО", str(cb_incomp.call_args[0][0]))

    async def test_search_parts(self):
        """Test search query matching and no-results fallback."""
        await self.state.set_state(PartEditingStates.in_parts_list)
        ans_s = await self._send_msg("🔍 Пошук")
        self.assertTrue(ans_s.called)
        self.assertEqual(await self.state.get_state(), PartEditingStates.search_query)

        # Matching query
        ans_found = await self._send_msg("Шестерня")
        self.assertTrue(ans_found.called)
        self.assertIn("Знайдено деталей: 1", ans_found.all_text())

        # No results query
        await self.state.set_state(PartEditingStates.in_parts_list)
        await self._send_msg("🔍 Пошук")
        ans_notfound = await self._send_msg("НеіснуючаДеталь12345")
        self.assertTrue(ans_notfound.called)
        self.assertIn("нічого не знайдено", ans_notfound.all_text().lower())

    async def test_navigation_and_reports(self):
        """Test back buttons and PDF report generators."""
        # 1. Back from part info to parts list
        await self._send_cb("part_view_part_101")
        ans_back = await self._send_msg("⬅️ До списку деталей")
        self.assertTrue(ans_back.called)
        self.assertEqual(await self.state.get_state(), PartEditingStates.in_parts_list)

        # 2. Back from parts list to main menu
        ans_main = await self._send_msg("⬅️ Назад")
        self.assertTrue(ans_main.called)
        self.assertIsNone(await self.state.get_state())

        # 3. PDF report buttons
        with patch("services.report_generator.generate_parts_pdf_report", return_value=b"%PDF-test"):
            ans_pdf = await self._send_msg("📊 Звіт деталей (PDF)")
            self.assertTrue(ans_pdf.called)
