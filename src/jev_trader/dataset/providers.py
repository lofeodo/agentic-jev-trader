"""The two data providers bars are downloaded from (spec appendix 2, section 1).

- Stocks: Twelve Data's free Basic plan, 15-minute bars of regular hours, corrected for splits
  and dividends (`adjust=all`), so a change in price is always a real gain or loss to a holder.
  Its times are New York time and are turned into UTC here. The plan allows 8 requests a minute
  and 800 a day; one request returns up to 5,000 bars.
- Crypto: Binance's public monthly files (`data.binance.vision`), no account. Bitcoin is priced
  in USDT, a token worth $1. Bar times are in milliseconds until the end of 2024 and in
  microseconds from 2025.

Each asset class sits behind its own interface (`StockProvider`, `CryptoProvider`), so a dataset can
later be built from another provider. Nothing here is ever written to the repo.
"""

import csv
import io
import time
import zipfile
from collections import deque
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from jev_trader.dataset.bars import Bar

NEW_YORK = ZoneInfo("America/New_York")


class ProviderError(Exception):
    """A provider refused or failed a request; the message is the provider's."""


class UnknownTicker(ProviderError):
    """A typed ticker the provider does not know."""


class StockProvider(Protocol):
    def stock_bars(self, ticker: str, first_day: date, last_day: date) -> list[Bar]:
        """Adjusted 15-minute bars from `first_day` to `last_day` (New York dates), in UTC."""


class CryptoProvider(Protocol):
    def crypto_bars(self, symbol: str, first_day: date, last_day: date) -> list[Bar]:
        """15-minute bars from `first_day` to `last_day` (UTC dates)."""


# --- Twelve Data ------------------------------------------------------------------------------

TWELVE_DATA_URL = "https://api.twelvedata.com/time_series"
TWELVE_DATA_MOST_BARS = 5000
# The plan's daily allowance. A build counts its own requests only: it cannot see requests made
# earlier the same day, so it stops before passing 800 itself (the first dataset needs about 40).
TWELVE_DATA_DAILY_REQUESTS = 800
# About 3,300 regular-hours bars: well under the 5,000 one request returns.
TWELVE_DATA_WINDOW = timedelta(days=182)


def read_twelve_data_reply(reply: dict) -> list[Bar]:
    """The bars in one Twelve Data `time_series` reply, in UTC and time order."""
    if reply.get("status") == "error":
        message = str(reply.get("message", reply))
        if "No data is available" in message:
            return []
        if reply.get("code") == 404 or "not found" in message:
            raise UnknownTicker(f"Twelve Data does not know this ticker: {message}")
        raise ProviderError(f"Twelve Data: {message}")
    bars = [
        Bar(
            start=datetime.fromisoformat(v["datetime"])
            .replace(tzinfo=NEW_YORK)
            .astimezone(UTC),
            open=float(v["open"]),
            high=float(v["high"]),
            low=float(v["low"]),
            close=float(v["close"]),
            volume=float(v["volume"]),
        )
        for v in reply.get("values", [])
    ]
    return sorted(bars, key=lambda b: b.start)


