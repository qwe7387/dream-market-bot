from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Final

import cv2
import numpy as np
import pytesseract
from PIL import Image

from services.item_name import clean_ocr_item_name, resolve_local_item_name


ITEMS_FILE: Final[Path] = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "items.json"
)

PRICE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<!\d)"
    r"([0-9OIlSsB§][0-9OIlSsB§,\s.]{2,}[0-9OIlSsB§])"
    r"(?!\d)"
)

FOOTER_MARKERS: Final[tuple[str, ...]] = (
    "experimental image layout",
    "please report issues",
    "send suggestions",
)

STAT_HEADERS: Final[set[str]] = {
    "STR",
    "DEX",
    "INT",
    "LUK",
    "ATT",
    "MATT",
    "UPG",
}


class OCRError(RuntimeError):
    """Raised when a DreamBot market image cannot be parsed safely."""


@dataclass(frozen=True)
class FMListing:
    seller: str
    price: int
    quantity: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "seller": self.seller,
            "price": self.price,
            "quantity": self.quantity,
        }


@dataclass(frozen=True)
class FMResult:
    item_id: int | None
    item_name: str
    listings: list[FMListing]
    is_stackable: bool
    raw_text: str

    @property
    def cheapest(self) -> FMListing:
        if not self.listings:
            raise OCRError("No valid FM listings were parsed.")
        return min(self.listings, key=lambda listing: listing.price)

    def as_dict(self) -> dict[str, Any]:
        listings = [listing.as_dict() for listing in self.listings]
        return {
            "item_id": self.item_id,
            "item_name": self.item_name,
            "listings": listings,
            "cheapest": self.cheapest.as_dict(),
            "is_stackable": self.is_stackable,
            "raw_text": self.raw_text,
        }


