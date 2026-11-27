"""One made-up memory, written to the local Postgres for the memory server to read.

The unit tests' `MadeUpMemory` (with past episodes planted "from the future") is built, and its
rows written beside a published made-up dataset and a finished sim: the snapshots with their
numbers, the candle patterns, the decisions and their outcomes. The in-memory stand-in holding
the same memory is what the real reads are compared with.
"""

from jev_trader.dataset.snapshots import EMBEDDING_SIZE
from tests.postgres.helpers import insert
from tests.unit.memory.conftest import MadeUpMemory, vector

NOW = 500
# A later step of the same memory: the trade decided at NOW - 20 has closed by then.
LATER = NOW + 12


def made_up(sim: int, dataset: int) -> MadeUpMemory:
    m = MadeUpMemory(sim, dataset)
    m.snapshot("ASSET_01", NOW, features=vector(0.0), window=[("doji", 0)])
    m.snapshot("ASSET_02", NOW, asset_class="stock", window=[("hammer", 1)])
    m.snapshot("ASSET_01", LATER, features=vector(0.2), window=[("hammer", 0)])
    m.no_trade("ASSET_01", 100, features=vector(0.1), embedding=(1, 0.1, 0))
    m.trade("ASSET_01", 120, position=1, window=[("hammer", 1)], features=vector(0.5))
    m.no_trade("ASSET_02", 200, asset_class="stock", embedding=(0, 1, 0))
    m.no_trade("ASSET_03", 300, window=[("hammer", 0)], features=vector(3.0))
    m.cancelled("ASSET_02", 260, asset_class="stock")  # decided long, never carried out
    for n in range(10):
        m.trade("ASSET_04", 10 + 10 * n, position=10 + n, window=[("hammer", 0)])
    m.trade("ASSET_02", 220, position=20, asset_class="stock", window=[("doji", 0)])
    m.review("ASSET_01", 140, position=30, profit=8.0)
    m.review("ASSET_03", 160, position=31, action="close", profit=-3.0)
    m.review("ASSET_04", 180, position=32, direction="short")
    # From the future: decided later, completed later, closed later.
    m.no_trade("ASSET_01", NOW + 8, window=[("hammer", 0)])
    m.no_trade("ASSET_02", NOW - 2, asset_class="stock")
    m.trade("ASSET_03", NOW - 20, position=40, closed_after=30, window=[("hammer", 0)])
    return m


def write(m: MadeUpMemory, con) -> None:
    """The made-up memory's rows into the tables, through `con` (the setup login)."""
    store = m.store
    classes = {asset: s["ASSET_CLASS"] for (_, asset, _), s in store.snapshots.items()}
    insert(
        con,
        "REF.ASSETS",
        [
            {"DATASET": m.dataset, "MASKED_ID": a, "ASSET_CLASS": c}
            for a, c in sorted(classes.items())
        ],
    )
    insert(
        con,
        "FEATURES.SNAPSHOTS",
        [
            {
                "DATASET": m.dataset,
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
    )
    insert(con, "FEATURES.PATTERNS", store.patterns)
    insert(con, "MEMORY.DECISIONS", store.decisions_table)
    insert(con, "MEMORY.OUTCOMES", store.outcomes_table)


def written_memory(sim_db, setup_login, made_up_dataset) -> MadeUpMemory:
    """A finished sim with memory over a made-up dataset, its memory written; returns the
    made-up memory, whose `store` is the in-memory stand-in holding the same."""
    dataset = made_up_dataset(days=6, assets=0)
    sim = sim_db.sim_store().create(
        {
            "DATASET": dataset,
            "KIND": "practice",
            "VARIANT": "memory_on",
            "FIRST_STEP": 97,
            "LAST_STEP": 576,
            "STARTING_VALUE": 10_000.0,
            "SETTINGS": {},
            "STATUS": "finished",
        }
    )
    m = made_up(sim, dataset)
    write(m, setup_login)
    return m
