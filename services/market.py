from core.config import Settings
from domain.models import MarketAnalysis


def apply_tax(price: int, tax_percent: float) -> tuple[int, int]:
    tax_amount = round(price * tax_percent / 100)
    return tax_amount, price - tax_amount


def analyze_market(
    current_price: int,
    average_price: int,
    settings: Settings,
) -> MarketAnalysis:
    buy_difference = ((current_price - average_price) / average_price) * 100
    tax_amount, net_after_tax = apply_tax(current_price, settings.fm_tax_percent)
    sell_difference = ((net_after_tax - average_price) / average_price) * 100

    if buy_difference <= -settings.strong_buy_threshold_percent:
        recommendation, emoji, description = (
            "STRONG BUY",
            "🟢",
            "The cheapest listing is far below the 7-day average.",
        )
    elif buy_difference <= -settings.buy_threshold_percent:
        recommendation, emoji, description = (
            "BUY",
            "🟢",
            "The cheapest listing is below your buy threshold.",
        )
    elif sell_difference >= settings.strong_sell_threshold_percent:
        recommendation, emoji, description = (
            "STRONG SELL",
            "🔴",
            "Even after FM tax, the expected proceeds are far above the 7-day average.",
        )
    elif sell_difference >= settings.sell_threshold_percent:
        recommendation, emoji, description = (
            "SELL",
            "🟠",
            "After FM tax, the expected proceeds are above your sell threshold.",
        )
    else:
        recommendation, emoji, description = (
            "HOLD",
            "⚪",
            "The current price is between your configured buy and sell thresholds.",
        )

    return MarketAnalysis(
        recommendation=recommendation,
        emoji=emoji,
        description=description,
        current_listing_price=current_price,
        net_after_tax=net_after_tax,
        tax_amount=tax_amount,
        average_price=average_price,
        buy_difference_percent=buy_difference,
        sell_difference_percent=sell_difference,
    )
