"""The Trade page and the decision trail (spec appendix 7 sections 6 and 7, appendix 8 sections
8.2 and 8.13), as the web app sees them: real HTTP requests, answered from the in-memory store.

Dormant until the slice's closing ticket: the skeleton answers with a fixed made-up answer.

The made-up dataset 7 starts on 1 March 2025: step 96 ends at midnight UTC on 2 March, and each
step is 15 minutes later. Apple's prices were rescaled by 0.5 (a real $200 is stored as 100);
Bitcoin's by 0.001.

One sim with memory holds one trade, a short in Apple (a bet that its price falls), stored the way
the sim writes it:

- step 97: the screen says yes and a full evaluation (the closer look at one asset) runs. The LLM
  picks two past episodes after 6 lookups (a 7th refused at the limit), a reply that was not a
  tool call (asked again), and an answer naming an episode it was never shown. Jev picks a short
  with a medium stop price (104, a real $208) and chooses $2,000; the trade risk limit trims it to
  $1,000.
- step 98: 10 rescaled units sold at 100 ($1,000), with 50 cents of slippage and a $1 commission.
- step 101: the position screen says no: nothing more asked, the position held on its stop price.
- step 105: the position screen says yes and a review runs: Jev adds $800, the position limit
  trims it to $500 (5 units sold at 100 at step 106).
- step 120: the end-of-session review (a stock's, with no position screen first): Jev holds.
- step 192: a 40-cent borrow fee for the night (the cost of borrowing the shares sold short).
- step 201: closed at its stop price, 15 units bought back at 104.

And a full evaluation of Bitcoin at step 110 that ended in no trade.
"""

import json
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
    messages_to_dict,
)

from jev_trader.api.app import create_app
from jev_trader.api.store import InMemoryApiStore
from jev_trader.jev.reading import load_wording
from jev_trader.llm.selection import SelectionLimits, wording_within
from jev_trader.sim.store import InMemorySimStore
from tests.unit.api.conftest import StandInBuilds, StandInLauncher

pytestmark = pytest.mark.dormant

NOW = datetime(2026, 11, 23, 12, 0)
MEMORY_SIM = (
    50  # the sim that wrote the past episodes this sim's memory was copied from
)
APPLE, BITCOIN = "ASSET_01", "ASSET_02"
JEV = load_wording()
LLM = wording_within(SelectionLimits())
ACTIONS = ("hold", "close", "reduce", "add")

# What Jev and the LLM are sent once per version: Jev's opening, the LLM's standing instructions
# and tools by job.
READING = "reading-1"
OPENING = "# The task\nYou read one asset at a time for a selective day trader."
PROMPT = "prompt-1"
SYSTEM_PROMPTS = {
    "full_evaluation": "You choose the past episodes Jev reads before a full evaluation.",
    "position_review": "You choose the past reviews Jev reads before it reviews a position.",
}
TOOLS = {
    job: [
        {
            "name": name,
            "description": f"{name} for the {job.replace('_', ' ')}.",
            "input_schema": {"type": "object", "properties": {}},
        }
        for name in (
            "search_episodes",
            "read_episodes",
            "read_track_record",
            "select_episodes",
        )
    ]
    for job in SYSTEM_PROMPTS
}

# The questions, as code words them (plain text, so they read the same in any layout).
SCREEN_Q = "Would a selective day trader act on ASSET_01 now, long or short?"
PICK_Q = "Which of these trades on ASSET_01, if any?"
SIZE_Q = "How much money should go into the short in ASSET_01?"
POSITION_SCREEN_Q = "Does the position in ASSET_01 call for action now?"
ACTION_Q = "What should the account do with the position in ASSET_01 at this step?"
ADD_Q = "How much more money should go into the position?"
BTC_SCREEN_Q = "Would a selective day trader act on ASSET_02 now, long or short?"
BTC_PICK_Q = "Which of these trades on ASSET_02, if any?"

# The backgrounds' sections, after the opening. Prices are rescaled, assets masked.
ACCOUNT = "# The account\nValue $10,000, all of it in cash."
APPLE_NOW = "# ASSET_01, a stock\nLast price 100.00, after a hammer on the last bar."
NOTES = "# Candle pattern notes\nHammer: a long lower shadow, often a turn up."
ENTRY_LINES = [
    (
        "Hammer, short, stock: 11 closed trades, 4 wins (36%), average win +$22, "
        "average loss -$15, all together -$17"
    ),
    "Bullish engulfing, short, stock: 6 closed trades, too few to show totals.",
]
# Jev reads the episodes newest first: 50-60 (step 60) before 50-40 (step 40).
ENTRY_EPISODES = {
    f"{MEMORY_SIM}-60-{BITCOIN}": "Episode 1: 9 hours ago, another asset, crypto\n"
    "Situation then: last price 61.20, after a doji.\n"
    "Decided: no trade.\n"
    "Afterwards: the price fell 0.8% by the end of the day.",
    f"{MEMORY_SIM}-40-{APPLE}": "Episode 2: 14 hours ago, same asset, stock\n"
    "Situation then: last price 98.40, after a hammer.\n"
    "Decided: short with a medium stop price (3.0% from the entry price), $1,000.\n"
    "Ended: closed at its stop price 9 bars later, -$31. At best +$12, at worst -$31.",
}
HELD = "# The account\nValue $9,998, with a short of $1,000 in ASSET_01 open."
POSITION = (
    "# Your position in ASSET_01\n"
    "Short $1,000 at 100.00, open 7 bars, -$2 so far. Stop price 104.00, 4.0% away."
)
REVIEW_LINES = [
    (
        "Hammer, short, stock: 12 closed trades, 5 wins (42%), average win +$20, "
        "average loss -$14, all together -$2"
    ),
]
REVIEW_EPISODES = {
    f"{MEMORY_SIM}-80-{APPLE}": "Episode 1: 6 hours ago, same asset, stock\n"
    "Situation then: last price 97.10, a short $8 ahead.\n"
    "Decided: hold.\n"
    "Ended: the trade closed at its stop price 5 bars later, -$12.",
}
END_OF_SESSION_LINES = [
    "Spinning top, short, stock: 3 closed trades, too few to show totals.",
]


