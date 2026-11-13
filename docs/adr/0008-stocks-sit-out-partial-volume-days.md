# A stock sits out its partial-volume days

The agent reads volume (how much was traded in a bar, a 15-minute summary of trading; for example 1,000 shares) to judge how much a price move counts: a rise on heavy trading is taken more seriously than one on light trading. Stock bars come from Twelve Data's free plan, and on some days its bars for a stock carry only part of the market's trading, though their prices look sound. Either some bars arrive with a volume of zero (JPMorgan and Exxon on about ten days of April 2024), or every bar carries 10% or less of the usual volume (all four stocks on 25 March 2025, among others). On such a day the agent would see a market that looks asleep when it was not, and might pass on a $2,000 trade it would otherwise take. The volume cannot be recovered: Twelve Data's 1-minute and 5-minute bars are empty at the same times, while its daily bar shows a normal day. So a day like this is a partial-volume day, and every bar the stock has that day counts as a missing bar: the agent does not look at the stock, and the other assets carry on. We chose this because no data is safer than data that is quietly wrong, and because it reuses the rules missing bars already have.

A stock's day is a partial-volume day when, after bars outside trading hours are dropped, either any of its bars has zero volume, or its average volume per bar is under a quarter of the middle value of that stock's previous 20 days. The average is per bar so that a short trading day compares fairly. Measured on the first dataset's range (3 April 2023 to 31 October 2026, 899 trading days), the second test has a wide margin: every day it catches sits at 10% or less of usual, and the quietest day it lets through at 29%.

The rule covers stocks only. Bitcoin's bars come from Binance, where a zero-volume bar means the exchange was down for those minutes, so those stay missing one bar at a time.

## Considered Options

- **Switch to a provider with full-market volume.** Massive (formerly Polygon) documents volume from every US exchange for US$29 a month; Databento would probably be free with its new-account credit, but its prices are not corrected for splits and dividends, so that correction would be ours to write. Sign-up from Canada was confirmed for neither, and a switch reopens the licence and access checks already done for Twelve Data. Too much for a flaw on 1 or 2 days in 100.
- **Trade on prices, with volume marked unknown.** Keeps the day, but every measurement that uses volume would need an "unknown" case, and the feature vector would need a made-up value in its place.
- **Change nothing.** Zero-volume bars would stay missing one at a time, leaving half-empty days whose remaining bars still understate volume, and the days with no zero-volume bar would pass unnoticed.
- **Keep the 2022 start and raise the limit on missing bars.** In 2022 the stocks have thousands of zero-volume bars, many as whole days. No planned run uses dates before December 2023, so the dataset now starts on 3 April 2023.

## Consequences

- On the first dataset the rule removes 6 to 17 days per stock out of 899: SPY 8, Apple 6, JPMorgan 16, Exxon 17. The build-up year loses 11 days of JPMorgan and 12 of Exxon out of 249. In the test period each stock loses one day in each 30-day market, and JPMorgan two in the falling one. Runs with and without memory read the same bars, so the comparison between them stays fair.
- Bars outside trading hours have to be dropped first, using the exchange calendar. On a day the market closes early, Twelve Data still returns bars up to the usual close, with zero volume: 3 July 2023 has eleven or twelve of them per stock after the 1 pm close, and would otherwise count as a partial-volume day.
- A position already open in the stock keeps its last known price through the day, and its stop price can only trigger once bars return.
- A build no longer checks one limit on missing bars but two: at most 0.5% of an asset's bars not supplied by the provider, and at most 3% of a stock's days as partial-volume days. The quality report lists every partial-volume day.
- The test looks at earlier days only, so a long run of partial-volume days with no zero-volume bar would lower what counts as usual and could hide its own later days. None has been seen.
- The quarter and the 20 days are settings. Changing them, or the rule, means building a new dataset, since a published dataset never changes, and then repeating the build-up run, about $10.
- ADR 0004 gives early April 2022 as the first dataset's first tradable step. With the new start it is 3 July 2023.
