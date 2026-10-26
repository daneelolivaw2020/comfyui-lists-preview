"""Full-resolution Comfy IMAGE decoding with a small shared CPU cache."""
from collections import OrderedDict
from hashlib import sha256
from io import BytesIO
from threading import RLock

CACHE_BYTES = 64 * 1024 * 1024
_cache = OrderedDict()
_cache_bytes = 0
_lock = RLock()


def clear_image_cache():
    global _cache_bytes
    with _lock:
        _cache.clear()
        _cache_bytes = 0


def blocked_image():
    try:
        from comfy_execution.graph_utils import ExecutionBlocker
    except ImportError:  # Older supported ComfyUI versions export it from graph.
        from comfy_execution.graph import ExecutionBlocker
    return ExecutionBlocker(None)


def load_image(path):
    """Return RGB float32 [1,H,W,3]. A clone protects cached pixels from consumers."""
    import numpy as np
    import torch
    from PIL import Image, ImageOps

    global _cache_bytes
    content = path.read_bytes()
    key = (str(path.resolve()), sha256(content).hexdigest())
    with _lock:
        image = _cache.get(key)
        if image is not None:
            _cache.move_to_end(key)
            return image.clone()
    with Image.open(BytesIO(content)) as original:
        corrected = ImageOps.exif_transpose(original)
        if corrected.mode in ("I", "I;16", "I;16L", "I;16B"):
            gray = np.clip(np.array(corrected, dtype=np.float32), 0, 65535) / 65535.0
            pixels = np.repeat(gray[..., None], 3, axis=-1)
        else:
            image = corrected.convert("RGB")
            pixels = np.array(image, dtype=np.float32) / 255.0
    tensor = torch.from_numpy(pixels).unsqueeze(0)
    size = tensor.nelement() * tensor.element_size()
    if size <= CACHE_BYTES:
        with _lock:
            # Keep only the latest decoded contents of a particular file.
            for old in [k for k in _cache if k[0] == key[0]]:
                previous = _cache.pop(old)
                _cache_bytes -= previous.nelement() * previous.element_size()
            while _cache and _cache_bytes + size > CACHE_BYTES:
                _, previous = _cache.popitem(last=False)
                _cache_bytes -= previous.nelement() * previous.element_size()
            _cache[key] = tensor
            _cache_bytes += size
    return tensor.clone()
