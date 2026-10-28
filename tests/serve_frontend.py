"""Real ComfyUI production frontend + real extension/routes, lightweight queue host.

No image model or GPU is loaded. This host is exclusively a development fixture.
"""
import asyncio
import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import types
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / ".test-deps"), str(ROOT / "tests")]
from support import ROOT, ExecutionBlocker
from aiohttp import web
from PIL import Image, ImageDraw
import comfyui_frontend_package
from luis_lists_test.node import ListPreview
from luis_lists_test.routes import register_routes

RUNTIME = ROOT / ".test-runtime"
DATA = RUNTIME / "library"
(DATA / "texts").mkdir(parents=True, exist_ok=True)
shutil.copyfile(ROOT / "texts" / "illumination.txt", DATA / "texts" / "illumination.txt")
folder = DATA / "previews" / "illumination"
folder.mkdir(parents=True, exist_ok=True)
colors = [("#a837b4", "#102b4a"), ("#edbc72", "#58372c"), ("#9cbac0", "#263c50"), ("#b7793b", "#152a3b"), ("#f4a34c", "#592958"), ("#b1d984", "#154c3f"), ("#d09a6a", "#473938"), ("#8b9da7", "#1a354b")]
for index, (top, bottom) in enumerate(colors, 1):
    image = Image.new("RGB", (320, 240), bottom)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 320, 130), fill=top)
    draw.polygon([(0, 180), (120, 90), (220, 170), (320, 70), (320, 240), (0, 240)], fill=bottom)
    draw.text((12, 12), f"QA thumbnail {index:02}", fill="white")
    image.save(folder / f"{index:02}.png")
os.environ["COMFYUI_LISTS_ROOT"] = str(DATA)

routes = web.RouteTableDef()
sys.modules["server"] = types.SimpleNamespace(PromptServer=types.SimpleNamespace(instance=types.SimpleNamespace(routes=routes)))
register_routes()
clients = set()
instances = {}
histories = {}
observed = []
current_context = None
queue_lock = asyncio.Lock()
qa = {"metadata": True, "success_event": True, "context": True, "outcome": "success"}
sys.modules["server"].PromptServer.instance.prompt_queue = types.SimpleNamespace(get_history=lambda prompt_id: {prompt_id: histories[prompt_id]} if prompt_id in histories else {})
sys.modules["comfy_execution"] = types.ModuleType("comfy_execution")
sys.modules["comfy_execution.utils"] = types.SimpleNamespace(get_executing_context=lambda: current_context)
settings = {"Comfy.TutorialCompleted": True, "Comfy.UseNewMenu": "Top", "Comfy.Workflow.WorkflowTabsPosition": "Topbar", "Comfy.NodeSearchBoxImpl": "default"}


def info():
    return {"LuisListPreview": {"input": ListPreview.INPUT_TYPES(), "input_order": {k: list(v) for k, v in ListPreview.INPUT_TYPES().items()}, "output": list(ListPreview.RETURN_TYPES), "output_name": list(ListPreview.RETURN_NAMES), "output_is_list": [False]*6, "name": "LuisListPreview", "display_name": "List Preview • Luis", "description": ListPreview.DESCRIPTION, "category": ListPreview.CATEGORY, "output_node": True, "python_module": "custom_nodes.comfyui_lists_preview"},
            "TestListSource": {"input": {"required": {"value": ["STRING", {"multiline": True, "default": "One: Alpha\\nTwo: Beta"}]}}, "output": ["STRING"], "output_name": ["text"], "output_is_list": [False], "name": "TestListSource", "display_name": "Test List Source", "description": "QA fixture", "category": "testing", "output_node": False, "python_module": "testing"},
            "TestImageSink": {"input": {"required": {"images":["IMAGE",{}]}}, "output": [], "output_name":[], "output_is_list":[], "name":"TestImageSink", "display_name":"Test Image Sink", "description":"QA image consumer", "category":"testing", "output_node":True, "python_module":"testing"},
            "TestTextSink": {"input": {"required": {"text":["STRING",{"forceInput":True}]}}, "output":[], "output_name":[], "output_is_list":[], "name":"TestTextSink", "display_name":"Test Text Sink", "description":"QA text consumer", "category":"testing", "output_node":True, "python_module":"testing"}}


