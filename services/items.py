import json
import logging
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from core.paths import ITEMS_FILE

logger = logging.getLogger(__name__)




def load_items() -> list[dict[str, Any]]:
    if not ITEMS_FILE.exists():
        return []

    try:
        data = json.loads(
            ITEMS_FILE.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return []

    if isinstance(data, dict):
        data = data.get("items", [])

    if not isinstance(data, list):
        return []

    return [
        item
        for item in data
        if isinstance(item, dict)
    ]


def save_items(
    items: list[dict[str, Any]],
) -> None:
    ITEMS_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    items.sort(
        key=lambda item: str(
            item.get("name", "")
        ).casefold()
    )

    ITEMS_FILE.write_text(
        json.dumps(
            items,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def normalize_item_name(
    value: str,
) -> str:
    value = value.casefold()
    value = re.sub(
        r"[^a-z0-9%]+",
        " ",
        value,
    )
    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def get_item_name_by_id(
    item_id: int | None,
) -> str | None:
    if item_id is None:
        return None

    for item in load_items():
        try:
            stored_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue

        if stored_id != item_id:
            continue

        name = item.get("name")

        if isinstance(name, str) and name.strip():
            return name.strip()

    return None


def get_item_names() -> list[str]:
    names: list[str] = []

    for item in load_items():
        name = item.get("name")

        if isinstance(name, str) and name.strip():
            names.append(name.strip())

    return sorted(
        set(names),
        key=str.casefold,
    )


def get_close_item_names(
    query: str,
    *,
    limit: int = 4,
    minimum_score: float = 0.72,
) -> list[str]:
    normalized_query = normalize_item_name(query)

    if not normalized_query:
        return []

    scored: list[tuple[float, str]] = []

    for name in get_item_names():
        normalized_name = normalize_item_name(name)

        score = SequenceMatcher(
            None,
            normalized_query,
            normalized_name,
        ).ratio()

        # Strongly favor names where one normalized string contains
        # the other. This is useful for icon artifacts such as:
        # "f Advanced LUK Crystal".
        if (
            normalized_query in normalized_name
            or normalized_name in normalized_query
        ):
            score = max(score, 0.94)

        if score >= minimum_score:
            scored.append((score, name))

    scored.sort(
        key=lambda pair: (
            -pair[0],
            pair[1].casefold(),
        )
    )

    return [
        name
        for _, name in scored[:limit]
    ]


def learn_item(
    item_id: int | None,
    item_name: str,
) -> bool:
    """
    Save an API-confirmed item.

    Existing ID/name mappings are treated as trusted and are never
    overwritten by a later OCR reading.
    """

    item_name = " ".join(
        item_name.strip().split()
    )

    if not item_name:
        return False

    items = load_items()

    if item_id is not None:
        for item in items:
            try:
                stored_id = int(item.get("id"))
            except (TypeError, ValueError):
                continue

            if stored_id == item_id:
                return False

    normalized_name = normalize_item_name(
        item_name
    )

    for item in items:
        stored_name = item.get("name")

        if not isinstance(stored_name, str):
            continue

        if (
            normalize_item_name(stored_name)
            != normalized_name
        ):
            continue

        if (
            item_id is not None
            and item.get("id") is None
        ):
            item["id"] = item_id
            save_items(items)

        return False

    items.append(
        {
            "id": item_id,
            "name": item_name,
        }
    )

    save_items(items)

    logger.info("Learned new API-confirmed item: %s", item_name)

    return True
