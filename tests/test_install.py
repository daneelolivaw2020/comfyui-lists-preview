import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from support import ROOT

spec = importlib.util.spec_from_file_location("installer", ROOT / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def test_install_and_update_preserve_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            comfy = Path(tmp) / "ComfyUI"
            comfy.mkdir()
            (comfy / "main.py").touch()
            (comfy / "custom_nodes").mkdir()
            data = Path(tmp) / "persistent"
            target = installer.install(comfy, data)
            self.assertTrue((target / "web" / "list_preview.js").is_file())
            self.assertTrue((data / "texts" / "illumination.txt").is_file())
            for directory in ("texts", "previews", "workflows"):
                source = ROOT / directory
                if source.is_dir():
                    for original in source.rglob("*"):
                        if original.is_file() and original.name != ".gitkeep":
                            copied = data / directory / original.relative_to(source)
                            self.assertEqual(copied.read_bytes(), original.read_bytes())
            (data / "texts" / "illumination.txt").write_text("Personal: keep this")
            personal = data / "previews" / "illumination" / "01.png"
            personal.parent.mkdir(parents=True, exist_ok=True)
            personal.write_bytes(b"personal-preview-to-keep")
            installer.install(comfy)
            self.assertEqual((data / "texts" / "illumination.txt").read_text(), "Personal: keep this")
            self.assertEqual(personal.read_bytes(), b"personal-preview-to-keep")
            self.assertEqual(json.loads((target / "config.json").read_text())["data_root"], str(data.resolve()))
            # Exercise ComfyUI's real package-loading mechanism, not just direct class imports.
            from aiohttp import web
            routes = web.RouteTableDef()
            server = types.SimpleNamespace(PromptServer=types.SimpleNamespace(instance=types.SimpleNamespace(routes=routes)))
            with patch.dict("sys.modules", {"server": server}):
                spec = importlib.util.spec_from_file_location("installed_luis_lists", target / "__init__.py", submodule_search_locations=[str(target)])
                module = importlib.util.module_from_spec(spec)
                with patch.dict("sys.modules", {"installed_luis_lists": module}):
                    spec.loader.exec_module(module)
                    self.assertIn("LuisListPreview", module.NODE_CLASS_MAPPINGS)
                    self.assertEqual(module.WEB_DIRECTORY, "./web")
                    self.assertEqual(len(routes), 4)

    def test_invalid_comfyui_path(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            installer.install(tmp)
