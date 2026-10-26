# Paste into one Colab cell, after installing ComfyUI and before starting it.
from google.colab import drive
from pathlib import Path
import subprocess
import sys

COMFYUI_DIR = "/content/ComfyUI"
DATA_ROOT = "/content/drive/MyDrive/ComfyUI/luis-lists"
repository = Path("/content/comfyui-lists-preview")

if not (Path(COMFYUI_DIR) / "main.py").is_file():
    raise FileNotFoundError("Install ComfyUI first, or correct COMFYUI_DIR.")

drive.mount("/content/drive")
if (repository / ".git").is_dir():
    subprocess.run(["git", "-C", str(repository), "pull", "--ff-only"], check=True)
else:
    subprocess.run(["git", "clone", "https://github.com/daneelolivaw2020/comfyui-lists-preview.git", str(repository)], check=True)

subprocess.run([sys.executable, str(repository / "install.py"),
                "--comfyui", COMFYUI_DIR, "--data-root", DATA_ROOT], check=True)
