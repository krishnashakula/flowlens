"""
FlowLens — Screen Frame Utilities
Processes raw screen captures into compact JPEG bytes suitable for Gemini Vision.

Optimisation targets:
  Input:  raw PNG/BMP from getDisplayMedia → 1-4 MB
  Output: JPEG 60% quality, max 1280×720 → ~50–120 KB
  Effect: 20-40x token reduction → ~300ms faster frame analysis
"""

import io
import logging
from typing import Optional

import structlog
from PIL import Image, ImageOps

log = structlog.get_logger(__name__)

# ---- Compression parameters ------------------------------------------------
MAX_WIDTH = 1280
MAX_HEIGHT = 720
JPEG_QUALITY = 60          # 60% — good enough for scene understanding
MAX_OUTPUT_BYTES = 200_000  # Hard cap; fall back to lower quality if exceeded
# ---------------------------------------------------------------------------


def compress_frame(raw_bytes: bytes) -> bytes:
    """
    Compress a raw image (PNG, JPEG, BMP, WebP) to a small JPEG.

    Args:
        raw_bytes: Raw image bytes from client (any Pillow-supported format).

    Returns:
        JPEG bytes at JPEG_QUALITY, max 1280×720.

    Raises:
        ValueError: If raw_bytes cannot be decoded as an image.
    """
    try:
        image = Image.open(io.BytesIO(raw_bytes))
    except Exception as exc:
        raise ValueError(f"Cannot decode screen frame: {exc}") from exc

    # Convert to RGB (drops alpha channel, required for JPEG)
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    # Resize if larger than target, preserving aspect ratio
    image = _resize_if_needed(image, MAX_WIDTH, MAX_HEIGHT)

    return _encode_jpeg(image, JPEG_QUALITY)


def _resize_if_needed(image: Image.Image, max_w: int, max_h: int) -> Image.Image:
    w, h = image.size
    if w <= max_w and h <= max_h:
        return image

    ratio = min(max_w / w, max_h / h)
    new_w = int(w * ratio)
    new_h = int(h * ratio)
    resized = image.resize((new_w, new_h), Image.LANCZOS)
    log.debug("frame_resized", orig=(w, h), new=(new_w, new_h))
    return resized


def _encode_jpeg(image: Image.Image, quality: int) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality, optimize=True)
    result = buf.getvalue()

    if len(result) > MAX_OUTPUT_BYTES and quality > 30:
        log.warning(
            "frame_too_large", bytes=len(result), retrying_at_quality=quality - 20
        )
        return _encode_jpeg(image, quality - 20)

    log.debug("frame_compressed", bytes=len(result), quality=quality)
    return result


def frame_to_base64(jpeg_bytes: bytes) -> str:
    """Convenience: convert JPEG bytes to base64 string for JSON transport."""
    import base64
    return base64.b64encode(jpeg_bytes).decode("utf-8")


def validate_frame(raw_bytes: bytes) -> bool:
    """Quick validation — returns False if bytes don't look like a valid image."""
    try:
        with Image.open(io.BytesIO(raw_bytes)) as img:
            img.verify()
        return True
    except Exception:
        return False
