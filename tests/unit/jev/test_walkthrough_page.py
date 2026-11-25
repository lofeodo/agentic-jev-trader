"""The Jev walkthrough page matches what is sent (spec appendix 10, section 18).

The page's own code writes the screen's, the full evaluation's, the position screen's and the
position review's text from its made-up story. This test runs that code with Node and compares
it, word for word, with what our code writes from the same story. The full evaluation is compared
with memory (tab 2, and the "nothing to show" cases A and B) and without (case C); the review as
the agent without memory sends it, since position reviews with memory are not built yet.
"""

import json
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from jev_trader.broker import Direction, load_stop_price_settings, load_trading_costs
from jev_trader.jev.full_evaluation import candidate_trades
from jev_trader.jev.reading import (
    MEMORIES_RELEVANT,
    AccountView,
    AssetView,
    MemorySections,
    PastEpisodes,
    PositionLine,
    PositionView,
    Reading,
)
from jev_trader.memory.episodes import Ended, Episode, Prices, Trade
from jev_trader.memory.track_record import Group, TrackRecord
from jev_trader.risk import load_risk_profile

PAGE = Path(__file__).parents[3] / "docs" / "jev-reading-walkthrough.html"
PRINT_THE_STORY = """
console.log(JSON.stringify({
  opening: taskSection(),
  background: screenBackground(ASSET, ACCOUNT, PLAYBOOK),
  question: QUESTIONS.screen(ASSET),
  asset: ASSET, account: ACCOUNT, playbook: PLAYBOOK,
  trades: candidateTrades(ASSET),
  pickQuestion: QUESTIONS.pick(ASSET),
  pickOptions: pickOptions(ASSET, ACCOUNT),
  withoutMemory: fullEvaluationBackground(ASSET, ACCOUNT, PLAYBOOK, null),
  selected: SELECTED,
  withMemory: fullEvaluationBackground(ASSET, ACCOUNT, PLAYBOOK, MEMORY),
  sizeWithMemory: fullEvaluationBackground(ASSET, ACCOUNT, PLAYBOOK, MEMORY, candidateTrades(ASSET)[0]),
  noneSelected: fullEvaluationBackground(ASSET, ACCOUNT, PLAYBOOK, { trackRecord: TRACK_RECORD, episodes: [] }),
  noneYet: fullEvaluationBackground(ASSET, ACCOUNT, PLAYBOOK, { trackRecord: THIN_TRACK_RECORD, episodes: [], holdsNoEpisodes: true }),
  memoriesRelevant: QUESTIONS.memoriesRelevant,
  sizeBackground: fullEvaluationBackground(ASSET, ACCOUNT, PLAYBOOK, null, candidateTrades(ASSET)[0]),
  sizeQuestion: QUESTIONS.size,
  sizeOptions: sizeOptions(ACCOUNT, candidateTrades(ASSET)[0]),
  ratingQuestion: QUESTIONS.rating,
  ratingLevels: RATING_LEVELS,
  shuffledCopies: SETTINGS.shuffledCopies,
  later: ASSET_LATER, accountLater: ACCOUNT_LATER, position: POSITION,
  positionFacts: positionFacts(POSITION, ASSET_LATER),
  positionScreenBackground: positionScreenBackground(ASSET_LATER, ACCOUNT_LATER, PLAYBOOK, POSITION),
  positionScreenQuestion: QUESTIONS.positionScreen(ASSET_LATER),
  reviewBackground: positionReviewBackground(ASSET_LATER, ACCOUNT_LATER, PLAYBOOK, POSITION, null),
  actionQuestion: QUESTIONS.action(ASSET_LATER),
  actionOptions: actionOptions(POSITION, ASSET_LATER, ACCOUNT_LATER),
  thesisIntact: QUESTIONS.thesisIntact,
  reduceBackground: positionReviewBackground(ASSET_LATER, ACCOUNT_LATER, PLAYBOOK, POSITION, null,
    "Reduce: close part of the position and keep the rest."),
  reduceQuestion: QUESTIONS.reduce,
  reduceOptions: reduceOptions(POSITION, ASSET_LATER),
  addBackground: positionReviewBackground(ASSET_LATER, ACCOUNT_LATER, PLAYBOOK, POSITION, null,
    "Add: put more money into the position, in the same direction and with the same stop price."),
  addQuestion: QUESTIONS.add,
  addOptions: (() => { const facts = positionFacts(POSITION, ASSET_LATER);
    return sizeOptions(ACCOUNT_LATER, POSITION, { stopShare: facts.stopDistance, riskUsed: facts.riskUsed, held: facts.worth }); })(),
  endOfSession: positionSection({ ...POSITION, barsAgo: 22, since: ["bars 1 to 21 hold"] }, ASSET_LATER, true),
}));
"""


