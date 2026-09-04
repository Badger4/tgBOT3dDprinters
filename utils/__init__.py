"""
Utility functions package (backward-compatibility alias for functions package).
"""

from functions.filament_utils import extract_filament_type_from_name, parse_slot_key_from_text
from functions.i18n import t, get_user_lang, set_user_lang
from functions.image_utils import render_plate_diagram, render_plate_gif
from functions.math_eval import safe_eval_math
from functions.retry import async_retry
from functions.spool_fingerprint import delete_active_print_context, record_active_print_context, save_active_print_context

__all__ = [
    "t",
    "get_user_lang",
    "set_user_lang",
    "render_plate_diagram",
    "render_plate_gif",
    "safe_eval_math",
    "parse_slot_key_from_text",
    "extract_filament_type_from_name",
    "async_retry",
    "record_active_print_context",
    "save_active_print_context",
    "delete_active_print_context",
]
