from __future__ import annotations

import re
from pathlib import Path
from typing import Any


DREAMBOT_FILENAME_PATTERN = re.compile(
    r"^p(?P<page>\d+)_(?P<seller>.+)_(?P<price>\d+)$",
    re.IGNORECASE,
)


def parse_cheapest_metadata(
    filename: str | None,
) -> tuple[str, int] | None:
    """Parse ``p<page>_<seller>_<price>.<ext>`` DreamBot filenames."""
    if not filename:
        return None

    match = DREAMBOT_FILENAME_PATTERN.fullmatch(
        Path(filename).stem
    )

    if match is None:
        return None

    seller = match.group("seller").strip()
    price_text = match.group("price")

    if not seller or not price_text:
        return None

    return seller, int(price_text)


def apply_filename_cheapest(
    fm_result: dict[str, Any],
    filename: str | None,
    *,
    trusted_quantity: int | None = None,
) -> bool:
    """
    Replace OCR's cheapest seller and price with trusted filename data.

    OCR remains responsible for the item name, item ID, and quantity.
    Returns True when filename metadata was successfully applied.
    """
    metadata = parse_cheapest_metadata(filename)

    if metadata is None:
        return False

    filename_seller, filename_price = metadata
    listings = fm_result.get("listings")
    quantity = _safe_quantity(trusted_quantity) if trusted_quantity is not None else 1
    matching_index: int | None = None

    if isinstance(listings, list):
        for index, listing in enumerate(listings):
            if not isinstance(listing, dict):
                continue

            seller = str(listing.get("seller", "")).casefold()

            if seller != filename_seller.casefold():
                continue

            matching_index = index
            if trusted_quantity is None:
                quantity = _safe_quantity(listing.get("quantity"))
            break

    if matching_index is None:
        cheapest = fm_result.get("cheapest")

        if isinstance(cheapest, dict) and trusted_quantity is None:
            quantity = _safe_quantity(cheapest.get("quantity"))

    reliable_cheapest = {
        "seller": filename_seller,
        "price": filename_price,
        "quantity": quantity,
    }

    fm_result["cheapest"] = reliable_cheapest

    if isinstance(listings, list):
        if matching_index is None:
            listings.append(reliable_cheapest.copy())
        else:
            listings[matching_index] = reliable_cheapest.copy()

        listings.sort(key=_listing_price)

    print(
        "Used DreamBot filename for cheapest listing: "
        f"seller={filename_seller!r}, "
        f"price={filename_price:,}, "
        f"quantity={quantity}"
    )

    return True


def _safe_quantity(value: Any) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1


def _listing_price(listing: Any) -> int:
    if not isinstance(listing, dict):
        return 0

    try:
        return int(listing.get("price", 0))
    except (TypeError, ValueError):
        return 0
