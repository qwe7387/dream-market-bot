import json
from pathlib import Path
import discord
ITEMS_FILE=Path(__file__).resolve().parent.parent/'data'/'items.json'

def load_item_names() -> list[str]:
    try:
        raw=json.loads(ITEMS_FILE.read_text(encoding='utf-8'))
    except (FileNotFoundError,json.JSONDecodeError):
        return []
    names=[]
    for item in raw:
        if isinstance(item,str): names.append(item)
        elif isinstance(item,dict) and isinstance(item.get('name'),str): names.append(item['name'].strip())
    return sorted(set(filter(None,names)), key=str.casefold)

async def item_name_autocomplete(interaction: discord.Interaction, current: str) -> list[discord.app_commands.Choice[str]]:
    items=load_item_names(); q=current.casefold().strip()
    if not q: matches=items[:25]
    else:
        starts=[i for i in items if i.casefold().startswith(q)]
        contains=[i for i in items if q in i.casefold() and i not in starts]
        matches=(starts+contains)[:25]
    return [discord.app_commands.Choice(name=i,value=i) for i in matches]
