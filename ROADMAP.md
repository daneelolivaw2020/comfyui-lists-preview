# Version 0.2 notes

The approved image output, structured text outputs, and prefix/suffix fields are implemented in version 0.2.0. Reload improvements from bug-fix build 1.0.1 are retained.

## Reload files

- Delivered in 1.0.1: label the action **Reload files**, reread lists/text/images, bypass stale browser/proxy image caches, and display actual library paths.
- Delivered in 0.2.0: Reload files also clears the decoded-image cache.

## Selected preview as an IMAGE output

- Add a direct **IMAGE** output alongside the existing selected-text **STRING** output.
- Load the matching preview from the configured `previews/<list>/` directory, including a custom Google Drive data root. No copy into ComfyUI's `input/` directory or separate Load Image node should be needed.
- Output the image corresponding to the text selected for the current execution. Randomize/increment modes must not accidentally output the next row's image.
- Decode at the source image's full resolution, independently of the gallery's display size.
- Reuse a decoded image while its path and file contents are unchanged, with bounded memory use suitable for Colab free tier.
- Missing or unreadable previews emit a silent ComfyUI execution blocker only on the IMAGE socket; text and metadata outputs remain usable.

Reference: [ComfyUI IMAGE output format](https://docs.comfy.org/custom-nodes/backend/images_and_masks).

## More text outputs and prefix/suffix fields

User-requested outputs:

- **list_file** (STRING): the full resolved path and filename of the file actually supplying the list. Return the literal `file: none` for pasted or connected text, even if a file remains selected in the interface.
- **row** (INT): the entry position used for the current execution, for example `3`. This must match the emitted text/image, rather than the next row displayed after increment/randomization.
- **title** (STRING): the selected title, or the literal `no title` when absent.
- **description** (STRING): the plain selected description, independent of Include title. The user accepted this separation from the composed main text output.
- Preserve the existing main **text** output.

User-requested fields:

- **prefix** and **suffix**: optional text to prepend/append to the main output string; empty defaults preserve existing workflows.

Accepted design:

- Keep **description** as the plain description in all modes. Apply Include title and prefix/suffix only to the main **text** output, providing predictable reusable component outputs.
- Compose main text as `prefix + selected content + suffix`. Preserve spaces/newlines exactly as entered; do not insert automatic separators.
- Apply prefix/suffix only to main text. Do not modify the separate title/description/path outputs or the source file.
- A `no title` fallback is output metadata; do not insert that placeholder into the composed prompt when the entry has no title.

The user accepted this output layout and prefix/suffix behavior; it is implemented in 0.2.0. Scope remains limited to the approved features.
