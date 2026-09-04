"""
3D Printer Farm Telegram Bot entrypoint wrapper (re-exports main.py).
"""

import importlib.util
from pathlib import Path

_module_path = Path(__file__).with_name("main.py")
_spec = importlib.util.spec_from_file_location("main", _module_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Could not load main module from {_module_path}")
_main_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_main_module)
main = _main_module.main

if __name__ == "__main__":
    main()
