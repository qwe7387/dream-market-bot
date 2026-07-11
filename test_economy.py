import json
import os

import requests
from dotenv import load_dotenv


load_dotenv()

API_KEY = os.getenv("GAME_API_KEY")
API_BASE_URL = os.getenv("GAME_API_BASE_URL")


if not API_KEY:
    raise RuntimeError("GAME_API_KEY is missing from the .env file.")

if not API_BASE_URL:
    raise RuntimeError("GAME_API_BASE_URL is missing from the .env file.")


item_name = "White Scroll"

response = requests.get(
    f"{API_BASE_URL.rstrip('/')}/economy",
    headers={
        "X-API-Key": API_KEY,
        "Accept": "application/json",
    },
    params={
        "item": item_name,
        "period": 7,
    },
    timeout=20,
)

print(f"Status code: {response.status_code}")

try:
    data = response.json()
except requests.JSONDecodeError:
    print("The API did not return valid JSON:")
    print(response.text)
    raise SystemExit(1)

print(json.dumps(data, indent=2, ensure_ascii=False))