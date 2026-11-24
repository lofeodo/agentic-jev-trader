-- What an open position's decisions store (spec appendix 4, sections 3.2 and 7; appendix 6,
-- section 4). A position is a holding not sold yet: $4,000 of a stock bought and still held. At
-- every step Jev answers a quick yes-or-no about it (the position screen, KIND 'position_screen');
-- on a yes, or always at a stock's second-to-last bar of the session (the end-of-session review),
-- a position review runs (KIND 'position_review', TIER 2): Jev decides to hold, close, reduce
-- (sell part) or add (put more money in). Each review's decision row is its episode.
--
-- MEMORY.DECISIONS gains, empty on the rows of an asset with no position:
-- POSITION: the position looked at (the broker's ID for it, as in SIM.ORDERS.POSITION).
-- STANDING: how the position stood at a review: direction, dollars put in, bars open, profit or
--   loss so far after trading costs (dollars and percent), the stop price's distance as a share
--   of the price, and its best and worst point so far.
-- END_OF_SESSION: whether the review was an end-of-session review (it then has no SCREEN_ANSWER).
-- THESIS_INTACT: Jev's probability that the reason for opening the position still holds.
--   Recorded only: it never moves money.
-- REDUCE_SHARE: the share of the position closed after a reduce, from 0 to 1 (0.375 is three
--   eighths).
--
-- On a review the existing columns hold: SCREEN_ANSWER the position screen's answer; ANSWERS
-- 'action_1' to 'action_5' (shuffled copies), 'thesis_intact', and after a reduce or an add
-- 'reduce_small_first' and 'reduce_large_first' or 'add_small_first' and 'add_large_first'; PICK
-- the action decided ('hold', 'close', 'reduce', 'add'); SIZE_CHOSEN, SIZE_AFTER_TRIMMING and
-- LIMITED_BY after an add. ACTION gains 'close', 'reduce' and 'add'. At a stock's last bar of the
-- session nothing is asked: TIER 0, SKIPPED_BECAUSE 'session_end'.
--
-- SIM.JEV_REQUESTS.PURPOSE and SIM.CALLS.PURPOSE gain 'position_screen', 'action', 'reduce' and
-- 'add'. SIM.SIMS.ACCOUNT_STATE gains 'agent': each open position's situation at entry and its
-- journal, so a resumed sim carries on the same.
ALTER TABLE MEMORY.DECISIONS ADD COLUMN
    POSITION NUMBER,
    STANDING VARIANT,
    END_OF_SESSION BOOLEAN,
    THESIS_INTACT FLOAT,
    REDUCE_SHARE FLOAT;
