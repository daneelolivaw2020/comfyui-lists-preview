"""Read-only library API. ComfyUI already provides aiohttp."""
import asyncio

from .library import list_files, payload, preview_folder_for, preview_path, read_text
from .image_output import clear_image_cache


def register_routes():
    from aiohttp import web
    from server import PromptServer

    routes = PromptServer.instance.routes

    def json_response(body, status=200):
        return web.json_response(body, status=status, headers={"Cache-Control": "no-store"})

    def error(exc):
        return json_response({"error": str(exc)}, status=400)

    @routes.get("/luis-lists/files")
    async def files(request):
        try:
            clear_image_cache()
            return json_response({"files": await asyncio.to_thread(list_files)})
        except (OSError, ValueError) as exc:
            return error(exc)

    @routes.get("/luis-lists/list")
    async def get_list(request):
        try:
            name = request.query.get("file", "")
            folder = preview_folder_for(name, request.query.get("folder", ""))
            text = await asyncio.to_thread(read_text, name)
            return json_response(await asyncio.to_thread(payload, text, folder))
        except (ValueError, OSError) as exc:
            return error(exc)

    @routes.post("/luis-lists/parse")
    async def parse(request):
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("Expected a JSON object.")
            name = body.get("file", "")
            folder = preview_folder_for(name if name != "(no files)" else "", body.get("folder", ""))
            return json_response(await asyncio.to_thread(payload, body.get("text", ""), folder))
        except (ValueError, OSError, TypeError, AttributeError) as exc:
            return error(exc)

    @routes.get("/luis-lists/preview")
    async def preview(request):
        try:
            path = preview_path(request.query.get("folder", ""), request.query.get("file", ""))
            return web.FileResponse(path, headers={"Cache-Control": "no-store"})
        except (ValueError, OSError) as exc:
            return json_response({"error": str(exc)}, status=404)
