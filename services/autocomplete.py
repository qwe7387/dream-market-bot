import discord

from services.items import get_item_names


async def item_name_autocomplete(
    interaction: discord.Interaction,
    current: str,
) -> list[discord.app_commands.Choice[str]]:
    item_names = get_item_names()
    search_text = current.casefold().strip()

    if not search_text:
        matches = item_names[:25]
    else:
        starts_with = [
            item_name
            for item_name in item_names
            if item_name.casefold().startswith(search_text)
        ]

        contains = [
            item_name
            for item_name in item_names
            if search_text in item_name.casefold()
            and item_name not in starts_with
        ]

        matches = (starts_with + contains)[:25]

    return [
        discord.app_commands.Choice(
            name=item_name,
            value=item_name,
        )
        for item_name in matches
    ]
