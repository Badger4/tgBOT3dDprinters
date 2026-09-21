"""
Parts warehouse management REST API endpoints supporting reference bot fields.
"""

import asyncio
import time
from aiohttp import web

from config import logger
from services.http.auth import check_auth


async def handle_get_parts(request: web.Request) -> web.Response:
    """GET /api/parts - Returns warehouse inventory of printed parts."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    parts = await app_obj.storage.load_parts()
    if not isinstance(parts, dict):
        parts = {}

    import config
    from services.gcode_parser import parse_3mf_file

    modified = False
    for p_id, part in parts.items():
        three_mf = part.get("three_mf")
        three_mf_name = part.get("three_mf_name")
        curr_weight = float(part.get("weight_g") or part.get("weight") or 0.0)
        if (three_mf or three_mf_name) and (not part.get("three_mf_parsed") or curr_weight <= 0.0):
            part["three_mf_parsed"] = True
            for fname in [three_mf, three_mf_name]:
                if not fname:
                    continue
                found = False
                for dir_path in [config.STORAGE_DIR / "uploads", config.STORAGE_DIR / "parts_files"]:
                    sp = dir_path / fname
                    if sp.exists() and sp.is_file():
                        try:
                            content = await asyncio.to_thread(sp.read_bytes)
                            meta = await asyncio.to_thread(parse_3mf_file, content, three_mf_name or sp.name)
                            if meta.get("printer_model") and meta.get("printer_model") != "Unknown":
                                part["printer_model"] = meta["printer_model"]
                                modified = True
                            if meta.get("filament_type"):
                                part["filament_type"] = meta["filament_type"]
                                modified = True
                            if meta.get("nozzle_diameter"):
                                part["nozzle_diameter"] = str(meta["nozzle_diameter"])
                                modified = True
                            if meta.get("weight_g"):
                                w = float(meta["weight_g"])
                                part["weight_g"] = w
                                part["weight"] = w
                                modified = True
                            if meta.get("time_mins"):
                                t_mins = int(meta["time_mins"])
                                part["time_mins"] = t_mins
                                part["print_time"] = t_mins
                                modified = True
                            found = True
                        except Exception:
                            pass
                        break
                if found and float(part.get("weight_g") or 0.0) > 0.0:
                    break

    if modified:
        await app_obj.storage.save_parts(parts)

    return web.json_response(parts)


async def handle_save_part(request: web.Request) -> web.Response:
    """POST /api/parts - Add or update a part in warehouse."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    try:
        data = await request.json()
        part_id = data.get("id") or f"part_{int(time.time() * 1000)}"
        parts = await app_obj.storage.load_parts()
        if not isinstance(parts, dict):
            parts = {}

        existing = parts.get(part_id, {}) if isinstance(parts.get(part_id), dict) else {}
        new_three_mf = str(data.get("three_mf", existing.get("three_mf", ""))).strip()
        old_three_mf = existing.get("old_three_mf", "")

        if new_three_mf and existing.get("three_mf") and new_three_mf != existing.get("three_mf"):
            old_three_mf = existing.get("three_mf")

        cnt = max(0, int(data.get("count", data.get("quantity", existing.get("count", 1)))))

        printer_model = existing.get("printer_model", "Unknown")
        filament_type = existing.get("filament_type", "PLA")
        nozzle_diameter = existing.get("nozzle_diameter", "0.4")
        weight_g = existing.get("weight_g", existing.get("weight", 0.0))
        time_mins = existing.get("time_mins", existing.get("print_time", 0))

        if new_three_mf:
            import config
            from services.gcode_parser import parse_3mf_file
            save_path = config.STORAGE_DIR / "uploads" / new_three_mf
            if not save_path.exists():
                save_path = config.STORAGE_DIR / "parts_files" / new_three_mf
            if save_path.exists():
                content = await asyncio.to_thread(save_path.read_bytes)
                meta = await asyncio.to_thread(parse_3mf_file, content, save_path.name)
                if meta.get("printer_model") and meta.get("printer_model") != "Unknown":
                    printer_model = meta["printer_model"]
                if meta.get("filament_type"):
                    filament_type = meta["filament_type"]
                if meta.get("nozzle_diameter"):
                    nozzle_diameter = str(meta["nozzle_diameter"])
                if meta.get("weight_g"):
                    weight_g = float(meta["weight_g"])
                if meta.get("time_mins"):
                    time_mins = int(meta["time_mins"])

        parts[part_id] = {
            "id": part_id,
            "name": str(data.get("name", existing.get("name", "Деталь"))).strip(),
            "image": str(data.get("image", existing.get("image", ""))).strip(),
            "count": cnt,
            "quantity": cnt,
            "three_mf": new_three_mf,
            "three_mf_parsed": True,
            "printer_model": printer_model,
            "filament_type": filament_type,
            "nozzle_diameter": nozzle_diameter,
            "weight_g": weight_g,
            "weight": weight_g,
            "time_mins": time_mins,
            "print_time": time_mins,
            "updated_at": time.time(),
        }

        await app_obj.storage.save_parts(parts)
        return web.json_response({"status": "ok", "part": parts[part_id]})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


