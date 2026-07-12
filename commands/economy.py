import traceback
import discord
from discord.ext import commands
from services.api import DreamMSClient
from services.autocomplete import item_name_autocomplete

async def setup(bot: commands.Bot, api_client: DreamMSClient) -> None:
    @bot.tree.command(name="economyprice", description="Show the DreamMS 7-day economy average.")
    @discord.app_commands.describe(item="Start typing an item name.")
    @discord.app_commands.autocomplete(item=item_name_autocomplete)
    async def economyprice(interaction: discord.Interaction, item: str) -> None:
        await interaction.response.defer()
        try:
            r = await api_client.get_economy_average(item, 7)
            lines = [
                f"**{r['item']}**",
                f"Period: **{r['period']}**",
                f"Average price: **{r['avg_price']:,} mesos**",
            ]
            if isinstance(r.get("items_sold"), int):
                lines.append(f"Items sold: **{r['items_sold']:,}**")
            if isinstance(r.get("sales"), int):
                lines.append(f"Sales: **{r['sales']:,}**")
            await interaction.followup.send("\n".join(lines))
        except Exception as error:
            traceback.print_exception(type(error), error, error.__traceback__)
            await interaction.followup.send(
                f"Failed to retrieve the economy price: `{error}`",
                ephemeral=True,
            )
