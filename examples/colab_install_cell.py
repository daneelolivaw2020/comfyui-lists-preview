# Paste this entire file into one Colab code cell, before starting ComfyUI.
from google.colab import drive, files
from pathlib import Path
import importlib.util
import shutil
import tempfile
import zipfile

COMFYUI_DIR = "/content/ComfyUI"  # Change if your notebook installs it elsewhere.
DATA_ROOT = Path("/content/drive/MyDrive/ComfyUI/luis-lists")

if not (Path(COMFYUI_DIR) / "main.py").is_file():
    raise FileNotFoundError(f"Install ComfyUI first, or correct COMFYUI_DIR: {COMFYUI_DIR}")

drive.mount("/content/drive")
DATA_ROOT.mkdir(parents=True, exist_ok=True)
ZIP_PATH = DATA_ROOT / "comfyui-lists-preview.zip"

if not ZIP_PATH.is_file():
    print("Upload comfyui-lists-preview.zip (needed only the first time):")
    uploaded = files.upload()
    archives = [name for name in uploaded if name.lower().endswith(".zip")]
    if len(archives) != 1:
        raise ValueError("Upload exactly one comfyui-lists-preview.zip file.")
    shutil.copy2(archives[0], ZIP_PATH)

with tempfile.TemporaryDirectory(prefix="luis-lists-") as temp:
    destination = Path(temp).resolve()
    with zipfile.ZipFile(ZIP_PATH) as archive:
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

print("Ready. Start ComfyUI, then add: Luis/Text > List Preview • Luis")
