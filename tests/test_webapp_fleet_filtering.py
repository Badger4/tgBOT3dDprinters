import shutil
import subprocess
import unittest
from pathlib import Path


class TestWebappFleetFilteringUI(unittest.TestCase):
    def setUp(self):
        self.webapp_dir = Path(__file__).parent.parent / "webapp"
        self.html_path = self.webapp_dir / "index.html"
        self.js_path = self.webapp_dir / "static" / "js" / "app.js"

    def test_index_html_exists(self):
        self.assertTrue(self.html_path.exists(), "webapp/index.html should exist")

    def test_fleet_controls_elements_present(self):
        content = self.html_path.read_text(encoding="utf-8")

        # Check search input box
        self.assertIn('id="printer-search-input"', content)
        self.assertIn('search-input', content)

        # Check filter pills container and badges
        self.assertIn('class="filter-pills', content)
        self.assertIn('data-filter="all"', content)
        self.assertIn('data-filter="RUNNING"', content)
        self.assertIn('data-filter="PAUSE"', content)
        self.assertIn('data-filter="IDLE"', content)

        # Check count badges
        self.assertIn('id="count-filter-all"', content)
        self.assertIn('id="count-filter-running"', content)
        self.assertIn('id="count-filter-pause"', content)
        self.assertIn('id="count-filter-idle"', content)
        self.assertIn("Вільні ⚪", content)
        self.assertIn('id="btn-view-detailed"', content)
        self.assertIn('id="btn-view-compact"', content)
        self.assertIn('id="fleet-batch-modal"', content)
        self.assertIn('id="spool-search-input"', content)
        self.assertIn('id="spool-filter-pills"', content)

    def test_app_js_valid_syntax(self):
        self.assertTrue(self.js_path.exists(), "webapp/static/js/app.js should exist")
        node_bin = shutil.which("node")
        if node_bin:
            res = subprocess.run([node_bin, "--check", str(self.js_path)], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"JavaScript syntax error in app.js:\n{res.stderr}")


if __name__ == "__main__":
    unittest.main()
