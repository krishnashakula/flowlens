"""Pytest configuration for FlowLens backend tests."""

import io
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from PIL import Image

# Make the backend importable without installing
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Image factories
# ---------------------------------------------------------------------------

def make_png(width: int = 100, height: int = 100, color=(30, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


def make_jpeg(width: int = 100, height: int = 100, color=(30, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def make_rgba_png(width: int = 100, height: int = 100) -> bytes:
    """PNG with alpha channel — must be stripped by compress_frame."""
    buf = io.BytesIO()
    Image.new("RGBA", (width, height), (0, 128, 255, 200)).save(buf, format="PNG")
    return buf.getvalue()


def make_grayscale_png(width: int = 100, height: int = 100) -> bytes:
    buf = io.BytesIO()
    Image.new("L", (width, height), 128).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def small_png():
    return make_png(100, 100)


@pytest.fixture
def large_png():
    """2560×1440 — must be downscaled to max 1280×720."""
    return make_png(2560, 1440)


@pytest.fixture
def wide_png():
    """3840×1080 ultrawide — aspect ratio must be preserved, not cropped."""
    return make_png(3840, 1080)


@pytest.fixture
def rgba_png():
    return make_rgba_png()


@pytest.fixture
def jpeg_frame():
    return make_jpeg(640, 480)


# ---------------------------------------------------------------------------
# Redis fake
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_redis():
    """
    Async Redis fake backed by a plain dict.
    Exposes ._store and ._expiries for test assertions.
    """
    store: dict = {}
    expiries: dict = {}
    redis = AsyncMock()

    async def _get(key):
        return store.get(key)

    async def _setex(key, ttl, value):
        store[key] = value if isinstance(value, bytes) else str(value).encode()
        expiries[key] = ttl

    async def _delete(key):
        store.pop(key, None)
        expiries.pop(key, None)

    async def _ping():
        return b"PONG"

    redis.get.side_effect = _get
    redis.setex.side_effect = _setex
    redis.delete.side_effect = _delete
    redis.ping.side_effect = _ping
    redis._store = store
    redis._expiries = expiries
    return redis


@pytest.fixture
def null_redis():
    """Simulates Redis being unavailable."""
    return None


@pytest.fixture
def broken_redis():
    """Redis that raises on every call — tests graceful degradation."""
    r = AsyncMock()
    r.get.side_effect = ConnectionError("Redis unreachable")
    r.setex.side_effect = ConnectionError("Redis unreachable")
    r.delete.side_effect = ConnectionError("Redis unreachable")
    r.ping.side_effect = ConnectionError("Redis unreachable")
    return r
