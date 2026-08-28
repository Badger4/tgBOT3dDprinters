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


def _load_unicode_font(size: int = 14) -> Any:
    if Image is None:
        return None
    try:
        from PIL import ImageFont

        font_candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "DejaVuSans.ttf",
            "arial.ttf",
            "Arial.ttf",
        ]
        for font_path in font_candidates:
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                pass
    except Exception:
        pass
    return None


def _safe_draw_text(draw: Any, xy: tuple[int, int], text: str, fill: str, font: Any = None) -> None:
    try:
        if font:
            draw.text(xy, text, fill=fill, font=font)
        else:
            draw.text(xy, text, fill=fill)
    except Exception:
        # Fallback transliteration to ASCII for latin-1 restricted default fonts
        translit_map = {
            "Спереду": "Front",
            "Ззаду": "Back",
            "Ліворуч": "Left",
            "Праворуч": "Right",
            "По центру": "Center",
            "Об'єкт": "Object",
            "Пропущено": "Skipped",
        }
        safe_text = text
        for k, v in translit_map.items():
            safe_text = safe_text.replace(k, v)
        safe_text = "".join(c if ord(c) < 128 else "" for c in safe_text).strip()
        if not safe_text:
            safe_text = "Object"
        try:
            draw.text(xy, safe_text, fill=fill)
        except Exception:
            pass


