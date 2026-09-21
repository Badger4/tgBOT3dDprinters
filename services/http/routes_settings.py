"""
Commercial presets, history, health check, global settings, and WebApp static index routes.
"""

import html
import time
from pathlib import Path
from typing import Any

from aiohttp import web

import config
from config import ADMIN_CHAT_ID, TELEGRAM_BOT_TOKEN, __version__, logger
from models.commercial import calculate_commercial_price, validate_val_or_percent
from services.http.auth import check_auth, verify_telegram_init_data

START_TIME = time.time()
WEBAPP_DIR = Path(__file__).parent.parent.parent / "webapp"


def get_presets_file(app_obj: Any) -> Path:
    if hasattr(app_obj, "storage") and hasattr(app_obj.storage, "base_dir"):
        return app_obj.storage.base_dir / "commercial_presets.json"
    return config.STORAGE_DIR / "commercial_presets.json"


DEFAULT_PRESETS = {
    "default_pla": {
        "id": "default_pla",
        "name": "Стандарт PLA (850 грн/кг, +100%)",
        "price_per_g": 0.85,
        "electricity_rate_uah": 4.32,
        "power_watts": 120.0,
        "depreciation_val": "10",
        "consumables_val": "5",
        "profit_val": "100%",
    },
    "default_petg": {
        "id": "default_petg",
        "name": "PETG / Engineering (950 грн/кг, +100%)",
        "price_per_g": 0.95,
        "electricity_rate_uah": 4.32,
        "power_watts": 150.0,
        "depreciation_val": "15",
        "consumables_val": "8",
        "profit_val": "100%",
    },
}


async def handle_serve_index(request: web.Request) -> web.StreamResponse:
    """Serves the main Telegram WebApp single-page application."""
    index_file = WEBAPP_DIR / "index.html"
    if not index_file.exists():
        return web.Response(text="<h1>WebApp index.html not found</h1>", content_type="text/html", status=404)
    resp = web.FileResponse(index_file)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


async def handle_health(request: web.Request) -> web.Response:
    """GET /health - System health check endpoint for UptimeRobot / Docker / systemd."""
    app_obj = request.app["app_obj"]
    uptime = int(time.time() - START_TIME)
    printers = list(app_obj.printers.values())
    active = sum(1 for p in printers if p.gcode_state == "RUNNING")

    return web.json_response(
        {
            "status": "ok",
            "version": __version__,
            "uptime_seconds": uptime,
            "total_printers": len(printers),
            "active_printers": active,
        }
    )


def sanitize_commercial_presets(presets: dict[str, Any]) -> dict[str, Any]:
    """Sanitizes preset entries and ensures valid dictionaries."""
    if not isinstance(presets, dict):
        return {}
    clean = {}
    for pid, p in presets.items():
        if not isinstance(p, dict):
            continue
        if not p.get("name"):
            continue
        clean[pid] = p
    return clean


async def load_commercial_presets(app_obj: Any) -> dict:
    presets_file = get_presets_file(app_obj)
    presets = await app_obj.storage.load_json(presets_file, None)
    if presets is None:
        presets = DEFAULT_PRESETS.copy()
        await app_obj.storage.save_json(presets_file, presets)

    sanitized = sanitize_commercial_presets(presets)

    unique_presets = {}
    seen_names = set()
    for pid, p in sanitized.items():
        pname = str(p.get("name", "")).strip()
        if pname and pname not in seen_names:
            seen_names.add(pname)
            unique_presets[pid] = p

    if len(unique_presets) != len(presets):
        presets = unique_presets
        await app_obj.storage.save_json(presets_file, presets)
    else:
        presets = unique_presets

    return presets


