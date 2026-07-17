from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Literal


AlertType = Literal["buy", "sell"]


class PriceAlertService:
    """Persistent per-user buy and sell price targets stored in JSON."""

    def __init__(self, path: str | Path = "data/watchlist.json") -> None:
        self.path = Path(path)
        self._lock = asyncio.Lock()
        self._data: dict[str, list[dict[str, Any]]] = {}

    async def initialize(self) -> None:
        async with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)

            if not self.path.exists():
                self._data = {}
                await self._save_unlocked()
                return

            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                loaded = {}

            self._data = loaded if isinstance(loaded, dict) else {}
            changed = self._migrate_unlocked()

            if changed:
                await self._save_unlocked()

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.strip().split()).casefold()

    @staticmethod
    def _validate_alert_type(alert_type: str) -> AlertType:
        normalized = alert_type.strip().casefold()

        if normalized not in {"buy", "sell"}:
            raise ValueError("Alert type must be 'buy' or 'sell'.")

        return normalized  # type: ignore[return-value]

    def _migrate_unlocked(self) -> bool:
        """Treat old alerts without a type as buy alerts."""
        changed = False

        for user_key, watches in list(self._data.items()):
            if not isinstance(watches, list):
                self._data[user_key] = []
                changed = True
                continue

            valid_watches: list[dict[str, Any]] = []

            for watch in watches:
                if not isinstance(watch, dict):
                    changed = True
                    continue

                if watch.get("alert_type") not in {"buy", "sell"}:
                    watch["alert_type"] = "buy"
                    changed = True

                valid_watches.append(watch)

            self._data[user_key] = valid_watches

        return changed

    async def add_watch(
        self,
        user_id: int,
        item_name: str,
        target_price: int,
        alert_type: AlertType,
    ) -> None:
        alert_type = self._validate_alert_type(alert_type)
        user_key = str(user_id)
        canonical = " ".join(item_name.strip().split())
        normalized = self._normalize(canonical)

        async with self._lock:
            watches = self._data.setdefault(user_key, [])

            for watch in watches:
                same_item = (
                    self._normalize(str(watch.get("item_name", "")))
                    == normalized
                )
                same_type = str(watch.get("alert_type", "buy")) == alert_type

                if same_item and same_type:
                    watch["item_name"] = canonical
                    watch["target_price"] = int(target_price)
                    watch["alert_type"] = alert_type
                    await self._save_unlocked()
                    return

            watches.append(
                {
                    "item_name": canonical,
                    "target_price": int(target_price),
                    "alert_type": alert_type,
                }
            )
            watches.sort(
                key=lambda entry: (
                    str(entry["item_name"]).casefold(),
                    str(entry.get("alert_type", "buy")),
                )
            )
            await self._save_unlocked()

    async def remove_watch(
        self,
        user_id: int,
        item_name: str,
        alert_type: AlertType | None = None,
    ) -> int:
        user_key = str(user_id)
        normalized = self._normalize(item_name)
        normalized_type = (
            self._validate_alert_type(alert_type)
            if alert_type is not None
            else None
        )

        async with self._lock:
            watches = self._data.get(user_key, [])
            kept: list[dict[str, Any]] = []
            removed_count = 0

            for watch in watches:
                same_item = (
                    self._normalize(str(watch.get("item_name", "")))
                    == normalized
                )
                watch_type = str(watch.get("alert_type", "buy"))
                same_type = (
                    normalized_type is None
                    or watch_type == normalized_type
                )

                if same_item and same_type:
                    removed_count += 1
                else:
                    kept.append(watch)

            if removed_count == 0:
                return 0

            if kept:
                self._data[user_key] = kept
            else:
                self._data.pop(user_key, None)

            await self._save_unlocked()
            return removed_count

    async def get_watches(self, user_id: int) -> list[dict[str, Any]]:
        async with self._lock:
            return [dict(watch) for watch in self._data.get(str(user_id), [])]

    async def matching_alerts(
        self,
        item_name: str,
        observed_price: int,
    ) -> list[dict[str, Any]]:
        normalized = self._normalize(item_name)
        matches: list[dict[str, Any]] = []

        async with self._lock:
            for user_key, watches in self._data.items():
                for watch in watches:
                    if self._normalize(str(watch.get("item_name", ""))) != normalized:
                        continue

                    target = int(watch.get("target_price", 0))
                    alert_type = str(watch.get("alert_type", "buy"))
                    triggered = (
                        observed_price <= target
                        if alert_type == "buy"
                        else observed_price >= target
                    )

                    if triggered:
                        matches.append(
                            {
                                "user_id": int(user_key),
                                "item_name": str(watch["item_name"]),
                                "target_price": target,
                                "alert_type": alert_type,
                            }
                        )

        return matches

    async def _save_unlocked(self) -> None:
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = json.dumps(self._data, indent=2, ensure_ascii=False)
        temporary.write_text(payload + "\n", encoding="utf-8")
        temporary.replace(self.path)
