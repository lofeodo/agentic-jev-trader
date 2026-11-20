"""Start or resume a sim from the command line, with no API running (spec appendix 10).

    conda run -n agentic-jev-trader python -m jev_trader.sim start --dataset 1 --variant buy_hold
    conda run -n agentic-jev-trader python -m jev_trader.sim resume 12

`start` runs the sim over the dataset's steps after its warm-up, or over one test period with
`--market "falling market"`, or over `--first-step` to `--last-step`. `resume` carries a sim on
from its last completed step: one killed mid-step, stopped by hand, or failed. Only the holding
sim (`buy_hold`) is built so far. `--database TRADING_AGENT_TEST` runs against the test database.

Logs in as the sim login (`SNOWFLAKE_ACCOUNT` and `SNOWFLAKE_PRIVATE_KEY_FILE_PWD` in `.env`,
the key `sim.p8` in `SNOWFLAKE_LOCAL_DIR`). Output is plain ASCII: `conda run` on Windows fails
on other characters.
"""

import argparse
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from jev_trader.sim.runner import (
    KINDS,
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
    for command in (start, resume):
        command.add_argument("--database", default=DATABASE)
        command.add_argument(
            "--steps-per-write",
            type=int,
            help=f"steps stored at once (default: {HOLDING_STEPS_PER_WRITE} for buy_hold)",
        )
    args = parser.parse_args(argv)

    load_dotenv(REPO_ROOT / ".env")
    try:
        connection = connect("sim", database=args.database)
    except LoginNotSet as missing:
        print(missing)
        return 2
    store, market = SnowflakeSimStore(connection), SnowflakeMarket(connection)
    try:
        try:
            sim_id = (
                start_sim(args, store, market) if args.command == "start" else args.sim
            )
            if store.sim(sim_id)["STATUS"] == "finished":
                raise ValueError(f"sim {sim_id} is finished")
        except (ValueError, KeyError) as refused:
            print(f"Refused: {refused}")
            return 2
        began = time.monotonic()
        result = run_sim(
            store,
            market,
            sim_id,
            steps_per_write=args.steps_per_write or HOLDING_STEPS_PER_WRITE,
            report=lambda line: print(line, flush=True),
        )
    except StepAlreadyWritten as other_copy:
        print(f"Another copy of this sim is writing it: {other_copy}")
        return 1
    except DuplicateRecords as duplicates:
        print(
            f"Sim failed its last check: record IDs stored more than once: {duplicates}"
        )
        return 1
    finally:
        connection.close()
    print(
        f"Sim {sim_id} finished: ending account value ${result.ending_value:,.2f}, "
        f"{result.steps_stored} steps stored in {time.monotonic() - began:,.0f} s."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
