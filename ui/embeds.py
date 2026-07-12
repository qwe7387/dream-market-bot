import discord
from config import Settings
from services.market import MarketAnalysis

def _color(rec: str) -> discord.Color:
    if rec in {'STRONG BUY','BUY'}: return discord.Color.green()
    if rec == 'SELL': return discord.Color.orange()
    if rec == 'STRONG SELL': return discord.Color.red()
    return discord.Color.light_grey()

def create_comparison_embed(fm_result: dict, economy_record: dict, analysis: MarketAnalysis, settings: Settings) -> discord.Embed:
    cheapest=fm_result['cheapest']
    embed=discord.Embed(title=f"{analysis.emoji} {analysis.recommendation}: {fm_result['item_name']}", description=analysis.description, color=_color(analysis.recommendation))
    embed.add_field(name='Current cheapest listing', value=f"{analysis.current_listing_price:,} mesos", inline=False)
    embed.add_field(name=f"FM tax ({settings.fm_tax_percent:g}%)", value=f"-{analysis.tax_amount:,} mesos", inline=True)
    embed.add_field(name='Net after tax', value=f"{analysis.net_after_tax:,} mesos", inline=True)
    embed.add_field(name='7-day economy average', value=f"{analysis.average_price:,} mesos", inline=False)
    listing_diff=f"{analysis.buy_difference_percent:+.2f}%"
    net_diff=f"{analysis.sell_difference_percent:+.2f}%"
    embed.add_field(name='Listing vs average', value=listing_diff, inline=False)
    embed.add_field(name='Net after tax vs average', value=net_diff, inline=False)
    embed.add_field(name='Quantity', value=f"{cheapest['quantity']:,}", inline=True)
    embed.add_field(name='Seller', value=cheapest['seller'], inline=True)
    if isinstance(economy_record.get('items_sold'),int): embed.add_field(name='Items sold in 7 days', value=f"{economy_record['items_sold']:,}", inline=True)
    if isinstance(economy_record.get('sales'),int): embed.add_field(name='Sales in 7 days', value=f"{economy_record['sales']:,}", inline=True)
    if fm_result.get('item_id'): embed.set_footer(text=f"Item ID: {fm_result['item_id']} | Sell signals use net proceeds after {settings.fm_tax_percent:g}% FM tax.")
    return embed
