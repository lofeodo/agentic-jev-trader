"""The holding sim (`buy_hold`) from start to finish, on the in-memory store.

It puts equal money into each asset at the first step, pays the usual costs, holds, and sells
everything at the last step (spec appendix 1, section 6; ADR 0009).
"""

from dataclasses import replace

import pytest

from jev_trader.sim.runner import SimRequest, create_sim, run_sim
from jev_trader.sim.store import InMemorySimStore


def holding_sim(store, market, **changes):
    request = SimRequest(
        dataset=7,
        variant="buy_hold",
        kind="practice",
        first_step=97,
        last_step=288,
        starting_value=10_000.0,
    )
    return create_sim(store, market, replace(request, **changes))


def test_the_holding_sim_buys_at_the_first_step_and_ends_in_cash(market):
    store = InMemorySimStore()
    sim_id = holding_sim(store, market)

    result = run_sim(store, market, sim_id)

    # $5,000 per asset, made smaller to leave room for costs, down to the cent:
    #   stock:  $4,999 of stock + $1 commission                      -> $5,000.00
    #   crypto: $4,995 of crypto + 0.1% fee ($4.995)                 -> $4,999.995
    # leaving $0.005 of cash. Both buy at an open of 100 plus 0.05% slippage (100.05).
    # At the last step each sells at its last close less 0.05% slippage:
    #   stock:  4,999 / 100.05 units x 119.94 = $5,992.80, less $1        -> $5,991.80
    #   crypto: 4,995 / 100.05 units x 109.945 = $5,489.01, less 0.1%     -> $5,483.52
    assert result.ending_value == pytest.approx(11_475.33, abs=0.01)
    sim = store.sim(sim_id)
    assert (sim["STATUS"], sim["STOP_REASON"]) == ("finished", "finished")
    assert sim["LAST_COMPLETED_STEP"] == 288


def test_the_orders_are_four_purchases_and_four_final_sales(market):
    store = InMemorySimStore()
    sim_id = holding_sim(store, market)
    run_sim(store, market, sim_id)

    orders = sorted(
        (
            o["SIDE"],
            o["INSTRUMENT"],
            o["REASON"],
            o["STEP_DECIDED"],
            o["STEP_CARRIED_OUT"],
        )
        for o in store.rows("SIM.ORDERS", sim_id)
    )
    # Decided at the first step; each carried out at its asset's next bar: the crypto at the
    # next step, the stock at the next morning's open.
    assert orders == [
        ("buy", "ASSET_01_SPOT", "buy_hold", 97, 151),
        ("buy", "ASSET_02_SPOT", "buy_hold", 97, 98),
        ("sell", "ASSET_01_SPOT", "sim_ended", 288, 288),
        ("sell", "ASSET_02_SPOT", "sim_ended", 288, 288),
    ]
    assert {o["STATUS"] for o in store.rows("SIM.ORDERS", sim_id)} == {"carried out"}


def test_the_holding_sim_never_owes_so_pays_no_nightly_charge(market):
    store = InMemorySimStore()
    sim_id = holding_sim(store, market)
    run_sim(store, market, sim_id)

    assert store.rows("SIM.CHARGES", sim_id) == []


def test_an_asset_is_looked_at_only_where_it_has_a_bar(make_market):
    # Stocks only: the sim stores its first and last steps, and the steps with a stock bar.
    market = make_market(assets=("ASSET_01",))
    store = InMemorySimStore()
    sim_id = holding_sim(store, market)
    run_sim(store, market, sim_id)

    steps = [r["STEP"] for r in store.rows("SIM.ACCOUNT_STEPS", sim_id)]
    assert steps == [97, *range(151, 177), *range(247, 273), 288]


def test_every_step_with_a_bar_stores_the_account(market):
    store = InMemorySimStore()
    sim_id = holding_sim(store, market)
    run_sim(store, market, sim_id)

    rows = store.rows("SIM.ACCOUNT_STEPS", sim_id)
    assert [r["STEP"] for r in rows] == list(range(97, 288 + 1))
    assert rows[-1]["EXPOSURE"] == 0.0
    assert rows[-1]["CASH"] == pytest.approx(11_475.33, abs=0.01)


def test_storing_many_steps_at_once_stores_the_same_records(market):
    one_by_one, in_bulk = InMemorySimStore(), InMemorySimStore()
    run_sim(one_by_one, market, holding_sim(one_by_one, market), steps_per_write=1)
    run_sim(in_bulk, market, holding_sim(in_bulk, market), steps_per_write=50)

    assert one_by_one.all_rows() == in_bulk.all_rows()


def test_a_sim_cannot_start_on_a_dataset_that_is_not_published(make_market):
    market = make_market(status="being built")
    with pytest.raises(ValueError, match="not published"):
        holding_sim(InMemorySimStore(), market)


def test_no_sim_runs_in_the_warm_up_period(market):
    with pytest.raises(ValueError, match="warm-up"):
        holding_sim(InMemorySimStore(), market, first_step=50)


def test_the_holding_sim_may_replay_test_period_days_whatever_its_kind(market):
    # It decides nothing and is shared by the measurement sims on those days (checker.py).
    store = InMemorySimStore()
    run_sim(store, market, holding_sim(store, market, kind="free"))

    assert store.sim(1)["STATUS"] == "finished"
