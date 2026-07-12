# Dream Market Bot

Reads DreamBot `/fm` results and compares the cheapest listing with the DreamMS 7-day economy average.
SELL recommendations use net proceeds after the configured FM tax.

## Run

```powershell
python bot.py
```

Only `bot.py` needs to be started.

## Setup

1. Copy `.env.example` to `.env`.
2. Add your Discord token and DreamMS API key.
3. Install dependencies with `python -m pip install -r requirements.txt`.
4. Run `python bot.py`.
