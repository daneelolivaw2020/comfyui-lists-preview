"""ComfyUI V1 list selector with structured outputs and a matching IMAGE."""
import secrets

from .library import (data_root, file_hash, list_files, payload, parse_text,
                      preview_files, preview_folder_for, read_text, safe_child, text_hash)
from .image_output import blocked_image, load_image


class ListPreview:
    CATEGORY = "Luis/Text"
    FUNCTION = "select"
    RETURN_TYPES = ("STRING", "STRING", "INT", "STRING", "STRING", "IMAGE")
    RETURN_NAMES = ("text", "list_file", "row", "title", "description", "image")
    OUTPUT_NODE = True  # Also allows running this node alone to inspect a connected list.
    DESCRIPTION = "Choose a prompt visually from a text list and optional numbered thumbnails."

    def __init__(self):
        self._context = None
        self._last_requested = None
        self._next_row = None
        self._pending = None

    def _execution(self):
        """Recover the cursor if downstream rendering failed after this node ran."""
        try:
            from comfy_execution.utils import get_executing_context
            from server import PromptServer
        except ImportError:
            return None
        context = get_executing_context()
        prompt_id = context.prompt_id if context else None
        if self._pending and self._pending[0] != prompt_id:
            previous_id, previous_state = self._pending
            history = PromptServer.instance.prompt_queue.get_history(prompt_id=previous_id)
            previous = history.get(previous_id, {}).get("status", {})
            if previous.get("status_str") == "error":
                self._context, self._last_requested, self._next_row = previous_state
            self._pending = None
        return prompt_id

    @classmethod
    def INPUT_TYPES(cls):
        files = list_files() or ["(no files)"]
        return {"required": {
            "source": (["File", "Text"],),
            "list_file": (files,),
            "row": ("INT", {"default": 1, "min": 1, "max": 10000,
                            "tooltip": "1-based entry position (blank lines are ignored)."}),
            "mode": (["Fixed", "Randomize", "Increment after render"],),
            "include_title": ("BOOLEAN", {"default": False}),
            "preview_folder": ("STRING", {"default": "", "tooltip": "Optional folder inside previews/. Blank uses the file name."}),
            "text": ("STRING", {"multiline": True, "default": "", "dynamicPrompts": False,
                                "tooltip": "Loaded file contents, or an editable list in Text mode. Can also be converted to an input."}),
        }, "optional": {
            "list_input": ("STRING", {"forceInput": True, "tooltip": "Connected list overrides File/Text. Run once to load generated lists."}),
            "prefix": ("STRING", {"default": "", "dynamicPrompts": False,
                                  "tooltip": "Added before main text exactly as entered. Add your own spacing."}),
            "suffix": ("STRING", {"default": "", "dynamicPrompts": False,
                                  "tooltip": "Added after main text exactly as entered. Add your own spacing."}),
        }, "hidden": {"unique_id": "UNIQUE_ID", "extra_pnginfo": "EXTRA_PNGINFO", "prompt": "PROMPT"}}

    @classmethod
    def VALIDATE_INPUTS(cls, list_file):
        # Refresh can discover files absent from the original /object_info combo.
        # The filesystem is validated when the file is actually used.
        return True

    @classmethod
    def IS_CHANGED(cls, source="File", list_file="", mode="Fixed", row=1,
                   preview_folder="", text="", list_input=None, prompt=None, unique_id=None, **kwargs):
        if mode != "Fixed":
            return float("nan")
        inputs = (prompt or {}).get(str(unique_id), {}).get("inputs", {})
        if any(isinstance(inputs.get(name), list) for name in ("list_input", "text")):
            # Upstream values are unresolved during cache checks. Recheck the image on execution.
            return float("nan")
        try:
            raw = list_input if list_input is not None else (read_text(list_file) if source == "File" else text)
            entries = parse_text(raw)
            folder = preview_folder_for(list_file if list_file != "(no files)" else "", preview_folder)
            image = preview_files(folder).get(entries[row - 1].number) if 1 <= row <= len(entries) else None
            return (text_hash(raw), str(image) if image else "", file_hash(image) if image else "missing")
        except (ValueError, OSError):
            return float("nan")

    def select(self, source, list_file, row, mode, include_title, preview_folder,
               text, list_input=None, unique_id=None, extra_pnginfo=None, prompt=None,
               prefix="", suffix=""):
        prompt_id = self._execution()
        text_linked = isinstance((prompt or {}).get(str(unique_id), {}).get("inputs", {}).get("text"), list)
        is_connected = list_input is not None or text_linked
        raw = list_input if list_input is not None else (text if text_linked or source == "Text" else read_text(list_file))
        entries = parse_text(raw)
        if not entries:
            raise ValueError("The list is empty. Add one entry per nonblank line.")
        if not isinstance(row, int) or not 1 <= row <= len(entries):
            raise ValueError(f"Row {row} is outside this list (1–{len(entries)}). Select an available row.")
        if mode not in ("Fixed", "Randomize", "Increment after render"):
            raise ValueError(f"Unknown selection mode: {mode}")
        revision = 0
        if isinstance(extra_pnginfo, dict):
            workflow = extra_pnginfo.get("workflow", {})
            for node in workflow.get("nodes", []) if isinstance(workflow, dict) else []:
                if str(node.get("id")) == str(unique_id):
                    revision = node.get("properties", {}).get("lp_selection_revision", 0)
                    break
        context = (text_hash(raw), mode, revision)
        selected = row
        if mode != "Fixed" and context == self._context and row in (self._last_requested, self._next_row):
            selected = self._next_row
        entry = entries[selected - 1]
        if mode == "Increment after render":
            next_row = selected % len(entries) + 1
        elif mode == "Randomize" and len(entries) > 1:
            # Sample every other row uniformly; never get stuck on the same thumbnail.
            next_row = secrets.randbelow(len(entries) - 1) + 1
            if next_row >= selected:
                next_row += 1
        else:
            next_row = selected
        folder = preview_folder_for(list_file if list_file != "(no files)" else "", preview_folder)
        result = payload(raw, folder)
        output = prefix + (entry.text if include_title else entry.description) + suffix
        file_output = str(safe_child(data_root() / "texts", list_file)) if source == "File" and not is_connected else "file: none"
        selected_entry = result["entries"][selected - 1]
        image_status = "No preview for this row; image branch skipped."
        image = blocked_image()
        if selected_entry["preview"]:
            try:
                image = load_image(safe_child(data_root() / "previews", folder + "/" + selected_entry["preview"]))
                image_status = ""
            except (OSError, ValueError) as exc:
                image_status = f"Preview could not be loaded; image branch skipped: {exc}"
        result.update(selected_row=selected, next_row=next_row, output=output,
                      connected=is_connected, mode=mode, prompt_id=prompt_id,
                      selection_revision=revision, image_status=image_status,
                      selected_outputs={"text": output, "list_file": file_output, "row": selected,
                                        "title": entry.title or "no title", "description": entry.description})
        # Commit progression only after successful parsing, preview discovery and output.
        # All mapped list items belong to one prompt. Keep its initial snapshot
        # so a downstream failure rolls back the entire batch, not just its tail.
        if prompt_id and (not self._pending or self._pending[0] != prompt_id):
            self._pending = (prompt_id, (self._context, self._last_requested, self._next_row))
        self._context, self._last_requested, self._next_row = context, row, next_row
        return {"ui": {"list_preview": [result]},
                "result": (output, file_output, selected, entry.title or "no title", entry.description, image)}
