import unittest

from core.config import Settings
from services.market import analyze_market, apply_tax


def settings() -> Settings:
    return Settings(
        discord_token="x",
        game_api_key="x",
        game_api_base_url="https://example.invalid",
        dreambot_id=1,
        fm_tax_percent=2,
        buy_threshold_percent=10,
        strong_buy_threshold_percent=20,
        sell_threshold_percent=10,
        strong_sell_threshold_percent=20,
        embed_style="discord",
        enable_details_button=True,
        economy_cache_minutes=5,
        bot_version="test",
    )


class MarketTests(unittest.TestCase):
    def test_tax(self) -> None:
        self.assertEqual(apply_tax(100, 2), (2, 98))

    def test_strong_buy(self) -> None:
        result = analyze_market(70, 100, settings())
        self.assertEqual(result.recommendation, "STRONG BUY")

    def test_sell_uses_net_after_tax(self) -> None:
        result = analyze_market(125, 100, settings())
        self.assertEqual(result.recommendation, "STRONG SELL")
        self.assertEqual(result.net_after_tax, 123)


if __name__ == "__main__":
    unittest.main()
