"""Start or resume a sim from the command line, with no API running (spec appendix 10).

    conda run -n agentic-jev-trader python -m jev_trader.sim start --dataset 1 --variant buy_hold
    conda run -n agentic-jev-trader python -m jev_trader.sim resume 12
    conda run -n agentic-jev-trader python -m jev_trader.sim practice --dataset 1

`start` runs the holding sim over the dataset's steps after its warm-up, or over one test period
with `--market "falling market"`, or over `--first-step` to `--last-step`. `resume` carries a sim
on from its last completed step: one killed mid-step, stopped by hand, or failed.

`practice` runs the agent without memory for at most one replayed day and 25 cents, from
`--first-step` or the first step after the warm-up. It calls Jev, which costs money: for now it
only asks the screen, about a cent a day. `--database TRADING_AGENT_TEST` uses the test database.

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
from jev_trader.sim.runner import (
    KINDS,
    PRACTICE_MOST_STEPS,
    PRACTICE_SPENDING_CAP,
    VARIANTS,
    DuplicateRecords,
    SimRequest,
    create_sim,
    run_sim,
)
from jev_trader.sim.snowflake_store import SnowflakeMarket, SnowflakeSimStore
from jev_trader.sim.store import StepAlreadyWritten
from jev_trader.storage.snowflake import DATABASE, LoginNotSet, connect

REPO_ROOT = Path(__file__).resolve().parents[3]
# Steps stored per write. The holding sim calls nothing paid, so a redone batch costs nothing;
# the agent's sims will store one step per write.
HOLDING_STEPS_PER_WRITE = 960  # ten days


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
            variant="memory_off",
            kind="practice",
            first_step=first_step,
            last_step=last_step,
        ),
    )
    print(
        f"Practice sim {sim_id}: steps {first_step} to {last_step}, "
        f"at most ${PRACTICE_SPENDING_CAP:.2f}."
    )
    return sim_id


def jev_client_for(sim: dict) -> JevClient | None:
    """The agent's sims call Jev with the settings they started with; the holding sim does not."""
    if sim["VARIANT"] == "buy_hold":
        return None
    return JevClient(JevSettings(**sim["SETTINGS"]["jev"]))


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
    )
    sim_id = create_sim(store, market, request)
    print(f"Sim {sim_id}: {args.variant}, steps {first_step} to {last_step}.")
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
        help="run the agent without memory for one day, at most 25 cents (calls Jev)",
    )
    practice.add_argument(
        "--dataset", type=int, required=True, help="a published dataset's ID"
    )
    practice.add_argument("--first-step", type=int)
    practice.add_argument("--database", default=DATABASE)
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
            jev = jev_client_for(sim)
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
    except JevFailed as failed:
        print(f"Sim {sim_id} stopped: {failed}")
        print(f"Carry it on later with: python -m jev_trader.sim resume {sim_id}")
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
