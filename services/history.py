import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HISTORY_FILE = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "price_history.json"
)

MAX_RECORDS_PER_ITEM = 50


class PriceHistoryService:
    def __init__(
        self,
        history_file: Path = HISTORY_FILE,
    ) -> None:
        self.history_file = history_file
        self.lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self.lock:
            await asyncio.to_thread(
                self._initialize_sync
            )

    def _initialize_sync(self) -> None:
        self.history_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not self.history_file.exists():
            self._write_sync(
                {
                    "version": 1,
                    "items": {},
                }
            )
            return

        data = self._read_sync()

        if not isinstance(data.get("items"), dict):
            data["items"] = {}

        if "version" not in data:
            data["version"] = 1

        self._write_sync(data)

    def _read_sync(self) -> dict[str, Any]:
        if not self.history_file.exists():
            return {
                "version": 1,
                "items": {},
            }

        try:
            text = self.history_file.read_text(
                encoding="utf-8"
            )

            if not text.strip():
                return {
                    "version": 1,
                    "items": {},
                }

            data = json.loads(text)

        except json.JSONDecodeError as error:
            raise RuntimeError(
                "data/price_history.json contains invalid JSON."
            ) from error

        except OSError as error:
            raise RuntimeError(
                "Could not read data/price_history.json."
            ) from error

        if not isinstance(data, dict):
            raise RuntimeError(
                "price_history.json must contain a JSON object."
            )

        return data

    def _write_sync(
        self,
        data: dict[str, Any],
    ) -> None:
        temporary_file = self.history_file.with_suffix(
            ".json.tmp"
        )

        serialized = json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )

        try:
            temporary_file.write_text(
                serialized + "\n",
                encoding="utf-8",
            )

            os.replace(
                temporary_file,
                self.history_file,
            )

        except OSError as error:
            try:
                temporary_file.unlink(
                    missing_ok=True
                )
            except OSError:
                pass

            raise RuntimeError(
                "Could not save data/price_history.json."
            ) from error

    @staticmethod
    def _item_key(
        item_id: int | None,
        item_name: str,
    ) -> str:
        if item_id is not None:
            return str(item_id)

        return item_name.casefold().strip()

    async def add_record(
        self,
        item_id: int | None,
        item_name: str,
        listing_price: int,
        net_after_tax: int,
        average_price: int,
        seller: str,
        shop_quantity: int,
        recommendation: str,
    ) -> None:
        async with self.lock:
            await asyncio.to_thread(
                self._add_record_sync,
                item_id,
                item_name,
                listing_price,
                net_after_tax,
                average_price,
                seller,
                shop_quantity,
                recommendation,
            )

    def _add_record_sync(
        self,
        item_id: int | None,
        item_name: str,
        listing_price: int,
        net_after_tax: int,
        average_price: int,
        seller: str,
        shop_quantity: int,
        recommendation: str,
    ) -> None:
        data = self._read_sync()
        items = data.setdefault("items", {})

        item_key = self._item_key(
            item_id,
            item_name,
        )

        item_data = items.setdefault(
            item_key,
            {
                "item_id": item_id,
                "item_name": item_name,
                "records": [],
            },
        )

        item_data["item_id"] = item_id
        item_data["item_name"] = item_name

        records = item_data.setdefault(
            "records",
            [],
        )

        records.append(
            {
                "checked_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "listing_price": listing_price,
                "net_after_tax": net_after_tax,
                "average_price": average_price,
                "seller": seller,
                "shop_quantity": shop_quantity,
                "recommendation": recommendation,
            }
        )

        # Keep only the newest records.
        item_data["records"] = records[
            -MAX_RECORDS_PER_ITEM:
        ]

        self._write_sync(data)

    async def get_history(
        self,
        item_name: str,
        limit: int = 10,
    ) -> dict[str, Any] | None:
        async with self.lock:
            return await asyncio.to_thread(
                self._get_history_sync,
                item_name,
                limit,
            )

    def _get_history_sync(
        self,
        item_name: str,
        limit: int,
    ) -> dict[str, Any] | None:
        data = self._read_sync()
        items = data.get("items", {})

        if not isinstance(items, dict):
            return None

        normalized_name = item_name.casefold().strip()

        for item_data in items.values():
            if not isinstance(item_data, dict):
                continue

            stored_name = str(
                item_data.get("item_name", "")
            ).casefold().strip()

            if stored_name != normalized_name:
                continue

            records = item_data.get(
                "records",
                [],
            )

            if not isinstance(records, list):
                records = []

            return {
                "item_id": item_data.get("item_id"),
                "item_name": item_data.get(
                    "item_name",
                    item_name,
                ),
                "records": records[-limit:],
            }

        return None

    async def clear_history(
        self,
        item_name: str,
    ) -> bool:
        async with self.lock:
            return await asyncio.to_thread(
                self._clear_history_sync,
                item_name,
            )

    def _clear_history_sync(
        self,
        item_name: str,
    ) -> bool:
        data = self._read_sync()
        items = data.get("items", {})

        if not isinstance(items, dict):
            return False

        normalized_name = item_name.casefold().strip()

        matching_key = None

        for item_key, item_data in items.items():
            if not isinstance(item_data, dict):
                continue

            stored_name = str(
                item_data.get("item_name", "")
            ).casefold().strip()

            if stored_name == normalized_name:
                matching_key = item_key
                break

        if matching_key is None:
            return False

        del items[matching_key]
        self._write_sync(data)

        return True