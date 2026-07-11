import asyncio
import os
import re
import traceback
from typing import Any

import aiohttp
import discord
from discord.ext import commands
from dotenv import load_dotenv


# ============================================================
# Configuration
# ============================================================

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GAME_API_KEY = os.getenv("GAME_API_KEY")

GAME_API_BASE_URL = os.getenv(
    "GAME_API_BASE_URL",
    "https://dreamms.gg/api/v1",
)

BUY_DISCOUNT_PERCENT = float(
    os.getenv("BUY_DISCOUNT_PERCENT", "10")
)

# DreamBot's Discord user ID.
DREAMBOT_ID = 912628058375217163


if not DISCORD_TOKEN:
    raise RuntimeError(
        "DISCORD_TOKEN is missing from the .env file."
    )

if not GAME_API_KEY:
    raise RuntimeError(
        "GAME_API_KEY is missing from the .env file."
    )


# ============================================================
# Item names used for /economyprice autocomplete
# ============================================================

ITEM_NAMES = [
    "White Scroll",
    "Chaos Scroll 60%",
    "Clean Slate Scroll 20%",
    "Onyx Apple",
    "Advanced Dark Crystal",
    "Advanced Black Crystal",
    "Advanced Diamond",
    "Advanced Garnet",
    "Advanced Sapphire",
    "Advanced Topaz",
    "Advanced Emerald",
    "Advanced Aquamarine",
    "Advanced Amethyst",
    "Advanced Opal",
    "Advanced Steel",
    "Advanced Mithril",
    "Advanced Adamantium",
    "Advanced Bronze",
    "Advanced Silver",
    "Advanced Orihalcon",
]


# ============================================================
# Bot class
# ============================================================

class DreamMarketBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix="!",
            intents=intents,
        )

        self.http_session: aiohttp.ClientSession | None = None

        # Prevent the same DreamBot result from being processed twice.
        self.processed_message_ids: set[int] = set()

    async def setup_hook(self) -> None:
        self.http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                "X-API-Key": GAME_API_KEY,
                "Accept": "application/json",
            },
        )

        synced_commands = await self.tree.sync()

        print(
            f"Synced {len(synced_commands)} "
            "slash command(s)."
        )

        for command in synced_commands:
            print(f"Registered command: /{command.name}")

    async def close(self) -> None:
        if self.http_session is not None:
            await self.http_session.close()

        await super().close()


bot = DreamMarketBot()


# ============================================================
# Parse DreamBot /fm results
# ============================================================

def parse_fm_embed(
    embed: discord.Embed,
) -> dict[str, Any] | None:
    if not embed.title or not embed.description:
        return None

    item_name = embed.title.strip()
    description = embed.description

    item_id_match = re.search(
        r"search=(\d+)",
        description,
    )

    item_id = (
        int(item_id_match.group(1))
        if item_id_match
        else None
    )

    # Example:
    # :coin: **40,444,444** [9]・*Grimhilde*
    listing_pattern = re.compile(
        r"\*\*([\d,]+)\*\*"
        r"\s*\[(\d+)\]"
        r"\s*・\*([^*]+)\*"
    )

    listings: list[dict[str, Any]] = []

    for match in listing_pattern.finditer(description):
        price = int(
            match.group(1).replace(",", "")
        )

        quantity = int(match.group(2))
        seller = match.group(3).strip()

        listings.append(
            {
                "price": price,
                "quantity": quantity,
                "seller": seller,
            }
        )

    if not listings:
        return None

    listings.sort(
        key=lambda listing: listing["price"]
    )

    return {
        "item_name": item_name,
        "item_id": item_id,
        "listings": listings,
        "cheapest": listings[0],
    }


# ============================================================
# DreamMS economy API
# ============================================================

async def get_economy_average(
    item_name: str,
    period: int = 7,
) -> dict[str, Any]:
    if bot.http_session is None:
        raise RuntimeError(
            "HTTP session has not been initialized."
        )

    url = (
        f"{GAME_API_BASE_URL.rstrip('/')}/economy"
    )

    params = {
        "item": item_name,
        "period": period,
    }

    async with bot.http_session.get(
        url,
        params=params,
    ) as response:
        response_text = await response.text()

        if response.status != 200:
            raise RuntimeError(
                f"Economy API returned status "
                f"{response.status}: "
                f"{response_text[:300]}"
            )

        try:
            result = await response.json(
                content_type=None
            )
        except Exception as error:
            raise RuntimeError(
                "Economy API did not return valid JSON."
            ) from error

    if not result.get("ok"):
        raise RuntimeError(
            "Economy API returned an unsuccessful "
            f"response: {result}"
        )

    data = result.get("data", {})
    average_price = data.get("avgPrice")

    if not isinstance(
        average_price,
        (int, float),
    ):
        raise RuntimeError(
            "The API did not return an average price."
        )

    return {
        "item": data.get("item", item_name),
        "period": data.get(
            "period",
            f"{period}D",
        ),
        "avg_price": int(average_price),
        "items_sold": data.get("itemsSold"),
        "sales": data.get("sales"),
    }