async def handle_get_presets(request: web.Request) -> web.Response:
    """GET /api/commercial/presets - List commercial pricing presets."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    presets = await load_commercial_presets(app_obj)
    return web.json_response(presets)


async def handle_save_preset(request: web.Request) -> web.Response:
    """POST /api/commercial/presets - Create or update commercial preset."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    try:
        data = await request.json()
        p_id = data.get("id") or f"preset_{int(time.time())}"

        name = str(data.get("name") or "").strip()
        if not name:
            return web.json_response({"error": "Назва пресету не може бути порожньою"}, status=400)

        raw_price = data.get("price_per_g")
        try:
            val_p = float(str(raw_price).replace(",", ".")) if raw_price is not None else 0.85
            if val_p <= 0:
                val_p = 0.85
            price_g = val_p / 1000.0 if val_p >= 50 else val_p
        except (ValueError, TypeError):
            price_g = 0.85

        raw_elec = data.get("electricity_rate_uah")
        try:
            val_e = float(str(raw_elec).replace(",", ".")) if raw_elec is not None else 4.32
            if val_e < 0:
                val_e = 4.32
            elec_rate = val_e
        except (ValueError, TypeError):
            elec_rate = 4.32

        raw_power = data.get("power_watts")
        try:
            val_pw = float(str(raw_power).replace(",", ".")) if raw_power is not None else 120.0
            if val_pw < 0:
                val_pw = 120.0
            power_w = val_pw
        except (ValueError, TypeError):
            power_w = 120.0

        raw_depr = str(data.get("depreciation_val") or "10")
        ok_d, depr_clean = validate_val_or_percent(raw_depr)
        if not ok_d:
            return web.json_response({"error": f"Амортизація: {depr_clean}"}, status=400)

        raw_cons = str(data.get("consumables_val") or "5")
        ok_c, cons_clean = validate_val_or_percent(raw_cons)
        if not ok_c:
            return web.json_response({"error": f"Витратники: {cons_clean}"}, status=400)

        raw_profit = str(data.get("profit_val") or "100%")
        ok_pr, profit_clean = validate_val_or_percent(raw_profit)
        if not ok_pr:
            return web.json_response({"error": f"Прибуток: {profit_clean}"}, status=400)

        presets = await load_commercial_presets(app_obj)
        presets[p_id] = {
            "id": p_id,
            "name": name,
            "price_per_g": price_g,
            "electricity_rate_uah": elec_rate,
            "power_watts": power_w,
            "depreciation_val": depr_clean,
            "consumables_val": cons_clean,
            "profit_val": profit_clean,
        }
        presets_file = get_presets_file(app_obj)
        await app_obj.storage.save_json(presets_file, presets)
        return web.json_response({"status": "ok", "preset": presets[p_id]})
    except Exception as e:
        logger.error(f"Error saving commercial preset: {e}")
        return web.json_response({"error": str(e)}, status=400)


async def handle_delete_preset(request: web.Request) -> web.Response:
    """DELETE /api/commercial/presets/{id} - Remove commercial preset."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    p_id = request.match_info.get("id", "")
    presets = await load_commercial_presets(app_obj)
    if p_id in presets:
        del presets[p_id]
        presets_file = get_presets_file(app_obj)
        await app_obj.storage.save_json(presets_file, presets)
        return web.json_response({"status": "ok"})
    return web.json_response({"error": "Preset not found"}, status=404)


async def handle_calculate_commercial(request: web.Request) -> web.Response:
    """POST /api/commercial/calculate - Calculate pricing breakdown."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    try:
        data = await request.json()
        weight_g = float(data.get("weight_g", 100.0))
        time_mins = int(data.get("time_mins", 60))
        preset_id = data.get("preset_id")

        presets = await load_commercial_presets(app_obj)
        preset = presets.get(preset_id) if preset_id else data.get("preset")
        if not preset:
            preset = list(presets.values())[0] if presets else DEFAULT_PRESETS["default_pla"]

        calc = calculate_commercial_price(preset, weight_g, time_mins)
        return web.json_response({"status": "ok", "calculation": calc})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