@routes.get("/ws")
async def websocket(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    clients.add(ws)
    await ws.send_json({"type": "status", "data": {"sid": "test-session", "status": {"exec_info": {"queue_remaining": 0}}}})
    try:
        async for message in ws:
            pass
    finally:
        clients.discard(ws)
    return ws


@routes.post("/prompt")
async def prompt(request):
    body = await request.json()
    prompt_id = str(uuid.uuid4())
    options = dict(qa)
    async def execute_inner():
        global current_context
        await asyncio.sleep(options.get("start_delay", 0.05))
        for ws in list(clients):
            await ws.send_json({"type": "execution_start", "data": {"prompt_id": prompt_id}})
        results = {}
        for node_id, item in body["prompt"].items():
            if item["class_type"] != "LuisListPreview":
                continue
            await asyncio.sleep(options.get("node_delay", 0))
            instance = instances.setdefault(node_id, ListPreview())
            current_context = types.SimpleNamespace(prompt_id=prompt_id) if options["context"] else None
            inputs = dict(item["inputs"])
            for key, value in inputs.items():
                if isinstance(value, list):
                    inputs[key] = body["prompt"][str(value[0])]["inputs"]["value"]
            result = instance.select(**inputs, prompt=body["prompt"], unique_id=node_id, extra_pnginfo=body.get("extra_data", {}).get("extra_pnginfo") if options["metadata"] else None)
            results[node_id] = result["result"]
            image = result["result"][5]
            recorded = dict(result["ui"]["list_preview"][0]["selected_outputs"])
            recorded.update(prompt_id=prompt_id, node_id=node_id,
                            image_shape=None if isinstance(image,ExecutionBlocker) else list(image.shape))
            observed.append(recorded)
            del observed[:-100]
            for ws in list(clients):
                await ws.send_json({"type": "executed", "data": {"node": node_id, "display_node": node_id, "prompt_id": prompt_id, "output": result["ui"]}})
        for node_id,item in body["prompt"].items():
            if item["class_type"] == "TestTextSink":
                source,slot = item["inputs"]["text"]
                observed.append({"text_sink":node_id,"value":results[str(source)][slot],"prompt_id":prompt_id})
                continue
            if item["class_type"] != "TestImageSink": continue
            source,slot = item["inputs"]["images"]
            image = results[str(source)][slot]
            if isinstance(image,ExecutionBlocker):
                observed.append({"sink":node_id,"skipped":True,"prompt_id":prompt_id})
                continue
            # Consume the emitted tensor as an image node would, without reloading its source.
            output_dir = RUNTIME / "executed"
            output_dir.mkdir(exist_ok=True)
            filename = f"{prompt_id}-{node_id}.png"
            Image.fromarray((image[0].numpy()*255).round().astype("uint8")).save(output_dir/filename)
            observed.append({"sink":node_id,"skipped":False,"prompt_id":prompt_id,"image_shape":list(image.shape)})
            for ws in list(clients):
                await ws.send_json({"type":"executed","data":{"node":node_id,"display_node":node_id,"prompt_id":prompt_id,
                    "output":{"images":[{"filename":filename,"type":"temp","subfolder":""}]}}})
        await asyncio.sleep(0.5)  # Simulate work downstream from the selector.
        histories[prompt_id] = {"status": {"status_str": "success" if options["outcome"] == "success" else "error"}}
        for ws in list(clients):
            if options["outcome"] != "success":
                await ws.send_json({"type": "execution_interrupted", "data": {"prompt_id": prompt_id, "node_id": "downstream", "node_type": "testing", "executed": []}})
            elif options["success_event"]:
                await ws.send_json({"type": "execution_success", "data": {"prompt_id": prompt_id}})
        for ws in list(clients):
            await ws.send_json({"type": "executing", "data": {"node": None, "prompt_id": prompt_id}})
    async def execute():
        async with queue_lock:
            await execute_inner()
    asyncio.create_task(execute())
    return web.json_response({"prompt_id": prompt_id, "number": 1, "node_errors": {}})


@routes.post("/qa/settings")
async def qa_settings(request):
    qa.update(await request.json())
    return web.json_response(qa)


@routes.get("/qa/observed")
async def qa_observed(request):
    return web.json_response(observed)


@routes.get("/view")
async def view(request):
    name = Path(request.query.get("filename", "")).name
    path = RUNTIME / "executed" / name
    return web.FileResponse(path) if path.is_file() else web.Response(status=404)


@routes.get("/extensions")
async def extensions(request):
    return web.json_response(["/extensions/luis/list_preview.js"])


@routes.route("*", "/{path:.*}")
async def fallback(request):
    path = request.match_info["path"]
    if path.startswith("api/"):
        path = path[4:]
    if path == "object_info": return web.json_response(info())
    if path.startswith("object_info/"): return web.json_response(info())
    if path == "settings": return web.json_response(settings)
    if path.startswith("settings/"):
        if request.method == "POST": settings[path[9:]] = await request.json()
        return web.json_response(None)
    if path == "users": return web.json_response({"storage": "server", "migrated": True})
    if path == "system_stats": return web.json_response({"system": {"os": "test", "python_version": sys.version, "embedded_python": False, "comfyui_version": "0.3.test", "pytorch_version": "test", "argv": []}, "devices": []})
    if path == "features": return web.json_response({})
    if path == "queue": return web.json_response({"queue_running": [], "queue_pending": []})
    if path == "history": return web.json_response({})
    if path == "prompt": return web.json_response({"exec_info": {"queue_remaining": 0}})
    if path in ("embeddings", "models", "userdata", "templates", "workflow_templates", "subgraphs"): return web.json_response([])
    if path.startswith("userdata/"): return web.Response(status=404)
    if path == "extensions": return await extensions(request)
    if path.startswith("extensions/luis/"):
        file = ROOT / "web" / Path(path).name
        if file.is_file(): return web.FileResponse(file)
    base = Path(comfyui_frontend_package.__file__).parent / "static"
    file = (base / (path or "index.html")).resolve()
    if file.is_relative_to(base.resolve()) and file.is_file(): return web.FileResponse(file)
    return web.json_response({"error": path}, status=404)

app = web.Application(client_max_size=3 * 1024 * 1024)
api_routes = web.RouteTableDef()
for route in routes:
    if route.path != "/{path:.*}":
        api_routes.route(route.method, "/api" + route.path)(route.handler, **route.kwargs)
app.add_routes(api_routes)
app.add_routes(routes)
if __name__ == "__main__":
    web.run_app(app, host="127.0.0.1", port=8189)