def track_record(lines):
    footer = JEV["track_record_footer"].format(minimum=10)
    return "\n".join([JEV["track_record_heading"], *lines, footer])


def past_episodes(blocks, review=False):
    if not blocks:
        return (
            f"{JEV['past_episodes_none_heading']}\n{JEV['past_episodes_none_selected']}"
        )
    key = "review_past_episodes_heading" if review else "past_episodes_heading"
    heading = JEV[key].format(count=len(blocks))
    return "\n".join([heading, "\n\n".join(blocks)])


def sections(*parts):
    return "\n\n".join(parts)


SCREEN_BACKGROUND = sections(ACCOUNT, APPLE_NOW, NOTES)
BITCOIN_NOW = "# ASSET_02, crypto\nLast price 61.00."
PICK_BACKGROUND = sections(
    ACCOUNT,
    APPLE_NOW,
    track_record(ENTRY_LINES),
    past_episodes(list(ENTRY_EPISODES.values())),
    NOTES,
)
SIZE_BACKGROUND = sections(
    PICK_BACKGROUND,
    f"{JEV['trade_picked_heading']}\nShort, medium stop price at 104.00.",
)
POSITION_SCREEN_BACKGROUND = sections(HELD, APPLE_NOW, POSITION, NOTES)
REVIEW_BACKGROUND = sections(
    HELD,
    APPLE_NOW,
    POSITION,
    track_record(REVIEW_LINES),
    past_episodes(list(REVIEW_EPISODES.values()), review=True),
    NOTES,
)
ADD_BACKGROUND = sections(
    REVIEW_BACKGROUND, f"{JEV['decided_heading']}\n{JEV['decided_add']}"
)
END_OF_SESSION_BACKGROUND = sections(
    HELD,
    APPLE_NOW,
    POSITION,
    track_record(END_OF_SESSION_LINES),
    past_episodes([], review=True),
    NOTES,
)

# The LLM's exchange in the full evaluation, after its standing instructions.
FIRST_MESSAGE = (
    "Situation: ASSET_01, a stock, last price 100.00, after a hammer.\n"
    "E1: 14 hours ago, same asset: short, closed at its stop price, -$31.\n"
    "E2: 9 hours ago, another asset: no trade."
)
PATTERNS = (
    "hammer",
    "doji",
    "bullish engulfing",
    "shooting star",
    "spinning top",
    "belt-hold",
    "harami",
)
NOT_A_TOOL_CALL = "E1 looks closest to this hammer."
REVIEW_NOTE = "The same short, held."
NONE_FITS = "None fits."
NOTE = "E1 is the same short on the same stock."
REVIEW_FIRST_MESSAGE = (
    "Position: short ASSET_01 at 100.00, open 7 bars, -$2 so far.\n"
    "E1: 6 hours ago, same asset: held, closed at its stop price."
)
END_OF_SESSION_FIRST_MESSAGE = (
    "Position: short ASSET_01 at 100.00, open 22 bars, -$4 so far, at the session's end.\n"
    "E1: 2 days ago, another asset: closed."
)


def full_evaluation_exchange():
    lookups = [
        {"name": "search_episodes", "args": {"pattern": p}, "id": f"c{n}"}
        for n, p in enumerate(PATTERNS, start=1)
    ]
    results = [
        ToolMessage(f"No more episodes on {p}.", tool_call_id=f"c{n}")
        for n, p in enumerate(PATTERNS[:6], start=1)
    ]
    refused = ToolMessage(LLM.lookups_used_up(), tool_call_id="c7")
    answer = {
        "name": "select_episodes",
        "args": {"episode_ids": ["E1", "E2", "E9"], "note": NOTE},
        "id": "c8",
    }
    return messages_to_dict(
        [
            HumanMessage(FIRST_MESSAGE),
            AIMessage("", tool_calls=lookups),
            *results,
            refused,
            HumanMessage(LLM.answer_now_at_limit()),
            AIMessage(NOT_A_TOOL_CALL),
            HumanMessage(LLM.reask(lookups_left=False)),
            AIMessage("", tool_calls=[answer]),
        ]
    )


def answer_only_exchange(first, ids, note):
    answer = {
        "name": "select_episodes",
        "args": {"episode_ids": ids, "note": note},
        "id": "c1",
    }
    return messages_to_dict([HumanMessage(first), AIMessage("", tool_calls=[answer])])


def key_row(masked_id, name, ticker, scale):
    return {
        "DATASET": 7,
        "MASKED_ID": masked_id,
        "TICKER": ticker,
        "NAME": name,
        "PRICE_SCALE": scale,
        "FIRST_DAY": date(2025, 3, 1),
    }


@pytest.fixture
def sims():
    return InMemorySimStore()


