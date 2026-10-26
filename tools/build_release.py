"""Build a private, dependency-free install ZIP and a Colab installer notebook."""
import json
from pathlib import Path
import zipfile
import shutil

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def notebook():
    setup = '''from google.colab import drive, files
from pathlib import Path
import importlib.util
import shutil
import tempfile
import zipfile

# Change these if your usual Colab notebook uses different locations.
COMFYUI_DIR = "/content/ComfyUI"
DATA_ROOT = "/content/drive/MyDrive/ComfyUI/luis-lists"

drive.mount("/content/drive")
print("Upload comfyui-lists-preview.zip from the delivered files:")
uploaded = files.upload()
archives = [name for name in uploaded if name.lower().endswith(".zip")]
if len(archives) != 1:
    raise ValueError("Upload exactly one comfyui-lists-preview.zip file.")

with tempfile.TemporaryDirectory(prefix="luis-lists-") as temp:
    destination = Path(temp).resolve()
    with zipfile.ZipFile(archives[0]) as archive:
        for member in archive.infolist():
            if not (destination / member.filename).resolve().is_relative_to(destination):
                raise ValueError("Invalid path inside ZIP.")
        archive.extractall(destination)
    installer = destination / "comfyui-lists-preview" / "install.py"
    if not installer.is_file():
        raise ValueError("This ZIP does not contain the List Preview installer.")
    spec = importlib.util.spec_from_file_location("luis_list_installer", installer)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.install(COMFYUI_DIR, DATA_ROOT)
'''
    return {"nbformat": 4, "nbformat_minor": 5,
            "metadata": {"colab": {"name": "Install List Preview • Luis"}, "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
            "cells": [
                {"cell_type": "markdown", "id": "instructions", "metadata": {}, "source": ["# Install List Preview • Luis\n", "Run this after installing ComfyUI and before starting its server. Upload the private ZIP when prompted. Your lists and previews stay in Google Drive. No GPU is needed for installation.\n", "\n", "On each fresh Colab session, rerun this cell before launching ComfyUI. If ComfyUI is already running, restart its process afterward, then reload the browser tab.\n"]},
                {"cell_type": "code", "id": "install", "metadata": {}, "execution_count": None, "outputs": [], "source": setup.splitlines(keepends=True)},
                {"cell_type": "markdown", "id": "next", "metadata": {}, "source": ["## Next\n", "Start ComfyUI using your usual launch cell. Add **Luis/Text → List Preview • Luis**.\n", "\n", "Put UTF-8 `.txt` files in `/content/drive/MyDrive/ComfyUI/luis-lists/texts/` and matching numbered images in `previews/<file name without .txt>/`. Click **Reload files** after adding files.\n", "\n", "The bundled `illumination.txt` is installed only if that file does not already exist. Add your own `previews/illumination/01.png`, `02.png`, etc.\n"]},
            ]}


def main():
    DIST.mkdir(exist_ok=True)
    notebook_path = DIST / "Install_in_Colab.ipynb"
    notebook_path.write_text(json.dumps(notebook(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths = [ROOT / name for name in ("__init__.py", "library.py", "node.py", "routes.py", "image_output.py", "install.py", "Install_from_GitHub.ipynb", "README.md", "TESTING.md", "ROADMAP.md", "pyproject.toml", "package.json", ".gitignore")]
    for directory in ["web", "texts", "previews", "workflows", "tests", "tools", "examples"]:
        base = ROOT / directory
        if base.exists():
            paths.extend(p for p in base.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    archive_path = DIST / "comfyui-lists-preview.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            archive.write(path, Path("comfyui-lists-preview") / path.relative_to(ROOT))
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
    version = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]
    shutil.copy2(archive_path, DIST / f"comfyui-lists-preview-{version}.zip")
    shutil.copy2(ROOT / "examples/colab_update_cell.py", DIST / "Update_cell.py")
    print(f"{archive_path} ({archive_path.stat().st_size:,} bytes)")
    print(notebook_path)


if __name__ == "__main__":
    main()
