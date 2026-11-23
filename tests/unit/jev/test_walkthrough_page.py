"""The Jev walkthrough page matches what is sent (spec appendix 10, section 18).

The page's own code writes the screen's text from its made-up story. This test runs that code
with Node and compares it, word for word, with what our code writes from the same story.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from jev_trader.broker import load_trading_costs
from jev_trader.jev.reading import AccountView, AssetView, PositionLine, Reading
from jev_trader.risk import load_risk_profile

PAGE = Path(__file__).parents[3] / "docs" / "jev-reading-walkthrough.html"
PRINT_THE_STORY = """
console.log(JSON.stringify({
  opening: taskSection(),
  background: screenBackground(ASSET, ACCOUNT, PLAYBOOK),
  question: QUESTIONS.screen(ASSET),
  asset: ASSET, account: ACCOUNT, playbook: PLAYBOOK,
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


def our_request(story):
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
    reading = Reading(load_trading_costs(), load_risk_profile())
    return reading, reading.screen_request(asset, account, playbook)


def test_the_opening_is_the_pages_word_for_word(story):
    reading, _ = our_request(story)
    assert reading.opening == story["opening"]


def test_the_screens_background_is_the_pages_word_for_word(story):
    _, request = our_request(story)
    assert request.background == story["background"]


def test_the_screens_question_is_the_pages_word_for_word(story):
    _, request = our_request(story)
    assert request.questions == {
        "screen": {"type": "noul", "instructions": story["question"]}
    }
