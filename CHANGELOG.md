# Changelog

## v1.1.1

- Replaced `/watch` with explicit `/watchbuy` and `/watchsell` commands.
- Grouped active alerts into buy and sell sections in `/watchlist`.
- Updated `/unwatch` so it can remove a buy alert, sell alert, or all alerts for an item.
- Existing alerts without a type are automatically migrated to buy alerts.
- Improved triggered alert embeds to clearly show buy and sell conditions.

## v2.4.0

- Added a timeline graph to `/history show`.
- The graph compares the observed FM listing, net price after tax, and 7-day economy average.
- Removed duplicate item-loading logic from autocomplete.
- Fixed item learning so parsing failures cannot crash the listener.
- Cleaned and reformatted the application entry point.

## OCR v2 benchmark update

- Added icon-noise cleanup on either side of item titles.
- Added local item-catalog resolution with token-aware similarity scoring.
- Added dedicated first-row QTY extraction anchored to the QTY header.
- DreamBot filename remains authoritative for cheapest seller and price.
- OCR benchmark now reports raw item OCR separately from final production output.
- Added sample item names discovered from the regression screenshots.
