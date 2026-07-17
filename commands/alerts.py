from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from services.alerts import PriceAlertService
from services.autocomplete import item_name_autocomplete


ALERT_TYPE_CHOICES = [
    app_commands.Choice(name="Buy alert", value="buy"),
    app_commands.Choice(name="Sell alert", value="sell"),
]


async def setup(
    bot: commands.Bot,
    alert_service: PriceAlertService,
) -> None:
    async def save_alert(
        interaction: discord.Interaction,
        *,
        item: str,
        target_price: int,
        alert_type: str,
    ) -> None:
        await alert_service.add_watch(
            interaction.user.id,
            item,
            int(target_price),
            alert_type,  # type: ignore[arg-type]
        )

        is_buy = alert_type == "buy"
        direction = "at or below" if is_buy else "at or above"
        symbol = "≤" if is_buy else "≥"
        title = "Buy Alert Saved" if is_buy else "Sell Alert Saved"

        embed = discord.Embed(
            title=title,
            description=(
                f"I will alert you when **{item}** is scanned {direction} "
                f"**{int(target_price):,} mesos**."
            ),
        )
        embed.add_field(
            name="Trigger",
            value=f"Current FM price {symbol} {int(target_price):,}",
            inline=False,
        )
        embed.set_footer(
            text="Alerts are checked whenever the bot processes a DreamBot /fm result."
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(
        name="watchbuy",
        description="Alert you when an FM item is scanned at or below your target.",
    )
    @app_commands.describe(
        item="Start typing an item name.",
        target_price="Alert when the cheapest listing is at or below this amount.",
    )
    @app_commands.autocomplete(item=item_name_autocomplete)
    async def watchbuy(
        interaction: discord.Interaction,
        item: str,
        target_price: app_commands.Range[int, 1, 20_000_000_000],
    ) -> None:
        await save_alert(
            interaction,
            item=item,
            target_price=int(target_price),
            alert_type="buy",
        )

    @bot.tree.command(
        name="watchsell",
        description="Alert you when an FM item is scanned at or above your target.",
    )
    @app_commands.describe(
        item="Start typing an item name.",
        target_price="Alert when the cheapest listing is at or above this amount.",
    )
    @app_commands.autocomplete(item=item_name_autocomplete)
    async def watchsell(
        interaction: discord.Interaction,
        item: str,
        target_price: app_commands.Range[int, 1, 20_000_000_000],
    ) -> None:
        await save_alert(
            interaction,
            item=item,
            target_price=int(target_price),
            alert_type="sell",
        )

    @bot.tree.command(
        name="watchlist",
        description="Show your active buy and sell price alerts.",
    )
    async def watchlist(interaction: discord.Interaction) -> None:
        watches = await alert_service.get_watches(interaction.user.id)

        if not watches:
            await interaction.response.send_message(
                "You do not have any price alerts yet. Use `/watchbuy` or `/watchsell` to add one.",
                ephemeral=True,
            )
            return

        buy_watches = [
            watch for watch in watches
            if str(watch.get("alert_type", "buy")) == "buy"
        ]
        sell_watches = [
            watch for watch in watches
            if str(watch.get("alert_type", "buy")) == "sell"
        ]

        embed = discord.Embed(
            title=f"{interaction.user.display_name}'s Price Alerts"
        )

        if buy_watches:
            embed.add_field(
                name="🟢 Buy Alerts",
                value="\n\n".join(
                    f"**{watch['item_name']}**\n≤ {int(watch['target_price']):,} mesos"
                    for watch in buy_watches
                ),
                inline=False,
            )

        if sell_watches:
            embed.add_field(
                name="🔴 Sell Alerts",
                value="\n\n".join(
                    f"**{watch['item_name']}**\n≥ {int(watch['target_price']):,} mesos"
                    for watch in sell_watches
                ),
                inline=False,
            )

        embed.set_footer(text=f"{len(watches)} active alert(s)")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(
        name="unwatch",
        description="Remove buy, sell, or all alerts for an item.",
    )
    @app_commands.describe(
        item="The exact item name in your watchlist.",
        alert_type="Choose a type, or omit it to remove all alerts for the item.",
    )
    @app_commands.autocomplete(item=item_name_autocomplete)
    @app_commands.choices(alert_type=ALERT_TYPE_CHOICES)
    async def unwatch(
        interaction: discord.Interaction,
        item: str,
        alert_type: app_commands.Choice[str] | None = None,
    ) -> None:
        selected_type = alert_type.value if alert_type is not None else None
        removed_count = await alert_service.remove_watch(
            interaction.user.id,
            item,
            selected_type,  # type: ignore[arg-type]
        )

        if removed_count == 0:
            type_text = f" {selected_type}" if selected_type else ""
            await interaction.response.send_message(
                f"You do not have a{type_text} alert for **{item}**.",
                ephemeral=True,
            )
            return

        removed_text = (
            f"your {selected_type} alert"
            if selected_type
            else f"{removed_count} alert(s)"
        )
        await interaction.response.send_message(
            f"Removed {removed_text} for **{item}**.",
            ephemeral=True,
        )
