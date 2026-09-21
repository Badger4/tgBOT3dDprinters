"""
Spool inventory warehouse management endpoints with audit movement logs.
"""

import asyncio
import time
from aiohttp import web

from services.http.auth import check_auth


async def handle_get_spools(request: web.Request) -> web.Response:
    """GET /api/spools - Filament spool inventory with warehouse financial summary."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    spools = await app_obj.storage.load_spools()
    if not isinstance(spools, dict):
        spools = {}

    total_spools = 0
    total_weight_g = 0.0
    total_value_uah = 0.0

    for s in spools.values():
        if isinstance(s, dict):
            rem_g = float(s.get("remaining_grams") or s.get("total_grams") or 1000.0)
            price_kg = float(s.get("price_per_kg") or s.get("price_uah") or 650.0)
            qty = max(1, int(s.get("quantity", 1)))
            total_spools += qty
            total_weight_g += rem_g * qty
            total_value_uah += (rem_g / 1000.0) * price_kg * qty

    if request.query.get("with_summary") == "true" or request.headers.get("X-Include-Summary") == "true":
        return web.json_response({
            "spools": spools,
            "summary": {
                "total_spools_count": total_spools,
                "total_weight_kg": round(total_weight_g / 1000.0, 2),
                "total_value_uah": round(total_value_uah, 2),
            }
        })

    return web.json_response(spools)


async def handle_get_spool_movements(request: web.Request) -> web.Response:
    """GET /api/spools/movements - Retrieve warehouse audit movement log with optional filters."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    spool_id_filter = request.query.get("spool_id", "").strip()
    action_filter = request.query.get("action", "").strip()
    date_filter = request.query.get("date", "").strip()
    query_filter = request.query.get("q", "").strip()

    from utils.filament_utils import filter_spool_movements
    movements = await app_obj.storage.load_spool_movements()
    movements = filter_spool_movements(
        movements,
        spool_id=spool_id_filter,
        action=action_filter,
        date_range=date_filter,
        query=query_filter,
    )
    return web.json_response(movements)


async def handle_save_spool(request: web.Request) -> web.Response:
    """POST /api/spools - Add or update a spool with automatic audit trail logging."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    try:
        data = await request.json()
        spool_id = data.get("id") or f"spool_{int(time.time())}"
        spools = await app_obj.storage.load_spools()
        if not isinstance(spools, dict):
            spools = {}

        is_existing = spool_id in spools
        existing = spools.get(spool_id, {}) if isinstance(spools.get(spool_id), dict) else {}

        prev_weight = float(existing.get("remaining_grams", 0.0))
        new_weight = float(data.get("remaining_grams", 1000.0))
        spool_name = data.get("name", existing.get("name", "Котушка"))

        if new_weight <= 0.0:
            if spool_id in spools:
                del spools[spool_id]
            await app_obj.storage.save_spools(spools)
            return web.json_response({"status": "deleted", "spool_id": spool_id, "message": "Котушку видалено через нульову вагу"})

        initial_g = float(existing.get("initial_grams") or data.get("initial_grams") or new_weight)

        assigned_p = data.get("assigned_printer_id", existing.get("assigned_printer_id"))
        assigned_s = data.get("assigned_slot_key", existing.get("assigned_slot_key"))

        spools[spool_id] = {
            "id": spool_id,
            "name": spool_name,
            "type": data.get("type", existing.get("type", "PLA")),
            "color": data.get("color", existing.get("color", "#ffffff")),
            "initial_grams": initial_g,
            "remaining_grams": new_weight,
            "quantity": max(1, int(data.get("quantity", existing.get("quantity", 1)))),
            "price_per_kg": float(data.get("price_per_kg", existing.get("price_per_kg", 650.0))),
            "notes": data.get("notes", existing.get("notes", "")),
            "assigned_printer_id": assigned_p,
            "assigned_slot_key": assigned_s,
        }
        await app_obj.storage.save_spools(spools)

        # Audit movement logging
        if not is_existing:
            await app_obj.storage.record_spool_movement(
                spool_id=spool_id,
                spool_name=spool_name,
                action="initial_stock",
                weight_change_g=new_weight,
                prev_weight_g=0.0,
                new_weight_g=new_weight,
                reason="Первинне внесення котушки на склад",
                user="Admin",
            )
        elif abs(new_weight - prev_weight) > 0.01:
            delta = new_weight - prev_weight
            action = "refill" if delta > 0 else "manual_edit"
            reason = data.get("reason") or ("Поповнення запасу котушки" if delta > 0 else "Ручне коригування ваги")
            await app_obj.storage.record_spool_movement(
                spool_id=spool_id,
                spool_name=spool_name,
                action=action,
                weight_change_g=delta,
                prev_weight_g=prev_weight,
                new_weight_g=new_weight,
                reason=reason,
                user="Admin",
            )

        return web.json_response({"status": "ok", "spool": spools[spool_id]})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


async def handle_delete_spool(request: web.Request) -> web.Response:
    """DELETE /api/spools/{id} - Remove a spool from inventory with audit logging."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    spool_id = request.match_info.get("id", "")
    spools = await app_obj.storage.load_spools()
    if not isinstance(spools, dict):
        spools = {}

    if spool_id in spools:
        spool = spools.pop(spool_id)
        await app_obj.storage.save_spools(spools)

        prev_weight = float(spool.get("remaining_grams", 0.0))
        await app_obj.storage.record_spool_movement(
            spool_id=spool_id,
            spool_name=spool.get("name", "Котушка"),
            action="write_off",
            weight_change_g=-prev_weight,
            prev_weight_g=prev_weight,
            new_weight_g=0.0,
            reason="Списання / Видалення котушки зі складу",
            user="Admin",
        )
        return web.json_response({"status": "ok"})
    return web.json_response({"error": "Spool not found"}, status=404)


