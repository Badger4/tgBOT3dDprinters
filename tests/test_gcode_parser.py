"""
Unit tests for services/gcode_parser.py functions and 3MF parsing edge cases.
"""

import io
import unittest
import zipfile

from services.gcode_parser import (
    check_compatibility,
    format_print_time_human,
    parse_3mf_file,
    parse_time_str,
    resolve_model_name,
    sanitize_object_name,
)


class TestGcodeParser(unittest.TestCase):
    def test_sanitize_object_name(self):
        self.assertEqual(sanitize_object_name(""), "")
        self.assertEqual(sanitize_object_name(None), "")
        self.assertEqual(sanitize_object_name("Box #1 (Спереду)"), "Box #1 (Спереду)")
        self.assertEqual(sanitize_object_name("Gear #2 (Ззаду Ліворуч)"), "Gear #2 (Ззаду Ліворуч)")
        self.assertEqual(sanitize_object_name("Bracket"), "Bracket")
        self.assertEqual(sanitize_object_name("Bracket (По центру)"), "Bracket (По центру)")

        # Idempotency check
        raw = "Component #3 (Спереду Праворуч)"
        first_pass = sanitize_object_name(raw)
        second_pass = sanitize_object_name(first_pass)
        self.assertEqual(first_pass, second_pass)

    def test_parse_time_str(self):
        self.assertEqual(parse_time_str("1h 30m"), 90)
        self.assertEqual(parse_time_str("45m"), 45)
        self.assertEqual(parse_time_str("01:15:00"), 75)
        self.assertEqual(parse_time_str("70:00"), 70)
        self.assertEqual(parse_time_str("8d 18h 54m 54s"), 8 * 1440 + 18 * 60 + 54)
        self.assertEqual(
            parse_time_str("model printing time: 8d 18h 54m 54s; total estimated time: 8d 19h 1m 9s"),
            8 * 1440 + 19 * 60 + 1,
        )
        self.assertEqual(parse_time_str(""), 0)

    def test_format_print_time_human(self):
        self.assertEqual(format_print_time_human(0), "0 хв")
        self.assertEqual(format_print_time_human(-5), "0 хв")
        self.assertEqual(format_print_time_human(45), "~45 хв")
        self.assertEqual(format_print_time_human(135), "~2г 15хв (135 хв)")
        self.assertEqual(format_print_time_human(1440 + 65), "~1д 1г 5хв (1505 хв)")

    def test_resolve_model_name(self):
        self.assertEqual(resolve_model_name("n2s"), "Bambu Lab A1 mini")
        self.assertEqual(resolve_model_name("n1"), "Bambu Lab A1")
        self.assertEqual(resolve_model_name("c12"), "Bambu Lab P1S")
        self.assertEqual(resolve_model_name("c11"), "Bambu Lab P1S")
        self.assertEqual(resolve_model_name("c10"), "Bambu Lab X1 Carbon")
        self.assertEqual(resolve_model_name("x1"), "Bambu Lab X1 Carbon")
        self.assertEqual(resolve_model_name("Bambu ABS @BBL A1"), "Bambu Lab A1")
        self.assertEqual(resolve_model_name("Bambu ABS @BBL A1M"), "Bambu Lab A1 mini")
        self.assertEqual(resolve_model_name("Unknown"), "Unknown")
        self.assertEqual(resolve_model_name("generic"), "Unknown")
        self.assertEqual(resolve_model_name(""), "Unknown")
        self.assertEqual(resolve_model_name(None), "Unknown")

    def test_check_compatibility(self):
        # Same printer model
        res1 = check_compatibility("Bambu Lab A1", "PLA", "Bambu Lab A1")
        self.assertTrue(res1["compatible"])
        self.assertEqual(res1["level"], "OK")

        # Unknown file model - OK level
        res_unk = check_compatibility("Unknown", "PLA", "Bambu Lab A1")
        self.assertTrue(res_unk["compatible"])
        self.assertEqual(res_unk["level"], "OK")

        # Incompatible model (P1S gcode on A1 mini)
        res2 = check_compatibility("Bambu Lab P1S", "PLA", "Bambu Lab A1 mini")
        self.assertFalse(res2["compatible"])
        self.assertEqual(res2["level"], "BLOCK")

        # Material mismatch test (TPU 3MF vs ABS active spool)
        res4 = check_compatibility("Bambu Lab A1", "TPU", "Bambu Lab A1", "Bambu ABS")
        self.assertFalse(res4["compatible"])
        self.assertEqual(res4["reason_type"], "FILAMENT")
        self.assertIn("Філамент несумісний з файлом", res4["reason"])

    def test_parse_3mf_file_non_3mf(self):
        result = parse_3mf_file(b"not a zip file", "test.txt")
        self.assertFalse(result["valid"])
        self.assertIn("Дозволено завантажувати тільки файли .3mf", result["error"])

    def test_parse_3mf_file_valid_zip(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            slice_info_xml = """<?xml version="1.0" encoding="UTF-8"?>
            <config>
                <printer_model_id>n2s</printer_model_id>
                <filament_type>PETG</filament_type>
                <object identify_id="1" name="Cover_Plate"/>
                <object identify_id="2" name="Base_Holder"/>
            </config>
            """
            zf.writestr("Metadata/slice_info.config", slice_info_xml)

            plate_json = """{
                "objects": [
                    {"id": "1", "name": "Cover_Plate", "bbox": [10.0, 10.0, 50.0, 50.0]},
                    {"id": "2", "name": "Base_Holder", "bbox": [60.0, 60.0, 100.0, 100.0]}
                ]
            }"""
            zf.writestr("Metadata/plate_1.json", plate_json)

            gcode_content = """; filament used [g] = 42.5
            ; total estimated time = 1h 15m
            """
            zf.writestr("Metadata/plate_1.gcode", gcode_content)

        zip_bytes = buf.getvalue()
        res = parse_3mf_file(zip_bytes, "model.3mf")

        self.assertTrue(res["valid"])
        self.assertEqual(res["printer_model"], "Bambu Lab A1 mini")
        self.assertEqual(res["filament_type"], "PETG")
        self.assertAlmostEqual(res["weight_g"], 42.5)
        self.assertEqual(res["time_mins"], 75)
        self.assertEqual(len(res["objects"]), 2)
        self.assertEqual(res["objects"][0]["id"], "1")
        self.assertEqual(res["objects"][0]["bbox"], [10.0, 10.0, 50.0, 50.0])

    def test_parse_3mf_file_gcode_m486_and_header_fallback(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            gcode_content = """; model printing time: 45m; total estimated time: 45m
            ; total filament weight [g] : 18.2
            M486 S1
            M486 S2
            """
            zf.writestr("Metadata/plate_1.gcode", gcode_content)

        zip_bytes = buf.getvalue()
        res = parse_3mf_file(zip_bytes, "part.3mf")

        self.assertTrue(res["valid"])
        self.assertAlmostEqual(res["weight_g"], 18.2)
        self.assertEqual(res["time_mins"], 45)
        self.assertEqual(len(res["objects"]), 2)


if __name__ == "__main__":
    unittest.main()
