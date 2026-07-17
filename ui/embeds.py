from __future__ import annotations

from typing import Any

import discord

from config import Settings
from services.market import MarketAnalysis


def _color(recommendation: str) -> discord.Color:
    if recommendation in {"STRONG BUY", "BUY"}:
        return discord.Color.green()

    if recommendation == "SELL":
        return discord.Color.orange()

    if recommendation == "STRONG SELL":
        return discord.Color.red()

    return discord.Color.light_grey()


def create_comparison_embed(
    fm_result: dict[str, Any],
    economy_record: dict[str, Any],
    analysis: MarketAnalysis,
    settings: Settings,
    owners: list[dict[str, Any]] | None = None,
) -> discord.Embed:
    """Create the compact market response shown by default."""
    cheapest = fm_result["cheapest"]

    embed = discord.Embed(
        title=(
            f"{analysis.emoji} {analysis.recommendation}: "
            f"{fm_result['item_name']}"
        ),
        description=analysis.description,
        color=_color(analysis.recommendation),
    )

    embed.add_field(
        name="Current cheapest listing",
        value=f"{analysis.current_listing_price:,} mesos",
        inline=False,
    )
    embed.add_field(
        name="Net after tax per item",
        value=f"{analysis.net_after_tax:,} mesos",
        inline=True,
    )
    embed.add_field(
        name="7-day economy average",
        value=f"{analysis.average_price:,} mesos",
        inline=True,
    )
    embed.add_field(
        name="Net after tax vs average",
        value=f"{analysis.sell_difference_percent:+.2f}%",
        inline=True,
    )
    embed.add_field(
        name="Cheapest shop quantity",
        value=f"{cheapest['quantity']:,}",
        inline=True,
    )
    embed.add_field(
        name="Cheapest shop seller",
        value=str(cheapest["seller"]),
        inline=True,
    )

    items_sold = economy_record.get("items_sold")

    if isinstance(items_sold, int):
        embed.add_field(
            name="Items sold in 7 days",
            value=f"{items_sold:,}",
            inline=True,
        )

    item_id = fm_result.get("item_id")

    if item_id:
        embed.set_footer(text=f"Item ID: {item_id}")

    return embed


def create_detailed_comparison_embed(
    fm_result: dict[str, Any],
    economy_record: dict[str, Any],
    analysis: MarketAnalysis,
    settings: Settings,
    owners: list[dict[str, Any]] | None = None,
) -> discord.Embed:
    """Create the full details displayed by the button."""
    cheapest = fm_result["cheapest"]

    embed = discord.Embed(
        title=f"Market details: {fm_result['item_name']}",
        color=_color(analysis.recommendation),
    )

    embed.add_field(
        name="Recommendation",
        value=f"{analysis.emoji} {analysis.recommendation}",
        inline=False,
    )
    embed.add_field(
        name="Current cheapest listing",
        value=f"{analysis.current_listing_price:,} mesos",
        inline=True,
    )
    embed.add_field(
        name=f"FM tax ({settings.fm_tax_percent:g}%)",
        value=f"-{analysis.tax_amount:,} mesos",
        inline=True,
    )
    embed.add_field(
        name="Net after tax per item",
        value=f"{analysis.net_after_tax:,} mesos",
        inline=True,
    )
    embed.add_field(
        name="7-day economy average",
        value=f"{analysis.average_price:,} mesos",
        inline=True,
    )
    embed.add_field(
        name="Listing vs average",
        value=f"{analysis.buy_difference_percent:+.2f}%",
        inline=True,
    )
    embed.add_field(
        name="Net after tax vs average",
        value=f"{analysis.sell_difference_percent:+.2f}%",
        inline=True,
    )
    embed.add_field(
        name="Cheapest shop quantity",
        value=f"{cheapest['quantity']:,}",
        inline=True,
    )
    embed.add_field(
        name="Cheapest shop seller",
        value=str(cheapest["seller"]),
        inline=True,
    )

    items_sold = economy_record.get("items_sold")

    if isinstance(items_sold, int):
        embed.add_field(
            name="Items sold in 7 days",
            value=f"{items_sold:,}",
            inline=True,
        )

    sales = economy_record.get("sales")

    if isinstance(sales, int):
        embed.add_field(
            name="Sales in 7 days",
            value=f"{sales:,}",
            inline=True,
        )

    _add_portfolio_details(embed, owners)

    item_id = fm_result.get("item_id")

    if item_id:
        embed.set_footer(
            text=(
                f"Item ID: {item_id} | Estimated portfolio proceeds "
                "assume every owned item sells at the current cheapest "
                f"price and pays {settings.fm_tax_percent:g}% FM tax."
            )
        )

    return embed


def _add_portfolio_details(
    embed: discord.Embed,
    owners: list[dict[str, Any]] | None,
) -> None:
    if not owners:
        embed.add_field(
            name="Portfolio Owners",
            value="Neither portfolio currently contains this item.",
            inline=False,
        )
        return

    owner_lines: list[str] = []
    total_owned = 0
    total_proceeds = 0

    for owner in owners:
        quantity = int(owner["quantity"])
        proceeds = int(owner["estimated_net_proceeds"])
        total_owned += quantity
        total_proceeds += proceeds
        owner_lines.append(
            f"**{owner['display_name']}** - {quantity:,} owned - "
            f"{proceeds:,} mesos estimated net"
        )

    owner_lines.append(
        f"\n**Combined:** {total_owned:,} owned - "
        f"{total_proceeds:,} mesos estimated net"
    )

    embed.add_field(
        name="Portfolio Owners",
        value="\n".join(owner_lines),
        inline=False,
    )