async def handle_mount_spool(request: web.Request) -> web.Response:
    """POST /api/spools/{id}/mount - Assign a spool to a specific printer and AMS slot."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    spool_id = request.match_info.get("id", "")
    try:
        data = await request.json()
        printer_id = data.get("printer_id", "").strip()
        slot_key = str(data.get("slot_key", "0")).strip()

        spools = await app_obj.storage.load_spools()
        if spool_id not in spools:
            return web.json_response({"error": "Spool not found"}, status=404)

        target_printer = app_obj.printers.get(printer_id)
        if not target_printer:
            return web.json_response({"error": "Printer not found"}, status=404)

        # Unmount any previously mounted spool in this same printer slot
        for s_id, s in spools.items():
            if s.get("assigned_printer_id") == printer_id and str(s.get("assigned_slot_key")) == slot_key:
                s["assigned_printer_id"] = None
                s["assigned_slot_key"] = None

        spool = spools[spool_id]
        spool["assigned_printer_id"] = printer_id
        spool["assigned_slot_key"] = slot_key
        await app_obj.storage.save_spools(spools)

        # Update printer slot telemetry
        rem_g = float(spool.get("remaining_grams", 1000.0))
        target_printer.set_slot_grams(rem_g, slot_id=slot_key)
        if hasattr(app_obj, "save_printers_config") and callable(app_obj.save_printers_config):
            res = app_obj.save_printers_config()
            if asyncio.iscoroutine(res) or asyncio.isfuture(res):
                await res

        return web.json_response({"status": "ok", "spool": spool})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


async def handle_unmount_spool(request: web.Request) -> web.Response:
    """POST /api/spools/{id}/unmount - Unmount a spool from its assigned printer slot."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    spool_id = request.match_info.get("id", "")
    spools = await app_obj.storage.load_spools()
    if spool_id not in spools:
        return web.json_response({"error": "Spool not found"}, status=404)

    spool = spools[spool_id]
    p_id = spool.get("assigned_printer_id")
    slot_k = spool.get("assigned_slot_key")

    spool["assigned_printer_id"] = None
    spool["assigned_slot_key"] = None
    await app_obj.storage.save_spools(spools)

    if p_id and p_id in app_obj.printers:
        p = app_obj.printers[p_id]
        p.set_slot_grams(0.0, slot_id=str(slot_k or "0"))
        if hasattr(app_obj, "save_printers_config") and callable(app_obj.save_printers_config):
            res = app_obj.save_printers_config()
            if asyncio.iscoroutine(res) or asyncio.isfuture(res):
                await res

    return web.json_response({"status": "ok", "spool": spool})



