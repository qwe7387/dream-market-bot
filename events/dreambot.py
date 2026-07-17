from __future__ import annotations

import asyncio
import logging
from typing import Any

import discord
from discord.ext import commands

from core.config import Settings
from domain.models import MarketScan, OwnerPosition, owners_to_dicts
from services.alerts import PriceAlertService
from services.api import DreamMSClient
from services.database import PortfolioDatabase
from services.dreambot_result import DreamBotResultParser
from services.history import PriceHistoryService
from services.market_pipeline import MarketPipeline
from services.resolver import ItemResolver
from ui.embeds import create_comparison_embed
from ui.market_view import MarketDetailsView

logger = logging.getLogger(__name__)


class DreamBotListener:
    """Discord adapter for the market-processing pipeline."""

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
        self.alert_service = alert_service
        self.result_parser = DreamBotResultParser(api_client)
        self.pipeline = MarketPipeline(
            settings=settings,
            resolver=ItemResolver(api_client),
            history_service=history_service,
        )
        self.processed_message_ids: set[int] = set()
        self.processing_message_ids: set[int] = set()
        self.raw_components_by_message_id: dict[int, Any] = {}

    async def get_owner_details(
        self,
        guild: discord.Guild | None,
        item_name: str,
        net_price_per_item: int,
    ) -> list[OwnerPosition]:
        stored_owners = await self.database.get_item_owners(item_name)
        owner_details: list[OwnerPosition] = []
        for owner in stored_owners:
            discord_id = int(owner["discord_id"])
            quantity = int(owner["quantity"])
            display_name = f"User {discord_id}"
            if guild is not None:
                member = guild.get_member(discord_id)
                if member is None:
                    try:
                        member = await guild.fetch_member(discord_id)
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        member = None
                if member is not None:
                    display_name = member.display_name
            owner_details.append(
                OwnerPosition(
                    discord_id=discord_id,
                    display_name=display_name,
                    quantity=quantity,
                    estimated_net_proceeds=quantity * net_price_per_item,
                )
            )
        return owner_details

    async def process_message(self, message: discord.Message) -> None:
        if message.id in self.processed_message_ids or message.id in self.processing_message_ids:
            return
        if message.author.id != self.settings.dreambot_id:
            return

        self.processing_message_ids.add(message.id)
        scan: MarketScan | None = None
        try:
            scan = await self.result_parser.parse(
                message,
                self.raw_components_by_message_id.get(message.id, []),
            )
            if scan is None:
                return

            result = await self.pipeline.process(scan)
            guild = message.guild if isinstance(message.guild, discord.Guild) else None
            owners = await self.get_owner_details(
                guild,
                result.scan.item_name,
                result.analysis.net_after_tax,
            )
            self._log_result(result.scan, result.economy.average_price, result.analysis, owners)

            scan_dict = result.scan.to_dict()
            economy_dict = result.economy.to_dict()
            owner_dicts = owners_to_dicts(owners)
            view = MarketDetailsView(
                fm_result=scan_dict,
                economy_record=economy_dict,
                analysis=result.analysis,
                settings=self.settings,
                owners=owner_dicts,
            )
            await message.channel.send(
                embed=create_comparison_embed(
                    fm_result=scan_dict,
                    economy_record=economy_dict,
                    analysis=result.analysis,
                    settings=self.settings,
                    owners=owner_dicts,
                ),
                view=view,
            )
            cheapest = result.scan.cheapest
            await self._send_price_alerts(
                message=message,
                item_name=result.scan.item_name,
                seller=cheapest.seller,
                observed_price=cheapest.price,
                quantity=cheapest.quantity,
            )
            self._mark_processed(message.id)
        except Exception as error:
            await self._handle_error(message, error, scan)
        finally:
            self.processing_message_ids.discard(message.id)

    async def _send_price_alerts(self, *, message: discord.Message, item_name: str, seller: str, observed_price: int, quantity: int) -> None:
        matches = await self.alert_service.matching_alerts(item_name, observed_price)
        if not matches:
            return
        mentions = " ".join(sorted({f"<@{match['user_id']}>" for match in matches}))
        buy_matches = [match for match in matches if match.get("alert_type") == "buy"]
        sell_matches = [match for match in matches if match.get("alert_type") == "sell"]
        title = (
            f"Price Alerts Triggered: {item_name}"
            if buy_matches and sell_matches
            else f"Buy Alert: {item_name}"
            if buy_matches
            else f"Sell Alert: {item_name}"
        )
        embed = discord.Embed(
            title=title,
            description=(
                f"Current cheapest listing: **{observed_price:,} mesos**\n"
                f"Seller: **{seller}** | Quantity: **{quantity:,}**"
            ),
        )
        if buy_matches:
            targets = sorted({int(match["target_price"]) for match in buy_matches})
            embed.add_field(
                name="🟢 Buy target reached",
                value="\n".join(f"Current price ≤ {target:,} mesos" for target in targets),
                inline=False,
            )
        if sell_matches:
            targets = sorted({int(match["target_price"]) for match in sell_matches})
            embed.add_field(
                name="🔴 Sell target reached",
                value="\n".join(f"Current price ≥ {target:,} mesos" for target in targets),
                inline=False,
            )
        embed.set_footer(text="Manage alerts with /watchlist and /unwatch.")
        try:
            await message.channel.send(
                content=mentions,
                embed=embed,
                allowed_mentions=discord.AllowedMentions(users=True),
            )
        except discord.HTTPException:
            logger.exception("Could not send price alert")

    def _mark_processed(self, message_id: int) -> None:
        self.processed_message_ids.add(message_id)
        self.raw_components_by_message_id.pop(message_id, None)
        if len(self.processed_message_ids) > 500:
            self.processed_message_ids = {message_id}

    @staticmethod
    def _log_result(scan: MarketScan, average_price: int, analysis: Any, owners: list[OwnerPosition]) -> None:
        cheapest = scan.cheapest
        logger.info(
            "FM result item=%r item_id=%s price=%s quantity=%s seller=%r average=%s net=%s recommendation=%s owners=%s",
            scan.item_name,
            scan.item_id,
            f"{cheapest.price:,}",
            cheapest.quantity,
            cheapest.seller,
            f"{average_price:,}",
            f"{analysis.net_after_tax:,}",
            analysis.recommendation,
            len(owners),
        )

    async def _handle_error(self, message: discord.Message, error: Exception, scan: MarketScan | None) -> None:
        logger.exception("Failed to compare FM and economy data")
        item_name = scan.item_name if scan is not None else "the requested item"
        try:
            await message.channel.send(
                f"I found the DreamBot response for **{item_name}**, "
                "but the market comparison failed:\n"
                f"`{error}`"
            )
        except discord.HTTPException:
            logger.exception("Discord could not display the market comparison error")

    async def on_message(self, message: discord.Message) -> None:
        if self.bot.user and message.author.id == self.bot.user.id:
            return
        if message.author.id == self.settings.dreambot_id:
            await self.process_message(message)
        await self.bot.process_commands(message)

    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        self.raw_components_by_message_id[payload.message_id] = payload.data.get("components", [])
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
            except discord.HTTPException:
                logger.exception("Could not fetch channel")
                return
        if not hasattr(channel, "fetch_message"):
            return
        await asyncio.sleep(0.75)
        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.NotFound:
            logger.warning("DreamBot's edited message was not found")
            return
        except discord.Forbidden:
            logger.warning("Missing permission to read the edited DreamBot message")
            return
        except discord.HTTPException:
            logger.exception("Could not fetch edited DreamBot message")
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
