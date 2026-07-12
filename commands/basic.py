import discord
from discord.ext import commands
from config import Settings

async def setup(bot: commands.Bot, settings: Settings) -> None:
    @bot.tree.command(name='hello', description='Check whether the bot is working.')
    async def hello(interaction: discord.Interaction) -> None:
        await interaction.response.send_message('Hello! The market bot is working.')

    @bot.tree.command(name='thresholds', description='Show the current market thresholds.')
    async def thresholds(interaction: discord.Interaction) -> None:
        e=discord.Embed(title='Market Recommendation Thresholds', description='BUY compares listing price with the 7-day average. SELL compares net proceeds after FM tax.')
        e.add_field(name='Strong Buy', value=f"{settings.strong_buy_threshold_percent:g}% or more below average", inline=False)
        e.add_field(name='Buy', value=f"{settings.buy_threshold_percent:g}% or more below average", inline=False)
        e.add_field(name='Sell', value=f"Net after tax is {settings.sell_threshold_percent:g}% or more above average", inline=False)
        e.add_field(name='Strong Sell', value=f"Net after tax is {settings.strong_sell_threshold_percent:g}% or more above average", inline=False)
        e.add_field(name='FM Tax', value=f"{settings.fm_tax_percent:g}%", inline=False)
        await interaction.response.send_message(embed=e)
