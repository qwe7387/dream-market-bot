from __future__ import annotations

from typing import Any

import discord

from config import Settings
from services.market import MarketAnalysis
from ui.embeds import create_detailed_comparison_embed


class MarketDetailsView(discord.ui.View):
    """Adds an ephemeral full-details button to the compact response."""

    def __init__(
        self,
        fm_result: dict[str, Any],
        economy_record: dict[str, Any],
        analysis: MarketAnalysis,
        settings: Settings,
        owners: list[dict[str, Any]] | None,
    ) -> None:
        super().__init__(timeout=900)
        self.details_embed = create_detailed_comparison_embed(
            fm_result=fm_result,
            economy_record=economy_record,
            analysis=analysis,
            settings=settings,
            owners=owners,
        )

    @discord.ui.button(
        label="View more details",
        style=discord.ButtonStyle.secondary,
    )
    async def view_more_details(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        del button
        await interaction.response.send_message(
            embed=self.details_embed,
            ephemeral=True,
        )
