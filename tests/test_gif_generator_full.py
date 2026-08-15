import io
from unittest.mock import MagicMock

from PIL import Image

import services.gif_generator as gif_gen


def test_fonts_loaded():
    assert gif_gen.FONT_TITLE is not None
    assert gif_gen.FONT_BODY is not None
    assert gif_gen.FONT_SMALL is not None


def _create_printer(state="RUNNING", percent=50.0):
    printer = MagicMock()
    printer.name = "MyPrinter"
    printer.gcode_state = state
    printer.mc_percent = percent
    printer.nozzle_temper = 200.0
    printer.bed_temper = 60.0
    printer.layer_num = 10
    printer.total_layer_num = 100
    printer.mc_remaining_time = 45
    printer.filament_type = "PLA"
    return printer


def test_gif_generator_running():
    printer = _create_printer("RUNNING", 50.0)
    data = gif_gen.generate_printer_status_gif(printer)

    assert isinstance(data, bytes)
    assert data.startswith(b"GIF87a") or data.startswith(b"GIF89a")

    img = Image.open(io.BytesIO(data))
    assert img.size == (480, 310)
    assert img.mode == "P"

    frames = 0
    try:
        while True:
            frames += 1
            img.seek(frames)
    except EOFError:
        pass

    assert frames == 5


def test_gif_generator_idle():
    printer = _create_printer("IDLE", 0)
    data = gif_gen.generate_printer_status_gif(printer)
    assert data.startswith(b"GIF")


def test_gif_generator_pause():
    printer = _create_printer("PAUSE", 75)
    data = gif_gen.generate_printer_status_gif(printer)
    assert data.startswith(b"GIF")


def test_gif_generator_clamping_negative():
    printer = _create_printer("RUNNING", -10.0)
    data = gif_gen.generate_printer_status_gif(printer)
    assert data.startswith(b"GIF")


def test_gif_generator_clamping_over_100():
    printer = _create_printer("RUNNING", 150.0)
    data = gif_gen.generate_printer_status_gif(printer)
    assert data.startswith(b"GIF")


def test_gif_generator_progress_zero():
    printer = _create_printer("RUNNING", 0)
    data = gif_gen.generate_printer_status_gif(printer)
    assert data.startswith(b"GIF")


def test_gif_generator_progress_100():
    printer = _create_printer("RUNNING", 100.0)
    data = gif_gen.generate_printer_status_gif(printer)
    assert data.startswith(b"GIF")


def test_filament_types():
    printer = _create_printer("RUNNING", 50.0)
    printer.filament_type = "PETG/ABS/TPU"
    data = gif_gen.generate_printer_status_gif(printer)
    assert data.startswith(b"GIF")