@pytest.fixture
def store(sims):
    return InMemoryApiStore(
        sims,
        asset_key=[
            key_row(APPLE, "Apple", "AAPL", 0.5),
            key_row(BITCOIN, "Bitcoin", "BTC", 0.001),
        ],
        closes={
            7: {
                APPLE: {
                    96: 99.5,
                    98: 100.0,
                    105: 99.0,
                    120: 101.0,
                    150: 102.0,
                    201: 104.0,
                },
                BITCOIN: {96: 60.0, 110: 61.0},
            }
        },
    )


@pytest.fixture
def api(store):
    return TestClient(
        create_app(
            store,
            spending_ceiling=75.0,
            not_responding_after=timedelta(minutes=7),
            launcher=StandInLauncher(),
            builds=StandInBuilds(),
            clock=lambda: NOW,
        ),
        base_url="http://localhost",
        client=("127.0.0.1", 50000),
    )


def add_sim(sims):
    """A finished sim with memory over two days (steps 97 to 288) of dataset 7, with $10,000."""
    sim = sims.create(
        {
            "DATASET": 7,
            "KIND": "free",
            "VARIANT": "memory_on",
            "REPEAT_NUMBER": None,
            "MARKET": None,
            "FIRST_STEP": 97,
            "LAST_STEP": 288,
            "STARTING_VALUE": 10_000.0,
            "SPENDING_CAP": 1.5,
            "ESTIMATED_COST": 1.0,
            "SETTINGS": {"starting_value": 10_000.0},
        }
    )
    sims.update(sim, STATUS="finished", LAST_COMPLETED_STEP=288, LAST_WRITTEN_AT=NOW)
    return sim


def decision(sims, sim, step, asset, kind, tier, written_by=None, **columns):
    """A `MEMORY.DECISIONS` row with every column, as the sim writes it."""
    written_by = written_by or sim
    row = {
        "ID": f"{written_by}-{step}-{asset}",
        "SIM": sim,
        "FIRST_WRITTEN_BY": written_by,
        "DATASET": 7,
        "ASSET": asset,
        "STEP": step,
        "KIND": kind,
        "TIER": tier,
        "SCREEN_ANSWER": None,
        "SKIPPED_BECAUSE": None,
        "JEV_VERSION": "jev-1",
        "CANDIDATE_TRADES": None,
        "ANSWERS": None,
        "PICK": None,
        "RATING": None,
        "SIZE_CHOSEN": None,
        "SIZE_AFTER_TRIMMING": None,
        "LIMITED_BY": None,
        "ACTION": "nothing",
        "OUTCOMES_KNOWN_FROM": None,
        "LLM_MODEL": None,
        "PROMPT_VERSION": None,
        "SELECTED": None,
        "LLM_NOTE": None,
        "LIMIT_HIT": None,
        "EPISODES_SHOWN": None,
        "LOOKUPS": None,
        "MEMORIES_RELEVANT": None,
        "POSITION": None,
        "STANDING": None,
        "END_OF_SESSION": None,
        "THESIS_INTACT": None,
        "REDUCE_SHARE": None,
    }
    sims.tables["MEMORY.DECISIONS"].append({**row, **columns})
    return row["ID"]


def selection(selected, note, shown, lookups=(), limit_hit=None):
    return {
        "LLM_MODEL": "claude-haiku-5-5",
        "PROMPT_VERSION": PROMPT,
        "SELECTED": selected,
        "LLM_NOTE": note,
        "LIMIT_HIT": limit_hit,
        "EPISODES_SHOWN": [
            {
                "episode_id": episode,
                "label": f"E{n}",
                "vector_rank": n,
                "text_rank": n,
                "merged_rank": n,
                "from_first_search": True,
                "opened": False,
            }
            for n, episode in enumerate(shown, start=1)
        ],
        "LOOKUPS": list(lookups),
    }


def jev_request(sims, sim, step, asset, purpose, background, questions, answers):
    """A Jev request and its answer, word for word: the background after the opening."""
    sims.tables["SIM.JEV_REQUESTS"].append(
        {
            "ID": f"{sim}-{step}-{asset}-{purpose}",
            "SIM": sim,
            "STEP": step,
            "ASSET": asset,
            "DECISION": f"{sim}-{step}-{asset}",
            "PURPOSE": purpose,
            "READING_VERSION": READING,
            "BACKGROUND_AFTER_OPENING": background,
            "QUESTIONS": questions,
            "ANSWER": json.dumps({"answers": answers}),
            "JEV_VERSION": "jev-1",
        }
    )


def llm_exchange(sims, sim, step, asset, messages, failed_replies=()):
    sims.tables["SIM.LLM_EXCHANGES"].append(
        {
            "ID": f"{sim}-{step}-{asset}",
            "SIM": sim,
            "STEP": step,
            "ASSET": asset,
            "DECISION": f"{sim}-{step}-{asset}",
            "PROMPT_VERSION": PROMPT,
            "MESSAGES": messages,
            "FAILED_REPLIES": list(failed_replies),
            "SLIPS": [],
        }
    )


def event(sims, sim, step, kind, **details):
    number = len(sims.tables["SIM.SIM_EVENTS"])
    sims.tables["SIM.SIM_EVENTS"].append(
        {
            "ID": f"{sim}-{step}-{kind}-{number}",
            "SIM": sim,
            "STEP": step,
            "KIND": kind,
            "DETAILS": details,
        }
    )


