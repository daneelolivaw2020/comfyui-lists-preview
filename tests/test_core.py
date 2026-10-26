import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from support import ROOT
from luis_lists_test import library
from luis_lists_test.node import ListPreview

SAMPLE = "01 Neon Rain: Blue: magenta; 50mm\n\n02 Golden Light: Warm sun\n03 Misty View: Cool clouds"


class LibraryFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {"COMFYUI_LISTS_ROOT": self.tmp.name})
        self.env.start()
        (self.root / "texts").mkdir()
        (self.root / "texts" / "illumination.txt").write_text(SAMPLE, encoding="utf-8-sig")

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()


class LibraryTests(LibraryFixture):
    def test_parse_bom_crlf_blanks_first_colon(self):
        entries = library.parse_text("\ufeff" + SAMPLE.replace("\n", "\r\n"))
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0].title, "Neon Rain")
        self.assertEqual(entries[0].description, "Blue: magenta; 50mm")
        self.assertEqual(entries[1].row, 2)

    def test_number_styles_unnumbered_and_no_title(self):
        entries = library.parse_text("01. A: One\n2) B: Two\n3 - plain\nNo title\nTitle: http://url:88\n35mm lens")
        self.assertEqual([e.number for e in entries], [1, 2, 3, 4, 5, 6])
        self.assertEqual(entries[3].description, "No title")
        self.assertEqual(entries[4].description, "http://url:88")
        self.assertEqual(entries[5].description, "35mm lens")

    def test_original_numbers_for_previews_positions_for_rows(self):
        folder = self.root / "previews" / "illumination"
        folder.mkdir(parents=True)
        (folder / "10.PNG").write_bytes(b"preview")
        result = library.payload("10 Ten: T\n20 Twenty: W", "illumination")
        self.assertEqual(result["entries"][0]["row"], 1)
        self.assertEqual(result["entries"][0]["preview"], "10.PNG")
        self.assertIsNone(result["entries"][1]["preview"])

    def test_optional_previews_and_unicode(self):
        self.assertIsNone(library.payload("Café: Luz cálida", "missing")["entries"][0]["preview"])
        self.assertEqual(library.read_text("illumination.txt"), SAMPLE)

    def test_lists_sorted_and_only_txt(self):
        (self.root / "texts" / "B.TXT").write_text("B")
        (self.root / "texts" / "a.txt").write_text("A")
        (self.root / "texts" / "other.csv").write_text("CSV")
        self.assertEqual(library.list_files(), ["a.txt", "B.TXT", "illumination.txt"])

    def test_path_traversal_rejected(self):
        for name in ["../secret.txt", "/etc/passwd", "C:/secret.txt", "..\\secret.txt", "a/../../b", "a//b", "a/./b", "\x00"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                library.safe_child(self.root, name)

    def test_invalid_encoding_and_file_errors(self):
        (self.root / "texts" / "bad.txt").write_bytes(b"\xff\xfe")
        for name in ["bad.txt", "missing.txt", "other.png", "sub/file.txt"]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                library.read_text(name)

    def test_limits(self):
        with patch.object(library, "MAX_TEXT_BYTES", 10), self.assertRaises(ValueError):
            library.parse_text("x" * 11)
        with patch.object(library, "MAX_ENTRIES", 2), self.assertRaises(ValueError):
            library.parse_text("a\nb\nc")


class NodeTests(LibraryFixture):
    def setUp(self):
        super().setUp()
        self.node = ListPreview()
        self.args = dict(source="File", list_file="illumination.txt", row=1, mode="Fixed",
                         include_title=False, preview_folder="", text="")

    def run_node(self, **changes):
        return self.node.select(**(self.args | changes))

    def test_title_toggle_and_number_stripping(self):
        self.assertEqual(self.run_node()["result"][0], "Blue: magenta; 50mm")
        self.assertEqual(self.run_node(include_title=True)["result"][0], "Neon Rain: Blue: magenta; 50mm")

    def test_connected_text_overrides_file_and_text(self):
        self.assertEqual(self.run_node(list_file="absent.txt", list_input="X: connected")["result"][0], "connected")
        self.assertEqual(self.run_node(source="Text", text="X: pasted")["result"][0], "pasted")

    def test_converted_text_input_overrides_file(self):
        result = self.run_node(text="Converted: from link", list_file="absent.txt", unique_id="1",
                               prompt={"1": {"inputs": {"text": ["2", 0]}}})
        self.assertEqual(result["result"][0], "from link")
        self.assertTrue(result["ui"]["list_preview"][0]["connected"])

    def test_editing_file_text_keeps_preview_folder(self):
        ui = self.run_node(source="Text", text="Edited: pasted")["ui"]["list_preview"][0]
        self.assertEqual(ui["folder"], "illumination")

    def test_downstream_failure_rolls_back_cursor(self):
        import sys
        import types
        current = types.SimpleNamespace(prompt_id="first")
        history = {"first": {"status": {"status_str": "error"}}}
        modules = {"comfy_execution": types.ModuleType("comfy_execution"),
                   "comfy_execution.utils": types.SimpleNamespace(get_executing_context=lambda: current),
                   "server": types.SimpleNamespace(PromptServer=types.SimpleNamespace(instance=types.SimpleNamespace(prompt_queue=types.SimpleNamespace(get_history=lambda prompt_id: {prompt_id: history[prompt_id]}))))}
        with patch.dict(sys.modules, modules):
            self.run_node(mode="Increment after render")
            current.prompt_id = "retry"
            ui = self.run_node(mode="Increment after render")["ui"]["list_preview"][0]
            self.assertEqual(ui["selected_row"], 1)

    def test_empty_connected_does_not_fall_back(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            self.run_node(list_input="")

    def test_invalid_row_and_empty_list(self):
        for row in [0, 4]:
            with self.assertRaisesRegex(ValueError, "outside"):
                self.run_node(row=row)
        with self.assertRaisesRegex(ValueError, "empty"):
            self.run_node(source="Text", text="\n\n")

    def test_fixed_does_not_advance(self):
        for _ in range(3):
            result = self.run_node(row=2)["ui"]["list_preview"][0]
            self.assertEqual((result["selected_row"], result["next_row"]), (2, 2))

    def test_increment_batch_and_wrap(self):
        rows = [self.run_node(mode="Increment after render")["ui"]["list_preview"][0]["selected_row"] for _ in range(7)]
        self.assertEqual(rows, [1, 2, 3, 1, 2, 3, 1])

    def test_increment_frontend_next_row(self):
        row = 1
        for expected in [1, 2, 3, 1]:
            ui = self.run_node(row=row, mode="Increment after render")["ui"]["list_preview"][0]
            self.assertEqual(ui["selected_row"], expected)
            row = ui["next_row"]

    def test_manual_selection_revision_resets_batch_cursor(self):
        self.run_node(mode="Increment after render")
        ui = self.run_node(mode="Increment after render", unique_id="1", extra_pnginfo={"workflow": {"nodes": [{"id": 1, "properties": {"lp_selection_revision": 2}}]}})["ui"]["list_preview"][0]
        self.assertEqual(ui["selected_row"], 1)

    def test_randomize_next_and_single_row(self):
        previous = None
        for _ in range(30):
            ui = self.run_node(mode="Randomize")["ui"]["list_preview"][0]
            self.assertNotEqual(ui["selected_row"], ui["next_row"])
            if previous:
                self.assertEqual(ui["selected_row"], previous)
            previous = ui["next_row"]
        ui = self.run_node(source="Text", text="Only: one", mode="Randomize")["ui"]["list_preview"][0]
        self.assertEqual(ui["next_row"], 1)

    def test_failure_does_not_advance(self):
        self.run_node(mode="Increment after render")
        with self.assertRaises(ValueError):
            self.run_node(mode="Increment after render", preview_folder="../bad")
        ui = self.run_node(mode="Increment after render")["ui"]["list_preview"][0]
        self.assertEqual(ui["selected_row"], 2)

    def test_file_change_invalidates_cache_and_cursor(self):
        before = ListPreview.IS_CHANGED(**self.args)
        (self.root / "texts" / "illumination.txt").write_text("New: text")
        self.assertNotEqual(before, ListPreview.IS_CHANGED(**self.args))

    def test_schema_no_extra_dependencies(self):
        schema = self.node.INPUT_TYPES()
        self.assertEqual(schema["optional"]["list_input"][0], "STRING")
        self.assertFalse(schema["required"]["text"][1]["dynamicPrompts"])
        self.assertEqual(self.node.RETURN_TYPES, ("STRING", "STRING", "INT", "STRING", "STRING", "IMAGE"))


if __name__ == "__main__":
    unittest.main()
