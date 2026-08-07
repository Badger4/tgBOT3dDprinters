"""
Animated GIF status card generator for 3D printer telemetry.
"""
import io
from typing import Any
from PIL import Image, ImageDraw, ImageFont

# Cached fonts to prevent re-reading files from disk on every frame
try:
    FONT_TITLE = ImageFont.truetype("arial.ttf", 18)
    FONT_BODY = ImageFont.truetype("arial.ttf", 14)
    FONT_SMALL = ImageFont.truetype("arial.ttf", 12)
except Exception:
    FONT_TITLE = ImageFont.load_default()
    FONT_BODY = ImageFont.load_default()
    FONT_SMALL = ImageFont.load_default()

def generate_printer_status_gif(printer: Any) -> bytes:
    """Generates an instant dynamic animated GIF showing live 3D printing simulation & telemetry."""
    width, height = 480, 310
    frames = []
    num_frames = 10
    progress_pct = max(0, min(100, printer.mc_percent if printer.gcode_state in ["RUNNING", "PAUSE"] else 0))

    for frame_idx in range(num_frames):
        img = Image.new("RGB", (width, height), color="#18181b")
        draw = ImageDraw.Draw(img)

        # Header bar
        draw.rectangle([(0, 0), (width, 45)], fill="#27272a")
        status_color = "#22c55e" if printer.gcode_state == "RUNNING" else ("#f59e0b" if printer.gcode_state == "PAUSE" else "#3b82f6")
        draw.ellipse([(14, 16), (26, 28)], fill=status_color)
        draw.text((34, 12), f"{printer.name} [{printer.gcode_state}]", fill="#ffffff", font=FONT_TITLE)

        # Telemetry panel (Left)
        draw.rectangle([(12, 55), (225, 240)], fill="#27272a", outline="#3f3f46", width=1)

        info_lines = [
            f"🔥 Nozzle: {printer.nozzle_temper}°C",
            f"🛏️ Bed: {printer.bed_temper}°C",
            f"🥞 Layer: {printer.layer_num}/{printer.total_layer_num}",
            f"⏱️ Time: ~{printer.mc_remaining_time}m",
            f"🧵 Plastic: {printer.filament_type}"
        ]

        y_off = 65
        for line in info_lines:
            draw.text((22, y_off), line, fill="#e4e4e7", font=FONT_SMALL)
            y_off += 33

        # Simulated 3D Printer Bed (Right)
        bed_x1, bed_y1, bed_x2, bed_y2 = 240, 150, 465, 230
        draw.rectangle([(bed_x1, bed_y1), (bed_x2, bed_y2)], fill="#27272a", outline="#0284c7", width=2)

        for gx in range(bed_x1 + 25, bed_x2, 35):
            draw.line([(gx, bed_y1), (gx, bed_y2)], fill="#3f3f46", width=1)

        # Extruder & Nozzle Animation
        if printer.gcode_state == "RUNNING":
            offset = (frame_idx / num_frames) * (bed_x2 - bed_x1 - 40)
            nozzle_x = bed_x1 + 20 + offset
            nozzle_y = bed_y1 - 35

            draw.rectangle([(bed_x1 + 10, bed_y1 - 8), (nozzle_x, bed_y1 - 2)], fill="#38bdf8")
            draw.rectangle([(nozzle_x - 12, nozzle_y), (nozzle_x + 12, nozzle_y + 22)], fill="#71717a")
            draw.polygon([(nozzle_x - 4, nozzle_y + 22), (nozzle_x + 4, nozzle_y + 22), (nozzle_x, nozzle_y + 30)], fill="#f97316")
        else:
            draw.rectangle([(bed_x1 + 10, bed_y1 - 35), (bed_x1 + 34, bed_y1 - 13)], fill="#52525b")

        # Progress bar (Bottom)
        draw.rectangle([(12, 252), (468, 290)], fill="#27272a", outline="#3f3f46")
        prog_w = int((progress_pct / 100.0) * (468 - 14))
        if prog_w > 0:
            draw.rectangle([(13, 253), (13 + prog_w, 289)], fill="#0284c7")

        draw.text((200, 261), f"Progress: {progress_pct}%", fill="#ffffff", font=FONT_BODY)
        frames.append(img)

    out_buffer = io.BytesIO()
    frames[0].save(out_buffer, format="GIF", save_all=True, append_images=frames[1:], duration=180, loop=0)
    return out_buffer.getvalue()