def order(sims, sim, kind, side, step, units, price, decision_id, **columns):
    """A carried-out order of position 1 in Apple, decided at the step before."""
    sims.tables["SIM.ORDERS"].append(
        {
            "ID": f"{sim}-{step - 1}-{APPLE}-{kind}",
            "SIM": sim,
            "POSITION": 1,
            "INSTRUMENT": f"{APPLE}_SPOT",
            "DECISION": decision_id,
            "KIND": kind,
            "REASON": "jev",
            "SIDE": side,
            "STEP_DECIDED": step - 1,
            "STEP_CARRIED_OUT": step,
            "STATUS": "carried out",
            "UNITS": units,
            "PRICE_BEFORE_SLIPPAGE": price,
            "PRICE": price,
            "VALUE": units * price,
            "SLIPPAGE_COST": 0.0,
            "COMMISSION_OR_TRADING_FEE": 0.0,
            "AMOUNT_CHOSEN": None,
            "AMOUNT_AFTER_TRIMMING": None,
            "LIMITED_BY": None,
            **columns,
        }
    )


def charge(sims, sim, step, kind, amount, position):
    sims.tables["SIM.CHARGES"].append(
        {
            "ID": f"{sim}-{step}-{kind}-{position or 'loan'}",
            "SIM": sim,
            "STEP": step,
            "KIND": kind,
            "POSITION": position,
            "CHARGED_ON": 1_000.0,
            "YEARLY_RATE": 0.05,
            "AMOUNT": amount,
        }
    )


def action_copies(*copies):
    return {
        f"action_{n}": dict(zip(ACTIONS, copy, strict=True))
        for n, copy in enumerate(copies, start=1)
    }


