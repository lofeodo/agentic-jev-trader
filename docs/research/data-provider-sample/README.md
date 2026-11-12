# Data provider sample (throwaway)

Assets for the map ticket "Create the data provider accounts and pull a sample"
(https://github.com/lofeodo/agentic-jev-trader/issues/21). This branch is never merged; the
findings live on the ticket.

- `coinbase_sample.py`: pages Coinbase Exchange public 15-minute candles (no account) from
  2015 to now and counts missing bars. Run 2026-11-12 for BTC-USD and ETH-USD.
- `twelvedata_sample.py`: pages Twelve Data 15-minute bars for one stock. Run 2026-11-12 for
  AAPL with Twelve Data's public `demo` key.
- `*_summary.json`: the output of those runs (first and last bar, bar counts, gaps per year).

The raw price files are not committed (about 50 MB, and the providers' terms on
redistribution are unread). Re-create them from the repo root with:

    conda run -n agentic-jev-trader python docs/research/data-provider-sample/coinbase_sample.py . BTC-USD ETH-USD
    conda run -n agentic-jev-trader python docs/research/data-provider-sample/twelvedata_sample.py . AAPL demo
