"""Run a sim on the local Postgres and kill this program partway, as a Stop or a crash would.

    python tests/postgres/killed_sim.py SIM_ID STEPS_PER_WRITE WHEN WRITE_NUMBER

WHEN is `mid-step` (the step is worked out but its write never starts) or `while-writing` (the
write is under way: another connection holds the sim's row, so the write waits inside its open
transaction, and the program dies while it waits; this relies on the write waiting for the
sim's row, which it changes to move the last completed step). The program ends with `os._exit`: no
clean-up, no rollback, no closed connection. Run with the repo root and `src` on PYTHONPATH.
"""

import os
import sys
import threading

from jev_trader.sim.runner import run_sim
from tests.postgres.helpers import connect, database

KILLED = 9


def main(sim_id: int, steps_per_write: int, when: str, write_number: int) -> None:
    opened = database("sim")
    store = opened.sim_store()
    writes = 0

    class Killing(type(store)):
        def write_steps(self, *args, **kwargs):
            nonlocal writes
            writes += 1
            if writes == write_number:
                if when == "mid-step":
                    os._exit(KILLED)
                holder = connect("sim")
                holder.execute("BEGIN")
                holder.execute(
                    "SELECT ID FROM SIM.SIMS WHERE ID = %s FOR UPDATE", (sim_id,)
                )
                threading.Timer(2.0, os._exit, (KILLED,)).start()
            return super().write_steps(*args, **kwargs)

    run_sim(
        Killing(opened.connection),
        opened.market(),
        sim_id,
        steps_per_write=steps_per_write,
    )
    sys.exit("the sim finished without being killed")


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], int(sys.argv[4]))