async def handle_download_part_3mf(request: web.Request) -> web.Response:
    """GET /api/parts/{id}/download_3mf - Download the .3mf file of a warehouse part."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    part_id = request.match_info.get("id", "")
    parts = await app_obj.storage.load_parts()
    if not isinstance(parts, dict):
        parts = {}
    part = parts.get(part_id)
    if not part:
        return web.json_response({"error": "Part not found"}, status=404)

    three_mf_id = part.get("three_mf")
    if not three_mf_id:
        return web.json_response({"error": "Файл .3mf відсутній для цієї деталі"}, status=404)

    import config
    file_bytes = None
    filename = part.get("name", "model").replace(" ", "_") + ".3mf"

    # Search local disk uploads or parts_files
    for dir_path in [config.STORAGE_DIR / "uploads", config.STORAGE_DIR / "parts_files"]:
        target_path = dir_path / three_mf_id
        if target_path.exists():
            file_bytes = target_path.read_bytes()
            break

    # If telegram file_id, download via bot
    if not file_bytes and getattr(app_obj, "bot", None) and not three_mf_id.startswith(("/", "\\", "http")):
        try:
            file_info = await app_obj.bot.get_file(three_mf_id)
            file_bytes_io = await app_obj.bot.download_file(file_info.file_path)
            file_bytes = file_bytes_io.read()
        except Exception:
            pass

    if not file_bytes:
        return web.json_response({"error": "Файл .3mf недоступний на сервері"}, status=404)

    return web.Response(
        body=file_bytes,
        headers={
            "Content-Type": "application/octet-stream",
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


async def handle_delete_part(request: web.Request) -> web.Response:
    """DELETE /api/parts/{id} - Remove a part from warehouse."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    part_id = request.match_info.get("id", "")
    parts = await app_obj.storage.load_parts()
    if not isinstance(parts, dict):
        parts = {}
    if part_id in parts:
        del parts[part_id]
        await app_obj.storage.save_parts(parts)
        return web.json_response({"status": "ok"})
    return web.json_response({"error": "Part not found"}, status=404)


