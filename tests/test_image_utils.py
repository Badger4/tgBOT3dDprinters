"""
Unit tests for image compression, plate diagram, and plate GIF rendering utilities.
"""

import io
from PIL import Image
from utils.image_utils import (
    compress_part_photo,
    render_plate_diagram,
    render_plate_gif,
    MAX_DIMENSION,
)


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


def test_render_plate_diagram_valid_objects():
    objects = [
        {"id": "1", "name": "Gear #1", "bbox": [10.0, 10.0, 50.0, 50.0]},
        {"id": "2", "name": "Box #2", "bbox": [60.0, 60.0, 110.0, 110.0]},
    ]
    jpeg_bytes = render_plate_diagram(objects, bed_size_mm=(256, 256), skipped_ids=[1])
    assert len(jpeg_bytes) > 0

    img = Image.open(io.BytesIO(jpeg_bytes))
    assert img.format == "JPEG"
    assert img.width > 700
    assert img.height > 700


def test_render_plate_diagram_fallback_grid_and_small_bed():
    # Objects without explicit bbox -> fallback 2D grid allocation
    objects = [
        {"id": 1, "name": "Part A"},
        {"id": 2, "name": "Part B"},
        {"id": 3, "name": "Part C"},
    ]
    jpeg_bytes = render_plate_diagram(objects, bed_size_mm=(180, 180), skipped_ids=["2"])
    assert len(jpeg_bytes) > 0

    img = Image.open(io.BytesIO(jpeg_bytes))
    assert img.format == "JPEG"


def test_render_plate_diagram_empty_objects():
    jpeg_bytes = render_plate_diagram([], bed_size_mm=(256, 256))
    assert len(jpeg_bytes) > 0

    img = Image.open(io.BytesIO(jpeg_bytes))
    assert img.format == "JPEG"


def test_render_plate_gif_valid_objects():
    objects = [
        {"id": "1", "name": "Obj 1", "bbox": [15.0, 15.0, 45.0, 45.0]},
        {"id": "2", "name": "Obj 2", "bbox": [70.0, 70.0, 120.0, 120.0]},
    ]
    gif_bytes = render_plate_gif(objects, bed_size_mm=(256, 256), skipped_ids=["1"])
    assert len(gif_bytes) > 0

    img = Image.open(io.BytesIO(gif_bytes))
    assert img.format == "GIF"


def test_render_plate_gif_empty():
    gif_bytes = render_plate_gif([])
    assert gif_bytes == b""
