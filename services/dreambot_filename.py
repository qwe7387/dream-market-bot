from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from domain.models import MarketListing, MarketScan

logger = logging.getLogger(__name__)

DREAMBOT_FILENAME_PATTERN = re.compile(
    r"^p(?P<page>\d+)_(?P<seller>.+)_(?P<price>\d+)$",
    re.IGNORECASE,
)


def parse_cheapest_metadata(filename: str | None) -> tuple[str, int] | None:
    """Parse ``p<page>_<seller>_<price>.<ext>`` DreamBot filenames."""
    if not filename:
        return None
    match = DREAMBOT_FILENAME_PATTERN.fullmatch(Path(filename).stem)
    if match is None:
        return None
    seller = match.group("seller").strip()
    price_text = match.group("price")
    if not seller or not price_text:
        return None
    return seller, int(price_text)


def apply_filename_to_scan(
    scan: MarketScan,
    filename: str | None,
    *,
    trusted_quantity: int | None = None,
) -> MarketScan:
    """Return a scan whose cheapest seller/price uses trusted filename data."""
    metadata = parse_cheapest_metadata(filename)
    if metadata is None:
        return scan

    seller, price = metadata
    quantity = _safe_quantity(trusted_quantity)
    if trusted_quantity is None:
        same_seller = next(
            (row for row in scan.listings if row.seller.casefold() == seller.casefold()),
            None,
        )
        quantity = same_seller.quantity if same_seller else scan.cheapest.quantity

    reliable = MarketListing(seller=seller, price=price, quantity=quantity)
    # The DreamBot filename identifies the cheapest listing. OCR rows below
    # that trusted price are necessarily recognition artifacts.
    credible_rows = tuple(
        row for row in scan.listings
        if row.price >= price or row.seller.casefold() == seller.casefold()
    )
    updated = MarketScan(
        item_id=scan.item_id,
        item_name=scan.item_name,
        listings=credible_rows or (reliable,),
        is_stackable=scan.is_stackable,
        raw_text=scan.raw_text,
    ).with_reliable_listing(reliable)
    logger.info(
        "Used DreamBot filename for cheapest listing: seller=%r price=%s quantity=%s",
        seller,
        f"{price:,}",
        quantity,
    )
    return updated


def apply_filename_cheapest(
    fm_result: dict[str, Any],
    filename: str | None,
    *,
    trusted_quantity: int | None = None,
) -> bool:
    """Backward-compatible in-place dictionary adapter for older callers/tests."""
    original = MarketScan.from_dict(fm_result)
    updated = apply_filename_to_scan(
        original,
        filename,
        trusted_quantity=trusted_quantity,
    )
    if updated == original:
        return False
    fm_result.clear()
    fm_result.update(updated.to_dict())
    return True


def _safe_quantity(value: Any) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return 1
