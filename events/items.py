import json
import re
from difflib import SequenceMatcher
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
        data = json.loads(ITEMS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if isinstance(data, dict):
        data = data.get("items", [])

    return data if isinstance(data, list) else []


def save_items(items: list[dict]) -> None:
    ITEMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    items.sort(key=lambda item: str(item.get("name", "")).casefold())
    ITEMS_FILE.write_text(
        json.dumps(items, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _normalize_name(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"[^a-z0-9%]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def learn_item(
    item_id: int | None,
    item_name: str,
) -> bool:
    """Learn a validated item without overwriting trusted ID mappings."""
    item_name = " ".join(item_name.strip().split())
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
                # Existing ID/name pairs are authoritative. Never replace a
                # trusted name with a later OCR reading.
                return False

    normalized_name = _normalize_name(item_name)

    for item in items:
        stored_name = item.get("name")
        if not isinstance(stored_name, str):
            continue

        if _normalize_name(stored_name) != normalized_name:
            continue

        # Fill a missing ID when the API-validated name is already known.
        if item_id is not None and item.get("id") is None:
            item["id"] = item_id
            save_items(items)
        return False

    items.append({"id": item_id, "name": item_name})
    save_items(items)
    print(f"Learned new API-validated item: {item_name}")
    return True


def get_item_names() -> list[str]:
    names = [
        item["name"]
        for item in load_items()
        if isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and item["name"].strip()
    ]
    return sorted(set(names), key=str.casefold)


def get_close_item_names(
    query: str,
    *,
    limit: int = 4,
    minimum_score: float = 0.72,
) -> list[str]:
    """Return conservative fuzzy candidates for exact API validation."""
    normalized_query = _normalize_name(query)
    if not normalized_query:
        return []

    scored: list[tuple[float, str]] = []

    for name in get_item_names():
        normalized_name = _normalize_name(name)
        score = SequenceMatcher(
            None,
            normalized_query,
            normalized_name,
        ).ratio()

        # Strong prefix/containment relationships are useful for icon junk at
        # the beginning or end of the OCR title.
        if (
            normalized_query in normalized_name
            or normalized_name in normalized_query
        ):
            score = max(score, 0.90)

        if score >= minimum_score:
            scored.append((score, name))

    scored.sort(key=lambda pair: (-pair[0], pair[1].casefold()))
    return [name for _, name in scored[:limit]]
