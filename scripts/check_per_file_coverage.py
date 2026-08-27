"""
Per-file coverage validation gate.
Parses coverage.json and verifies that every individual module meets its required threshold.
"""

import json
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows terminal
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Per-file minimum required coverage thresholds (%)
PER_FILE_THRESHOLDS = {
    # Critical Tier (Security, Auth, API, User Context)
    "models/user.py": 95.0,
    "models/enums.py": 100.0,
    "services/http/auth.py": 90.0,
    "services/http/routes_auth.py": 75.0,
    "services/http/middleware.py": 85.0,
    "services/http/routes_printers.py": 75.0,
    "services/http/routes_control.py": 75.0,
    "services/http/routes_files.py": 55.0,
    "services/http/routes_parts.py": 80.0,
    "services/http/routes_spools.py": 60.0,
    "services/http/routes_sse.py": 80.0,
    "services/http/routes_settings.py": 70.0,
    "services/http_server.py": 80.0,
    "services/gif_generator.py": 85.0,
    "services/camera_stream.py": 60.0,
    "services/report_generator.py": 30.0,
    "utils/math_eval.py": 90.0,
    "utils/filament_utils.py": 85.0,
    # Domain & Infrastructure Tier
    "models/commercial.py": 85.0,
    "services/mqtt_message_parser.py": 75.0,
    "services/gcode_parser.py": 60.0,
    "config.py": 60.0,
    "storage/manager.py": 55.0,
    "services/ftps_client.py": 50.0,
    "models/printer.py": 50.0,
    "utils/retry.py": 20.0,
}

# Absolute minimum floor for any tracked file not explicitly listed above
DEFAULT_FILE_FLOOR = 40.0


def validate_per_file_coverage(coverage_file: Path) -> bool:
    if not coverage_file.exists():
        print(f"[ERROR] Coverage file '{coverage_file}' not found!")
        return False

    with coverage_file.open("r", encoding="utf-8") as f:
        data = json.load(f)

    files_data = data.get("files", {})
    failed_files = []
    passed_files = []

    print("\nChecking Per-File Coverage Thresholds:")
    print("=" * 70)

    for file_path_raw, stats in sorted(files_data.items()):
        # Normalize path separators
        norm_path = file_path_raw.replace("\\", "/")
        # Match against relative project path
        matched_key = None
        for key in PER_FILE_THRESHOLDS:
            if norm_path.endswith(key):
                matched_key = key
                break

        summary = stats.get("summary", {})
        percent = summary.get("percent_covered", 0.0)
        required = PER_FILE_THRESHOLDS.get(matched_key, DEFAULT_FILE_FLOOR) if matched_key else DEFAULT_FILE_FLOOR

        display_name = matched_key if matched_key else norm_path

        if percent < required:
            failed_files.append((display_name, percent, required))
            print(f"[FAIL] {display_name:<40} {percent:>6.2f}% (Required: {required:>5.1f}%)")
        else:
            passed_files.append((display_name, percent, required))
            print(f"[PASS] {display_name:<40} {percent:>6.2f}% (Required: {required:>5.1f}%)")

    print("=" * 70)
    total_covered = data.get("totals", {}).get("percent_covered", 0.0)
    print(f"Total Project Coverage: {total_covered:.2f}%\n")

    if failed_files:
        print(f"[BLOCKED] {len(failed_files)} file(s) failed per-file coverage requirements:")
        for name, pct, req in failed_files:
            print(f"   * {name}: {pct:.2f}% < {req:.1f}%")
        return False

    print(f"[SUCCESS] All {len(passed_files)} tracked files met or exceeded their per-file coverage floors!")
    return True


if __name__ == "__main__":
    json_path = Path("coverage.json")
    if len(sys.argv) > 1:
        json_path = Path(sys.argv[1])

    success = validate_per_file_coverage(json_path)
    sys.exit(0 if success else 1)
