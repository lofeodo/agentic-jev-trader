"""The one renderer of a past episode and of the track record, for the LLM's lookups and for
Jev's background alike (spec appendix 5, sections 4 and 5), so the two never drift apart.

The words live in `prompts/episodes.toml`. The same episode always gives the same text: the only
moving parts are the label code gives it ("E3" for the LLM, "Episode 2" for Jev), the step it is
read at (for "3 days ago") and the asset looked at (for "same asset").

- **One line** (the LLM's search results): how long ago, which asset, the part of the day, the
  long-term trend and the volume, the 15-minute patterns, what was decided, how it ended.
- **In full**: the situation as written then, what was decided, and how it ended. For the LLM a
  past trade also shows how it was handled bar by bar; Jev's block leaves that line out and
  names no other asset. A past position review reads the same for both.
- **The track record**: for the LLM, one line per group shown, the one that fits marked; for
  Jev, one line per candle pattern and direction: the group that fits, or the count alone.

Choices the spec leaves to the build:

- A measurement not available at the time leaves its word out of the one-line setting.
- A trade stored before its best and worst, its journal or the money it put in were kept with
  its outcomes reads without them.
- An episode in full whose prices afterwards are not stored leaves its "Afterwards" line out;
  its one line leaves the price moves empty.
"""

import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from jev_trader.memory.episodes import NO_TRADE, Episode, Step
from jev_trader.memory.track_record import Group, TrackRecord
from jev_trader.sim.clock import STEPS_PER_DAY

WORDING_PATH = Path(__file__).resolve().parents[3] / "prompts" / "episodes.toml"
STEPS_PER_HOUR = 4
REDUCE_SHARES = (0.25, 0.5, 0.75)


def load_wording(path: Path = WORDING_PATH) -> dict:
    with open(path, "rb") as file:
        return tomllib.load(file)


@dataclass(frozen=True)
class Reader:
    """Who reads the text, and when: the asset looked at and the current step."""

    asset: str
    now: int
    for_jev: bool = False
    wording: dict = field(default_factory=load_wording, compare=False, repr=False)


def _round(n: float) -> int:
    return math.floor(n + 0.5)


def _dollars(n: float) -> str:
    rounded = _round(n)
    return f"{'-' if rounded < 0 else ''}${abs(rounded):,}"


def _signed_dollars(n: float) -> str:
    rounded = _round(n)
    return f"{'-' if rounded < 0 else '+'}${abs(rounded):,}"


def _signed_percent(n: float) -> str:
    """0.4 gives "+0.4%"."""
    return f"{'-' if n < 0 else '+'}{abs(n):.1f}%"


def _share(share: float) -> str:
    """0.006 gives "0.6%"."""
    return f"{100 * share:.1f}%"


def _count(forms: list[str], n: int) -> str:
    return forms[0 if n == 1 else 1].format(n=n)


