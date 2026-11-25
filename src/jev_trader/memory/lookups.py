"""The memory server's three lookups, over a `MemoryStore` (spec appendix 5, sections 3 and 4):
search episodes, read up to 5 episodes in full, and read the track record. All read-only.

Each takes the sim and the step, which code fills in on every call (the LLM never sees them),
and reads only what was known by that step (`store`).

How the search learns what it serves is left to the build; code passes it on each call:
the asset looked at, the job (a full evaluation of an asset with no position, or a position
review), and for a review the open position's direction. A full evaluation finds past full
evaluations; a review finds past reviews of positions in the same direction only.
"""

from collections.abc import Sequence

from pydantic import BaseModel

from jev_trader.dataset.measurements import MEASUREMENT_NAMES
from jev_trader.dataset.situation_text import (
    VOLUME_HIGH_ABOVE,
    VOLUME_LOW_BELOW,
    read_situation,
)
from jev_trader.memory import episodes as built
from jev_trader.memory.episodes import Episode
from jev_trader.memory.scorecard import (
    MINIMUM_SAMPLE,
    FiledTrade,
    Moment,
    trend,
    volume_level,
)
from jev_trader.memory.search import (
    ASSET_FILTERS,
    DECIDED_FILTERS,
    DIRECTIONS,
    FULL_EVALUATION,
    POSITION_REVIEW,
    STANDING_FILTERS,
    Filters,
    Query,
    SearchSettings,
    best_without_repeats,
    feature_weights,
    merge,
)
from jev_trader.memory.store import MemoryStore
from jev_trader.memory.track_record import TrackRecord, track_record
from jev_trader.sim.store import KIND_POSITION_REVIEW

MOST_READ = 5
_LONG_TERM_TREND = MEASUREMENT_NAMES.index("long_term_trend")
_VOLUME = MEASUREMENT_NAMES.index("volume_against_normal")


class NotAllowed(ValueError):
    """A lookup asked with a value it may not use; the message names the allowed values."""


class Found(BaseModel):
    """One search result: the episode, its two ranks (1 is closest; None: outside that ranking's
    top 50) and its merged rank, kept so later analysis can tell whether the text ranking
    helped."""

    episode: Episode
    vector_rank: int | None
    text_rank: int | None
    merged_rank: int


class SearchResult(BaseModel):
    episodes: list[Found]  # closest first; empty: nothing matches


class Episodes(BaseModel):
    episodes: list[Episode]  # in the order asked; one not shown by now is left out


def volume_cut_offs(settings: dict | None) -> tuple[float, float]:
    """The sim's volume levels: below the first is low, above the second high (`track_record`
    in its settings, else the version 1 cut-offs). Episodes and the track record share them."""
    found = (settings or {}).get("track_record") or {}
    return (
        found.get("volume_low_below", VOLUME_LOW_BELOW),
        found.get("volume_high_above", VOLUME_HIGH_ABOVE),
    )


def _check(name: str, value: str, allowed: Sequence[str]) -> None:
    if value not in allowed:
        listed = ", ".join(f'"{a}"' for a in allowed)
        raise NotAllowed(f"{name} must be one of {listed}.")


