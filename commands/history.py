from datetime import datetime
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from services.autocomplete import (
    item_name_autocomplete,
)
from services.chart import create_price_timeline
from services.history import PriceHistoryService


def format_timestamp(
    timestamp: str,
) -> str:
    try:
        parsed = datetime.fromisoformat(
            timestamp.replace("Z", "+00:00")
        )

        return discord.utils.format_dt(
            parsed,
            style="R",
        )

    except (TypeError, ValueError):
        return timestamp


def calculate_trend(
    records: list[dict[str, Any]],
) -> tuple[str, float | None]:
    if len(records) < 2:
        return "Not enough data", None

    first_price = records[0].get(
        "listing_price"
    )
    latest_price = records[-1].get(
        "listing_price"
    )

    if not isinstance(first_price, (int, float)):
        return "Unknown", None

    if not isinstance(latest_price, (int, float)):
        return "Unknown", None

    if first_price <= 0:
        return "Unknown", None

    change_percent = (
        (latest_price - first_price)
        / first_price
    ) * 100

    if change_percent >= 5:
        return "📈 Rising", change_percent

    if change_percent <= -5:
        return "📉 Falling", change_percent

    return "➡️ Stable", change_percent


class HistoryCommands(app_commands.Group):
    def __init__(
        self,
        history_service: PriceHistoryService,
    ) -> None:
        super().__init__(
            name="history",
            description="View recorded FM price history.",
        )

        self.history_service = history_service

    @app_commands.command(
        name="show",
        description="Show recent observed FM prices.",
    )
    @app_commands.describe(
        item="Start typing an item name.",
        entries="Number of records to display.",
    )
    @app_commands.autocomplete(
        item=item_name_autocomplete
    )
    async def show(
        self,
        interaction: discord.Interaction,
        item: str,
        entries: app_commands.Range[int, 2, 15] = 10,
    ) -> None:
        history = await self.history_service.get_history(
            item_name=item,
            limit=entries,
        )

        if history is None or not history["records"]:
            await interaction.response.send_message(
                f"No FM history has been recorded for "
                f"**{item}** yet.\n\n"
                "Use DreamBot's `/fm` command for this item "
                "to begin recording prices.",
                ephemeral=True,
            )
            return

        records = history["records"]
        trend_name, change_percent = calculate_trend(
            records
        )

        latest = records[-1]

        embed = discord.Embed(
            title=(
                f"Price History: "
                f"{history['item_name']}"
            ),
            description=(
                "This contains FM prices observed when "
                "DreamBot's `/fm` command was used."
            ),
            color=discord.Color.blue(),
        )

        embed.add_field(
            name="Latest listing",
            value=(
                f"{latest['listing_price']:,} mesos"
            ),
            inline=True,
        )

        embed.add_field(
            name="Latest net after tax",
            value=(
                f"{latest['net_after_tax']:,} mesos"
            ),
            inline=True,
        )

        embed.add_field(
            name="Latest recommendation",
            value=latest["recommendation"],
            inline=True,
        )

        if change_percent is None:
            trend_value = trend_name
        else:
            trend_value = (
                f"{trend_name}\n"
                f"{change_percent:+.2f}%"
            )

        embed.add_field(
            name="Observed trend",
            value=trend_value,
            inline=False,
        )

        history_lines: list[str] = []

        for record in reversed(records):
            checked_at = format_timestamp(
                record["checked_at"]
            )

            history_lines.append(
                f"**{record['listing_price']:,}** mesos "
                f"• {checked_at}\n"
                f"Net: {record['net_after_tax']:,} "
                f"• Average: {record['average_price']:,} "
                f"• {record['recommendation']}"
            )

        history_text = "\n\n".join(
            history_lines
        )

        # Discord embed field values are limited in size.
        if len(history_text) > 1024:
            history_text = (
                history_text[:1020]
                + "..."
            )

        embed.add_field(
            name=f"Recent checks ({len(records)})",
            value=history_text,
            inline=False,
        )

        if history.get("item_id"):
            embed.set_footer(
                text=(
                    f"Item ID: {history['item_id']} | "
                    "Trend compares the oldest and newest "
                    "records displayed."
                )
            )

        try:
            graph_buffer = create_price_timeline(
                item_name=history["item_name"],
                records=records,
            )
            graph_file = discord.File(
                graph_buffer,
                filename="price_timeline.png",
            )
            embed.set_image(
                url="attachment://price_timeline.png"
            )

            await interaction.response.send_message(
                embed=embed,
                file=graph_file,
            )
        except ValueError:
            await interaction.response.send_message(
                embed=embed
            )

    @app_commands.command(
        name="clear",
        description="Delete an item's recorded history.",
    )
    @app_commands.describe(
        item="Start typing an item name."
    )
    @app_commands.autocomplete(
        item=item_name_autocomplete
    )
    async def clear(
        self,
        interaction: discord.Interaction,
        item: str,
    ) -> None:
        removed = (
            await self.history_service.clear_history(
                item
            )
        )

        if not removed:
            await interaction.response.send_message(
                f"No history exists for **{item}**.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Cleared the recorded history for "
            f"**{item}**."
        )


async def setup(
    bot: commands.Bot,
    history_service: PriceHistoryService,
) -> None:
    bot.tree.add_command(
        HistoryCommands(history_service)
    )