class Pacer:
    """Waits before a request so no more than `per_minute` go out in any 60 seconds."""

    def __init__(
        self,
        per_minute: int,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.per_minute = per_minute
        self.sleep = sleep
        self.clock = clock
        self.sent: deque[float] = deque()

    def wait(self) -> None:
        now = self.clock()
        while self.sent and now - self.sent[0] >= 60:
            self.sent.popleft()
        if len(self.sent) >= self.per_minute:
            self.sleep(60 - (now - self.sent[0]) + 1)
            self.sent.popleft()
        self.sent.append(self.clock())


class TwelveData:
    """Twelve Data's free plan: adjusted 15-minute stock bars, paced to 8 requests a minute
    and stopped before 800 in one build."""

    def __init__(
        self, api_key: str, get: Callable | None = None, pacer: Pacer | None = None
    ):
        import httpx

        self.api_key = api_key
        self.get = get or (
            lambda url, params: httpx.get(url, params=params, timeout=60).json()
        )
        self.pacer = pacer or Pacer(per_minute=8)
        self.requests = 0

    def stock_bars(self, ticker: str, first_day: date, last_day: date) -> list[Bar]:
        bars: dict[datetime, Bar] = {}
        start = first_day
        while start <= last_day:
            end = min(start + TWELVE_DATA_WINDOW, last_day + timedelta(days=1))
            if self.requests >= TWELVE_DATA_DAILY_REQUESTS:
                raise ProviderError(
                    f"this build has used Twelve Data's {TWELVE_DATA_DAILY_REQUESTS} requests "
                    "a day; build again tomorrow"
                )
            self.pacer.wait()
            self.requests += 1
            reply = self.get(
                TWELVE_DATA_URL,
                {
                    "symbol": ticker,
                    "interval": "15min",
                    "start_date": f"{start} 00:00:00",
                    "end_date": f"{end} 00:00:00",
                    "timezone": "America/New_York",
                    "adjust": "all",
                    "order": "asc",
                    "outputsize": TWELVE_DATA_MOST_BARS,
                    "apikey": self.api_key,
                },
            )
            window = read_twelve_data_reply(reply)
            if len(window) >= TWELVE_DATA_MOST_BARS:
                raise ProviderError(
                    f"Twelve Data cut its reply for {ticker} at {TWELVE_DATA_MOST_BARS} bars "
                    f"from {start}: some bars would be lost"
                )
            bars.update((b.start, b) for b in window)
            start = end
        if not bars:
            raise UnknownTicker(
                f"Twelve Data has no bars for {ticker} from {first_day} to {last_day}"
            )
        return sorted(bars.values(), key=lambda b: b.start)


# --- Binance ----------------------------------------------------------------------------------

BINANCE_URL = "https://data.binance.vision/data/spot"
MICROSECONDS_FROM = 10**14  # a time this large is in microseconds, not milliseconds


def read_binance_zip(data: bytes) -> list[Bar]:
    """The bars in one Binance kline zip file (one CSV inside), in UTC and time order."""
    bars = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            with z.open(name) as f:
                for row in csv.reader(io.TextIOWrapper(f, encoding="utf-8")):
                    if not row or not row[0].strip().isdigit():
                        continue  # a header line
                    stamp = int(row[0])
                    seconds = (
                        stamp / 1_000_000
                        if stamp >= MICROSECONDS_FROM
                        else stamp / 1000
                    )
                    bars.append(
                        Bar(
                            start=datetime.fromtimestamp(seconds, tz=UTC),
                            open=float(row[1]),
                            high=float(row[2]),
                            low=float(row[3]),
                            close=float(row[4]),
                            volume=float(row[5]),
                        )
                    )
    return sorted(bars, key=lambda b: b.start)


def _months(first_day: date, last_day: date) -> list[date]:
    months, m = [], first_day.replace(day=1)
    while m <= last_day:
        months.append(m)
        m = (m + timedelta(days=32)).replace(day=1)
    return months


class BinanceFiles:
    """Binance's public 15-minute kline files: one per month. The range's last month may have
    no monthly file yet; its days' files are read instead. An earlier month with no file has
    no bars (one request, not thirty, for a symbol Binance does not know)."""

    def __init__(self, get: Callable[[str], bytes | None] | None = None):
        self.get = get or _download

    def crypto_bars(self, symbol: str, first_day: date, last_day: date) -> list[Bar]:
        bars: dict[datetime, Bar] = {}
        months = _months(first_day, last_day)
        for month in months:
            tag = f"{month:%Y-%m}"
            data = self.get(
                f"{BINANCE_URL}/monthly/klines/{symbol}/15m/{symbol}-15m-{tag}.zip"
            )
            if data is not None:
                files = [data]
            elif month == months[-1]:
                files = self._days_of(symbol, month, last_day)
            else:
                files = []
            for f in files:
                bars.update((b.start, b) for b in read_binance_zip(f))
        if not bars:
            raise UnknownTicker(
                f"Binance has no files for {symbol} from {first_day} to {last_day}"
            )
        lo = datetime.combine(first_day, datetime.min.time(), tzinfo=UTC)
        hi = datetime.combine(
            last_day + timedelta(days=1), datetime.min.time(), tzinfo=UTC
        )
        return sorted(
            (b for b in bars.values() if lo <= b.start < hi), key=lambda b: b.start
        )

    def _days_of(self, symbol: str, month: date, last_day: date) -> list[bytes]:
        files, d = [], month
        while d.month == month.month and d <= last_day:
            data = self.get(
                f"{BINANCE_URL}/daily/klines/{symbol}/15m/{symbol}-15m-{d}.zip"
            )
            if data is not None:
                files.append(data)
            d += timedelta(days=1)
        return files


def _download(url: str) -> bytes | None:
    """The file at `url`, or None if there is none (404)."""
    import httpx

    response = httpx.get(url, timeout=120, follow_redirects=True)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.content
