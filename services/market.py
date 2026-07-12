from dataclasses import dataclass
from config import Settings

@dataclass(frozen=True)
class MarketAnalysis:
    recommendation: str
    emoji: str
    description: str
    current_listing_price: int
    net_after_tax: int
    tax_amount: int
    average_price: int
    buy_difference_percent: float
    sell_difference_percent: float

def apply_tax(price: int, tax_percent: float) -> tuple[int,int]:
    tax_amount=round(price*tax_percent/100)
    return tax_amount, price-tax_amount

def analyze_market(current_price: int, average_price: int, settings: Settings) -> MarketAnalysis:
    buy_difference=((current_price-average_price)/average_price)*100
    tax_amount, net_after_tax=apply_tax(current_price, settings.fm_tax_percent)
    sell_difference=((net_after_tax-average_price)/average_price)*100
    if buy_difference <= -settings.strong_buy_threshold_percent:
        rec,emoji,desc='STRONG BUY','🟢','The cheapest listing is far below the 7-day average.'
    elif buy_difference <= -settings.buy_threshold_percent:
        rec,emoji,desc='BUY','🟢','The cheapest listing is below your buy threshold.'
    elif sell_difference >= settings.strong_sell_threshold_percent:
        rec,emoji,desc='STRONG SELL','🔴','Even after FM tax, the expected proceeds are far above the 7-day average.'
    elif sell_difference >= settings.sell_threshold_percent:
        rec,emoji,desc='SELL','🟠','After FM tax, the expected proceeds are above your sell threshold.'
    else:
        rec,emoji,desc='HOLD','⚪','The current price is between your configured buy and sell thresholds.'
    return MarketAnalysis(rec,emoji,desc,current_price,net_after_tax,tax_amount,average_price,buy_difference,sell_difference)
