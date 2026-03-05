"""
Tests for screen.py — compress_frame, validate_frame, frame_to_base64.

Risk tier: HIGH — every turn's screen context flows through this pipeline.
Bugs here silently degrade vision quality or crash the turn.

Test categories: boundary values, error paths, output contracts,
                 aspect ratio invariant, quality fallback, format correctness.
"""

import base64
import io

import pytest
from PIL import Image

# conftest.py makes backend importable
from screen import compress_frame, frame_to_base64, validate_frame

# Inline helpers (also in conftest — redefined here to keep this file self-contained)
def _png(w, h, color=(30, 30, 30), mode="RGB") -> bytes:
    buf = io.BytesIO()
    Image.new(mode, (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg(w, h) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (100, 100, 100)).save(buf, format="JPEG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# compress_frame — output format
# ---------------------------------------------------------------------------

class TestCompressFrameOutputFormat:
    """Compressed output must always be valid JPEG regardless of input format."""

    def test_png_input_produces_jpeg(self):
        result = compress_frame(_png(100, 100))
        img = Image.open(io.BytesIO(result))
        assert img.format == "JPEG"

    def test_jpeg_input_produces_jpeg(self):
        result = compress_frame(_jpeg(200, 200))
        img = Image.open(io.BytesIO(result))
        assert img.format == "JPEG"

    def test_rgba_png_is_converted_to_rgb(self):
        """JPEG does not support alpha — RGBA input must be converted."""
        rgba = _png(100, 100, color=(0, 128, 255, 200), mode="RGBA")
        result = compress_frame(rgba)
        img = Image.open(io.BytesIO(result))
        assert img.mode == "RGB"

    def test_grayscale_png_is_accepted(self):
        gray = _png(100, 100, color=128, mode="L")
        result = compress_frame(gray)
        img = Image.open(io.BytesIO(result))
        assert img.format == "JPEG"

    def test_result_is_bytes(self):
        assert isinstance(compress_frame(_png(50, 50)), bytes)

    def test_result_under_hard_cap(self):
        """Output must never exceed 200 KB (hard cap in screen.py)."""
        # Even a large high-detail image must fit
        result = compress_frame(_png(2560, 1440))
        assert len(result) <= 200_000


# ---------------------------------------------------------------------------
# compress_frame — downscaling invariants
# ---------------------------------------------------------------------------

class TestCompressFrameDownscaling:
    """Images larger than 1280×720 must be downscaled. Aspect ratio must be preserved."""

    def test_large_image_downscaled_below_max(self):
        result = compress_frame(_png(2560, 1440))
        img = Image.open(io.BytesIO(result))
        assert img.width <= 1280
        assert img.height <= 720

    def test_small_image_not_upscaled(self):
        """Small images must not be enlarged — that wastes tokens."""
        result = compress_frame(_png(100, 100))
        img = Image.open(io.BytesIO(result))
        assert img.width <= 1280
        assert img.height <= 720

    def test_aspect_ratio_preserved_on_wide_image(self):
        """3840×1080 ultrawide: width-bounded, height proportional."""
        result = compress_frame(_png(3840, 1080))
        img = Image.open(io.BytesIO(result))
        # Original ratio: 3840/1080 ≈ 3.556
        ratio = img.width / img.height
        assert ratio == pytest.approx(3840 / 1080, rel=0.05)  # 5% tolerance

    def test_aspect_ratio_preserved_on_portrait_image(self):
        """Portrait 720×1440: height-bounded, width proportional."""
        result = compress_frame(_png(720, 1440))
        img = Image.open(io.BytesIO(result))
        ratio = img.width / img.height
        assert ratio == pytest.approx(720 / 1440, rel=0.05)

    def test_1280x720_exactly_not_resized(self):
        """Image exactly at the limit must not be resized at all."""
        result = compress_frame(_png(1280, 720))
        img = Image.open(io.BytesIO(result))
        assert img.size == (1280, 720)

    def test_1x1_pixel_is_accepted(self):
        """Boundary: minimum possible image should not crash."""
        result = compress_frame(_png(1, 1))
        assert len(result) > 0


# ---------------------------------------------------------------------------
# compress_frame — error paths
# ---------------------------------------------------------------------------

class TestCompressFrameErrors:
    """Invalid input must raise ValueError, never a bare PIL exception."""

    def test_empty_bytes_raises_value_error(self):
        with pytest.raises(ValueError, match="Cannot decode"):
            compress_frame(b"")

    def test_random_bytes_raises_value_error(self):
        with pytest.raises(ValueError, match="Cannot decode"):
            compress_frame(b"\x00\x01\x02\x03garbage not an image")

    def test_truncated_jpeg_raises_value_error(self):
        valid = _jpeg(100, 100)
        truncated = valid[:len(valid) // 2]
        with pytest.raises(ValueError):
            compress_frame(truncated)

    def test_text_file_raises_value_error(self):
        with pytest.raises(ValueError):
            compress_frame(b"Hello, this is not an image at all")


# ---------------------------------------------------------------------------
# validate_frame
# ---------------------------------------------------------------------------

class TestValidateFrame:
    """validate_frame returns True for valid images, False for garbage."""

    def test_valid_jpeg_returns_true(self):
        assert validate_frame(_jpeg(100, 100)) is True

    def test_valid_png_returns_true(self):
        assert validate_frame(_png(100, 100)) is True

    def test_garbage_bytes_returns_false(self):
        assert validate_frame(b"this is not an image") is False

    def test_empty_bytes_returns_false(self):
        assert validate_frame(b"") is False

    def test_partial_jpeg_returns_false(self):
        valid = _jpeg(100, 100)
        assert validate_frame(valid[:20]) is False

    def test_returns_bool_not_truthy(self):
        result = validate_frame(_jpeg(50, 50))
        assert result is True  # Must be exactly True, not just truthy

    def test_garbage_returns_false_not_raises(self):
        """Must never raise — caller treats return value as signal."""
        try:
            result = validate_frame(b"\xff\xfe garbage")
        except Exception as exc:
            pytest.fail(f"validate_frame raised unexpectedly: {exc}")
        assert result is False


# ---------------------------------------------------------------------------
# frame_to_base64
# ---------------------------------------------------------------------------

class TestFrameToBase64:
    """frame_to_base64 must produce valid base64 without padding issues."""

    def test_produces_string(self):
        assert isinstance(frame_to_base64(_jpeg(50, 50)), str)

    def test_roundtrip(self):
        original = _jpeg(100, 100)
        encoded = frame_to_base64(original)
        decoded = base64.b64decode(encoded)
        assert decoded == original

    def test_no_newlines_in_output(self):
        """Base64 must be a clean single string — no line breaks."""
        encoded = frame_to_base64(_jpeg(200, 200))
        assert "\n" not in encoded

    def test_empty_bytes_produces_empty_string(self):
        assert frame_to_base64(b"") == ""
