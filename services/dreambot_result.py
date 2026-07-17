from __future__ import annotations

import traceback
from typing import Any

import discord

from services.api import DreamMSClient
from services.dreambot_filename import apply_filename_cheapest
from services.dreambot_media import DreamBotMediaService
from services.ocr import OCRError, OCRService
from services.parser import parse_fm_embed


class DreamBotResultParser:
    """Convert DreamBot messages into one normalized FM result dictionary."""

    def __init__(self, api_client: DreamMSClient) -> None:
        self.media_service = DreamBotMediaService(api_client)
        self.ocr_service = OCRService()

    async def parse(
        self,
        message: discord.Message,
        raw_components: Any = None,
    ) -> dict[str, Any] | None:
        image = await self.media_service.get_image(
            message,
            raw_components,
        )

        if image is not None:
            try:
                fm_result = await self.ocr_service.parse_bytes_async(
                    image.content
                )
                apply_filename_cheapest(
                    fm_result,
                    image.filename,
                )
                print("DreamBot image parsed successfully with OCR.")
                return fm_result
            except OCRError as error:
                print(f"DreamBot OCR could not parse the image: {error}")
            except Exception as error:
                print("Unexpected DreamBot OCR error:")
                traceback.print_exception(
                    type(error),
                    error,
                    error.__traceback__,
                )

        for embed in message.embeds:
            fm_result = parse_fm_embed(embed)

            if fm_result is not None:
                print("DreamBot legacy embed parsed successfully.")
                return fm_result

        return None