def stored_sim(sims):
    """The sim described at the top of this file. Returns its ID."""
    sims.save_reading(READING, OPENING)
    sims.save_prompt(PROMPT, SYSTEM_PROMPTS, TOOLS)
    sim = add_sim(sims)

    # The past episodes in the memory the sim was copied from.
    decision(sims, sim, 40, APPLE, "full_evaluation", 2, written_by=MEMORY_SIM)
    decision(sims, sim, 60, BITCOIN, "full_evaluation", 2, written_by=MEMORY_SIM)
    decision(sims, sim, 80, APPLE, "position_review", 2, written_by=MEMORY_SIM)

    # Step 97: the full evaluation that opened the trade.
    shown = list(reversed(ENTRY_EPISODES))  # E1 is 50-40, E2 is 50-60
    lookups = [
        {
            "tool": "search_episodes",
            "inputs": {"pattern": p},
            "episode_ids": [],
            "latency_seconds": 0.2,
            "refused": None,
        }
        for p in PATTERNS[:6]
    ] + [
        {
            "tool": "search_episodes",
            "inputs": {"pattern": PATTERNS[6]},
            "episode_ids": [],
            "latency_seconds": 0.0,
            "refused": "lookups",
        }
    ]
    decision(
        sims,
        sim,
        97,
        APPLE,
        "full_evaluation",
        2,
        SCREEN_ANSWER=0.8,
        CANDIDATE_TRADES=[
            {
                "name": f"short_{width}_stop",
                "direction": "short",
                "stop_price": stop,
                "stop_share": stop / 100.0 - 1,
            }
            for width, stop in (("tight", 102.0), ("medium", 104.0), ("wide", 106.0))
        ],
        ANSWERS={"pick_1": {"short_medium_stop": 0.6, "no_trade": 0.4}},
        PICK="short_medium_stop",
        RATING=2.5,
        SIZE_CHOSEN=2_000.0,
        SIZE_AFTER_TRIMMING=1_000.0,
        LIMITED_BY="trade_risk",
        ACTION="entry",
        MEMORIES_RELEVANT=0.7,
        **selection(list(shown), NOTE, shown, lookups=lookups, limit_hit="lookups"),
    )
    jev_request(
        sims,
        sim,
        97,
        APPLE,
        "screen",
        SCREEN_BACKGROUND,
        {"screen": {"type": "noul", "instructions": SCREEN_Q}},
        {"screen": {"noul": 0.8}},
    )
    jev_request(
        sims,
        sim,
        97,
        APPLE,
        "pick",
        PICK_BACKGROUND,
        {
            "pick_1": {
                "type": "choice",
                "instructions": PICK_Q,
                "criteria": {
                    "short_medium_stop": "Short, medium stop price at 104.00.",
                    "no_trade": "No trade.",
                },
            }
        },
        {"pick_1": {"probabilities": {"short_medium_stop": 0.6, "no_trade": 0.4}}},
    )
    jev_request(
        sims,
        sim,
        97,
        APPLE,
        "size",
        SIZE_BACKGROUND,
        {"size_small_first": {"type": "choice", "instructions": SIZE_Q}},
        {"size_small_first": {"probabilities": {"size_2": 1.0}}},
    )
    llm_exchange(
        sims,
        sim,
        97,
        APPLE,
        full_evaluation_exchange(),
        failed_replies=[json.dumps({"content": NOT_A_TOOL_CALL, "tool_calls": []})],
    )
    event(sims, sim, 97, "an LLM limit hit", asset=APPLE, limit="lookups")
    event(sims, sim, 97, "a failed reply", asset=APPLE, number=1, why="no tool call")
    event(sims, sim, 97, "an unknown episode ID dropped", asset=APPLE, episode_id="E9")
    order(
        sims,
        sim,
        "entry",
        "sell",
        98,
        10.0,
        100.0,
        f"{sim}-97-{APPLE}",
        PRICE_BEFORE_SLIPPAGE=100.05,
        SLIPPAGE_COST=0.5,
        COMMISSION_OR_TRADING_FEE=1.0,
        AMOUNT_CHOSEN=2_000.0,
        AMOUNT_AFTER_TRIMMING=1_000.0,
        LIMITED_BY="trade_risk",
    )

    # Step 101: the position screen says no.
    decision(sims, sim, 101, APPLE, "position_screen", 1, SCREEN_ANSWER=0.2, POSITION=1)
    jev_request(
        sims,
        sim,
        101,
        APPLE,
        "position_screen",
        POSITION_SCREEN_BACKGROUND,
        {"position_screen": {"type": "noul", "instructions": POSITION_SCREEN_Q}},
        {"position_screen": {"noul": 0.2}},
    )

    # Step 105: the position screen says yes; the review adds $800, trimmed to $500.
    decision(
        sims,
        sim,
        105,
        APPLE,
        "position_review",
        2,
        SCREEN_ANSWER=0.9,
        POSITION=1,
        END_OF_SESSION=False,
        ANSWERS={
            **action_copies(
                (0.2, 0.1, 0.1, 0.6),
                (0.4, 0.1, 0.1, 0.4),
                (0.3, 0.1, 0.1, 0.5),
                (0.3, 0.1, 0.1, 0.5),
                (0.3, 0.1, 0.1, 0.5),
            ),
            "thesis_intact": 0.7,
        },
        PICK="add",
        SIZE_CHOSEN=800.0,
        SIZE_AFTER_TRIMMING=500.0,
        LIMITED_BY="position",
        ACTION="add",
        THESIS_INTACT=0.7,
        **selection(list(REVIEW_EPISODES), REVIEW_NOTE, REVIEW_EPISODES),
    )
    jev_request(
        sims,
        sim,
        105,
        APPLE,
        "position_screen",
        POSITION_SCREEN_BACKGROUND,
        {"position_screen": {"type": "noul", "instructions": POSITION_SCREEN_Q}},
        {"position_screen": {"noul": 0.9}},
    )
    jev_request(
        sims,
        sim,
        105,
        APPLE,
        "action",
        REVIEW_BACKGROUND,
        {"action_1": {"type": "choice", "instructions": ACTION_Q}},
        {
            "action_1": {
                "probabilities": {"hold": 0.2, "close": 0.1, "reduce": 0.1, "add": 0.6}
            }
        },
    )
    jev_request(
        sims,
        sim,
        105,
        APPLE,
        "add",
        ADD_BACKGROUND,
        {"add_small_first": {"type": "choice", "instructions": ADD_Q}},
        {"add_small_first": {"probabilities": {"size_1": 1.0}}},
    )
    llm_exchange(
        sims,
        sim,
        105,
        APPLE,
        answer_only_exchange(REVIEW_FIRST_MESSAGE, ["E1"], REVIEW_NOTE),
    )
    order(
        sims,
        sim,
        "add",
        "sell",
        106,
        5.0,
        100.0,
        f"{sim}-105-{APPLE}",
        SLIPPAGE_COST=0.25,
        COMMISSION_OR_TRADING_FEE=0.5,
        AMOUNT_CHOSEN=800.0,
        AMOUNT_AFTER_TRIMMING=500.0,
        LIMITED_BY="position",
    )

    # Step 120: the end-of-session review, with no position screen: hold.
    decision(
        sims,
        sim,
        120,
        APPLE,
        "position_review",
        2,
        POSITION=1,
        END_OF_SESSION=True,
        ANSWERS={**action_copies((0.7, 0.2, 0.1, 0.0)), "thesis_intact": 0.6},
        PICK="hold",
        THESIS_INTACT=0.6,
        **selection([], NONE_FITS, [f"{MEMORY_SIM}-20-{BITCOIN}"]),
    )
    jev_request(
        sims,
        sim,
        120,
        APPLE,
        "action",
        END_OF_SESSION_BACKGROUND,
        {"action_1": {"type": "choice", "instructions": ACTION_Q}},
        {
            "action_1": {
                "probabilities": {"hold": 0.7, "close": 0.2, "reduce": 0.1, "add": 0.0}
            }
        },
    )
    llm_exchange(
        sims,
        sim,
        120,
        APPLE,
        answer_only_exchange(END_OF_SESSION_FIRST_MESSAGE, [], NONE_FITS),
    )

    # The night's charges: the trade's borrow fee, the account's loan interest, another
    # position's borrow fee.
    charge(sims, sim, 192, "borrow_fee", 0.40, position=1)
    charge(sims, sim, 192, "loan_interest", 1.37, position=None)
    charge(sims, sim, 192, "borrow_fee", 0.02, position=2)

    # Step 201: closed at its stop price.
    order(
        sims,
        sim,
        "close",
        "buy",
        201,
        15.0,
        104.0,
        None,
        REASON="stop_price",
        COMMISSION_OR_TRADING_FEE=1.5,
    )

    # Step 110: a full evaluation of Bitcoin that ended in no trade.
    decision(
        sims,
        sim,
        110,
        BITCOIN,
        "full_evaluation",
        2,
        SCREEN_ANSWER=0.75,
        ANSWERS={"pick_1": {"long_tight_stop": 0.3, "no_trade": 0.7}},
        PICK="no_trade",
        **selection([], NONE_FITS, [f"{MEMORY_SIM}-60-{BITCOIN}"]),
    )
    jev_request(
        sims,
        sim,
        110,
        BITCOIN,
        "screen",
        BITCOIN_NOW,
        {"screen": {"type": "noul", "instructions": BTC_SCREEN_Q}},
        {"screen": {"noul": 0.75}},
    )
    jev_request(
        sims,
        sim,
        110,
        BITCOIN,
        "pick",
        BITCOIN_NOW,
        {"pick_1": {"type": "choice", "instructions": BTC_PICK_Q}},
        {"pick_1": {"probabilities": {"long_tight_stop": 0.3, "no_trade": 0.7}}},
    )
    llm_exchange(
        sims,
        sim,
        110,
        BITCOIN,
        answer_only_exchange("Situation: ASSET_02, crypto.", [], NONE_FITS),
    )
    return sim