def render_plate_diagram(
    objects: list[dict[str, Any]],
    bed_size_mm: tuple[int, int] = (256, 256),
    skipped_ids: list[Any] | None = None,
) -> bytes:
    """
    Renders a 2D top-down visual map diagram of the print bed with bounding boxes and object IDs.
    - Green boxes: Active objects
    - Red boxes: Skipped objects
    """
    if Image is None:
        return b""

    try:
        from PIL import ImageDraw

        font = _load_unicode_font(14)
        skipped_set = {str(s) for s in (skipped_ids or [])}
        bed_w, bed_h = bed_size_mm
        scale = 3.0  # 3 px per mm -> 768x768 canvas
        margin = 45  # margin for axes labels

        img_w = int(bed_w * scale + margin * 2)
        img_h = int(bed_h * scale + margin * 2)

        img = Image.new("RGB", (img_w, img_h), color="#16161a")
        draw = ImageDraw.Draw(img)

        # Bed outline
        bx1 = margin
        by1 = margin
        bx2 = margin + int(bed_w * scale)
        by2 = margin + int(bed_h * scale)

        draw.rectangle([bx1, by1, bx2, by2], outline="#3a3a4c", width=3, fill="#1e1e24")

        # Grid lines every 50mm
        for mm in range(50, bed_w, 50):
            gx = margin + int(mm * scale)
            draw.line([gx, by1, gx, by2], fill="#282834", width=1)
        for mm in range(50, bed_h, 50):
            gy = margin + int(mm * scale)
            draw.line([bx1, gy, bx2, gy], fill="#282834", width=1)

        # Axes orientation labels
        _safe_draw_text(draw, (img_w // 2 - 45, by2 + 12), "Спереду (Front)", fill="#8a8a9c", font=font)
        _safe_draw_text(draw, (img_w // 2 - 35, by1 - 25), "Ззаду (Back)", fill="#8a8a9c", font=font)
        _safe_draw_text(draw, (bx1 - 38, img_h // 2 - 10), "Ліворуч", fill="#8a8a9c", font=font)
        _safe_draw_text(draw, (bx2 + 8, img_h // 2 - 10), "Праворуч", fill="#8a8a9c", font=font)

        # Check grid fallback if bbox is missing
        n_objs = len(objects)
        cols = 3 if n_objs >= 4 else (2 if n_objs >= 2 else 1)
        rows = (n_objs + cols - 1) // cols if cols > 0 else 1

        import re

        for idx, obj in enumerate(objects):
            obj_id = str(obj.get("id", idx + 1)).strip()
            raw_name = str(obj.get("name", f"Об'єкт #{obj_id}")).strip()

            # Clean object name for display on map
            clean_name = re.sub(r"\s*#\d+.*$", "", raw_name)
            clean_name = re.sub(r"\s*\(.*?\)$", "", clean_name).strip()
            if not clean_name:
                clean_name = f"Об'єкт #{obj_id}"

            is_skipped = obj_id in skipped_set or (
                obj_id.isdigit() and int(obj_id) in [int(s) for s in skipped_set if s.isdigit()]
            )

            bbox = obj.get("bbox")
            if not bbox or not isinstance(bbox, list) or len(bbox) < 4:
                # Fallback 2D grid allocation on plate
                r = idx // cols
                c = idx % cols
                cell_w = bed_w / cols
                cell_h = bed_h / rows
                xmin = c * cell_w + cell_w * 0.15
                xmax = (c + 1) * cell_w - cell_w * 0.15
                ymin = r * cell_h + cell_h * 0.15
                ymax = (r + 1) * cell_h - cell_h * 0.15
                bbox = [xmin, ymin, xmax, ymax]

            try:
                xmin, ymin, xmax, ymax = [float(v) for v in bbox[:4]]
            except Exception:
                xmin, ymin, xmax, ymax = 10.0, 10.0, 50.0, 50.0

            # Convert to screen coordinates (Bambu Y=0 is front -> by2)
            px1 = margin + int(xmin * scale)
            px2 = margin + int(xmax * scale)
            py1 = by2 - int(ymax * scale)
            py2 = by2 - int(ymin * scale)

            # Ensure minimum bounding box dimension for small objects
            if px2 - px1 < 30:
                px2 = px1 + 30
            if py2 - py1 < 30:
                py1 = py2 - 30

            # Styling
            if is_skipped:
                fill_col = "#3d1616"
                border_col = "#ff4444"
                text_col = "#ff9999"
                status_label = " ❌"
            else:
                fill_col = "#13382c"
                border_col = "#00ffaa"
                text_col = "#ffffff"
                status_label = ""

            draw.rectangle([px1, py1, px2, py2], fill=fill_col, outline=border_col, width=3)

            # Text inside/above object box
            badge_text = f"#{obj_id}: {clean_name[:14]}{status_label}"
            _safe_draw_text(draw, (px1 + 6, py1 + 6), badge_text, fill=text_col, font=font)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=88)
        return buffer.getvalue()
    except Exception as e:
        import logging

        logging.warning(f"Failed rendering plate diagram: {e}")
        return b""


def render_plate_gif(
    objects: list[dict[str, Any]],
    bed_size_mm: tuple[int, int] = (256, 256),
    skipped_ids: list[Any] | None = None,
    frame_duration_ms: int = 900,
) -> bytes:
    """
    Renders an animated GIF sequentially highlighting each object on the print bed with its #ID.
    Ideal for <= 6 objects to clarify spatial layout.
    """
    if Image is None or not objects:
        return b""

    try:
        from PIL import ImageDraw

        font_large = _load_unicode_font(20)
        font_small = _load_unicode_font(12)
        skipped_set = {str(s) for s in (skipped_ids or [])}
        bed_w, bed_h = bed_size_mm
        scale = 2.0  # 2 px per mm for fast GIF frame generation
        margin = 35

        img_w = int(bed_w * scale + margin * 2)
        img_h = int(bed_h * scale + margin * 2)

        import re

        n_objs = len(objects)
        cols = 3 if n_objs >= 4 else (2 if n_objs >= 2 else 1)
        rows = (n_objs + cols - 1) // cols if cols > 0 else 1

        processed_objs = []
        for idx, obj in enumerate(objects):
            obj_id = str(obj.get("id", idx + 1)).strip()
            raw_name = str(obj.get("name", f"Об'єкт #{obj_id}")).strip()

            clean_name = re.sub(r"\s*#\d+.*$", "", raw_name)
            clean_name = re.sub(r"\s*\(.*?\)$", "", clean_name).strip()
            if not clean_name:
                clean_name = f"Об'єкт #{obj_id}"

            bbox = obj.get("bbox")
            if not bbox or not isinstance(bbox, list) or len(bbox) < 4:
                r = idx // cols
                c = idx % cols
                cell_w = bed_w / cols
                cell_h = bed_h / rows
                xmin = c * cell_w + cell_w * 0.15
                xmax = (c + 1) * cell_w - cell_w * 0.15
                ymin = r * cell_h + cell_h * 0.15
                ymax = (r + 1) * cell_h - cell_h * 0.15
                bbox = [xmin, ymin, xmax, ymax]

            processed_objs.append({"id": obj_id, "name": clean_name, "bbox": bbox})

        frames = []

        for h_obj in processed_objs:
            img = Image.new("RGB", (img_w, img_h), color="#16161a")
            draw = ImageDraw.Draw(img)

            # Bed outline
            bx1 = margin
            by1 = margin
            bx2 = margin + int(bed_w * scale)
            by2 = margin + int(bed_h * scale)
            draw.rectangle([bx1, by1, bx2, by2], outline="#3a3a4c", width=2, fill="#1e1e24")

            # Grid lines
            for mm in range(50, bed_w, 50):
                gx = margin + int(mm * scale)
                draw.line([gx, by1, gx, by2], fill="#282834", width=1)
            for mm in range(50, bed_h, 50):
                gy = margin + int(mm * scale)
                draw.line([bx1, gy, bx2, gy], fill="#282834", width=1)

            # Axes labels
            _safe_draw_text(draw, (img_w // 2 - 35, by2 + 8), "Спереду", fill="#7a7a8c", font=font_small)
            _safe_draw_text(draw, (img_w // 2 - 25, by1 - 20), "Ззаду", fill="#7a7a8c", font=font_small)

            for obj in processed_objs:
                obj_id = obj["id"]
                is_highlighted = obj_id == h_obj["id"]
                is_skipped = obj_id in skipped_set or (
                    obj_id.isdigit() and int(obj_id) in [int(s) for s in skipped_set if s.isdigit()]
                )

                try:
                    xmin, ymin, xmax, ymax = [float(v) for v in obj["bbox"][:4]]
                except Exception:
                    xmin, ymin, xmax, ymax = 10.0, 10.0, 50.0, 50.0

                px1 = margin + int(xmin * scale)
                px2 = margin + int(xmax * scale)
                py1 = by2 - int(ymax * scale)
                py2 = by2 - int(ymin * scale)

                if px2 - px1 < 25:
                    px2 = px1 + 25
                if py2 - py1 < 25:
                    py1 = py2 - 25

                if is_highlighted:
                    fill_col = "#3d1616" if is_skipped else "#1b4d3e"
                    border_col = "#ff4444" if is_skipped else "#00ffaa"
                    border_w = 4
                else:
                    fill_col = "#1a1a20"
                    border_col = "#ff4444" if is_skipped else "#333344"
                    border_w = 1

                draw.rectangle([px1, py1, px2, py2], fill=fill_col, outline=border_col, width=border_w)

                if is_highlighted:
                    # Large centered ID tag
                    cx = (px1 + px2) // 2
                    cy = (py1 + py2) // 2
                    tag = f"#{obj_id}"
                    _safe_draw_text(draw, (cx - 12, cy - 10), tag, fill="#ff4444" if is_skipped else "#00ffaa", font=font_large)

            frames.append(img)

        buffer = io.BytesIO()
        frames[0].save(
            buffer,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=frame_duration_ms,
            loop=0,
            optimize=True,
        )
        return buffer.getvalue()
    except Exception as e:
        import logging

        logging.warning(f"Failed rendering plate GIF: {e}")
        return b""
