import discord
from discord import app_commands
from discord.ext import commands

from services.autocomplete import (
    item_name_autocomplete,
)
from services.database import PortfolioDatabase


class PortfolioCommands(
    app_commands.Group,
):
    def __init__(
        self,
        database: PortfolioDatabase,
    ) -> None:
        super().__init__(
            name="portfolio",
            description="Manage your item portfolio.",
        )

        self.database = database

    @app_commands.command(
        name="add",
        description="Add an item to your portfolio.",
    )
    @app_commands.describe(
        item="Start typing an item name.",
        quantity="Quantity to add.",
    )
    @app_commands.autocomplete(
        item=item_name_autocomplete
    )
    async def add(
        self,
        interaction: discord.Interaction,
        item: str,
        quantity: app_commands.Range[int, 1, 999999],
    ) -> None:
        new_quantity = await self.database.add_item(
            discord_id=interaction.user.id,
            item_name=item,
            quantity=quantity,
        )

        await interaction.response.send_message(
            f"Added **{item} x{quantity:,}** "
            f"to **{interaction.user.display_name}'s** "
            f"portfolio.\n"
            f"New quantity: **{new_quantity:,}**"
        )

    @app_commands.command(
        name="remove",
        description="Remove an item from your portfolio.",
    )
    @app_commands.describe(
        item="Start typing an item name.",
        quantity="Quantity to remove.",
    )
    @app_commands.autocomplete(
        item=item_name_autocomplete
    )
    async def remove(
        self,
        interaction: discord.Interaction,
        item: str,
        quantity: app_commands.Range[int, 1, 999999],
    ) -> None:
        try:
            remaining = await self.database.remove_item(
                discord_id=interaction.user.id,
                item_name=item,
                quantity=quantity,
            )
        except ValueError as error:
            await interaction.response.send_message(
                str(error),
                ephemeral=True,
            )
            return

        if remaining == 0:
            message = (
                f"Removed **{item}** from your portfolio."
            )
        else:
            message = (
                f"Removed **{quantity:,} {item}**.\n"
                f"Remaining quantity: **{remaining:,}**"
            )

        await interaction.response.send_message(
            message
        )

    @app_commands.command(
        name="list",
        description="Show your portfolio.",
    )
    async def list_items(
        self,
        interaction: discord.Interaction,
    ) -> None:
        inventory = await self.database.get_inventory(
            interaction.user.id
        )

        if not inventory:
            await interaction.response.send_message(
                "Your portfolio is empty.",
                ephemeral=True,
            )
            return

        lines = [
            (
                f"**{index}. {entry['item_name']}** "
                f"x{entry['quantity']:,}"
            )
            for index, entry in enumerate(
                inventory,
                start=1,
            )
        ]

        embed = discord.Embed(
            title=(
                f"{interaction.user.display_name}'s "
                "Portfolio"
            ),
            description="\n".join(lines),
        )

        total_quantity = sum(
            entry["quantity"]
            for entry in inventory
        )

        embed.set_footer(
            text=(
                f"{len(inventory)} item type(s) | "
                f"{total_quantity:,} total item(s)"
            )
        )

        await interaction.response.send_message(
            embed=embed
        )

    @app_commands.command(
        name="clear",
        description="Remove everything from your portfolio.",
    )
    async def clear(
        self,
        interaction: discord.Interaction,
    ) -> None:
        removed_rows = (
            await self.database.clear_inventory(
                interaction.user.id
            )
        )

        if removed_rows == 0:
            await interaction.response.send_message(
                "Your portfolio was already empty.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Your portfolio has been cleared."
        )

    @app_commands.command(
        name="owners",
        description="Show who owns an item.",
    )
    @app_commands.describe(
        item="Start typing an item name."
    )
    @app_commands.autocomplete(
        item=item_name_autocomplete
    )
    async def owners(
        self,
        interaction: discord.Interaction,
        item: str,
    ) -> None:
        owners = await self.database.get_item_owners(
            item
        )

        if not owners:
            await interaction.response.send_message(
                f"Nobody owns **{item}**."
            )
            return

        lines: list[str] = []
        total_quantity = 0

        guild = interaction.guild

        for owner in owners:
            discord_id = owner["discord_id"]
            quantity = owner["quantity"]
            total_quantity += quantity

            display_name = f"User {discord_id}"

            if guild is not None:
                member = guild.get_member(discord_id)

                if member is None:
                    try:
                        member = await guild.fetch_member(
                            discord_id
                        )
                    except discord.HTTPException:
                        member = None

                if member is not None:
                    display_name = member.display_name

            lines.append(
                f"**{display_name}** — {quantity:,}"
            )

        embed = discord.Embed(
            title=f"Owners: {item}",
            description="\n".join(lines),
        )

        embed.add_field(
            name="Total owned",
            value=f"{total_quantity:,}",
            inline=False,
        )

        await interaction.response.send_message(
            embed=embed
        )


async def setup(
    bot: commands.Bot,
    database: PortfolioDatabase,
) -> None:
    bot.tree.add_command(
        PortfolioCommands(database)
    )