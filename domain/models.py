from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable


@dataclass(frozen=True)
class MarketListing:
    seller: str
    price: int
    quantity: int = 1

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MarketListing":
        return cls(
            seller=str(value.get("seller", "")).strip(),
            price=int(value.get("price", 0)),
            quantity=max(1, int(value.get("quantity", 1))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "seller": self.seller,
            "price": self.price,
            "quantity": self.quantity,
        }

    def as_dict(self) -> dict[str, Any]:
        """Backward-compatible alias used by the pre-refactor OCR pipeline."""
        return self.to_dict()


@dataclass(frozen=True)
class MarketScan:
    item_id: int | None
    item_name: str
    listings: tuple[MarketListing, ...]
    is_stackable: bool = False
    raw_text: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MarketScan":
        listings = tuple(
            MarketListing.from_dict(item)
            for item in value.get("listings", [])
            if isinstance(item, dict)
        )
        if not listings and isinstance(value.get("cheapest"), dict):
            listings = (MarketListing.from_dict(value["cheapest"]),)
        return cls(
            item_id=value.get("item_id"),
            item_name=str(value.get("item_name", "")).strip(),
            listings=listings,
            is_stackable=bool(value.get("is_stackable", False)),
            raw_text=str(value.get("raw_text", "")),
        )

    @property
    def cheapest(self) -> MarketListing:
        if not self.listings:
            raise ValueError("A market scan must contain at least one listing.")
        return min(self.listings, key=lambda listing: listing.price)

    def with_item_name(self, item_name: str) -> "MarketScan":
        return replace(self, item_name=item_name)

    def with_reliable_listing(self, listing: MarketListing) -> "MarketScan":
        replaced = False
        updated: list[MarketListing] = []
        for current in self.listings:
            if not replaced and current.seller.casefold() == listing.seller.casefold():
                updated.append(listing)
                replaced = True
            else:
                updated.append(current)
        if not replaced:
            updated.append(listing)
        return replace(self, listings=tuple(sorted(updated, key=lambda row: row.price)))

    def to_dict(self) -> dict[str, Any]:
        listings = [listing.to_dict() for listing in self.listings]
        return {
            "item_id": self.item_id,
            "item_name": self.item_name,
            "listings": listings,
            "cheapest": self.cheapest.to_dict(),
            "is_stackable": self.is_stackable,
            "raw_text": self.raw_text,
        }

    def as_dict(self) -> dict[str, Any]:
        """Backward-compatible alias used by existing OCR callers and tests."""
        return self.to_dict()


@dataclass(frozen=True)
class EconomySnapshot:
    item_name: str
    period: str
    average_price: int
    items_sold: int | None = None
    sales: int | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EconomySnapshot":
        return cls(
            item_name=str(value.get("item", "")).strip(),
            period=str(value.get("period", "7D")),
            average_price=int(value.get("avg_price", 0)),
            items_sold=value.get("items_sold"),
            sales=value.get("sales"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "item": self.item_name,
            "period": self.period,
            "avg_price": self.average_price,
            "items_sold": self.items_sold,
            "sales": self.sales,
        }


@dataclass(frozen=True)
class ResolvedEconomy:
    item_name: str
    economy: EconomySnapshot


@dataclass(frozen=True)
class MarketAnalysis:
    recommendation: str
    emoji: str
    description: str
    current_listing_price: int
    net_after_tax: int
    tax_amount: int
    average_price: int
    buy_difference_percent: float
    sell_difference_percent: float


@dataclass(frozen=True)
class OwnerPosition:
    discord_id: int
    display_name: str
    quantity: int
    estimated_net_proceeds: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "discord_id": self.discord_id,
            "display_name": self.display_name,
            "quantity": self.quantity,
            "estimated_net_proceeds": self.estimated_net_proceeds,
        }


def owners_to_dicts(owners: Iterable[OwnerPosition]) -> list[dict[str, Any]]:
    return [owner.to_dict() for owner in owners]
