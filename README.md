# List Preview • Luis

A personal ComfyUI node that selects a prompt and its matching preview image from a `.txt` list using a clickable thumbnail gallery. The node uses ComfyUI's existing PyTorch, NumPy, Pillow, and aiohttp dependencies. It requires no GPU or model downloads and is intended for your own installation.

## Version 0.2

The outputs, in order, are:

| Output | Type | Value |
| --- | --- | --- |
| text | STRING | Prefix + selected content (with optional title) + suffix |
| list_file | STRING | Full resolved file path, or `file: none` for pasted/connected text |
| row | INT | Entry position used for this execution |
| title | STRING | Title only, or `no title` |
| description | STRING | Plain description, independent of title toggle and affixes |
| image | IMAGE | Full-resolution preview belonging to the same selected entry |

All outputs correspond to the executed row; increment/randomization may display a different next row after rendering. The first text socket stays at index 0. Existing saved workflows gain the new sockets without losing their text connection; prefix/suffix default to empty for old workflows and API requests.

**prefix** and **suffix** affect only **text**. Add your own spaces/punctuation; no separators are inserted. For example, `photo, ` + `Warm sunlight` + `, soft grain` outputs `photo, Warm sunlight, soft grain`. Their STRING fields can be converted to inputs for multiline values; spaces and newlines are preserved. Separate title/description/file outputs and the source file are unaffected. `no title` is only a metadata fallback and is not inserted into the prompt.

Connect **image** directly to an IMAGE input. The node loads from your configured `previews/` folder, at the source image's full resolution, with EXIF orientation applied. It outputs normalized RGB pixels, including conversion of grayscale, RGBA, and 16-bit PNG images. The gallery's display size does not resize the IMAGE output. No separate image loader or copy to `input/` is required.

When the selected preview is missing or unreadable, the image output returns ComfyUI's silent execution blocker. Consumers of that IMAGE branch are skipped; the text, path, row, title, and description outputs still work. The browser status explains missing/unreadable previews. It never substitutes another entry's image or a blank placeholder.

Decoded images use a shared CPU cache limited to 64 MiB; larger images are decoded without retaining a cache copy. File-content hashes detect replacements even when timestamps are preserved. Reload files clears the decoded cache as well as refreshing the gallery. Returned tensors are copied so a downstream node cannot mutate the cached source.

## Update 1.0.1

Fixes increment/random row advancement when workflow metadata is missing and supports completion via `executing(null)` on older ComfyUI versions. Completion events are matched locally, so workflow metadata is not required to update the row; failed/interrupted renders still preserve it.

**Reload files** replaces the Refresh label. It rereads the file list and selected text, rescans previews, and forces fresh image requests even when a replacement image retains its timestamp. **Library folders** shows the actual text/preview paths and installed build.

To update an existing Colab install, stop ComfyUI and paste `examples/colab_update_cell.py` into one cell. It prompts for the new ZIP, installs the code, and replaces the cached ZIP used by the original install cell. Your existing library/configuration is retained. Restart ComfyUI and hard-refresh its browser tab (Ctrl+Shift+R). Confirm version **0.2.0** in Library folders. Running the original cached install cell alone can reinstall the old ZIP until that cache is replaced.

## Install in Colab

### From the private GitHub repository

The repository is `daneelolivaw2020/comfyui-lists-preview`. Paste `examples/colab_install_github.py` into a code cell after installing ComfyUI and before starting its server, or use `Install_from_GitHub.ipynb`.

In GitHub, create a fine-grained personal access token limited to this repository with **Contents: Read-only**. In Colab's **Secrets** panel (key icon), add it as **GITHUB_TOKEN** and enable **Notebook access** for your notebook. The cell reads it with `google.colab.userdata.get`, sends it only as an authorization header, and downloads the selected branch. Do not paste the token into notebook source or a Git remote URL. No ZIP upload or public repository is required.

The cell defaults to `main` and the same ComfyUI/Drive paths as the ZIP installer. Each run installs current node code. Bundled texts, previews, and workflows are copied into the Drive library only when the destination file does not exist; your edited library files are preserved. To take a newer bundled data file after editing your Drive copy, compare and replace it yourself.