async def handle_print_part(request: web.Request) -> web.Response:
    """POST /api/parts/{part_id}/print/{printer_id} - Sends a part model to a printer and starts print."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    part_id = request.match_info.get("part_id", "")
    printer_id = request.match_info.get("printer_id", "")

    parts = await app_obj.storage.load_parts()
    if not isinstance(parts, dict):
        parts = {}
    part = parts.get(part_id)
    if not part:
        return web.json_response({"error": "Part not found"}, status=404)

    printer = app_obj.printers.get(printer_id)
    if not printer:
        return web.json_response({"error": "Printer not found"}, status=404)

    three_mf_id = part.get("three_mf")
    if not three_mf_id:
        return web.json_response({"error": "Для цієї деталі немає збереженого .3mf файлу"}, status=400)

    try:
        try:
            data = await request.json()
        except Exception:
            data = {}
        import config
        from pathlib import Path
        clean_name = three_mf_id.replace("\\", "/").split("/")[-1]
        clean_rel = three_mf_id.lstrip("/").lstrip("\\")

        possible_paths = [
            config.STORAGE_DIR / "uploads" / clean_name,
            config.STORAGE_DIR / "parts_files" / clean_name,
            config.STORAGE_DIR / clean_name,
            config.STORAGE_DIR / clean_rel,
            Path(three_mf_id),
        ]

        file_bytes = None
        for p in possible_paths:
            try:
                if p.exists() and p.is_file():
                    file_bytes = p.read_bytes()
                    break
            except Exception:
                pass

        if not file_bytes and getattr(app_obj, "bot", None) and not three_mf_id.startswith(("/", "\\", "http")):
            file_info = await app_obj.bot.get_file(three_mf_id)
            file_bytes_io = await app_obj.bot.download_file(file_info.file_path)
            file_bytes = file_bytes_io.read()

        if not file_bytes:
            return web.json_response({"error": "Файл .3mf недоступний на сервері"}, status=404)

        # Strict Hardware & Filament Compatibility Validation
        from services.gcode_parser import check_compatibility, get_printer_active_filament
        spools = await app_obj.storage.load_spools() if (app_obj and hasattr(app_obj, "storage") and hasattr(app_obj.storage, "load_spools")) else {}
        active_fil = get_printer_active_filament(printer, spools)

        comp = check_compatibility(
            sliced_model=part.get("printer_model", ""),
            filament_type=part.get("filament_type", ""),
            target_printer_name=printer.name,
            target_filament=active_fil,
            printer=printer,
            tray_info_idx=part.get("tray_info_idx", ""),
            color=part.get("color", ""),
            filament_name=part.get("filament_name", ""),
            nozzle_diameter=part.get("nozzle_diameter"),
        )
        if not comp.get("compatible"):
            reason = comp.get("reason", "🛑 Несумісний принтер або пластик!")
            logger.warning(f"⛔ Blocked incompatible print of part '{part.get('name')}' on '{printer.name}': {reason}")
            return web.json_response({"error": f"🛑 Друк заблоковано: {reason}"}, status=400)

        filename = part.get("three_mf_name") or f"{part.get('name', 'model')}.3mf"
        part_title = part.get("name") or filename
        chosen_slot = data.get("ams_slot") or comp.get("matched_ams_slot")
        ok, msg = await printer.start_print_job_async(file_bytes, filename, part_name=part_title, ams_slot=chosen_slot)
        if ok:
            printer._is_printing = True
            printer._was_running = True
            printer._job_started_from_app = True
            return web.json_response({"status": "ok", "message": msg})
        else:
            return web.json_response({"error": msg}, status=500)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_export_parts_csv(request: web.Request) -> web.Response:
    """GET /api/parts/export_csv - Download PDF report of printed parts warehouse."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        app_obj = request.app["app_obj"]
        parts = await app_obj.storage.load_parts()

        from services.report_generator import generate_parts_pdf_report
        pdf_bytes = generate_parts_pdf_report(parts)

        headers = {
            "Content-Disposition": 'attachment; filename="parts_report.pdf"; filename*=UTF-8\'\'parts_report.pdf',
            "Content-Type": "application/pdf",
        }
        return web.Response(body=pdf_bytes, headers=headers)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_export_parts_pdf(request: web.Request) -> web.Response:
    """GET /api/parts/export_pdf - Generates clean printable HTML/PDF report of parts warehouse."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        import time
        app_obj = request.app["app_obj"]
        parts = await app_obj.storage.load_parts()

        date_str = time.strftime("%Y-%m-%d %H:%M")

        total_parts = 0
        total_weight_g = 0.0
        total_val_uah = 0.0

        rows_html = ""
        if parts and isinstance(parts, dict):
            for p_id, p in parts.items():
                if isinstance(p, dict):
                    name = p.get("name", "Деталь")
                    model = p.get("printer_model", "-")
                    fil_type = p.get("filament_type", "PLA")
                    weight_g = float(p.get("weight_g", 0.0) or p.get("weight", 0.0) or 0.0)
                    price = float(p.get("price", 0.0) or p.get("cost", 0.0) or 0.0)
                    qty = max(1, int(p.get("count", 1) or p.get("quantity", 1) or 1))

                    row_val = price * qty
                    total_parts += qty
                    total_weight_g += weight_g * qty
                    total_val_uah += row_val

                    rows_html += f"""
                    <tr>
                        <td style="font-weight:600;">{name}</td>
                        <td>{model}</td>
                        <td style="text-align:center;">{fil_type}</td>
                        <td style="text-align:right;">{weight_g:.1f}г</td>
                        <td style="text-align:center;">{qty}</td>
                        <td style="text-align:right;">{price:.2f} ₴</td>
                        <td style="text-align:right; font-weight:700; color:#4f46e5;">{row_val:.2f} ₴</td>
                    </tr>
                    """

        if request.query.get("send_telegram") == "1":
            from services.report_generator import generate_parts_pdf_report
            from services.http.routes_settings import get_authenticated_user_id
            from aiogram.types import BufferedInputFile
            from aiogram.enums import ParseMode
            import config

            bot = getattr(app_obj, "bot", None)
            if not bot:
                return web.json_response({"error": "Бот зараз не активний"}, status=503)

            u_id = get_authenticated_user_id(request) or getattr(config, "ADMIN_CHAT_ID", None)
            if not u_id:
                return web.json_response({"error": "Користувача не ідентифіковано"}, status=400)

            pdf_bytes = generate_parts_pdf_report(parts)
            fname = f"parts_inventory_{int(time.time())}.pdf"
            doc_file = BufferedInputFile(pdf_bytes, filename=fname)
            cap = (
                f"🧩 <b>Звіт складу готових деталей</b>\n"
                f"Деталей усього: <b>{total_parts} шт</b>\n"
                f"Загальна вага: <b>{(total_weight_g/1000.0):.2f} кг</b>\n"
                f"Загальна вартість: <b>{total_val_uah:.2f} ₴</b>"
            )
            try:
                await bot.send_document(chat_id=int(u_id), document=doc_file, caption=cap, parse_mode=ParseMode.HTML)
                return web.json_response({"status": "ok", "message": "PDF успішно надіслано в чат!"})
            except Exception as ex:
                from config import logger
                logger.error(f"Failed to send parts PDF to user {u_id}: {ex}")
                return web.json_response({"error": f"Помилка відправки в Telegram: {ex}"}, status=500)

        req_format = request.query.get("format", "").lower()
        if req_format != "html":
            from services.report_generator import generate_parts_pdf_report
            pdf_bytes = generate_parts_pdf_report(parts)
            fname = f"parts_inventory_{int(time.time())}.pdf"
            disp_type = "inline" if request.query.get("inline") == "1" else "attachment"
            return web.Response(
                body=pdf_bytes,
                headers={
                    "Content-Type": "application/pdf",
                    "Content-Disposition": f'{disp_type}; filename="{fname}"; filename*=UTF-8\'\'{fname}',
                },
            )

        import urllib.parse
        q_dict = dict(request.query)
        q_dict["format"] = "pdf"
        pdf_download_url = f"/api/parts/export_pdf?{urllib.parse.urlencode(q_dict)}"

        html_content = f"""<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Звіт складу деталей</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
    @page {{ size: A4 portrait; margin: 8mm; }}
    * {{ box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; background: #f8fafc; color: #0f172a; margin: 0; padding: 12px; font-size: 11px; }}
    .container {{ width: 100%; max-width: 800px; margin: 0 auto; background: #fff; border-radius: 8px; padding: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); border: 1px solid #e2e8f0; }}
    .header {{ border-bottom: 2px solid #4f46e5; padding-bottom: 8px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; }}
    h2 {{ margin: 0; color: #4f46e5; font-size: 16px; display: flex; align-items: center; gap: 6px; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; background: #f1f5f9; padding: 10px; border-radius: 6px; margin-bottom: 12px; text-align: center; }}
    .summary-item {{ font-size: 11px; color: #475569; }}
    .summary-item strong {{ display: block; font-size: 14px; color: #1e293b; margin-top: 2px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 0; font-size: 10.5px; min-width: 620px; }}
    th, td {{ padding: 6px 8px; border: 1px solid #e2e8f0; }}
    th {{ background: #4f46e5 !important; color: #fff !important; font-weight: 600; text-align: left; }}
    tr:nth-child(even) {{ background: #f8fafc; }}
    .table-responsive {{ width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; margin-bottom: 12px; border-radius: 6px; border: 1px solid #cbd5e1; background: #fff; }}
    .btn-row {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 0 auto 14px; max-width: 540px; width: 100%; }}
    @media (max-width: 520px) {{
        .btn-row {{ grid-template-columns: 1fr; }}
    }}
    .btn-action {{ width: 100%; padding: 10px 12px; border: none; border-radius: 6px; font-size: 13px; font-weight: bold; cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; justify-content: center; gap: 6px; text-align: center; transition: all 0.15s ease; box-shadow: 0 1px 3px rgba(0,0,0,0.1); box-sizing: border-box; }}
    .btn-action:active {{ transform: scale(0.98); }}
    .btn-tg {{ background: #0284c7; color: #fff !important; }}
    .btn-pdf {{ background: #4f46e5; color: #fff !important; }}
    .btn-print {{ background: #64748b; color: #fff !important; }}
    .toast-msg {{ display: none; margin: 0 auto 12px; padding: 10px 14px; background: #ecfdf5; border: 1px solid #10b981; color: #065f46; border-radius: 6px; font-weight: 600; text-align: center; max-width: 540px; font-size: 12px; }}
    @media print {{
        body {{ background: #fff; padding: 0; }}
        .container {{ box-shadow: none; border: none; padding: 0; max-width: 100%; }}
        .no-print {{ display: none !important; }}
        .table-responsive {{ border: none; overflow: visible; }}
    }}
</style>
</head>
<body>
<div class="container">
    <div class="no-print">
        <div id="toast" class="toast-msg"></div>
        <div class="btn-row">
            <button type="button" id="btn-send-tg" onclick="sendToTelegram(this)" class="btn-action btn-tg">
                💬 Надіслати в Telegram
            </button>
            <a id="btn-direct-download" href="{pdf_download_url}" target="_blank" download="parts_inventory_{int(time.time())}.pdf" class="btn-action btn-pdf" onclick="handleDirectDownload(event, this)">
                📥 Зберегти як PDF
            </a>
            <button type="button" onclick="handlePrint()" class="btn-action btn-print">
                🖨️ Друк
            </button>
        </div>
    </div>
    <div class="header">
        <div>
            <h2>🧩 Звіт складу готових деталей</h2>
            <small style="color: #64748b;">3D Farm Hub — Інвентар деталей</small>
        </div>
        <div style="font-size: 11px; color: #64748b; text-align: right;"><strong>Дата:</strong> {date_str}</div>
    </div>
    <div class="summary-grid">
        <div class="summary-item">Деталей усього: <strong>{total_parts} шт</strong></div>
        <div class="summary-item">Загальна вага: <strong>{(total_weight_g/1000.0):.2f} кг</strong> ({total_weight_g:.0f}г)</div>
        <div class="summary-item">Загальна вартість: <strong>{total_val_uah:.2f} ₴</strong></div>
    </div>
    <div class="table-responsive">
        <table>
            <thead>
                <tr>
                    <th style="width: 28%;">Назва деталі</th>
                    <th style="width: 20%;">Модель принтера</th>
                    <th style="width: 10%; text-align:center;">Тип</th>
                    <th style="width: 12%; text-align:right;">Вага 1 шт</th>
                    <th style="width: 8%; text-align:center;">К-сть</th>
                    <th style="width: 10%; text-align:right;">Ціна/шт</th>
                    <th style="width: 12%; text-align:right;">Сума</th>
                </tr>
            </thead>
            <tbody>
                {rows_html if rows_html else '<tr><td colspan="7" style="text-align:center; padding:15px; color:#64748b;">Склад порожній</td></tr>'}
            </tbody>
        </table>
    </div>
</div>
<script>
function showToast(text, isError) {{
    var t = document.getElementById('toast');
    if (!t) return;
    t.innerHTML = text;
    t.style.display = 'block';
    t.style.background = isError ? '#fef2f2' : '#ecfdf5';
    t.style.borderColor = isError ? '#ef4444' : '#10b981';
    t.style.color = isError ? '#991b1b' : '#065f46';
    setTimeout(function() {{
        t.style.display = 'none';
    }}, 6000);
}}

function sendToTelegram(btn) {{
    var origText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '⏳ Надсилаємо...';

    var targetUrl = new URL(window.location.href);
    targetUrl.searchParams.set('send_telegram', '1');
    if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initData) {{
        targetUrl.searchParams.set('initData', window.Telegram.WebApp.initData);
    }}
    try {{
        var st = localStorage.getItem('web_session_token');
        if (st && !targetUrl.searchParams.has('token')) targetUrl.searchParams.set('token', st);
    }} catch(e) {{}}

    fetch(targetUrl.toString(), {{
        credentials: 'include',
        headers: {{ 'ngrok-skip-browser-warning': 'true' }}
    }})
    .then(function(res) {{
        if (!res.ok) {{
            return res.json().then(function(j) {{ throw new Error(j.error || ('HTTP ' + res.status)); }});
        }}
        return res.json();
    }})
    .then(function(data) {{
        if (data.status === 'ok') {{
            btn.innerHTML = '✅ Надіслано в чат!';
            showToast('✅ PDF успішно надіслано вам у чат Telegram! Перевірте повідомлення від бота.', false);
            if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.HapticFeedback) {{
                window.Telegram.WebApp.HapticFeedback.notificationOccurred('success');
            }}
            setTimeout(function() {{
                btn.innerHTML = origText;
                btn.disabled = false;
            }}, 4000);
        }} else {{
            throw new Error(data.error || 'Помилка надсилання');
        }}
    }})
    .catch(function(err) {{
        btn.disabled = false;
        btn.innerHTML = origText;
        showToast('⚠️ ' + err.message, true);
    }});
}}

function handleDirectDownload(e, link) {{
    if (window.Telegram && window.Telegram.WebApp && typeof window.Telegram.WebApp.downloadFile === 'function') {{
        try {{
            window.Telegram.WebApp.downloadFile({{
                url: link.href,
                filename: link.getAttribute('download') || 'parts_inventory.pdf'
            }});
            showToast('⏳ Завантаження розпочато...', false);
        }} catch (err) {{
            console.warn("downloadFile failed:", err);
        }}
    }}
}}

function handlePrint() {{
    var isTgMobile = window.Telegram && window.Telegram.WebApp && 
                     (window.Telegram.WebApp.platform === 'android' || 
                      window.Telegram.WebApp.platform === 'ios' || 
                      /android|iphone|ipad|ipod/i.test(navigator.userAgent));
    if (isTgMobile) {{
        showToast("ℹ️ У мобільному Telegram прямий друк недоступний усередині застосунку. Скористайтеся 'Надіслати в Telegram' або 'Зберегти як PDF'.", false);
        try {{
            window.print();
        }} catch(e) {{}}
        return;
    }}
    try {{
        window.print();
    }} catch(err) {{
        console.warn("Print error:", err);
        showToast("⚠️ Друк не підтримується цим переглядачем. Скористайтеся 'Зберегти як PDF'.", true);
    }}
}}
</script>
</body>
</html>"""
        return web.Response(text=html_content, content_type="text/html", charset="utf-8")
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

