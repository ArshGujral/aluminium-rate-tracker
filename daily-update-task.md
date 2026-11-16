# Daily update task

Runs at 8:40 AM IST, Tuesday to Saturday, and logs the previous trading day's close of
the near-month MCX Aluminium futures contract (standard contract, not Mini) in INR/kg.

## Sources

Dated sources (show when the price is from; these establish the trade date):

- https://dhan.co/commodity/aluminium-futures-summary/
- https://www.indmoney.com/commodities/futures/aluminium
- https://mcxlive.org/aluminium/

Confirm-only sources (used only to confirm a price a dated source already gave, and
only when fewer than two dated sources returned a usable price):

- https://groww.in/commodities/futures/mcx_aluminium
- https://www.5paisa.com/commodity-trading/mcx-aluminium-price

Not used: upstox.com and choiceindia.com headline prices, which were returned weeks
out of date.

## Rule for logging a rate

A rate is logged only if all of these hold:

1. A dated source shows the price with a trade date within the last 4 calendar days.
2. The price is between 150 and 600.
3. At least one other source agrees within Rs 1.00 for the same contract expiry, and no
   in-date dated source disagrees by more than Rs 1.00.

If the run happens while the market is open, the previous close is used with the
previous trading day's date. If no price passes, nothing is logged and the run is
recorded as failed. Prices are never estimated or carried forward.

## What it writes

- `rates/<YYYY-MM-DD>`: `{date, mcx, contract, source, loggedBy: "auto"}`, plus `low` and
  `high` (the day's low and high) when a dated source shows them for that trade date
- `status/lastRun`: `{at, ok, message}`

## Website copy

After logging, the task copies the tracker's latest 15 rates into `data.json` in this
repository, sets `updatedAt` to the day's date and pushes to `main`, which republishes the
GitHub Pages site. It changes no other file.