def real(rescaled, scale=0.5):
    return {"real": rescaled / scale, "rescaled": rescaled}


# The Trade page


def test_the_trade_page_shows_the_trade_and_its_order_in_real_prices(sims, api):
    sim = stored_sim(sims)

    page = api.get(f"/sims/{sim}/trades/1").json()

    trade = page["trade"]
    assert trade["position"] == 1
    assert trade["decision"] == f"{sim}-97-{APPLE}"
    assert trade["asset"] == {"name": "Apple", "masked_id": APPLE}
    assert trade["direction"] == "short"
    assert trade["opened_at"] == "2025-03-02T00:30:00"
    assert trade["closed_at"] == "2025-03-03T02:15:00"
    assert trade["entry_price"] == real(100.0)
    assert trade["closing_reason"] == "stop_price"
    assert page["stop_price"] == real(104.0)  # the medium stop price Jev picked
    # Jev chose $2,000; the trade risk limit trimmed it to $1,000.
    assert page["order"] == {
        "amount_chosen_usd": 2_000.0,
        "amount_placed_usd": 1_000.0,
        "limited_by": "trade_risk",
        "slippage_usd": 0.5,
        "commission_or_fee_usd": 1.0,
    }


def test_the_trade_page_draws_the_price_around_the_trade_with_its_marks(sims, api):
    sim = stored_sim(sims)

    page = api.get(f"/sims/{sim}/trades/1").json()

    bars = {bar["step"]: bar for bar in page["bars"]}
    assert [bar["step"] for bar in page["bars"]] == sorted(bars)
    for step in (98, 105, 120, 150, 201):  # every stored close while the trade was open
        assert step in bars
    assert bars[120]["close"] == real(101.0)
    assert bars[120]["at"] == "2025-03-02T06:00:00"

    marks = {(m["kind"], m["step"]): m for m in page["marks"]}
    assert marks[("entry", 98)]["price"] == real(100.0)
    assert marks[("close", 201)]["price"] == real(104.0)
    [stop_price] = [m for m in page["marks"] if m["kind"] == "stop price"]
    assert stop_price["price"] == real(104.0)
    assert marks[("position screen", 101)]["decision"] == f"{sim}-101-{APPLE}"
    assert marks[("position review", 105)]["decision"] == f"{sim}-105-{APPLE}"
    assert marks[("position review", 120)]["decision"] == f"{sim}-120-{APPLE}"
    assert marks[("position review", 105)]["at"] == "2025-03-02T02:15:00"


def test_position_reviews_are_told_apart_from_steps_the_position_screen_said_no(
    sims, api
):
    sim = stored_sim(sims)

    steps = api.get(f"/sims/{sim}/trades/1").json()["position_steps"]

    assert [(s["step"], s["kind"], s["end_of_session"]) for s in steps] == [
        (101, "screen said no", False),
        (105, "review", False),
        (120, "review", True),
    ]
    held, added, end_of_session = steps
    # A no: nothing more was asked, so no answer and no memory of its own.
    assert held["screen_answer"] == 0.2
    assert held["decision"] == f"{sim}-101-{APPLE}"
    assert (held["answer"], held["probabilities"], held["fresh_memory"]) == (
        None,
        [],
        None,
    )
    assert held["at"] == "2025-03-02T01:15:00"
    assert added["screen_answer"] == 0.9
    assert (added["answer"], added["amount_usd"]) == ("add", 500.0)
    assert added["decision"] == f"{sim}-105-{APPLE}"
    # An end-of-session review had no position screen before it.
    assert end_of_session["screen_answer"] is None
    assert end_of_session["answer"] == "hold"
    assert end_of_session["amount_usd"] is None


def test_each_review_carries_jev_s_probabilities_averaged_over_its_copies(sims, api):
    sim = stored_sim(sims)

    steps = api.get(f"/sims/{sim}/trades/1").json()["position_steps"]

    added = {
        p["option"]: p["probability"]
        for p in steps[1]["probabilities"]
        if p["option"] in ACTIONS
    }
    assert added == pytest.approx(
        {"hold": 0.3, "close": 0.1, "reduce": 0.1, "add": 0.5}
    )
    held = {
        p["option"]: p["probability"]
        for p in steps[2]["probabilities"]
        if p["option"] in ACTIONS
    }
    assert held == pytest.approx({"hold": 0.7, "close": 0.2, "reduce": 0.1, "add": 0.0})


def test_the_trade_page_lists_only_the_trade_s_own_nightly_charges(sims, api):
    sim = stored_sim(sims)

    charges = api.get(f"/sims/{sim}/trades/1").json()["nightly_charges"]

    assert charges == [
        {
            "step": 192,
            "at": "2025-03-03T00:00:00",
            "kind": "borrow_fee",
            "amount_usd": pytest.approx(0.40),
        }
    ]


def test_the_entry_memory_is_what_jev_read_when_the_trade_opened(sims, api):
    sim = stored_sim(sims)

    memory = api.get(f"/sims/{sim}/trades/1").json()["entry_memory"]

    assert memory["decision"] == f"{sim}-97-{APPLE}"
    assert memory["scorecard_lines"] == ENTRY_LINES
    # As Jev read them: newest first, each word for word, with its stored episode ID.
    assert [(e["episode"], e["text"]) for e in memory["episodes"]] == list(
        ENTRY_EPISODES.items()
    )


