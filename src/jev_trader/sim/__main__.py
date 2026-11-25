"""Start or resume a sim from the command line, with no API running (spec appendix 10).

    conda run -n agentic-jev-trader python -m jev_trader.sim start --dataset 1 --variant buy_hold
    conda run -n agentic-jev-trader python -m jev_trader.sim resume 12
    conda run -n agentic-jev-trader python -m jev_trader.sim practice --dataset 1

`start` runs the holding sim over the dataset's steps after its warm-up, or over one test period
with `--market "falling market"`, or over `--first-step` to `--last-step`. `resume` carries a sim
on from its last completed step: one killed mid-step, stopped by hand, or failed.

`practice` runs the agent without memory for at most one replayed day, under the practice cap
(`practice_cap_usd` in `config/spending.toml`) or the higher `--spending-cap` given, from
`--first-step` or the first step after the warm-up. It calls Jev,
which costs money: a screen for each asset at each step, and on a yes the full evaluation's two
requests, which can open a trade (pretend money). Open positions are left to code until the
position screen is built.

`--memory-from SIM` (on `practice` and `start`) starts the agent with memory from a copy of a
finished sim's memory: on `practice`, the rehearsal's later sims start from the small memory its
first sim left. A sim with memory given none starts from the base memory, the latest finished
build-up sim's. The copy is made when the sim's job first marks it running. The agent with memory
is not built yet: until it is, the checker refuses such a sim before creating it.

Every start and resume goes through the one checker (`checker.py`): a refused sim stores
nothing (a refused resume leaves the sim as it was), and each reason is printed with its fix.
`--database TRADING_AGENT_TEST` uses the test database. It needs migrations V5 and V6 applied.

Logs in as the sim login (`SNOWFLAKE_ACCOUNT` and `SNOWFLAKE_PRIVATE_KEY_FILE_PWD` in `.env`,
the key `sim.p8` in `SNOWFLAKE_LOCAL_DIR`); Jev's key is `TYPESAFE_API_KEY` in `.env`. Output is
plain ASCII: `conda run` on Windows fails on other characters.
"""

import argparse
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from typesafe_sdk import TypeSafeError

from jev_trader.jev.client import (
    JevClient,
    JevFailed,
    JevSettings,
    load_jev_settings,
)
from jev_trader.llm.selection import LlmFailed
from jev_trader.sim.checker import (
    KINDS,
    PRACTICE_MOST_STEPS,
    VARIANTS,
    Refused,
    require_resumable,
)
from jev_trader.sim.runner import (
    DuplicateRecords,
    SimRequest,
    create_sim,
    run_sim,
)
from jev_trader.sim.snowflake_store import SnowflakeMarket, SnowflakeSimStore
from jev_trader.sim.spending import load_spending_settings
from jev_trader.sim.store import StepAlreadyWritten
from jev_trader.storage.snowflake import DATABASE, LoginNotSet, connect

REPO_ROOT = Path(__file__).resolve().parents[3]
# Steps stored per write. The holding sim calls nothing paid, so a redone batch costs nothing;
# the agent's sims will store one step per write.
HOLDING_STEPS_PER_WRITE = 960  # ten days
YES_SHARE_TO_STOP_AND_ASK = 0.30  # spec appendix 9, section 12


def steps_for(args, market) -> tuple[int, int]:
    """The sim's first and last step: given, one test period's, or everything after warm-up."""
    info = market.dataset(args.dataset)
    if args.market:
        for period in info.test_periods():
            if period.name == args.market:
                return period.first_step, period.last_step
        names = ", ".join(f'"{p.name}"' for p in info.test_periods()) or "none"
        raise ValueError(f'no test period "{args.market}"; this dataset has {names}')
    return (
        args.first_step or info.warm_up_last_step + 1,
        args.last_step or info.last_step,
    )


def practice_steps(args, market) -> tuple[int, int]:
    """One replayed day: from `--first-step`, or from the first step after the warm-up."""
    info = market.dataset(args.dataset)
    first_step = args.first_step or info.warm_up_last_step + 1
    return first_step, min(first_step + PRACTICE_MOST_STEPS - 1, info.last_step)


