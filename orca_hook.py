import json
import logging
import re
import sys
import time
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
        with open(gcode_path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                line_clean = line.strip()
                if not line_clean.startswith(";"):
                    continue
                line_lower = line_clean.lower()

                if any(
                    k in line_lower
                    for k in [
                        "filament used [g]",
                        "total filament used [g]",
                        "filament weight",
                        "total filament weight",
                        "filament_weight_total",
                        "extruder_weight_total",
                        "filament_used_g",
                        "filament_used",
                        "weight [g]",
                        "used_g",
                    ]
                ):
                    if "[mm]" in line_lower and "[g]" not in line_lower and "weight" not in line_lower:
                        continue

                    after_eq = line_clean.split("=", 1)[-1] if "=" in line_clean else line_clean.split(":", 1)[-1]
                    after_eq_clean = after_eq.split("(")[0]

                    numbers = re.findall(r"\b\d+(?:[\.,]\d+)?\b", after_eq_clean)
                    valid_weights = []
                    for num_str in numbers:
                        try:
                            val = float(num_str.replace(",", "."))
                            if 0.05 <= val <= 5000:
                                valid_weights.append(val)
                        except ValueError:
                            pass

                    if valid_weights:
                        weight = round(sum(valid_weights), 2)
                        break
    except Exception as e:
        logging.error(f"Error reading gcode: {e}")

    if weight > 0:
        logging.info(f"✅ Exact weight extracted from OrcaSlicer: {weight}g for {gcode_path}")
        try:
            WEIGHT_CACHE.parent.mkdir(parents=True, exist_ok=True)
            cache_data = {
                "weight": weight,
                "path": gcode_path,
                "filename": Path(gcode_path).name,
                "timestamp": time.time(),
            }
            with open(WEIGHT_CACHE, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False)
            logging.info(f"💾 Saved cached weight data: {cache_data}")
        except Exception as e:
            logging.error(f"Error writing cache: {e}")


if __name__ == "__main__":
    main()
