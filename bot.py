import logging
import traceback

import aiohttp
import discord
from discord.ext import commands

from commands import alerts, basic, economy, history, portfolio
from core.config import get_settings
from core.logging import configure_logging
from events.dreambot import register as register_dreambot_events
from services.alerts import PriceAlertService
from services.api import DreamMSClient
from services.database import PortfolioDatabase
from services.history import PriceHistoryService

logger = logging.getLogger(__name__)
SETTINGS = get_settings()


class DreamMarketBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.database = PortfolioDatabase()
        self.history_service = PriceHistoryService()
        self.alert_service = PriceAlertService()
        self.http_session: aiohttp.ClientSession | None = None
        self.api_client: DreamMSClient | None = None

    async def setup_hook(self) -> None:
        self.http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                "X-API-Key": SETTINGS.game_api_key,
                "Accept": "application/json",
            },
        )
        self.api_client = DreamMSClient(
            self.http_session,
            SETTINGS.game_api_base_url,
            cache_ttl_seconds=SETTINGS.economy_cache_minutes * 60,
        )
        await self.database.initialize()
        await self.history_service.initialize()
        await self.alert_service.initialize()
        await basic.setup(self, SETTINGS, self.api_client)
        await economy.setup(self, self.api_client)
        await portfolio.setup(self, self.database)
        await history.setup(self, self.history_service)
        await alerts.setup(self, self.alert_service)
        register_dreambot_events(
            bot=self,
            settings=SETTINGS,
            api_client=self.api_client,
            database=self.database,
            history_service=self.history_service,
            alert_service=self.alert_service,
        )
        synced_commands = await self.tree.sync()
        logger.info("Synced %s slash command(s)", len(synced_commands))
        for command in synced_commands:
            logger.info("Registered command: /%s", command.name)

    async def close(self) -> None:
        if self.http_session is not None:
            await self.http_session.close()
        await super().close()


bot = DreamMarketBot()


@bot.event
async def on_ready() -> None:
    logger.info("Bot is online as %s", bot.user)
    logger.info("Bot ID: %s", bot.user.id if bot.user else "Unknown")
    if not bot.guilds:
        logger.warning("The bot is not connected to any server")
    for guild in bot.guilds:
        logger.info("Connected server: %s | Server ID: %s", guild.name, guild.id)


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: discord.app_commands.AppCommandError,
) -> None:
    logger.error("Slash-command error", exc_info=(type(error), error, error.__traceback__))
    try:
        if interaction.response.is_done():
            await interaction.followup.send(f"Command error: {error}", ephemeral=True)
        else:
            await interaction.response.send_message(f"Command error: {error}", ephemeral=True)
    except discord.HTTPException:
        logger.exception("Discord could not display the command error")


def main() -> None:
    configure_logging()
    bot.run(SETTINGS.discord_token)


if __name__ == "__main__":
    main()