# ============================================================
# Price comparison
# ============================================================

def calculate_discount_percent(
    current_price: int,
    average_price: int,
) -> float:
    return (
        (average_price - current_price)
        / average_price
    ) * 100


def create_comparison_embed(
    fm_result: dict[str, Any],
    economy_record: dict[str, Any],
) -> discord.Embed:
    cheapest = fm_result["cheapest"]

    current_price = cheapest["price"]
    average_price = economy_record["avg_price"]

    discount = calculate_discount_percent(
        current_price=current_price,
        average_price=average_price,
    )

    should_buy = (
        discount >= BUY_DISCOUNT_PERCENT
    )

    if should_buy:
        title = f"BUY: {fm_result['item_name']}"
        description = (
            "The cheapest listing is below your "
            "configured buy threshold."
        )

    elif discount > 0:
        title = (
            f"Below Average: "
            f"{fm_result['item_name']}"
        )
        description = (
            "The listing is below the 7-day average, "
            "but not cheap enough for a BUY alert."
        )

    else:
        title = (
            f"Do Not Buy: "
            f"{fm_result['item_name']}"
        )
        description = (
            "The cheapest listing is equal to or "
            "above the 7-day economy average."
        )

    embed = discord.Embed(
        title=title,
        description=description,
    )

    embed.add_field(
        name="Current cheapest listing",
        value=f"{current_price:,} mesos",
        inline=False,
    )

    embed.add_field(
        name="7-day economy average",
        value=f"{average_price:,} mesos",
        inline=False,
    )

    if discount >= 0:
        difference_text = (
            f"{discount:.2f}% below average"
        )
    else:
        difference_text = (
            f"{abs(discount):.2f}% above average"
        )

    embed.add_field(
        name="Difference",
        value=difference_text,
        inline=True,
    )

    embed.add_field(
        name="Buy threshold",
        value=(
            f"{BUY_DISCOUNT_PERCENT:.1f}% below"
        ),
        inline=True,
    )

    embed.add_field(
        name="Quantity",
        value=f"{cheapest['quantity']:,}",
        inline=True,
    )

    embed.add_field(
        name="Seller",
        value=cheapest["seller"],
        inline=True,
    )

    items_sold = economy_record.get(
        "items_sold"
    )

    if isinstance(items_sold, int):
        embed.add_field(
            name="Items sold in 7 days",
            value=f"{items_sold:,}",
            inline=True,
        )

    sales = economy_record.get("sales")

    if isinstance(sales, int):
        embed.add_field(
            name="Sales in 7 days",
            value=f"{sales:,}",
            inline=True,
        )

    item_id = fm_result.get("item_id")

    if item_id:
        embed.set_footer(
            text=f"Item ID: {item_id}"
        )

    return embed


# ============================================================
# Process DreamBot message
# ============================================================

