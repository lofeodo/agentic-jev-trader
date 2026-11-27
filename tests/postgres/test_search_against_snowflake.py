"""Postgres's search finds what Snowflake's found, in the same order (spec appendix 11, section
2: "The search returns the same episodes in the same order").

`snowflake_searches.json`, beside this file, is the check set, taken from a `storage save` of
Snowflake (no Snowflake call): the three practice sims with memory (301, 501 and 701), their
episodes and outcomes, the snapshots and candle patterns those episodes and the sims' own
decisions were made beside, and every search those sims made on Snowflake, with what it
returned:

- each decision's first search (the one code makes, every filter "any"), from the decision's
  `EPISODES_SHOWN`: the episodes it found, in order, with their two ranks and merged rank;
- each search the LLM made, from the decision's `LOOKUPS`: its filters and the episodes it
  found, in order.

The rows are written to the local Postgres, and each search is made again there, as the memory
login, at the same sim, step and asset. Each must find the same episodes in the same order.

**The database as it stood then.** The saved rows are the sims' last state. A step's records
are saved after its decisions, so an episode whose last outcome came at step N
(`OUTCOMES_KNOWN_FROM` N) was not yet complete for the searches made at step N: Snowflake did
not show it. While a step's searches are made again, its episodes completing at that step are
set back to not complete.
"""

import itertools
import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from jev_trader.memory.lookups import Lookups
from jev_trader.memory.search import Filters
from tests.postgres.helpers import insert

SAVED = Path(__file__).with_name("snowflake_searches.json")


@pytest.fixture
def check_set(setup_login):
    saved = json.loads(SAVED.read_text(encoding="utf-8"))
    for table, rows in (
        ("SIM.SIMS", saved["sims"]),
        ("REF.ASSETS", saved["assets"]),
        ("FEATURES.SNAPSHOTS", saved["snapshots"]),
        ("FEATURES.PATTERNS", saved["patterns"]),
        ("MEMORY.DECISIONS", saved["decisions"]),
        ("MEMORY.OUTCOMES", saved["outcomes"]),
    ):
        insert(setup_login, table, rows)
    return saved


def test_each_search_finds_what_snowflake_found(check_set, setup_login, memory_db):
    searches = check_set["searches"]
    lookups = Lookups(memory_db.memory_store())

    # Not vacuous: most searches found something, first searches and the LLM's alike.
    assert sum(1 for s in searches if s["found"]) >= 30
    assert sum(1 for s in searches if not s["filters"] and s["found"]) >= 20

    for (sim, step), made in itertools.groupby(
        searches, key=lambda s: (s["sim"], s["step"])
    ):
        with completing_later(setup_login, sim, step):
            for s in made:
                check(lookups, s)


@contextmanager
def completing_later(con, sim: int, step: int):
    """The sim's episodes completing at `step` set back to not complete, for the block."""
    ids = [
        i
        for (i,) in con.execute(
            "UPDATE memory.decisions SET outcomes_known_from = NULL "
            "WHERE sim = %s AND outcomes_known_from = %s RETURNING id",
            (sim, step),
        ).fetchall()
    ]
    try:
        yield
    finally:
        con.execute(
            "UPDATE memory.decisions SET outcomes_known_from = %s "
            "WHERE sim = %s AND id = ANY(%s)",
            (step, sim, ids),
        )


def check(lookups: Lookups, s: dict) -> None:
    result = lookups.search(
        s["sim"],
        s["step"],
        s["asset"],
        s["job"],
        Filters(**s["filters"]),
        s["position_direction"],
    )
    keys = s["found"][0].keys() if s["found"] else ["id"]
    found = [
        {
            "id": f.episode.id,
            "vector_rank": f.vector_rank,
            "text_rank": f.text_rank,
            "merged_rank": f.merged_rank,
        }
        for f in result.episodes
    ]
    assert [{k: f[k] for k in keys} for f in found] == s["found"], (
        f"{s['decision']}, filters {s['filters']}"
    )