async def handle_get_history(request: web.Request) -> web.Response:
    """GET /api/history - Completed print jobs history."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    if hasattr(app_obj, "storage") and hasattr(app_obj.storage, "load_history"):
        history = await app_obj.storage.load_history()
    else:
        history = await app_obj.storage.load_json(app_obj.storage.history_file, [])

    total_grams = sum(float(item.get("weight_g", 0.0)) for item in history)
    total_cost = sum(float(item.get("cost_uah", 0.0)) for item in history)

    normalized_history = []
    for item in history:
        ts = item.get("timestamp", 0)
        dt_str = (
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
            if isinstance(ts, (int, float)) and ts > 0
            else str(ts or "-")
        )
        pname = item.get("printer_name") or item.get("printer") or "Принтер"
        pid = item.get("printer_id", "")
        psn = item.get("printer_sn", "")
        raw_sub = str(item.get("subtask_name") or item.get("task") or item.get("model_name") or "").strip()
        subtask = "Модель 3D" if not raw_sub or raw_sub.lower() in ["untitled", "none", "null"] else raw_sub
        w_g = round(float(item.get("weight_g", 0.0)), 1)
        cost = round(float(item.get("cost_uah", 0.0)), 2)
        filament = item.get("filament_type", "PLA")
        normalized_history.append(
            {
                "timestamp": ts,
                "datetime": dt_str,
                "printer_name": pname,
                "printer": pname,
                "printer_id": pid,
                "printer_sn": psn,
                "subtask_name": subtask,
                "task": subtask,
                "weight_g": w_g,
                "cost_uah": cost,
                "filament_type": filament,
                "note": item.get("note", "Успішно виконано"),
            }
        )

    return web.json_response(
        {
            "total_jobs": len(normalized_history),
            "total_weight_g": round(total_grams, 1),
            "total_weight_kg": round(total_grams / 1000.0, 3),
            "total_cost_uah": round(total_cost, 2),
            "history": normalized_history,
        }
    )


async def handle_delete_history(request: web.Request) -> web.Response:
    """DELETE /api/history - Clears history or deletes a specific entry by timestamp."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    ts_param = request.query.get("timestamp")
    if ts_param:
        try:
            ts_val = float(ts_param)
            if hasattr(app_obj.storage, "delete_history_entry"):
                await app_obj.storage.delete_history_entry(ts_val)
            else:
                history = await app_obj.storage.load_history()
                filtered = [item for item in history if item.get("timestamp") != ts_val]
                await app_obj.storage.save_json(app_obj.storage.history_file, filtered)
            return web.json_response({"status": "ok", "message": "Entry deleted"})
        except ValueError:
            return web.json_response({"error": "Invalid timestamp"}, status=400)

    if hasattr(app_obj.storage, "clear_history"):
        await app_obj.storage.clear_history()
    else:
        await app_obj.storage.save_json(app_obj.storage.history_file, [])
    return web.json_response({"status": "ok", "message": "History cleared"})


