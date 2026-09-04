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
    """GET /api/spools/movements - Retrieve warehouse audit movement log."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    spool_id_filter = request.query.get("spool_id", "").strip()

    movements = await app_obj.storage.load_spool_movements()
    if spool_id_filter:
        movements = [m for m in movements if m.get("spool_id") == spool_id_filter]

    # Return sorted descending by timestamp
    movements = sorted(movements, key=lambda x: x.get("timestamp", 0), reverse=True)
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

        spools[spool_id] = {
            "id": spool_id,
            "name": spool_name,
            "type": data.get("type", existing.get("type", "PLA")),
            "color": data.get("color", existing.get("color", "#ffffff")),
            "remaining_grams": new_weight,
            "quantity": max(1, int(data.get("quantity", existing.get("quantity", 1)))),
            "price_per_kg": float(data.get("price_per_kg", existing.get("price_per_kg", 650.0))),
            "notes": data.get("notes", existing.get("notes", "")),
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
        pdf_bytes = generate_warehouse_pdf_report(spools, parts, report_type=report_type)

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
                    status_text = f"Слот {slot}" if slot else "На складі"

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

        html_content = f"""<!DOCTYPE html>
<html lang="uk">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Звіт складу пластику</title>
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
    table {{ width: 100%; border-collapse: collapse; margin-bottom: 12px; font-size: 10.5px; table-layout: fixed; }}
    th, td {{ padding: 5px 6px; border: 1px solid #cbd5e1; word-wrap: break-word; overflow-wrap: break-word; }}
    th {{ background: #4f46e5 !important; color: #fff !important; font-weight: 600; text-align: left; }}
    tr:nth-child(even) {{ background: #f8fafc; }}
    .btn-print {{ display: block; width: 100%; max-width: 240px; margin: 0 auto 12px; padding: 8px 16px; background: #4f46e5; color: #fff; text-align: center; border: none; border-radius: 6px; font-size: 13px; font-weight: bold; cursor: pointer; text-decoration: none; }}
    @media print {{
        body {{ background: #fff; padding: 0; }}
        .container {{ box-shadow: none; border: none; padding: 0; max-width: 100%; }}
        .no-print {{ display: none !important; }}
    }}
</style>
</head>
<body>
<div class="container">
    <div class="no-print">
        <button onclick="window.print()" class="btn-print">🖨️ Зберегти як PDF / Друк</button>
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
<script>
    window.onload = function() {{ setTimeout(function() {{ window.print(); }}, 400); }};
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
        movements = await app_obj.storage.load_spool_movements()

        from services.report_generator import generate_movements_pdf_report
        pdf_bytes = generate_movements_pdf_report(movements)

        headers = {
            "Content-Disposition": 'attachment; filename="spool_movements_audit.pdf"; filename*=UTF-8\'\'spool_movements_audit.pdf',
            "Content-Type": "application/pdf",
        }
        return web.Response(body=pdf_bytes, headers=headers)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_export_movements_csv(request: web.Request) -> web.Response:
    """GET /api/spools/movements/export_csv - Redirect/Return PDF report."""
    return await handle_export_movements_pdf(request)