@pytest.fixture(scope="module")
def story(tmp_path_factory):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is not installed")
    html = PAGE.read_text(encoding="utf-8")
    portable = html.split("<script>")[1].split("PAGE (throwaway shell")[0]
    script = tmp_path_factory.mktemp("page") / "story.js"
    script.write_text(portable + "*/" + PRINT_THE_STORY, encoding="utf-8")
    done = subprocess.run(
        [node, str(script)],
        capture_output=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(done.stdout)


def views(story):
    """The page's made-up asset, account and playbook, as our code takes them."""
    a, acc = story["asset"], story["account"]
    worth = sum(p["worth"] for p in acc["positions"])
    account = AccountView(
        value=acc["cash"] + worth,
        cash=acc["cash"],
        loan=acc["loan"],
        exposure=worth,
        positions=tuple(
            PositionLine(
                asset=p["asset"],
                asset_class=p["assetClass"],
                direction=p["direction"],
                worth=p["worth"],
                bars_ago=p["barsAgo"],
                profit=p["profit"],
                percent=p["percent"],
            )
            for p in acc["positions"]
        ),
    )
    asset = AssetView(
        asset_id=a["id"],
        asset_class=a["assetClass"],
        price=a["price"],
        typical_move=a["typicalMove"],
        situation=a["situation"],
        patterns=tuple(a["patternsAll"]),
    )
    playbook = {n: (e["lean"], e["shape"]) for n, e in story["playbook"].items()}
    return asset, account, playbook


def reading():
    return Reading(load_trading_costs(), load_risk_profile())


def our_trades(story):
    a = story["asset"]
    return candidate_trades(a["price"], a["typicalMove"], load_stop_price_settings())


def test_the_opening_is_the_pages_word_for_word(story):
    assert reading().opening == story["opening"]


def test_the_screens_background_is_the_pages_word_for_word(story):
    request = reading().screen_request(*views(story))
    assert request.background == story["background"]


def test_a_changed_layout_changes_the_reading_version():
    class Reordered(Reading):
        def _asset(self, asset, held=False):
            return "\n".join(reversed(super()._asset(asset, held).split("\n")))

    costs, risk = load_trading_costs(), load_risk_profile()
    assert Reordered(costs, risk).version != Reading(costs, risk).version


def test_a_changed_pick_layout_changes_the_reading_version():
    class Reordered(Reading):
        def _trade_text(self, trade, price):
            return super()._trade_text(trade, price).upper()

    costs, risk = load_trading_costs(), load_risk_profile()
    assert Reordered(costs, risk).version != Reading(costs, risk).version


def test_a_changed_position_layout_changes_the_reading_version():
    class Reordered(Reading):
        def _position(self, asset, position):
            return "\n".join(reversed(super()._position(asset, position).split("\n")))

    costs, risk = load_trading_costs(), load_risk_profile()
    assert Reordered(costs, risk).version != Reading(costs, risk).version


def test_the_screens_question_is_the_pages_word_for_word(story):
    request = reading().screen_request(*views(story))
    assert request.questions == {
        "screen": {"type": "noul", "instructions": story["question"]}
    }


# The full evaluation (tabs 2 and 3; without memory, as in tab 6, case C)


def test_code_lists_the_pages_six_candidate_trades(story):
    trades = our_trades(story)
    assert [(t.name, str(t.direction), t.width) for t in trades] == [
        (t["name"], t["direction"], t["width"]) for t in story["trades"]
    ]
    for ours, page in zip(trades, story["trades"], strict=True):
        assert ours.stop_price == pytest.approx(page["stop"])
        assert ours.stop_share == pytest.approx(page["stopShare"])


def test_the_picks_background_without_memory_is_the_pages_word_for_word(story):
    names = [o["name"] for o in story["pickOptions"]]
    request = reading().pick_request(*views(story), our_trades(story), [names] * 5)
    assert request.background == story["withoutMemory"]


# The agent with memory: the page's tab 2 (four episodes selected) and its cases A and B.

NOW = 1000 * 96  # the step of the page's full evaluation
REASONS = {"choice": "jev", "stop": "stop_price"}


def tracks(*records) -> tuple[TrackRecord, ...]:
    """The page's track record, one line per pattern and direction, as our records."""
    return tuple(
        TrackRecord(
            pattern=pattern,
            direction=direction,
            asset_class="stock",
            minimum_sample=10,
            closed_trades=fits.trades if fits else closed,
            groups=[fits] if fits else [],
        )
        for pattern, direction, fits, closed in records
    )


def fits(trades, wins, gain, loss, total, **split) -> Group:
    return Group(
        trades=trades,
        made_money=wins,
        average_gain=gain,
        average_loss=loss,
        total_profit=total,
        fits=True,
        **split,
    )


WITH_TREND = {"trend": "with the trend", "volume_level": "high"}
TRACK_RECORD = tracks(
    (
        "bullish engulfing",
        "long",
        fits(11, 7, 38, -21, 182, **WITH_TREND, part_of_day="first hour"),
        11,
    ),
    (
        "bullish engulfing",
        "short",
        fits(14, 4, 27, -24, -132, trend="against the trend"),
        14,
    ),
    ("hammer", "long", fits(23, 11, 29, -22, 55, **WITH_TREND), 23),
    ("hammer", "short", None, 6),
)
THIN_TRACK_RECORD = tracks(
    ("bullish engulfing", "long", None, 2),
    ("bullish engulfing", "short", None, 0),
    ("hammer", "long", None, 1),
    ("hammer", "short", None, 0),
)


def episodes(story) -> tuple[Episode, ...]:
    """The page's four selected episodes, as memory stores them."""
    found = []
    for n, e in enumerate(story["selected"], start=1):
        trade, ended, after = e.get("trade"), e.get("ended"), e.get("after")
        found.append(
            Episode(
                id=f"made-up-{n}",
                kind="full_evaluation",
                asset=e["asset"],
                asset_class=e["assetClass"],
                step=NOW - e["stepsAgo"],
                situation=e["situation"],
                patterns=e["patterns"],
                longer_patterns=e.get("patternsOnLongerBars", []),
                part_of_day="first hour",
                trend="up",
                volume="high",
                decided=trade["direction"] if trade else "no_trade",
                trade=trade
                and Trade(
                    direction=trade["direction"],
                    stop=trade["stop"],
                    stop_distance=trade["stopPercent"] / 100,
                    dollars=trade["dollars"],
                ),
                ended=ended
                and Ended(
                    reason=REASONS[ended["reason"]],
                    bars_after=ended["bars"],
                    profit=ended["profit"],
                    percent=ended["percent"],
                    best=ended["best"],
                    worst=ended["worst"],
                ),
                prices=after
                and Prices(
                    after_1_bar=after["oneBar"] / 100,
                    after_4_bars=after["fourBars"] / 100,
                    end_of_day=after["endOfDay"] / 100,
                ),
            )
        )
    return tuple(found)


def test_the_picks_background_with_memory_is_the_pages_word_for_word(story):
    names = [o["name"] for o in story["pickOptions"]]
    memory = MemorySections(NOW, TRACK_RECORD, PastEpisodes.SELECTED, episodes(story))

    request = reading().pick_request(
        *views(story), our_trades(story), [names] * 5, memory
    )

    assert request.background == story["withMemory"]
    assert request.questions[MEMORIES_RELEVANT] == {
        "type": "noul",
        "instructions": story["memoriesRelevant"],
    }
    size = reading().size_request(*views(story), our_trades(story)[0], memory)
    assert size.background == story["sizeWithMemory"]


@pytest.mark.parametrize(
    ("past", "track_record", "page"),
    [
        (PastEpisodes.NONE_SELECTED, TRACK_RECORD, "noneSelected"),
        (PastEpisodes.NONE_YET, THIN_TRACK_RECORD, "noneYet"),
    ],
)
def test_each_nothing_to_show_case_is_the_pages_word_for_word(
    story, past, track_record, page
):
    names = [o["name"] for o in story["pickOptions"]]
    memory = MemorySections(NOW, track_record, past)

    request = reading().pick_request(
        *views(story), our_trades(story), [names] * 5, memory
    )

    assert request.background == story[page]
    assert MEMORIES_RELEVANT not in request.questions


def test_the_pick_is_asked_as_copies_with_the_pages_options(story):
    page_options = {o["name"]: o["text"] for o in story["pickOptions"]}
    orders = [list(reversed(page_options)), *[list(page_options)] * 4]
    request = reading().pick_request(*views(story), our_trades(story), orders)

    assert list(request.questions) == [
        f"pick_{n}" for n in range(1, story["shuffledCopies"] + 1)
    ]
    first = request.questions["pick_1"]
    assert first["type"] == "choice"
    assert first["instructions"] == story["pickQuestion"]
    assert first["criteria"] == page_options
    assert list(first["criteria"]) == orders[0]  # sent in the order given


def test_the_size_request_is_the_pages_word_for_word(story):
    request = reading().size_request(*views(story), our_trades(story)[0])

    assert request.background == story["sizeBackground"]
    smallest_first = {o["name"]: o["text"] for o in story["sizeOptions"]}
    assert request.questions["size_small_first"] == {
        "type": "choice",
        "instructions": story["sizeQuestion"],
        "criteria": smallest_first,
    }
    largest_first = request.questions["size_large_first"]
    assert list(largest_first["criteria"]) == list(reversed(smallest_first))
    assert largest_first["criteria"] == smallest_first
    assert request.questions["rating"] == {
        "type": "score",
        "instructions": story["ratingQuestion"],
        "criteria": story["ratingLevels"],
    }


# The position screen and the position review (tabs 4 and 5; without memory)


def position_views(story, since=None, end_of_session=False):
    """The page's position five bars later, as our code takes it, with the page's figures."""
    p, facts = story["position"], story["positionFacts"]
    asset, account, playbook = views(
        {**story, "asset": story["later"], "account": story["accountLater"]}
    )
    position = PositionView(
        direction=Direction(p["direction"]),
        put_in=p["putIn"],
        bars_ago=p["barsAgo"],
        entry_price=p["entryPrice"],
        stop_price=p["stopPrice"],
        worth=facts["worth"],
        profit=facts["profit"],
        percent=facts["profitPercent"],
        best=p["best"],
        worst=p["worst"],
        situation_at_entry=p["situationAtEntry"],
        patterns_at_entry=tuple(p["patternsAtEntry"]),
        since=tuple(p["since"] if since is None else since),
        end_of_session=end_of_session,
    )
    return asset, account, playbook, position


def test_the_position_screen_is_the_pages_word_for_word(story):
    request = reading().position_screen_request(*position_views(story))

    assert request.background == story["positionScreenBackground"]
    assert request.questions == {
        "position_screen": {
            "type": "noul",
            "instructions": story["positionScreenQuestion"],
        }
    }


def page_options(options):
    return {o["name"]: o["text"] for o in options}


def test_the_review_asks_the_action_as_copies_with_the_pages_options(story):
    options = page_options(story["actionOptions"])
    orders = [list(reversed(options)), *[list(options)] * 4]
    request = reading().action_request(*position_views(story), orders)

    assert request.background == story["reviewBackground"]
    assert list(request.questions) == [f"action_{n}" for n in range(1, 6)] + [
        "thesis_intact"
    ]
    first = request.questions["action_1"]
    assert first["instructions"] == story["actionQuestion"]
    assert first["criteria"] == options
    assert list(first["criteria"]) == orders[0]
    assert request.questions["thesis_intact"] == {
        "type": "noul",
        "instructions": story["thesisIntact"],
    }


def test_no_add_option_when_nothing_can_be_added(story):
    names = ["hold", "close", "reduce"]
    request = reading().action_request(
        *position_views(story), [names] * 5, add_allowed=False
    )
    assert list(request.questions["action_1"]["criteria"]) == names


def test_the_reduce_request_is_the_pages_word_for_word(story):
    request = reading().reduce_request(*position_views(story))

    assert request.background == story["reduceBackground"]
    smallest_first = page_options(story["reduceOptions"])
    assert request.questions["reduce_small_first"] == {
        "type": "choice",
        "instructions": story["reduceQuestion"],
        "criteria": smallest_first,
    }
    largest_first = request.questions["reduce_large_first"]["criteria"]
    assert list(largest_first) == list(reversed(smallest_first))


def test_the_add_request_is_the_pages_word_for_word(story):
    request = reading().add_request(*position_views(story))

    assert request.background == story["addBackground"]
    smallest_first = page_options(story["addOptions"])
    assert request.questions["add_small_first"] == {
        "type": "choice",
        "instructions": story["addQuestion"],
        "criteria": smallest_first,
    }
    largest_first = request.questions["add_large_first"]["criteria"]
    assert list(largest_first) == list(reversed(smallest_first))


def test_an_end_of_session_review_adds_the_pages_one_line(story):
    asset, account, playbook, position = position_views(
        story, since=["bars 1 to 21 hold"], end_of_session=True
    )
    position = replace(position, bars_ago=22)
    request = reading().action_request(
        asset, account, playbook, position, [["hold", "close", "reduce", "add"]] * 5
    )
    assert story["endOfSession"] in request.background
