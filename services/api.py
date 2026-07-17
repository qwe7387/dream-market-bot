from __future__ import annotations

from typing import Any

import aiohttp

from domain.models import EconomySnapshot
from services.cache import EconomyCache


class DreamMSClient:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        *,
        cache_ttl_seconds: float = 300.0,
    ) -> None:
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.cache = EconomyCache(cache_ttl_seconds)

    async def get_economy_snapshot(
        self,
        item_name: str,
        period: int = 7,
    ) -> EconomySnapshot:
        cached = await self.cache.get(item_name, period)
        if cached is not None:
            return EconomySnapshot.from_dict(cached)

        async with self.session.get(
            f"{self.base_url}/economy",
            params={"item": item_name, "period": period},
        ) as response:
            text = await response.text()
            if response.status != 200:
                raise RuntimeError(
                    "Economy API returned status "
                    f"{response.status}: {text[:300]}"
                )
            try:
                result = await response.json(content_type=None)
            except Exception as error:
                raise RuntimeError(
                    "Economy API did not return valid JSON."
                ) from error

        if not result.get("ok"):
            raise RuntimeError(
                "Economy API returned an unsuccessful response: "
                f"{result}"
            )

        data = result.get("data", {})
        average = data.get("avgPrice")
        if not isinstance(average, (int, float)):
            raise RuntimeError("The API did not return an average price.")

        snapshot = EconomySnapshot(
            item_name=str(data.get("item", item_name)),
            period=str(data.get("period", f"{period}D")),
            average_price=int(average),
            items_sold=data.get("itemsSold"),
            sales=data.get("sales"),
        )
        normalized = snapshot.to_dict()
        await self.cache.set(item_name, period, normalized)
        if snapshot.item_name.strip():
            await self.cache.set(snapshot.item_name, period, normalized)
        return snapshot

    async def get_economy_average(
        self,
        item_name: str,
        period: int = 7,
    ) -> dict[str, Any]:
        """Backward-compatible dictionary adapter for slash commands."""
        return (await self.get_economy_snapshot(item_name, period)).to_dict()
