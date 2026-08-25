"""
Unit tests for image compression and optimization utilities.
"""

import io
from PIL import Image
from utils.image_utils import compress_part_photo, MAX_DIMENSION, JPEG_QUALITY


def test_compress_part_photo_large_png():
    # Create a 2000x1500 RGBA PNG image in memory
    img = Image.new("RGBA", (2000, 1500), color=(255, 100, 50, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw_bytes = buf.getvalue()

    # Compress
    compressed = compress_part_photo(raw_bytes)
    assert len(compressed) > 0
    assert len(compressed) < len(raw_bytes)

    # Open compressed result and check properties
    res_img = Image.open(io.BytesIO(compressed))
    assert res_img.format == "JPEG"
    assert res_img.mode == "RGB"
    assert max(res_img.width, res_img.height) <= MAX_DIMENSION


def test_compress_part_photo_small_jpeg():
    # Create a small 400x300 RGB JPEG image in memory
    img = Image.new("RGB", (400, 300), color=(100, 200, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    raw_bytes = buf.getvalue()

    # Compress
    compressed = compress_part_photo(raw_bytes)
    assert len(compressed) > 0

    res_img = Image.open(io.BytesIO(compressed))
    assert res_img.format == "JPEG"
    assert res_img.width == 400
    assert res_img.height == 300
