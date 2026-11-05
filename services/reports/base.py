"""
Base PDF reporting utilities, TrueType font setup, and dynamic page-numbered canvas.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

_FONTS_INITIALIZED = False
_FONT_REGULAR = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"


def _setup_reportlab_fonts() -> tuple[str, str]:
    """Registers TrueType font supporting Cyrillic/Ukrainian characters if available."""
    global _FONTS_INITIALIZED, _FONT_REGULAR, _FONT_BOLD
    if _FONTS_INITIALIZED:
        return _FONT_REGULAR, _FONT_BOLD

    candidates = [
        # Linux / Raspberry Pi standard system paths
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ),
        (
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ),
        (
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        ),
        # Windows system paths
        ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
        ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
    ]

    for reg_path, bold_path in candidates:
        if os.path.exists(reg_path):
            try:
                pdfmetrics.registerFont(TTFont("ReportCyrillic", reg_path))
                _FONT_REGULAR = "ReportCyrillic"
                if os.path.exists(bold_path):
                    pdfmetrics.registerFont(TTFont("ReportCyrillicBold", bold_path))
                    _FONT_BOLD = "ReportCyrillicBold"
                else:
                    _FONT_BOLD = "ReportCyrillic"
                break
            except Exception:
                pass

    _FONTS_INITIALIZED = True
    return _FONT_REGULAR, _FONT_BOLD


class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to dynamically calculate total pages and render uniform footers."""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_decorations(self, page_count: int) -> None:
        self.saveState()
        font_reg, _ = _setup_reportlab_fonts()
        self.setFont(font_reg, 8)
        self.setFillColor(colors.HexColor("#64748b"))

        # Footer divider line
        w, _ = self._pagesize
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(20, 25, w - 20, 25)

        # Footer text
        self.drawString(20, 14, "3D Farm Bot Management System • Автоматичний звіт")
        page_str = f"Сторінка {self._pageNumber} з {page_count}"
        self.drawRightString(w - 20, 14, page_str)
        self.restoreState()


def _resolve_printer_name(printer_id: str | None, printers: Any = None) -> str:
    """Resolves human-readable printer name from id and optional printers collection."""
    if not printer_id:
        return "Невідомий принтер"
    p_id_str = str(printer_id).strip()
    if printers:
        if isinstance(printers, dict):
            p = printers.get(p_id_str)
            if p:
                if isinstance(p, dict):
                    return str(p.get("name") or p_id_str)
                return str(getattr(p, "name", None) or p_id_str)
            for item in printers.values():
                pid = item.get("id") if isinstance(item, dict) else getattr(item, "id", None)
                if pid and str(pid).strip() == p_id_str:
                    if isinstance(item, dict):
                        return str(item.get("name") or p_id_str)
                    return str(getattr(item, "name", None) or p_id_str)
        elif isinstance(printers, (list, tuple)):
            for item in printers:
                pid = item.get("id") if isinstance(item, dict) else getattr(item, "id", None)
                if pid and str(pid).strip() == p_id_str:
                    if isinstance(item, dict):
                        return str(item.get("name") or p_id_str)
                    return str(getattr(item, "name", None) or p_id_str)
    try:
        for cand in [Path("printers_storage/printers.json"), Path("printers.json")]:
            if cand.exists():
                with open(cand, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and str(item.get("id")).strip() == p_id_str:
                                return str(item.get("name") or p_id_str)
                    elif isinstance(data, dict):
                        item = data.get(p_id_str)
                        if isinstance(item, dict):
                            return str(item.get("name") or p_id_str)
    except Exception:
        pass
    return f"Принтер {p_id_str}"


def _format_slot_name(slot_key: Any) -> str:
    """Formats slot key into human-friendly Ukrainian slot description."""
    if slot_key is None:
        return "Невідомий слот"
    slot_str = str(slot_key).strip()
    slot_map = {
        "0": "Слот A1 (AMS)",
        "1": "Слот A2 (AMS)",
        "2": "Слот A3 (AMS)",
        "3": "Слот A4 (AMS)",
        "254": "Слот VT (Зовнішній)",
        "255": "Слот VT (Зовнішній)",
    }
    if slot_str in slot_map:
        return slot_map[slot_str]
    return f"Слот {slot_str}"
