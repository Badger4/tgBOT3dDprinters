"""
Main Application orchestrating Telegram bot, storage, and printer monitoring.
"""
import re
import time
import asyncio
from typing import Dict, Any, Optional
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from config import logger, STORAGE_DIR, TELEGRAM_BOT_TOKEN, ADMIN_CHAT_ID
from storage.manager import StorageManager
from models.printer import BambuPrinter
from bot.handlers import setup_routers

def parse_slot_key_from_text(text: str) -> str:
    clean = text.lower()
    if "a1" in clean or "slot 1" in clean:
        return "0"
    elif "a2" in clean or "slot 2" in clean:
        return "1"
    elif "a3" in clean or "slot 3" in clean:
        return "2"
    elif "a4" in clean or "slot 4" in clean:
        return "3"
    elif "зовнішн" in clean or "vt" in clean:
        return "255"
    return "0"

def extract_filament_type_from_name(name: str) -> str:
    types = [
        "PLA+", "PLA-CF", "PLA", "PETG-CF", "PETG", "PET",
        "ABS-GF", "ABS", "ASA", "TPU-95A", "TPU",
        "PPA-CF", "PA-CF", "PA6-CF", "PA", "PC", "HIPS", "PVA"
    ]
    name_upper = name.upper()
    for t in types:
        pattern = r'(?:\b|_)' + re.escape(t) + r'(?:\b|_)'
        if re.search(pattern, name_upper):
            return t
    words = name.strip().split()
    return words[0] if words else name.strip()

