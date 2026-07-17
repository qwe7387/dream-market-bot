import unittest

from domain.models import MarketListing, MarketScan
from services.dreambot_filename import apply_filename_to_scan, parse_cheapest_metadata


class FilenameTests(unittest.TestCase):
    def test_parse_valid_filename(self) -> None:
        self.assertEqual(
            parse_cheapest_metadata("p1_mayb_24999999.png"),
            ("mayb", 24_999_999),
        )

    def test_apply_filename_keeps_trusted_quantity(self) -> None:
        scan = MarketScan(
            item_id=1,
            item_name="Advanced DEX Crystal",
            listings=(MarketListing("bad", 999, 1),),
        )
        result = apply_filename_to_scan(
            scan,
            "p1_mayb_24999999.png",
            trusted_quantity=16,
        )
        self.assertEqual(result.cheapest.seller, "mayb")
        self.assertEqual(result.cheapest.price, 24_999_999)
        self.assertEqual(result.cheapest.quantity, 16)


if __name__ == "__main__":
    unittest.main()
