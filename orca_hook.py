import sys
import re
import json
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "orca_hook.log"
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format="%(asctime)s - %(message)s")

WEIGHT_CACHE = BASE_DIR / "printers_storage" / "last_sliced_weight.json"

def main():
    if len(sys.argv) < 2:
        logging.info("No gcode file argument provided.")
        return

    gcode_path = sys.argv[1]
    logging.info(f"Processing G-code file from OrcaSlicer: {gcode_path}")

    weight = 0.0
    try:
        with open(gcode_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line_lower = line.lower()
                # Exclude lines containing length in [mm]
                if "[mm]" in line_lower or "length" in line_lower:
                    continue

                # Look specifically for filament weight in grams
                if any(k in line_lower for k in ["filament weight", "total filament weight", "filament_weight_total", "filament used [g]", "extruder_weight_total", "weight [g]"]):
                    m = re.search(r'(?:=|\:)\s*([\d\.]+)', line)
                    if m:
                        try:
                            val = float(m.group(1))
                            if 0 < val < 5000:
                                weight = val
                                break
                        except ValueError:
                            pass
    except Exception as e:
        logging.error(f"Error reading gcode: {e}")

    if weight > 0:
        logging.info(f"✅ Exact weight extracted from OrcaSlicer: {weight}g")
        try:
            WEIGHT_CACHE.parent.mkdir(parents=True, exist_ok=True)
            with open(WEIGHT_CACHE, 'w', encoding='utf-8') as f:
                json.dump({"weight": weight, "path": gcode_path}, f)
        except Exception as e:
            logging.error(f"Error writing cache: {e}")

if __name__ == "__main__":
    main()