def start_practice(args, store, market) -> int:
    first_step, last_step = practice_steps(args, market)
    sim_id = create_sim(
        store,
        market,
        SimRequest(
            dataset=args.dataset,
            variant="memory_off" if args.memory_from is None else "memory_on",
            kind="practice",
            first_step=first_step,
            last_step=last_step,
            spending_cap=args.spending_cap,
            memory_from=args.memory_from,
        ),
    )
    sim = store.sim(sim_id)
    print(
        f"Practice sim {sim_id}: steps {first_step} to {last_step}, estimated "
        f"${sim['ESTIMATED_COST']:.2f}, at most ${sim['SPENDING_CAP']:.2f}."
        + memory_line(sim)
    )
    return sim_id


def memory_line(sim: dict) -> str:
    """Which memory a sim with memory starts from, for the line that announces it."""
    if sim["MEMORY_FROM_SIM"] is None:
        return ""
    return f" It starts from a copy of sim {sim['MEMORY_FROM_SIM']}'s memory."


def refusal_lines(refused: Refused) -> list[str]:
    """Each reason a sim was refused, with how to fix it."""
    lines = ["Refused:"]
    for refusal in refused.refusals:
        lines += [f"- {refusal.problem}", f"  Fix: {refusal.fix}"]
    return lines


def jev_client_for(sim: dict) -> JevClient | None:
    """The agent's sims call Jev with the settings they started with; the holding sim does not."""
    if sim["VARIANT"] == "buy_hold":
        return None
    return JevClient(JevSettings(**sim["SETTINGS"]["jev"]))


def screen_report(store, sim: dict) -> list[str]:
    """The shares of screens and of position screens that said yes, with the spec's stop-and-ask
    rule when the two together are above 30% (appendix 4, section 13), and what the full
    evaluations and position reviews did."""
    cut_off = sim["SETTINGS"]["risk_profile"]["screen_cut_off"]
    asked, yes = store.screen_counts(sim["ID"], cut_off)
    held, held_yes = store.position_screen_counts(sim["ID"], cut_off)
    lines = [
        _yes_share("Screens", asked, yes),
        _yes_share("Position screens", held, held_yes),
    ]
    if asked + held and (yes + held_yes) / (asked + held) > YES_SHARE_TO_STOP_AND_ASK:
        lines.append(
            f"Above {YES_SHARE_TO_STOP_AND_ASK:.0%} together: the developer decides what "
            "to do before any measurement sim."
        )
    evaluations, entries = store.full_evaluation_counts(sim["ID"])
    lines.append(f"Full evaluations: {evaluations}, trades opened: {entries}.")
    reviews = store.position_review_counts(sim["ID"])
    lines.append(
        f"Position reviews: {reviews['reviews']}, {reviews['end_of_session']} at the end "
        f"of a session; closed {reviews['close']}, reduced {reviews['reduce']}, "
        f"added {reviews['add']}."
    )
    return lines


def _yes_share(name: str, asked: int, yes: int) -> str:
    if not asked:
        return f"{name}: none asked."
    return f"{name}: {asked} asked, {yes} said yes ({yes / asked:.1%})."


def default_steps_per_write(sim: dict) -> int:
    """Many steps per write for the holding sim, which calls nothing paid; one otherwise."""
    return HOLDING_STEPS_PER_WRITE if sim["VARIANT"] == "buy_hold" else 1