def test_each_review_s_fresh_memory_is_returned_beside_the_entry_memory(sims, api):
    sim = stored_sim(sims)

    page = api.get(f"/sims/{sim}/trades/1").json()

    _, added, end_of_session = page["position_steps"]
    fresh = added["fresh_memory"]
    assert fresh["decision"] == f"{sim}-105-{APPLE}"
    assert fresh["scorecard_lines"] == REVIEW_LINES
    assert [(e["episode"], e["text"]) for e in fresh["episodes"]] == list(
        REVIEW_EPISODES.items()
    )
    # The LLM selected none at the end of the session: the lines alone.
    assert end_of_session["fresh_memory"]["scorecard_lines"] == END_OF_SESSION_LINES
    assert end_of_session["fresh_memory"]["episodes"] == []
    assert page["entry_memory"]["scorecard_lines"] == ENTRY_LINES


def test_an_unknown_trade_is_not_found(sims, api):
    sim = stored_sim(sims)
    other = add_sim(sims)

    assert api.get(f"/sims/{sim}/trades/2").status_code == 404
    assert api.get(f"/sims/{other}/trades/1").status_code == 404


# The decision trail


def trail(api, sim, step, asset=APPLE):
    response = api.get(f"/sims/{sim}/decisions/{sim}-{step}-{asset}/trail")
    assert response.status_code == 200
    return response.json()


def stop_named(found, name):
    [stop] = [s for s in found["stops"] if s["name"] == name]
    return stop


def texts(stop, sender):
    return [m["text"] for m in stop["messages"] if m["sender"] == sender]


def assert_jev_exchange(stop, background, questions, answers):
    """The stop holds Jev's request (its whole background, the opening joined back on, and each
    question's wording) and Jev's answer, all word for word."""
    sent = "\n".join(texts(stop, "code"))
    assert f"{OPENING}\n\n{background}" in sent
    for question in questions:
        assert question in sent
    assert texts(stop, "jev") == [json.dumps({"answers": a}) for a in answers]


def test_a_trade_opening_s_trail_has_six_stops_in_order(sims, api):
    sim = stored_sim(sims)

    found = trail(api, sim, 97)

    assert [s["name"] for s in found["stops"]] == [
        "screen",
        "memory",
        "pick",
        "size",
        "limits",
        "order",
    ]
    assert found["decision"] == f"{sim}-97-{APPLE}"
    assert (found["kind"], found["end_of_session"]) == ("full_evaluation", False)
    assert (found["step"], found["position"]) == (97, 1)


def test_the_screen_pick_and_size_stops_show_jev_s_requests_word_for_word(sims, api):
    sim = stored_sim(sims)

    found = trail(api, sim, 97)

    assert_jev_exchange(
        stop_named(found, "screen"),
        SCREEN_BACKGROUND,
        [SCREEN_Q],
        [{"screen": {"noul": 0.8}}],
    )
    assert_jev_exchange(
        stop_named(found, "pick"),
        PICK_BACKGROUND,
        [PICK_Q, "Short, medium stop price at 104.00."],
        [{"pick_1": {"probabilities": {"short_medium_stop": 0.6, "no_trade": 0.4}}}],
    )
    assert_jev_exchange(
        stop_named(found, "size"),
        SIZE_BACKGROUND,
        [SIZE_Q],
        [{"size_small_first": {"probabilities": {"size_2": 1.0}}}],
    )


def test_the_memory_stop_joins_the_standing_instructions_and_tools_to_the_exchange(
    sims, api
):
    sim = stored_sim(sims)

    messages = stop_named(trail(api, sim, 97), "memory")["messages"]

    instructions, tools, *exchange = messages
    assert (instructions["sender"], instructions["role"]) == ("code", "instructions")
    assert instructions["text"] == SYSTEM_PROMPTS["full_evaluation"]
    assert (tools["sender"], tools["role"]) == ("code", "tools")
    for tool in TOOLS["full_evaluation"]:
        assert tool["name"] in tools["text"]
        assert tool["description"] in tools["text"]
    # Then every stored message, in order: 1 first message, 1 reply with 7 lookups, 7 results,
    # code's message to answer now, the reply that was not a tool call, the re-ask, and the
    # answer.
    assert len(exchange) == 13
    first, lookups, *results = exchange[:9]
    assert (first["sender"], first["role"], first["text"]) == (
        "code",
        "request",
        FIRST_MESSAGE,
    )
    assert (lookups["sender"], lookups["role"]) == ("llm", "tool call")
    assert "search_episodes" in lookups["text"]
    assert all(p in lookups["text"] for p in PATTERNS)
    assert [(r["sender"], r["role"]) for r in results] == [("code", "tool result")] * 7
    assert [r["text"] for r in results] == [
        *(f"No more episodes on {p}." for p in PATTERNS[:6]),
        LLM.lookups_used_up(),
    ]
    answer_now, not_a_tool_call, reask, answer = exchange[9:]
    assert (answer_now["sender"], answer_now["text"]) == (
        "code",
        LLM.answer_now_at_limit(),
    )
    assert not_a_tool_call["sender"] == "llm"
    assert NOT_A_TOOL_CALL in not_a_tool_call["text"]
    assert (reask["sender"], reask["text"]) == ("code", LLM.reask(lookups_left=False))
    assert (answer["sender"], answer["role"]) == ("llm", "answer")
    assert "select_episodes" in answer["text"]
    assert NOTE in answer["text"]


