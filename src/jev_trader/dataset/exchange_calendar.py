"""The New York Stock Exchange's published calendar: which days it opens, and its hours.

It comes from the `exchange_calendars` library (calendar `XNYS`), used as it comes. The calendar
is published years ahead, so using it is not looking into the future. A full session runs 09:30
to 16:00 New York time; a half day closes at 13:00. Times here are UTC.
"""

from datetime import date, timedelta
from functools import cache

from jev_trader.dataset.measurements import Session

EXCHANGE = "XNYS"


@cache
def _calendar(start_year: int):
    import exchange_calendars

    return exchange_calendars.get_calendar(EXCHANGE, start=f"{start_year}-01-01")


def _session(cal, label) -> tuple[date, Session]:
    opens = cal.session_open(label).to_pydatetime()
    closes = cal.session_close(label).to_pydatetime()
    return label.date(), Session(open=opens, close=closes)


def stock_sessions(first_day: date, last_day: date) -> list[tuple[date, Session]]:
    """Every session from `first_day` to `last_day`, oldest first."""
    cal = _calendar(first_day.year - 1)
    return [_session(cal, s) for s in cal.sessions_in_range(first_day, last_day)]


def sessions_before(first_day: date, count: int) -> list[tuple[date, Session]]:
    """The `count` sessions just before `first_day`, oldest first."""
    # Twice as many calendar days as sessions, plus a month, always holds `count` sessions.
    reach_back = first_day - timedelta(days=2 * count + 30)
    cal = _calendar(reach_back.year - 1)
    earlier = cal.sessions_in_range(reach_back, first_day)
    earlier = [s for s in earlier if s.date() < first_day][-count:]
    return [_session(cal, s) for s in earlier]
