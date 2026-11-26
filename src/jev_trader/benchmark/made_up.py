"""Made-up moments and fake answers, for running the benchmark command end to end with no
Snowflake, no memory server and no model (`--made-up`): it costs nothing and writes no table.

Four moments (two full evaluations, two position reviews) of one made-up asset; every attempt
names the same made-up episode with one fake call costing `FAKE_CALL_USD`, so the spend meter's
stop can be watched: both models, three passes, is 24 attempts, and at $0.10 each the $1.50 cap
stops the run after 15 of them.
"""

from jev_trader.benchmark.attempts import Attempt, Outcome
from jev_trader.benchmark.moments import SavedMoment
from jev_trader.llm.clients import LlmCall
from jev_trader.llm.selection import ReviewedPosition, Situation
from jev_trader.llm.settings import LlmSettings
from jev_trader.memory.episodes import Standing
from jev_trader.memory.lookups import SearchResult

MADE_UP_SIM = 0
FAKE_CALL_USD = 0.10


def made_up_moments() -> list[SavedMoment]:
    """Two full evaluations, then two position reviews, of the made-up asset `ASSET_01`."""
    long_position = ReviewedPosition(
        Standing(
            direction="long",
            put_in=1000.0,
            bars_open=3,
            profit=4.0,
            percent=0.4,
            stop_distance=0.01,
            best=6.0,
            worst=-2.0,
        )
    )
    return [
        SavedMoment(
            sim=MADE_UP_SIM,
            situation=Situation(
                asset="ASSET_01",
                asset_class="crypto",
                step=step,
                text="A made-up situation.",
                patterns=(),
                playbook={},
                position=position,
            ),
            first_search=SearchResult(episodes=[]),
        )
        for step, position in [
            (100, None),
            (200, None),
            (300, long_position),
            (400, long_position),
        ]
    ]


class FakeRunner:
    """Answers every attempt at once, naming one made-up episode, for `FAKE_CALL_USD`."""

    def run(self, moment: SavedMoment, model: LlmSettings, pass_number: int) -> Attempt:
        call = LlmCall(
            service="fake",
            model=model.name,
            tokens_in=1000,
            cached_tokens=0,
            tokens_out=50,
            thinking_tokens=0,
            cost_usd=FAKE_CALL_USD,
            latency_seconds=0.0,
            retries=0,
        )
        return Attempt(
            moment=moment,
            model=model.model,
            pass_number=pass_number,
            outcome=Outcome.FINE,
            episode_ids=(f"{MADE_UP_SIM}-1-ASSET_01",),
            calls=(call,),
        )
