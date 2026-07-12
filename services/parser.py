import re
from typing import Any
import discord

def parse_fm_embed(embed: discord.Embed) -> dict[str, Any] | None:
    if not embed.title or not embed.description:
        return None
    item_name = embed.title.strip()
    description = embed.description
    item_id_match = re.search(r"search=(\d+)", description)
    item_id = int(item_id_match.group(1)) if item_id_match else None
    listing_pattern = re.compile(r"\*\*([\d,]+)\*\*\s*\[(\d+)\]\s*・\*([^*]+)\*")
    listings=[]
    for match in listing_pattern.finditer(description):
        listings.append({'price': int(match.group(1).replace(',','')), 'quantity': int(match.group(2)), 'seller': match.group(3).strip()})
    if not listings:
        return None
    listings.sort(key=lambda x: x['price'])
    return {'item_name': item_name, 'item_id': item_id, 'listings': listings, 'cheapest': listings[0]}