def start_sim(args, store, market) -> int:
    first_step, last_step = steps_for(args, market)
    request = SimRequest(
        dataset=args.dataset,
        variant=args.variant,
        kind=args.kind,
        first_step=first_step,
        last_step=last_step,
        starting_value=args.starting_value,
        market=args.market,
        memory_from=args.memory_from,
    )
    sim_id = create_sim(store, market, request)
    print(
        f"Sim {sim_id}: {args.variant}, steps {first_step} to {last_step}."
        + memory_line(store.sim(sim_id))
    )
    return sim_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m jev_trader.sim")
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start", help="start a sim and run it to its last step")
    start.add_argument(
        "--dataset", type=int, required=True, help="a published dataset's ID"
    )
    start.add_argument("--variant", choices=VARIANTS, default="buy_hold")
    start.add_argument("--kind", choices=KINDS, default="practice")
    start.add_argument("--market", help="run over this test period, by name")
    start.add_argument("--first-step", type=int)
    start.add_argument("--last-step", type=int)
    start.add_argument("--starting-value", type=float, default=10_000.0)
    resume = commands.add_parser(
        "resume", help="carry a sim on from its last stored step"
    )
    resume.add_argument("sim", type=int, help="the sim's ID")
    practice = commands.add_parser(
        "practice",
        help="run the agent for one day, at most 25 cents (calls Jev): without memory, "
        "or with --memory-from",
    )
    practice.add_argument(
        "--dataset", type=int, required=True, help="a published dataset's ID"
    )
    practice.add_argument("--first-step", type=int)
    practice.add_argument(
        "--spending-cap",
        type=float,
        help="raise this sim's cap above the usual practice cap, in US dollars",
    )
    practice.add_argument("--database", default=DATABASE)
    for command in (start, practice):
        command.add_argument(
            "--memory-from",
            type=int,
            metavar="SIM",
            help="start the agent with memory from a copy of this finished sim's memory "
            "(a practice sim: the rehearsal); without it, a sim with memory starts from "
            "the base memory",
        )
    for command in (start, resume):
        command.add_argument("--database", default=DATABASE)
        command.add_argument(
            "--steps-per-write",
            type=int,
            help=f"steps stored at once (default: {HOLDING_STEPS_PER_WRITE} for buy_hold, else 1)",
        )
    args = parser.parse_args(argv)

    load_dotenv(REPO_ROOT / ".env")
    try:
        connection = connect("sim", database=args.database)
    except LoginNotSet as missing:
        print(missing)
        return 2
    store, market = SnowflakeSimStore(connection), SnowflakeMarket(connection)
    jev = None
    try:
        try:
            if args.command == "practice":
                # Checked first, so a missing key leaves no sim row behind.
                JevClient(load_jev_settings()).close()
                sim_id = start_practice(args, store, market)
            elif args.command == "start":
                sim_id = start_sim(args, store, market)
            else:
                sim_id = args.sim
            sim = store.sim(sim_id)
            if sim["STATUS"] == "finished":
                raise ValueError(f"sim {sim_id} is finished")
            if args.command == "resume":
                require_resumable(sim, store, load_spending_settings())
            jev = jev_client_for(sim)
        except Refused as refused:
            for line in refusal_lines(refused):
                print(line)
            return 2
        except (ValueError, KeyError) as refused:
            print(f"Refused: {refused}")
            return 2
        except TypeSafeError:
            print("Refused: set a valid TYPESAFE_API_KEY in .env to call Jev.")
            return 2
        began = time.monotonic()
        try:
            result = run_sim(
                store,
                market,
                sim_id,
                steps_per_write=getattr(args, "steps_per_write", None)
                or default_steps_per_write(sim),
                report=lambda line: print(line, flush=True),
                jev=jev,
            )
        except ValueError as refused:
            print(f"Refused: {refused}")
            return 2
        if jev is not None:
            for line in screen_report(store, sim):
                print(line)
            seconds = time.monotonic() - began
            print(f"Seconds a step: {seconds / max(1, result.steps_stored):.2f}.")
    except (JevFailed, LlmFailed) as failed:
        reason = str(failed).encode("ascii", "replace").decode("ascii")
        print(f"Sim {sim_id} stopped: {reason}")
        print(
            "Carry it on later with: conda run -n agentic-jev-trader "
            f"python -m jev_trader.sim resume {sim_id}"
        )
        return 1
    except StepAlreadyWritten as other_copy:
        print(f"Another copy of this sim is writing it: {other_copy}")
        return 1
    except DuplicateRecords as duplicates:
        print(
            f"Sim failed its last check: record IDs stored more than once: {duplicates}"
        )
        return 1
    finally:
        if jev is not None:
            jev.close()
        connection.close()
    if result.stopped_by_cap:
        print(f"Sim {sim_id} stopped at its spending cap.")
        return 0
    print(
        f"Sim {sim_id} finished: ending account value ${result.ending_value:,.2f}, "
        f"{result.steps_stored} steps stored in {time.monotonic() - began:,.0f} s."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