async def handle_export_history_csv(request: web.Request) -> web.Response:
    """GET /api/history/export - Exports completed print jobs history as PDF file."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    if hasattr(app_obj, "storage") and hasattr(app_obj.storage, "load_history"):
        history = await app_obj.storage.load_history()
    else:
        history = await app_obj.storage.load_json(app_obj.storage.history_file, [])

    from services.report_generator import generate_history_pdf_report

    pdf_bytes = generate_history_pdf_report(history)
    filename = f"farm_history_{int(time.time())}.pdf"
    return web.Response(
        body=pdf_bytes,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{filename}',
            "Content-Type": "application/pdf",
        },
    )


async def handle_export_commercial_pdf(request: web.Request) -> web.Response:
    """GET /api/commercial/export_pdf - Generates clean printable HTML/PDF report for commercial calculation."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    try:
        weight_g = float(request.query.get("weight_g", 100.0))
        time_mins = int(request.query.get("time_mins", 60))
        preset_id = request.query.get("preset_id")

        presets = await load_commercial_presets(app_obj)
        preset = presets.get(preset_id) if preset_id else None
        if not preset and presets:
            preset = list(presets.values())[0]
        elif not preset:
            preset = DEFAULT_PRESETS.get("default_pla", {})

        calc = calculate_commercial_price(preset, weight_g, time_mins)
        preset_name = preset.get("name", "За замовчуванням")

        if request.query.get("send_telegram") == "1":
            from services.report_generator import generate_commercial_calc_pdf
            from aiogram.types import BufferedInputFile
            from aiogram.enums import ParseMode
            import config

            bot = getattr(app_obj, "bot", None)
            if not bot:
                return web.json_response({"error": "Бот зараз не активний"}, status=503)

            u_id = get_authenticated_user_id(request) or getattr(config, "ADMIN_CHAT_ID", None)
            if not u_id:
                return web.json_response({"error": "Користувача не ідентифіковано"}, status=400)

            pdf_bytes = generate_commercial_calc_pdf(calc, filename=request.query.get("filename"), lang="uk")
            fname = f"commercial_quote_{int(time.time())}.pdf"
            doc_file = BufferedInputFile(pdf_bytes, filename=fname)
            cap = (
                f"💼 <b>Розрахунок вартості друку</b>\n"
                f"Пресет: <b>{html.escape(preset_name)}</b>\n"
                f"Вага: <b>{weight_g:.1f} г</b> | Час: <b>~{time_mins} хв</b>\n"
                f"🏷️ <b>Підсумкова ціна: {calc.get('total_price', 0):.2f} ₴</b>"
            )
            try:
                await bot.send_document(chat_id=int(u_id), document=doc_file, caption=cap, parse_mode=ParseMode.HTML)
                return web.json_response({"status": "ok", "message": "PDF успішно надіслано в чат!"})
            except Exception as ex:
                logger.error(f"Failed to send PDF to user {u_id}: {ex}")
                return web.json_response({"error": f"Помилка відправки в Telegram: {ex}"}, status=500)

        req_format = request.query.get("format", "").lower()
        if req_format != "html":
            from services.report_generator import generate_commercial_calc_pdf
            pdf_bytes = generate_commercial_calc_pdf(calc, filename=request.query.get("filename"), lang="uk")
            fname = f"commercial_quote_{int(time.time())}.pdf"
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
        pdf_download_url = f"/api/commercial/export_pdf?{urllib.parse.urlencode(q_dict)}"

        date_str = time.strftime("%Y-%m-%d %H:%M")

        pr_g = float(calc.get("price_per_g", preset.get("price_per_g", 0.85)))
        pr_kg = pr_g * 1000.0
        elec_rate = float(calc.get("electricity_rate_uah", preset.get("electricity_rate_uah", 4.32)))
        power_w = float(calc.get("power_watts", preset.get("power_watts", 120.0)))
        time_hours = float(calc.get("time_hours", time_mins / 60.0))
        direct_cost = float(calc.get("direct_cost", 0.0))
        depr_str = str(calc.get("depreciation_str", "-"))
        cons_str = str(calc.get("consumables_str", "-"))
        profit_str = str(calc.get("profit_str", "-"))
        profit_is_pct = calc.get("profit_is_pct", False)

        if profit_is_pct or "%" in profit_str:
            formatted_profit = f"+{profit_str.lstrip('+')}" if not profit_str.startswith("+") else profit_str
        else:
            try:
                val = float(profit_str)
                formatted_profit = f"{val:.2f} ₴"
            except ValueError:
                formatted_profit = f"{profit_str} ₴"

        if "%" in depr_str:
            depr_model = f"База: {direct_cost:.2f} ₴"
            depr_preset = f"Ставка: {depr_str}"
        else:
            depr_model = f"Час: {time_hours:.2f} год"
            depr_preset = f"{depr_str} ₴/год" if not depr_str.endswith("₴/год") and not depr_str.endswith("грн") else depr_str

        if "%" in cons_str:
            cons_model = f"База: {direct_cost:.2f} ₴"
            cons_preset = f"Ставка: {cons_str}"
        else:
            cons_model = f"Час: {time_hours:.2f} год"
            cons_preset = f"{cons_str} ₴/год" if not cons_str.endswith("₴/год") and not cons_str.endswith("грн") else cons_str

        html_content = f"""<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Звіт розрахунку вартості друку</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
    @page {{ size: A4 portrait; margin: 8mm; }}
    * {{ box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; background: #f8fafc; color: #0f172a; margin: 0; padding: 12px; font-size: 11px; }}
    .container {{ width: 100%; max-width: 620px; margin: 0 auto; background: #fff; border-radius: 8px; padding: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); border: 1px solid #e2e8f0; }}
    .header {{ border-bottom: 2px solid #4f46e5; padding-bottom: 8px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; }}
    h2 {{ margin: 0; color: #4f46e5; font-size: 16px; display: flex; align-items: center; gap: 6px; }}
    .summary-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; background: #f1f5f9; padding: 10px; border-radius: 6px; margin-bottom: 12px; font-size: 11px; }}
    .table-responsive {{ width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; margin-bottom: 12px; border-radius: 6px; border: 1px solid #cbd5e1; background: #fff; }}
    table {{ width: 100%; border-collapse: collapse; margin: 0; font-size: 11px; min-width: 480px; }}
    th, td {{ padding: 7px 9px; border: 1px solid #e2e8f0; }}
    th {{ background: #4f46e5 !important; color: #fff !important; font-weight: 600; text-align: left; }}
    .total-box {{ background: #eef2ff; border: 2px solid #4f46e5; border-radius: 6px; padding: 12px; text-align: right; font-size: 16px; font-weight: bold; color: #4f46e5; }}
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
            <a id="btn-direct-download" href="{pdf_download_url}" target="_blank" download="commercial_quote_{int(time.time())}.pdf" class="btn-action btn-pdf" onclick="handleDirectDownload(event, this)">
                📥 Зберегти як PDF
            </a>
            <button type="button" onclick="handlePrint()" class="btn-action btn-print">
                🖨️ Друк
            </button>
        </div>
    </div>
    <div class="header">
        <div>
            <h2>📊 Розрахунок вартості друку</h2>
            <small style="color: #64748b;">3D Farm Hub — Комерційне ціноутворення</small>
        </div>
        <div style="font-size: 11px; color: #64748b; text-align: right;"><strong>Дата:</strong> {date_str}</div>
    </div>
    <div class="summary-grid">
        <div><strong>Пресет:</strong> {preset_name}</div>
        <div><strong>Вага нитки:</strong> {weight_g:.1f} г</div>
        <div><strong>Час друку:</strong> {time_mins} хв</div>
        <div><strong>Маржа / Націнка:</strong> {formatted_profit}</div>
    </div>
    <div class="table-responsive">
        <table>
            <thead>
                <tr>
                    <th style="width: 32%;">Стаття витрат</th>
                    <th style="width: 24%;">Дані моделі</th>
                    <th style="width: 26%;">Дані пресета</th>
                    <th style="width: 18%; text-align:right;">Сума</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>🧵 Пластик (матеріал)</td>
                    <td>Вага: {weight_g:.1f} г</td>
                    <td>{pr_g:.2f} ₴/г ({pr_kg:.0f} ₴/кг)</td>
                    <td style="text-align:right;">{calc.get("filament_cost", 0):.2f} ₴</td>
                </tr>
                <tr>
                    <td>⚡ Електроенергія</td>
                    <td>Час: ~{time_mins} хв ({time_hours:.2f} год)</td>
                    <td>{power_w:.0f} Вт | {elec_rate:.2f} ₴/кВт·год</td>
                    <td style="text-align:right;">{calc.get("electricity_cost", 0):.2f} ₴</td>
                </tr>
                <tr>
                    <td>🔧 Амортизація обладнання</td>
                    <td>{depr_model}</td>
                    <td>{depr_preset}</td>
                    <td style="text-align:right;">{calc.get("depreciation_cost", 0):.2f} ₴</td>
                </tr>
                <tr>
                    <td>🧼 Витратні матеріали та ТО</td>
                    <td>{cons_model}</td>
                    <td>{cons_preset}</td>
                    <td style="text-align:right;">{calc.get("consumables_cost", 0):.2f} ₴</td>
                </tr>
                <tr style="font-weight:bold; background:#f8fafc;">
                    <td>💵 Собівартість (прямі витрати)</td>
                    <td>{weight_g:.1f} г | ~{time_mins} хв</td>
                    <td>Прямі витрати + амортизація</td>
                    <td style="text-align:right;">{calc.get("cost_before_profit", 0):.2f} ₴</td>
                </tr>
                <tr style="font-weight:bold; color:#16a34a; background:#f8fafc;">
                    <td>💼 Прибуток (Маржа)</td>
                    <td>База: {calc.get("cost_before_profit", 0):.2f} ₴</td>
                    <td>Націнка: {formatted_profit}</td>
                    <td style="text-align:right; color:#16a34a;">{calc.get("profit_cost", 0):.2f} ₴</td>
                </tr>
            </tbody>
        </table>
    </div>
    <div class="total-box">
        Підсумкова ціна: {calc.get("total_price", 0):.2f} ₴
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
                filename: link.getAttribute('download') || 'commercial_quote.pdf'
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
        return web.json_response({"error": str(e)}, status=400)


async def handle_export_history_pdf(request: web.Request) -> web.Response:
    """GET /api/history/export_pdf - Generates clean printable HTML/PDF report of print history."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        app_obj = request.app["app_obj"]
        history = await app_obj.storage.load_history()
        total_prints = len(history)
        total_weight_g = sum(float(item.get("weight_g", 0.0) or 0.0) for item in history)

        if request.query.get("send_telegram") == "1":
            from services.report_generator import generate_history_pdf_report
            from aiogram.types import BufferedInputFile
            from aiogram.enums import ParseMode
            import config

            bot = getattr(app_obj, "bot", None)
            if not bot:
                return web.json_response({"error": "Бот зараз не активний"}, status=503)

            u_id = get_authenticated_user_id(request) or getattr(config, "ADMIN_CHAT_ID", None)
            if not u_id:
                return web.json_response({"error": "Користувача не ідентифіковано"}, status=400)

            pdf_bytes = generate_history_pdf_report(history)
            fname = f"print_history_{int(time.time())}.pdf"
            doc_file = BufferedInputFile(pdf_bytes, filename=fname)
            cap = f"📊 <b>Звіт історії друку</b>\nВиконано робіт: <b>{total_prints}</b>\nВитрачено пластику: <b>{(total_weight_g/1000.0):.2f} кг</b>"
            try:
                await bot.send_document(chat_id=int(u_id), document=doc_file, caption=cap, parse_mode=ParseMode.HTML)
                return web.json_response({"status": "ok", "message": "PDF успішно надіслано в чат!"})
            except Exception as ex:
                logger.error(f"Failed to send history PDF to user {u_id}: {ex}")
                return web.json_response({"error": f"Помилка відправки в Telegram: {ex}"}, status=500)

        req_format = request.query.get("format", "").lower()
        if req_format != "html":
            from services.report_generator import generate_history_pdf_report
            pdf_bytes = generate_history_pdf_report(history)
            fname = f"print_history_{int(time.time())}.pdf"
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
        pdf_download_url = f"/api/history/export_pdf?{urllib.parse.urlencode(q_dict)}"

        date_str = time.strftime("%Y-%m-%d %H:%M")

        rows_html = ""
        for idx, item in enumerate(reversed(history), 1):
            ts = item.get("timestamp", time.time())
            if isinstance(ts, (int, float)):
                dt = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
            else:
                dt = str(ts)[:16]
            p_name = item.get("printer_name", "Принтер")
            subtask = item.get("subtask_name", "Модель")
            filament = item.get("filament_type", "PLA")
            weight_g = float(item.get("weight_g", 0.0) or 0.0)
            note = item.get("note", "Успішно")

            rows_html += f"""
            <tr>
                <td style="text-align:center;">{idx}</td>
                <td>{dt}</td>
                <td style="font-weight:600;">{p_name}</td>
                <td>{subtask}</td>
                <td style="text-align:center;">{filament}</td>
                <td style="text-align:right;">{weight_g:.1f}г</td>
                <td>{note}</td>
            </tr>
            """

        html_content = f"""<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Звіт історії друку</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
    @page {{ size: A4 portrait; margin: 8mm; }}
    * {{ box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; background: #f8fafc; color: #0f172a; margin: 0; padding: 12px; font-size: 11px; }}
    .container {{ width: 100%; max-width: 800px; margin: 0 auto; background: #fff; border-radius: 8px; padding: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); border: 1px solid #e2e8f0; }}
    .header {{ border-bottom: 2px solid #4f46e5; padding-bottom: 8px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; }}
    h2 {{ margin: 0; color: #4f46e5; font-size: 16px; display: flex; align-items: center; gap: 6px; }}
    .summary-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; background: #f1f5f9; padding: 10px; border-radius: 6px; margin-bottom: 12px; text-align: center; }}
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
            <a id="btn-direct-download" href="{pdf_download_url}" target="_blank" download="print_history_{int(time.time())}.pdf" class="btn-action btn-pdf" onclick="handleDirectDownload(event, this)">
                📥 Зберегти як PDF
            </a>
            <button type="button" onclick="handlePrint()" class="btn-action btn-print">
                🖨️ Друк
            </button>
        </div>
    </div>
    <div class="header">
        <div>
            <h2>📊 Звіт історії друку</h2>
            <small style="color: #64748b;">3D Farm Hub — Журнал виконаних робіт</small>
        </div>
        <div style="font-size: 11px; color: #64748b; text-align: right;"><strong>Дата:</strong> {date_str}</div>
    </div>
    <div class="summary-grid">
        <div class="summary-item">Всього виконано завдань: <strong>{total_prints}</strong></div>
        <div class="summary-item">Витрачено пластику: <strong>{(total_weight_g/1000.0):.2f} кг</strong> ({total_weight_g:.1f}г)</div>
    </div>
    <div class="table-responsive">
        <table>
            <thead>
                <tr>
                    <th style="width: 6%; text-align:center;">№</th>
                    <th style="width: 18%;">Дата</th>
                    <th style="width: 18%;">Принтер</th>
                    <th style="width: 26%;">Модель</th>
                    <th style="width: 10%; text-align:center;">Пластик</th>
                    <th style="width: 10%; text-align:right;">Вага</th>
                    <th style="width: 12%;">Результат</th>
                </tr>
            </thead>
            <tbody>
                {rows_html if rows_html else '<tr><td colspan="7" style="text-align:center; padding:15px; color:#64748b;">Історія порожня</td></tr>'}
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
                filename: link.getAttribute('download') || 'print_history.pdf'
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


async def handle_get_settings(request: web.Request) -> web.Response:
    """GET /api/settings - Global settings."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    settings = await app_obj.storage.load_json(app_obj.storage.settings_file, app_obj.global_settings)
    return web.json_response(settings)


