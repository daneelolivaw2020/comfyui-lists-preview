# Paste into one Colab cell, after installing ComfyUI and before starting it.
# Colab Secrets: add GITHUB_TOKEN and enable Notebook access.
# Use a fine-grained token limited to this repository, Contents: Read-only.
from google.colab import drive, userdata
from pathlib import Path
from urllib.parse import quote
import importlib.util
import requests
import tempfile
import zipfile

REPOSITORY = "daneelolivaw2020/comfyui-lists-preview"
REF = "main"
COMFYUI_DIR = "/content/ComfyUI"
DATA_ROOT = "/content/drive/MyDrive/ComfyUI/luis-lists"

if not (Path(COMFYUI_DIR) / "main.py").is_file():
    raise FileNotFoundError("Install ComfyUI first, or correct COMFYUI_DIR.")

token = userdata.get("GITHUB_TOKEN")
if not token:
    raise ValueError("GITHUB_TOKEN is empty. Set it in Colab Secrets.")
drive.mount("/content/drive")
headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
url = f"https://api.github.com/repos/{REPOSITORY}/zipball/{quote(REF, safe='')}"

with tempfile.TemporaryDirectory(prefix="luis-github-") as temp:
    destination = Path(temp).resolve()
    archive_path = destination / "repository.zip"
    with requests.get(url, headers=headers, stream=True, timeout=(15, 120)) as response:
        if response.status_code != 200:
            raise RuntimeError(
                f"GitHub download failed (HTTP {response.status_code}). "
                "Check the repository/ref, token expiration, and Contents: Read-only access."
            )
        with archive_path.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output.write(chunk)
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            if not (destination / member.filename).resolve().is_relative_to(destination):
                raise ValueError("Invalid path in repository archive.")
        archive.extractall(destination)
    installers = list(destination.glob("*/install.py"))
    if len(installers) != 1:
        raise ValueError("Repository archive does not contain the expected node installer.")
    spec = importlib.util.spec_from_file_location("luis_github_installer", installers[0])
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    installer.install(COMFYUI_DIR, DATA_ROOT)

del token, headers
print(f"Installed from {REPOSITORY} ({REF}). Start or restart ComfyUI, then reload its browser tab.")
