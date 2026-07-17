import unittest

from domain.models import MarketListing, MarketScan


class MarketModelTests(unittest.TestCase):
    def test_cheapest_and_round_trip(self) -> None:
        scan = MarketScan(
            item_id=123,
            item_name="White Scroll",
            listings=(
                MarketListing("SellerA", 50_000_000, 1),
                MarketListing("SellerB", 40_000_000, 2),
            ),
            is_stackable=True,
        )
        self.assertEqual(scan.cheapest.seller, "SellerB")
        self.assertEqual(MarketScan.from_dict(scan.to_dict()), scan)
        self.assertEqual(scan.as_dict(), scan.to_dict())
        self.assertEqual(scan.cheapest.as_dict(), scan.cheapest.to_dict())

    def test_reliable_listing_replaces_matching_seller(self) -> None:
        scan = MarketScan(
            item_id=None,
            item_name="Item",
            listings=(MarketListing("Seller", 99, 3),),
        )
        updated = scan.with_reliable_listing(MarketListing("seller", 50, 4))
        self.assertEqual(len(updated.listings), 1)
        self.assertEqual(updated.cheapest.price, 50)
        self.assertEqual(updated.cheapest.quantity, 4)


if __name__ == "__main__":
    unittest.main()
