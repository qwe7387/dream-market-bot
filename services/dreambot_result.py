from __future__ import annotations

import logging
from typing import Any

import discord

from domain.models import MarketScan
from services.api import DreamMSClient
from services.dreambot_filename import apply_filename_to_scan
from services.dreambot_media import DreamBotMediaService
from services.ocr import OCRError, OCRService
from services.parser import parse_fm_embed

logger = logging.getLogger(__name__)


class DreamBotResultParser:
    """Convert DreamBot messages into one normalized MarketScan object."""

    def __init__(self, api_client: DreamMSClient) -> None:
        self.media_service = DreamBotMediaService(api_client)
        self.ocr_service = OCRService()

    async def parse(
        self,
        message: discord.Message,
        raw_components: Any = None,
    ) -> MarketScan | None:
        image = await self.media_service.get_image(message, raw_components)

        if image is not None:
            try:
                scan = await self.ocr_service.parse_model_async(image.content)
                quantity = self.ocr_service.extract_first_quantity_bytes(image.content)
                scan = apply_filename_to_scan(
                    scan,
                    image.filename,
                    trusted_quantity=quantity,
                )
                logger.info("DreamBot image parsed successfully with OCR")
                return scan
            except OCRError as error:
                logger.warning("DreamBot OCR could not parse the image: %s", error)
            except Exception:
                logger.exception("Unexpected DreamBot OCR error")

        for embed in message.embeds:
            legacy = parse_fm_embed(embed)
            if legacy is not None:
                logger.info("DreamBot legacy embed parsed successfully")
                return MarketScan.from_dict(legacy)

        return None
