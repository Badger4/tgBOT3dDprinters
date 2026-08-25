"""
Spool inventory warehouse management endpoints.
"""

import time

from aiohttp import web

from services.http.auth import check_auth


async def handle_get_spools(request: web.Request) -> web.Response:
    """GET /api/spools - Filament spool inventory."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    spools = await app_obj.storage.load_json(app_obj.storage.spools_file, {})
    return web.json_response(spools)


async def handle_save_spool(request: web.Request) -> web.Response:
    """POST /api/spools - Add or update a spool."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    try:
        data = await request.json()
        spool_id = data.get("id") or f"spool_{int(time.time())}"
        spools = await app_obj.storage.load_json(app_obj.storage.spools_file, {})
        spools[spool_id] = {
            "id": spool_id,
            "name": data.get("name", "Котушка"),
            "type": data.get("type", "PLA"),
            "color": data.get("color", "#ffffff"),
            "remaining_grams": float(data.get("remaining_grams", 1000.0)),
            "quantity": max(1, int(data.get("quantity", 1))),
            "price_per_kg": float(data.get("price_per_kg", 650.0)),
            "notes": data.get("notes", ""),
        }
        await app_obj.storage.save_json(app_obj.storage.spools_file, spools)
        return web.json_response({"status": "ok", "spool": spools[spool_id]})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)


async def handle_delete_spool(request: web.Request) -> web.Response:
    """DELETE /api/spools/{id} - Remove a spool from inventory."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    spool_id = request.match_info.get("id", "")
    spools = await app_obj.storage.load_json(app_obj.storage.spools_file, {})
    if spool_id in spools:
        del spools[spool_id]
        await app_obj.storage.save_json(app_obj.storage.spools_file, spools)
        return web.json_response({"status": "ok"})
    return web.json_response({"error": "Spool not found"}, status=404)


async def handle_export_warehouse_csv(request: web.Request) -> web.Response:
    """GET /api/warehouse/export_csv - Download structured CSV report of spools and parts warehouse."""
    if not await check_auth(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    app_obj = request.app["app_obj"]
    spools = await app_obj.storage.load_spools()
    parts = await app_obj.storage.load_parts()

    from services.report_generator import generate_warehouse_csv_report
    csv_bytes = generate_warehouse_csv_report(spools, parts)

    headers = {
        "Content-Disposition": 'attachment; filename="warehouse_report.csv"',
        "Content-Type": "text/csv; charset=utf-8",
    }
    return web.Response(body=csv_bytes, headers=headers)
