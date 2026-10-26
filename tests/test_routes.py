import sys
import types
import unittest

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from support import ROOT
import test_core
from luis_lists_test.routes import register_routes


class RouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fixture = test_core.LibraryFixture()
        self.fixture.setUp()
        routes = web.RouteTableDef()
        self.original_server = sys.modules.get("server")
        sys.modules["server"] = types.SimpleNamespace(PromptServer=types.SimpleNamespace(instance=types.SimpleNamespace(routes=routes)))
        register_routes()
        app = web.Application(client_max_size=3 * 1024 * 1024)
        app.add_routes(routes)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        if self.original_server is None:
            sys.modules.pop("server", None)
        else:
            sys.modules["server"] = self.original_server
        self.fixture.tearDown()

    async def test_refresh_and_file_load(self):
        response = await self.client.get("/luis-lists/files")
        self.assertEqual((await response.json())["files"], ["illumination.txt"])
        response = await self.client.get("/luis-lists/list?file=illumination.txt")
        body = await response.json()
        self.assertEqual(body["text"], test_core.SAMPLE)
        self.assertEqual(body["folder"], "illumination")
        self.assertEqual(len(body["entries"]), 3)

    async def test_reload_reports_paths_and_bypasses_caches(self):
        directory = self.fixture.root / "previews" / "illumination"
        directory.mkdir(parents=True)
        response = await self.client.get("/luis-lists/list?file=illumination.txt&reload=first")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        before = await response.json()
        self.assertEqual(before["preview_directory"], str(directory.resolve()))
        self.assertTrue(before["preview_folder_exists"])
        self.assertIsNone(before["entries"][0]["preview"])
        (directory / "01.png").write_bytes(b"new-image")
        response = await self.client.get("/luis-lists/list?file=illumination.txt&reload=second")
        self.assertEqual((await response.json())["entries"][0]["preview"], "01.png")
        response = await self.client.get("/luis-lists/preview?folder=illumination&file=01.png&reload=second")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(await response.read(), b"new-image")
        (directory / "01.png").write_bytes(b"replacement")
        response = await self.client.get("/luis-lists/preview?folder=illumination&file=01.png&reload=third")
        self.assertEqual(await response.read(), b"replacement")
        (directory / "01.png").unlink()
        response = await self.client.get("/luis-lists/list?file=illumination.txt&reload=fourth")
        self.assertIsNone((await response.json())["entries"][0]["preview"])

    async def test_pasted_text_keeps_selected_file_preview_folder(self):
        response = await self.client.post("/luis-lists/parse", json={"text":"One: pasted", "file":"illumination.txt"})
        self.assertEqual((await response.json())["folder"], "illumination")

    async def test_missing_file_and_traversal(self):
        for path in ["/luis-lists/list?file=missing.txt", "/luis-lists/list?file=../secret.txt", "/luis-lists/list?file=illumination.txt&folder=../secret"]:
            response = await self.client.get(path)
            self.assertEqual(response.status, 400)
            self.assertIn("error", await response.json())

    async def test_post_text_and_bad_json(self):
        response = await self.client.post("/luis-lists/parse", json={"text": "01 Café: Warm: glow"})
        self.assertEqual((await response.json())["entries"][0]["description"], "Warm: glow")
        for data in [[], {"text": []}, {"text": "ok", "folder": 3}]:
            response = await self.client.post("/luis-lists/parse", json=data)
            self.assertEqual(response.status, 400)
        response = await self.client.post("/luis-lists/parse", data="broken", headers={"Content-Type": "application/json"})
        self.assertEqual(response.status, 400)

    async def test_images_and_disallowed_files(self):
        directory = self.fixture.root / "previews" / "illumination"
        directory.mkdir(parents=True)
        (directory / "01.png").write_bytes(b"test-png")
        (directory / "01.txt").write_text("private")
        response = await self.client.get("/luis-lists/preview?folder=illumination&file=01.png")
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.read(), b"test-png")
        for name in ["01.txt", "missing.png", "../../secret.png"]:
            response = await self.client.get("/luis-lists/preview", params={"folder": "illumination", "file": name})
            self.assertEqual(response.status, 404)


if __name__ == "__main__":
    unittest.main()
