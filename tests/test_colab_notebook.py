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
    def test_public_github_cell_clones_updates_and_preserves_library(self):
        import shutil
        import subprocess
        real_run = subprocess.run
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            comfy = base / "ComfyUI"
            comfy.mkdir()
            (comfy / "main.py").touch()
            (comfy / "custom_nodes").mkdir()
            data = base / "Drive" / "lists"
            repository = base / "repository"
            fixture = base / "remote-fixture"
            for name in ["install.py", "__init__.py", "library.py", "node.py", "routes.py", "image_output.py", "pyproject.toml", "texts/illumination.txt", "web/list_preview.js", "web/list_browser.js", "web/execution_tracking.js"]:
                destination = fixture / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / name, destination)
            (fixture / "previews/additional").mkdir(parents=True)
            (fixture / "previews/additional/01.png").write_bytes(b"bundled-image")
            (fixture / "workflows").mkdir()
            (fixture / "workflows/example.json").write_text("{}")
            commands = []
            def run(command, check):
                self.assertTrue(check)
                commands.append(command)
                if command[:2] == ["git", "clone"]:
                    self.assertEqual(command[2], "https://github.com/daneelolivaw2020/comfyui-lists-preview.git")
                    shutil.copytree(fixture, command[3])
                    (Path(command[3]) / ".git").mkdir()
                elif command[0] == "git":
                    self.assertEqual(command[1:], ["-C", str(repository), "pull", "--ff-only"])
                else:
                    return real_run(command, check=True, capture_output=True, text=True)
            colab = types.ModuleType("google.colab")
            colab.drive = types.SimpleNamespace(mount=lambda path: None)
            code = (ROOT / "examples/colab_install_github.py").read_text(encoding="utf-8")
            self.assertNotIn("userdata", code)
            self.assertNotIn("GITHUB_TOKEN", code)
            code = code.replace('COMFYUI_DIR = "/content/ComfyUI"', f"COMFYUI_DIR = {str(comfy)!r}")
            code = code.replace('DATA_ROOT = "/content/drive/MyDrive/ComfyUI/luis-lists"', f"DATA_ROOT = {str(data)!r}")
            code = code.replace('Path("/content/comfyui-lists-preview")', f"Path({str(repository)!r})")
            with patch.dict(sys.modules, {"google.colab": colab, "subprocess": types.SimpleNamespace(run=run)}):
                exec(compile(code, "public-github-colab-cell", "exec"), {})
                self.assertEqual((data / "previews/additional/01.png").read_bytes(), b"bundled-image")
                self.assertTrue((data / "workflows/example.json").is_file())
                (data / "texts/illumination.txt").write_text("Personal: preserve")
                exec(compile(code, "public-github-colab-cell", "exec"), {})
            self.assertEqual((data / "texts/illumination.txt").read_text(), "Personal: preserve")
            self.assertEqual(sum(c[:2] == ["git", "clone"] for c in commands), 1)
            self.assertEqual(sum("pull" in c for c in commands), 1)

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
            archive = base / "comfyui-lists-preview-0.2.1.zip"
            with zipfile.ZipFile(archive, "w") as z:
                for name in ["install.py", "__init__.py", "library.py", "node.py", "routes.py", "image_output.py", "pyproject.toml", "texts/illumination.txt", "web/list_preview.js", "web/list_browser.js", "web/execution_tracking.js"]:
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
            self.assertTrue((target / "web" / "execution_tracking.js").is_file())

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
                for name in ["install.py", "__init__.py", "library.py", "node.py", "routes.py", "image_output.py", "pyproject.toml", "texts/illumination.txt", "web/list_preview.js", "web/list_browser.js", "web/execution_tracking.js"]:
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
            self.assertTrue((target / "web" / "execution_tracking.js").is_file())
            self.assertEqual(json.loads((target / "config.json").read_text())["data_root"], str(data))
            self.assertTrue((data / "texts" / "illumination.txt").is_file())
