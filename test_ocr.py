from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from services.dreambot_filename import apply_filename_cheapest
from services.item_name import clean_ocr_item_name, resolve_local_item_name
from services.ocr import OCRError, OCRService

DEFAULT_IMAGE_ROOT = Path("tests/images")
SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

@dataclass(frozen=True)
class ExpectedResult:
    item_name: str
    seller: str
    price: int
    quantity: int

@dataclass
class TestResult:
    image: str
    expected: dict[str, Any] | None
    raw: dict[str, Any] | None
    production: dict[str, Any] | None
    raw_item_ok: bool = False
    production_item_ok: bool = False
    seller_ok: bool = False
    price_ok: bool = False
    quantity_ok: bool = False
    parse_ok: bool = False
    error: str | None = None

    @property
    def all_fields_ok(self) -> bool:
        return self.parse_ok and self.production_item_ok and self.seller_ok and self.price_ok and self.quantity_ok

def norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()

def parse_expected(path: Path) -> ExpectedResult:
    stem = path.stem
    marker = "__p1__" if "__p1__" in stem else "_p1_"
    if marker not in stem:
        raise ValueError("filename must contain _p1_ or __p1__")
    item_part, rest = stem.split(marker, 1)
    separator = "__" if marker == "__p1__" else "_"
    seller, price_text, qty_text = rest.rsplit(separator, 2)
    rough_name = " ".join(item_part.replace("__", " ").replace("_", " ").split())
    # Filename-safe names can lose punctuation. Resolve them through the same
    # local catalog used by production, e.g. 60 -> 60%.
    item_name = resolve_local_item_name(rough_name, minimum_score=0.64)
    return ExpectedResult(item_name, seller, int(price_text), int(qty_text))

def find_images(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS)

def cheapest(parsed: dict[str, Any]) -> dict[str, Any]:
    value = parsed.get("cheapest")
    if not isinstance(value, dict):
        raise OCRError("OCR returned no cheapest listing")
    return value

def run_one(service: OCRService, path: Path, root: Path) -> TestResult:
    rel = str(path.relative_to(root))
    try:
        expected = parse_expected(path)
    except Exception as exc:
        return TestResult(rel, None, None, None, error=f"Invalid filename: {exc}")
    try:
        parsed = service.parse_path(path)
        raw_cheapest = cheapest(parsed)
        raw = {
            "item_name": str(parsed.get("item_name", "")).strip(),
            "seller": str(raw_cheapest.get("seller", "")).strip(),
            "price": int(raw_cheapest.get("price", 0)),
            "quantity": int(raw_cheapest.get("quantity", 1)),
        }
        # Production receives p1_<seller>_<price> from DreamBot. The test
        # filename contains extra labels, so create the real production form.
        trusted_quantity = service.extract_first_quantity_array(
            __import__("cv2").imread(str(path), __import__("cv2").IMREAD_COLOR)
        )
        apply_filename_cheapest(
            parsed,
            f"p1_{expected.seller}_{expected.price}.png",
            trusted_quantity=trusted_quantity,
        )
        parsed["item_name"] = resolve_local_item_name(clean_ocr_item_name(str(parsed.get("item_name", ""))))
        prod_cheapest = cheapest(parsed)
        production = {
            "item_name": str(parsed.get("item_name", "")).strip(),
            "seller": str(prod_cheapest.get("seller", "")).strip(),
            "price": int(prod_cheapest.get("price", 0)),
            "quantity": int(prod_cheapest.get("quantity", 1)),
        }
        return TestResult(
            image=rel, expected=asdict(expected), raw=raw, production=production, parse_ok=True,
            raw_item_ok=norm(raw["item_name"]) == norm(expected.item_name),
            production_item_ok=norm(production["item_name"]) == norm(expected.item_name),
            seller_ok=norm(production["seller"]) == norm(expected.seller),
            price_ok=production["price"] == expected.price,
            quantity_ok=production["quantity"] == expected.quantity,
        )
    except Exception as exc:
        return TestResult(rel, asdict(expected), None, None, error=f"{type(exc).__name__}: {exc}")

def pct(n: int, total: int) -> float:
    return 0.0 if not total else 100.0*n/total

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--images',type=Path,default=DEFAULT_IMAGE_ROOT)
    parser.add_argument('--report',type=Path,default=Path('tests/ocr_report.json'))
    parser.add_argument('--verbose',action='store_true')
    args=parser.parse_args()
    root=args.images.resolve(); images=find_images(root)
    if not images:
        print(f'No images found under {root}'); return 1
    service=OCRService(); results=[]
    for path in images:
        r=run_one(service,path,root); results.append(r)
        print(f"[{'PASS' if r.all_fields_ok else 'FAIL'}] {r.image}")
        if r.error: print('  '+r.error)
        elif args.verbose or not r.all_fields_ok:
            for field,ok in [('item_name',r.production_item_ok),('seller',r.seller_ok),('price',r.price_ok),('quantity',r.quantity_ok)]:
                if args.verbose or not ok:
                    print(f'  {field}: {"PASS" if ok else "FAIL"}')
                    print(f'    expected: {r.expected[field]!r}')
                    print(f'    raw:      {r.raw[field]!r}')
                    print(f'    final:    {r.production[field]!r}')
    total=len(results)
    counts={
      'Parsed':sum(r.parse_ok for r in results),
      'Raw item':sum(r.raw_item_ok for r in results),
      'Final item':sum(r.production_item_ok for r in results),
      'Seller':sum(r.seller_ok for r in results),
      'Price':sum(r.price_ok for r in results),
      'Quantity':sum(r.quantity_ok for r in results),
      'Perfect':sum(r.all_fields_ok for r in results),
    }
    print('\n'+'='*68+'\nOCR BENCHMARK SUMMARY\n'+'='*68)
    for label,n in counts.items(): print(f'{label:12} {n:>3}/{total:<3} ({pct(n,total):6.2f}%)')
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps({'total_images':total,'metrics':counts,'results':[{**asdict(r),'all_fields_ok':r.all_fields_ok} for r in results]},indent=2,ensure_ascii=False),encoding='utf-8')
    print(f'\nReport: {args.report.resolve()}')
    return 0 if counts['Perfect']==total else 1

if __name__=='__main__': sys.exit(main())
