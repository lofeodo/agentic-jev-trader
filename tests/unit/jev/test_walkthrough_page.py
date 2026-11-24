"""The Jev walkthrough page matches what is sent (spec appendix 10, section 18).

The page's own code writes the screen's and the full evaluation's text from its made-up story.
This test runs that code with Node and compares it, word for word, with what our code writes
from the same story. The full evaluation is compared as the agent without memory sends it (the
page's tab 6, case C): the memory sections come with the agent with memory.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from jev_trader.broker import load_stop_price_settings, load_trading_costs
from jev_trader.jev.full_evaluation import candidate_trades
from jev_trader.jev.reading import AccountView, AssetView, PositionLine, Reading
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
  sizeBackground: fullEvaluationBackground(ASSET, ACCOUNT, PLAYBOOK, null, candidateTrades(ASSET)[0]),
  sizeQuestion: QUESTIONS.size,
  sizeOptions: sizeOptions(ACCOUNT, candidateTrades(ASSET)[0]),
  ratingQuestion: QUESTIONS.rating,
  ratingLevels: RATING_LEVELS,
  shuffledCopies: SETTINGS.shuffledCopies,
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
        def _asset(self, asset):
            return "\n".join(reversed(super()._asset(asset).split("\n")))

    costs, risk = load_trading_costs(), load_risk_profile()
    assert Reordered(costs, risk).version != Reading(costs, risk).version


def test_a_changed_pick_layout_changes_the_reading_version():
    class Reordered(Reading):
        def _trade_text(self, trade, price):
            return super()._trade_text(trade, price).upper()

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
