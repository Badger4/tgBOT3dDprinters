"""
Main Application orchestrating Telegram bot, storage, and printer monitoring.
"""

import asyncio
import gc
import html
import os
import re
import time
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from bot.handlers import setup_routers
from bot.keyboards import get_notification_inline_keyboard
from config import ADMIN_CHAT_ID, STORAGE_DIR, TELEGRAM_BOT_TOKEN, logger
from models.printer import BambuPrinter
from services.mqtt_message_parser import extract_subtask_weight
from storage.manager import StorageManager


class PrinterBotApp:
    def __init__(self) -> None:
        self.storage = StorageManager(STORAGE_DIR)
        self.printers: dict[str, BambuPrinter] = {}
        self.global_settings = {
            "notify_start": True,
            "notify_finish": True,
            "notify_pause": True,
            "notify_time_before_end": 0,
            "notify_filament_low": 0,
        }
        self.bot: Bot | None = None
        self.dp: Dispatcher | None = None
        self.printer_states: dict[str, dict[str, Any]] = {}

    async def initialize(self) -> None:
        printers_data = await self.storage.load_json(self.storage.printers_file, [])
        logger.info(f"Loaded {len(printers_data)} printers from {self.storage.printers_file}")
        running_loop = asyncio.get_running_loop()
        for p_config in printers_data:
            p_obj = BambuPrinter(p_config, self.storage, save_callback=self.save_printers_config)
            p_obj._main_loop = running_loop
            asyncio.create_task(asyncio.to_thread(p_obj.init_mqtt, running_loop))
            self.printers[p_obj.id] = p_obj

        self.global_settings = await self.storage.load_json(self.storage.settings_file, self.global_settings)

    async def save_printers_config(self) -> None:
        printers_list = [p.to_storage_dict() for p in self.printers.values()]
        await self.storage.save_json(self.storage.printers_file, printers_list)

    async def is_user_admin(self, user_id: str) -> bool:
        if str(user_id) == str(ADMIN_CHAT_ID):
            return True
        user = await self.storage.load_user(user_id)
        return bool(user.get("admin", {}).get("access_admin", False))

    async def is_user_approved(self, user_id: str) -> bool:
        if await self.is_user_admin(user_id):
            return True
        user = await self.storage.load_user(user_id)
        return bool(user.get("is_approved", False))

    async def safe_send_message(
        self, chat_id: str, text: str, parse_mode: str | None = ParseMode.MARKDOWN, reply_markup: Any | None = None
    ) -> bool:
        if not self.bot:
            return False
        user = await self.storage.load_user(chat_id)
        if user.get("chat_active") is False:
            return False
        try:
            await self.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode, reply_markup=reply_markup)
            return True
        except Exception as e:
            err_str = str(e).lower()
            if "chat not found" in err_str or "bot was blocked" in err_str or "user is deactivated" in err_str:
                logger.info(f"🚫 Marked chat {chat_id} as inactive ({e})")
                user["chat_active"] = False
                await self.storage.save_user(user)
            else:
                logger.warning(f"Failed sending message to {chat_id}: {e}")
            return False

    async def send_notification(self, event_type: str, text: str, reply_markup: Any | None = None, printer: Any | None = None) -> None:
        if printer and hasattr(printer, "get_notify_dict"):
            p_dict = printer.get_notify_dict()
            if not p_dict.get(event_type, True):
                return
        users = await self.storage.load_all_users()
        for chat_id, udata in users.items():
            if udata.get("chat_active") is False:
                continue
            user_allows = udata.get("notify", {}).get(event_type, True)
            is_app = udata.get("is_approved", False) or await self.is_user_admin(chat_id)
            if user_allows and is_app:
                await self.safe_send_message(chat_id, text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

    async def monitoring_loop(self) -> None:
        logger.info("⚙️ [Monitoring] Background printer monitor loop started!")
        await asyncio.sleep(5)

        main_loop = asyncio.get_running_loop()
        from utils.spool_fingerprint import build_spool_fingerprint, delete_active_print_context, load_active_print_context

        for p_id, p in list(self.printers.items()):
            p._main_loop = main_loop
            if not getattr(p, "storage", None):
                p.storage = self.storage

            # Step 5: Active print context recovery check on bot startup
            saved_context = load_active_print_context(p.id)
            if saved_context and p.gcode_state in ("RUNNING", "PAUSE", "PREPARATION", "PREPARING", "BUILDING"):
                current_fp = build_spool_fingerprint(p)
                if (
                    saved_context.get("subtask_name") == p.subtask_name
                    and saved_context.get("spool_fingerprint") == current_fp
                    and p.layer_num >= saved_context.get("saved_layer", 0)
                ):
                    p._current_job_grams = float(saved_context.get("job_grams", 0.0))
                    p._job_deducted = bool(saved_context.get("job_deducted", True))
                    logger.info(f"✅ Відновлено сесію друку для {p.name} (вага: {p._current_job_grams}g)")
                else:
                    logger.warning(f"⚠️ Контекст друку не збігається для {p.name}, видаляю застарілий запис")
                    delete_active_print_context(p.id)

            self.printer_states[p_id] = {
                "lastState": p.gcode_state,
                "notifiedStart": (p.gcode_state == "RUNNING"),
                "notifiedFinish": (p.gcode_state == "FINISH"),
                "notifiedPause": (p.gcode_state == "PAUSE"),
                "notifiedClearReminder": (p.gcode_state == "FINISH"),
                "notifiedHMS": bool(getattr(p, "hms_errors", None)),
            }

        while True:
            try:
                # Prune removed printer states to prevent memory leaks
                active_ids = set(self.printers.keys())
                self.printer_states = {k: v for k, v in self.printer_states.items() if k in active_ids}

                is_any_printing = False
                for p_id, p in list(self.printers.items()):
                    p._main_loop = main_loop
                    if not getattr(p, "storage", None):
                        p.storage = self.storage

                    is_online = getattr(p, "is_online", True)
                    if not is_online and p.gcode_state not in ["OFFLINE", "UNKNOWN"]:
                        p.gcode_state = "OFFLINE"

                    if p.id not in self.printer_states:
                        self.printer_states[p.id] = {
                            "lastState": p.gcode_state,
                            "notifiedStart": (p.gcode_state == "RUNNING"),
                            "notifiedFinish": (p.gcode_state == "FINISH"),
                            "notifiedPause": (p.gcode_state == "PAUSE"),
                            "notifiedClearReminder": (p.gcode_state == "FINISH"),
                            "notifiedHMS": bool(getattr(p, "hms_errors", None)),
                        }

                    st = self.printer_states[p.id]
                    curr_state = p.gcode_state

                    if curr_state == "RUNNING" and is_online:
                        is_any_printing = True

                    # 1. Start Notification & Filament Warning
                    if curr_state == "RUNNING":
                        used_w = getattr(p, "last_job_grams", 0.0) or getattr(p, "_current_job_grams", 0.0)
                        spool_before = round(p.filament_grams + (used_w if p._job_deducted else 0.0), 2)
                        is_insufficient = used_w > 0 and used_w > spool_before

                        if st["lastState"] != "RUNNING" and p.notify and not st["notifiedStart"]:
                            start_txt = f"🚀 *Принтер {p.name} розпочав друк!*\nХ-хмпф! Не думай, що я буду стежити за ним замість тебе, Бака! 😤\n"
                            if p.subtask_name:
                                start_txt += f"📄 **Модель:** `{p.subtask_name}`\n"
                            start_txt += f"🧵 **Матеріал:** *{p.filament_type}*\n"
                            if used_w > 0:
                                start_txt += f"⚖️ **Вага моделі:** `{used_w}g` (списано)\n"
                            start_txt += f"📦 **Залишок на бабіні:** *{p.filament_grams}g*"

                            if is_insufficient:
                                deficit = round(used_w - spool_before, 2)
                                start_txt += (
                                    f"\n\n🚨 **УВАГА! Недостатньо пластику для друку!**\n"
                                    f"❌ Вага моделі (`{used_w}g`) більша ніж залишок (`{spool_before}g`)!\n"
                                    f"⚠️ Не вистачає ~*{deficit}g*! Не кажи потім, що я не попереджала, Бака!"
                                )
                                st["notifiedInsufficentWarning"] = True

                            await self.send_notification(
                                "start", start_txt, reply_markup=get_notification_inline_keyboard(p.id)
                            )
                            st["notifiedStart"] = True
                            st["notifiedFinish"] = False

                        elif is_insufficient and not st.get("notifiedInsufficentWarning"):
                            deficit = round(used_w - spool_before, 2)
                            warn_txt = (
                                f"🚨 **УВАГА! Недостатньо пластику на принтері {p.name}!**\n"
                                f"📄 **Модель:** `{p.subtask_name or 'Невідомо'}`\n"
                                f"⚖️ **Вага моделі:** `{used_w}g` | 📦 **Залишок:** `{spool_before}g`\n"
                                f"⚠️ Не вистачає ~*{deficit}g* пластику! Іди міняй котушку, Бака! 😤"
                            )
                            await self.send_notification("start", warn_txt)
                            st["notifiedInsufficentWarning"] = True

                        # Advance Time Notification
                        if p.mc_remaining_time > 0:
                            all_users = await self.storage.load_all_users()
                            for chat_id, udata in all_users.items():
                                if udata.get("chat_active") is False:
                                    continue
                                is_app = udata.get("is_approved", False) or await self.is_user_admin(chat_id)
                                if not is_app:
                                    continue
                                u_notify = udata.get("notify", {})
                                min_time = u_notify.get("min_time_to_end", 0)

                                time_key = f"notifiedTimeBeforeEnd_{chat_id}"
                                if min_time > 0 and p.mc_remaining_time <= min_time:
                                    if not st.get(time_key):
                                        time_txt = (
                                            f"⏳ *Гей, Бака! Попереджую заздалегідь!*\n"
                                            f"🖨️ **Принтер:** *{p.name}*\n"
                                            f"📄 **Модель:** `{p.subtask_name or 'Невідомо'}`\n"
                                            f"⏱️ Друк завершиться приблизно через *{p.mc_remaining_time} хв*! Іди вже готуйся! 😤"
                                        )
                                        sent = await self.safe_send_message(
                                            chat_id, time_txt, parse_mode=ParseMode.MARKDOWN
                                        )
                                        if sent:
                                            st[time_key] = True
                                elif p.mc_remaining_time > min_time:
                                    st[time_key] = False

                    # Low Filament Threshold Warning
                    is_printer_online = getattr(p, "online", False) and getattr(p, "is_mqtt_connected", True) and p.gcode_state not in ["OFFLINE", "UNKNOWN"]
                    if is_printer_online and p.filament_grams > 0.0:
                        all_users = await self.storage.load_all_users()
                        for chat_id, udata in all_users.items():
                            if udata.get("chat_active") is False:
                                continue
                            is_app = udata.get("is_approved", False) or await self.is_user_admin(chat_id)
                            if not is_app:
                                continue
                            u_notify = udata.get("notify", {})
                            raw_fil = u_notify.get("min_filament")
                            try:
                                min_fil = float(raw_fil) if raw_fil is not None else 0.0
                            except (ValueError, TypeError):
                                min_fil = 0.0

                            # If threshold is <= 0, warning is disabled for this user
                            if min_fil <= 0.0:
                                continue

                            fil_key = f"notifiedLowFilament_{chat_id}_{p.id}"
                            if p.filament_grams <= min_fil:
                                if not st.get(fil_key):
                                    fil_txt = (
                                        f"📦 *Гей! Автоматичне попередження про малий залишок нитки!*\n"
                                        f"🖨️ **Принтер:** *{p.name}*\n"
                                        f"🧵 **Залишок на бабіні:** *{p.filament_grams}g* (поріг: ≤{int(min_fil)}g)\n"
                                        f"⚠️ На бабіні замало пластику! Підготуй нову котушку, не кажи потім, що я не попереджала, Бака! 😤"
                                    )
                                    sent = await self.safe_send_message(chat_id, fil_txt, parse_mode=ParseMode.MARKDOWN)
                                    if sent:
                                        st[fil_key] = True
                            elif p.filament_grams > min_fil:
                                st[fil_key] = False
                    elif p.filament_grams <= 0.0 or not is_printer_online:
                        # Reset low filament flags if spool was removed or printer is off/disconnected
                        for k in list(st.keys()):
                            if k.startswith("notifiedLowFilament_"):
                                st[k] = False

                    # 2. Pause Notification
                    if curr_state == "PAUSE" and st["lastState"] != "PAUSE":
                        if p.notify and not st["notifiedPause"]:
                            await self.send_notification(
                                "pause",
                                f"⏸️ *Гей! Принтер {p.name} поставлено на паузу!* Іди перевір, що там сталося, Бака! 😤",
                            )
                            st["notifiedPause"] = True

                    # 3. Finish Notification & History Recording
                    if curr_state == "FINISH" and st["lastState"] != "FINISH":
                        if p.notify and not st["notifiedFinish"]:
                            used_w = getattr(p, "last_job_grams", 0.0) or getattr(p, "_current_job_grams", 0.0)
                            finish_txt = f"🎉 *Принтер {p.name} нарешті завершив друк!*\n"
                            if p.subtask_name:
                                finish_txt += f"📄 **Модель:** `{p.subtask_name}`\n"
                            if used_w > 0:
                                finish_txt += f"⚖️ **Списано:** `{used_w}g`\n"
                            finish_txt += f"📦 **Залишок на бабіні:** *{p.get_slot_grams()}g*\nІди й негайно зніми деталь зі столу, скільки можна чекати?! 😤🧹"

                            await self.send_notification("finish", finish_txt)
                            st["notifiedFinish"] = True
                            st["notifiedStart"] = False
                            st["notifiedPause"] = False
                            st["notifiedInsufficentWarning"] = False
                            st["notifiedClearReminder"] = False
                            p.finish_timestamp = time.time()

                            # Record completed print hours
                            job_mins = getattr(p, "last_job_mins", 0) or getattr(p, "mc_remaining_time", 0) or 30
                            p.record_print_hours(job_mins / 60.0)
                            await self.save_printers_config()

                        # Ensure History Entry is Recorded for Slicer / App / Bot prints
                        if not getattr(p, "_history_recorded", False):
                            final_weight = getattr(p, "last_job_grams", 0.0) or getattr(p, "_current_job_grams", 0.0)
                            if final_weight == 0.0 and p.subtask_name:
                                final_weight = extract_subtask_weight(p.subtask_name)

                            if final_weight == 0.0:
                                cache_file = STORAGE_DIR / "last_sliced_weight.json"
                                if cache_file.exists():
                                    try:
                                        c_data = json.loads(cache_file.read_text(encoding="utf-8"))
                                        c_w = float(c_data.get("weight", 0.0))
                                        if c_w > 0:
                                            final_weight = c_w
                                    except Exception:
                                        pass

                            raw_title = getattr(p, "_custom_job_name", None) or str(p.subtask_name or "").strip()
                            raw_title = raw_title.replace("Metadata/", "").replace("metadata/", "").strip()
                            if "." in raw_title and not raw_title.endswith((".3mf", ".gcode")):
                                raw_title = raw_title.rsplit(".", 1)[0]
                            elif raw_title.endswith((".3mf", ".gcode")):
                                raw_title = raw_title.rsplit(".", 1)[0]

                            clean_subtask = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", raw_title).strip()
                            if not clean_subtask or clean_subtask.lower() in ["untitled", "none", "null"] or re.match(r"^[_ -]+$", clean_subtask):
                                clean_subtask = "Деталь 3D"

                            entry = {
                                "timestamp": time.time(),
                                "printer_name": p.name,
                                "subtask_name": clean_subtask,
                                "weight_g": round(float(final_weight), 1),
                                "filament_type": p.filament_type,
                                "note": "Завершено",
                            }
                            await self.storage.add_history_entry(entry)
                            p._history_recorded = True
                            logger.info(f"📜 History entry recorded via monitoring_loop for [{p.name}]: '{clean_subtask}' ({final_weight}g)")

                    # 4. Part Removal Reminder (Strict 15..30 min window)
                    if curr_state == "FINISH" and getattr(p, "finish_timestamp", 0.0) > 0:
                        mins_passed = (time.time() - p.finish_timestamp) / 60.0
                        if 15.0 <= mins_passed <= 30.0:
                            if not st.get("notifiedClearReminder"):
                                rem_txt = f"🔔 *Скільки можна чекати, Бака?!*\nДрук на {p.name} закінчився 15 хв тому!\nНегайно зніми готову деталь зі столу, щоб звільнити принтер! 🧼😤"
                                await self.send_notification("finish", rem_txt)
                                st["notifiedClearReminder"] = True
                        elif mins_passed > 30.0:
                            st["notifiedClearReminder"] = True
                    elif curr_state != "FINISH":
                        st["notifiedClearReminder"] = False

                    # 5. HMS Error Alert
                    if getattr(p, "hms_errors", None) and not st.get("notifiedHMS"):
                        resolved = getattr(p, "hms_resolved", []) or []
                        if resolved:
                            hms_lines = "\n".join([f"• <code>{html.escape(str(h))}</code>" for h in resolved])
                        else:
                            hms_lines = ", ".join([str(e) for e in p.hms_errors])
                        hms_txt = (
                            f"⚡ <b>HMS Помилка на принтері {html.escape(p.name)}!</b>\n\n"
                            f"⚠️ <b>Виявлено збої:</b>\n{hms_lines}\n\n"
                            f"Біжи перевіряй принтер, Бака! 😤"
                        )
                        await self.send_notification("pause", hms_txt)
                        st["notifiedHMS"] = True
                    elif not getattr(p, "hms_errors", None):
                        st["notifiedHMS"] = False

                    # 6. Maintenance & Lubing Alerts (Per-item thresholds)
                    for item_k, item in p.maintenance_items.items():
                        c_hrs = item.get("counter_hours", 0.0)
                        i_hrs = item.get("interval_hours", 100.0)
                        notif_key = f"notifiedMaint_{item_k}"
                        if c_hrs >= i_hrs:
                            if not st.get(notif_key):
                                item_name = item.get("name", "ТО")
                                maint_txt = (
                                    f"🧹 *Час провести {item_name} на принтері {p.name}!*\n"
                                    f"⏱️ Відпрацьовано: *{c_hrs:.1f} годин* (встановлений поріг: {int(i_hrs)} год)!\n"
                                    f"🔧 Проведіть технічне обслуговування, Бака! 🧼✨"
                                )
                                from bot.keyboards import get_maintenance_inline_keyboard

                                await self.send_notification(
                                    "pause",
                                    maint_txt,
                                    reply_markup=get_maintenance_inline_keyboard(p.id, item_k, item_name),
                                )
                                st[notif_key] = True
                        else:
                            st[notif_key] = False

                    st["lastState"] = curr_state

                sleep_interval = 5 if is_any_printing else 15
                gc.collect()
                await asyncio.sleep(sleep_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(10)

    async def run(self) -> None:
        if not TELEGRAM_BOT_TOKEN:
            logger.error("❌ TELEGRAM_BOT_TOKEN is missing! Please set it in your environment or .env file.")
            return

        await self.initialize()

        self.bot = Bot(token=TELEGRAM_BOT_TOKEN)
        self.dp = Dispatcher()
        self.dp["app"] = self

        main_router = setup_routers()
        self.dp.include_router(main_router)

        monitor_task = asyncio.create_task(self.monitoring_loop())

        # Start REST API & Healthcheck HTTP server
        from services.http_server import start_http_server

        await start_http_server(self)

        # Auto-start Ngrok HTTPS tunnel if configured
        ngrok_tunnel = None
        from config import HTTP_PORT, NGROK_AUTHTOKEN, NGROK_DOMAIN

        auto_ngrok = os.getenv("AUTO_NGROK", "true").lower() in ("true", "1", "yes")
        if (NGROK_AUTHTOKEN or auto_ngrok) and not os.getenv("DISABLE_NGROK"):
            try:
                from scripts.run_ngrok import start_ngrok_tunnel

                ngrok_tunnel = start_ngrok_tunnel(HTTP_PORT, NGROK_AUTHTOKEN, NGROK_DOMAIN)
                if ngrok_tunnel:
                    active_url = str(getattr(ngrok_tunnel, "public_url", "")).replace("http://", "https://")
                    if active_url:
                        import config

                        config.WEBAPP_URL = active_url
                        logger.info(f"🌐 [Ngrok] Auto-started HTTPS Tunnel: {active_url}")
            except Exception as e:
                logger.warning(f"⚠️ Could not auto-start Ngrok tunnel: {e}")

        try:
            from aiogram.types import MenuButtonWebApp, WebAppInfo

            from config import WEBAPP_URL as current_webapp_url

            if current_webapp_url:
                await self.bot.set_chat_menu_button(
                    menu_button=MenuButtonWebApp(text="WebApp 🖨️", web_app=WebAppInfo(url=current_webapp_url))
                )
                logger.info(f"📱 WebApp Chat Menu Button configured with URL: {current_webapp_url}")
        except Exception as e:
            logger.warning(f"Could not set chat menu button: {e}")

        try:
            logger.info("🤖 Starting Telegram Bot polling...")
            await self.dp.start_polling(self.bot)
        finally:
            monitor_task.cancel()
            if ngrok_tunnel:
                try:
                    from scripts.run_ngrok import stop_ngrok_tunnel

                    stop_ngrok_tunnel(ngrok_tunnel)
                except Exception as e:
                    logger.warning(f"Error stopping ngrok tunnel on bot shutdown: {e}")
            for p in self.printers.values():
                p.destroy()
            await self.bot.session.close()