async def handle_update_settings(request: web.Request) -> web.Response:
    """POST /api/settings - Save global settings."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    try:
        data = await request.json()
        app_obj.global_settings.update(data)
        await app_obj.storage.save_json(app_obj.storage.settings_file, app_obj.global_settings)
        return web.json_response({"status": "ok", "settings": app_obj.global_settings})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


def get_authenticated_user_id(request: web.Request) -> str | None:
    init_data = request.headers.get("X-Telegram-Init-Data") or request.query.get("initData", "")
    if init_data:
        t_user = verify_telegram_init_data(init_data, TELEGRAM_BOT_TOKEN)
        if t_user and isinstance(t_user, dict):
            u_id = str(t_user.get("id") or "")
            if u_id:
                return u_id
    return None


async def handle_get_user_settings(request: web.Request) -> web.Response:
    """GET /api/user/settings - Get user-specific notification settings."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    u_id = get_authenticated_user_id(request)

    user_notify = {
        "start": True,
        "finish": True,
        "pause": True,
        "hms": True,
        "remind_clear": True,
        "min_time_to_end": 0,
        "min_filament": 0,
    }
    user_info = {"id": u_id or "", "role": "USER", "approved": True}
    user_lang = "uk"

    is_admin = False
    if u_id and hasattr(app_obj, "storage"):
        user = await app_obj.storage.load_user(u_id)
        if user:
            user_notify.update(user.get("notify", {}))
            is_admin = (str(u_id) == str(ADMIN_CHAT_ID)) or bool(user.get("admin", {}).get("access_admin")) or user.get("role") == "ADMIN"
            user_info["role"] = "ADMIN" if is_admin else "USER"
            user_info["is_admin"] = is_admin
            user_info["approved"] = user.get("approved", True)
            user_lang = user.get("language", "uk")
    else:
        is_admin = True
        user_info["role"] = "ADMIN"
        user_info["is_admin"] = True

    return web.json_response({"notify": user_notify, "user": user_info, "language": user_lang})


