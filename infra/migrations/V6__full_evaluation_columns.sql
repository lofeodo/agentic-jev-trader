-- What a full evaluation stores on its decision (spec appendix 4, sections 5 and 13; appendix 6,
-- section 3.5). A full evaluation runs when the screen says yes: Jev picks one of seven options
-- (a long or a short with a tight, medium or wide stop price, or no trade), then says how much
-- money to put in. Its decision row is the episode, stored whether or not a trade was placed.
--
-- MEMORY.DECISIONS gains, for a full evaluation (KIND 'full_evaluation', TIER 2; empty on other
-- rows):
-- CANDIDATE_TRADES: the six trades code listed, each with its name ('long_tight_stop'),
--   direction, stop price and the stop price's distance as a share of the price. No target price.
-- ANSWERS: Jev's probabilities question by question, every copy: 'pick_1' to 'pick_5' (each copy
--   in its own shuffled order), 'size_small_first' and 'size_large_first' (mirrored), and
--   'rating' (its score from 0 to 4 and each level's probability).
-- PICK: the option code read from the pick ('long_tight_stop', ..., 'no_trade').
-- RATING: how strong Jev rated the case, 0 to 4. Recorded only: it never moves money.
-- SIZE_CHOSEN: Jev's size in dollars, the five sizes averaged with its probabilities as weights.
-- SIZE_AFTER_TRIMMING: what the risk limits left of it when the order was placed (0 if nothing).
-- LIMITED_BY: the limit that trimmed it ('trade_risk', 'position', 'exposure', ...), if any.
-- ACTION is now 'entry' when an order was placed, otherwise still 'nothing'.
-- SKIPPED_BECAUSE gains 'no_typical_move': no stop price can be set, so no trade can open.
--
-- SIM.JEV_REQUESTS.PURPOSE and SIM.CALLS.PURPOSE gain 'pick' and 'size'. SIM.ORDERS.DECISION now
-- names the decision behind every order Jev decided.
ALTER TABLE MEMORY.DECISIONS ADD COLUMN
    CANDIDATE_TRADES VARIANT,
    ANSWERS VARIANT,
    PICK VARCHAR,
    RATING FLOAT,
    SIZE_CHOSEN FLOAT,
    SIZE_AFTER_TRIMMING FLOAT,
    LIMITED_BY VARCHAR;
