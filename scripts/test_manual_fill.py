import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import manual_fill  # noqa: E402


class ManualFillSaveTest(unittest.TestCase):
    def test_required_blank_values_are_rejected(self) -> None:
        req = {
            "values": {"hp": "112", "attack": " ", "defense": ""},
            "requireNonEmpty": True,
        }
        self.assertEqual(
            manual_fill.missing_required_values(req), ["attack", "defense"]
        )

    def test_edit_mode_allows_clearing_values(self) -> None:
        req = {"values": {"hp": ""}, "requireNonEmpty": False}
        self.assertEqual(manual_fill.missing_required_values(req), [])


if __name__ == "__main__":
    unittest.main()