References: [Colab Secrets API](https://github.com/googlecolab/colabtools/blob/main/google/colab/userdata.py), [GitHub repository archives](https://docs.github.com/en/rest/repos/contents#download-a-repository-archive-zip).

### From a ZIP

Download `comfyui-lists-preview.zip` and `Install_in_Colab.ipynb` from the delivered files. Open the notebook in Colab and run its cells **after installing ComfyUI and before launching the ComfyUI server**. It asks you to upload the ZIP, mounts Google Drive, and installs the node. Adjust `COMFYUI_DIR` if your notebook uses a different ComfyUI location.

The installer keeps your library in:

```text
/content/drive/MyDrive/ComfyUI/luis-lists/
  texts/
    illumination.txt
  previews/
    illumination/
      01.png
      02.png
      ...
```

On a new free-tier session, rerun the install cell before starting ComfyUI. Your Drive library persists. Updating the node seeds missing bundled texts, previews, and workflows while retaining existing library files. You can also paste the notebook's install cell into your usual Colab notebook.

## Manual installation

Extract this folder into `ComfyUI/custom_nodes/comfyui-lists-preview/`, restart ComfyUI, and reload its browser tab. Find **Luis/Text → List Preview • Luis**.

For a separate persistent library, put this `config.json` beside `node.py` (the Colab installer does this for you):

```json
{"data_root": "/content/drive/MyDrive/ComfyUI/luis-lists"}
```

Alternatively set `COMFYUI_LISTS_ROOT` before starting ComfyUI. The environment variable takes precedence over `config.json`. Without either setting, `texts/` and `previews/` beside `node.py` are used. Python 3.10+ is required.

## Use

1. Set **source = File** and select a `.txt` in **list_file**. Its full contents appear in the textarea. **Reload files** discovers new files and reloads text and thumbnails without restarting. Open **Library folders** to see exactly where the node reads previews; for the default Colab installer this is Google Drive, not the copy under `custom_nodes/`.
2. Click a thumbnail to select a row. The row number, entry dropdown, and highlighted card stay synchronized. Search filters cards by title or description. Missing images show a selectable **No preview** card.
3. **include_title = false** outputs only the description. Set it to **true** for `Title: description`. Leading entry numbers are always removed.
4. Connect the **text** STRING output to a prompt input, such as CLIP Text Encode's text input.
5. Choose a **mode**:
   - **Fixed** keeps the selected row.
   - **Randomize** uses the selected row first, then picks a different row for the next successful render (unless there is only one row).
   - **Increment after render** uses the selected row, then advances by one after the workflow succeeds, wrapping from the last row to the first.

The gallery displays the row being used while rendering, and the next row after successful completion. The output area shows the last output after a run. Failed or interrupted renders preserve the row. Queued workflows progress independently on the backend; manually clicking a row resets the sequence for subsequently queued work. Already queued workflows retain their own settings. Progression state is session-local; a saved workflow retains the currently displayed row.

### Pasted and connected text

Set **source = Text** to paste a list into the textarea. Editing loaded file text automatically switches to Text mode; it does not modify the file on disk. Set source back to File to reload the original.

Connect a STRING containing a list to **list_input** to override File/Text. You can also convert the **text** textarea to an input and connect it. `list_input` takes priority if both are connected. Generated upstream text is only available after execution: run once to load the gallery, choose visually, then run again. The first run outputs the row currently selected. An empty connected list reports an error instead of silently using a file. One STRING should contain all lines; a ComfyUI batch/list of STRING objects is processed as separate executions.

Use **preview_folder** to choose a folder under `previews/` (for example `illumination`). A blank preview folder uses the selected file's stem in both File and Text mode, preserving previews when editing a loaded file. With no selected file, set preview_folder explicitly for pasted/connected lists. A preview folder and all its images are optional.

### Text and image formats

Save `.txt` files as UTF-8, with one entry per nonblank line:

```text
01 Neon Rain Streets: Blue and magenta neon reflecting on wet pavement
02 Golden Window Light: Warm sunlight through interior shadows
03 Misty Mountain View: Diffused morning light, low clouds, cool tones
```

Numbers are optional; `1. Title: description` and `1) Title: description` are accepted too. Blank lines are ignored. Lines without a colon output their whole content in either title mode. Only the first colon separates the title, so later colons, URLs, semicolons, camera settings, and Unicode text are retained. The maximum is 2 MiB and 10,000 entries per list.

**row is a 1-based entry position**, ignoring blank lines. The gallery labels use these row positions. Images match the leading number written in the file; if no number is present, the row position is used. Thus `10 Example: ...` in the first row uses `10.png`, and clicking its card selects row 1. Use sequential numbering as in the sample for the clearest experience.

Preview filenames may be zero-padded or unpadded (`01.png`, `1.png`, `001.png`), with PNG/JPEG/WebP extensions. Use only one image per number. Preview images are displayed as supplied; the node does not generate pictures or thumbnails. Smaller preview images (roughly 320–640 pixels wide) load faster over Colab tunnels. Nested preview folders are supported; text files belong directly inside `texts/`.

## Development and verification

Prepare the pinned official ComfyUI execution helpers once for standalone tests. Backend tests use real CPU PyTorch image tensors and the official result-merging/blocker-propagation functions:

```bash
pip install --target .test-deps aiohttp comfyui-frontend-package==1.57.3 Pillow numpy
pip install --target .test-torch --index-url https://download.pytorch.org/whl/cpu torch==2.5.1
python tools/prepare_test_runtime.py
python -m unittest discover -s tests -v
```

The browser suite uses the actual ComfyUI production frontend package and a lightweight test queue host, executing the real node and real HTTP routes without loading image models:

```bash
npm install
python tests/serve_frontend.py
# In another terminal (Edge installed):
npm run test:browser
```

Use `BROWSER_CHANNEL=chrome` for Chrome or adjust the Playwright launch configuration. Screenshots and browser results are written to `test-results/`; synthetic QA thumbnails stay under `.test-runtime/` and are not included in the installable ZIP. `TESTING.md` records the tested scope and remaining environment-specific checks.

Implementation references: [ComfyUI node schema](https://docs.comfy.org/custom-nodes/backend/server_overview), [IMAGE format](https://docs.comfy.org/custom-nodes/backend/images_and_masks), [execution blockers](https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_execution/graph_utils.py), [frontend extension lifecycle](https://github.com/Comfy-Org/ComfyUI_frontend/blob/main/docs/extensions/core.md), [DOM widget API](https://github.com/Comfy-Org/ComfyUI_frontend/blob/main/src/types/domWidget.ts).
