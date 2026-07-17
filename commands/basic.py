from __future__ import annotations

import platform

import discord
from discord.ext import commands

from config import Settings
from services.api import DreamMSClient


async def setup(
    bot: commands.Bot,
    settings: Settings,
    api_client: DreamMSClient,
) -> None:
    @bot.tree.command(
        name="hello",
        description="Show bot status, version, and available features.",
    )
    async def hello(interaction: discord.Interaction) -> None:
        cache_size = await api_client.cache.size()
        embed = discord.Embed(
            title="Dream Market Bot",
            description=(
                "DreamMS FM analysis powered by DreamBot image parsing "
                "and the 7-day Economy API."
            ),
        )
        embed.add_field(
            name="Status",
            value="Online and ready",
            inline=True,
        )
        embed.add_field(
            name="Version",
            value=f"v{settings.bot_version}",
            inline=True,
        )
        embed.add_field(
            name="Python",
            value=platform.python_version(),
            inline=True,
        )
        embed.add_field(
            name="OCR",
            value="OCR v2 enabled",
            inline=True,
        )
        embed.add_field(
            name="Economy Cache",
            value=(
                f"{settings.economy_cache_minutes:g}-minute TTL\n"
                f"{cache_size} cached item(s)"
            ),
            inline=True,
        )
        embed.add_field(
            name="FM Tax",
            value=f"{settings.fm_tax_percent:g}%",
            inline=True,
        )
        embed.add_field(
            name="Features",
            value=(
                "• DreamBot `/fm` OCR and market analysis\n"
                "• Economy API caching\n"
                "• Buy alerts: `/watchbuy`\n"
                "• Sell alerts: `/watchsell`\n"
                "• Alert management: `/watchlist`, `/unwatch`\n"
                "• Portfolio and observed price history"
            ),
            inline=False,
        )
        embed.set_footer(
            text="Use /thresholds to view recommendation settings."
        )
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(
        name="thresholds",
        description="Show the current market thresholds.",
    )
    async def thresholds(interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Market Recommendation Thresholds",
            description=(
                "BUY compares listing price with the 7-day average. "
                "SELL compares net proceeds after FM tax."
            ),
        )
        embed.add_field(
            name="Strong Buy",
            value=f"{settings.strong_buy_threshold_percent:g}% or more below average",
            inline=False,
        )
        embed.add_field(
            name="Buy",
            value=f"{settings.buy_threshold_percent:g}% or more below average",
            inline=False,
        )
        embed.add_field(
            name="Sell",
            value=f"Net after tax is {settings.sell_threshold_percent:g}% or more above average",
            inline=False,
        )
        embed.add_field(
            name="Strong Sell",
            value=f"Net after tax is {settings.strong_sell_threshold_percent:g}% or more above average",
            inline=False,
        )
        embed.add_field(
            name="FM Tax",
            value=f"{settings.fm_tax_percent:g}%",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)