def how_long_ago(steps: int, w: dict) -> str:
    """Hours under one day, days after."""
    if steps < STEPS_PER_DAY:
        return _count(w["hours_ago"], max(1, steps // STEPS_PER_HOUR))
    return _count(w["days_ago"], steps // STEPS_PER_DAY)


def _which(episode: Episode, reader: Reader) -> str:
    w = reader.wording
    if episode.asset == reader.asset:
        name = w["same_asset"]
    else:
        name = w["another_asset"] if reader.for_jev else episode.asset
    return f"{name}, {episode.asset_class}"


def _setting(episode: Episode, w: dict) -> str:
    words = [episode.part_of_day]
    if episode.trend is not None:
        words.append(w["long_term_trend"].format(way=episode.trend))
    if episode.volume is not None:
        words.append(w["volume"].format(level=episode.volume))
    return ", ".join(words)


def _price_after(episode: Episode, w: dict) -> str:
    p = episode.prices
    return w["price_after"].format(
        one=_signed_percent(100 * p.after_1_bar),
        four=_signed_percent(100 * p.after_4_bars),
        end=_signed_percent(100 * p.end_of_day),
    )


def _standing(episode: Episode, w: dict) -> str:
    s = episode.standing
    return w["standing"].format(
        direction=s.direction,
        dollars=_dollars(s.put_in),
        bars=_count(w["bars"], s.bars_open),
        profit=_signed_dollars(s.profit),
        percent=_signed_percent(s.percent),
        stop=_share(s.stop_distance),
    )


def _percent_of(ended, w: dict) -> str:
    if ended.percent is None:
        return ""
    return w["percent"].format(percent=_signed_percent(ended.percent))


def _trade_ended(episode: Episode, separator: str, w: dict) -> str:
    """How a past trade ended, counted from the decision that opened it."""
    e = episode.ended
    return w["trade_ended"].format(
        reason=w["closing_reasons"][e.reason],
        bars=_count(w["bars"], e.bars_after),
        separator=separator,
        profit=_signed_dollars(e.profit),
        percent=_percent_of(e, w),
    )


def _review_ended(episode: Episode, separator: str, w: dict) -> str:
    """How the trade ended, counted from the review."""
    e = episode.ended
    values = {
        "separator": separator,
        "profit": _signed_dollars(e.profit),
        "percent": _percent_of(e, w),
    }
    if e.closed_at_this_review:
        return w["closed_at_this_review"].format(**values)
    return w["review_ended"].format(
        reason=w["closing_reasons"][e.reason],
        bars=_count(w["bars"], e.bars_after),
        **values,
    )


def step_text(step: Step, w: dict) -> str:
    """What was done at one bar: "hold", "reduce by half (that part: +$13)", "add $2,000"."""
    if step.action == "reduce":
        words = dict(zip(REDUCE_SHARES, w["reduce_share_words"], strict=True))
        text = w["reduce"].format(
            share=words.get(step.share, f"{_round(100 * step.share)}%"),
            profit=_signed_dollars(step.profit),
        )
    elif step.action == "add":
        text = w["add"].format(amount=_dollars(step.amount))
    elif step.action in w["ended_by_code"]:
        text = w["ended_by_code"][step.action]
    else:
        text = w[step.action]
    return w["this_review"].format(entry=text) if step.this_review else text


def bar_by_bar(steps: list[Step], w: dict) -> str:
    """The trade bar by bar, runs of the same entry merged: "bars 1 to 2 hold; bar 3 close"."""
    runs: list[list] = []  # [first bar, last bar, text]
    for step in steps:
        text = step_text(step, w)
        if runs and runs[-1][2] == text and runs[-1][1] == step.bar - 1:
            runs[-1][1] = step.bar
        else:
            runs.append([step.bar, step.bar, text])
    return "; ".join(
        w["step_bar"].format(bar=first, entry=text)
        if first == last
        else w["step_bars"].format(first=first, last=last, entry=text)
        for first, last, text in runs
    )


def summary_line(episode: Episode, label: str, reader: Reader) -> str:
    """The episode in one line, as the LLM's search results list it."""
    w = reader.wording
    columns = [
        label,
        how_long_ago(reader.now - episode.step, w),
        _which(episode, reader),
        _setting(episode, w),
        ", ".join(episode.patterns) or w["no_pattern"],
    ]
    if episode.is_review:
        columns += [
            _standing(episode, w),
            step_text(episode.review, w),
            "; ".join([*_moves(episode, w), _review_ended(episode, ": ", w)]),
        ]
    elif episode.decided == NO_TRADE:
        columns += [w["no_trade"], "".join(_moves(episode, w))]
    else:
        t = episode.trade
        columns += [
            w["trade"].format(
                direction=t.direction, stop=t.stop, dollars=_dollars(t.dollars)
            ),
            _trade_ended(episode, ": ", w),
        ]
    return w["column_separator"].join(columns)


def _moves(episode: Episode, w: dict) -> list[str]:
    """Where the price went afterwards, or nothing when those prices are not stored."""
    return [] if episode.prices is None else [_price_after(episode, w)]


def _afterwards(episode: Episode, w: dict) -> list[str]:
    if episode.prices is None:
        return []
    return [w["afterwards"].format(after=_price_after(episode, w))]


def full_episode(episode: Episode, label: str, reader: Reader) -> str:
    """The episode in full: the LLM's `read_episodes`, or one block of Jev's background."""
    w = reader.wording
    lines = [
        w["full_heading"].format(
            label=label,
            ago=how_long_ago(reader.now - episode.step, w),
            which=_which(episode, reader),
        ),
        w["situation_then"].format(situation=episode.situation),
    ]
    if episode.is_review:
        s = episode.standing
        lines += [
            w["position_then"].format(
                standing=_standing(episode, w),
                best=_signed_dollars(s.best),
                worst=_signed_dollars(s.worst),
            ),
            w["review_decided"].format(decided=step_text(episode.review, w)),
            *_afterwards(episode, w),
        ]
        if episode.journal:
            lines.append(w["whole_trade"].format(steps=bar_by_bar(episode.journal, w)))
        lines.append(w["ended"].format(ended=_review_ended(episode, ", ", w)))
    elif episode.decided == NO_TRADE:
        lines += [w["decided_no_trade"], *_afterwards(episode, w)]
    else:
        t, e = episode.trade, episode.ended
        lines.append(
            w["decided_trade"].format(
                direction=t.direction,
                stop=t.stop,
                distance=_share(t.stop_distance),
                dollars=_dollars(t.dollars),
            )
        )
        if episode.journal and not reader.for_jev:
            lines.append(w["handled"].format(steps=bar_by_bar(episode.journal, w)))
        ended = w["ended"].format(ended=_trade_ended(episode, ", ", w))
        if e.best is not None and e.worst is not None:
            ended += w["best_and_worst"].format(
                best=_signed_dollars(e.best), worst=_signed_dollars(e.worst)
            )
        lines.append(ended)
    return "\n".join(lines)


def _capitalized(text: str) -> str:
    return text[0].upper() + text[1:]


def _splits(group: Group, w: dict) -> list[str]:
    """What the group is split by: "with the long-term trend", "high volume", "first hour"."""
    words = []
    if group.trend is not None:
        words.append(w["trends"][group.trend])
    if group.volume_level is not None:
        words.append(w["volume_levels"][group.volume_level])
    if group.part_of_day is not None:
        words.append(group.part_of_day)
    return words


def _group_name(group: Group, w: dict) -> str:
    words = _splits(group, w)
    return _capitalized(", ".join(words)) if words else w["all_trades"]


def _group_line(group: Group, name: str, w: dict) -> str:
    return w["group"].format(
        name=name,
        trades=group.trades,
        wins=group.made_money,
        share=f"{_round(100 * group.made_money / group.trades)}%",
        gain=_maybe(group.average_gain, w),
        loss=_maybe(group.average_loss, w),
        total=_signed_dollars(group.total_profit),
    )


def _maybe(n: float | None, w: dict) -> str:
    return w["no_gain"] if n is None else _signed_dollars(n)


def track_record(record: TrackRecord, wording: dict | None = None) -> str:
    w = wording or load_wording()
    heading = w["track_record_heading"].format(
        pattern=record.pattern,
        direction=record.direction,
        asset_class=w["asset_classes"][record.asset_class],
    )
    if not record.groups:
        return heading + "\n" + _count(w["too_few"], record.closed_trades)
    lines = [heading]
    for g in record.groups:
        line = _group_line(g, _group_name(g, w), w)
        lines.append(line + (w["fits"] if g.fits else ""))
    lines.append(w["not_shown"].format(minimum=record.minimum_sample))
    return "\n".join(lines)


def track_record_line(record: TrackRecord, wording: dict | None = None) -> str:
    """The track record in one line, as Jev reads it: the group that fits the current
    situation, named in full ("Hammer, long, stocks, with the long-term trend: 23 closed
    trades, ..."), or the count alone when no group holds the minimum sample."""
    w = wording or load_wording()
    fits = next((g for g in record.groups if g.fits), None)
    words = [
        w["line_name"].format(
            pattern=record.pattern,
            direction=record.direction,
            asset_class=w["asset_classes"][record.asset_class],
        ),
        *([] if fits is None else _splits(fits, w)),
    ]
    name = _capitalized(", ".join(words))
    if fits is None:
        too_few = _count(w["too_few"], record.closed_trades)
        return w["too_few_line"].format(name=name, too_few=too_few)
    return _group_line(fits, name, w)
