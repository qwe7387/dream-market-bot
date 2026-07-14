# Dream Market Bot

A Discord market assistant for DreamMS. It reads DreamBot `/fm` results, compares the cheapest listing with the DreamMS 7-day economy average, applies FM tax to sell calculations, and tracks two personal portfolios.

## Main features

- BUY, HOLD, SELL, STRONG BUY, and STRONG SELL recommendations
- FM tax-aware estimated proceeds
- Per-user portfolio commands
- Portfolio owners shown in market analysis
- Self-learning item autocomplete
- Observed price history stored in JSON
- Timeline graph in `/history show`

## Setup

1. Install Python.
2. Copy `.env.example` to `.env`.
3. Add your Discord token and DreamMS API key.
4. Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

5. Start the bot:

```powershell
python bot.py
```

Only `bot.py` needs to be run.

## History graph

Every completed DreamBot `/fm` result is added to `data/price_history.json`.

Use:

```text
/history show item:White Scroll entries:10
```

The response includes a graph with:

- Current FM listing
- Net value after FM tax
- 7-day economy average

The graph reflects only the `/fm` checks observed by your bot.
