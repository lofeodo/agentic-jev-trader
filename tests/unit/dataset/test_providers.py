"""Reading the two data providers' answers into bars (spec appendix 2, section 1). Made-up data."""

import io
import zipfile
from datetime import UTC, datetime

import pytest

from jev_trader.dataset.bars import Bar
from jev_trader.dataset.providers import (
    ProviderError,
    UnknownTicker,
    read_binance_zip,
    read_twelve_data_reply,
)


def test_twelve_data_bars_are_read_in_new_york_time_and_turned_into_utc():
    reply = {
        "meta": {
            "symbol": "XYZ",
            "interval": "15min",
            "exchange_timezone": "America/New_York",
        },
        "values": [
            # Summer: New York is 4 hours behind UTC. Winter: 5 hours.
            {
                "datetime": "2024-07-01 09:30:00",
                "open": "10.5",
                "high": "11",
                "low": "10",
                "close": "10.75",
                "volume": "1200",
            },
            {
                "datetime": "2024-01-02 15:45:00",
                "open": "9",
                "high": "9.5",
                "low": "8.5",
                "close": "9.25",
                "volume": "0",
            },
        ],
        "status": "ok",
    }
    assert read_twelve_data_reply(reply) == [
        Bar(datetime(2024, 1, 2, 20, 45, tzinfo=UTC), 9.0, 9.5, 8.5, 9.25, 0.0),
        Bar(datetime(2024, 7, 1, 13, 30, tzinfo=UTC), 10.5, 11.0, 10.0, 10.75, 1200.0),
    ]


def test_twelve_data_reply_with_no_data_for_the_dates_is_no_bars():
    reply = {
        "code": 400,
        "message": "No data is available on the specified dates. Try setting different start/end dates.",
        "status": "error",
    }
    assert read_twelve_data_reply(reply) == []


def test_twelve_data_says_when_a_typed_ticker_does_not_exist():
    reply = {"code": 404, "message": "**symbol** not found: NOPE.", "status": "error"}
    with pytest.raises(UnknownTicker):
        read_twelve_data_reply(reply)


def test_any_other_twelve_data_error_stops_with_its_message():
    reply = {
        "code": 429,
        "message": "You have run out of API credits.",
        "status": "error",
    }
    with pytest.raises(ProviderError, match="run out of API credits"):
        read_twelve_data_reply(reply)


def zip_of(lines: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("BTCUSDT-15m-2024-12.csv", "\n".join(lines) + "\n")
    return buffer.getvalue()


def test_binance_files_are_read_with_times_in_milliseconds_or_microseconds():
    # 2024-12-31 23:45 UTC in milliseconds, 2025-01-01 00:00 UTC in microseconds.
    ms = "1735688700000,93000.1,93100,92900,93050.5,12.5,1735689599999,0,10,0,0,0"
    us = "1735689600000000,93050.5,93200,93000,93150,0,1735690499999999,0,0,0,0,0"
    assert read_binance_zip(zip_of([ms, us])) == [
        Bar(
            datetime(2024, 12, 31, 23, 45, tzinfo=UTC),
            93000.1,
            93100.0,
            92900.0,
            93050.5,
            12.5,
        ),
        Bar(
            datetime(2025, 1, 1, 0, 0, tzinfo=UTC),
            93050.5,
            93200.0,
            93000.0,
            93150.0,
            0.0,
        ),
    ]


def test_a_binance_file_with_a_header_line_is_read_too():
    header = (
        "open_time,open,high,low,close,volume,close_time,quote_volume,count,a,b,ignore"
    )
    row = "1735688700000,1,2,0.5,1.5,3,1735689599999,0,1,0,0,0"
    assert len(read_binance_zip(zip_of([header, row]))) == 1


def test_a_symbol_binance_does_not_know_fails_after_one_request_per_month():
    asked = []

    def nothing(url):
        asked.append(url)

    from datetime import date

    from jev_trader.dataset.providers import BinanceFiles

    with pytest.raises(UnknownTicker):
        BinanceFiles(get=nothing).crypto_bars(
            "NOPEUSDT", date(2023, 1, 1), date(2023, 6, 3)
        )
    # Six monthly files, then the last month's three daily files.
    assert len(asked) == 6 + 3


def test_twelve_data_stops_before_800_requests_in_one_build():
    from datetime import date

    from jev_trader.dataset.providers import TwelveData

    def never(url, params):
        raise AssertionError("no request should go out")

    provider = TwelveData("key", get=never)
    provider.requests = 800
    with pytest.raises(ProviderError, match="800 requests"):
        provider.stock_bars("XYZ", date(2023, 1, 2), date(2023, 1, 6))
