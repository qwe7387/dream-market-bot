import json
from pathlib import Path

ITEMS_FILE = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "items.json"
)


def load_items() -> list[dict]:
    if not ITEMS_FILE.exists():
        return []

    try:
        with open(
            ITEMS_FILE,
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

            if isinstance(data, list):
                return data

    except Exception:
        pass

    return []


def save_items(
    items: list[dict],
) -> None:
    items.sort(
        key=lambda item: item["name"].lower()
    )

    with open(
        ITEMS_FILE,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            items,
            file,
            indent=2,
            ensure_ascii=False,
        )


def learn_item(
    item_id: int | None,
    item_name: str,
) -> bool:
    """
    Returns True if a new item was learned.
    """

    if not item_name:
        return False

    items = load_items()

    # First try matching by ID
    if item_id is not None:
        for item in items:
            if item.get("id") == item_id:
                if item["name"] != item_name:
                    item["name"] = item_name
                    save_items(items)
                return False

    # Then by name
    for item in items:
        if (
            item["name"].casefold()
            == item_name.casefold()
        ):
            return False

    items.append(
        {
            "id": item_id,
            "name": item_name,
        }
    )

    save_items(items)

    print(
        f"Learned new item: {item_name}"
    )

    return True


def get_item_names() -> list[str]:
    return sorted(
        [
            item["name"]
            for item in load_items()
        ],
        key=str.casefold,
    )