def test_the_memory_stop_marks_a_refused_lookup_a_reply_asked_again_and_an_unshown_id(
    sims, api
):
    sim = stored_sim(sims)

    messages = stop_named(trail(api, sim, 97), "memory")["messages"]

    marked = {m["text"]: m["marks"] for m in messages if m["marks"]}
    refused = LLM.lookups_used_up()
    assert marked.pop(refused) == ["refused at the limit"]
    [(reply, reply_marks)] = [
        (text, marks) for text, marks in marked.items() if NOT_A_TOOL_CALL in text
    ]
    assert reply_marks == ["asked again"]
    del marked[reply]
    # The answer named E9, which the LLM was never shown.
    [(answer, answer_marks)] = marked.items()
    assert "E9" in answer
    assert answer_marks == ["episode never shown"]


def test_the_limits_and_order_stops_carry_the_order_s_figures(sims, api):
    sim = stored_sim(sims)

    found = trail(api, sim, 97)

    assert found["order"] == {
        "amount_chosen_usd": 2_000.0,
        "amount_placed_usd": 1_000.0,
        "limited_by": "trade_risk",
        "slippage_usd": 0.5,
        "commission_or_fee_usd": 1.0,
    }


def test_a_full_evaluation_that_ended_in_no_trade_stops_at_the_pick(sims, api):
    sim = stored_sim(sims)

    found = trail(api, sim, 110, asset=BITCOIN)

    assert [s["name"] for s in found["stops"]] == ["screen", "memory", "pick"]
    assert (found["position"], found["order"]) == (None, None)
    assert found["asset"] == {"name": "Bitcoin", "masked_id": BITCOIN}
    assert_jev_exchange(
        stop_named(found, "pick"),
        BITCOIN_NOW,
        [BTC_PICK_Q],
        [{"pick_1": {"probabilities": {"long_tight_stop": 0.3, "no_trade": 0.7}}}],
    )


def test_a_position_review_s_trail_has_its_own_stops(sims, api):
    sim = stored_sim(sims)

    found = trail(api, sim, 105)

    assert [s["name"] for s in found["stops"]] == [
        "position screen",
        "memory",
        "answer",
        "limits",
        "order",
    ]
    assert (found["kind"], found["end_of_session"]) == ("position_review", False)
    assert found["position"] == 1
    assert_jev_exchange(
        stop_named(found, "position screen"),
        POSITION_SCREEN_BACKGROUND,
        [POSITION_SCREEN_Q],
        [{"position_screen": {"noul": 0.9}}],
    )
    # Jev's answer and how much: the action, then how much to add.
    assert_jev_exchange(
        stop_named(found, "answer"),
        ADD_BACKGROUND,
        [ACTION_Q, ADD_Q],
        [
            {
                "action_1": {
                    "probabilities": {
                        "hold": 0.2,
                        "close": 0.1,
                        "reduce": 0.1,
                        "add": 0.6,
                    }
                }
            },
            {"add_small_first": {"probabilities": {"size_1": 1.0}}},
        ],
    )
    # The review's own standing instructions and tools, and its own exchange.
    memory = stop_named(found, "memory")["messages"]
    assert memory[0]["text"] == SYSTEM_PROMPTS["position_review"]
    assert TOOLS["position_review"][0]["description"] in memory[1]["text"]
    assert TOOLS["full_evaluation"][0]["description"] not in memory[1]["text"]
    assert memory[2]["text"] == REVIEW_FIRST_MESSAGE
    assert found["order"] == {
        "amount_chosen_usd": 800.0,
        "amount_placed_usd": 500.0,
        "limited_by": "position",
        "slippage_usd": 0.25,
        "commission_or_fee_usd": 0.5,
    }


def test_an_end_of_session_review_s_trail_starts_at_memory(sims, api):
    sim = stored_sim(sims)

    found = trail(api, sim, 120)

    names = [s["name"] for s in found["stops"]]
    assert names[:2] == ["memory", "answer"]
    assert "position screen" not in names
    assert (found["kind"], found["end_of_session"]) == ("position_review", True)
    assert found["order"] is None  # it held: no order
    assert_jev_exchange(
        stop_named(found, "answer"),
        END_OF_SESSION_BACKGROUND,
        [ACTION_Q],
        [
            {
                "action_1": {
                    "probabilities": {
                        "hold": 0.7,
                        "close": 0.2,
                        "reduce": 0.1,
                        "add": 0.0,
                    }
                }
            }
        ],
    )


def test_the_trail_s_text_keeps_masked_ids_and_rescaled_prices_with_the_key_beside_it(
    sims, api
):
    sim = stored_sim(sims)

    found = trail(api, sim, 97)

    every_text = "\n".join(m["text"] for s in found["stops"] for m in s["messages"])
    assert APPLE in every_text and "100.00" in every_text
    for real_word in ("Apple", "AAPL", "200.00"):
        assert real_word not in every_text
    assert {
        "masked_id": APPLE,
        "name": "Apple",
        "ticker": "AAPL",
        "price_scale": 0.5,
    } in found["key"]
    # Outside the text, the real name and date lead.
    assert found["asset"] == {"name": "Apple", "masked_id": APPLE}
    assert found["at"] == "2025-03-02T00:15:00"


def test_an_unknown_decision_is_not_found(sims, api):
    sim = stored_sim(sims)
    other = add_sim(sims)

    assert api.get(f"/sims/{sim}/decisions/{sim}-99-{APPLE}/trail").status_code == 404
    assert api.get(f"/sims/{other}/decisions/{sim}-97-{APPLE}/trail").status_code == 404
