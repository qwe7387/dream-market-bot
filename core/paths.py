from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ITEMS_FILE = DATA_DIR / "items.json"
PORTFOLIO_FILE = DATA_DIR / "portfolio.json"
PRICE_HISTORY_FILE = DATA_DIR / "price_history.json"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"
