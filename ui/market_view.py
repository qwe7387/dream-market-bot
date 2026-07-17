from typing import Any

import discord

from config import Settings
from services.market import MarketAnalysis
from ui.embeds import (
    create_detailed_comparison_embed,
)


class MarketDetailsView(discord.ui.View):
    def __init__(
        self,
        fm_result: dict[str, Any],
        economy_record: dict[str, Any],
        analysis: MarketAnalysis,
        settings: Settings,
        owners: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(timeout=900)

        self.fm_result = fm_result
        self.economy_record = economy_record
        self.analysis = analysis
        self.settings = settings
        self.owners = owners

    @discord.ui.button(
        label="View more details",
        style=discord.ButtonStyle.secondary,
        emoji="🔎",
    )
    async def view_more_details(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        del button

        detailed_embed = (
            create_detailed_comparison_embed(
                fm_result=self.fm_result,
                economy_record=self.economy_record,
                analysis=self.analysis,
                settings=self.settings,
                owners=self.owners,
            )
        )

        await interaction.response.send_message(
            embed=detailed_embed,
            ephemeral=True,
        )
