# Aluminium Rate Tracker

Source for the Aluminium Rate Tracker page: a daily MCX aluminium close, turned into
winding wire prices by gauge, with a log of supplier quotes.

## What is here

- `tracker.html` — the page. It is published as a Claude artifact and reads its data
  (daily rates, supplier quotes, settings) from that artifact's database. Opened
  directly from this repository it shows no rates, because the data is not stored here.
- `index.html` and `data.json` — a standalone copy for GitHub Pages. It shows a snapshot of
  the rates, quotes and settings held in `data.json`; it does not update by itself.
- `daily-update-task.md` — the instructions for the scheduled task that logs the
  MCX aluminium close each trading day.

## Pricing rules on the page

| Gauge | Before tax | With tax |
|---|---|---|
| Up to 32 SWG | MCX close + markup % | + tax %, rounded up to the next rupee |
| 33 SWG | MCX close + its own markup % | same |
| 38 SWG | MCX close + its own markup % | same |

The markup and tax percentages are editable on the page and saved in the artifact's
database; the values in `tracker.html` are only starting defaults.

## Learning the markup from supplier quotes

Each logged quote gives a markup over MCX (quote before tax divided by the MCX rate).
When learning is on, a gauge's markup is the average of its last 5 quotes; a gauge with
no quotes uses the markup typed in. On the Pages copy, quotes and settings are saved in
the browser on that device only.

## Buying signal

Compares the latest close with the last 30 logged days: "Buy" when it is at least 1%
below their average and in the bottom third of their range, "Don't buy extra" when at
least 1% above and in the top third. It describes past prices only and is not a forecast.
