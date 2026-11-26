"""The saved moments the benchmark hands each model (spec appendix 9, section 8).

A saved moment is one point in the build-up sim where the LLM would be asked to pick past
episodes: 25 full evaluations and 25 position reviews, 5 of each per asset, drawn at random from
the build-up year's last 30 days. Each model starts where the sim did: the same situation text and
the same first search, whose ten episodes it sees as one-line summaries in today's wording
(not the wording the build-up sim had).

Choices the spec leaves to the build:

- The moments are drawn, not stored: the build-up sim's own full evaluations and position
  reviews of its last 30 days (`MEMORY.DECISIONS`), 5 of each job per asset picked by the sim's
  random seed, so every run on the same sim gets the same 50. Only a finished build-up sim is
  drawn from. An asset with fewer than 5 of a job gives all it has; the command says how many
  moments it ran on.
- The situation is rebuilt from the dataset (`FEATURES.SNAPSHOTS`, the playbook, the asset's
  class), and a position review's open position from its decision row (`STANDING`,
  `END_OF_SESSION`), as the sim built them.
- The first search is made once per moment, through the memory server on the build-up sim's
  memory at the moment's step, and the same result is handed to every model at every pass. It
  is made again on each run, so a run after a change to the search's settings starts from the
  changed search.
"""

import json
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from jev_trader.dataset.bars import STEPS_PER_DAY
from jev_trader.llm.selection import (
    MemoryLookups,
    ReviewedPosition,
    Situation,
)
from jev_trader.memory.bridge import LookupContext
from jev_trader.memory.episodes import Standing
from jev_trader.memory.lookups import SearchResult
from jev_trader.memory.outcomes import EPISODE_KINDS
from jev_trader.memory.search import FULL_EVALUATION, Job
from jev_trader.sim.snowflake_store import SnowflakeMarket, SnowflakeSimStore
from jev_trader.sim.store import SimStatus

BUILD_UP = "build-up"  # SIM.SIMS.KIND of the build-up sim
PER_JOB_AND_ASSET = 5  # moments of each job drawn for each asset
LAST_DAYS = 30  # drawn from the build-up year's last 30 days


@dataclass(frozen=True)
class SavedMoment:
    """One moment from the build-up sim `sim`.

    `situation` holds what the model is told: the asset (masked) and its class, the situation
    text, and in a position review the open position. Its step is the moment's "now": the
    model's own lookups see only the records older than it. `first_search` is code's first
    search at that moment, the ten episodes whose summaries open the exchange.
    """

    sim: int
    situation: Situation
    first_search: SearchResult

    @property
    def job(self) -> Job:
        """Full evaluation or position review."""
        return self.situation.job

    @property
    def asset(self) -> str:
        return self.situation.asset

    @property
    def now(self) -> int:
        """The step the moment was saved at."""
        return self.situation.step

    @property
    def id(self) -> str:
        """The same for every pass and model: "12-4410-ASSET_03-full_evaluation"."""
        return f"{self.sim}-{self.now}-{self.asset}-{self.job}"


def context_at(sim: int, situation: Situation) -> LookupContext:
    """What code fills in on each lookup at `situation`: the build-up sim `sim`'s memory as it
    stood at the situation's step, for its asset and job (and, in a position review, the open
    position's direction)."""
    position = situation.position
    return LookupContext(
        sim=sim,
        step=situation.step,
        asset=situation.asset,
        job=situation.job,
        position_direction=None if position is None else position.standing.direction,
    )


class NoSavedMoments(LookupError):
    """The sim asked for has no moments to hand the models; the message says why."""


@dataclass(frozen=True)
class Candidate:
    """A full evaluation or position review of the build-up sim that may be drawn: its asset,
    step and job, and in a position review the open position."""

    asset: str
    step: int
    job: Job
    position: ReviewedPosition | None = None


