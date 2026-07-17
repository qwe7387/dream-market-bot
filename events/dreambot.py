import asyncio
import re
import traceback
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import discord
from discord.ext import commands

from config import Settings
from services.api import DreamMSClient
from services.database import PortfolioDatabase
from services.history import PriceHistoryService
from services.resolver import ItemResolver
from services.market import analyze_market
from services.ocr import OCRError, OCRService
from services.parser import parse_fm_embed
from ui.embeds import create_comparison_embed


IMAGE_EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
)


DREAMBOT_FILENAME_PATTERN = re.compile(
    r"^p\d+_(?P<seller>.+)_(?P<price>\d+)$",
    re.IGNORECASE,
)


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
        self.ocr_service = OCRService()
        self.item_resolver = ItemResolver(api_client)

        # Prevent processing the same completed DreamBot result twice.
        self.processed_message_ids: set[int] = set()

        # Prevent two Discord events from processing the same message
        # simultaneously.
        self.processing_message_ids: set[int] = set()
        self.raw_components_by_message_id: dict[int, Any] = {}

    async def get_owner_details(
        self,
        guild: discord.Guild | None,
        item_name: str,
        net_price_per_item: int,
    ) -> list[dict[str, Any]]:
        """
        Find everyone who owns the item and resolve their current
        Discord server display names.
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

    @staticmethod
    def _attachment_looks_like_image(
        attachment: discord.Attachment,
    ) -> bool:
        content_type = (
            attachment.content_type or ""
        ).casefold()

        if content_type.startswith("image/"):
            return True

        filename = attachment.filename.casefold()

        return filename.endswith(IMAGE_EXTENSIONS)

    def _collect_media_urls(
        self,
        value: Any,
        found: list[str],
        seen: set[int],
    ) -> None:
        """Recursively find media URLs in Discord Components V2 payloads."""
        if value is None:
            return

        if isinstance(value, str):
            if value.startswith(("https://", "http://")) and value not in found:
                found.append(value)
            return

        if isinstance(value, (bytes, int, float, bool)):
            return

        object_id = id(value)
        if object_id in seen:
            return
        seen.add(object_id)

        if isinstance(value, dict):
            for child in value.values():
                self._collect_media_urls(child, found, seen)
            return

        if isinstance(value, (list, tuple, set)):
            for child in value:
                self._collect_media_urls(child, found, seen)
            return

        # discord.py component classes may expose a raw dictionary.
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            try:
                self._collect_media_urls(to_dict(), found, seen)
            except Exception:
                pass

        for attribute_name in (
            "url",
            "proxy_url",
            "media",
            "thumbnail",
            "image",
            "item",
            "items",
            "children",
            "components",
            "content",
        ):
            try:
                child = getattr(value, attribute_name)
            except Exception:
                continue
            self._collect_media_urls(child, found, seen)

        try:
            object_dict = vars(value)
        except TypeError:
            object_dict = None

        if isinstance(object_dict, dict):
            self._collect_media_urls(object_dict, found, seen)

    @staticmethod
    def _filename_from_url(
        url: str,
    ) -> str | None:
        """
        Extract the original media filename from a Discord CDN URL.

        Example:
            .../p1_Complete_999999.png?... ->
            p1_Complete_999999.png
        """

        try:
            path = unquote(
                urlparse(url).path
            )
        except Exception:
            return None

        filename = Path(path).name.strip()

        return filename or None

    @staticmethod
    def _parse_cheapest_metadata(
        filename: str | None,
    ) -> tuple[str, int] | None:
        """
        DreamBot filenames currently use:

            p<page>_<cheapest seller>_<cheapest price>.png

        Seller names may contain underscores, so the regular expression
        captures everything between the first and last underscore.
        """

        if not filename:
            return None

        stem = Path(filename).stem

        match = DREAMBOT_FILENAME_PATTERN.fullmatch(
            stem
        )

        if match is None:
            return None

        seller = match.group("seller").strip()
        price_text = match.group("price")

        if not seller or not price_text:
            return None

        return seller, int(price_text)

    @staticmethod
    def _apply_filename_cheapest(
        fm: dict[str, Any],
        filename: str | None,
    ) -> None:
        """
        Override OCR's cheapest seller and price using DreamBot's
        filename metadata.

        OCR is still used for the item title, item ID, and quantity.
        """

        metadata = (
            DreamBotListener._parse_cheapest_metadata(
                filename
            )
        )

        if metadata is None:
            return

        filename_seller, filename_price = metadata
        listings = fm.get("listings")

        quantity = 1
        matching_index: int | None = None

        if isinstance(listings, list):
            for index, listing in enumerate(listings):
                if not isinstance(listing, dict):
                    continue

                seller = str(
                    listing.get("seller", "")
                ).casefold()

                if seller == filename_seller.casefold():
                    matching_index = index

                    try:
                        quantity = max(
                            1,
                            int(
                                listing.get(
                                    "quantity",
                                    1,
                                )
                            ),
                        )
                    except (
                        TypeError,
                        ValueError,
                    ):
                        quantity = 1

                    break

        if matching_index is None:
            current_cheapest = fm.get("cheapest", {})

            if isinstance(current_cheapest, dict):
                try:
                    quantity = max(
                        1,
                        int(
                            current_cheapest.get(
                                "quantity",
                                1,
                            )
                        ),
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    quantity = 1

        reliable_cheapest = {
            "seller": filename_seller,
            "price": filename_price,
            "quantity": quantity,
        }

        fm["cheapest"] = reliable_cheapest

        if isinstance(listings, list):
            if matching_index is not None:
                listings[matching_index] = (
                    reliable_cheapest.copy()
                )
            else:
                listings.append(
                    reliable_cheapest.copy()
                )

            listings.sort(
                key=lambda listing: int(
                    listing.get(
                        "price",
                        0,
                    )
                )
                if isinstance(listing, dict)
                else 0
            )

        print(
            "Used DreamBot filename for cheapest "
            f"listing: seller={filename_seller!r}, "
            f"price={filename_price:,}, "
            f"quantity={quantity}"
        )

    async def _download_url(
        self,
        url: str,
    ) -> bytes | None:
        """
        Download an image URL using the bot's existing HTTP session.
        """

        session = getattr(
            self.api_client,
            "session",
            None,
        )

        if session is None:
            print(
                "Cannot download DreamBot image: "
                "the API HTTP session is unavailable."
            )
            return None

        try:
            async with session.get(url) as response:
                if response.status != 200:
                    print(
                        "Could not download DreamBot image. "
                        f"HTTP status: {response.status}"
                    )
                    return None

                return await response.read()

        except Exception as error:
            print(
                "Could not download DreamBot image URL: "
                f"{error}"
            )
            return None

    async def _get_image_source(
        self,
        message: discord.Message,
    ) -> tuple[bytes, str | None] | None:
        """
        Find the DreamBot result image.

        DreamBot may send it as:
        1. A normal Discord attachment.
        2. An embed image or thumbnail.
        3. A Components V2 media-gallery item.
        """

        for attachment in message.attachments:
            if not self._attachment_looks_like_image(
                attachment
            ):
                continue

            try:
                return (
                    await attachment.read(),
                    attachment.filename,
                )
            except discord.HTTPException as error:
                print(
                    "Could not read DreamBot attachment: "
                    f"{error}"
                )

        for embed in message.embeds:
            if embed.image and embed.image.url:
                image_bytes = await self._download_url(
                    embed.image.url
                )

                if image_bytes:
                    return (
                        image_bytes,
                        self._filename_from_url(
                            embed.image.url
                        ),
                    )

            if embed.thumbnail and embed.thumbnail.url:
                image_bytes = await self._download_url(
                    embed.thumbnail.url
                )

                if image_bytes:
                    return (
                        image_bytes,
                        self._filename_from_url(
                            embed.thumbnail.url
                        ),
                    )

        # DreamBot now uses Discord Components V2 media galleries.
        component_urls: list[str] = []

        self._collect_media_urls(
            getattr(message, "components", []),
            component_urls,
            set(),
        )

        raw_components = self.raw_components_by_message_id.get(
            message.id,
            [],
        )
        self._collect_media_urls(
            raw_components,
            component_urls,
            set(),
        )

        for url in component_urls:
            image_bytes = await self._download_url(url)

            if image_bytes:
                return (
                    image_bytes,
                    self._filename_from_url(url),
                )

        if getattr(message, "components", None) or raw_components:
            print(
                "DreamBot used a component message, but no downloadable "
                "media URL was found."
            )
            print(f"Raw components: {raw_components!r}")

        return None

    async def _parse_dreambot_result(
        self,
        message: discord.Message,
    ) -> dict[str, Any] | None:
        """
        Prefer the new image OCR format, while keeping compatibility
        with DreamBot's previous text-embed format.
        """

        image_source = await self._get_image_source(
            message
        )

        if image_source:
            image_bytes, image_filename = image_source

            try:
                fm = await self.ocr_service.parse_bytes_async(
                    image_bytes
                )

                self._apply_filename_cheapest(
                    fm,
                    image_filename,
                )

                print(
                    "DreamBot image parsed successfully "
                    "with OCR."
                )

                return fm

            except OCRError as error:
                print(
                    "DreamBot OCR could not parse the image: "
                    f"{error}"
                )

            except Exception as error:
                print(
                    "Unexpected DreamBot OCR error:"
                )
                traceback.print_exception(
                    type(error),
                    error,
                    error.__traceback__,
                )

        # Temporary fallback in case DreamBot sends an old-style embed.
        for embed in message.embeds:
            fm = parse_fm_embed(embed)

            if fm is not None:
                print(
                    "DreamBot legacy embed parsed "
                    "successfully."
                )
                return fm

        return None

    async def process_message(
        self,
        message: discord.Message,
    ) -> None:
        if message.id in self.processed_message_ids:
            return

        if message.id in self.processing_message_ids:
            return

        if message.author.id != self.settings.dreambot_id:
            return

        self.processing_message_ids.add(message.id)

        try:
            fm = await self._parse_dreambot_result(
                message
            )

            if fm is None:
                # DreamBot's first interaction response may still be
                # the loading message. Wait for its later edit event.
                return

            resolved = (
                await self.item_resolver.resolve_economy(
                    item_id=fm["item_id"],
                    ocr_item_name=fm["item_name"],
                    period=7,
                )
            )

            fm["item_name"] = resolved.item_name
            economy = resolved.economy

            cheapest = fm["cheapest"]

            print("\nFM result parsed successfully")
            print(f"Item: {fm['item_name']}")
            print(f"Item ID: {fm['item_id']}")
            print(
                f"Lowest price: "
                f"{cheapest['price']:,}"
            )
            print(
                f"Quantity: "
                f"{cheapest['quantity']}"
            )
            print(
                f"Seller: "
                f"{cheapest['seller']}"
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
                if isinstance(
                    message.guild,
                    discord.Guild,
                )
                else None
            )

            owners = await self.get_owner_details(
                guild=guild,
                item_name=fm["item_name"],
                net_price_per_item=(
                    analysis.net_after_tax
                ),
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
            print(
                "Portfolio owners found: "
                f"{len(owners)}"
            )

            await message.channel.send(
                embed=create_comparison_embed(
                    fm_result=fm,
                    economy_record=economy,
                    analysis=analysis,
                    settings=self.settings,
                    owners=owners,
                )
            )

            self.processed_message_ids.add(
                message.id
            )
            self.raw_components_by_message_id.pop(
                message.id,
                None,
            )

            if (
                len(self.processed_message_ids)
                > 500
            ):
                self.processed_message_ids.clear()
                self.processed_message_ids.add(
                    message.id
                )

        except Exception as error:
            print(
                "Failed to compare FM and economy data:"
            )

            traceback.print_exception(
                type(error),
                error,
                error.__traceback__,
            )

            # fm might not exist if OCR failed before parsing.
            item_name = "the requested item"

            if "fm" in locals() and fm is not None:
                item_name = fm.get(
                    "item_name",
                    item_name,
                )

            try:
                await message.channel.send(
                    f"I found the DreamBot response for "
                    f"**{item_name}**, but the market "
                    "comparison failed:\n"
                    f"`{error}`"
                )
            except discord.HTTPException:
                print(
                    "Discord could not display the "
                    "market comparison error."
                )

        finally:
            self.processing_message_ids.discard(
                message.id
            )

    async def on_message(
        self,
        message: discord.Message,
    ) -> None:
        if (
            self.bot.user
            and message.author.id
            == self.bot.user.id
        ):
            return

        if (
            message.author.id
            == self.settings.dreambot_id
        ):
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
                print(
                    f"Could not fetch channel: {error}"
                )
                return

        if not hasattr(channel, "fetch_message"):
            return

        # Give DreamBot time to finish replacing its loading response
        # with the final image.
        await asyncio.sleep(0.75)

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
                "Could not fetch edited DreamBot "
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