class Lookups:
    def __init__(self, store: MemoryStore):
        self.store = store

    def search(
        self,
        sim: int,
        step: int,
        asset: str,
        job: str,
        filters: Filters,
        position_direction: str | None = None,
    ) -> SearchResult:
        _check("asset", filters.asset, ASSET_FILTERS)
        _check("job", job, (FULL_EVALUATION, POSITION_REVIEW))
        _check("decided", filters.decided, DECIDED_FILTERS[job])
        if job == POSITION_REVIEW:
            _check("standing", filters.standing, STANDING_FILTERS)
            _check("position_direction", position_direction or "", DIRECTIONS)
        elif filters.standing != "any":
            raise NotAllowed("standing is only for a position review.")
        row = self.store.sim(sim)
        settings = SearchSettings.of_sim(row["SETTINGS"])
        current = self.store.snapshot(row["DATASET"], asset, step)
        query = Query(
            sim=sim,
            step=step,
            asset=asset,
            asset_class=current["ASSET_CLASS"],
            job=job,
            direction=position_direction if job == POSITION_REVIEW else None,
            filters=filters,
            dataset=row["DATASET"],
        )
        by_vector, by_text = self.store.ranked(
            query, current, feature_weights(settings), settings.each_ranking_top
        )
        merged = merge([c.id for c in by_vector], [c.id for c in by_text])
        candidates = {c.id: c for c in (*by_vector, *by_text)}
        kept = best_without_repeats(
            [candidates[m.id] for m in merged], settings.results
        )
        ranks = {m.id: m for m in merged}
        found = self._episodes(
            sim, step, [c.id for c in kept], journals=False, settings=row["SETTINGS"]
        )
        return SearchResult(
            episodes=[
                Found(
                    episode=found[c.id],
                    vector_rank=ranks[c.id].vector_rank,
                    text_rank=ranks[c.id].text_rank,
                    merged_rank=ranks[c.id].merged_rank,
                )
                for c in kept
                if c.id in found
            ]
        )

    def read(self, sim: int, step: int, episode_ids: Sequence[str]) -> Episodes:
        if not 1 <= len(episode_ids) <= MOST_READ:
            raise NotAllowed(f"episode_ids must hold 1 to {MOST_READ} IDs.")
        settings = self.store.sim(sim)["SETTINGS"]
        found = self._episodes(
            sim, step, list(episode_ids), journals=True, settings=settings
        )
        return Episodes(episodes=[found[i] for i in episode_ids if i in found])

    def _episodes(
        self, sim: int, step: int, ids: list[str], journals: bool, settings: dict | None
    ) -> dict[str, Episode]:
        cut_offs = volume_cut_offs(settings)
        rows = self.store.decisions(sim, step, ids)
        outcomes: dict[str, list[dict]] = {r["ID"]: [] for r in rows}
        for o in self.store.outcomes(sim, step, list(outcomes)):
            outcomes[o["DECISION"]].append(o)
        positions = {}
        if journals:
            for r in rows:
                p = (
                    r.get("POSITION")
                    if r["KIND"] == KIND_POSITION_REVIEW
                    else built.position_of(outcomes[r["ID"]])
                )
                if p is not None:
                    positions[r["ID"]] = p
        by_position: dict[int, list[dict]] = {p: [] for p in positions.values()}
        if by_position:
            for p in self.store.position_rows(sim, step, list(by_position)):
                by_position[p["POSITION"]].append(p)
        return {
            r["ID"]: built.build(
                r,
                outcomes[r["ID"]],
                by_position.get(positions.get(r["ID"]), []) if journals else None,
                cut_offs,
            )
            for r in rows
        }

    def track_record(
        self, sim: int, step: int, asset: str, pattern: str, direction: str
    ) -> TrackRecord:
        _check("direction", direction, DIRECTIONS)
        row = self.store.sim(sim)
        settings = (row["SETTINGS"] or {}).get("track_record") or {}
        low, high = volume_cut_offs(row["SETTINGS"])
        current = self.store.snapshot(row["DATASET"], asset, step)
        asset_class = current["ASSET_CLASS"]
        trades = [
            self._filed(t, low, high)
            for t in self.store.closed_trades(sim, step, asset_class)
        ]
        measured = current["MEASUREMENTS"]
        moment = Moment(
            pattern=pattern,
            direction=direction,
            asset_class=asset_class,
            trend=trend(direction, measured[_LONG_TERM_TREND]),
            volume_level=volume_level(measured[_VOLUME], low, high),
            part_of_day=read_situation(current["SITUATION_TEXT"]).part_of_day,
        )
        minimum = settings.get("minimum_sample", MINIMUM_SAMPLE)
        return track_record(trades, moment, minimum, step)

    @staticmethod
    def _filed(row: dict, low: float, high: float) -> FiledTrade:
        """A closed trade filed under what it was decided beside (as the scorecard files it)."""
        direction = row["PICK"].split("_")[0]
        measured = row["MEASUREMENTS"]
        read = read_situation(row["SITUATION_TEXT"])
        return FiledTrade(
            patterns=read.window,
            direction=direction,
            asset_class=row["ASSET_CLASS"],
            trend=trend(direction, measured[_LONG_TERM_TREND]),
            volume_level=volume_level(measured[_VOLUME], low, high),
            part_of_day=read.part_of_day,
            profit=row["PROFIT"],
            closed_step=row["CLOSED_STEP"],
        )
