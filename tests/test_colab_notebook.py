import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

from support import ROOT


class ColabNotebookTests(unittest.TestCase):
    def test_private_github_cell_uses_secret_header_and_installs_library(self):
        import io
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            comfy = base / "ComfyUI"
            comfy.mkdir()
            (comfy / "main.py").touch()
            (comfy / "custom_nodes").mkdir()
            data = base / "Drive" / "lists"
            content = io.BytesIO()
            names = ["install.py", "__init__.py", "library.py", "node.py", "routes.py", "image_output.py", "pyproject.toml", "texts/illumination.txt", "web/list_preview.js", "web/list_browser.js"]
            with zipfile.ZipFile(content, "w") as z:
                for name in names:
                    z.write(ROOT / name, "owner-comfyui-lists-preview-1234/" + name)
                z.writestr("owner-comfyui-lists-preview-1234/texts/additional.txt", "Title: More text")
                z.writestr("owner-comfyui-lists-preview-1234/previews/additional/01.png", b"bundled-preview")
                z.writestr("owner-comfyui-lists-preview-1234/workflows/example.json", "{}")
            class Response:
                status_code = 200
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def iter_content(self, chunk_size): yield content.getvalue()
            def get(url, **kwargs):
                self.assertEqual(kwargs["headers"]["Authorization"], "Bearer fake-colab-secret")
                self.assertNotIn("fake-colab-secret", url)
                self.assertEqual(url, "https://api.github.com/repos/daneelolivaw2020/comfyui-lists-preview/zipball/main")
                return Response()
            colab = types.ModuleType("google.colab")
            colab.drive = types.SimpleNamespace(mount=lambda path: None)
            colab.userdata = types.SimpleNamespace(get=lambda name: "fake-colab-secret" if name == "GITHUB_TOKEN" else None)
            code = (ROOT / "examples/colab_install_github.py").read_text(encoding="utf-8")
            code = code.replace('COMFYUI_DIR = "/content/ComfyUI"', f"COMFYUI_DIR = {str(comfy)!r}")
            code = code.replace('DATA_ROOT = "/content/drive/MyDrive/ComfyUI/luis-lists"', f"DATA_ROOT = {str(data)!r}")
            namespace = {}
            with patch.dict(sys.modules, {"google.colab": colab, "requests": types.SimpleNamespace(get=get)}):
                exec(compile(code, "private-github-colab-cell", "exec"), namespace)
            self.assertNotIn("token", namespace)
            self.assertNotIn("headers", namespace)
            self.assertEqual((data / "texts/additional.txt").read_text(), "Title: More text")
            self.assertEqual((data / "previews/additional/01.png").read_bytes(), b"bundled-preview")
            self.assertTrue((data / "workflows/example.json").is_file())

    def test_update_cell_replaces_cached_zip_and_preserves_user_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            comfy = base / "ComfyUI"
            target = comfy / "custom_nodes" / "comfyui-lists-preview"
            target.mkdir(parents=True)
            (comfy / "main.py").touch()
            data = base / "Drive" / "personal library"
            (data / "texts").mkdir(parents=True)
            (data / "previews" / "illumination").mkdir(parents=True)
            (data / "texts" / "illumination.txt").write_text("Private: preserve this")
            image = data / "previews" / "illumination" / "01.png"
            image.write_bytes(b"personal-image")
            cached = data / "comfyui-lists-preview.zip"
            cached.write_bytes(b"old archive")
            (target / "config.json").write_text(json.dumps({"data_root": str(data)}))
            archive = base / "comfyui-lists-preview-0.2.0.zip"
            with zipfile.ZipFile(archive, "w") as z:
                for name in ["install.py", "__init__.py", "library.py", "node.py", "routes.py", "image_output.py", "pyproject.toml", "texts/illumination.txt", "web/list_preview.js", "web/list_browser.js"]:
                    z.write(ROOT / name, "comfyui-lists-preview/" + name)
            colab = types.ModuleType("google.colab")
            colab.drive = types.SimpleNamespace(mount=lambda path: None)
            colab.files = types.SimpleNamespace(upload=lambda: {str(archive): b""})
            with patch.dict(sys.modules, {"google.colab": colab}):
                code = (ROOT / "examples" / "colab_update_cell.py").read_text(encoding="utf-8")
                exec(compile(code, "colab-update-cell", "exec"), {"COMFYUI_DIR": str(comfy)})
            self.assertEqual(cached.read_bytes(), archive.read_bytes())
            self.assertEqual((data / "texts" / "illumination.txt").read_text(), "Private: preserve this")
            self.assertEqual(image.read_bytes(), b"personal-image")
            self.assertTrue((target / "web" / "list_browser.js").is_file())

    def test_upload_extract_install_cell_end_to_end(self):
        spec = importlib.util.spec_from_file_location("release_builder", ROOT / "tools" / "build_release.py")
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        code = "".join(next(c["source"] for c in builder.notebook()["cells"] if c["cell_type"] == "code"))
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            comfy = base / "ComfyUI"
            comfy.mkdir()
            (comfy / "main.py").touch()
            (comfy / "custom_nodes").mkdir()
            data = base / "Drive" / "lists"
            archive = base / "comfyui-lists-preview.zip"
            with zipfile.ZipFile(archive, "w") as z:
                for name in ["install.py", "__init__.py", "library.py", "node.py", "routes.py", "image_output.py", "pyproject.toml", "texts/illumination.txt", "web/list_preview.js", "web/list_browser.js"]:
                    z.write(ROOT / name, "comfyui-lists-preview/" + name)
            code = code.replace('COMFYUI_DIR = "/content/ComfyUI"', f"COMFYUI_DIR = {str(comfy)!r}")
            code = code.replace('DATA_ROOT = "/content/drive/MyDrive/ComfyUI/luis-lists"', f"DATA_ROOT = {str(data)!r}")
            colab = types.ModuleType("google.colab")
            colab.drive = types.SimpleNamespace(mount=lambda path: None)
            colab.files = types.SimpleNamespace(upload=lambda: {str(archive): b""})
            with patch.dict(sys.modules, {"google.colab": colab}):
                exec(compile(code, "colab-install-cell", "exec"), {})
            target = comfy / "custom_nodes" / "comfyui-lists-preview"
            self.assertTrue((target / "web" / "list_browser.js").is_file())
            self.assertEqual(json.loads((target / "config.json").read_text())["data_root"], str(data))
            self.assertTrue((data / "texts" / "illumination.txt").is_file())
