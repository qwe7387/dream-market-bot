import asyncio
import json
import os
from pathlib import Path
from typing import Any
from core.paths import PORTFOLIO_FILE


PORTFOLIO_PATH = PORTFOLIO_FILE



class PortfolioDatabase:
    """
    JSON-backed portfolio storage.

    The public methods remain the same as the previous SQLite
    implementation, so commands/portfolio.py does not need to change.
    """

    def __init__(
        self,
        portfolio_path: Path = PORTFOLIO_PATH,
    ) -> None:
        self.portfolio_path = portfolio_path
        self.lock = asyncio.Lock()

    async def initialize(self) -> None:
        async with self.lock:
            await asyncio.to_thread(
                self._initialize_sync
            )

    def _initialize_sync(self) -> None:
        self.portfolio_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not self.portfolio_path.exists():
            self._write_data_sync(
                {
                    "version": 1,
                    "users": {},
                }
            )
            return

        # Verify that the existing file is readable.
        data = self._read_data_sync()

        if "version" not in data:
            data["version"] = 1

        if not isinstance(data.get("users"), dict):
            data["users"] = {}

        self._write_data_sync(data)

    def _read_data_sync(self) -> dict[str, Any]:
        if not self.portfolio_path.exists():
            return {
                "version": 1,
                "users": {},
            }

        try:
            text = self.portfolio_path.read_text(
                encoding="utf-8"
            )

            if not text.strip():
                return {
                    "version": 1,
                    "users": {},
                }

            data = json.loads(text)

        except json.JSONDecodeError as error:
            raise RuntimeError(
                "data/portfolio.json contains invalid JSON."
            ) from error

        except OSError as error:
            raise RuntimeError(
                "Could not read data/portfolio.json."
            ) from error

        if not isinstance(data, dict):
            raise RuntimeError(
                "data/portfolio.json must contain a JSON object."
            )

        if not isinstance(data.get("users"), dict):
            data["users"] = {}

        return data

    def _write_data_sync(
        self,
        data: dict[str, Any],
    ) -> None:
        """
        Write to a temporary file and then replace the original.

        This avoids leaving a partially written portfolio file if
        the program is interrupted during saving.
        """

        self.portfolio_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = self.portfolio_path.with_suffix(
            ".json.tmp"
        )

        serialized = json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )

        try:
            temporary_path.write_text(
                serialized + "\n",
                encoding="utf-8",
            )

            os.replace(
                temporary_path,
                self.portfolio_path,
            )

        except OSError as error:
            try:
                temporary_path.unlink(
                    missing_ok=True
                )
            except OSError:
                pass

            raise RuntimeError(
                "Could not save data/portfolio.json."
            ) from error

    @staticmethod
    def _normalize_item_name(
        item_name: str,
    ) -> str:
        normalized = " ".join(
            item_name.strip().split()
        )

        if not normalized:
            raise ValueError(
                "Item name cannot be empty."
            )

        return normalized

    @staticmethod
    def _find_item_key(
        items: dict[str, Any],
        item_name: str,
    ) -> str | None:
        target = item_name.casefold()

        for existing_name in items:
            if existing_name.casefold() == target:
                return existing_name

        return None

    async def add_item(
        self,
        discord_id: int,
        item_name: str,
        quantity: int,
        item_id: int | None = None,
    ) -> int:
        if quantity <= 0:
            raise ValueError(
                "Quantity must be greater than zero."
            )

        normalized_name = self._normalize_item_name(
            item_name
        )

        async with self.lock:
            return await asyncio.to_thread(
                self._add_item_sync,
                discord_id,
                normalized_name,
                quantity,
                item_id,
            )

    def _add_item_sync(
        self,
        discord_id: int,
        item_name: str,
        quantity: int,
        item_id: int | None,
    ) -> int:
        data = self._read_data_sync()
        users = data.setdefault("users", {})

        user_key = str(discord_id)

        user_data = users.setdefault(
            user_key,
            {
                "items": {},
            },
        )

        items = user_data.setdefault(
            "items",
            {},
        )

        existing_key = self._find_item_key(
            items,
            item_name,
        )

        if existing_key is None:
            existing_key = item_name
            items[existing_key] = {
                "item_id": item_id,
                "quantity": 0,
            }

        entry = items[existing_key]

        if not isinstance(entry, dict):
            entry = {
                "item_id": item_id,
                "quantity": 0,
            }
            items[existing_key] = entry

        current_quantity = int(
            entry.get("quantity", 0)
        )

        new_quantity = (
            current_quantity + quantity
        )

        entry["quantity"] = new_quantity

        if item_id is not None:
            entry["item_id"] = item_id
        elif "item_id" not in entry:
            entry["item_id"] = None

        self._write_data_sync(data)

        return new_quantity

    async def remove_item(
        self,
        discord_id: int,
        item_name: str,
        quantity: int,
    ) -> int:
        if quantity <= 0:
            raise ValueError(
                "Quantity must be greater than zero."
            )

        normalized_name = self._normalize_item_name(
            item_name
        )

        async with self.lock:
            return await asyncio.to_thread(
                self._remove_item_sync,
                discord_id,
                normalized_name,
                quantity,
            )

    def _remove_item_sync(
        self,
        discord_id: int,
        item_name: str,
        quantity: int,
    ) -> int:
        data = self._read_data_sync()
        users = data.get("users", {})

        user_key = str(discord_id)
        user_data = users.get(user_key)

        if not isinstance(user_data, dict):
            raise ValueError(
                "That item is not in your portfolio."
            )

        items = user_data.get("items", {})

        if not isinstance(items, dict):
            raise ValueError(
                "That item is not in your portfolio."
            )

        existing_key = self._find_item_key(
            items,
            item_name,
        )

        if existing_key is None:
            raise ValueError(
                "That item is not in your portfolio."
            )

        entry = items.get(existing_key, {})

        if not isinstance(entry, dict):
            raise ValueError(
                "That item is not in your portfolio."
            )

        current_quantity = int(
            entry.get("quantity", 0)
        )

        remaining_quantity = (
            current_quantity - quantity
        )

        if remaining_quantity <= 0:
            del items[existing_key]
            remaining_quantity = 0
        else:
            entry["quantity"] = remaining_quantity

        # Remove empty user entries.
        if not items:
            users.pop(user_key, None)

        self._write_data_sync(data)

        return remaining_quantity

    async def get_inventory(
        self,
        discord_id: int,
    ) -> list[dict[str, Any]]:
        async with self.lock:
            return await asyncio.to_thread(
                self._get_inventory_sync,
                discord_id,
            )

    def _get_inventory_sync(
        self,
        discord_id: int,
    ) -> list[dict[str, Any]]:
        data = self._read_data_sync()
        users = data.get("users", {})

        user_data = users.get(
            str(discord_id),
            {},
        )

        if not isinstance(user_data, dict):
            return []

        items = user_data.get("items", {})

        if not isinstance(items, dict):
            return []

        inventory: list[dict[str, Any]] = []

        for item_name, entry in items.items():
            if not isinstance(entry, dict):
                continue

            quantity = int(
                entry.get("quantity", 0)
            )

            if quantity <= 0:
                continue

            inventory.append(
                {
                    "item_id": entry.get(
                        "item_id"
                    ),
                    "item_name": item_name,
                    "quantity": quantity,
                }
            )

        inventory.sort(
            key=lambda entry: (
                entry["item_name"].casefold()
            )
        )

        return inventory

    async def clear_inventory(
        self,
        discord_id: int,
    ) -> int:
        async with self.lock:
            return await asyncio.to_thread(
                self._clear_inventory_sync,
                discord_id,
            )

    def _clear_inventory_sync(
        self,
        discord_id: int,
    ) -> int:
        data = self._read_data_sync()
        users = data.get("users", {})

        user_key = str(discord_id)
        user_data = users.get(user_key)

        if not isinstance(user_data, dict):
            return 0

        items = user_data.get("items", {})

        removed_rows = (
            len(items)
            if isinstance(items, dict)
            else 0
        )

        users.pop(user_key, None)

        self._write_data_sync(data)

        return removed_rows

    async def get_item_owners(
        self,
        item_name: str,
    ) -> list[dict[str, Any]]:
        normalized_name = self._normalize_item_name(
            item_name
        )

        async with self.lock:
            return await asyncio.to_thread(
                self._get_item_owners_sync,
                normalized_name,
            )

    def _get_item_owners_sync(
        self,
        item_name: str,
    ) -> list[dict[str, Any]]:
        data = self._read_data_sync()
        users = data.get("users", {})

        owners: list[dict[str, Any]] = []

        for discord_id, user_data in users.items():
            if not isinstance(user_data, dict):
                continue

            items = user_data.get("items", {})

            if not isinstance(items, dict):
                continue

            existing_key = self._find_item_key(
                items,
                item_name,
            )

            if existing_key is None:
                continue

            entry = items.get(existing_key, {})

            if not isinstance(entry, dict):
                continue

            quantity = int(
                entry.get("quantity", 0)
            )

            if quantity <= 0:
                continue

            try:
                numeric_discord_id = int(
                    discord_id
                )
            except ValueError:
                continue

            owners.append(
                {
                    "discord_id": numeric_discord_id,
                    "quantity": quantity,
                }
            )

        owners.sort(
            key=lambda owner: owner["quantity"],
            reverse=True,
        )

        return owners
