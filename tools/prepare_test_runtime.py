"""Fetch pinned official lightweight execution helpers for standalone regression tests."""
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "4887743a2aef67e05909aeea61f6cdc93e269de3"


def main():
    base = ROOT / ".test-runtime" / "comfy-source"
    for name in ("comfy_execution/graph_utils.py", "execution.py"):
        target = base / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(urlopen(f"https://raw.githubusercontent.com/Comfy-Org/ComfyUI/{COMMIT}/{name}", timeout=30).read())
    (base / "UPSTREAM_COMMIT").write_text(COMMIT, encoding="utf-8")
    print(f"Prepared official execution test helpers at {COMMIT}")


if __name__ == "__main__":
    main()