async def handle_update_user_settings(request: web.Request) -> web.Response:
    """POST /api/user/settings - Update user-specific notification settings."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    u_id = get_authenticated_user_id(request)
    try:
        data = await request.json()
        notify_data = data.get("notify", {})
        new_lang = data.get("language")

        if u_id and hasattr(app_obj, "storage"):
            user = await app_obj.storage.load_user(u_id)
            if not isinstance(user.get("notify"), dict):
                user["notify"] = {}
            if notify_data:
                user["notify"].update(notify_data)
            if new_lang and str(new_lang).lower() in ["uk", "en"]:
                user["language"] = str(new_lang).lower()
            await app_obj.storage.save_user(user)
            return web.json_response({"status": "ok", "notify": user["notify"], "language": user.get("language", "uk")})

        return web.json_response({"status": "ok", "notify": notify_data, "language": new_lang or "uk"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


async def handle_get_users(request: web.Request) -> web.Response:
    """GET /api/users - Admin list of registered Telegram users."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    u_id = get_authenticated_user_id(request)
    if u_id and hasattr(app_obj, "storage"):
        u_data = await app_obj.storage.load_user(u_id)
        is_caller_admin = (str(u_id) == str(ADMIN_CHAT_ID)) or bool(u_data.get("admin", {}).get("access_admin")) or u_data.get("role") == "ADMIN"
        if not is_caller_admin:
            return web.json_response({"error": "Forbidden: Admin access required"}, status=403)

    app_obj = request.app["app_obj"]
    users = {}
    if hasattr(app_obj, "storage"):
        users = await app_obj.storage.load_all_users()

    user_list = []
    for uid, udata in users.items():
        uid_str = str(uid)
        is_admin = (uid_str == str(ADMIN_CHAT_ID)) or bool(udata.get("admin", {}).get("access_admin"))

        # Strictly default to False for non-admin users if is_approved is missing or False
        raw_approved = udata.get("is_approved")
        if raw_approved is None:
            raw_approved = udata.get("approved")
        is_approved = is_admin or (bool(raw_approved) if raw_approved is not None else False)

        first_name = str(udata.get("personal", {}).get("first_name") or udata.get("first_name") or "").strip()
        last_name = str(udata.get("personal", {}).get("last_name") or udata.get("last_name") or "").strip()
        username = str(udata.get("personal", {}).get("username") or udata.get("username") or "").strip()

        full_name = f"{first_name} {last_name}".strip() or f"Користувач {uid_str}"
        display_name = f"{full_name} (@{username})" if username else full_name

        user_list.append({
            "id": uid_str,
            "user_id": uid_str,
            "first_name": first_name,
            "username": username,
            "name": display_name,
            "role": udata.get("role") or ("ADMIN" if is_admin else "USER"),
            "approved": is_approved,
            "is_approved": is_approved,
            "created_at": udata.get("created_at", 0),
        })

    return web.json_response({"users": user_list})


