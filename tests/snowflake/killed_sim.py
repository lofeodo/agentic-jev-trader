"""Run a sim and kill this program partway, as a Stop or a crash would (hand-run tests only).

    python tests/snowflake/killed_sim.py SIM_ID STEPS_PER_WRITE WHEN WRITE_NUMBER

WHEN is `mid-step` (the step is worked out but its write never starts) or `while-writing`
(inside the open transaction, after the last completed step moved and before anything commits).
The program ends with `os._exit`: no clean-up, no rollback, no closed connection.
"""

import os
import sys

from dotenv import dotenv_values

from jev_trader.sim import snowflake_store
from jev_trader.sim.runner import run_sim
from jev_trader.sim.snowflake_store import SnowflakeMarket, SnowflakeSimStore
from jev_trader.storage.snowflake import TEST_DATABASE, connect

KILLED = 9


def main(sim_id: int, steps_per_write: int, when: str, write_number: int) -> None:
    env = {**dotenv_values(".env"), **os.environ}
    con = connect("sim", database=TEST_DATABASE, env=env)
    writes = 0

    class Killing(SnowflakeSimStore):
        def write_steps(self, *args, **kwargs):
            nonlocal writes
            writes += 1
            if writes == write_number and when == "mid-step":
                os._exit(KILLED)
            return super().write_steps(*args, **kwargs)

    insert = snowflake_store._insert

    def killing_insert(*args, **kwargs):
        if writes == write_number and when == "while-writing":
            os._exit(KILLED)
        return insert(*args, **kwargs)

    snowflake_store._insert = killing_insert
    run_sim(Killing(con), SnowflakeMarket(con), sim_id, steps_per_write=steps_per_write)
    sys.exit("the sim finished without being killed")


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], int(sys.argv[4]))
