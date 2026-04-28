"""Efficient screenshot capture with MSS + JPEG downscaling."""
from __future__ import annotations

import io

from .config import CONFIG


def capture_screen(
    max_width: int = CONFIG.screenshot_max_width,
    quality: int = CONFIG.screenshot_jpeg_quality,
) -> tuple[bytes, tuple[int, int]]:
    """Return ``(jpeg_bytes, (width, height))`` for the primary monitor."""
    import mss  # local import: keeps test discovery fast & avoids hard dep at import time
    from PIL import Image

    with mss.mss() as sct:
        mon = sct.monitors[1]
        raw = sct.grab(mon)
        img = Image.frombytes("RGB", raw.size, raw.rgb)

    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue(), img.size
