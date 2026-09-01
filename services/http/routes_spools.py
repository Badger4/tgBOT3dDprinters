"""
Spool inventory warehouse management endpoints with audit movement logs.
"""

import time
from aiohttp import web

from services.http.auth import check_auth


async def handle_get_spools(request: web.Request) -> web.Response:
    """GET /api/spools - Filament spool inventory with warehouse financial summary."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    spools = await app_obj.storage.load_json(app_obj.storage.spools_file, {})

    total_spools = 0
    total_weight_g = 0.0
    total_value_uah = 0.0

    if isinstance(spools, dict):
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
        spools = await app_obj.storage.load_json(app_obj.storage.spools_file, {})
        is_existing = spool_id in spools
        existing = spools.get(spool_id, {})

        prev_weight = float(existing.get("remaining_grams", 0.0))
        new_weight = float(data.get("remaining_grams", 1000.0))
        spool_name = data.get("name", existing.get("name", "Котушка"))

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
        await app_obj.storage.save_json(app_obj.storage.spools_file, spools)

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
    spools = await app_obj.storage.load_json(app_obj.storage.spools_file, {})
    if spool_id in spools:
        spool = spools.pop(spool_id)
        await app_obj.storage.save_json(app_obj.storage.spools_file, spools)

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


async def handle_export_warehouse_csv(request: web.Request) -> web.Response:
    """GET /api/warehouse/export_csv - Download structured CSV report of spools/parts warehouse."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        app_obj = request.app["app_obj"]
        spools = await app_obj.storage.load_spools()
        parts = await app_obj.storage.load_parts()
        report_type = request.query.get("type", "spools")

        from services.report_generator import generate_warehouse_csv_report
        csv_bytes = generate_warehouse_csv_report(spools, parts, report_type=report_type)

        filename = "parts_report.csv" if report_type == "parts" else "spools_report.csv"
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{filename}',
            "Content-Type": "text/csv; charset=utf-8",
        }
        return web.Response(body=csv_bytes, headers=headers)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_export_movements_csv(request: web.Request) -> web.Response:
    """GET /api/spools/movements/export_csv - Download CSV report of warehouse audit movement logs."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        app_obj = request.app["app_obj"]
        movements = await app_obj.storage.load_spool_movements()

        from services.report_generator import generate_movements_csv_report
        csv_bytes = generate_movements_csv_report(movements)

        headers = {
            "Content-Disposition": 'attachment; filename="spool_movements_audit.csv"; filename*=UTF-8\'\'spool_movements_audit.csv',
            "Content-Type": "text/csv; charset=utf-8-sig",
        }
        return web.Response(body=csv_bytes, headers=headers)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)