async def handle_export_warehouse_csv(request: web.Request) -> web.Response:
    """GET /api/warehouse/export_csv - Download structured PDF report of spools/parts warehouse."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        app_obj = request.app["app_obj"]
        spools = await app_obj.storage.load_spools()
        parts = await app_obj.storage.load_parts()
        report_type = request.query.get("type", "spools")

        from services.report_generator import generate_warehouse_pdf_report
        pdf_bytes = generate_warehouse_pdf_report(
            spools, parts, report_type=report_type, printers=getattr(app_obj, "printers", None)
        )

        filename = "parts_report.pdf" if report_type == "parts" else "spools_report.pdf"
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{filename}',
            "Content-Type": "application/pdf",
        }
        return web.Response(body=pdf_bytes, headers=headers)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_export_spools_pdf(request: web.Request) -> web.Response:
    """GET /api/spools/export_pdf - Generates clean printable HTML/PDF report of spools warehouse."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        app_obj = request.app["app_obj"]
        spools = await app_obj.storage.load_spools()

        date_str = time.strftime("%Y-%m-%d %H:%M")

        total_spools = 0
        total_weight_g = 0.0
        total_val_uah = 0.0

        rows_html = ""
        if spools and isinstance(spools, dict):
            for s_id, s in spools.items():
                if isinstance(s, dict):
                    name = s.get("name", "Котушка")
                    fil_type = s.get("type", "PLA")
                    color = str(s.get("color") or "-")
                    initial_g = float(s.get("initial_grams") or s.get("total_grams") or 1000.0)
                    rem_g = float(s.get("remaining_grams") or 1000.0)
                    price_kg = float(s.get("price_per_kg") or 650.0)
                    qty = max(1, int(s.get("quantity", 1)))
                    slot = s.get("assigned_slot_key")
                    p_id = s.get("assigned_printer_id")
                    if p_id or slot:
                        from services.report_generator import _format_slot_name, _resolve_printer_name
                        p_name = _resolve_printer_name(p_id, getattr(app_obj, "printers", None))
                        slot_desc = _format_slot_name(slot)
                        status_text = f"{p_name} ({slot_desc})"
                    else:
                        status_text = "На складі"

                    val = (rem_g / 1000.0) * price_kg * qty
                    total_spools += qty
                    total_weight_g += rem_g * qty
                    total_val_uah += val

                    rows_html += f"""
                    <tr>
                        <td style="font-weight:600;">{name}</td>
                        <td style="text-align:center;">{fil_type}</td>
                        <td style="text-align:center;">{color}</td>
                        <td style="text-align:right;">{rem_g:.0f} / {initial_g:.0f}г</td>
                        <td style="text-align:center;">{qty}</td>
                        <td style="text-align:right;">{price_kg:.2f} ₴</td>
                        <td style="text-align:center; font-size:10px;">{status_text}</td>
                        <td style="text-align:right; font-weight:700; color:#4f46e5;">{val:.2f} ₴</td>
                    </tr>
                    """

        if request.query.get("send_telegram") == "1":
            from services.report_generator import generate_spools_pdf_report
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

            pdf_bytes = generate_spools_pdf_report(spools, printers=getattr(app_obj, "printers", None))
            fname = f"spools_inventory_{int(time.time())}.pdf"
            doc_file = BufferedInputFile(pdf_bytes, filename=fname)
            cap = (
                f"📦 <b>Звіт складу пластику</b>\n"
                f"Котушок усього: <b>{total_spools} шт</b>\n"
                f"Загальний залишок: <b>{(total_weight_g/1000.0):.2f} кг</b>\n"
                f"Загальна вартість: <b>{total_val_uah:.2f} ₴</b>"
            )
            try:
                await bot.send_document(chat_id=int(u_id), document=doc_file, caption=cap, parse_mode=ParseMode.HTML)
                return web.json_response({"status": "ok", "message": "PDF успішно надіслано в чат!"})
            except Exception as ex:
                from config import logger
                logger.error(f"Failed to send spools PDF to user {u_id}: {ex}")
                return web.json_response({"error": f"Помилка відправки в Telegram: {ex}"}, status=500)

        req_format = request.query.get("format", "").lower()
        if req_format != "html":
            from services.report_generator import generate_spools_pdf_report
            pdf_bytes = generate_spools_pdf_report(spools, printers=getattr(app_obj, "printers", None))
            fname = f"spools_inventory_{int(time.time())}.pdf"
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
        pdf_download_url = f"/api/spools/export_pdf?{urllib.parse.urlencode(q_dict)}"

        html_content = f"""<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Звіт складу пластику</title>
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
    table {{ width: 100%; border-collapse: collapse; margin: 0; font-size: 10.5px; min-width: 660px; }}
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
            <a id="btn-direct-download" href="{pdf_download_url}" target="_blank" download="spools_inventory_{int(time.time())}.pdf" class="btn-action btn-pdf" onclick="handleDirectDownload(event, this)">
                📥 Зберегти як PDF
            </a>
            <button type="button" onclick="handlePrint()" class="btn-action btn-print">
                🖨️ Друк
            </button>
        </div>
    </div>
    <div class="header">
        <div>
            <h2>📦 Звіт складу філаменту</h2>
            <small style="color: #64748b;">3D Farm Hub — Інвентар пластику</small>
        </div>
        <div style="font-size: 11px; color: #64748b; text-align: right;"><strong>Дата:</strong> {date_str}</div>
    </div>
    <div class="summary-grid">
        <div class="summary-item">Котушок усього: <strong>{total_spools} шт</strong></div>
        <div class="summary-item">Загальний залишок: <strong>{(total_weight_g/1000.0):.2f} кг</strong></div>
        <div class="summary-item">Загальна вартість: <strong>{total_val_uah:.2f} ₴</strong></div>
    </div>
    <div class="table-responsive">
        <table>
            <thead>
                <tr>
                    <th style="width: 26%;">Назва</th>
                    <th style="width: 10%; text-align:center;">Тип</th>
                    <th style="width: 10%; text-align:center;">Колір</th>
                    <th style="width: 15%; text-align:right;">Залишок</th>
                    <th style="width: 7%; text-align:center;">К-сть</th>
                    <th style="width: 11%; text-align:right;">Ціна/кг</th>
                    <th style="width: 9%; text-align:center;">Статус</th>
                    <th style="width: 12%; text-align:right;">Сума</th>
                </tr>
            </thead>
            <tbody>
                {rows_html if rows_html else '<tr><td colspan="8" style="text-align:center; padding:15px; color:#64748b;">Склад порожній</td></tr>'}
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
                filename: link.getAttribute('download') || 'spools_inventory.pdf'
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


async def handle_export_movements_pdf(request: web.Request) -> web.Response:
    """GET /api/spools/movements/export_pdf - Download PDF report of warehouse audit movement logs."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        app_obj = request.app["app_obj"]
        spool_id_filter = request.query.get("spool_id", "").strip()
        action_filter = request.query.get("action", "").strip()
        date_filter = request.query.get("date", "").strip()
        query_filter = request.query.get("q", "").strip()

        from utils.filament_utils import filter_spool_movements
        movements = await app_obj.storage.load_spool_movements()
        movements = filter_spool_movements(
            movements,
            spool_id=spool_id_filter,
            action=action_filter,
            date_range=date_filter,
            query=query_filter,
        )

        filter_parts = []
        if spool_id_filter and spool_id_filter != "all":
            spools = await app_obj.storage.load_spools()
            s_name = spools.get(spool_id_filter, {}).get("name", spool_id_filter) if isinstance(spools, dict) else spool_id_filter
            filter_parts.append(f"Котушка: {s_name}")
        if action_filter and action_filter != "all":
            act_names = {"print": "Друк", "manual_edit": "Коригування", "initial_stock": "Внесення", "refill": "Поповнення", "write_off": "Списання", "stock": "Внесення/Поповнення"}
            filter_parts.append(f"Дія: {act_names.get(action_filter, action_filter)}")
        if date_filter and date_filter != "all":
            date_names = {"today": "Сьогодні", "yesterday": "Вчора", "week": "Останні 7 днів", "month": "Останні 30 днів"}
            filter_parts.append(f"Період: {date_names.get(date_filter, date_filter)}")
        if query_filter:
            filter_parts.append(f"Пошук: '{query_filter}'")

        filter_subtitle = " | ".join(filter_parts) if filter_parts else None

        from services.report_generator import generate_movements_pdf_report
        pdf_bytes = generate_movements_pdf_report(movements, filter_subtitle=filter_subtitle)

        if request.query.get("send_telegram") == "1":
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

            fname = f"spool_movements_{int(time.time())}.pdf"
            doc_file = BufferedInputFile(pdf_bytes, filename=fname)
            cap = f"📋 <b>Журнал руху котушок (Аудит)</b>\nЗаписів: <b>{len(movements)}</b>"
            try:
                await bot.send_document(chat_id=int(u_id), document=doc_file, caption=cap, parse_mode=ParseMode.HTML)
                return web.json_response({"status": "ok", "message": "PDF успішно надіслано в чат!"})
            except Exception as ex:
                from config import logger
                logger.error(f"Failed to send movements PDF to user {u_id}: {ex}")
                return web.json_response({"error": f"Помилка відправки в Telegram: {ex}"}, status=500)

        disp_type = "inline" if request.query.get("inline") == "1" else "attachment"
        headers = {
            "Content-Disposition": f'{disp_type}; filename="spool_movements_audit.pdf"; filename*=UTF-8\'\'spool_movements_audit.pdf',
            "Content-Type": "application/pdf",
        }
        return web.Response(body=pdf_bytes, headers=headers)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_export_movements_csv(request: web.Request) -> web.Response:
    """GET /api/spools/movements/export_csv - Redirect/Return PDF report."""
    return await handle_export_movements_pdf(request)