def draw(candidates: Sequence[Candidate], seed: int) -> list[Candidate]:
    """`PER_JOB_AND_ASSET` of each job for each asset, picked at random by `seed`: full
    evaluations first, then position reviews, each by asset and step."""
    picker = random.Random(seed)
    groups: dict[tuple[bool, str], list[Candidate]] = {}
    for candidate in sorted(candidates, key=_order):
        groups.setdefault(_group(candidate), []).append(candidate)
    drawn = []
    for key in sorted(groups):
        group = groups[key]
        drawn += picker.sample(group, min(PER_JOB_AND_ASSET, len(group)))
    return sorted(drawn, key=_order)


def _group(candidate: Candidate) -> tuple[bool, str]:
    """Full evaluations before position reviews, then by asset."""
    return (candidate.job != FULL_EVALUATION, candidate.asset)


def _order(candidate: Candidate) -> tuple[bool, str, int]:
    return (*_group(candidate), candidate.step)


class BuildUpSim:
    """The build-up sim `sim`, read through `connection` (the sim login): what its moments are
    drawn from."""

    def __init__(self, connection, sim: int):
        self.connection, self.sim = connection, sim
        try:
            row = SnowflakeSimStore(connection).sim(sim)
        except KeyError:
            raise NoSavedMoments(f"there is no sim {sim}") from None
        if row["KIND"] != BUILD_UP:
            raise NoSavedMoments(
                f"sim {sim} is a {row['KIND']} sim, not the build-up sim"
            )
        if row["STATUS"] != SimStatus.FINISHED:
            raise NoSavedMoments(
                f"sim {sim} is {row['STATUS']}: its moments are drawn once it has finished"
            )
        self.dataset = row["DATASET"]
        self.seed = row["RANDOM_SEED"]
        self.last_step = row["LAST_COMPLETED_STEP"]
        self.market = SnowflakeMarket(connection)
        self.playbook = self.market.playbook(self.dataset)

    def candidates(self) -> list[Candidate]:
        """The sim's own full evaluations and position reviews of its last `LAST_DAYS` days."""
        with self.connection.cursor() as cur:
            cur.execute(
                "SELECT ASSET, STEP, KIND, STANDING, END_OF_SESSION FROM MEMORY.DECISIONS "
                "WHERE SIM = ? AND FIRST_WRITTEN_BY = SIM "
                f"AND KIND IN ({', '.join('?' for _ in EPISODE_KINDS)}) AND STEP > ?",
                (
                    self.sim,
                    *EPISODE_KINDS,
                    self.last_step - LAST_DAYS * STEPS_PER_DAY,
                ),
            )
            rows = cur.fetchall()
        return [
            Candidate(
                asset=asset,
                step=step,
                job=kind,
                position=_reviewed(standing, end_of_session),
            )
            for asset, step, kind, standing, end_of_session in rows
        ]

    def saved_moments(
        self, lookups_at: Callable[[LookupContext], MemoryLookups]
    ) -> list[SavedMoment]:
        """The 50 moments, in a fixed order, each with its first search made through
        `lookups_at` (`jev_trader.memory.bridge.Connection.lookups_at`)."""
        drawn = draw(self.candidates(), self.seed)
        if not drawn:
            raise NoSavedMoments(
                f"sim {self.sim} made no full evaluation or position review in its last "
                f"{LAST_DAYS} days"
            )
        classes = self.market.dataset(self.dataset).assets
        snapshots = self.market.snapshots(
            self.dataset, min(c.step for c in drawn), max(c.step for c in drawn)
        )
        moments = []
        for candidate in drawn:
            snapshot = snapshots[candidate.step][candidate.asset]
            situation = Situation(
                asset=candidate.asset,
                asset_class=str(classes[candidate.asset]),
                step=candidate.step,
                text=snapshot.situation_text,
                patterns=snapshot.patterns,
                playbook=self.playbook,
                position=candidate.position,
            )
            lookups = lookups_at(context_at(self.sim, situation))
            moments.append(SavedMoment(self.sim, situation, lookups.search()))
        return moments


def _reviewed(standing, end_of_session) -> ReviewedPosition | None:
    """A position review's open position, from its decision row's STANDING (JSON) and
    END_OF_SESSION; None on a full evaluation's row."""
    if standing is None:
        return None
    if isinstance(standing, str):
        standing = json.loads(standing)
    return ReviewedPosition(Standing(**standing), bool(end_of_session))
