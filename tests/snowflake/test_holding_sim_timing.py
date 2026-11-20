"""How long a one-year holding sim takes to store (spec appendix 6, section 3.4). Hand-run.

About 35,000 steps. Storing each as its own write is timed on 100 steps and scaled up to the
year; storing ten days per write is timed on the whole year. Run with `-s` to see the figures:

    conda run -n agentic-jev-trader python -m pytest tests/snowflake/test_holding_sim_timing.py -s

Uploading the made-up year of bars as the builder takes a few minutes before the timing starts.
"""

import time

from jev_trader.sim.runner import SimRequest, create_sim, run_sim
from jev_trader.sim.snowflake_store import SnowflakeMarket, SnowflakeSimStore

YEAR_STEPS = 365 * 96
TIMED_ONE_BY_ONE = 100
TEN_DAYS = 960


def test_time_to_store_a_one_year_holding_sim(sim_login, made_up_dataset, remove_sims):
    dataset_id = made_up_dataset(days=366, assets=2)  # day 1 is the warm-up
    store, market = SnowflakeSimStore(sim_login), SnowflakeMarket(sim_login)

    def timed(last_step, steps_per_write):
        request = SimRequest(
            dataset=dataset_id,
            variant="buy_hold",
            kind="practice",
            first_step=97,
            last_step=last_step,
        )
        sim_id = create_sim(store, market, request)
        remove_sims.append(sim_id)
        began = time.monotonic()
        result = run_sim(store, market, sim_id, steps_per_write=steps_per_write)
        return time.monotonic() - began, result.steps_stored

    seconds, steps = timed(96 + TIMED_ONE_BY_ONE, steps_per_write=1)
    one_by_one_year = seconds / steps * YEAR_STEPS
    bulk_seconds, bulk_steps = timed(96 + YEAR_STEPS, steps_per_write=TEN_DAYS)

    print(
        f"\nOne step per write: {seconds:.1f} s for {steps} steps, "
        f"{seconds / steps:.2f} s a step; a year would take about "
        f"{one_by_one_year / 3600:.1f} h."
        f"\nTen days per write: {bulk_seconds:.1f} s for the year's {bulk_steps} steps."
    )
    assert bulk_steps == YEAR_STEPS
    assert bulk_seconds < 3600
