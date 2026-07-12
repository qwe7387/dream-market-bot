import asyncio
import traceback
from typing import Any

import discord
from discord.ext import commands
from services.items import learn_item
from config import Settings
from services.api import DreamMSClient
from services.database import PortfolioDatabase
from services.market import analyze_market
from services.parser import parse_fm_embed
from ui.embeds import create_comparison_embed
from services.history import PriceHistoryService

class DreamBotListener:
    def __init__(
        self,
        bot: commands.Bot,
        settings: Settings,
        api_client: DreamMSClient,
        database: PortfolioDatabase,
        history_service: PriceHistoryService,
    ) -> None:
        self.bot = bot
        self.settings = settings
        self.api_client = api_client
        self.database = database
        self.history_service = history_service
        self.processed_message_ids: set[int] = set()

    async def get_owner_details(
        self,
        guild: discord.Guild | None,
        item_name: str,
        net_price_per_item: int,
    ) -> list[dict[str, Any]]:
        """
        Find everyone who owns the item and resolve their
        current Discord server display names.
        """

        stored_owners = await self.database.get_item_owners(
            item_name
        )

        owner_details: list[dict[str, Any]] = []

        for owner in stored_owners:
            discord_id = owner["discord_id"]
            quantity = owner["quantity"]

            display_name = f"User {discord_id}"

            if guild is not None:
                member = guild.get_member(discord_id)

                if member is None:
                    try:
                        member = await guild.fetch_member(
                            discord_id
                        )
                    except (
                        discord.NotFound,
                        discord.Forbidden,
                        discord.HTTPException,
                    ):
                        member = None

                if member is not None:
                    display_name = member.display_name

            owner_details.append(
                {
                    "discord_id": discord_id,
                    "display_name": display_name,
                    "quantity": quantity,
                    "estimated_net_proceeds": (
                        quantity * net_price_per_item
                    ),
                }
            )

        return owner_details

    async def process_message(
        self,
        message: discord.Message,
    ) -> None:
        if message.id in self.processed_message_ids:
            return

        if message.author.id != self.settings.dreambot_id:
            return

        if not message.embeds:
            return

        fm = parse_fm_embed(message.embeds[0])
        learn_item(
        fm["item_id"],
        fm["item_name"],
        )

        if fm is None:
            print(
                "DreamBot message was received, but FM listings "
                "could not be parsed."
            )
            return

        self.processed_message_ids.add(message.id)

        if len(self.processed_message_ids) > 500:
            self.processed_message_ids.clear()
            self.processed_message_ids.add(message.id)

        cheapest = fm["cheapest"]

        print("\nFM result parsed successfully")
        print(f"Item: {fm['item_name']}")
        print(f"Item ID: {fm['item_id']}")
        print(f"Lowest price: {cheapest['price']:,}")
        print(f"Quantity: {cheapest['quantity']}")
        print(f"Seller: {cheapest['seller']}")

        try:
            economy = await self.api_client.get_economy_average(
                fm["item_name"],
                7,
            )

            analysis = analyze_market(
                cheapest["price"],
                economy["avg_price"],
                self.settings,
            )
            await self.history_service.add_record(
            item_id=fm["item_id"],
            item_name=fm["item_name"],
            listing_price=cheapest["price"],
            net_after_tax=analysis.net_after_tax,
            average_price=economy["avg_price"],
            seller=cheapest["seller"],
            shop_quantity=cheapest["quantity"],
            recommendation=analysis.recommendation,
)
            guild = (
                message.guild
                if isinstance(message.guild, discord.Guild)
                else None
            )

            owners = await self.get_owner_details(
                guild=guild,
                item_name=fm["item_name"],
                net_price_per_item=analysis.net_after_tax,
            )

            print(
                f"7-day economy average: "
                f"{economy['avg_price']:,}"
            )
            print(
                f"Net after tax per item: "
                f"{analysis.net_after_tax:,}"
            )
            print(
                f"Recommendation: "
                f"{analysis.recommendation}"
            )
            print(f"Portfolio owners found: {len(owners)}")

            await message.channel.send(
                embed=create_comparison_embed(
                    fm_result=fm,
                    economy_record=economy,
                    analysis=analysis,
                    settings=self.settings,
                    owners=owners,
                )
            )

        except Exception as error:
            traceback.print_exception(
                type(error),
                error,
                error.__traceback__,
            )

            await message.channel.send(
                f"I found the FM price for "
                f"**{fm['item_name']}**, "
                "but the economy comparison failed:\n"
                f"`{error}`"
            )

    async def on_message(
        self,
        message: discord.Message,
    ) -> None:
        if (
            self.bot.user
            and message.author.id == self.bot.user.id
        ):
            return

        if (
            message.author.id == self.settings.dreambot_id
            and message.embeds
        ):
            await self.process_message(message)

        await self.bot.process_commands(message)

    async def on_raw_message_edit(
        self,
        payload: discord.RawMessageUpdateEvent,
    ) -> None:
        author_data = payload.data.get("author")

        if not author_data:
            return

        try:
            author_id = int(
                author_data.get("id", 0)
            )
        except (TypeError, ValueError):
            return

        if author_id != self.settings.dreambot_id:
            return

        channel = self.bot.get_channel(
            payload.channel_id
        )

        if channel is None:
            try:
                channel = await self.bot.fetch_channel(
                    payload.channel_id
                )
            except discord.HTTPException as error:
                print(f"Could not fetch channel: {error}")
                return

        if not hasattr(channel, "fetch_message"):
            return

        await asyncio.sleep(0.5)

        try:
            message = await channel.fetch_message(
                payload.message_id
            )

        except discord.NotFound:
            print(
                "DreamBot's edited message was not found."
            )
            return

        except discord.Forbidden:
            print(
                "The bot does not have permission to read "
                "the edited DreamBot message."
            )
            return

        except discord.HTTPException as error:
            print(
                f"Could not fetch edited DreamBot "
                f"message: {error}"
            )
            return

        await self.process_message(message)


def register(
    bot: commands.Bot,
    settings: Settings,
    api_client: DreamMSClient,
    database: PortfolioDatabase,
    history_service: PriceHistoryService,
) -> DreamBotListener:
    listener = DreamBotListener(
        bot=bot,
        settings=settings,
        api_client=api_client,
        database=database,
        history_service=history_service,
    )

    bot.add_listener(
        listener.on_message,
        "on_message",
    )

    bot.add_listener(
        listener.on_raw_message_edit,
        "on_raw_message_edit",
    )

    return listener