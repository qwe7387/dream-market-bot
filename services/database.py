import asyncio
import sqlite3
from pathlib import Path
from typing import Any


DATABASE_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "portfolio.db"
)


class PortfolioDatabase:
    def __init__(
        self,
        database_path: Path = DATABASE_PATH,
    ) -> None:
        self.database_path = database_path
        self.lock = asyncio.Lock()

    async def initialize(self) -> None:
        await asyncio.to_thread(
            self._initialize_sync
        )

    def _initialize_sync(self) -> None:
        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with sqlite3.connect(
            self.database_path
        ) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS inventory (
                    discord_id INTEGER NOT NULL,
                    item_id INTEGER,
                    item_name TEXT NOT NULL,
                    quantity INTEGER NOT NULL
                        CHECK(quantity >= 0),
                    PRIMARY KEY (
                        discord_id,
                        item_name
                    )
                )
                """
            )

            connection.commit()

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

        async with self.lock:
            return await asyncio.to_thread(
                self._add_item_sync,
                discord_id,
                item_name,
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
        normalized_name = item_name.strip()

        with sqlite3.connect(
            self.database_path
        ) as connection:
            connection.execute(
                """
                INSERT INTO inventory (
                    discord_id,
                    item_id,
                    item_name,
                    quantity
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(discord_id, item_name)
                DO UPDATE SET
                    quantity = quantity + excluded.quantity,
                    item_id = COALESCE(
                        excluded.item_id,
                        inventory.item_id
                    )
                """,
                (
                    discord_id,
                    item_id,
                    normalized_name,
                    quantity,
                ),
            )

            connection.commit()

            row = connection.execute(
                """
                SELECT quantity
                FROM inventory
                WHERE discord_id = ?
                  AND item_name = ?
                """,
                (
                    discord_id,
                    normalized_name,
                ),
            ).fetchone()

        return int(row[0])

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

        async with self.lock:
            return await asyncio.to_thread(
                self._remove_item_sync,
                discord_id,
                item_name,
                quantity,
            )

    def _remove_item_sync(
        self,
        discord_id: int,
        item_name: str,
        quantity: int,
    ) -> int:
        normalized_name = item_name.strip()

        with sqlite3.connect(
            self.database_path
        ) as connection:
            row = connection.execute(
                """
                SELECT quantity
                FROM inventory
                WHERE discord_id = ?
                  AND item_name = ?
                """,
                (
                    discord_id,
                    normalized_name,
                ),
            ).fetchone()

            if row is None:
                raise ValueError(
                    "That item is not in your portfolio."
                )

            current_quantity = int(row[0])
            remaining_quantity = (
                current_quantity - quantity
            )

            if remaining_quantity <= 0:
                connection.execute(
                    """
                    DELETE FROM inventory
                    WHERE discord_id = ?
                      AND item_name = ?
                    """,
                    (
                        discord_id,
                        normalized_name,
                    ),
                )

                remaining_quantity = 0
            else:
                connection.execute(
                    """
                    UPDATE inventory
                    SET quantity = ?
                    WHERE discord_id = ?
                      AND item_name = ?
                    """,
                    (
                        remaining_quantity,
                        discord_id,
                        normalized_name,
                    ),
                )

            connection.commit()

        return remaining_quantity

    async def get_inventory(
        self,
        discord_id: int,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._get_inventory_sync,
            discord_id,
        )

    def _get_inventory_sync(
        self,
        discord_id: int,
    ) -> list[dict[str, Any]]:
        with sqlite3.connect(
            self.database_path
        ) as connection:
            connection.row_factory = sqlite3.Row

            rows = connection.execute(
                """
                SELECT
                    item_id,
                    item_name,
                    quantity
                FROM inventory
                WHERE discord_id = ?
                ORDER BY item_name COLLATE NOCASE
                """,
                (discord_id,),
            ).fetchall()

        return [
            {
                "item_id": row["item_id"],
                "item_name": row["item_name"],
                "quantity": row["quantity"],
            }
            for row in rows
        ]

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
        with sqlite3.connect(
            self.database_path
        ) as connection:
            cursor = connection.execute(
                """
                DELETE FROM inventory
                WHERE discord_id = ?
                """,
                (discord_id,),
            )

            connection.commit()
            return cursor.rowcount

    async def get_item_owners(
        self,
        item_name: str,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._get_item_owners_sync,
            item_name,
        )

    def _get_item_owners_sync(
        self,
        item_name: str,
    ) -> list[dict[str, Any]]:
        with sqlite3.connect(
            self.database_path
        ) as connection:
            connection.row_factory = sqlite3.Row

            rows = connection.execute(
                """
                SELECT
                    discord_id,
                    quantity
                FROM inventory
                WHERE item_name = ? COLLATE NOCASE
                  AND quantity > 0
                ORDER BY quantity DESC
                """,
                (item_name.strip(),),
            ).fetchall()

        return [
            {
                "discord_id": row["discord_id"],
                "quantity": row["quantity"],
            }
            for row in rows
        ]