"""Install/update from a local ZIP extraction. No GitHub account or pip required."""
import argparse
import json
from pathlib import Path
import shutil

CODE_FILES = ("__init__.py", "library.py", "node.py", "routes.py", "image_output.py", "pyproject.toml")


def install(comfyui, data_root=None):
    source = Path(__file__).resolve().parent
    comfyui = Path(comfyui).expanduser().resolve()
    if not (comfyui / "main.py").is_file() or not (comfyui / "custom_nodes").is_dir():
        raise ValueError(f"{comfyui} does not look like a ComfyUI installation (main.py and custom_nodes/ required).")
    target = comfyui / "custom_nodes" / "comfyui-lists-preview"
    target.mkdir(parents=True, exist_ok=True)
    if source != target:
        for name in CODE_FILES:
            shutil.copy2(source / name, target / name)
        shutil.copytree(source / "web", target / "web", dirs_exist_ok=True)
    if data_root:
        data = Path(data_root).expanduser().resolve()
        (target / "config.json").write_text(json.dumps({"data_root": str(data)}, indent=2), encoding="utf-8")
    elif (target / "config.json").is_file():
        data = Path(json.loads((target / "config.json").read_text(encoding="utf-8"))["data_root"])
    else:
        data = target
    for directory in ("texts", "previews", "workflows"):
        bundled = source / directory
        destination = data / directory
        destination.mkdir(parents=True, exist_ok=True)
        if bundled.is_dir():
            for original in bundled.rglob("*"):
                if not original.is_file() or original.name == ".gitkeep":
                    continue
                relative = original.relative_to(bundled)
                output = destination / relative
                if not output.exists():
                    output.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(original, output)
    print(f"Installed: {target}")
    print(f"Lists:     {data / 'texts'}")
    print(f"Previews:  {data / 'previews'}")
    print(f"Workflows: {data / 'workflows'}")
    print("Restart ComfyUI, then refresh its browser tab. Add: Luis/Text > List Preview • Luis")
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comfyui", default="/content/ComfyUI")
    parser.add_argument("--data-root", help="Persistent folder containing texts/ and previews/ (e.g. Google Drive)")
    args = parser.parse_args()
    install(args.comfyui, args.data_root)
