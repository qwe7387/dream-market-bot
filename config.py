import os
from dataclasses import dataclass
from dotenv import load_dotenv
load_dotenv()

@dataclass(frozen=True)
class Settings:
    discord_token: str
    game_api_key: str
    game_api_base_url: str
    dreambot_id: int
    fm_tax_percent: float
    buy_threshold_percent: float
    strong_buy_threshold_percent: float
    sell_threshold_percent: float
    strong_sell_threshold_percent: float

    @classmethod
    def from_env(cls) -> "Settings":
        discord_token = os.getenv("DISCORD_TOKEN", "").strip()
        game_api_key = os.getenv("GAME_API_KEY", "").strip()
        if not discord_token:
            raise RuntimeError("DISCORD_TOKEN is missing from the .env file.")
        if not game_api_key:
            raise RuntimeError("GAME_API_KEY is missing from the .env file.")
        settings = cls(
            discord_token=discord_token,
            game_api_key=game_api_key,
            game_api_base_url=os.getenv("GAME_API_BASE_URL", "https://dreamms.gg/api/v1").rstrip("/"),
            dreambot_id=int(os.getenv("DREAMBOT_ID", "912628058375217163")),
            fm_tax_percent=float(os.getenv("FM_TAX_PERCENT", "3")),
            buy_threshold_percent=float(os.getenv("BUY_THRESHOLD_PERCENT", "10")),
            strong_buy_threshold_percent=float(os.getenv("STRONG_BUY_THRESHOLD_PERCENT", "20")),
            sell_threshold_percent=float(os.getenv("SELL_THRESHOLD_PERCENT", "10")),
            strong_sell_threshold_percent=float(os.getenv("STRONG_SELL_THRESHOLD_PERCENT", "20")),
        )
        if not 0 <= settings.fm_tax_percent < 100:
            raise RuntimeError("FM_TAX_PERCENT must be between 0 and 100.")
        return settings

SETTINGS = Settings.from_env()
