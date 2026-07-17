from typing import Any

import discord

from core.config import Settings
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


def _format_percent(
    value: float,
) -> str:
    return f"{value:+.1f}%"


def _items_sold_text(
    economy_record: dict[str, Any],
) -> str | None:
    items_sold = economy_record.get(
        "items_sold"
    )

    if isinstance(items_sold, int):
        return f"{items_sold:,}"

    return None


def _base_embed(
    fm_result: dict[str, Any],
    analysis: MarketAnalysis,
) -> discord.Embed:
    return discord.Embed(
        title=(
            f"{analysis.emoji} "
            f"{analysis.recommendation}: "
            f"{fm_result['item_name']}"
        ).strip(),
        description=analysis.description,
        color=_color(
            analysis.recommendation
        ),
    )


def _create_discord_embed(
    fm_result: dict[str, Any],
    economy_record: dict[str, Any],
    analysis: MarketAnalysis,
) -> discord.Embed:
    """
    One-glance Discord layout.

    The DreamBot image already shows the current listing,
    seller, and quantity, so this preset focuses only on
    information the image does not provide.
    """

    embed = _base_embed(
        fm_result,
        analysis,
    )

    difference = (
        analysis.buy_difference_percent
        if analysis.recommendation
        in {"STRONG BUY", "BUY", "HOLD"}
        else analysis.sell_difference_percent
    )

    lines = [
        (
            f"💰 **7-day avg:** "
            f"{analysis.average_price:,} mesos"
        ),
        (
            f"🏷️ **Net after tax:** "
            f"{analysis.net_after_tax:,} mesos"
        ),
        (
            f"📊 **Difference:** "
            f"{_format_percent(difference)}"
        ),
    ]

    items_sold = _items_sold_text(
        economy_record
    )

    if items_sold is not None:
        lines.append(
            f"📈 **Sold in 7 days:** {items_sold}"
        )

    embed.description = "\n".join(lines)

    return embed


def _create_minimal_embed(
    fm_result: dict[str, Any],
    economy_record: dict[str, Any],
    analysis: MarketAnalysis,
) -> discord.Embed:
    embed = _base_embed(
        fm_result,
        analysis,
    )

    difference = (
        analysis.buy_difference_percent
        if analysis.recommendation
        in {"STRONG BUY", "BUY", "HOLD"}
        else analysis.sell_difference_percent
    )

    lines = [
        (
            f"**{abs(difference):.1f}% "
            f"{'below' if difference < 0 else 'above'} "
            "the 7-day average**"
        )
    ]

    items_sold = _items_sold_text(
        economy_record
    )

    if items_sold is not None:
        lines.append(
            f"{items_sold} sold in 7 days"
        )

    embed.description = "\n".join(lines)

    return embed


def _create_compact_embed(
    fm_result: dict[str, Any],
    economy_record: dict[str, Any],
    analysis: MarketAnalysis,
) -> discord.Embed:
    embed = _base_embed(
        fm_result,
        analysis,
    )

    embed.add_field(
        name="Net",
        value=(
            f"{analysis.net_after_tax:,} mesos"
        ),
        inline=True,
    )

    embed.add_field(
        name="7-day average",
        value=(
            f"{analysis.average_price:,} mesos"
        ),
        inline=True,
    )

    embed.add_field(
        name="Difference",
        value=_format_percent(
            analysis.buy_difference_percent
        ),
        inline=True,
    )

    items_sold = _items_sold_text(
        economy_record
    )

    if items_sold is not None:
        embed.add_field(
            name="Sold in 7 days",
            value=items_sold,
            inline=True,
        )

    return embed


def _create_normal_embed(
    fm_result: dict[str, Any],
    economy_record: dict[str, Any],
    analysis: MarketAnalysis,
) -> discord.Embed:
    cheapest = fm_result["cheapest"]
    embed = _base_embed(
        fm_result,
        analysis,
    )

    embed.add_field(
        name="Net after tax per item",
        value=(
            f"{analysis.net_after_tax:,} mesos"
        ),
        inline=True,
    )

    embed.add_field(
        name="7-day economy average",
        value=(
            f"{analysis.average_price:,} mesos"
        ),
        inline=True,
    )

    embed.add_field(
        name="Net vs average",
        value=_format_percent(
            analysis.sell_difference_percent
        ),
        inline=True,
    )

    embed.add_field(
        name="Quantity",
        value=f"{cheapest['quantity']:,}",
        inline=True,
    )

    embed.add_field(
        name="Seller",
        value=str(cheapest["seller"]),
        inline=True,
    )

    items_sold = _items_sold_text(
        economy_record
    )

    if items_sold is not None:
        embed.add_field(
            name="Items sold in 7 days",
            value=items_sold,
            inline=True,
        )

    return embed


def create_detailed_comparison_embed(
    fm_result: dict[str, Any],
    economy_record: dict[str, Any],
    analysis: MarketAnalysis,
    settings: Settings,
    owners: list[dict[str, Any]] | None = None,
) -> discord.Embed:
    cheapest = fm_result["cheapest"]

    embed = _base_embed(
        fm_result,
        analysis,
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
        value=(
            f"{analysis.net_after_tax:,} mesos"
        ),
        inline=True,
    )

    embed.add_field(
        name="7-day economy average",
        value=(
            f"{analysis.average_price:,} mesos"
        ),
        inline=False,
    )

    embed.add_field(
        name="Listing vs average",
        value=_format_percent(
            analysis.buy_difference_percent
        ),
        inline=True,
    )

    embed.add_field(
        name="Net after tax vs average",
        value=_format_percent(
            analysis.sell_difference_percent
        ),
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
            display_name = owner[
                "display_name"
            ]
            quantity = owner["quantity"]
            proceeds = owner[
                "estimated_net_proceeds"
            ]

            total_owned += quantity
            total_estimated_proceeds += proceeds

            owner_lines.append(
                f"**{display_name}**\n"
                f"Owned: {quantity:,}\n"
                "Estimated net proceeds: "
                f"{proceeds:,} mesos"
            )

        owner_lines.append(
            "\n"
            "**Combined total owned:** "
            f"{total_owned:,}\n"
            "**Combined estimated net proceeds:** "
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
                "item sells at the current cheapest "
                "listing price and pays "
                f"{settings.fm_tax_percent:g}% FM tax."
            )
        )

    return embed


def create_comparison_embed(
    fm_result: dict[str, Any],
    economy_record: dict[str, Any],
    analysis: MarketAnalysis,
    settings: Settings,
    owners: list[dict[str, Any]] | None = None,
) -> discord.Embed:
    style = settings.embed_style

    if style == "minimal":
        return _create_minimal_embed(
            fm_result,
            economy_record,
            analysis,
        )

    if style == "compact":
        return _create_compact_embed(
            fm_result,
            economy_record,
            analysis,
        )

    if style == "normal":
        return _create_normal_embed(
            fm_result,
            economy_record,
            analysis,
        )

    if style == "full":
        return create_detailed_comparison_embed(
            fm_result=fm_result,
            economy_record=economy_record,
            analysis=analysis,
            settings=settings,
            owners=owners,
        )

    return _create_discord_embed(
        fm_result,
        economy_record,
        analysis,
    )
