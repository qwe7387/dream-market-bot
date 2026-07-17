from __future__ import annotations

import asyncio
import traceback
from typing import Any

import discord
from discord.ext import commands

from config import Settings
from services.alerts import PriceAlertService
from services.api import DreamMSClient
from services.database import PortfolioDatabase
from services.dreambot_result import DreamBotResultParser
from services.history import PriceHistoryService
from services.market import analyze_market
from services.resolver import ItemResolver
from ui.embeds import create_comparison_embed
from ui.market_view import MarketDetailsView


class DreamBotListener:
    """Listen for DreamBot results and publish market comparisons."""

    def __init__(
        self,
        bot: commands.Bot,
        settings: Settings,
        api_client: DreamMSClient,
        database: PortfolioDatabase,
        history_service: PriceHistoryService,
        alert_service: PriceAlertService,
    ) -> None:
        self.bot = bot
        self.settings = settings
        self.database = database
        self.history_service = history_service
        self.alert_service = alert_service
        self.result_parser = DreamBotResultParser(api_client)
        self.item_resolver = ItemResolver(api_client)
        self.processed_message_ids: set[int] = set()
        self.processing_message_ids: set[int] = set()
        self.raw_components_by_message_id: dict[int, Any] = {}

    async def get_owner_details(
        self,
        guild: discord.Guild | None,
        item_name: str,
        net_price_per_item: int,
    ) -> list[dict[str, Any]]:
        stored_owners = await self.database.get_item_owners(item_name)
        owner_details: list[dict[str, Any]] = []

        for owner in stored_owners:
            discord_id = owner["discord_id"]
            quantity = owner["quantity"]
            display_name = f"User {discord_id}"

            if guild is not None:
                member = guild.get_member(discord_id)

                if member is None:
                    try:
                        member = await guild.fetch_member(discord_id)
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
                    "estimated_net_proceeds": quantity * net_price_per_item,
                }
            )

        return owner_details

    async def process_message(self, message: discord.Message) -> None:
        if message.id in self.processed_message_ids:
            return

        if message.id in self.processing_message_ids:
            return

        if message.author.id != self.settings.dreambot_id:
            return

        self.processing_message_ids.add(message.id)

        try:
            fm_result = await self.result_parser.parse(
                message,
                self.raw_components_by_message_id.get(message.id, []),
            )

            if fm_result is None:
                return

            resolved = await self.item_resolver.resolve_economy(
                item_id=fm_result["item_id"],
                ocr_item_name=fm_result["item_name"],
                period=7,
            )

            fm_result["item_name"] = resolved.item_name
            economy = resolved.economy
            cheapest = fm_result["cheapest"]
            analysis = analyze_market(
                cheapest["price"],
                economy["avg_price"],
                self.settings,
            )

            await self.history_service.add_record(
                item_id=fm_result["item_id"],
                item_name=fm_result["item_name"],
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
                item_name=fm_result["item_name"],
                net_price_per_item=analysis.net_after_tax,
            )

            self._print_result(fm_result, economy, analysis, owners)

            view = MarketDetailsView(
                fm_result=fm_result,
                economy_record=economy,
                analysis=analysis,
                settings=self.settings,
                owners=owners,
            )
            await message.channel.send(
                embed=create_comparison_embed(
                    fm_result=fm_result,
                    economy_record=economy,
                    analysis=analysis,
                    settings=self.settings,
                    owners=owners,
                ),
                view=view,
            )

            await self._send_price_alerts(
                message=message,
                item_name=fm_result["item_name"],
                seller=cheapest["seller"],
                observed_price=cheapest["price"],
                quantity=cheapest["quantity"],
            )

            self._mark_processed(message.id)
        except Exception as error:
            await self._handle_error(message, error, locals().get("fm_result"))
        finally:
            self.processing_message_ids.discard(message.id)


    async def _send_price_alerts(
        self,
        *,
        message: discord.Message,
        item_name: str,
        seller: str,
        observed_price: int,
        quantity: int,
    ) -> None:
        matches = await self.alert_service.matching_alerts(
            item_name,
            observed_price,
        )

        if not matches:
            return

        mentions = " ".join(
            sorted({f"<@{match['user_id']}>" for match in matches})
        )
        buy_matches = [
            match for match in matches
            if match.get("alert_type") == "buy"
        ]
        sell_matches = [
            match for match in matches
            if match.get("alert_type") == "sell"
        ]

        if buy_matches and sell_matches:
            title = f"Price Alerts Triggered: {item_name}"
        elif buy_matches:
            title = f"Buy Alert: {item_name}"
        else:
            title = f"Sell Alert: {item_name}"

        embed = discord.Embed(
            title=title,
            description=(
                f"Current cheapest listing: **{observed_price:,} mesos**\n"
                f"Seller: **{seller}** | Quantity: **{quantity:,}**"
            ),
        )

        if buy_matches:
            buy_targets = sorted(
                {int(match["target_price"]) for match in buy_matches}
            )
            embed.add_field(
                name="🟢 Buy target reached",
                value="\n".join(
                    f"Current price ≤ {target:,} mesos"
                    for target in buy_targets
                ),
                inline=False,
            )

        if sell_matches:
            sell_targets = sorted(
                {int(match["target_price"]) for match in sell_matches}
            )
            embed.add_field(
                name="🔴 Sell target reached",
                value="\n".join(
                    f"Current price ≥ {target:,} mesos"
                    for target in sell_targets
                ),
                inline=False,
            )

        embed.set_footer(
            text="Manage alerts with /watchlist and /unwatch."
        )

        try:
            await message.channel.send(
                content=mentions,
                embed=embed,
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        except discord.HTTPException as error:
            print(f"Could not send price alert: {error}")

    def _mark_processed(self, message_id: int) -> None:
        self.processed_message_ids.add(message_id)
        self.raw_components_by_message_id.pop(message_id, None)

        if len(self.processed_message_ids) > 500:
            self.processed_message_ids = {message_id}

    @staticmethod
    def _print_result(
        fm_result: dict[str, Any],
        economy: dict[str, Any],
        analysis: Any,
        owners: list[dict[str, Any]],
    ) -> None:
        cheapest = fm_result["cheapest"]
        print("\nFM result parsed successfully")
        print(f"Item: {fm_result['item_name']}")
        print(f"Item ID: {fm_result['item_id']}")
        print(f"Lowest price: {cheapest['price']:,}")
        print(f"Quantity: {cheapest['quantity']}")
        print(f"Seller: {cheapest['seller']}")
        print(f"7-day economy average: {economy['avg_price']:,}")
        print(f"Net after tax per item: {analysis.net_after_tax:,}")
        print(f"Recommendation: {analysis.recommendation}")
        print(f"Portfolio owners found: {len(owners)}")

    async def _handle_error(
        self,
        message: discord.Message,
        error: Exception,
        fm_result: dict[str, Any] | None,
    ) -> None:
        print("Failed to compare FM and economy data:")
        traceback.print_exception(type(error), error, error.__traceback__)

        item_name = "the requested item"

        if fm_result is not None:
            item_name = fm_result.get("item_name", item_name)

        try:
            await message.channel.send(
                f"I found the DreamBot response for **{item_name}**, "
                "but the market comparison failed:\n"
                f"`{error}`"
            )
        except discord.HTTPException:
            print("Discord could not display the market comparison error.")

    async def on_message(self, message: discord.Message) -> None:
        if self.bot.user and message.author.id == self.bot.user.id:
            return

        if message.author.id == self.settings.dreambot_id:
            await self.process_message(message)

        await self.bot.process_commands(message)

    async def on_raw_message_edit(
        self,
        payload: discord.RawMessageUpdateEvent,
    ) -> None:
        self.raw_components_by_message_id[payload.message_id] = (
            payload.data.get("components", [])
        )

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
                channel = await self.bot.fetch_channel(payload.channel_id)
            except discord.HTTPException as error:
                print(f"Could not fetch channel: {error}")
                return

        if not hasattr(channel, "fetch_message"):
            return

        await asyncio.sleep(0.75)

        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.NotFound:
            print("DreamBot's edited message was not found.")
            return
        except discord.Forbidden:
            print(
                "The bot does not have permission to read "
                "the edited DreamBot message."
            )
            return
        except discord.HTTPException as error:
            print(f"Could not fetch edited DreamBot message: {error}")
            return

        await self.process_message(message)


def register(
    bot: commands.Bot,
    settings: Settings,
    api_client: DreamMSClient,
    database: PortfolioDatabase,
    history_service: PriceHistoryService,
    alert_service: PriceAlertService,
) -> DreamBotListener:
    listener = DreamBotListener(
        bot=bot,
        settings=settings,
        api_client=api_client,
        database=database,
        history_service=history_service,
        alert_service=alert_service,
    )
    bot.add_listener(listener.on_message, "on_message")
    bot.add_listener(listener.on_raw_message_edit, "on_raw_message_edit")
    return listener
