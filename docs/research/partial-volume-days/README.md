# Partial-volume days in Twelve Data's 15-minute stock bars

Throwaway measurement for issue #48 ("Stock bars with prices but zero volume: what the first dataset does about them"). Run on 2026-11-13. Branch `research/partial-volume-days`, never merged. Only counts and dates are committed; the raw price bars are not (the data provider forbids sharing them) and live outside the repo.

The decision this supports is ADR 0008 on `main`.

## What it measures

For SPY, Apple, JPMorgan and Exxon, 2023-04-03 to 2026-10-31, on Twelve Data's free plan (`adjust=all`, 15-minute bars):

- A **bar** is one 15-minute summary of trading; its **volume** is how much was traded in it, for example 1,000 shares.
- A **session** is a stock's trading hours within one day.
- A **partial-volume day** is a day on which the provider's bars for a stock carry only part of the market's trading. The test: after bars outside the session are dropped, any bar has zero volume, or the average volume per bar is under a quarter of the median (middle value) of the stock's previous 20 sessions.

## How to rerun

Needs the `agentic-jev-trader` conda env and a Twelve Data free-plan key in an env file as `TWELVE_DATA_API_KEY`. One line, works in cmd and bash:

```
conda run -n agentic-jev-trader python docs/research/partial-volume-days/measure.py <bars_dir> <env_file> docs/research/partial-volume-days/results.md
```

`<bars_dir>` must be an existing directory outside the repo. The download is about 36 requests and takes about 6 minutes at the free plan's rate limit; bars already in `<bars_dir>` are reused. Nothing costs money.

## Choices and limits

- Early-close days (the exchange shuts at 1 pm New York time) are found from the bars themselves: a day with fewer than 20 bar times. 2023-07-03 is added by hand, because Twelve Data returns zero-volume bars up to the usual close that day. A real build uses the exchange calendar.
- The volume test starts at a stock's eleventh session, and compares with as many earlier sessions as exist, up to 20. Earlier partial-volume days are counted among them.
- "Bars not supplied" is measured against the bar times that any of the four stocks has, so a bar missing for all four at once would not show.
- Checked separately, not by this script: Twelve Data's 1-minute and 5-minute bars for JPMorgan on 2024-04-17 are also empty at the times of the twelve zero-volume 15-minute bars, with `adjust=all`. The day's 15-minute volumes add up to 2,026,516 shares against 9,017,100 in the daily bar.
- Checked separately: over 2023-09-01 to 2025-05-31 the 15-minute volumes of a session add up to a median 76% (JPMorgan) to 89% (SPY) of the daily bar's volume, and to only 31% to 55% on days such as the third Friday of March, June, September and December, so the daily bar cannot serve as the yardstick.

## Results

See `results.md`.
