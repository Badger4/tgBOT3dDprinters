"""
Commercial presets, history, health check, global settings, and WebApp static index routes.
"""

import time
from pathlib import Path
from typing import Any

from aiohttp import web

import config
from config import ADMIN_CHAT_ID, TELEGRAM_BOT_TOKEN, __version__, logger
from models.commercial import calculate_commercial_price
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
    return web.FileResponse(index_file)


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
    """Purges any preset entries containing test / demo / sample markers."""
    if not isinstance(presets, dict):
        return {}
    clean = {}
    test_keywords = {"test", "тест", "тестовий", "sample", "demo"}
    for pid, p in presets.items():
        if not isinstance(p, dict):
            continue
        p_id_str = str(p.get("id") or pid).lower()
        p_name_str = str(p.get("name") or "").lower()
        if any(kw in p_id_str or kw in p_name_str for kw in test_keywords):
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

        name = str(data.get("name") or "Новий пресет").strip()
        test_keywords = {"test", "тест", "тестовий", "sample", "demo"}
        if any(kw in name.lower() or kw in str(p_id).lower() for kw in test_keywords):
            return web.json_response({"error": "Тестові назви пресетів заборонені"}, status=400)

        raw_price = data.get("price_per_g")
        try:
            price_g = float(raw_price) if raw_price is not None else 0.85
        except (ValueError, TypeError):
            price_g = 0.85

        raw_elec = data.get("electricity_rate_uah")
        try:
            elec_rate = float(raw_elec) if raw_elec is not None else 4.32
        except (ValueError, TypeError):
            elec_rate = 4.32

        raw_power = data.get("power_watts")
        try:
            power_w = float(raw_power) if raw_power is not None else 120.0
        except (ValueError, TypeError):
            power_w = 120.0

        presets = await load_commercial_presets(app_obj)
        presets[p_id] = {
            "id": p_id,
            "name": str(data.get("name") or "Новий пресет"),
            "price_per_g": price_g,
            "electricity_rate_uah": elec_rate,
            "power_watts": power_w,
            "depreciation_val": str(data.get("depreciation_val") or "10"),
            "consumables_val": str(data.get("consumables_val") or "5"),
            "profit_val": str(data.get("profit_val") or "100%"),
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
    """GET /api/history/export - Exports completed print jobs history as CSV file."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    if hasattr(app_obj, "storage") and hasattr(app_obj.storage, "load_history"):
        history = await app_obj.storage.load_history()
    else:
        history = await app_obj.storage.load_json(app_obj.storage.history_file, [])

    from services.report_generator import generate_csv_report

    csv_bytes = generate_csv_report(history)
    filename = f"farm_history_{int(time.time())}.csv"
    return web.Response(
        body=csv_bytes,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{filename}',
            "Content-Type": "text/csv; charset=utf-8",
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
        date_str = time.strftime("%Y-%m-%d %H:%M")

        html_content = f"""<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Звіт розрахунку вартості друку</title>
<style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f8fafc; color: #0f172a; margin: 0; padding: 20px; }}
    .card {{ background: #fff; border-radius: 12px; padding: 24px; max-width: 600px; margin: 0 auto; box-shadow: 0 4px 12px rgba(0,0,0,0.05); border: 1px solid #e2e8f0; }}
    .header {{ border-bottom: 2px solid #6366f1; padding-bottom: 12px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }}
    h2 {{ margin: 0; color: #4f46e5; font-size: 20px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; background: #f1f5f9; padding: 14px; border-radius: 8px; margin-bottom: 20px; font-size: 14px; }}
    table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 14px; }}
    th {{ background: #4f46e5; color: #fff; padding: 10px 12px; text-align: left; border-radius: 4px 4px 0 0; }}
    td {{ padding: 10px 12px; border-bottom: 1px solid #e2e8f0; }}
    .total {{ background: #eef2ff; border: 2px solid #6366f1; border-radius: 8px; padding: 16px; text-align: right; font-size: 18px; font-weight: bold; color: #4f46e5; }}
    @media print {{ body {{ background: #fff; padding: 0; }} .card {{ box-shadow: none; max-width: 100%; border: none; }} }}
</style>
</head>
<body>
<div class="card">
    <div class="header">
        <div>
            <h2>📊 Звіт розрахунку вартості друку</h2>
            <small style="color: #64748b;">3D Farm Hub — Комерційне ціноутворення</small>
        </div>
        <div style="font-size: 12px; color: #64748b; text-align: right;"><strong>Дата:</strong><br>{date_str}</div>
    </div>
    <div class="grid">
        <div><strong>Пресет:</strong> {preset_name}</div>
        <div><strong>Вага нитки:</strong> {weight_g:.1f} г</div>
        <div><strong>Час друку:</strong> {time_mins} хв</div>
        <div><strong>Маржа:</strong> {calc.get("profit_margin_pct", 0)}%</div>
    </div>
    <table>
        <thead><tr><th>Стаття витрат</th><th style="text-align:right;">Сума</th></tr></thead>
        <tbody>
            <tr><td>Пластик (матеріал)</td><td style="text-align:right;">{calc.get("filament_cost", 0):.2f} ₴</td></tr>
            <tr><td>Електроенергія</td><td style="text-align:right;">{calc.get("electricity_cost", 0):.2f} ₴</td></tr>
            <tr><td>Амортизація обладнання</td><td style="text-align:right;">{calc.get("depreciation_cost", 0):.2f} ₴</td></tr>
            <tr><td>Витратні матеріали</td><td style="text-align:right;">{calc.get("consumables_cost", 0):.2f} ₴</td></tr>
            <tr style="font-weight:bold; background:#f8fafc;"><td>Собівартість (прямі витрати)</td><td style="text-align:right;">{calc.get("direct_cost", 0):.2f} ₴</td></tr>
            <tr style="font-weight:bold; color:#16a34a; background:#f8fafc;"><td>Прибуток (Маржа)</td><td style="text-align:right;">{calc.get("profit_amount", 0):.2f} ₴</td></tr>
        </tbody>
    </table>
    <div class="total">
        Підсумкова ціна: {calc.get("total_price", 0):.2f} ₴
    </div>
</div>
<script>
    window.onload = function() {{
        setTimeout(function() {{ window.print(); }}, 300);
    }};
</script>
</body>
</html>"""
        return web.Response(text=html_content, content_type="text/html", charset="utf-8")
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


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

