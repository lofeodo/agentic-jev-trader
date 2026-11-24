"""The memory server's real queries, as the memory login, against TRADING_AGENT_TEST (spec
appendix 5, sections 3 and 4).

One made-up memory (the unit tests' `MadeUpMemory`, with past episodes planted "from the future")
is written to the test database: the snapshots and patterns as the dataset builder, the sim and
its memory as the sim login. The memory login, whose role can only read, then answers every
lookup, and each answer must equal the in-memory stand-in's. Everything written is removed.
"""

import json

import pytest

from jev_trader.memory.lookups import Lookups
from jev_trader.memory.search import Filters
from jev_trader.memory.snowflake_store import SnowflakeMemoryStore
from tests.snowflake.conftest import login
from tests.unit.memory.conftest import MadeUpMemory, vector

NOW = 500
EMBEDDING_SIZE = 768


@pytest.fixture
def memory_login():
    con = login("memory")
    yield con
    con.close()


def _insert(con, table: str, rows: list[dict], casts: dict[str, str] | None = None):
    """Rows into `table` in one statement; dicts and lists go in as JSON, `casts` names the SQL
    to wrap a column's `?` in."""
    if not rows:
        return
    casts = casts or {}
    columns = list(rows[0])
    one = ", ".join(
        casts.get(c, "PARSE_JSON(?)" if isinstance(rows[0][c], (dict, list)) else "?")
        for c in columns
    )
    values = [
        json.dumps(r[c]) if isinstance(r[c], (dict, list)) else r[c]
        for r in rows
        for c in columns
    ]
    selects = " UNION ALL ".join(f"SELECT {one}" for _ in rows)
    with con.cursor() as cur:
        cur.execute(f"INSERT INTO {table} ({', '.join(columns)}) {selects}", values)


def made_up(sim: int, dataset: int) -> MadeUpMemory:
    m = MadeUpMemory(sim, dataset)
    m.snapshot("ASSET_01", NOW, features=vector(0.0), window=[("doji", 0)])
    m.no_trade("ASSET_01", 100, features=vector(0.1), embedding=(1, 0.1, 0))
    m.trade("ASSET_01", 120, position=1, window=[("hammer", 1)], features=vector(0.5))
    m.no_trade("ASSET_02", 200, asset_class="stock", embedding=(0, 1, 0))
    m.no_trade("ASSET_03", 300, window=[("hammer", 0)], features=vector(3.0))
    m.cancelled("ASSET_02", 260, asset_class="stock")  # decided long, never carried out
    for n in range(10):
        m.trade("ASSET_04", 10 + 10 * n, position=10 + n, window=[("hammer", 0)])
    m.review("ASSET_01", 140, position=30, profit=8.0)
    m.review("ASSET_03", 160, position=31, action="close", profit=-3.0)
    m.review("ASSET_04", 180, position=32, direction="short")
    # From the future: decided later, completed later, closed later.
    m.no_trade("ASSET_01", NOW + 8, window=[("hammer", 0)])
    m.no_trade("ASSET_02", NOW - 2, asset_class="stock")
    m.trade("ASSET_03", NOW - 20, position=40, closed_after=30, window=[("hammer", 0)])
    return m


def write(m: MadeUpMemory, builder, sim_login, dataset: int):
    store = m.store
    classes = {asset: s["ASSET_CLASS"] for (_, asset, _), s in store.snapshots.items()}
    _insert(
        builder,
        "REF.ASSETS",
        [
            {"DATASET": dataset, "MASKED_ID": a, "ASSET_CLASS": c}
            for a, c in sorted(classes.items())
        ],
    )
    _insert(
        builder,
        "FEATURES.SNAPSHOTS",
        [
            {
                "DATASET": dataset,
                "ASSET": asset,
                "STEP": step,
                "MEASUREMENTS": s["MEASUREMENTS"],
                "FEATURE_VECTOR": s["FEATURE_VECTOR"],
                "SITUATION_TEXT": s["SITUATION_TEXT"],
                "EMBEDDING": [
                    *s["EMBEDDING"],
                    *[0.0] * (EMBEDDING_SIZE - len(s["EMBEDDING"])),
                ],
            }
            for (_, asset, step), s in store.snapshots.items()
        ],
        casts={
            "MEASUREMENTS": "PARSE_JSON(?)::ARRAY",
            "FEATURE_VECTOR": "PARSE_JSON(?)::ARRAY::VECTOR(FLOAT, 58)",
            "EMBEDDING": f"PARSE_JSON(?)::ARRAY::VECTOR(FLOAT, {EMBEDDING_SIZE})",
        },
    )
    _insert(builder, "FEATURES.PATTERNS", store.patterns)
    columns = sorted({c for r in store.decisions_table for c in r})
    _insert(
        sim_login,
        "MEMORY.DECISIONS",
        [{c: r.get(c) for c in columns} for r in store.decisions_table],
        casts={c: "PARSE_JSON(?)" for c in ("CANDIDATE_TRADES", "STANDING")},
    )
    _insert(sim_login, "MEMORY.OUTCOMES", store.outcomes_table)


@pytest.fixture
def written(made_up_dataset, builder, sim_login, remove_sims):
    dataset = made_up_dataset(days=6, assets=0)
    with sim_login.cursor() as cur:
        cur.execute("SELECT SIM.SIM_IDS.NEXTVAL")
        [(sim,)] = cur.fetchall()
        remove_sims.append(sim)
        cur.execute(
            "INSERT INTO SIM.SIMS (ID, DATASET, KIND, VARIANT, FIRST_STEP, LAST_STEP, "
            "STARTING_VALUE, SETTINGS, STATUS) "
            "SELECT ?, ?, 'practice', 'memory_on', 1, 576, 10000, PARSE_JSON('{}'), "
            "'finished'",
            (sim, dataset),
        )
    m = made_up(sim, dataset)
    write(m, builder, sim_login, dataset)
    return m


def answers(lookups: Lookups, sim: int) -> dict:
    review = {"job": "position_review", "position_direction": "long"}
    searches = {
        "any": ({}, {}),
        "same asset": ({"asset": "same_asset"}, {}),
        "same class": ({"asset": "same_asset_class"}, {}),
        "hammer": ({"pattern": "hammer"}, {}),
        "long": ({"decided": "long"}, {}),
        "no trade": ({"decided": "no_trade"}, {}),
        "reviews": ({}, review),
        "closed reviews": ({"decided": "close"}, review),
        "in profit": ({"standing": "in_profit"}, review),
        "short reviews": ({}, {**review, "position_direction": "short"}),
    }
    found = {}
    for name, (filters, job) in searches.items():
        result = lookups.search(
            sim,
            NOW,
            "ASSET_01",
            job.get("job", "full_evaluation"),
            Filters(**filters),
            job.get("position_direction"),
        )
        found[name] = result.model_dump()
    every = [f"{sim}-{step}-{a}" for step, a in ((120, "ASSET_01"), (140, "ASSET_01"))]
    found["read"] = lookups.read(sim, NOW, every).model_dump()
    found["track record"] = lookups.track_record(
        sim, NOW, "ASSET_01", "hammer", "long"
    ).model_dump()
    return found


def test_the_real_queries_answer_as_the_stand_in_does(written, memory_login):
    expected = answers(Lookups(written.store), written.sim)
    real = answers(Lookups(SnowflakeMemoryStore(memory_login)), written.sim)

    # Not vacuous: the made-up memory gives each lookup something to find.
    assert all(expected[k]["episodes"] for k in expected if k != "track record")
    assert expected["track record"]["closed_trades"] == 11
    for name in expected:
        assert real[name] == expected[name], name
