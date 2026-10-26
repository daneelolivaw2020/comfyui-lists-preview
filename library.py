"""Filesystem and parsing shared by the node and HTTP routes (no Comfy imports)."""
from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import json
import os
import re

MAX_TEXT_BYTES = 2 * 1024 * 1024
VERSION = "0.2.0"
MAX_ENTRIES = 10000
NUMBER = re.compile(r"^([0-9]+)(?:[.)\-:]\s+|\s+)(.+)$")
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


@dataclass(frozen=True)
class Entry:
    row: int
    number: int
    title: str
    description: str
    text: str


def parse_text(text):
    if not isinstance(text, str):
        raise ValueError("The list must be a STRING containing one entry per line.")
    if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        raise ValueError("List exceeds the 2 MiB limit.")
    entries = []
    for line in text.lstrip("\ufeff").splitlines():
        line = line.strip()
        if not line:
            continue
        match = NUMBER.match(line)
        number = int(match[1]) if match else len(entries) + 1
        body = match[2].strip() if match else line
        title, separator, description = body.partition(":")
        title = title.strip() if separator else ""
        description = description.strip() if separator else body
        entries.append(Entry(len(entries) + 1, number, title, description, body))
        if len(entries) > MAX_ENTRIES:
            raise ValueError("List exceeds the 10,000-entry limit.")
    return entries


def data_root():
    root = os.environ.get("COMFYUI_LISTS_ROOT")
    config = Path(__file__).parent / "config.json"
    if not root and config.is_file():
        try:
            root = json.loads(config.read_text(encoding="utf-8")).get("data_root")
            if root is not None and not isinstance(root, str):
                raise ValueError("data_root must be a path string.")
        except (OSError, ValueError, AttributeError) as exc:
            raise ValueError(f"Invalid lists config.json: {exc}") from exc
    return Path(root or Path(__file__).parent).expanduser().resolve()


def safe_child(root, name):
    if not isinstance(name, str) or not name or "\x00" in name or "\\" in name:
        raise ValueError("Invalid library path.")
    parts = name.split("/")
    if any(part in ("", ".", "..") or ":" in part for part in parts):
        raise ValueError("Library paths must stay inside their data folder.")
    path = root.joinpath(*parts).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Library paths must stay inside their data folder.")
    return path


def list_files():
    root = data_root() / "texts"
    if not root.is_dir():
        return []
    return sorted((p.name for p in root.iterdir()
                   if p.is_file() and p.suffix.lower() == ".txt"
                   and p.resolve().is_relative_to(root.resolve())), key=str.casefold)


def read_text(name):
    if "/" in name:
        raise ValueError("Select a .txt file directly inside texts/.")
    path = safe_child(data_root() / "texts", name)
    if path.suffix.lower() != ".txt" or not path.is_file():
        raise ValueError(f"List file {name!r} was not found in texts/.")
    if path.stat().st_size > MAX_TEXT_BYTES:
        raise ValueError("List exceeds the 2 MiB limit.")
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("Save list files as UTF-8 text.") from exc


def preview_folder_for(list_file, override=""):
    folder = override.strip() or (Path(list_file).stem if list_file else "")
    if folder:
        safe_child(data_root() / "previews", folder)
    return folder


def preview_path(folder, filename):
    directory = safe_child(data_root() / "previews", folder)
    path = safe_child(directory, filename)
    if path.suffix.lower() not in IMAGE_EXTENSIONS or not path.is_file():
        raise ValueError("Preview image was not found.")
    return path


def preview_files(folder):
    images = {}
    if folder:
        directory = safe_child(data_root() / "previews", folder)
        if directory.is_dir():
            # Build the index once rather than stat'ing every potential image.
            for p in sorted(directory.iterdir(), key=lambda p: p.name.casefold()):
                if p.suffix.lower() in IMAGE_EXTENSIONS and p.stem.isascii() and p.stem.isdecimal():
                    if p.is_file() and p.resolve().is_relative_to(directory.resolve()):
                        images.setdefault(int(p.stem), p)
    return images


def payload(text, folder=""):
    entries = parse_text(text)
    images = preview_files(folder)
    result = []
    for entry in entries:
        item = asdict(entry)
        image = images.get(entry.number)
        item["preview"] = image.name if image else None
        item["version"] = str(image.stat().st_mtime_ns) if image else ""
        result.append(item)
    return {"text": text, "entries": result, "folder": folder, "node_version": VERSION,
            "texts_directory": str(data_root() / "texts"),
            "preview_directory": str(safe_child(data_root() / "previews", folder)) if folder else "",
            "preview_folder_exists": bool(folder and (data_root() / "previews" / folder).is_dir())}


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
