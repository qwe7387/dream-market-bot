import re
from dataclasses import dataclass
from typing import Any

from services.api import DreamMSClient
from services.items import (
    get_close_item_names,
    get_item_name_by_id,
    learn_item,
)


@dataclass(frozen=True)
class ResolvedEconomy:
    item_name: str
    economy: dict[str, Any]


class ItemResolver:
    """
    Confirm an OCR item name against the DreamMS economy API.

    Resolution order:
    1. Trusted name already stored for the OCR item ID.
    2. OCR name exactly as read.
    3. Conservative cleanup variants.
    4. A few close names from data/items.json.

    The economy response is returned with the resolved name so the
    caller does not need to request the same data again.
    """

    def __init__(
        self,
        api_client: DreamMSClient,
    ) -> None:
        self.api_client = api_client

    async def resolve_economy(
        self,
        *,
        item_id: int | None,
        ocr_item_name: str,
        period: int = 7,
    ) -> ResolvedEconomy:
        original_name = " ".join(
            ocr_item_name.strip().split()
        )

        if not original_name:
            raise RuntimeError(
                "OCR did not return an item name."
            )

        candidates: list[str] = []

        known_name = get_item_name_by_id(
            item_id
        )

        if known_name:
            candidates.append(known_name)

        candidates.append(original_name)

        candidates.extend(
            self._cleanup_candidates(
                original_name
            )
        )

        candidates.extend(
            get_close_item_names(
                original_name,
                limit=4,
                minimum_score=0.72,
            )
        )

        candidates = self._deduplicate(
            candidates
        )

        last_not_found_error: RuntimeError | None = None

        for candidate in candidates:
            try:
                economy = (
                    await self.api_client.get_economy_average(
                        candidate,
                        period,
                    )
                )

            except RuntimeError as error:
                if self._is_not_found_error(error):
                    last_not_found_error = error
                    continue

                # Do not hide network errors, authorization failures,
                # rate-limit responses, or server failures.
                raise

            confirmed_name = str(
                economy.get("item") or candidate
            ).strip()

            if not confirmed_name:
                confirmed_name = candidate

            if confirmed_name != original_name:
                print(
                    "Corrected OCR item name using "
                    "Economy API: "
                    f"{original_name!r} -> "
                    f"{confirmed_name!r}"
                )

            learn_item(
                item_id,
                confirmed_name,
            )

            return ResolvedEconomy(
                item_name=confirmed_name,
                economy=economy,
            )

        if last_not_found_error is not None:
            raise RuntimeError(
                "The Economy API could not identify "
                f"the OCR item name {original_name!r}. "
                "Tried: "
                + ", ".join(
                    repr(candidate)
                    for candidate in candidates
                )
            ) from last_not_found_error

        raise RuntimeError(
            "The item name could not be resolved."
        )

    @staticmethod
    def _is_not_found_error(
        error: RuntimeError,
    ) -> bool:
        text = str(error).casefold()

        return (
            "status 404" in text
            or "not_found" in text
            or "not found" in text
        )

    @staticmethod
    def _deduplicate(
        candidates: list[str],
    ) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()

        for candidate in candidates:
            candidate = " ".join(
                candidate.strip().split()
            )

            if not candidate:
                continue

            key = candidate.casefold()

            if key in seen:
                continue

            seen.add(key)
            result.append(candidate)

        return result

    @staticmethod
    def _cleanup_candidates(
        value: str,
    ) -> list[str]:
        """
        Remove common OCR artifacts produced by the item icon.

        Examples:
            "f) Advanced LUK Crystal"
            "Advanced Black Crystal f)"
            "| Advanced LUK Crystal"
        """

        candidates: list[str] = []

        def add(candidate: str) -> None:
            candidate = " ".join(
                candidate.strip().split()
            )

            if candidate and candidate != value:
                candidates.append(candidate)

        # Remove punctuation/icon noise from either edge.
        add(
            re.sub(
                r"^[^A-Za-z0-9]+|"
                r"[^A-Za-z0-9%)+.'-]+$",
                "",
                value,
            )
        )

        # Remove a one-character icon artifact plus optional brackets
        # at the start, such as "f)" or "|)".
        add(
            re.sub(
                r"^[A-Za-zIl1|][)\]}>]*\s+",
                "",
                value,
            )
        )

        # Remove a one-character artifact plus optional brackets
        # at the end, such as " f)".
        add(
            re.sub(
                r"\s+[A-Za-zIl1|][)\]}>]*$",
                "",
                value,
            )
        )

        # Apply both edge rules.
        cleaned_both = re.sub(
            r"^[A-Za-zIl1|][)\]}>]*\s+",
            "",
            value,
        )
        cleaned_both = re.sub(
            r"\s+[A-Za-zIl1|][)\]}>]*$",
            "",
            cleaned_both,
        )
        add(cleaned_both)

        return candidates