async def handle_update_user_access(request: web.Request) -> web.Response:
    """POST /api/users/access - Admin update user approval or role."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    try:
        data = await request.json()
        target_id = str(data.get("user_id", "")).strip()
        if not target_id:
            return web.json_response({"error": "Missing user_id"}, status=400)

        if hasattr(app_obj, "storage"):
            user = await app_obj.storage.load_user(target_id)
            if "approved" in data:
                user["approved"] = bool(data["approved"])
                user["is_approved"] = bool(data["approved"])
            if "role" in data and data["role"] in ["ADMIN", "USER"]:
                user["role"] = data["role"]
                if "admin" not in user or not isinstance(user["admin"], dict):
                    user["admin"] = {}
                user["admin"]["access_admin"] = (data["role"] == "ADMIN")
            await app_obj.storage.save_user(user)
            return web.json_response({"status": "ok", "user": user})

        return web.json_response({"error": "Storage unresolvable"}, status=500)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


async def handle_delete_user(request: web.Request) -> web.Response:
    """POST /api/users/delete or DELETE /api/users/{id} - Admin delete a user/bot account."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    try:
        target_id = request.match_info.get("id", "").strip()
        if not target_id:
            try:
                data = await request.json()
                target_id = str(data.get("user_id", "")).strip()
            except Exception:
                pass

        if not target_id:
            return web.json_response({"error": "Missing user_id"}, status=400)

        if target_id == str(ADMIN_CHAT_ID):
            return web.json_response({"error": "Cannot delete main admin"}, status=400)

        if hasattr(app_obj, "storage"):
            deleted = await app_obj.storage.delete_user(target_id)
            if deleted:
                return web.json_response({"status": "ok", "deleted_user_id": target_id})
            return web.json_response({"error": "User not found"}, status=404)

        return web.json_response({"error": "Storage unresolvable"}, status=500)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)

