# Paste into one Colab cell. Stop ComfyUI before running this update.
from google.colab import drive, files
from pathlib import Path
import importlib.util
import json
import shutil
import tempfile
import zipfile

COMFYUI_DIR = globals().get("COMFYUI_DIR", "/content/ComfyUI")
comfy = Path(COMFYUI_DIR)
if not (comfy / "main.py").is_file():
    raise FileNotFoundError("Correct COMFYUI_DIR to your existing ComfyUI folder.")
drive.mount("/content/drive")
config = comfy / "custom_nodes/comfyui-lists-preview/config.json"
data_root = Path(json.loads(config.read_text())["data_root"]) if config.is_file() else Path("/content/drive/MyDrive/ComfyUI/luis-lists")
data_root.mkdir(parents=True, exist_ok=True)

print("Upload the NEW comfyui-lists-preview ZIP (version 0.2.0):")
uploaded = files.upload()
archives = [name for name in uploaded if name.lower().endswith(".zip")]
if len(archives) != 1:
    raise ValueError("Upload exactly one updated node ZIP.")

with tempfile.TemporaryDirectory(prefix="luis-update-") as temp:
    destination = Path(temp).resolve()
    with zipfile.ZipFile(archives[0]) as archive:
        for member in archive.infolist():
            if not (destination / member.filename).resolve().is_relative_to(destination):
                raise ValueError("Invalid path inside ZIP.")
        archive.extractall(destination)
    installer = destination / "comfyui-lists-preview/install.py"
    spec = importlib.util.spec_from_file_location("luis_list_updater", installer)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.install(COMFYUI_DIR, data_root)
    cached_zip = data_root / "comfyui-lists-preview.zip"
    if Path(archives[0]).resolve() != cached_zip.resolve():
        shutil.copy2(archives[0], cached_zip)

print("Update installed. Restart ComfyUI and hard-refresh its browser tab (Ctrl+Shift+R).")
print("Open Library folders in the node to confirm version 0.2.0 and the preview path.")
