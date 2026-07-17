# Dream Market Bot

A Discord market assistant for DreamMS. It reads DreamBot `/fm` results, compares the cheapest listing with the DreamMS 7-day economy average, applies a 2% FM tax to sell calculations, and tracks personal portfolios and observed prices.

## Main features

- OCR v2 for DreamBot `/fm` screenshots
- BUY, HOLD, SELL, STRONG BUY, and STRONG SELL recommendations
- 2% FM tax-aware estimated proceeds
- 5-minute Economy API cache; every screenshot is still parsed fresh
- Price alerts checked whenever an `/fm` result is processed
- Per-user portfolio commands and owners in market analysis
- Self-learning item autocomplete
- Observed price history and timeline graph

## Setup

1. Install Python.
2. Copy `.env.example` to `.env`.
3. Add your Discord token, DreamMS API key, and Tesseract path.
4. Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

5. Start the bot:

```powershell
python bot.py
```

Only `bot.py` needs to be run.

## Main commands

- `/hello` - status, version, cache, and feature information
- `/thresholds` - recommendation thresholds and FM tax
- `/economyprice` - retrieve an item's 7-day Economy API average
- `/watchbuy item target_price` - alert when the cheapest FM listing is at or below the target
- `/watchsell item target_price` - alert when the cheapest FM listing is at or above the target
- `/watchlist` - show your active buy and sell alerts
- `/unwatch item [alert_type]` - remove one type or all alerts for an item
- `/portfolio ...` - manage your item portfolio
- `/history show` - display observed market history

Price alerts are stored in `data/watchlist.json`. Buy alerts trigger when the cheapest scanned listing is at or below the target. Sell alerts trigger when it is at or above the target. Existing alerts created with the old `/watch` command are automatically migrated as buy alerts.

## Economy cache

Set the TTL in `.env`:

```env
ECONOMY_CACHE_MINUTES=5
```

Only the Economy API response is cached. Item name, seller, FM price, and quantity are read from each new DreamBot result. Set the value to `0` to disable caching.

## History graph

Every completed DreamBot `/fm` result is added to `data/price_history.json`.

```text
/history show item:White Scroll entries:10
```

The response includes current FM listing, net value after FM tax, and the 7-day economy average.

## Project structure

```text
core/                 Runtime settings, paths, and logging setup
domain/               Typed data objects shared across the application
commands/             Discord slash-command adapters
events/               Discord event listeners
services/             OCR, API, cache, resolver, persistence, and market pipeline
ui/                   Discord embeds and interactive views
tests/images/         OCR regression image set
tests/unit/           Fast unit tests for models, filename parsing, cache, market logic, and resolver helpers
```

The DreamBot flow is intentionally separated:

```text
Discord message -> result parser -> MarketScan -> resolver -> EconomySnapshot
-> market analysis -> history -> Discord UI
```

Discord-specific code stays in `events/`, while `services/market_pipeline.py` handles the application workflow without Discord dependencies. Dictionary conversion happens only at compatibility and UI boundaries.

## Tests

Run the fast unit test suite:

```powershell
python -m unittest discover -s tests/unit -v
```

Run the OCR regression benchmark:

```powershell
python test_ocr.py
```
