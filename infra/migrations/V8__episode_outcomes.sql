-- Episode outcomes (spec appendix 5, section 1; appendix 6, section 3.5; ADR 0001). An episode is
-- a stored full evaluation or position review with what happened afterwards. Every outcome is a
-- fact code records as bars pass and trades close; no model writes any of them.
-- Access comes per schema from Terraform's future grants: the sim job reads and writes MEMORY.

-- One row per fact about how a decision turned out. ID: the decision's ID and the kind; it stays
-- the same in a copy of a memory. SIM is the memory the row belongs to, FIRST_WRITTEN_BY the sim
-- that wrote it.
-- KIND and VALUE:
--   'price_after_1_bar', 'price_after_4_bars', 'price_at_end_of_day': the asset's close then
--     (rescaled, as every price) and its change from the decision's close, as a share
--     ({"price": 100.2, "change": 0.002} is up 0.2%);
--   'order_carried_out': a traded full evaluation's entry ({"carried_out": true, "price": ...,
--     "value": ...}, or {"carried_out": false} when it was cancelled);
--   'position_closed': how the trade ended ({"closing_reason": 'jev', 'stop_price',
--     'forced_close' or 'sim_ended', "step_closed", "bars_after" (the asset's bars after the
--     decision), "profit" and "trading_costs" in dollars, and for a position review
--     "closed_at_this_review"}).
-- KNOWN_FROM: the step from which memory may show the fact.
CREATE TABLE MEMORY.OUTCOMES (
    ID VARCHAR NOT NULL,
    SIM NUMBER NOT NULL,
    FIRST_WRITTEN_BY NUMBER NOT NULL,
    DECISION VARCHAR NOT NULL,
    KIND VARCHAR NOT NULL,
    VALUE VARIANT NOT NULL,
    KNOWN_FROM NUMBER NOT NULL,
    PRIMARY KEY (SIM, ID)
);

-- OUTCOMES_KNOWN_FROM: the step from which all of an episode's outcomes are known, set in the step
-- that completes them; empty until then, and on every row that is not an episode. Episode search
-- returns a decision only from that step. A traded full evaluation is complete once its position
-- has fully closed; one with no trade once its three prices are in; a position review once its
-- three prices are in and its trade has closed.
ALTER TABLE MEMORY.DECISIONS ADD COLUMN OUTCOMES_KNOWN_FROM NUMBER;
