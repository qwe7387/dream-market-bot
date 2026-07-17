import unittest

from services.resolver import ItemResolver


class ResolverTests(unittest.TestCase):
    def test_deduplicate(self) -> None:
        self.assertEqual(
            ItemResolver._deduplicate([" Item ", "item", "Other"]),
            ["Item", "Other"],
        )

    def test_cleanup_candidates(self) -> None:
        candidates = ItemResolver._cleanup_candidates("f) Advanced LUK Crystal")
        self.assertIn("Advanced LUK Crystal", candidates)

    def test_not_found_detection(self) -> None:
        self.assertTrue(ItemResolver._is_not_found_error(RuntimeError("status 404")))
        self.assertFalse(ItemResolver._is_not_found_error(RuntimeError("status 500")))


if __name__ == "__main__":
    unittest.main()
