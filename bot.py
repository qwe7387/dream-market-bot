import traceback

import aiohttp
import discord
from discord.ext import commands

from commands import basic, economy, history, portfolio
from config import SETTINGS
from events.dreambot import register as register_dreambot_events
from services.api import DreamMSClient
from services.database import PortfolioDatabase
from services.history import PriceHistoryService


class DreamMarketBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix="!",
            intents=intents,
        )

        self.database = PortfolioDatabase()
        self.history_service = PriceHistoryService()
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
        )

        await self.database.initialize()
        await self.history_service.initialize()

        await basic.setup(self, SETTINGS)
        await economy.setup(self, self.api_client)
        await portfolio.setup(self, self.database)
        await history.setup(self, self.history_service)

        register_dreambot_events(
            bot=self,
            settings=SETTINGS,
            api_client=self.api_client,
            database=self.database,
            history_service=self.history_service,
        )

        synced_commands = await self.tree.sync()
        print(f"Synced {len(synced_commands)} slash command(s).")

        for command in synced_commands:
            print(f"Registered command: /{command.name}")

    async def close(self) -> None:
        if self.http_session is not None:
            await self.http_session.close()

        await super().close()


bot = DreamMarketBot()


@bot.event
async def on_ready() -> None:
    print(f"Bot is online as {bot.user}")
    print(f"Bot ID: {bot.user.id if bot.user else 'Unknown'}")

    if not bot.guilds:
        print("The bot is not connected to any server.")

    for guild in bot.guilds:
        print(
            f"Connected server: {guild.name} "
            f"| Server ID: {guild.id}"
        )


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error: discord.app_commands.AppCommandError,
) -> None:
    print("Slash-command error:")
    traceback.print_exception(
        type(error),
        error,
        error.__traceback__,
    )

    try:
        if interaction.response.is_done():
            await interaction.followup.send(
                f"Command error: {error}",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"Command error: {error}",
                ephemeral=True,
            )
    except discord.HTTPException:
        print("Discord could not display the error.")


bot.run(SETTINGS.discord_token)
