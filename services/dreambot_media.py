from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any
from urllib.parse import unquote, urlparse

import discord

from services.api import DreamMSClient


logger = logging.getLogger(__name__)


IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


@dataclass(frozen=True)
class DreamBotImage:
    content: bytes
    filename: str | None


class DreamBotMediaService:
    """Find and download DreamBot images from every Discord format used."""

    def __init__(self, api_client: DreamMSClient) -> None:
        self.api_client = api_client

    async def get_image(
        self,
        message: discord.Message,
        raw_components: Any = None,
    ) -> DreamBotImage | None:
        attachment_image = await self._from_attachments(message)

        if attachment_image is not None:
            return attachment_image

        embed_image = await self._from_embeds(message)

        if embed_image is not None:
            return embed_image

        return await self._from_components(
            message,
            raw_components or [],
        )

    async def _from_attachments(
        self,
        message: discord.Message,
    ) -> DreamBotImage | None:
        for attachment in message.attachments:
            if not self._attachment_looks_like_image(attachment):
                continue

            try:
                return DreamBotImage(
                    content=await attachment.read(),
                    filename=attachment.filename,
                )
            except discord.HTTPException as error:
                logger.warning("Could not read DreamBot attachment: %s", error)

        return None

    async def _from_embeds(
        self,
        message: discord.Message,
    ) -> DreamBotImage | None:
        for embed in message.embeds:
            urls = []

            if embed.image and embed.image.url:
                urls.append(embed.image.url)

            if embed.thumbnail and embed.thumbnail.url:
                urls.append(embed.thumbnail.url)

            for url in urls:
                content = await self._download_url(url)

                if content is not None:
                    return DreamBotImage(
                        content=content,
                        filename=self._filename_from_url(url),
                    )

        return None

    async def _from_components(
        self,
        message: discord.Message,
        raw_components: Any,
    ) -> DreamBotImage | None:
        urls: list[str] = []

        self._collect_media_urls(
            getattr(message, "components", []),
            urls,
            set(),
        )
        self._collect_media_urls(raw_components, urls, set())

        for url in urls:
            content = await self._download_url(url)

            if content is not None:
                return DreamBotImage(
                    content=content,
                    filename=self._filename_from_url(url),
                )

        if getattr(message, "components", None) or raw_components:
            logger.warning(
                "DreamBot used a component message, but no downloadable media URL was found"
            )

        return None

    async def _download_url(self, url: str) -> bytes | None:
        session = getattr(self.api_client, "session", None)

        if session is None:
            logger.error(
                "Cannot download DreamBot image: the API HTTP session is unavailable"
            )
            return None

        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.warning(
                        "Could not download DreamBot image; HTTP status=%s",
                        response.status,
                    )
                    return None

                return await response.read()
        except Exception as error:
            logger.warning("Could not download DreamBot image URL: %s", error)
            return None

    @staticmethod
    def _attachment_looks_like_image(
        attachment: discord.Attachment,
    ) -> bool:
        content_type = (attachment.content_type or "").casefold()

        if content_type.startswith("image/"):
            return True

        return attachment.filename.casefold().endswith(IMAGE_EXTENSIONS)

    @staticmethod
    def _filename_from_url(url: str) -> str | None:
        try:
            path = unquote(urlparse(url).path)
        except Exception:
            return None

        filename = path.rsplit("/", 1)[-1].strip()
        return filename or None

    def _collect_media_urls(
        self,
        value: Any,
        found: list[str],
        seen: set[int],
    ) -> None:
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

        to_dict = getattr(value, "to_dict", None)

        if callable(to_dict):
            try:
                self._collect_media_urls(to_dict(), found, seen)
            except Exception:
                pass

        for name in (
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
                child = getattr(value, name)
            except Exception:
                continue

            self._collect_media_urls(child, found, seen)

        try:
            object_dict = vars(value)
        except TypeError:
            object_dict = None

        if isinstance(object_dict, dict):
            self._collect_media_urls(object_dict, found, seen)