async def process_dreambot_message(
    message: discord.Message,
) -> None:
    if message.id in bot.processed_message_ids:
        return

    if message.author.id != DREAMBOT_ID:
        return

    if not message.embeds:
        return

    fm_result = parse_fm_embed(
        message.embeds[0]
    )

    if fm_result is None:
        print(
            "DreamBot message was received, "
            "but FM listings could not be parsed."
        )
        return

    bot.processed_message_ids.add(message.id)

    # Prevent the set from growing indefinitely.
    if len(bot.processed_message_ids) > 500:
        bot.processed_message_ids.clear()
        bot.processed_message_ids.add(message.id)

    cheapest = fm_result["cheapest"]

    print("\nFM result parsed successfully")
    print(f"Item: {fm_result['item_name']}")
    print(f"Item ID: {fm_result['item_id']}")
    print(
        f"Lowest price: "
        f"{cheapest['price']:,}"
    )
    print(
        f"Quantity: "
        f"{cheapest['quantity']}"
    )
    print(f"Seller: {cheapest['seller']}")

    try:
        economy_record = await get_economy_average(
            item_name=fm_result["item_name"],
            period=7,
        )

        print(
            f"7-day economy average: "
            f"{economy_record['avg_price']:,}"
        )

        result_embed = create_comparison_embed(
            fm_result=fm_result,
            economy_record=economy_record,
        )

        await message.channel.send(
            embed=result_embed
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

        await message.channel.send(
            f"I found the FM price for "
            f"**{fm_result['item_name']}**, but "
            f"the economy comparison failed:\n"
            f"`{error}`"
        )


# ============================================================
# Item autocomplete
# ============================================================

async def item_name_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[discord.app_commands.Choice[str]]:
    search_text = current.casefold().strip()

    if not search_text:
        matches = ITEM_NAMES[:25]

    else:
        # Items beginning with the entered text appear first.
        starts_with = [
            item_name
            for item_name in ITEM_NAMES
            if item_name.casefold().startswith(
                search_text
            )
        ]

        # Then include items containing the text elsewhere.
        contains = [
            item_name
            for item_name in ITEM_NAMES
            if search_text in item_name.casefold()
            and item_name not in starts_with
        ]

        matches = (
            starts_with + contains
        )[:25]

    return [
        discord.app_commands.Choice(
            name=item_name,
            value=item_name,
        )
        for item_name in matches
    ]


# ============================================================
# Discord events
# ============================================================

@bot.event
async def on_ready() -> None:
    print(f"Bot is online as {bot.user}")
    print(f"Bot ID: {bot.user.id}")

    if not bot.guilds:
        print(
            "The bot is not connected to any server."
        )

    for guild in bot.guilds:
        print(
            f"Connected server: {guild.name} "
            f"| Server ID: {guild.id}"
        )


@bot.event
async def on_message(
    message: discord.Message,
) -> None:
    if bot.user is not None:
        if message.author.id == bot.user.id:
            return

    if message.author.id == DREAMBOT_ID:
        if message.embeds:
            await process_dreambot_message(
                message
            )

    await bot.process_commands(message)


@bot.event
async def on_raw_message_edit(
    payload: discord.RawMessageUpdateEvent,
) -> None:
    author_data = payload.data.get("author")

    if not author_data:
        return

    try:
        author_id = int(
            author_data.get("id", 0)
        )
    except (TypeError, ValueError):
        return

    if author_id != DREAMBOT_ID:
        return

    channel = bot.get_channel(
        payload.channel_id
    )

    if channel is None:
        try:
            channel = await bot.fetch_channel(
                payload.channel_id
            )
        except discord.HTTPException as error:
            print(
                f"Could not fetch channel: {error}"
            )
            return

    if not hasattr(channel, "fetch_message"):
        return

    # Allow DreamBot time to finish editing its loading response.
    await asyncio.sleep(0.5)

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
            "The bot does not have permission to "
            "read the edited DreamBot message."
        )
        return

    except discord.HTTPException as error:
        print(
            f"Could not fetch edited DreamBot "
            f"message: {error}"
        )
        return

    await process_dreambot_message(message)


# ============================================================
# Slash commands
# ============================================================

@bot.tree.command(
    name="hello",
    description="Check whether the bot is working.",
)
async def hello(
    interaction: discord.Interaction,
) -> None:
    await interaction.response.send_message(
        "Hello! The market bot is working."
    )


@bot.tree.command(
    name="economyprice",
    description="Show the DreamMS 7-day economy average.",
)
@discord.app_commands.describe(
    item="Start typing an item name."
)
@discord.app_commands.autocomplete(
    item=item_name_autocomplete
)
async def economyprice(
    interaction: discord.Interaction,
    item: str,
) -> None:
    await interaction.response.defer()

    try:
        economy_record = await get_economy_average(
            item_name=item,
            period=7,
        )

        items_sold = economy_record.get(
            "items_sold"
        )

        sales = economy_record.get("sales")

        lines = [
            f"**{economy_record['item']}**",
            f"Period: **{economy_record['period']}**",
            (
                f"Average price: "
                f"**{economy_record['avg_price']:,} mesos**"
            ),
        ]

        if isinstance(items_sold, int):
            lines.append(
                f"Items sold: **{items_sold:,}**"
            )

        if isinstance(sales, int):
            lines.append(
                f"Sales: **{sales:,}**"
            )

        await interaction.followup.send(
            "\n".join(lines)
        )

    except Exception as error:
        print(
            "The /economyprice command failed:"
        )

        traceback.print_exception(
            type(error),
            error,
            error.__traceback__,
        )

        await interaction.followup.send(
            f"Failed to retrieve the economy price: "
            f"`{error}`",
            ephemeral=True,
        )


@bot.tree.command(
    name="threshold",
    description="Show the current BUY threshold.",
)
async def threshold(
    interaction: discord.Interaction,
) -> None:
    await interaction.response.send_message(
        f"The bot recommends BUY when the current "
        f"price is at least "
        f"**{BUY_DISCOUNT_PERCENT:.1f}% below "
        f"the 7-day economy average**."
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
        print(
            "Discord could not display the error."
        )


# ============================================================
# Start bot
# ============================================================

bot.run(DISCORD_TOKEN)