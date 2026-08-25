import unittest
from pathlib import Path


class TestWebappFleetFilteringUI(unittest.TestCase):
    def setUp(self):
        self.html_path = Path(__file__).parent.parent / "webapp" / "index.html"

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


if __name__ == "__main__":
    unittest.main()
