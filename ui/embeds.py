from typing import Any

import discord

from config import Settings
from services.market import MarketAnalysis


def _color(
    recommendation: str,
) -> discord.Color:
    if recommendation in {
        "STRONG BUY",
        "BUY",
    }:
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
    cheapest = fm_result["cheapest"]

    embed = discord.Embed(
        title=(
            f"{analysis.emoji} "
            f"{analysis.recommendation}: "
            f"{fm_result['item_name']}"
        ),
        description=analysis.description,
        color=_color(analysis.recommendation),
    )

    embed.add_field(
        name="Current cheapest listing",
        value=(
            f"{analysis.current_listing_price:,} mesos"
        ),
        inline=False,
    )

    embed.add_field(
        name=(
            f"FM tax "
            f"({settings.fm_tax_percent:g}%)"
        ),
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
        inline=False,
    )

    listing_difference = (
        f"{analysis.buy_difference_percent:+.2f}%"
    )

    net_difference = (
        f"{analysis.sell_difference_percent:+.2f}%"
    )

    embed.add_field(
        name="Listing vs average",
        value=listing_difference,
        inline=True,
    )

    embed.add_field(
        name="Net after tax vs average",
        value=net_difference,
        inline=True,
    )

    embed.add_field(
        name="Cheapest shop quantity",
        value=f"{cheapest['quantity']:,}",
        inline=True,
    )

    embed.add_field(
        name="Cheapest shop seller",
        value=cheapest["seller"],
        inline=True,
    )

    items_sold = economy_record.get(
        "items_sold"
    )

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

    if owners:
        owner_lines: list[str] = []
        total_owned = 0
        total_estimated_proceeds = 0

        for owner in owners:
            display_name = owner["display_name"]
            quantity = owner["quantity"]
            proceeds = owner[
                "estimated_net_proceeds"
            ]

            total_owned += quantity
            total_estimated_proceeds += proceeds

            owner_lines.append(
                f"**{display_name}**\n"
                f"Owned: {quantity:,}\n"
                f"Estimated net proceeds: "
                f"{proceeds:,} mesos"
            )

        owner_lines.append(
            "\n"
            f"**Combined total owned:** "
            f"{total_owned:,}\n"
            f"**Combined estimated net proceeds:** "
            f"{total_estimated_proceeds:,} mesos"
        )

        embed.add_field(
            name="Portfolio Owners",
            value="\n\n".join(owner_lines),
            inline=False,
        )

    else:
        embed.add_field(
            name="Portfolio Owners",
            value=(
                "Neither portfolio currently contains "
                "this item."
            ),
            inline=False,
        )

    item_id = fm_result.get("item_id")

    if item_id:
        embed.set_footer(
            text=(
                f"Item ID: {item_id} | "
                "Estimated proceeds assume every owned "
                "item sells at the current cheapest listing "
                f"price and pays {settings.fm_tax_percent:g}% "
                "FM tax."
            )
        )

    return embed