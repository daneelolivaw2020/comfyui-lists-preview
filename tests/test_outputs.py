import ast
import asyncio
from contextlib import nullcontext
import inspect
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from support import ROOT, ExecutionBlocker
import torch
from PIL import Image
from test_core import LibraryFixture
from luis_lists_test import image_output
from luis_lists_test.library import file_hash
from luis_lists_test.node import ListPreview


class OutputTests(LibraryFixture):
    def setUp(self):
        super().setUp()
        image_output.clear_image_cache()
        self.node = ListPreview()
        self.args = dict(source="File", list_file="illumination.txt", row=1, mode="Fixed",
                         include_title=False, preview_folder="", text="")
        self.folder = self.root / "previews" / "illumination"
        self.folder.mkdir(parents=True)

    def select(self, **changes):
        return self.node.select(**(self.args | changes))

    def image(self, number=1, color=(255,0,0), size=(31,19), mode="RGB"):
        path = self.folder / f"{number:02}.png"
        Image.new(mode, size, color).save(path)
        return path

    def test_exact_approved_sockets_and_types(self):
        self.assertEqual(self.node.RETURN_NAMES, ("text","list_file","row","title","description","image"))
        outputs = self.select()["result"]
        self.assertEqual(outputs[:5], ("Blue: magenta; 50mm", str((self.root / "texts/illumination.txt").resolve()), 1, "Neon Rain", "Blue: magenta; 50mm"))
        self.assertIs(type(outputs[2]), int)
        self.assertIsInstance(outputs[5], ExecutionBlocker)

    def test_affixes_only_change_main_text_and_keep_whitespace(self):
        outputs = self.select(include_title=True, prefix="  photo,\n", suffix="\n-- end  ")["result"]
        self.assertEqual(outputs[0], "  photo,\nNeon Rain: Blue: magenta; 50mm\n-- end  ")
        self.assertEqual(outputs[3:5], ("Neon Rain", "Blue: magenta; 50mm"))

    def test_pasted_connected_and_titleless_metadata(self):
        for change in [dict(source="Text",text="plain sentence"), dict(list_input="plain sentence"),
                       dict(text="plain sentence",unique_id="1",prompt={"1":{"inputs":{"text":["2",0]}}})]:
            outputs = self.select(include_title=True, prefix="[", suffix="]", **change)["result"]
            self.assertEqual(outputs[:5], ("[plain sentence]", "file: none",1,"no title","plain sentence"))

    def test_full_resolution_rgb_normalized_cpu_tensor(self):
        self.image(color=(255,128,0))
        image = self.select()["result"][5]
        self.assertEqual(tuple(image.shape), (1,19,31,3))
        self.assertEqual(image.dtype, torch.float32)
        self.assertEqual(image.device.type,"cpu")
        torch.testing.assert_close(image[0,0,0], torch.tensor([1,128/255,0]))

    def test_rgba_and_grayscale_convert_to_rgb(self):
        self.image(color=(40,80,120,100), mode="RGBA")
        torch.testing.assert_close(self.select()["result"][5][0,0,0], torch.tensor([40,80,120])/255)
        self.image(color=127, mode="L")
        torch.testing.assert_close(self.select()["result"][5][0,0,0], torch.tensor([127,127,127])/255)

    def test_exif_orientation_is_applied_at_full_resolution(self):
        original = Image.new("RGB",(7,11),(255,0,0))
        exif = original.getexif()
        exif[274] = 6
        original.save(self.folder/"01.jpg",exif=exif)
        self.assertEqual(tuple(self.select()["result"][5].shape),(1,7,11,3))

    def test_16_bit_png_is_normalized_without_clipping_to_white(self):
        import numpy as np
        Image.fromarray(np.array([[0,32768,65535]],dtype=np.uint16)).save(self.folder/"01.png")
        image = self.select()["result"][5]
        torch.testing.assert_close(image[0,0,:,0],torch.tensor([0.,32768/65535,1.]))

    def test_original_numbers_choose_preview_not_row_position(self):
        self.image(number=10, color=(0,255,0))
        outputs = self.select(source="Text",text="10 Special: chosen",row=1)["result"]
        self.assertEqual(outputs[2:5], (1,"Special","chosen"))
        torch.testing.assert_close(outputs[5][0,0,0], torch.tensor([0.,1.,0.]))

    def test_increment_all_outputs_match_used_row(self):
        self.image(1,color=(255,0,0)); self.image(2,color=(0,255,0)); self.image(3,color=(0,0,255))
        for index in range(6):
            outputs = self.select(mode="Increment after render")["result"]
            row = index % 3 + 1
            self.assertEqual(outputs[2],row)
            torch.testing.assert_close(outputs[5][0,0,0], torch.eye(3)[row-1])
            self.assertEqual(outputs[3], ["Neon Rain","Golden Light","Misty View"][row-1])

    def test_random_all_outputs_match_used_row(self):
        for n,color in enumerate([(255,0,0),(0,255,0),(0,0,255)],1): self.image(n,color)
        for _ in range(15):
            outputs = self.select(mode="Randomize")["result"]
            torch.testing.assert_close(outputs[5][0,0,0], torch.eye(3)[outputs[2]-1])

    def test_cache_reuses_decoding_and_resists_mutating_consumers(self):
        path = self.image()
        from PIL import Image as PILImage
        with patch.object(PILImage,"open",wraps=PILImage.open) as opened:
            first = image_output.load_image(path)
            first.zero_()
            second = image_output.load_image(path)
            self.assertEqual(opened.call_count,1)
            self.assertEqual(second[0,0,0,0],1)

    def test_image_replace_same_timestamp_invalidates_node_and_decode_cache(self):
        path = self.image()
        original_stat = path.stat()
        first_fingerprint = self.node.IS_CHANGED(**self.args)
        self.select()
        self.image(color=(0,0,255))
        os.utime(path, ns=(original_stat.st_atime_ns,original_stat.st_mtime_ns))
        self.assertNotEqual(first_fingerprint,self.node.IS_CHANGED(**self.args))
        torch.testing.assert_close(self.select()["result"][5][0,0,0],torch.tensor([0.,0.,1.]))
        path.unlink()
        self.assertIsInstance(self.select()["result"][5],ExecutionBlocker)

    def test_corrupt_image_skips_only_image_output(self):
        (self.folder/"01.png").write_bytes(b"not an image")
        result = self.select()
        self.assertEqual(result["result"][0],"Blue: magenta; 50mm")
        self.assertIsInstance(result["result"][5],ExecutionBlocker)
        self.assertIn("could not be loaded",result["ui"]["list_preview"][0]["image_status"])

    def test_cache_is_bounded_and_clearable(self):
        with patch.object(image_output,"CACHE_BYTES",8000):
            for n in range(1,5): image_output.load_image(self.image(n))
            self.assertLessEqual(image_output._cache_bytes,8000)
            self.assertEqual(len(image_output._cache),1)
        image_output.clear_image_cache()
        self.assertEqual(image_output._cache_bytes,0)

    def test_missing_image_blocks_image_branch_using_official_executor_functions(self):
        # Execute the upstream result-merging and blocker propagation code unchanged.
        tree = ast.parse((ROOT/".test-runtime/comfy-source/execution.py").read_text(encoding="utf-8"))
        selected = [n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))
                    and n.name in ("merge_result_data","_async_map_node_over_list")]
        self.assertEqual(len(selected),2)
        namespace = {"ExecutionBlocker":ExecutionBlocker,"inspect":inspect,"asyncio":asyncio,
                     "_ComfyNodeInternal":type("UnusedV3",(),{}),"is_class":inspect.isclass,
                     "CurrentNodeContext":lambda *args:nullcontext()}
        exec(compile(ast.Module(body=selected,type_ignores=[]),"official-execution-functions","exec"),namespace)
        merged = namespace["merge_result_data"]([self.select()["result"]],self.node)
        class ImageSink:
            def consume(self,image): raise AssertionError("Missing image must skip the image consumer")
        class TextSink:
            def consume(self,text): return (text,)
        map_node = namespace["_async_map_node_over_list"]
        image = asyncio.run(map_node("prompt","sink",ImageSink(),{"image":merged[5]},"consume"))
        text = asyncio.run(map_node("prompt","sink",TextSink(),{"text":merged[0]},"consume"))
        self.assertIsInstance(image[0],ExecutionBlocker)
        self.assertIsNone(image[0].message)
        self.assertEqual(text,[("Blue: magenta; 50mm",)])
