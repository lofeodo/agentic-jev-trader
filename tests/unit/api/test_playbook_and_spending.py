"""The Playbook and Spending screens' reads (spec appendix 7, section 10; appendix 8, 8.2)."""

from datetime import timedelta

from fastapi.testclient import TestClient

from jev_trader.api.app import create_app
from jev_trader.api.store import InMemoryApiStore
from jev_trader.sim.store import InMemorySimStore


def client_for(store):
    return TestClient(
        create_app(
            store, spending_ceiling=75.0, not_responding_after=timedelta(minutes=7)
        ),
        base_url="http://localhost",
        client=("127.0.0.1", 50000),
    )


def playbook_row(name, lean="bullish", version="0.6.4", pattern="CDLENGULFING"):
    return {
        "TALIB_VERSION": version,
        "PATTERN": pattern,
        "LEAN": lean,
        "NAME": name,
        "SHAPE": f"The shape of {name}.",
    }


def with_playbook(rows):
    return client_for(InMemoryApiStore(InMemorySimStore(), [], playbook=rows))


def test_the_playbook_lists_each_pattern_by_name_with_its_lean_and_shape():
    answer = with_playbook(
        [
            playbook_row("hammer", pattern="CDLHAMMER"),
            playbook_row("bearish engulfing", lean="bearish"),
            playbook_row("bullish engulfing"),
        ]
    ).get("/playbook")

    assert answer.status_code == 200
    assert answer.json() == {
        "talib_version": "0.6.4",
        "patterns": [
            {
                "name": "bearish engulfing",
                "detector": "CDLENGULFING",
                "lean": "bearish",
                "shape": "The shape of bearish engulfing.",
            },
            {
                "name": "bullish engulfing",
                "detector": "CDLENGULFING",
                "lean": "bullish",
                "shape": "The shape of bullish engulfing.",
            },
            {
                "name": "hammer",
                "detector": "CDLHAMMER",
                "lean": "bullish",
                "shape": "The shape of hammer.",
            },
        ],
    }


def test_the_playbook_shows_the_newest_talib_version_only():
    answer = with_playbook(
        [
            playbook_row("older hammer", version="0.6.10"),
            playbook_row("oldest hammer", version="0.6.9"),
            playbook_row("newest hammer", version="0.7.0"),
        ]
    ).get("/playbook")

    assert answer.json()["talib_version"] == "0.7.0"
    assert [p["name"] for p in answer.json()["patterns"]] == ["newest hammer"]


def test_an_empty_playbook_has_no_version():
    assert with_playbook([]).get("/playbook").json() == {
        "talib_version": None,
        "patterns": [],
    }


def add_sim(sims, kind, variant, market=None, repeat=None):
    return sims.create(
        {
            "DATASET": 7,
            "KIND": kind,
            "VARIANT": variant,
            "REPEAT_NUMBER": repeat,
            "MARKET": market,
            "FIRST_STEP": 97,
            "LAST_STEP": 288,
            "STARTING_VALUE": 10_000.0,
            "SPENDING_CAP": None,
            "SETTINGS": {},
        }
    )


def paid_call(sims, sim_id, service, cost, purpose="screen"):
    sims.tables["SIM.CALLS"].append(
        {
            "ID": f"call-{len(sims.tables['SIM.CALLS'])}",
            "SIM": sim_id,
            "PURPOSE": purpose,
            "SERVICE": service,
            "COST_USD": cost,
        }
    )


def test_spending_has_a_line_per_sim_in_kind_order_then_calls_outside_sims():
    sims = InMemorySimStore()
    free = add_sim(sims, "free", "memory_off")
    measured = add_sim(sims, "measurement", "memory_on", "falling market", 2)
    add_sim(sims, "practice", "memory_off")  # never called a model: no line
    paid_call(sims, free, "jev", 0.50)
    paid_call(sims, free, "jev", 0.25, purpose="pick")
    paid_call(sims, measured, "jev", 1.00)
    paid_call(sims, measured, "llm", 2.00)
    paid_call(sims, None, "llm", 1.50, purpose="benchmark")
    paid_call(sims, None, "jev", None, purpose="benchmark")  # failed: nothing paid

    answer = client_for(InMemoryApiStore(sims, [])).get("/spending")

    assert answer.status_code == 200
    assert answer.json() == {
        "spent_usd": 5.25,
        "ceiling_usd": 75.0,
        "left_usd": 69.75,
        "jev_usd": 1.75,
        "llm_usd": 3.50,
        "items": [
            {
                "kind": "measurement",
                "sim_id": measured,
                "name": "falling market / with memory / repeat 2",
                "jev_usd": 1.00,
                "llm_usd": 2.00,
                "total_usd": 3.00,
                "calls": 2,
            },
            {
                "kind": "free",
                "sim_id": free,
                "name": f"Sim {free} / without memory",
                "jev_usd": 0.75,
                "llm_usd": 0.0,
                "total_usd": 0.75,
                "calls": 2,
            },
            {
                "kind": "outside sims",
                "sim_id": None,
                "name": "benchmark",
                "jev_usd": 0.0,
                "llm_usd": 1.50,
                "total_usd": 1.50,
                "calls": 2,
            },
        ],
    }


def test_spending_before_any_paid_call_leaves_the_whole_ceiling():
    answer = client_for(InMemoryApiStore(InMemorySimStore(), [])).get("/spending")

    assert answer.json() == {
        "spent_usd": 0.0,
        "ceiling_usd": 75.0,
        "left_usd": 75.0,
        "jev_usd": 0.0,
        "llm_usd": 0.0,
        "items": [],
    }