class OCRService:
    """
    Parse DreamBot FM screenshots using Tesseract plus deterministic validation.

    Public methods:
        parse_path(path)
        parse_bytes(image_bytes)
        parse_array(bgr_image)
        parse_bytes_async(image_bytes)

    The returned dictionary matches the structure previously produced by
    parse_fm_embed(), allowing the rest of the bot to remain unchanged.
    """

    def __init__(
        self,
        *,
        tesseract_cmd: str | None = None,
        items_file: Path = ITEMS_FILE,
        minimum_price: int = 1_000,
        maximum_price: int = 20_000_000_000,
    ) -> None:
        configured_cmd = (
            tesseract_cmd
            or os.getenv("TESSERACT_CMD")
            or ""
        ).strip()

        if configured_cmd:
            pytesseract.pytesseract.tesseract_cmd = configured_cmd

        self.items_file = items_file
        self.minimum_price = minimum_price
        self.maximum_price = maximum_price

    async def parse_bytes_async(
        self,
        image_bytes: bytes,
    ) -> dict[str, Any]:
        """Run CPU-heavy OCR outside Discord's event loop."""
        return await asyncio.to_thread(
            self.parse_bytes,
            image_bytes,
        )

    def parse_path(
        self,
        image_path: str | Path,
    ) -> dict[str, Any]:
        path = Path(image_path)

        if not path.exists():
            raise FileNotFoundError(
                f"OCR image was not found: {path}"
            )

        image = cv2.imread(str(path), cv2.IMREAD_COLOR)

        if image is None:
            raise OCRError(
                f"OpenCV could not read the image: {path}"
            )

        return self.parse_array(image)

    def extract_first_quantity_bytes(
        self,
        image_bytes: bytes,
    ) -> int:
        """Read only the QTY cell of DreamBot's first (cheapest) row.

        DreamBot uses a stable table layout even when the item icon moves.
        The icon only affects the title, not the QTY column.
        """
        array = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(array, cv2.IMREAD_COLOR)
        if image is None:
            return 1
        return self.extract_first_quantity_array(image)

    def extract_first_quantity_array(
        self,
        image: np.ndarray,
    ) -> int:
        self._validate_image(image)
        height, width = image.shape[:2]
        values: list[int] = []

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        enlarged = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        data = pytesseract.image_to_data(
            cv2.bitwise_not(enlarged),
            config="--oem 3 --psm 6",
            output_type=pytesseract.Output.DICT,
        )

        # Anchor the crop to the detected QTY header. This handles both the
        # compact one-row layout and taller multi-row images.
        for index, text in enumerate(data.get("text", [])):
            if str(text).strip().upper() not in {"QTY", "QTY.", "QTY:"}:
                continue
            left = int(data["left"][index]) // 2
            top = int(data["top"][index]) // 2
            box_width = max(20, int(data["width"][index]) // 2)
            box_height = max(12, int(data["height"][index]) // 2)
            x1 = max(0, left - 8)
            x2 = min(width, left + max(70, box_width + 45))
            y1 = min(height, top + box_height + 8)
            y2 = min(height, y1 + 45)
            crop = image[y1:y2, x1:x2]
            for scale in (4, 5, 6):
                quantity = self._parse_quantity(
                    self._ocr_region(
                        crop,
                        config=(
                            "--oem 3 --psm 7 "
                            "-c tessedit_char_whitelist=0123456789"
                        ),
                        scale=scale,
                    )
                )
                if quantity is not None:
                    values.append(quantity)
            if values:
                break

        # Fallback for a header OCR miss: DreamBot's QTY column is stable.
        if not values:
            for y1, y2 in ((96, 140), (118, 168), (132, 178)):
                crop = image[y1:min(height, y2), int(width * 0.52):int(width * 0.70)]
                for scale in (4, 5):
                    quantity = self._parse_quantity(
                        self._ocr_region(
                            crop,
                            config=(
                                "--oem 3 --psm 7 "
                                "-c tessedit_char_whitelist=0123456789"
                            ),
                            scale=scale,
                        )
                    )
                    if quantity is not None:
                        values.append(quantity)
                if values:
                    break

        if not values:
            return 1
        return max(set(values), key=lambda value: (values.count(value), value))

    def parse_bytes(
        self,
        image_bytes: bytes,
    ) -> dict[str, Any]:
        if not image_bytes:
            raise OCRError("The DreamBot image was empty.")

        array = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(array, cv2.IMREAD_COLOR)

        if image is None:
            # Pillow fallback handles a few formats that OpenCV may reject.
            try:
                pil_image = Image.open(
                    BytesIO(image_bytes)
                ).convert("RGB")
            except Exception as error:
                raise OCRError(
                    "The DreamBot attachment was not a valid image."
                ) from error

            image = cv2.cvtColor(
                np.array(pil_image),
                cv2.COLOR_RGB2BGR,
            )

        return self.parse_array(image)

    def parse_array(
        self,
        image: np.ndarray,
    ) -> dict[str, Any]:
        self._validate_image(image)

        text_candidates = self._extract_text_candidates(image)
        parsed_candidates: list[FMResult] = []

        for raw_text in text_candidates:
            try:
                parsed_candidates.append(
                    self._parse_text(raw_text, image)
                )
            except OCRError:
                continue

        if not parsed_candidates:
            raise OCRError(
                "OCR could not find a valid item name and FM listing."
            )

        best_result = max(
            parsed_candidates,
            key=self._score_result,
        )

        # A second geometry-based pass can recover rows missed by full-page OCR.
        geometry_rows = self._parse_rows_by_price_color(
            image=image,
            is_stackable=best_result.is_stackable,
        )

        merged_rows = self._merge_listings(
            best_result.listings,
            geometry_rows,
        )

        if merged_rows:
            best_result = FMResult(
                item_id=best_result.item_id,
                item_name=best_result.item_name,
                listings=merged_rows,
                is_stackable=best_result.is_stackable,
                raw_text=best_result.raw_text,
            )

        return best_result.as_dict()

    @staticmethod
    def _validate_image(image: np.ndarray) -> None:
        if not isinstance(image, np.ndarray):
            raise TypeError("image must be a NumPy array.")

        if image.ndim != 3 or image.shape[2] != 3:
            raise OCRError(
                "Expected a three-channel BGR image."
            )

        height, width = image.shape[:2]

        if width < 250 or height < 180:
            raise OCRError(
                "The image is too small to be a DreamBot FM result."
            )

    def _extract_text_candidates(
        self,
        image: np.ndarray,
    ) -> list[str]:
        """
        Use several preprocessing variants.

        OCR failures are often local. Selecting the best deterministic parse
        from multiple passes is more reliable than trusting one OCR call.
        """
        variants = self._preprocess_variants(image)
        candidates: list[str] = []

        for processed in variants:
            text = pytesseract.image_to_string(
                processed,
                config="--oem 3 --psm 6",
            )
            text = self._normalize_text(text)

            if text and text not in candidates:
                candidates.append(text)

        return candidates

    @staticmethod
    def _preprocess_variants(
        image: np.ndarray,
    ) -> list[np.ndarray]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        enlarged = cv2.resize(
            gray,
            None,
            fx=2.5,
            fy=2.5,
            interpolation=cv2.INTER_CUBIC,
        )

        inverted = cv2.bitwise_not(enlarged)

        contrast = cv2.convertScaleAbs(
            enlarged,
            alpha=1.8,
            beta=-30,
        )
        contrast_inverted = cv2.bitwise_not(contrast)

        denoised = cv2.GaussianBlur(
            enlarged,
            (3, 3),
            0,
        )
        adaptive = cv2.adaptiveThreshold(
            denoised,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            31,
            8,
        )

        return [
            inverted,
            contrast_inverted,
            adaptive,
        ]

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized_lines: list[str] = []

        for raw_line in text.replace("\r", "").splitlines():
            line = re.sub(r"[ \t]+", " ", raw_line).strip()

            if not line:
                continue

            lowered = line.casefold()

            if any(
                marker in lowered
                for marker in FOOTER_MARKERS
            ):
                break

            normalized_lines.append(line)

        return "\n".join(normalized_lines)

    def _parse_text(
        self,
        raw_text: str,
        image: np.ndarray,
    ) -> FMResult:
        lines = [
            line.strip()
            for line in raw_text.splitlines()
            if line.strip()
        ]

        if not lines:
            raise OCRError("OCR returned no usable text.")

        header_index = self._find_table_header(lines)

        if header_index is None:
            raise OCRError(
                "Could not find the SELLER / PRICE header."
            )

        header = lines[header_index].upper()
        is_stackable = "QTY" in header

        if not is_stackable:
            has_equipment_header = (
                "PRICE" in header
                and any(
                    stat in header
                    for stat in STAT_HEADERS
                )
            )

            if not has_equipment_header:
                # Some OCR passes lose stat headings. PRICE without QTY is
                # still safely treated as equipment.
                is_stackable = False

        item_id = self._extract_item_id(
            image=image,
            lines=lines[:header_index],
        )

        item_name = self._extract_item_name(
            lines=lines[:header_index],
            item_id=item_id,
        )

        known_name = self._known_item_name(item_id)

        if known_name:
            item_name = known_name
        else:
            item_name = resolve_local_item_name(
                clean_ocr_item_name(item_name)
            )

        rows = self._parse_market_lines(
            lines=lines[header_index + 1 :],
            is_stackable=is_stackable,
        )

        if not rows:
            raise OCRError(
                "The market table did not contain valid rows."
            )

        return FMResult(
            item_id=item_id,
            item_name=item_name,
            listings=rows,
            is_stackable=is_stackable,
            raw_text=raw_text,
        )

    @staticmethod
    def _find_table_header(
        lines: list[str],
    ) -> int | None:
        for index, line in enumerate(lines):
            upper = line.upper()

            if "SELLER" in upper and "PRICE" in upper:
                return index

        return None

    def _extract_item_id(
        self,
        *,
        image: np.ndarray,
        lines: list[str],
    ) -> int | None:
        """
        Read the top-left ID area separately.

        This avoids mistaking an equipment price for an item ID.
        """
        height, width = image.shape[:2]
        id_crop = image[
            0 : max(45, int(height * 0.14)),
            0 : max(120, int(width * 0.35)),
        ]

        id_text = self._ocr_region(
            id_crop,
            config=(
                "--oem 3 --psm 6 "
                "-c tessedit_char_whitelist=0123456789"
            ),
            scale=4,
        )

        matches = re.findall(r"(?<!\d)(\d{7})(?!\d)", id_text)

        if matches:
            return int(matches[0])

        # Conservative text fallback: only consider the first few lines and
        # require the entire cleaned line to be seven digits.
        for line in lines[:3]:
            cleaned = re.sub(r"\D", "", line)

            if len(cleaned) == 7 and len(line) <= 12:
                return int(cleaned)

        return None

    @staticmethod
    def _extract_item_name(
        *,
        lines: list[str],
        item_id: int | None,
    ) -> str:
        candidates: list[str] = []

        for line in lines:
            digits_only = re.sub(r"\D", "", line)

            if (
                item_id is not None
                and digits_only == str(item_id)
            ):
                continue

            cleaned = re.sub(
                r"[^A-Za-z0-9 %'().+\-]+$",
                "",
                line,
            ).strip()

            if (
                cleaned
                and any(character.isalpha() for character in cleaned)
                and cleaned.upper() not in {"SELLER", "PRICE", "QTY"}
            ):
                candidates.append(cleaned)

        if not candidates:
            raise OCRError("Could not read the item name.")

        # The title is normally the final textual line before the table header.
        return candidates[-1]

    def _parse_market_lines(
        self,
        *,
        lines: list[str],
        is_stackable: bool,
    ) -> list[FMListing]:
        listings: list[FMListing] = []

        for line in lines:
            parsed = self._parse_market_line(
                line=line,
                is_stackable=is_stackable,
            )

            if parsed is not None:
                listings.append(parsed)

        return self._clean_listing_sequence(listings)

    def _parse_market_line(
        self,
        *,
        line: str,
        is_stackable: bool,
    ) -> FMListing | None:
        price_match = PRICE_PATTERN.search(line)

        if price_match is None:
            return None

        seller_text = line[: price_match.start()].strip()
        remainder = line[price_match.end() :].strip()

        seller = self._normalize_seller(seller_text)

        if not seller:
            return None

        price = self._parse_price(price_match.group(1))

        if price is None:
            return None

        quantity = 1

        if is_stackable:
            quantity = self._parse_quantity(remainder) or 1

        return FMListing(
            seller=seller,
            price=price,
            quantity=quantity,
        )

    @staticmethod
    def _normalize_seller(value: str) -> str:
        value = re.sub(r"\s+", "", value)
        value = re.sub(r"[^A-Za-z0-9_.\-]", "", value)

        if value.upper() in {
            "",
            "SELLER",
            "PRICE",
            "QTY",
        }:
            return ""

        return value[:32]

    def _parse_price(
        self,
        value: str,
    ) -> int | None:
        normalized = value.translate(
            str.maketrans(
                {
                    "O": "0",
                    "o": "0",
                    "I": "1",
                    "l": "1",
                    "S": "5",
                    "s": "5",
                    "B": "8",
                    "§": "5",
                }
            )
        )

        digits = re.sub(r"\D", "", normalized)

        if not digits:
            return None

        price = int(digits)

        if not (
            self.minimum_price
            <= price
            <= self.maximum_price
        ):
            return None

        return price

    @staticmethod
    def _parse_quantity(
        value: str,
    ) -> int | None:
        normalized = value.translate(
            str.maketrans(
                {
                    "O": "0",
                    "o": "0",
                    "I": "1",
                    "l": "1",
                    "S": "5",
                    "s": "5",
                }
            )
        )

        match = re.search(r"(?<!\d)(\d{1,6})(?!\d)", normalized)

        if match is None:
            return None

        quantity = int(match.group(1))

        if quantity <= 0:
            return None

        return quantity

    @staticmethod
    def _yellow_price_mask(
        image: np.ndarray,
    ) -> np.ndarray:
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

        # DreamBot prices use a saturated gold/yellow color.
        lower = np.array([10, 85, 105], dtype=np.uint8)
        upper = np.array([45, 255, 255], dtype=np.uint8)

        mask = cv2.inRange(hsv, lower, upper)

        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT,
            (3, 2),
        )

        return cv2.morphologyEx(
            mask,
            cv2.MORPH_CLOSE,
            kernel,
        )

    def _parse_rows_by_price_color(
        self,
        *,
        image: np.ndarray,
        is_stackable: bool,
    ) -> list[FMListing]:
        """
        Geometry fallback.

        Yellow text identifies price rows. Each detected row is OCRed
        independently, which often recovers rows lost by full-page OCR.
        """
        mask = self._yellow_price_mask(image)
        row_bands = self._find_row_bands(mask)

        height, width = image.shape[:2]
        listings: list[FMListing] = []

        for top, bottom in row_bands:
            y1 = max(0, top - 8)
            y2 = min(height, bottom + 9)

            row_mask = mask[y1:y2]
            _, xs = np.where(row_mask > 0)

            if xs.size == 0:
                continue

            price_left = int(xs.min())
            price_right = int(xs.max()) + 1

            # Ignore icons and title decorations.
            if not (
                int(width * 0.18)
                <= price_left
                <= int(width * 0.70)
            ):
                continue

            price_crop = image[
                y1:y2,
                max(0, price_left - 12) : min(
                    width,
                    price_right + 12,
                ),
            ]

            price_text = self._ocr_region(
                price_crop,
                config=(
                    "--oem 3 --psm 7 "
                    "-c tessedit_char_whitelist=0123456789,"
                ),
                scale=5,
            )

            price = self._parse_price(price_text)

            if price is None:
                continue

            seller_crop = image[
                y1:y2,
                4 : max(5, price_left - 10),
            ]

            seller_text = self._ocr_region(
                seller_crop,
                config="--oem 3 --psm 7",
                scale=4,
            )

            seller = self._normalize_seller(seller_text)

            if not seller:
                seller = "Unknown"

            quantity = 1

            if is_stackable:
                quantity_crop = image[
                    y1:y2,
                    min(width, price_right + 3) : min(
                        width,
                        price_right + 90,
                    ),
                ]

                quantity_text = self._ocr_region(
                    quantity_crop,
                    config=(
                        "--oem 3 --psm 7 "
                        "-c tessedit_char_whitelist=0123456789"
                    ),
                    scale=5,
                )

                quantity = (
                    self._parse_quantity(quantity_text)
                    or 1
                )

            listings.append(
                FMListing(
                    seller=seller,
                    price=price,
                    quantity=quantity,
                )
            )

        return self._clean_listing_sequence(listings)

    @staticmethod
    def _find_row_bands(
        mask: np.ndarray,
    ) -> list[tuple[int, int]]:
        projection = np.count_nonzero(mask, axis=1)
        active = projection >= 2

        groups: list[list[int]] = []
        start: int | None = None

        for y, enabled in enumerate(active):
            if enabled and start is None:
                start = y
            elif not enabled and start is not None:
                groups.append([start, y - 1])
                start = None

        if start is not None:
            groups.append([start, len(active) - 1])

        merged: list[list[int]] = []

        for group in groups:
            if (
                merged
                and group[0] - merged[-1][1] <= 5
            ):
                merged[-1][1] = group[1]
            else:
                merged.append(group)

        return [
            (top, bottom)
            for top, bottom in merged
            if bottom - top >= 4 and top > 45
        ]

    @staticmethod
    def _clean_listing_sequence(
        listings: list[FMListing],
    ) -> list[FMListing]:
        """
        Remove exact duplicates and obvious OCR outliers.

        DreamBot sorts FM listings by price. A severe backwards jump usually
        indicates that OCR dropped or substituted one or more digits.
        """
        if not listings:
            return []

        unique: list[FMListing] = []
        seen: set[tuple[str, int, int]] = set()

        for listing in listings:
            key = (
                listing.seller.casefold(),
                listing.price,
                listing.quantity,
            )

            if key in seen:
                continue

            seen.add(key)
            unique.append(listing)

        cleaned: list[FMListing] = []

        for listing in unique:
            if not cleaned:
                cleaned.append(listing)
                continue

            previous_price = cleaned[-1].price

            # Permit small OCR/order noise, but reject prices that suddenly
            # collapse to less than 40% of the previous valid row.
            if listing.price < previous_price * 0.40:
                continue

            cleaned.append(listing)

        return cleaned

    @staticmethod
    def _merge_listings(
        primary: list[FMListing],
        secondary: list[FMListing],
    ) -> list[FMListing]:
        """
        Merge full-text and geometry passes conservatively.

        Rows with the same seller and approximately the same price are treated
        as the same listing. The full-text pass has priority because it usually
        preserves quantity more accurately.
        """
        merged = list(primary)

        for candidate in secondary:
            duplicate = False

            for existing in merged:
                same_seller = (
                    existing.seller.casefold()
                    == candidate.seller.casefold()
                )

                price_difference = abs(
                    existing.price - candidate.price
                )

                close_price = price_difference <= max(
                    1_000,
                    int(existing.price * 0.002),
                )

                if same_seller and close_price:
                    duplicate = True
                    # The geometry pass OCRs the QTY column separately.
                    # Prefer its non-default quantity over a full-line parse
                    # that merged price and quantity together.
                    if existing.quantity == 1 and candidate.quantity > 1:
                        index = merged.index(existing)
                        merged[index] = FMListing(
                            seller=existing.seller,
                            price=existing.price,
                            quantity=candidate.quantity,
                        )
                    break

            if not duplicate:
                merged.append(candidate)

        merged.sort(key=lambda listing: listing.price)
        return OCRService._clean_listing_sequence(merged)

    def _known_item_name(
        self,
        item_id: int | None,
    ) -> str | None:
        if item_id is None or not self.items_file.exists():
            return None

        try:
            data = json.loads(
                self.items_file.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ):
            return None

        if isinstance(data, dict):
            data = data.get("items", [])

        if not isinstance(data, list):
            return None

        for item in data:
            if not isinstance(item, dict):
                continue

            stored_id = item.get("id")

            try:
                numeric_id = int(stored_id)
            except (
                TypeError,
                ValueError,
            ):
                continue

            if numeric_id != item_id:
                continue

            name = item.get("name")

            if isinstance(name, str) and name.strip():
                return name.strip()

        return None

    @staticmethod
    def _ocr_region(
        crop: np.ndarray,
        *,
        config: str,
        scale: int,
    ) -> str:
        if crop.size == 0:
            return ""

        gray = cv2.cvtColor(
            crop,
            cv2.COLOR_BGR2GRAY,
        )

        enlarged = cv2.resize(
            gray,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_CUBIC,
        )

        inverted = cv2.bitwise_not(enlarged)

        return pytesseract.image_to_string(
            inverted,
            config=config,
        ).strip()

    @staticmethod
    def _score_result(
        result: FMResult,
    ) -> tuple[int, int, int, int]:
        valid_sellers = sum(
            1
            for listing in result.listings
            if listing.seller != "Unknown"
        )

        monotonic_pairs = sum(
            1
            for previous, current in zip(
                result.listings,
                result.listings[1:],
            )
            if current.price >= previous.price
        )

        known_id = int(result.item_id is not None)

        return (
            len(result.listings),
            valid_sellers,
            monotonic_pairs,
            known_id,
        )
