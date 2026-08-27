"""
Image optimization and compression utilities for 3D part photos and previews.
"""

import io
from typing import Any

try:
    from PIL import Image, ImageOps
except ImportError:
    Image = None  # type: ignore[assignment]
    ImageOps = None  # type: ignore[assignment]

MAX_DIMENSION = 800       # Maximum dimension for longest side (px)
JPEG_QUALITY = 80         # Target JPEG quality
MAX_FILE_SIZE_KB = 250     # Target file size reference (KB)


def compress_part_photo(raw_bytes: bytes) -> bytes:
    """
    Стискає фото деталі перед збереженням: EXIF orientation correction,
    RGB conversion, LANCZOS thumbnail to MAX_DIMENSION, and JPEG re-encoding.
    """
    if Image is None:
        return raw_bytes

    img_raw = Image.open(io.BytesIO(raw_bytes))

    # 1. Fix orientation from EXIF metadata
    img: Image.Image = ImageOps.exif_transpose(img_raw)

    # 2. Convert to RGB (PNG with alpha channel or HEIC/P/RGBA will break JPEG saving)
    if img.mode != "RGB":
        img = img.convert("RGB")

    # 3. Downscale if longer side exceeds MAX_DIMENSION
    resample_filter = getattr(Image, "Resampling", Image).LANCZOS
    img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), resample_filter)

    # 4. Save as optimized JPEG in memory
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buffer.getvalue()
