import asyncio
import traceback

import discord
from discord.ext import commands

from config import Settings
from services.api import DreamMSClient
from services.market import analyze_market
from services.parser import parse_fm_embed
from ui.embeds import create_comparison_embed


class DreamBotListener:
    def __init__(
        self,
        bot: commands.Bot,
        settings: Settings,
        api_client: DreamMSClient,
    ) -> None:
        self.bot = bot
        self.settings = settings
        self.api_client = api_client
        self.processed_message_ids: set[int] = set()

    async def process_message(self, message: discord.Message) -> None:
        if message.id in self.processed_message_ids:
            return
        if message.author.id != self.settings.dreambot_id:
            return
        if not message.embeds:
            return

        fm = parse_fm_embed(message.embeds[0])
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

            print(
                f"7-day economy average: "
                f"{economy['avg_price']:,}"
            )
            print(f"Net after tax: {analysis.net_after_tax:,}")
            print(f"Recommendation: {analysis.recommendation}")

            await message.channel.send(
                embed=create_comparison_embed(
                    fm,
                    economy,
                    analysis,
                    self.settings,
                )
            )
        except Exception as error:
            traceback.print_exception(
                type(error),
                error,
                error.__traceback__,
            )
            await message.channel.send(
                f"I found the FM price for **{fm['item_name']}**, "
                "but the economy comparison failed:\n"
                f"`{error}`"
            )

    async def on_message(self, message: discord.Message) -> None:
        if self.bot.user and message.author.id == self.bot.user.id:
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
            author_id = int(author_data.get("id", 0))
        except (TypeError, ValueError):
            return

        if author_id != self.settings.dreambot_id:
            return

        channel = self.bot.get_channel(payload.channel_id)
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
            print("DreamBot's edited message was not found.")
            return
        except discord.Forbidden:
            print(
                "The bot does not have permission to read the "
                "edited DreamBot message."
            )
            return
        except discord.HTTPException as error:
            print(
                f"Could not fetch edited DreamBot message: {error}"
            )
            return

        await self.process_message(message)


def register(
    bot: commands.Bot,
    settings: Settings,
    api_client: DreamMSClient,
) -> DreamBotListener:
    listener = DreamBotListener(bot, settings, api_client)
    bot.add_listener(listener.on_message, "on_message")
    bot.add_listener(
        listener.on_raw_message_edit,
        "on_raw_message_edit",
    )
    return listener
