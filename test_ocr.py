import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from services.ocr import OCRService, OCRError
IMAGE_ROOT = Path("tests/images")


def find_images() -> list[Path]:
    extensions = {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
    }

    return sorted(
        path
        for path in IMAGE_ROOT.rglob("*")
        if path.is_file()
        and path.suffix.lower() in extensions
    )


def main() -> None:
    service = OCRService()

    images = find_images()

    if not images:
        print(
            "No test images were found under "
            f"{IMAGE_ROOT.resolve()}"
        )
        return

    passed = 0
    failed = 0

    for image_path in images:
        print("\n" + "=" * 70)
        print(f"Testing: {image_path}")
        print("=" * 70)

        try:
            result = service.parse_path(image_path)

            print(
                json.dumps(
                    result,
                    indent=2,
                    ensure_ascii=False,
                )
            )

            print(
                f"\nPASS: {result['item_name']} | "
                f"{len(result['listings'])} listing(s)"
            )

            passed += 1

        except OCRError as error:
            print(f"FAIL: {error}")
            failed += 1

        except Exception as error:
            print(
                f"UNEXPECTED ERROR: "
                f"{type(error).__name__}: {error}"
            )
            failed += 1

    print("\n" + "=" * 70)
    print("OCR TEST SUMMARY")
    print("=" * 70)
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Total:  {len(images)}")


if __name__ == "__main__":
    main()