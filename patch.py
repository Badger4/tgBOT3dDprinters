import sys
with open('app.py', 'r', encoding='utf-8') as f:
    c = f.read()

replacements = [
    ('await self.send_notification("finish", notif_text, parse_mode=ParseMode.HTML)', 'await self.send_notification("finish", notif_text, printer=printer, parse_mode=ParseMode.HTML)'),
    ('await self.send_notification("start", prompt_text, reply_markup=kb, parse_mode=ParseMode.HTML)', 'await self.send_notification("start", prompt_text, printer=printer, reply_markup=kb, parse_mode=ParseMode.HTML)'),
    ('await self.send_notification(\n                                "start", start_txt, reply_markup=get_notification_inline_keyboard(p.id)\n                            )', 'await self.send_notification(\n                                "start", start_txt, printer=p, reply_markup=get_notification_inline_keyboard(p.id)\n                            )'),
    ('await self.send_notification("start", warn_txt)', 'await self.send_notification("start", warn_txt, printer=p)'),
    ('await self.send_notification(\n                                        "start",\n                                        f"⏳ *До завершення', 'await self.send_notification(\n                                        "start",\n                                        f"⏳ *До завершення'), # wait, need a better replace for this
    ('await self.send_notification("finish", finish_txt)', 'await self.send_notification("finish", finish_txt, printer=p)'),
    ('await self.send_notification("remind_clear", rem_txt)', 'await self.send_notification("remind_clear", rem_txt, printer=p)')
]

for old, new in replacements:
    c = c.replace(old, new)

# manual regex for multiline pause
import re
c = re.sub(r'(await self\.send_notification\(\s*"pause",\s*err_txt,\s*)reply_markup=', r'\1printer=p,\n                                    reply_markup=', c)
c = re.sub(r'(await self\.send_notification\(\s*"pause",\s*rem_err_txt,\s*)reply_markup=', r'\1printer=p,\n                                    reply_markup=', c)
c = re.sub(r'(await self\.send_notification\(\s*"pause",\s*f"⏸️ \*Нагадування.*?,\s*)reply_markup=', r'\1printer=p,\n                                    reply_markup=', c)
c = re.sub(r'(await self\.send_notification\(\s*"pause",\s*maint_txt,\s*)reply_markup=', r'\1printer=p,\n                                    reply_markup=', c)
c = re.sub(r'(await self\.send_notification\(\s*"pause",\s*f"⏸️ \*Гей!.*?,\s*)reply_markup=', r'\1printer=p,\n                                reply_markup=', c)
c = re.sub(r'(await self\.send_notification\(\s*"start",\s*f"⏳ \*До завершення.*?,\s*)"', r'\1printer=p\n                                    )', c)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(c)