class PrinterBotApp:
    def __init__(self):
        self.storage = StorageManager(STORAGE_DIR)
        self.printers: Dict[str, BambuPrinter] = {}
        self.global_settings = {
            "notify_start": True,
            "notify_finish": True,
            "notify_pause": True,
            "notify_time_before_end": 0,
            "notify_filament_low": 0
        }
        self.bot: Optional[Bot] = None
        self.dp: Optional[Dispatcher] = None
        self.printer_states: Dict[str, Dict[str, Any]] = {}

    async def initialize(self):
        printers_data = await self.storage.load_json(self.storage.printers_file, [])
        logger.info(f"Loaded {len(printers_data)} printers from {self.storage.printers_file}")
        for p_config in printers_data:
            p_obj = BambuPrinter(p_config, self.storage, save_callback=self.save_printers_config)
            p_obj.init_mqtt()
            self.printers[p_obj.id] = p_obj

        self.global_settings = await self.storage.load_json(self.storage.settings_file, self.global_settings)

    async def save_printers_config(self):
        printers_list = [p.to_dict() for p in self.printers.values()]
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

    async def send_notification(self, event_type: str, text: str, reply_markup: Optional[Any] = None):
        users = await self.storage.load_all_users()
        for chat_id, udata in users.items():
            user_allows = udata.get("notify", {}).get(event_type, True)
            is_app = udata.get("is_approved", False) or await self.is_user_admin(chat_id)
            if user_allows and is_app and self.bot:
                try:
                    await self.bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
                except Exception as e:
                    logger.warning(f"Failed sending notification to {chat_id}: {e}")

    async def monitoring_loop(self):
        logger.info("⚙️ [Monitoring] Background printer monitor loop started!")
        await asyncio.sleep(5)

        for p_id, p in list(self.printers.items()):
            self.printer_states[p_id] = {
                "lastState": p.gcode_state,
                "notifiedStart": (p.gcode_state == "RUNNING"),
                "notifiedFinish": (p.gcode_state == "FINISH"),
                "notifiedPause": (p.gcode_state == "PAUSE")
            }

        while True:
            try:
                is_any_printing = False
                for p_id, p in list(self.printers.items()):
                    if p.id not in self.printer_states:
                        self.printer_states[p.id] = {
                            "lastState": p.gcode_state,
                            "notifiedStart": (p.gcode_state == "RUNNING"),
                            "notifiedFinish": (p.gcode_state == "FINISH"),
                            "notifiedPause": (p.gcode_state == "PAUSE")
                        }

                    st = self.printer_states[p.id]
                    curr_state = p.gcode_state

                    if curr_state == "RUNNING":
                        is_any_printing = True

                    # 1. Start Notification & Filament Warning
                    if curr_state == "RUNNING":
                        used_w = getattr(p, "last_job_grams", 0.0) or getattr(p, "_current_job_grams", 0.0)
                        spool_before = round(p.filament_grams + (used_w if p._job_deducted else 0.0), 2)
                        is_insufficient = (used_w > 0 and used_w > spool_before)

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

                            await self.send_notification("start", start_txt)
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
                                        try:
                                            await self.bot.send_message(chat_id=chat_id, text=time_txt, parse_mode=ParseMode.MARKDOWN)
                                            st[time_key] = True
                                        except Exception as e:
                                            logger.warning(f"Failed sending time notification to {chat_id}: {e}")
                                elif p.mc_remaining_time > min_time:
                                    st[time_key] = False

                    # Low Filament Threshold Warning
                    all_users = await self.storage.load_all_users()
                    for chat_id, udata in all_users.items():
                        is_app = udata.get("is_approved", False) or await self.is_user_admin(chat_id)
                        if not is_app:
                            continue
                        u_notify = udata.get("notify", {})
                        raw_fil = u_notify.get("min_filament")
                        min_fil = float(raw_fil) if raw_fil and float(raw_fil) > 0 else 100.0

                        fil_key = f"notifiedLowFilament_{chat_id}_{p.id}"
                        if p.filament_grams <= min_fil:
                            if not st.get(fil_key):
                                fil_txt = (
                                    f"📦 *Гей! Автоматичне попередження про малий залишок нитки!*\n"
                                    f"🖨️ **Принтер:** *{p.name}*\n"
                                    f"🧵 **Залишок на бабіні:** *{p.filament_grams}g* (поріг: ≤{int(min_fil)}g)\n"
                                    f"⚠️ На бабіні замало пластику! Підготуй нову котушку, не кажи потім, що я не попереджала, Бака! 😤"
                                )
                                try:
                                    await self.bot.send_message(chat_id=chat_id, text=fil_txt, parse_mode=ParseMode.MARKDOWN)
                                    st[fil_key] = True
                                except Exception as e:
                                    logger.warning(f"Failed sending low filament notification to {chat_id}: {e}")
                        elif p.filament_grams > min_fil:
                            st[fil_key] = False

                    # 2. Pause Notification
                    if curr_state == "PAUSE" and st["lastState"] != "PAUSE":
                        if p.notify and not st["notifiedPause"]:
                            await self.send_notification("pause", f"⏸️ *Гей! Принтер {p.name} поставлено на паузу!* Іди перевір, що там сталося, Бака! 😤")
                            st["notifiedPause"] = True

                    # 3. Finish Notification
                    if curr_state == "FINISH" and st["lastState"] != "FINISH":
                        if p.notify and not st["notifiedFinish"]:
                            finish_txt = f"🎉 *Принтер {p.name} нарешті завершив друк!*\n📦 **Залишок на бабіні:** *{p.filament_grams}g*\nІди й негайно зніми деталь зі столу, скільки можна чекати?! 😤🧹"
                            await self.send_notification("finish", finish_txt)
                            st["notifiedFinish"] = True
                            st["notifiedStart"] = False
                            st["notifiedPause"] = False
                            st["notifiedInsufficentWarning"] = False

                    # 4. Part Removal Reminder
                    if curr_state == "FINISH" and getattr(p, "finish_timestamp", 0.0) > 0:
                        mins_passed = (time.time() - p.finish_timestamp) / 60.0
                        if mins_passed >= 15 and not st.get("notifiedClearReminder"):
                            rem_txt = f"🔔 *Скільки можна чекати, Бака?!*\nДрук на {p.name} закінчився аж {int(mins_passed)} хв тому!\nНегайно зніми готову деталь зі столу, щоб звільнити принтер! 🧼😤"
                            await self.send_notification("finish", rem_txt)
                            st["notifiedClearReminder"] = True
                    elif curr_state != "FINISH":
                        st["notifiedClearReminder"] = False

                    # 5. HMS Error Alert
                    if getattr(p, "hms_errors", None) and not st.get("notifiedHMS"):
                        err_codes = ", ".join([str(e) for e in p.hms_errors])
                        hms_txt = f"⚡ *HMS Помилка на принтері {p.name}!*\n⚠️ Виявлено коди збоїв: `{err_codes}`\nБіжи перевіряй принтер, Бака! 😤"
                        await self.send_notification("pause", hms_txt)
                        st["notifiedHMS"] = True
                    elif not getattr(p, "hms_errors", None):
                        st["notifiedHMS"] = False

                    st["lastState"] = curr_state

                sleep_interval = 5 if is_any_printing else 15
                await asyncio.sleep(sleep_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(10)

    async def run(self):
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

        try:
            logger.info("🤖 Starting Telegram Bot polling...")
            await self.dp.start_polling(self.bot)
        finally:
            monitor_task.cancel()
            for p in self.printers.values():
                p.destroy()
            await self.bot.session.close()
